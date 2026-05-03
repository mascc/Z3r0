from datetime import datetime
from uuid import uuid4

from sqlalchemy import String, cast, or_
from sqlmodel import select

from database import get_async_session
from logger import get_logger
from model.work_project_model import WorkProject
from schema.work_project_schema import WorkProjectStatus, WorkProjectType
from schema.system_user_schema import SystemUserRole
from service.agent_session_service import delete_session, materialize_project_session_in_tx


logger = get_logger(__name__)


async def create_work_project(
    name: str,
    owner_id: int,
    description: str = "",
    type: WorkProjectType = WorkProjectType.PENETRATION_TEST,
) -> WorkProject:
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
        await materialize_project_session_in_tx(session, work_project.session_id, owner_id=owner_id)
        await session.commit()
        await session.refresh(work_project)

    logger.info("work project created: %s", work_project.id)
    return work_project


async def cancel_work_project(id: int) -> tuple[WorkProject | None, bool]:
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
    """route through delete_session so SDK rows + meta + pool are cleaned up in one place"""
    async with get_async_session() as session:
        work_project = await session.get(WorkProject, id)
        if work_project is None:
            return False
        session_id = work_project.session_id

    return await delete_session(session_id, user_role=SystemUserRole.ADMIN)


async def retry_work_project(id: int) -> tuple[WorkProject | None, bool]:
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


async def query_work_projects(page: int = 1, size: int = 100, keyword: str = "") -> list[WorkProject]:
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
