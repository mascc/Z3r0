"""Per-conversation Agent runtime: turn execution and pool lifecycle."""

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agents import Runner
from agents.stream_events import AgentUpdatedStreamEvent

from config import get_config
from core.agent.registry import AgentRegistry, AgentToolSnapshot, SessionAgentGraph
from core.runtime.context import AgentRuntimeContext, main_agent_instance_id
from core.runtime.events import SdkStreamEventNormalizer
from core.runtime.input_items import build_user_message_item, display_text_from_content, text_input_content
from core.runtime.live_projection import LiveEventProjection
from core.runtime.partial_context import DeltaBuffer, flush_partial_context, track_delta
from core.conversation.store import Z3r0Session
from core.delegation.subagents import cancel_sandbox_subagent_runs, cancel_session_subagent_runs
from core.sandbox.command_jobs import cancel_sandbox_async_commands, cancel_session_async_sandbox_commands
from core.delegation.notifications import notification_prompt
from database import get_engine
from logger import get_logger
from schema.agent.events import (
    AgentEventSchema,
    DoneEvent,
    ErrorEvent,
    RunStateEvent,
    UserMessageEvent,
)
from schema.agent.events import AgentInputPart
from schema.agent.notifications import AgentNotificationSnapshot
from service.agent import notifications as agent_notifications


logger = get_logger(__name__)

_SUBSCRIBER_QUEUE_SIZE = 512


