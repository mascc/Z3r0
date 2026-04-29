import json
from uuid import uuid4

from sqlalchemy import delete, func, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from core.agents import get_agent_pool
from core.events import events_from_sdk_message
from database import get_async_session
from logger import get_logger
from model.agent_session_meta_model import AgentSessionMeta
from model.work_project_model import WorkProject
from schema.agent_event_schema import AgentContentEventSchema
from schema.agent_session_schema import AgentSessionSummarySchema, SessionType
from utils.sdk_tables import BOOTSTRAP_SESSION_ID, agent_messages, agent_sessions


logger = get_logger(__name__)

_TITLE_MAX_LEN = 80


def create_session() -> str:
    return str(uuid4())


async def ensure_chat_session_meta(session_id: str, user_text: str) -> None:
    """idempotently create chat-session SDK rows + meta on the first turn"""
    async with get_async_session() as session:
        await _materialize_sdk_session(session, session_id)
        if await session.get(AgentSessionMeta, session_id) is None:
            session.add(AgentSessionMeta(
                session_id=session_id,
                session_type=SessionType.CHAT,
                title=_truncate(user_text),
            ))
        await session.commit()


async def materialize_project_session_in_tx(session: AsyncSession, session_id: str) -> None:
    """write SDK session storage + project meta inside an existing transaction"""
    if not session_id:
        return
    await _materialize_sdk_session(session, session_id)
    meta = await session.get(AgentSessionMeta, session_id)
    if meta is None:
        session.add(AgentSessionMeta(session_id=session_id, session_type=SessionType.PROJECT))
        return
    meta.session_type = SessionType.PROJECT
    session.add(meta)


async def list_sessions(limit: int = 100) -> list[AgentSessionSummarySchema]:
    """compose sidebar summaries from SDK sessions joined with app meta"""
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
        metas = {meta.session_id: meta for meta in (await session.exec(
            select(AgentSessionMeta).where(AgentSessionMeta.session_id.in_(session_ids))
        )).all()}
        projects = {project.session_id: project for project in (await session.exec(
            select(WorkProject).where(WorkProject.session_id.in_(session_ids))
        )).all()}

    summaries: list[AgentSessionSummarySchema] = []
    for row in rows:
        meta = metas.get(row.session_id)
        session_type = meta.session_type if meta else SessionType.CHAT
        summaries.append(AgentSessionSummarySchema(
            session_id=row.session_id,
            session_type=session_type,
            title=_resolve_title(session_type, meta, projects.get(row.session_id)),
            message_count=row.message_count or 0,
            created_at=row.created_at,
            updated_at=row.updated_at,
        ))
    return summaries


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
            logger.warning("invalid SDK agent message skipped: id=%s", row.id, exc_info=True)
            continue
        events.extend(events_from_sdk_message(message, str(row.id)))
    return events


async def delete_session(session_id: str) -> bool:
    """tear down a session end-to-end: pool eviction + SDK rows + meta + paired project"""
    if not session_id:
        return False

    await get_agent_pool().discard(session_id)

    async with get_async_session() as session:
        project_deleted = await _delete_paired_project_in_tx(session, session_id)
        records_deleted = await _delete_session_records_in_tx(session, session_id)
        await session.commit()

    deleted = project_deleted or records_deleted
    if deleted:
        logger.info("agent session deleted: %s", session_id)
    return deleted


async def _delete_session_records_in_tx(session: AsyncSession, session_id: str) -> bool:
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


async def _delete_paired_project_in_tx(session: AsyncSession, session_id: str) -> bool:
    result = await session.exec(select(WorkProject).where(WorkProject.session_id == session_id))
    project = result.first()
    if project is None:
        return False
    await session.delete(project)
    logger.info("paired work project deleted by session: %s", project.id)
    return True


async def _materialize_sdk_session(session: AsyncSession, session_id: str) -> None:
    await session.execute(
        text(
            "INSERT INTO agent_sessions (session_id) VALUES (:sid) "
            "ON CONFLICT (session_id) DO NOTHING"
        ),
        {"sid": session_id},
    )


def _truncate(value: str) -> str:
    value = value.strip().replace("\n", " ")
    return value if len(value) <= _TITLE_MAX_LEN else value[: _TITLE_MAX_LEN - 1] + "..."


def _resolve_title(
    session_type: SessionType,
    meta: AgentSessionMeta | None,
    project: WorkProject | None,
) -> str:
    if session_type == SessionType.PROJECT:
        return project.name if project else ""
    return meta.title if meta else ""
