import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from agents import Agent, Runner, TResponseInputItem
from agents.extensions.memory import SQLAlchemySession
from agents.extensions.models.litellm_model import LitellmModel
from agents.items import (
    HandoffCallItem,
    HandoffOutputItem,
    ToolCallItem,
    ToolCallOutputItem,
)
from agents.stream_events import (
    AgentUpdatedStreamEvent,
    RawResponsesStreamEvent,
    RunItemStreamEvent,
)
from openai.types.responses import (
    EasyInputMessageParam,
    ResponseInputMessageContentListParam,
    ResponseInputTextParam,
)
from openai.types.responses.response_error_event import ResponseErrorEvent
from openai.types.responses.response_reasoning_summary_text_delta_event import (
    ResponseReasoningSummaryTextDeltaEvent,
)
from openai.types.responses.response_reasoning_text_delta_event import (
    ResponseReasoningTextDeltaEvent,
)
from openai.types.responses.response_reasoning_text_done_event import (
    ResponseReasoningTextDoneEvent,
)
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent
from openai.types.responses.response_text_done_event import ResponseTextDoneEvent
from pydantic import BaseModel

from config import WORKSPACE, get_config
from database import get_engine
from logger import get_logger
from schema.agent_event_schema import (
    AgentEventSchema,
    DoneEvent,
    ErrorEvent,
    HandoffEvent,
    TextCompleteEvent,
    TextDeltaEvent,
    ThinkingCompleteEvent,
    ThinkingDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserMessageEvent,
)
from service.agent_session_service import ensure_session_meta


logger = get_logger(__name__)

_DELTA_EVENT_TYPES: tuple[type, ...] = (TextDeltaEvent, ThinkingDeltaEvent)
_COMPLETE_EVENT_TYPES: tuple[type, ...] = (TextCompleteEvent, ThinkingCompleteEvent)


@dataclass
class _DeltaBuffer:
    """in-memory accumulator for streaming deltas; flushed back into the SDK
    session as a partial item when a turn is interrupted, so that the next turn
    sees the partial context and history replay can reconstruct it."""

    is_thinking: bool
    item_id: str
    content: str = ""


def _read_field(raw: Any, key: str) -> Any:
    if isinstance(raw, dict):
        return raw.get(key)
    return getattr(raw, key, None)


def _normalize_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    return decoded if isinstance(decoded, dict) else {"_value": decoded}


def _build_user_input(text: str) -> list[TResponseInputItem]:
    """build a Responses-API input list from a plain user text"""
    text_item: ResponseInputTextParam = {"type": "input_text", "text": text}
    content: ResponseInputMessageContentListParam = [text_item]
    message: EasyInputMessageParam = {"type": "message", "role": "user", "content": content}
    return [message]


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


def _map_raw_event(data: Any, current_agent: str) -> AgentEventSchema | None:
    if isinstance(data, ResponseTextDeltaEvent):
        return TextDeltaEvent(agent_name=current_agent, item_id=data.item_id, delta=data.delta)
    if isinstance(data, ResponseTextDoneEvent):
        return TextCompleteEvent(agent_name=current_agent, item_id=data.item_id, text=data.text)
    if isinstance(data, (ResponseReasoningTextDeltaEvent, ResponseReasoningSummaryTextDeltaEvent)):
        return ThinkingDeltaEvent(agent_name=current_agent, item_id=data.item_id, delta=data.delta)
    if isinstance(data, ResponseReasoningTextDoneEvent):
        return ThinkingCompleteEvent(agent_name=current_agent, item_id=data.item_id, text=data.text)
    if isinstance(data, ResponseErrorEvent):
        return ErrorEvent(agent_name=current_agent, message=data.message, code=data.code or "")
    return None


def _map_run_item_event(event: RunItemStreamEvent, current_agent: str) -> AgentEventSchema | None:
    item = event.item
    agent_name = item.agent.name if item.agent is not None else current_agent

    if event.name == "tool_called" and isinstance(item, ToolCallItem):
        raw = item.raw_item
        return ToolCallEvent(
            agent_name=agent_name,
            call_id=_read_field(raw, "call_id") or _read_field(raw, "id") or "",
            name=_read_field(raw, "name") or item.title or "",
            arguments=_parse_tool_arguments(_read_field(raw, "arguments")),
        )

    if event.name == "tool_output" and isinstance(item, ToolCallOutputItem):
        raw = item.raw_item
        status = _read_field(raw, "status")
        return ToolResultEvent(
            agent_name=agent_name,
            call_id=_read_field(raw, "call_id") or "",
            output=_normalize_to_str(item.output),
            is_error=isinstance(status, str) and status.lower() in {"failed", "error", "incomplete"},
        )

    if event.name == "handoff_occured" and isinstance(item, HandoffOutputItem):
        return HandoffEvent(
            source_agent=item.source_agent.name if item.source_agent else current_agent,
            target_agent=item.target_agent.name if item.target_agent else "",
        )

    # handoff_requested duplicates handoff_occured; suppress to avoid double-emit
    if event.name == "handoff_requested" and isinstance(item, HandoffCallItem):
        return None

    return None