class AgentSession:
    def __init__(self, session_id: str, registry: AgentRegistry) -> None:
        self.session_id = session_id
        self._registry = registry
        self._start_lock = asyncio.Lock()
        self._turn_lock = asyncio.Lock()
        self._current_task: asyncio.Task | None = None
        self._subscribers: set[asyncio.Queue[AgentEventSchema]] = set()
        self._live_projection = LiveEventProjection()
        self._main_agent_code: str = ""
        self._tool_snapshot: AgentToolSnapshot | None = None
        self._agent_graph: SessionAgentGraph | None = None

    def is_running(self) -> bool:
        task = self._current_task
        return task is not None and not task.done()

    def has_subscribers(self) -> bool:
        return bool(self._subscribers)

    async def subscribe(self) -> asyncio.Queue[AgentEventSchema]:
        queue: asyncio.Queue[AgentEventSchema] = asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_SIZE)
        if self.is_running():
            for event in self._live_projection.snapshot():
                _put_nowait_drop_oldest(queue, event)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[AgentEventSchema]) -> None:
        self._subscribers.discard(queue)

    async def start_turn(self, content: list[AgentInputPart], agent_code: str, context: AgentRuntimeContext) -> None:
        async with self._start_lock:
            if self.is_running():
                await self.interrupt()
            await _mark_session_running(
                self.session_id,
                agent_code=agent_code,
                sandbox_container_id=context.sandbox_container_id,
                sandbox_container_generation=context.sandbox_container_generation,
            )
            self._begin_live_projection()
            task = asyncio.create_task(
                self._run_background_turn(content, agent_code, context),
                name=f"agent-turn-{self.session_id}",
            )
            self._current_task = task

    async def start_notification_drain(
        self,
        context: AgentRuntimeContext,
        *,
        target_agent_instance_id: str | None = None,
    ) -> bool:
        async with self._start_lock:
            if self.is_running():
                return False
            if not await self.has_pending_notification(target_agent_instance_id=target_agent_instance_id):
                return False
            await _mark_session_running(
                self.session_id,
                agent_code=context.agent_code,
                sandbox_container_id=context.sandbox_container_id,
                sandbox_container_generation=context.sandbox_container_generation,
            )
            self._begin_live_projection()
            task = asyncio.create_task(
                self._run_background_notifications(context, target_agent_instance_id=target_agent_instance_id),
                name=f"agent-notifications-{self.session_id}",
            )
            self._current_task = task
            return True

    async def _claim_and_run_notification(
        self,
        context: AgentRuntimeContext,
        *,
        target_agent_instance_id: str | None = None,
    ) -> AsyncIterator[AgentEventSchema]:
        notification = await agent_notifications.claim_next_pending_notification(
            session_id=self.session_id,
            target_agent_instance_id=target_agent_instance_id,
        )
        if notification is None:
            return
        agent_code = notification.target_agent_code
        notification_context = _context_for_notification(context, notification)
        saw_error = False
        try:
            async for event in self._run_turn(
                text_input_content(notification_prompt(notification)),
                agent_code,
                notification_context,
                emit_user_message=False,
            ):
                if isinstance(event, ErrorEvent):
                    saw_error = True
                yield _tag_notification_event(event, notification_context)
        except asyncio.CancelledError:
            await agent_notifications.release_notification(notification.id)
            raise
        except GeneratorExit:
            await agent_notifications.release_notification(notification.id)
            raise
        except Exception as exc:
            await agent_notifications.fail_notification(notification.id, str(exc) or "notification handling failed")
            raise
        else:
            if saw_error:
                await agent_notifications.fail_notification(notification.id, "notification handling produced an error")
            else:
                await agent_notifications.complete_notification(notification.id)

    async def has_pending_notification(self, *, target_agent_instance_id: str | None = None) -> bool:
        if target_agent_instance_id is None:
            return await agent_notifications.has_pending_main_agent_notification(session_id=self.session_id)
        return await agent_notifications.has_pending_notification(
            session_id=self.session_id,
            target_agent_instance_id=target_agent_instance_id,
        )

    async def interrupt(self) -> bool:
        task = self._current_task
        if task is None or task.done():
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await _mark_session_stopped(self.session_id)
        await self._publish(DoneEvent(created_at=datetime.now()))
        await self._publish_idle_if_inactive()
        return True

    async def cancel_all(self) -> bool:
        task = self._current_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await _mark_session_stopped(self.session_id)
            await self._publish(DoneEvent(created_at=datetime.now()))
        canceled_subagents = await cancel_session_subagent_runs(self.session_id)
        canceled_commands = await cancel_session_async_sandbox_commands(self.session_id)
        canceled_notifications = await agent_notifications.cancel_session_notifications(
            self.session_id,
            "Agent session tasks canceled by user.",
        )
        await _force_mark_session_stopped(self.session_id)
        await self._publish_run_state(False)
        return canceled_subagents or canceled_commands or bool(canceled_notifications)

    async def shutdown(self) -> None:
        await self.cancel_all()
        self.close()

    def close(self) -> None:
        self._dispose_agent_graph()

    def uses_sandbox_container(self, container_id: int) -> bool:
        return self._tool_snapshot is not None and self._tool_snapshot.sandbox_container_id == container_id

    async def invalidate_tool_binding(self) -> None:
        await self.cancel_all()
        self._tool_snapshot = None
        self._dispose_agent_graph()

    async def _run_turn(
        self,
        content: list[AgentInputPart],
        agent_code: str,
        context: AgentRuntimeContext,
        *,
        emit_user_message: bool = True,
    ) -> AsyncIterator[AgentEventSchema]:
        graph = self._ensure_agent_graph(agent_code, context)
        context.agent_code = agent_code
        if not context.agent_instance_id:
            context.agent_instance_id = main_agent_instance_id(context.session_id, context.user.id, agent_code)
        agent = graph.get(agent_code)
        display_text = display_text_from_content(content)
        if emit_user_message:
            yield UserMessageEvent(
                created_at=datetime.now(),
                content=content,
                display_text=display_text,
                target_agent_code=agent_code,
            )

        memory_session = Z3r0Session(
            session_id=self.session_id,
            engine=get_engine(),
            viewing_agent_code=agent_code,
            agent_code_to_name=graph.code_to_name(),
            nested_for_agent_code=context.nested_for_agent_code,
            nested_call_id=context.nested_call_id,
        )
        # SDK stream events converge into one queue for this turn
        queue: asyncio.Queue[AgentEventSchema | None] = asyncio.Queue()

        result_holder: dict[str, Any] = {"result": None}
        buffers: dict[str, DeltaBuffer] = {}

        async def _consume_main() -> None:
            try:
                normalizer = SdkStreamEventNormalizer()
                max_turns = get_config().agent_runtime.main_max_turns
                user_input = [build_user_message_item(content)]
                agent_config = get_config().agents.get(agent_code)
                if agent_config is not None:
                    await memory_session.compact_if_needed(
                        agent_config=agent_config,
                        incoming_items=user_input,
                    )
                stream = Runner.run_streamed(
                    starting_agent=agent,
                    session=memory_session,
                    input=user_input,
                    context=context,
                    max_turns=max_turns,
                )
                result_holder["result"] = stream
                async def _consume_stream_events() -> None:
                    sdk_events = stream.stream_events().__aiter__()
                    timeout = get_config().agent_runtime.model_stream_idle_timeout_seconds
                    while True:
                        try:
                            sdk_event = await asyncio.wait_for(sdk_events.__anext__(), timeout=timeout)
                        except StopAsyncIteration:
                            break
                        if isinstance(sdk_event, AgentUpdatedStreamEvent):
                            continue
                        event = normalizer.event_from_sdk_stream(sdk_event, agent.name)
                        if event is not None:
                            queue.put_nowait(event)

                await _consume_stream_events()
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                message = "model stream was idle for too long before returning output"
                logger.warning("agent stream idle timeout session=%s agent=%s", self.session_id, agent_code)
                queue.put_nowait(ErrorEvent(created_at=datetime.now(), agent_name=agent.name, message=message))
            except Exception as exc:
                logger.exception("agent stream failed: %s", exc)
                queue.put_nowait(ErrorEvent(created_at=datetime.now(), agent_name=agent.name, message=str(exc)))
            finally:
                queue.put_nowait(None)

        main_task = asyncio.create_task(_consume_main(), name="agent-main-stream")

        flush_partial = False
        stream_finished = False
        try:
            while True:
                event = await queue.get()
                if event is None:
                    stream_finished = True
                    break
                track_delta(buffers, event)
                yield event
            if not main_task.done():
                try:
                    await main_task
                except (asyncio.CancelledError, Exception):
                    pass
            yield DoneEvent(created_at=datetime.now(), agent_name=agent.name)
        except asyncio.CancelledError:
            flush_partial = True
            if not main_task.done():
                main_task.cancel()
            raise
        finally:
            if not stream_finished and not main_task.done():
                main_task.cancel()
                try:
                    await main_task
                except (asyncio.CancelledError, Exception):
                    pass
            if flush_partial:
                await flush_partial_context(
                    result_holder["result"],
                    memory_session,
                    buffers,
                    log_label="agent",
                )

    def _ensure_agent_graph(self, agent_code: str, context: AgentRuntimeContext) -> SessionAgentGraph:
        tool_snapshot = AgentToolSnapshot.from_context(context)
        if (
            self._agent_graph is None
            or self._main_agent_code != agent_code
            or self._tool_snapshot != tool_snapshot
        ):
            self._dispose_agent_graph()
            self._main_agent_code = agent_code
            self._tool_snapshot = tool_snapshot
            self._agent_graph = self._registry.bind(tool_snapshot)
            logger.debug(
                "agent graph bound session=%s agent=%s knowledge_generation=%d sandbox=%s generation=%d",
                self.session_id,
                agent_code,
                tool_snapshot.knowledge_generation,
                tool_snapshot.sandbox_container_id,
                tool_snapshot.sandbox_container_generation,
            )
        return self._agent_graph

    def _dispose_agent_graph(self) -> None:
        if self._agent_graph is None:
            return
        self._agent_graph.close()
        self._agent_graph = None
        self._main_agent_code = ""

    async def _run_background_turn(
        self,
        content: list[AgentInputPart],
        agent_code: str,
        context: AgentRuntimeContext,
    ) -> None:
        should_drain_notifications = False
        async with self._turn_lock:
            task = asyncio.current_task()
            self._current_task = task
            saw_done = False
            canceled = False
            try:
                async for event in self._run_turn(content, agent_code, context):
                    if isinstance(event, DoneEvent):
                        saw_done = True
                    await self._publish(event)
                should_drain_notifications = True
            except asyncio.CancelledError:
                canceled = True
                raise
            except Exception as exc:
                logger.exception("agent background turn failed session=%s", self.session_id)
                await _force_mark_session_stopped(self.session_id, error=str(exc) or "agent turn failed")
                await self._publish(ErrorEvent(created_at=datetime.now(), message=str(exc) or "agent turn failed"))
            finally:
                if not saw_done and not canceled:
                    await self._publish(DoneEvent(created_at=datetime.now()))
                if saw_done:
                    await _mark_session_stopped(self.session_id)
                if self._current_task is task:
                    self._current_task = None
                if not canceled:
                    await self._publish_idle_if_inactive()
        if should_drain_notifications:
            await self.start_notification_drain(context)

    async def _run_background_notifications(
        self,
        context: AgentRuntimeContext,
        *,
        target_agent_instance_id: str | None = None,
    ) -> None:
        async with self._turn_lock:
            task = asyncio.current_task()
            self._current_task = task
            failed = False
            try:
                while True:
                    if not await self.has_pending_notification(target_agent_instance_id=target_agent_instance_id):
                        break
                    saw_done = False
                    async for event in self._claim_and_run_notification(
                        context,
                        target_agent_instance_id=target_agent_instance_id,
                    ):
                        if isinstance(event, DoneEvent):
                            saw_done = True
                        await self._publish(event)
                    if not saw_done:
                        await self._publish(DoneEvent(created_at=datetime.now()))
            except asyncio.CancelledError:
                raise
            except Exception:
                failed = True
                logger.exception("agent notification drain failed session=%s", self.session_id)
                await _force_mark_session_stopped(self.session_id, error="agent notification handling failed")
                await self._publish(ErrorEvent(created_at=datetime.now(), message="agent notification handling failed"))
                await self._publish(DoneEvent(created_at=datetime.now()))
            finally:
                if not failed:
                    await _mark_session_stopped(self.session_id)
                if self._current_task is task:
                    self._current_task = None
                await self._publish_idle_if_inactive()

    def _begin_live_projection(self) -> None:
        event = RunStateEvent(created_at=datetime.now(), running=True)
        self._live_projection.reset(event)
        for queue in tuple(self._subscribers):
            _put_nowait_drop_oldest(queue, event)

    async def _publish_run_state(self, running: bool) -> None:
        event = RunStateEvent(created_at=datetime.now(), running=running)
        if running:
            self._live_projection.reset(event)
        else:
            self._live_projection.apply(event)
        for queue in tuple(self._subscribers):
            _put_nowait_drop_oldest(queue, event)
        if not running:
            self._live_projection.reset(event)

    async def _publish_idle_if_inactive(self) -> None:
        if self.is_running() or await _has_active_session_runtime(self.session_id):
            return
        await self._publish_run_state(False)

    async def _publish(self, event: AgentEventSchema) -> None:
        self._live_projection.apply(event)
        for queue in tuple(self._subscribers):
            _put_nowait_drop_oldest(queue, event)


