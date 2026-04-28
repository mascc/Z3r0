from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, cast, or_
from sqlmodel import select

from database import get_async_session
from logger import get_logger
from model.work_project_model import WorkProject, WorkProjectStatus, WorkProjectType
from service.agent_session_service import delete_session_records_in_session, materialize_project_session_record


logger = get_logger(__name__)


async def create_work_project(
    name: str,
    description: str = "",
    type: WorkProjectType = WorkProjectType.PENETRATION_TEST,
) -> WorkProject:
    """create work project"""
    now = datetime.now()
    work_project = WorkProject(
        name=name,
        session_id=str(uuid4()),
        description=description,
        status=WorkProjectStatus.WORKING,
        type=type,
        created_at=now,
        updated_at=now,
    )

    async with get_async_session() as session:
        session.add(work_project)
        await materialize_project_session_record(session, work_project.session_id)
        await session.commit()
        await session.refresh(work_project)

    logger.info("work project created: %s", work_project.id)
    return work_project


async def cancel_work_project(id: int) -> tuple[WorkProject | None, bool]:
    """cancel an active work project"""
    async with get_async_session() as session:
        work_project = await session.get(WorkProject, id)
        if work_project is None:
            return None, False
        if work_project.status != WorkProjectStatus.WORKING:
            return work_project, False

        work_project.status = WorkProjectStatus.CANCELED
        work_project.updated_at = datetime.now()
        session.add(work_project)
        await session.commit()
        await session.refresh(work_project)

    logger.info("work project canceled: %s", id)
    return work_project, True


async def delete_work_project(id: int) -> bool:
    """delete work project and its associated agent session in one transaction"""
    async with get_async_session() as session:
        work_project = await session.get(WorkProject, id)
        if work_project is None:
            return False

        session_id = work_project.session_id
        from core.agents import get_z3r0_agent_pool
        await get_z3r0_agent_pool().discard(session_id)
        await session.delete(work_project)
        await delete_session_records_in_session(session, session_id)
        await session.commit()

    logger.info("work project deleted: %s", id)
    return True


async def delete_work_project_record_by_session_id_in_session(session, session_id: str) -> bool:
    """delete the project row paired with a session inside an existing transaction"""
    if not session_id:
        return False
    result = await session.exec(select(WorkProject).where(WorkProject.session_id == session_id))
    work_project = result.first()
    if work_project is None:
        return False
    project_id = work_project.id
    await session.delete(work_project)
    logger.info("work project deleted by session: %s", project_id)
    return True


async def delete_work_project_record_by_session_id(session_id: str) -> bool:
    """delete the project row paired with a session without touching session records"""
    async with get_async_session() as session:
        deleted = await delete_work_project_record_by_session_id_in_session(session, session_id)
        await session.commit()
    return deleted


async def retry_work_project(id: int) -> tuple[WorkProject | None, bool]:
    """retry a failed or canceled work project"""
    async with get_async_session() as session:
        work_project = await session.get(WorkProject, id)
        if work_project is None:
            return None, False
        if work_project.status not in {WorkProjectStatus.FAILED, WorkProjectStatus.CANCELED}:
            return work_project, False

        work_project.status = WorkProjectStatus.WORKING
        work_project.updated_at = datetime.now()
        session.add(work_project)
        await session.commit()
        await session.refresh(work_project)

    logger.info("work project retried: %s", work_project.id)
    return work_project, True


async def get_work_project_by_session_id(session_id: str) -> WorkProject | None:
    """look up a work project by its allocated agent session_id"""
    if not session_id:
        return None
    statement = select(WorkProject).where(WorkProject.session_id == session_id)
    async with get_async_session() as session:
        result = await session.exec(statement)
        return result.first()


async def query_work_projects(page: int = 1, size: int = 100, keyword: str = "") -> list[WorkProject]:
    """query work projects"""
    statement = select(WorkProject).order_by(WorkProject.id).offset((page - 1) * size).limit(size)

    keyword = keyword.strip()
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(
                WorkProject.name.ilike(pattern),
                WorkProject.session_id.ilike(pattern),
                WorkProject.description.ilike(pattern),
                cast(WorkProject.status, String).ilike(pattern),
                cast(WorkProject.type, String).ilike(pattern),
            )
        )

    async with get_async_session() as session:
        result = await session.exec(statement)
        return list(result.all())
