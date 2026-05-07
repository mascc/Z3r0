from uuid import uuid4

from sqlalchemy import delete, func, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from core.subordinates import cancel_session_subagent_runs
from core.agents import DEFAULT_AGENT_CODE
from core.events import event_from_subagent_task, events_from_sdk_message
from core.runtime import get_agent_pool, get_agent_registry
from core.session import fetch_stored_items
from database import get_async_session
from logger import get_logger
from model.agent_session_meta_model import AgentSessionMeta
from model.agent_subordinate_model import AgentSubordinateTask
from model.work_project_model import WorkProject
from schema.agent_event_schema import AgentContentEventSchema
from schema.agent_session_schema import AgentSessionSummarySchema, SessionType
from schema.system_user_schema import SystemUserRole
from utils.sdk_tables import BOOTSTRAP_SESSION_ID, agent_messages, agent_sessions


logger = get_logger(__name__)

_TITLE_MAX_LEN = 80


async def create_session(user_id: int) -> str:
    session_id = str(uuid4())
    async with get_async_session() as session:
        await _ensure_sdk_session_row(session, session_id)
        session.add(AgentSessionMeta(
            session_id=session_id,
            session_type=SessionType.CHAT,
            agent_code=DEFAULT_AGENT_CODE,
            owner_id=user_id,
        ))
        await session.commit()
    return session_id


async def ensure_chat_session_meta(
    session_id: str,
    user_text: str,
    requested_agent_code: str | None,
    user_id: int,
    user_role: SystemUserRole,
) -> str:
    # resolution: override > sticky > default
    valid = set(get_agent_registry().codes())
    override = requested_agent_code if requested_agent_code in valid else None

    async with get_async_session() as session:
        meta = await session.get(AgentSessionMeta, session_id)
        if meta is None or not _can_access_meta(meta, user_id, user_role):
            raise PermissionError("agent session not found")
        existing = meta.agent_code if meta and meta.agent_code in valid else None
        resolved = override or existing or DEFAULT_AGENT_CODE

        if meta.agent_code != resolved:
            meta.agent_code = resolved
            if not meta.title:
                meta.title = _truncate(user_text)
            session.add(meta)
        elif not meta.title:
            meta.title = _truncate(user_text)
            session.add(meta)
        await session.commit()

    return resolved


async def materialize_project_session_in_tx(session: AsyncSession, session_id: str, owner_id: int) -> None:
    if not session_id:
        return
    await _ensure_sdk_session_row(session, session_id)
    meta = await session.get(AgentSessionMeta, session_id)
    if meta is None:
        session.add(AgentSessionMeta(
            session_id=session_id,
            session_type=SessionType.PROJECT,
            agent_code=DEFAULT_AGENT_CODE,
            owner_id=owner_id,
        ))
        return
    meta.session_type = SessionType.PROJECT
    meta.owner_id = owner_id
    session.add(meta)


async def list_sessions(
    limit: int = 100,
    user_id: int = 0,
    user_role: SystemUserRole = SystemUserRole.USER,
) -> list[AgentSessionSummarySchema]:
    meta_table = AgentSessionMeta.__table__
    source = agent_sessions.join(
        meta_table,
        agent_sessions.c.session_id == meta_table.c.session_id,
    ).outerjoin(
        agent_messages,
        agent_sessions.c.session_id == agent_messages.c.session_id,
    )

    stmt = (
        select(
            agent_sessions.c.session_id,
            agent_sessions.c.created_at,
            agent_sessions.c.updated_at,
            func.count(agent_messages.c.id).label("message_count"),
        )
        .select_from(source)
        .where(agent_sessions.c.session_id != BOOTSTRAP_SESSION_ID)
        .group_by(
            agent_sessions.c.session_id,
            agent_sessions.c.created_at,
            agent_sessions.c.updated_at,
        )
        .order_by(agent_sessions.c.updated_at.desc())
        .limit(limit)
    )
    if user_role != SystemUserRole.ADMIN:
        stmt = stmt.where(meta_table.c.owner_id == user_id)

    async with get_async_session() as session:
        rows = (await session.execute(stmt)).all()
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
            agent_code=meta.agent_code if meta else "",
            owner_id=meta.owner_id if meta else 0,
            message_count=row.message_count or 0,
            created_at=row.created_at,
            updated_at=row.updated_at,
        ))
    return summaries


