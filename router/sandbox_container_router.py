from fastapi import APIRouter, Depends, Query, WebSocket

from handler.sandbox_container_handler import (
    create_sandbox_container_handler,
    delete_sandbox_container_handler,
    handle_container_shell_stream,
    query_available_sandbox_containers_handler,
    query_sandbox_containers_handler,
    start_sandbox_container_handler,
    stop_sandbox_container_handler,
)
from middleware.auth import AuthUser, require_admin, require_user
from router._responses import BAD_REQUEST_RESPONSE, COMMON_ERROR_RESPONSES, not_found_response
from schema.response_schema import CommonResponse
from schema.sandbox_container_schema import (
    CreateSandboxContainerRequest,
    DeleteSandboxContainerResponse,
    QuerySandboxContainersResponse,
    SandboxContainerSchema,
)


NOT_FOUND_RESPONSE = not_found_response("Sandbox container")
CREATE_NOT_FOUND_RESPONSE = not_found_response("Sandbox image")

router = APIRouter(
    prefix="/sandbox-containers",
    tags=["sandbox-containers"],
)

ADMIN_ONLY = [Depends(require_admin)]


async def create_sandbox_container_route(
    request: CreateSandboxContainerRequest,
    user: AuthUser = Depends(require_admin),
) -> CommonResponse[SandboxContainerSchema]:
    return await create_sandbox_container_handler(request=request, owner_id=user.id)


async def query_sandbox_containers_route(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=100),
    keyword: str = Query(default=""),
) -> CommonResponse[QuerySandboxContainersResponse]:
    return await query_sandbox_containers_handler(page=page, size=size, keyword=keyword)


async def query_available_sandbox_containers_route(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=100),
    keyword: str = Query(default=""),
    user: AuthUser = Depends(require_user),
) -> CommonResponse[QuerySandboxContainersResponse]:
    return await query_available_sandbox_containers_handler(
        page=page,
        size=size,
        keyword=keyword,
        user_id=user.id,
        user_role=user.role,
    )


router.add_api_route(
    "",
    create_sandbox_container_route,
    methods=["POST"],
    response_model=CommonResponse[SandboxContainerSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **CREATE_NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/available",
    query_available_sandbox_containers_route,
    methods=["GET"],
    response_model=CommonResponse[QuerySandboxContainersResponse],
    responses=COMMON_ERROR_RESPONSES,
)

router.add_api_route(
    "/{id}",
    delete_sandbox_container_handler,
    methods=["DELETE"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[DeleteSandboxContainerResponse],
    responses={**COMMON_ERROR_RESPONSES, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/start",
    start_sandbox_container_handler,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[SandboxContainerSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "/{id}/stop",
    stop_sandbox_container_handler,
    methods=["POST"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[SandboxContainerSchema],
    responses={**COMMON_ERROR_RESPONSES, **BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)

router.add_api_route(
    "",
    query_sandbox_containers_route,
    methods=["GET"],
    dependencies=ADMIN_ONLY,
    response_model=CommonResponse[QuerySandboxContainersResponse],
    responses=COMMON_ERROR_RESPONSES,
)


@router.websocket("/{container_hash}/shell")
async def container_shell_stream(
    websocket: WebSocket,
    container_hash: str,
    token: str = Query(default=""),
) -> None:
    await handle_container_shell_stream(
        websocket=websocket,
        container_hash=container_hash,
        token=token,
    )
