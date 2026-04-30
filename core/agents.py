import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from agents import Agent, Runner, TResponseInputItem, Tool
from agents.extensions.memory import SQLAlchemySession
from agents.extensions.models.litellm_model import LitellmModel
from agents.stream_events import AgentUpdatedStreamEvent
from openai.types.responses import (
    EasyInputMessageParam,
    ResponseInputMessageContentListParam,
    ResponseInputTextParam,
)

from config import WORKSPACE, get_config
from core.context import AgentRuntimeContext
from core.events import event_from_sdk_stream
from core.tools import execute_command
from database import get_engine
from logger import get_logger
from schema.agent_event_schema import (
    AgentEventSchema,
    DoneEvent,
    ErrorEvent,
    TextCompleteEvent,
    TextDeltaEvent,
    ThinkingCompleteEvent,
    ThinkingDeltaEvent,
    UserMessageEvent,
)


logger = get_logger(__name__)

_DELTA_TYPES: tuple[type, ...] = (TextDeltaEvent, ThinkingDeltaEvent)
_COMPLETE_TYPES: tuple[type, ...] = (TextCompleteEvent, ThinkingCompleteEvent)


class RootAgentFactory:
    """build (and cache) the root SDK Agent per role.

    SDK Agents are stateless w.r.t. conversation history (state lives on the
    per-session SQLAlchemySession), so a single Agent instance is safe to
    share across all session bundles for the same role."""

    def __init__(self) -> None:
        self._cache: dict[str, Agent] = {}

    def _build_subagent(self, agent_code: str, agent_name: str, allowed_tools: list[Tool] | None = None) -> Agent:
        cfg = get_config()
        agent_cfg = cfg.agents.get(agent_code)
        if agent_cfg is None:
            raise ValueError(f"agent config not found for code: {agent_code}")

        agent_path = WORKSPACE / "agents" / agent_code
        agent_soul_md = (agent_path / "SOUL.md").read_text(encoding="utf-8").strip()
        agent_agents_md = (agent_path / "AGENTS.md").read_text(encoding="utf-8").strip()
        agent = Agent(
            name=agent_name,
            model=LitellmModel(base_url=agent_cfg.base_url, api_key=agent_cfg.api_key, model=agent_cfg.model),
            instructions=f"{agent_soul_md}\n\n{agent_agents_md}",
            tools=allowed_tools or [],
        )
        return agent

    def build(self) -> Agent:
        root_agent_code = "cso"

        cached = self._cache.get(root_agent_code)
        if cached is not None:
            return cached

        cfg = get_config()
        root_agent_cfg = cfg.agents.get(root_agent_code)
        if root_agent_cfg is None:
            raise ValueError(f"agent config not found for role: {root_agent_code}")

        cse_agent = self._build_subagent(agent_code="cse", agent_name="Fr4nk", allowed_tools=[execute_command])

        root_agent_path = WORKSPACE / "agents" / root_agent_cfg.code
        root_agent_soul_md = (root_agent_path / "SOUL.md").read_text(encoding="utf-8").strip()
        root_agent_agents_md = (root_agent_path / "AGENTS.md").read_text(encoding="utf-8").strip()
        root_agent = Agent(
            name=root_agent_cfg.name,
            model=LitellmModel(
                base_url=root_agent_cfg.base_url, api_key=root_agent_cfg.api_key, model=root_agent_cfg.model,
            ),
            instructions=f"{root_agent_soul_md}\n\n{root_agent_agents_md}",
            handoffs=[
                cse_agent,
            ]
        )
        self._cache[root_agent_code] = root_agent
        return root_agent


@dataclass
class _DeltaBuffer:
    """accumulator for streaming deltas; flushed back into the SDK session as
    a partial item when a turn is interrupted"""
    is_thinking: bool
    item_id: str
    content: str = ""


class AgentSession:
    """one conversation: serializes turns and owns interrupt-safe cleanup"""

    def __init__(self, session_id: str, root_agent: Agent):
        self.session_id = session_id
        self._root_agent = root_agent
        self._turn_lock = asyncio.Lock()
        self._current_task: asyncio.Task | None = None

    def is_running(self) -> bool:
        task = self._current_task
        return task is not None and not task.done()

    async def stream_turn(
        self,
        text: str,
        context: AgentRuntimeContext,
    ) -> AsyncIterator[AgentEventSchema]:
        async with self._turn_lock:
            task = asyncio.current_task()
            self._current_task = task
            try:
                async for event in self._run_turn(text, context):
                    yield event
            finally:
                if self._current_task is task:
                    self._current_task = None

    async def interrupt(self) -> bool:
        task = self._current_task
        if task is None or task.done():
            return False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True

    async def _run_turn(
        self,
        text: str,
        context: AgentRuntimeContext,
    ) -> AsyncIterator[AgentEventSchema]:
        yield UserMessageEvent(text=text)

        memory_session = SQLAlchemySession(session_id=self.session_id, engine=get_engine())
        result = None
        current_agent = self._root_agent.name
        buffers: dict[str, _DeltaBuffer] = {}

        try:
            result = Runner.run_streamed(
                starting_agent=self._root_agent,
                session=memory_session,
                input=_build_user_input(text),
                context=context,
            )
            async for sdk_event in result.stream_events():
                if isinstance(sdk_event, AgentUpdatedStreamEvent):
                    current_agent = sdk_event.new_agent.name
                    continue

                event = event_from_sdk_stream(sdk_event, current_agent)
                if event is None:
                    continue

                _track_delta(buffers, event)
                yield event

            yield DoneEvent(agent_name=current_agent)

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("agent stream failed: %s", exc)
            yield ErrorEvent(agent_name=current_agent, message=str(exc))
        finally:
            await _flush_partial_context(result, memory_session, buffers)