async def replay_session_events(
    session_id: str,
    user_id: int,
    user_role: SystemUserRole,
) -> list[AgentContentEventSchema] | None:
    # nested-call items are tagged so the UI re-attaches them to the parent ToolCard
    async with get_async_session() as session:
        if not await _can_access_session(session, session_id, user_id, user_role):
            return None
        stored_items = await fetch_stored_items(session, session_id)
        sub_tasks = list((await session.exec(
            select(AgentSubordinateTask)
            .where(AgentSubordinateTask.session_id == session_id)
            .order_by(AgentSubordinateTask.created_at)
        )).all())

    code_to_name = get_agent_registry().code_to_name()
    events: list[AgentContentEventSchema] = []
    for stored in stored_items:
        agent_name = code_to_name.get(stored.owner_code, "")
        events.extend(events_from_sdk_message(
            stored.item, str(stored.message_id),
            owner_code=stored.owner_code,
            agent_name=agent_name,
            nested_for=stored.nested_for,
            nested_call_id=stored.nested_call_id,
        ))
    for task in reversed(sub_tasks):
        index = _find_matching_tool_event_index(events, task.nested_call_id)
        if index == -1:
            continue
        events.insert(index + 1, event_from_subagent_task(
            run_id=task.run_id,
            parent_agent_code=task.parent_agent_code,
            agent_code=task.agent_code,
            agent_name=task.agent_name,
            status=task.status,
            result=task.result,
            error=task.error,
            progress=task.progress,
            nested_call_id=task.nested_call_id,
        ))
    return events


def _find_matching_tool_event_index(events: list[AgentContentEventSchema], nested_call_id: str) -> int:
    if not nested_call_id:
        return -1
    for index in range(len(events) - 1, -1, -1):
        event = events[index]
        if getattr(event, "type", "") == "tool_call" and getattr(event, "call_id", "") == nested_call_id:
            return index
    return -1


async def can_access_session(session_id: str, user_id: int, user_role: SystemUserRole) -> bool:
    async with get_async_session() as session:
        return await _can_access_session(session, session_id, user_id, user_role)


async def delete_session(
    session_id: str,
    user_id: int = 0,
    user_role: SystemUserRole = SystemUserRole.USER,
) -> bool:
    if not session_id:
        return False

    async with get_async_session() as session:
        if not await _can_access_session(session, session_id, user_id, user_role):
            return False

    await cancel_session_subagent_runs(session_id)
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
    # one DELETE drops the SDK session row and the FK CASCADE chain takes
    # care of agent_messages, agent_message_meta, and agent_session_meta
    result = await session.execute(
        delete(agent_sessions).where(agent_sessions.c.session_id == session_id)
    )
    return (result.rowcount or 0) > 0


async def _delete_paired_project_in_tx(session: AsyncSession, session_id: str) -> bool:
    result = await session.exec(select(WorkProject).where(WorkProject.session_id == session_id))
    project = result.first()
    if project is None:
        return False
    await session.delete(project)
    logger.info("paired work project deleted by session: %s", project.id)
    return True


async def _ensure_sdk_session_row(session: AsyncSession, session_id: str) -> None:
    # placeholder row owned by the SDK; required so AgentSessionMeta's FK can
    # bind and so list_sessions can surface freshly-created empty conversations
    await session.execute(
        text(
            "INSERT INTO agent_sessions (session_id) VALUES (:sid) "
            "ON CONFLICT (session_id) DO NOTHING"
        ),
        {"sid": session_id},
    )


async def _can_access_session(
    session: AsyncSession,
    session_id: str,
    user_id: int,
    user_role: SystemUserRole,
) -> bool:
    meta = await session.get(AgentSessionMeta, session_id)
    return meta is not None and _can_access_meta(meta, user_id, user_role)


def _can_access_meta(meta: AgentSessionMeta, user_id: int, user_role: SystemUserRole) -> bool:
    return user_role == SystemUserRole.ADMIN or meta.owner_id == user_id


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