def _map_sdk_event(sdk_event: Any, current_agent: str) -> AgentEventSchema | None:
    if isinstance(sdk_event, RawResponsesStreamEvent):
        return _map_raw_event(sdk_event.data, current_agent)
    if isinstance(sdk_event, RunItemStreamEvent):
        return _map_run_item_event(sdk_event, current_agent)
    return None


def _track_delta(buffers: dict[str, _DeltaBuffer], event: AgentEventSchema) -> None:
    """append a delta into its buffer, or clear the buffer when its complete arrives"""
    if isinstance(event, _DELTA_EVENT_TYPES):
        buf = buffers.get(event.item_id)
        if buf is None:
            buf = _DeltaBuffer(
                is_thinking=isinstance(event, ThinkingDeltaEvent),
                item_id=event.item_id,
            )
            buffers[event.item_id] = buf
        buf.content += event.delta
    elif isinstance(event, _COMPLETE_EVENT_TYPES):
        buffers.pop(event.item_id, None)


async def _cleanup_after_stream(result: Any, memory_session: SQLAlchemySession, buffers: dict[str, _DeltaBuffer]) -> None:
    """cancel the SDK run + re-inject partial buffers"""
    if getattr(result, "is_complete", True):
        return

    try:
        result.cancel(mode="immediate")
    except Exception:
        logger.warning("failed to cancel SDK stream", exc_info=True)

    sdk_items: list[TResponseInputItem] = []
    for buf in buffers.values():
        if not buf.content:
            continue
        builder = _build_partial_reasoning_item if buf.is_thinking else _build_partial_assistant_item
        sdk_items.append(builder(buf))

    if sdk_items:
        try:
            await memory_session.add_items(sdk_items)
        except Exception:
            logger.warning("failed to inject partial assistant context", exc_info=True)


class Z3r0Agents:
    """per-session runtime: serializes turns and owns interrupt-safe cleanup"""

    def __init__(self, session_id: str, root_agent: Agent):
        self.session_id = session_id
        self._root_agent = root_agent
        self._turn_lock = asyncio.Lock()
        self._current_task: asyncio.Task | None = None

    async def complete(self, text: str) -> AsyncIterator[AgentEventSchema]:
        """stream a single user turn as normalized events"""
        async with self._turn_lock:
            task = asyncio.current_task()
            self._current_task = task
            try:
                async for event in self._complete_locked(text):
                    yield event
            finally:
                if self._current_task is task:
                    self._current_task = None

    def is_running(self) -> bool:
        task = self._current_task
        return task is not None and not task.done()

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

    async def cancel(self) -> None:
        await self.interrupt()

    async def _complete_locked(self, text: str) -> AsyncIterator[AgentEventSchema]:
        await ensure_session_meta(self.session_id, text)

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
            )
            async for sdk_event in result.stream_events():
                if isinstance(sdk_event, AgentUpdatedStreamEvent):
                    current_agent = sdk_event.new_agent.name
                    continue

                mapped = _map_sdk_event(sdk_event, current_agent)
                if mapped is None:
                    continue

                _track_delta(buffers, mapped)
                yield mapped

            yield DoneEvent(agent_name=current_agent)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.exception("agent stream failed: %s", exc)
            error_event = ErrorEvent(agent_name=current_agent, message=str(exc))
            yield error_event

        finally:
            await _cleanup_after_stream(result, memory_session, buffers)


@dataclass
class _PooledZ3r0Agents:
    """one Z3r0Agents bundle plus its monotonic last-touch timestamp"""
    bundle: Z3r0Agents
    last_used_at: float