@dataclass
class _PooledSession:
    session: AgentSession
    last_used_at: float = field(default_factory=time.monotonic)


class AgentSessionPool:
    """LRU/TTL cache of AgentSession bundles keyed by session_id"""

    def __init__(self, factory: RootAgentFactory | None = None):
        cfg = get_config().agent_pool
        self._factory = factory or RootAgentFactory()
        self._max_size = cfg.max_size
        self._ttl = cfg.ttl_seconds
        self._sweep_interval = cfg.sweep_interval_seconds
        self._pool: dict[str, _PooledSession] = {}
        self._sweeper_task: asyncio.Task | None = None

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

        entries = list(self._pool.values())
        self._pool.clear()
        await asyncio.gather(*(entry.session.interrupt() for entry in entries), return_exceptions=True)
        logger.debug("agent pool stopped")

    def get_or_create(self, session_id: str) -> AgentSession:
        entry = self._pool.get(session_id)
        if entry is None:
            entry = _PooledSession(
                session=AgentSession(session_id=session_id, root_agent=self._factory.build()),
            )
            self._pool[session_id] = entry
            logger.debug("agent pool created session=%s", session_id)
            self._enforce_capacity()
        else:
            entry.last_used_at = time.monotonic()
        return entry.session

    async def discard(self, session_id: str) -> None:
        entry = self._pool.pop(session_id, None)
        if entry is None:
            return
        await entry.session.interrupt()
        logger.debug("agent pool discarded session=%s", session_id)

    async def try_interrupt(self, session_id: str) -> bool:
        """interrupt a pooled session if present; do not allocate on miss"""
        entry = self._pool.get(session_id)
        if entry is None:
            return False
        return await entry.session.interrupt()

    async def _sweep_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._sweep_interval)
                self._sweep_expired(time.monotonic())
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("agent pool sweep iteration failed")

    def _sweep_expired(self, now: float) -> None:
        if self._ttl <= 0:
            return
        expired = [
            sid
            for sid, entry in self._pool.items()
            if not entry.session.is_running() and now - entry.last_used_at > self._ttl
        ]
        for sid in expired:
            del self._pool[sid]
            logger.debug("agent pool evicted idle session=%s", sid)

    def _enforce_capacity(self) -> None:
        # running entries may exceed the cap temporarily; only idle entries are evicted
        overflow = len(self._pool) - self._max_size
        if overflow <= 0:
            return
        idle = sorted(
            ((sid, entry) for sid, entry in self._pool.items() if not entry.session.is_running()),
            key=lambda kv: kv[1].last_used_at,
        )
        for sid, _ in idle[:overflow]:
            del self._pool[sid]
            logger.debug("agent pool evicted LRU session=%s", sid)


_pool: AgentSessionPool | None = None


def get_agent_pool() -> AgentSessionPool:
    global _pool
    if _pool is None:
        _pool = AgentSessionPool()
    return _pool


def _build_user_input(text: str) -> list[TResponseInputItem]:
    text_item: ResponseInputTextParam = {"type": "input_text", "text": text}
    content: ResponseInputMessageContentListParam = [text_item]
    message: EasyInputMessageParam = {"type": "message", "role": "user", "content": content}
    return [message]


def _track_delta(buffers: dict[str, _DeltaBuffer], event: AgentEventSchema) -> None:
    if isinstance(event, _DELTA_TYPES):
        buf = buffers.get(event.item_id)
        if buf is None:
            buf = _DeltaBuffer(
                is_thinking=isinstance(event, ThinkingDeltaEvent),
                item_id=event.item_id,
            )
            buffers[event.item_id] = buf
        buf.content += event.delta
    elif isinstance(event, _COMPLETE_TYPES):
        buffers.pop(event.item_id, None)


async def _flush_partial_context(
    result: Any,
    memory_session: SQLAlchemySession,
    buffers: dict[str, _DeltaBuffer],
) -> None:
    """on cancellation, persist accumulated deltas as partial items so the
    next turn sees the truncated context"""
    if result is None or getattr(result, "is_complete", True):
        return

    try:
        result.cancel(mode="immediate")
    except Exception:
        logger.warning("failed to cancel SDK stream", exc_info=True)

    items: list[TResponseInputItem] = [
        _build_partial_reasoning_item(buf) if buf.is_thinking else _build_partial_assistant_item(buf)
        for buf in buffers.values()
        if buf.content
    ]
    if not items:
        return
    try:
        await memory_session.add_items(items)
    except Exception:
        logger.warning("failed to inject partial assistant context", exc_info=True)


def _build_partial_assistant_item(buf: _DeltaBuffer) -> TResponseInputItem:
    return {
        "id": f"partial_{buf.item_id}",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": buf.content, "annotations": []}],
        "status": "incomplete",
    }


def _build_partial_reasoning_item(buf: _DeltaBuffer) -> TResponseInputItem:
    return {
        "id": f"partial_{buf.item_id}",
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": buf.content}],
        "status": "incomplete",
    }
