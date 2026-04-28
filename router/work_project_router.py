from fastapi import APIRouter, Query

from handler.work_project_handler import (
    cancel_work_project_handler,
    create_work_project_handler,
    delete_work_project_handler,
    query_work_projects_handler,
    retry_work_project_handler,
)
from middleware.auth import admin_required
from schema.response_schema import CommonResponse
from schema.work_project_schema import (
    DeleteWorkProjectResponse,
    QueryWorkProjectsResponse,
    WorkProjectSchema,
)


COMMON_ERROR_RESPONSES = {
    401: {
        "description": "Unauthorized",
        "model": CommonResponse,
    },
    403: {
        "description": "Forbidden",
        "model": CommonResponse,
    },
    422: {
        "description": "Validation Error",
        "model": CommonResponse,
    },
}
BAD_REQUEST_RESPONSE = {
    400: {
        "description": "Bad Request",
        "model": CommonResponse,
    },
}
NOT_FOUND_RESPONSE = {
    404: {
        "description": "Work project not found",
        "model": CommonResponse,
    },
}


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
