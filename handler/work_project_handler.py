from http import HTTPStatus

from model.work_project_model import WorkProject, WorkProjectType
from schema.response_schema import CommonResponse
from schema.work_project_schema import (
    CreateWorkProjectRequest,
    DeleteWorkProjectResponse,
    QueryWorkProjectsResponse,
    WorkProjectSchema,
)
from service.work_project_service import (
    cancel_work_project,
    create_work_project,
    delete_work_project,
    query_work_projects,
    retry_work_project,
)


def _to_work_project_schema(work_project: WorkProject) -> WorkProjectSchema:
    """convert database model to public work project schema"""
    return WorkProjectSchema.model_validate(work_project)


async def create_work_project_handler(request: CreateWorkProjectRequest) -> CommonResponse:
    """create work project"""
    work_project = await create_work_project(
        name=request.name,
        description=request.description,
        type=WorkProjectType(request.type.value),
    )
    return CommonResponse(data=_to_work_project_schema(work_project))


async def delete_work_project_handler(id: int) -> CommonResponse:
    """delete work project"""
    deleted = await delete_work_project(id)
    if not deleted:
        return CommonResponse(
            code=HTTPStatus.NOT_FOUND.value,
            message="work project not found",
            data=DeleteWorkProjectResponse(id=id, deleted=False),
        )

    return CommonResponse(data=DeleteWorkProjectResponse(id=id, deleted=True))


async def cancel_work_project_handler(id: int) -> CommonResponse:
    """cancel active work project"""
    work_project, canceled = await cancel_work_project(id)
    if work_project is None:
        return CommonResponse(
            code=HTTPStatus.NOT_FOUND.value,
            message="work project not found",
        )
    if not canceled:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message="only working projects can be canceled",
            data=_to_work_project_schema(work_project),
        )

    return CommonResponse(
        message="work project canceled",
        data=_to_work_project_schema(work_project),
    )


async def retry_work_project_handler(id: int) -> CommonResponse:
    """retry failed work project"""
    work_project, retried = await retry_work_project(id)
    if work_project is None:
        return CommonResponse(
            code=HTTPStatus.NOT_FOUND.value,
            message="work project not found",
        )
    if not retried:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message="only failed or canceled projects can be retried",
            data=_to_work_project_schema(work_project),
        )

    return CommonResponse(
        message="work project restarted",
        data=_to_work_project_schema(work_project),
    )


async def query_work_projects_handler(page: int = 1, size: int = 100, keyword: str = "") -> CommonResponse:
    """query work projects"""
    if page < 1:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message="page must be greater than or equal to 1",
        )
    if size < 1 or size > 100:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message="size must be between 1 and 100",
        )

    work_projects = await query_work_projects(page=page, size=size, keyword=keyword)
    data = QueryWorkProjectsResponse(
        page=page,
        size=size,
        items=[_to_work_project_schema(work_project) for work_project in work_projects],
    )
    return CommonResponse(data=data)
