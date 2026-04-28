import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, text
from sqlmodel import select

from database import get_async_session
from logger import get_logger
from model.agent_session_meta_model import AgentSessionMeta, SessionType
from model.work_project_model import WorkProject
from schema.agent_event_schema import (
    AgentContentEventSchema,
    TextCompleteEvent,
    ThinkingCompleteEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserMessageEvent,
)
from schema.agent_session_schema import AgentSessionSummarySchema, SessionTypeSchema
from utils.sdk_tables import BOOTSTRAP_SESSION_ID, agent_messages, agent_sessions


logger = get_logger(__name__)

_TITLE_MAX_LEN = 80


def create_session() -> str:
    """allocate a fresh session_id; chat sessions materialize on first turn"""
    return str(uuid4())


def _truncate(text: str) -> str:
    text = text.strip().replace("\n", " ")
    return text if len(text) <= _TITLE_MAX_LEN else text[: _TITLE_MAX_LEN - 1] + "..."


async def ensure_session_meta(session_id: str, user_text: str) -> None:
    """idempotently create SDK session storage and app metadata for a chat turn"""
    async with get_async_session() as session:
        await _materialize_sdk_session(session, session_id)
        existing = await session.get(AgentSessionMeta, session_id)
        if existing is not None:
            await session.commit()
            return

        project = await _get_work_project_by_session_id(session, session_id)
        if project is None:
            session.add(AgentSessionMeta(
                session_id=session_id,
                session_type=SessionType.CHAT,
                title=_truncate(user_text),
            ))
        else:
            session.add(AgentSessionMeta(
                session_id=session_id,
                session_type=SessionType.PROJECT,
            ))
        await session.commit()


async def materialize_project_session_record(session, session_id: str) -> None:
    """write project session storage rows inside an existing transaction"""
    if not session_id:
        return
    await _materialize_sdk_session(session, session_id)
    meta = await session.get(AgentSessionMeta, session_id)
    if meta is None:
        session.add(AgentSessionMeta(
            session_id=session_id,
            session_type=SessionType.PROJECT,
        ))
        return
    meta.session_type = SessionType.PROJECT
    meta.updated_at = datetime.now()
    session.add(meta)


async def _materialize_sdk_session(session, session_id: str) -> None:
    await session.execute(
        text(
            "INSERT INTO agent_sessions (session_id) VALUES (:sid) "
            "ON CONFLICT (session_id) DO NOTHING"
        ),
        {"sid": session_id},
    )


async def list_sessions(limit: int = 100) -> list[AgentSessionSummarySchema]:
    """compose sidebar session summaries from SDK sessions and session metadata"""
    async with get_async_session() as session:
        rows = (await session.execute(
            select(
                agent_sessions.c.session_id,
                agent_sessions.c.created_at,
                agent_sessions.c.updated_at,
                func.count(agent_messages.c.id).label("message_count"),
            )
            .select_from(
                agent_sessions.outerjoin(
                    agent_messages,
                    agent_sessions.c.session_id == agent_messages.c.session_id,
                )
            )
            .where(agent_sessions.c.session_id != BOOTSTRAP_SESSION_ID)
            .group_by(
                agent_sessions.c.session_id,
                agent_sessions.c.created_at,
                agent_sessions.c.updated_at,
            )
            .order_by(agent_sessions.c.updated_at.desc())
            .limit(limit)
        )).all()
        if not rows:
            return []

        session_ids = [row.session_id for row in rows]
        meta_rows = (await session.exec(
            select(AgentSessionMeta).where(AgentSessionMeta.session_id.in_(session_ids))
        )).all()
        project_rows = (await session.exec(
            select(WorkProject).where(WorkProject.session_id.in_(session_ids))
        )).all()

    metas = {meta.session_id: meta for meta in meta_rows}
    projects = {project.session_id: project for project in project_rows}
    summaries: list[AgentSessionSummarySchema] = []
    for row in rows:
        meta = metas.get(row.session_id)
        session_type = _to_public_session_type(meta.session_type if meta else SessionType.CHAT)
        title = _resolve_title(session_type, meta, projects.get(row.session_id))
        summaries.append(AgentSessionSummarySchema(
            session_id=row.session_id,
            session_type=session_type,
            title=title,
            message_count=row.message_count or 0,
            created_at=row.created_at,
            updated_at=row.updated_at,
        ))
    return summaries


def _to_public_session_type(session_type: SessionType) -> SessionTypeSchema:
    return SessionTypeSchema(session_type.value)


def _resolve_title(
    session_type: SessionTypeSchema,
    meta: AgentSessionMeta | None,
    project: WorkProject | None,
) -> str:
    if session_type == SessionTypeSchema.PROJECT:
        return project.name if project else ""
    return meta.title if meta else ""