@dataclass
class _PooledSession:
    session: AgentSession
    last_used_at: float = field(default_factory=time.monotonic)


class AgentSessionPool:
    def __init__(self, registry: AgentRegistry | None = None) -> None:
        cfg = get_config().agent_pool
        self._registry = registry or AgentRegistry()
        self._max_size = cfg.max_size
        self._ttl = cfg.ttl_seconds
        self._sweep_interval = cfg.sweep_interval_seconds
        self._pool: dict[str, _PooledSession] = {}
        self._sweeper_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    @property
    def registry(self) -> AgentRegistry:
        return self._registry

    async def start(self) -> None:
        if self._sweeper_task is not None and not self._sweeper_task.done():
            return
        self._sweeper_task = asyncio.create_task(self._sweep_loop(), name="agent-pool-sweeper")
        logger.debug(
            "agent pool started (ttl=%ds, interval=%ds, max_size=%d)",
            self._ttl, self._sweep_interval, self._max_size,
        )

    async def stop(self) -> None:
        task, self._sweeper_task = self._sweeper_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            entries = list(self._pool.values())
            session_ids = list(self._pool.keys())
            self._pool.clear()
        await asyncio.gather(*(entry.session.shutdown() for entry in entries), return_exceptions=True)
        await _mark_sessions_stopped(session_ids)
        logger.debug("agent pool stopped")

    async def get_or_create(self, session_id: str) -> AgentSession:
        async with self._lock:
            return self._get_or_create_locked(session_id)

    def _get_or_create_locked(self, session_id: str) -> AgentSession:
        entry = self._pool.get(session_id)
        if entry is None:
            entry = _PooledSession(session=AgentSession(session_id, self._registry))
            self._pool[session_id] = entry
            logger.debug("agent pool created session=%s", session_id)
            self._enforce_capacity_locked()
        else:
            entry.last_used_at = time.monotonic()
        return entry.session

    async def discard(self, session_id: str) -> None:
        async with self._lock:
            entry = self._pool.pop(session_id, None)
        if entry is None:
            await _force_mark_session_stopped(session_id)
            return
        await entry.session.shutdown()
        logger.debug("agent pool discarded session=%s", session_id)

    async def try_interrupt(self, session_id: str) -> bool:
        async with self._lock:
            entry = self._pool.get(session_id)
        if entry is None:
            return False
        return await entry.session.interrupt()

    async def subscribe(self, session_id: str) -> tuple[AgentSession, asyncio.Queue[AgentEventSchema]]:
        session = await self.get_or_create(session_id)
        return session, await session.subscribe()

    async def drain_notifications(self, session_id: str, context: AgentRuntimeContext) -> bool:
        session = await self.get_or_create(session_id)
        return await session.start_notification_drain(context)

    async def cancel_all(self, session_id: str) -> bool:
        async with self._lock:
            entry = self._pool.get(session_id)
        if entry is None:
            canceled_subagents = await cancel_session_subagent_runs(session_id)
            canceled_commands = await cancel_session_async_sandbox_commands(session_id)
            canceled_notifications = await agent_notifications.cancel_session_notifications(
                session_id,
                "Agent session tasks canceled by user.",
            )
            await _force_mark_session_stopped(session_id)
            return canceled_subagents or canceled_commands or bool(canceled_notifications)
        return await entry.session.cancel_all()

    async def invalidate_tool_bindings(self, container_id: int | None = None) -> None:
        async with self._lock:
            entries = [
                entry for entry in self._pool.values()
                if container_id is None or entry.session.uses_sandbox_container(container_id)
            ]
        tasks = [entry.session.invalidate_tool_binding() for entry in entries]
        if container_id is not None:
            tasks.extend([
                cancel_sandbox_subagent_runs(container_id),
                cancel_sandbox_async_commands(container_id),
            ])
        if not tasks:
            return
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.debug("agent pool invalidated tool bindings container=%s count=%d", container_id, len(entries))

    async def _sweep_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._sweep_interval)
                async with self._lock:
                    self._sweep_expired_locked(time.monotonic())
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("agent pool sweep iteration failed")

    def _sweep_expired_locked(self, now: float) -> None:
        if self._ttl <= 0:
            return
        expired = [
            sid for sid, entry in self._pool.items()
            if (
                not entry.session.is_running()
                and not entry.session.has_subscribers()
                and now - entry.last_used_at > self._ttl
            )
        ]
        for sid in expired:
            entry = self._pool.pop(sid)
            entry.session.close()
            logger.debug("agent pool evicted idle session=%s", sid)

    def _enforce_capacity_locked(self) -> None:
        # only idle entries are evicted; running sessions may briefly exceed the cap
        overflow = len(self._pool) - self._max_size
        if overflow <= 0:
            return
        idle = sorted(
            (
                (sid, entry)
                for sid, entry in self._pool.items()
                if not entry.session.is_running() and not entry.session.has_subscribers()
            ),
            key=lambda kv: kv[1].last_used_at,
        )
        for sid, _ in idle[:overflow]:
            entry = self._pool.pop(sid)
            entry.session.close()
            logger.debug("agent pool evicted LRU session=%s", sid)


