from http import HTTPStatus

from middleware.auth import AuthUser
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


async def create_work_project_handler(request: CreateWorkProjectRequest, user: AuthUser) -> CommonResponse:
    work_project = await create_work_project(
        name=request.name,
        owner_id=user.id,
        description=request.description,
        type=request.type,
    )
    return CommonResponse(data=WorkProjectSchema.model_validate(work_project))


async def delete_work_project_handler(id: int) -> CommonResponse:
    if not await delete_work_project(id):
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="work project not found")
    return CommonResponse(data=DeleteWorkProjectResponse(id=id))


async def cancel_work_project_handler(id: int) -> CommonResponse:
    work_project, canceled = await cancel_work_project(id)
    if work_project is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="work project not found")
    if not canceled:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message="only working projects can be canceled",
            data=WorkProjectSchema.model_validate(work_project),
        )
    return CommonResponse(
        message="work project canceled",
        data=WorkProjectSchema.model_validate(work_project),
    )


async def retry_work_project_handler(id: int) -> CommonResponse:
    work_project, retried = await retry_work_project(id)
    if work_project is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="work project not found")
    if not retried:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message="only failed or canceled projects can be retried",
            data=WorkProjectSchema.model_validate(work_project),
        )
    return CommonResponse(
        message="work project restarted",
        data=WorkProjectSchema.model_validate(work_project),
    )


async def query_work_projects_handler(page: int, size: int, keyword: str) -> CommonResponse:
    work_projects = await query_work_projects(page=page, size=size, keyword=keyword)
    return CommonResponse(data=QueryWorkProjectsResponse(
        page=page,
        size=size,
        items=[WorkProjectSchema.model_validate(project) for project in work_projects],
    ))