class Z3r0AgentPool:
    """process-wide pool of per-session Z3r0Agents bundles, keyed by
    session_id; a background sweeper task evicts idle bundles by TTL,
    and inserts are capped by LRU"""

    DEFAULT_MAX_SIZE = 256
    DEFAULT_TTL_SECONDS = 30 * 60
    DEFAULT_SWEEP_INTERVAL_SECONDS = 60

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_size: int = DEFAULT_MAX_SIZE,
        sweep_interval_seconds: float = DEFAULT_SWEEP_INTERVAL_SECONDS,
    ):
        self._cfg = get_config()
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._sweep_interval = sweep_interval_seconds
        self._pool: dict[str, _PooledZ3r0Agents] = {}
        self._sweeper_task: asyncio.Task | None = None

    async def start(self) -> None:
        """spawn the background sweeper task; idempotent"""
        if self._sweeper_task is not None and not self._sweeper_task.done():
            return
        self._sweeper_task = asyncio.create_task(self._sweep_loop(), name="z3r0-agent-pool-sweeper")
        logger.debug(
            "agent pool sweeper started (ttl=%ds, interval=%ds, max_size=%d)",
            self._ttl,
            self._sweep_interval,
            self._max_size,
        )

    async def stop(self) -> None:
        """cancel the background sweeper and active session runtimes"""
        task, self._sweeper_task = self._sweeper_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        entries = list(self._pool.values())
        self._pool.clear()
        await asyncio.gather(*(entry.bundle.cancel() for entry in entries), return_exceptions=True)
        logger.debug("agent pool stopped")

    async def _sweep_loop(self) -> None:
        """sleep -> sweep, forever; survive per-iteration failures"""
        while True:
            try:
                await asyncio.sleep(self._sweep_interval)
                self._sweep_expired(time.monotonic())
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("agent pool sweep iteration failed")

    def _build_root_agent(self) -> Agent:
        cfg = self._cfg.agents.get("cso")
        if cfg is None:
            raise ValueError("cso agent config not found")

        agent_path = WORKSPACE / "agents" / cfg.code

        with open(agent_path / "SOUL.md", "r", encoding="utf-8") as f:
            soul_md = f.read().strip()
        with open(agent_path / "AGENTS.md", "r", encoding="utf-8") as f:
            agents_md = f.read().strip()

        instructions = soul_md + "\n\n" + agents_md
        llm = LitellmModel(base_url=cfg.base_url, api_key=cfg.api_key, model=cfg.model)
        return Agent(name=f"{cfg.name} Agent", model=llm, instructions=instructions)

    def _sweep_expired(self, now: float) -> None:
        """drop entries whose idle time exceeds TTL"""
        if self._ttl <= 0:
            return
        expired = [
            sid
            for sid, entry in self._pool.items()
            if not entry.bundle.is_running() and now - entry.last_used_at > self._ttl
        ]
        for sid in expired:
            del self._pool[sid]
            logger.debug("agent pool evicted idle bundle for session=%s", sid)

    def _enforce_capacity(self) -> None:
        """hard cap: evict only idle LRU entries; running turns may exceed the cap temporarily"""
        overflow = len(self._pool) - self._max_size
        if overflow <= 0:
            return
        idle_entries = [
            (sid, entry)
            for sid, entry in self._pool.items()
            if not entry.bundle.is_running()
        ]
        ordered = sorted(idle_entries, key=lambda kv: kv[1].last_used_at)
        for sid, _ in ordered[:overflow]:
            del self._pool[sid]
            logger.debug("agent pool evicted LRU bundle for session=%s", sid)

    def get_or_create(self, session_id: str) -> Z3r0Agents:
        """return the pooled Z3r0Agents bundle for session_id, creating
        and caching on miss; every call refreshes the LRU timestamp"""
        entry = self._pool.get(session_id)
        if entry is None:
            bundle = Z3r0Agents(session_id=session_id, root_agent=self._build_root_agent())
            entry = _PooledZ3r0Agents(bundle=bundle, last_used_at=time.monotonic())
            self._pool[session_id] = entry
            logger.debug("agent pool created bundle for session=%s", session_id)
            self._enforce_capacity()
        else:
            entry.last_used_at = time.monotonic()
        return entry.bundle

    async def discard(self, session_id: str) -> None:
        entry = self._pool.pop(session_id, None)
        if entry is not None:
            await entry.bundle.cancel()
            logger.debug("agent pool discarded bundle for session=%s", session_id)


_z3r0_agent_pool: Z3r0AgentPool | None = None


def get_z3r0_agent_pool() -> Z3r0AgentPool:
    """return the process-wide pool (lazy-initialized)"""
    global _z3r0_agent_pool
    if _z3r0_agent_pool is None:
        _z3r0_agent_pool = Z3r0AgentPool()
    return _z3r0_agent_pool