async def replay_session_events(session_id: str) -> list[AgentContentEventSchema]:
    """replay one session from the SDK-managed message table"""
    async with get_async_session() as session:
        rows = (await session.execute(
            select(agent_messages.c.id, agent_messages.c.message_data)
            .where(agent_messages.c.session_id == session_id)
            .order_by(agent_messages.c.created_at.asc(), agent_messages.c.id.asc())
        )).all()

    events: list[AgentContentEventSchema] = []
    for row in rows:
        try:
            message = json.loads(row.message_data)
        except json.JSONDecodeError:
            logger.warning("invalid SDK agent message skipped: %s", row.id, exc_info=True)
            continue
        events.extend(_sdk_message_to_events(message, str(row.id)))
    return events


def _sdk_message_to_events(message: Any, fallback_id: str) -> list[AgentContentEventSchema]:
    if not isinstance(message, dict):
        return []

    message_type = message.get("type")
    if message_type == "message":
        return _message_item_to_events(message, fallback_id)
    if message_type == "reasoning":
        text = _extract_reasoning_text(message)
        return [ThinkingCompleteEvent(item_id=_item_id(message, fallback_id), text=text)] if text else []
    if message_type == "function_call":
        return [_function_call_to_event(message)]
    if message_type == "function_call_output":
        return [_function_output_to_event(message)]
    return []


def _message_item_to_events(message: dict[str, Any], fallback_id: str) -> list[AgentContentEventSchema]:
    role = message.get("role")
    text_value = _extract_message_text(message.get("content"))
    if not text_value:
        return []
    if role == "user":
        return [UserMessageEvent(text=text_value)]
    if role == "assistant":
        return [TextCompleteEvent(item_id=_item_id(message, fallback_id), text=text_value)]
    return []


def _function_call_to_event(message: dict[str, Any]) -> ToolCallEvent:
    return ToolCallEvent(
        call_id=str(message.get("call_id") or message.get("id") or ""),
        name=str(message.get("name") or ""),
        arguments=_parse_json_object(message.get("arguments")),
    )


def _function_output_to_event(message: dict[str, Any]) -> ToolResultEvent:
    return ToolResultEvent(
        call_id=str(message.get("call_id") or ""),
        output=_stringify_output(message.get("output")),
        is_error=str(message.get("status") or "").lower() in {"failed", "error", "incomplete"},
    )


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and item.get("type") in {"input_text", "output_text", "text"}:
            parts.append(text)
    return "".join(parts)


def _extract_reasoning_text(message: dict[str, Any]) -> str:
    summary = message.get("summary")
    if isinstance(summary, str):
        return summary
    if not isinstance(summary, list):
        return ""

    parts: list[str] = []
    for item in summary:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {"_raw": value}
    return parsed if isinstance(parsed, dict) else {"_value": parsed}


def _stringify_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _item_id(message: dict[str, Any], fallback_id: str) -> str:
    return str(message.get("id") or message.get("call_id") or fallback_id)


async def _get_work_project_by_session_id(session, session_id: str) -> WorkProject | None:
    if not session_id:
        return None
    result = await session.exec(select(WorkProject).where(WorkProject.session_id == session_id))
    return result.first()


async def delete_session_records_in_session(session, session_id: str) -> bool:
    """delete SDK storage and session metadata in one transaction"""
    messages_result = await session.execute(
        delete(agent_messages).where(agent_messages.c.session_id == session_id)
    )
    sdk_result = await session.execute(
        delete(agent_sessions).where(agent_sessions.c.session_id == session_id)
    )
    meta = await session.get(AgentSessionMeta, session_id)
    meta_deleted = meta is not None
    if meta is not None:
        await session.delete(meta)

    return any((
        (messages_result.rowcount or 0) > 0,
        (sdk_result.rowcount or 0) > 0,
        meta_deleted,
    ))


async def delete_session_records(session_id: str) -> bool:
    """delete SDK storage and session metadata"""
    async with get_async_session() as session:
        deleted = await delete_session_records_in_session(session, session_id)
        await session.commit()
    return deleted


async def delete_session(session_id: str) -> bool:
    """delete a session and its paired work project when one exists"""
    from service.work_project_service import delete_work_project_record_by_session_id_in_session

    async with get_async_session() as session:
        project_deleted = await delete_work_project_record_by_session_id_in_session(session, session_id)
        session_deleted = await delete_session_records_in_session(session, session_id)
        await session.commit()

    deleted = project_deleted or session_deleted
    if deleted:
        logger.info("agent session deleted: %s", session_id)
    return deleted
