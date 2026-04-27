from fastapi import APIRouter, Query

from handler.sandbox_image_handler import (
    cancel_sandbox_image_pull_handler,
    create_sandbox_image_handler,
    delete_sandbox_image_handler,
    query_sandbox_images_handler,
    retry_sandbox_image_handler,
)
from middleware.auth import admin_required
from schema.response_schema import CommonResponse
from schema.sandbox_image_schema import (
    DeleteSandboxImageResponse,
    QuerySandboxImagesResponse,
    SandboxImageSchema,
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
        "description": "Sandbox image not found",
        "model": CommonResponse,
    },
}


router = APIRouter(prefix="/sandbox-images", tags=["sandbox-images"])


async def query_sandbox_images_route(
    page: int = Query(default=1),
    size: int = Query(default=100),
    keyword: str = Query(default=""),
) -> CommonResponse[QuerySandboxImagesResponse]:
    """query sandbox images"""
    return await query_sandbox_images_handler(page=page, size=size, keyword=keyword)


router.add_api_route(
    "",
    admin_required(create_sandbox_image_handler),
    methods=["POST"],
    response_model=CommonResponse[SandboxImageSchema],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}",
    admin_required(delete_sandbox_image_handler),
    methods=["DELETE"],
    response_model=CommonResponse[DeleteSandboxImageResponse],
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)


router.add_api_route(
    "/{id}/cancel",
    admin_required(cancel_sandbox_image_pull_handler),
    methods=["POST"],
    response_model=CommonResponse[SandboxImageSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/retry",
    admin_required(retry_sandbox_image_handler),
    methods=["POST"],
    response_model=CommonResponse[SandboxImageSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "",
    admin_required(query_sandbox_images_route),
    methods=["GET"],
    response_model=CommonResponse[QuerySandboxImagesResponse],
    responses=COMMON_ERROR_RESPONSES,
)