_pool: AgentSessionPool | None = None


def get_agent_pool() -> AgentSessionPool:
    global _pool
    if _pool is None:
        _pool = AgentSessionPool()
    return _pool


def get_agent_registry() -> AgentRegistry:
    return get_agent_pool().registry


def _put_nowait_drop_oldest(queue: asyncio.Queue[AgentEventSchema], event: AgentEventSchema) -> None:
    try:
        queue.put_nowait(event)
        return
    except asyncio.QueueFull:
        pass
    try:
        queue.get_nowait()
    except asyncio.QueueEmpty:
        pass
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        logger.debug("agent event dropped for slow subscriber")


def _context_for_notification(
    base: AgentRuntimeContext,
    notification: AgentNotificationSnapshot,
) -> AgentRuntimeContext:
    return AgentRuntimeContext(
        session_id=base.session_id,
        user=base.user,
        agent_code=notification.target_agent_code,
        agent_instance_id=notification.target_agent_instance_id,
        nested_for_agent_code=notification.nested_for_agent_code,
        nested_call_id=notification.nested_call_id,
        knowledge_generation=base.knowledge_generation,
        sandbox_container_id=notification.sandbox_container_id,
        sandbox_container_generation=notification.sandbox_container_generation,
        sandbox_skill_metadata=notification.sandbox_skill_metadata,
        work_project_id=base.work_project_id,
    )


