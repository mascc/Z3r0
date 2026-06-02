"""Timeline identity + durable writer for the per-session UI event log.

Every wire event that belongs on the rendered transcript is addressed by a
stable ``item_key`` so streaming updates upsert in place and the client can
merge history with live frames idempotently. Deltas and control frames carry a
``seq`` for ordering but are never persisted (the in-memory live projection
covers the in-flight tail; completed segments are what reach the log).
"""

import asyncio
from datetime import datetime

from logger import get_logger
from schema.agent.events import AgentEventSchema


logger = get_logger(__name__)

# event types that never enter the persisted timeline
_CONTROL_TYPES = frozenset({"run_state", "done"})
_DELTA_TYPES = frozenset({"text_delta", "thinking_delta"})


def timeline_item_key(event: AgentEventSchema) -> str | None:
    """Stable identity for events that carry their own id; None for keyless ones."""
    event_type = str(event.type)
    nested_call_id = getattr(event, "nested_call_id", "")
    if event_type in ("text_delta", "text_complete"):
        return f"text:{nested_call_id}:{event.segment_id}"
    if event_type in ("thinking_delta", "thinking_complete"):
        return f"thinking:{nested_call_id}:{event.segment_id}"
    if event_type == "tool_call":
        return f"tc:{nested_call_id}:{event.call_id}"
    if event_type == "tool_result":
        return f"tr:{nested_call_id}:{event.call_id}"
    if event_type == "subagent_task":
        return f"sa:{event.run_id}"
    return None


def is_persistable(event: AgentEventSchema) -> bool:
    event_type = str(event.type)
    return event_type not in _CONTROL_TYPES and event_type not in _DELTA_TYPES


def carries_seq(event: AgentEventSchema) -> bool:
    return str(event.type) not in _CONTROL_TYPES


class TimelineLogWriter:
    """Single-consumer async writer that batches timeline upserts for a session."""

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id
        self._queue: asyncio.Queue[tuple[str, int, str, datetime]] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name=f"timeline-writer-{self._session_id}")

    def enqueue(self, item_key: str, seq: int, payload: str, created_at: datetime) -> None:
        self._queue.put_nowait((item_key, seq, payload, created_at))

    async def _run(self) -> None:
        while True:
            first = await self._queue.get()
            batch = [first]
            while True:
                try:
                    batch.append(self._queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            await self._flush(batch)

    async def _flush(self, batch: list[tuple[str, int, str, datetime]]) -> None:
        from service.agent.event_log import upsert_timeline_events

        # collapse repeated keys within the window, keeping the latest payload
        collapsed: dict[str, tuple[str, int, str, datetime]] = {}
        for row in batch:
            collapsed[row[0]] = row
        try:
            await upsert_timeline_events(self._session_id, list(collapsed.values()))
        except Exception:
            logger.exception("timeline writer upsert failed session=%s", self._session_id)

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        # final drain so the last completed segments are not lost on eviction
        leftover: list[tuple[str, int, str, datetime]] = []
        while True:
            try:
                leftover.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if leftover:
            await self._flush(leftover)
