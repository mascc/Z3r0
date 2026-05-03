"""SDK Session backend that keeps SDK tables untouched and stores owner /
nested-call attribution in `agent_message_meta` (1:1 FK to agent_messages.id)."""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from agents.extensions.memory import SQLAlchemySession
from agents.items import TResponseInputItem
from sqlalchemy import insert, select, text as sql_text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from model.agent_message_meta_model import AgentMessageMeta
from utils.sdk_tables import agent_messages


_OWNER_PRIVATE_TYPES = frozenset({"reasoning", "function_call", "function_call_output"})
_TEXT_CONTENT_TYPES = frozenset({"input_text", "output_text", "text"})
_FOREIGN_PREFIX = "[other agent: {name}]\n"


@dataclass(frozen=True, slots=True)
class StoredItem:
    message_id: int
    owner_code: str
    item: dict[str, Any]
    nested_for: str = ""
    nested_call_id: str = ""


class Z3r0Session(SQLAlchemySession):
    def __init__(
        self,
        *,
        session_id: str,
        engine: AsyncEngine,
        viewing_agent_code: str,
        agent_code_to_name: dict[str, str],
        nested_for_agent_code: str = "",
        nested_call_id: str = "",
    ) -> None:
        super().__init__(session_id=session_id, engine=engine)
        self._viewing_agent_code = viewing_agent_code
        self._agent_code_to_name = agent_code_to_name
        self._nested_for = nested_for_agent_code
        self._nested_call_id = nested_call_id if nested_for_agent_code else ""

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        if not items:
            return
        await self._ensure_tables()

        message_payload = [
            {"session_id": self.session_id, "message_data": json.dumps(item, separators=(",", ":"))}
            for item in items
        ]
        owner = self._viewing_agent_code
        nested_for = self._nested_for
        nested_call_id = self._nested_call_id
        meta_table = AgentMessageMeta.__table__

        async def _write() -> None:
            async with self._session_factory() as sess:
                async with sess.begin():
                    await self._ensure_session_row(sess)

                    # bulk insert messages and capture the assigned ids in payload order
                    result = await sess.execute(
                        insert(self._messages).returning(self._messages.c.id),
                        message_payload,
                    )
                    inserted_ids = [row[0] for row in result]

                    if inserted_ids:
                        await sess.execute(insert(meta_table), [
                            {
                                "message_id": mid,
                                "owner_code": owner,
                                "nested_for": nested_for,
                                "nested_call_id": nested_call_id,
                            }
                            for mid in inserted_ids
                        ])

                    await sess.execute(
                        update(self._sessions)
                        .where(self._sessions.c.session_id == self.session_id)
                        .values(updated_at=sql_text("CURRENT_TIMESTAMP"))
                    )

        await self._run_sqlite_write_with_retry(_write)

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        await self._ensure_tables()
        async with self._session_factory() as sess:
            stored = await fetch_stored_items(sess, self.session_id)
        projected = list(self._project(stored))
        return projected if limit is None else projected[-limit:]

    async def _ensure_session_row(self, sess: AsyncSession) -> None:
        existing = await sess.execute(
            select(self._sessions.c.session_id).where(self._sessions.c.session_id == self.session_id)
        )
        if existing.scalar_one_or_none() is not None:
            return
        try:
            async with sess.begin_nested():
                await sess.execute(insert(self._sessions).values({"session_id": self.session_id}))
        except IntegrityError:
            # raced with another writer that created the parent row first
            pass

    def _project(self, stored_items: Iterable[StoredItem]) -> Iterable[TResponseInputItem]:
        # Projection rules (viewer = agent about to receive input):
        #   1. nested-call runs are isolated to their own call id
        #   2. user-role items: every viewer sees verbatim
        #   3. items owned by viewer: verbatim
        #   4. other agents' assistant messages: merged into one "[other agent: <name>]" block
        #   5. other agents' reasoning / function_call / function_call_output: dropped
        viewer = self._viewing_agent_code
        pending_owner: str = ""
        pending_texts: list[str] = []

        if self._nested_for:
            for stored in stored_items:
                if (
                    stored.owner_code == viewer
                    and stored.nested_for == self._nested_for
                    and stored.nested_call_id == self._nested_call_id
                ):
                    yield stored.item
            return

        def flush() -> TResponseInputItem | None:
            nonlocal pending_owner, pending_texts
            if not pending_texts:
                return None
            merged = _build_foreign_block(
                source_name=self._agent_code_to_name.get(pending_owner, pending_owner),
                texts=pending_texts,
            )
            pending_owner = ""
            pending_texts = []
            return merged

        for stored in stored_items:
            owner, item, nested_for = stored.owner_code, stored.item, stored.nested_for
            role = item.get("role")
            item_type = item.get("type")

            if nested_for:
                continue

            if role == "user":
                if (m := flush()) is not None:
                    yield m
                yield item
                continue

            if owner == viewer:
                if (m := flush()) is not None:
                    yield m
                yield item
                continue

            if item_type in _OWNER_PRIVATE_TYPES:
                continue
            if role != "assistant" or item_type != "message":
                continue
            text = _extract_message_text(item.get("content"))
            if not text:
                continue
            if pending_owner and pending_owner != owner:
                if (m := flush()) is not None:
                    yield m
            pending_owner = owner
            pending_texts.append(text)

        if (m := flush()) is not None:
            yield m


async def fetch_stored_items(sess: AsyncSession, session_id: str) -> list[StoredItem]:
    """Load all messages + their owner attribution for one conversation, in order."""
    meta_table = AgentMessageMeta.__table__
    stmt = (
        select(
            agent_messages.c.id,
            agent_messages.c.message_data,
            meta_table.c.owner_code,
            meta_table.c.nested_for,
            meta_table.c.nested_call_id,
        )
        .select_from(
            agent_messages.outerjoin(meta_table, agent_messages.c.id == meta_table.c.message_id)
        )
        .where(agent_messages.c.session_id == session_id)
        .order_by(agent_messages.c.created_at.asc(), agent_messages.c.id.asc())
    )
    result = await sess.execute(stmt)

    items: list[StoredItem] = []
    for row in result.all():
        try:
            item = json.loads(row.message_data)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(item, dict):
            continue
        items.append(StoredItem(
            message_id=row.id,
            owner_code=row.owner_code or "",
            item=item,
            nested_for=row.nested_for or "",
            nested_call_id=row.nested_call_id or "",
        ))
    return items


def _build_foreign_block(*, source_name: str, texts: list[str]) -> dict[str, Any]:
    body = "\n\n".join(texts)
    return {
        "type": "message",
        "role": "assistant",
        "content": [{
            "type": "output_text",
            "text": _FOREIGN_PREFIX.format(name=source_name) + body,
            "annotations": [],
        }],
        "status": "completed",
    }


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for piece in content:
        if not isinstance(piece, dict):
            continue
        if piece.get("type") in _TEXT_CONTENT_TYPES:
            text = piece.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)
