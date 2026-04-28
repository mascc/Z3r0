from fastapi import APIRouter, Query

from handler.work_project_handler import (
    cancel_work_project_handler,
    create_work_project_handler,
    delete_work_project_handler,
    query_work_projects_handler,
    retry_work_project_handler,
)
from middleware.auth import admin_required
from router._responses import BAD_REQUEST_RESPONSE, COMMON_ERROR_RESPONSES, not_found_response
from schema.response_schema import CommonResponse
from schema.work_project_schema import (
    DeleteWorkProjectResponse,
    QueryWorkProjectsResponse,
    WorkProjectSchema,
)


NOT_FOUND_RESPONSE = not_found_response("Work project")


router = APIRouter(prefix="/work-projects", tags=["work-projects"])


async def query_work_projects_route(
    page: int = Query(default=1),
    size: int = Query(default=100),
    keyword: str = Query(default=""),
) -> CommonResponse[QueryWorkProjectsResponse]:
    """query work projects"""
    return await query_work_projects_handler(page=page, size=size, keyword=keyword)


router.add_api_route(
    "",
    admin_required(create_work_project_handler),
    methods=["POST"],
    response_model=CommonResponse[WorkProjectSchema],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}",
    admin_required(delete_work_project_handler),
    methods=["DELETE"],
    response_model=CommonResponse[DeleteWorkProjectResponse],
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)


router.add_api_route(
    "/{id}/cancel",
    admin_required(cancel_work_project_handler),
    methods=["POST"],
    response_model=CommonResponse[WorkProjectSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/retry",
    admin_required(retry_work_project_handler),
    methods=["POST"],
    response_model=CommonResponse[WorkProjectSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "",
    admin_required(query_work_projects_route),
    methods=["GET"],
    response_model=CommonResponse[QueryWorkProjectsResponse],
    responses=COMMON_ERROR_RESPONSES,
)