def _tag_notification_event(event: AgentEventSchema, context: AgentRuntimeContext) -> AgentEventSchema:
    if not context.nested_for_agent_code or not hasattr(event, "nested_for"):
        return event
    return event.model_copy(update={
        "nested_for": context.nested_for_agent_code,
        "nested_call_id": context.nested_call_id,
    })


async def _mark_session_running(
    session_id: str,
    *,
    agent_code: str,
    sandbox_container_id: int | None,
    sandbox_container_generation: int,
) -> None:
    from service.agent import sessions as agent_sessions

    await agent_sessions.mark_session_running(
        session_id,
        agent_code=agent_code,
        sandbox_container_id=sandbox_container_id,
        sandbox_container_generation=sandbox_container_generation,
    )


async def _mark_session_stopped(session_id: str, *, error: str = "") -> None:
    from service.agent import sessions as agent_sessions

    await agent_sessions.mark_session_stopped(session_id, error=error)


async def _force_mark_session_stopped(session_id: str, *, error: str = "") -> None:
    from service.agent import sessions as agent_sessions

    await agent_sessions.force_mark_session_stopped(session_id, error=error)


async def _finish_session_run(session_id: str, *, error: str = "") -> None:
    from service.agent import sessions as agent_sessions

    await agent_sessions.finish_session_run(session_id, error=error)


async def _has_active_session_runtime(session_id: str) -> bool:
    from service.agent import sessions as agent_sessions

    return await agent_sessions.has_active_session_runtime(session_id)


async def _mark_sessions_stopped(session_ids: list[str], *, error: str = "") -> None:
    from service.agent import sessions as agent_sessions

    await agent_sessions.mark_sessions_stopped(session_ids, error=error)
