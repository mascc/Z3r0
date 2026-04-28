from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from agents import set_tracing_disabled
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import ROOT_PATH
from core.agents import get_z3r0_agent_pool
from database import close_engine, create_all_tables, init_engine
from logger import get_logger
from middleware.auth import JwtAuthMiddleware, RoleAuthMiddleware, auth_whitelist
from middleware.response import (
    CommonResponseStatusMiddleware,
    http_exception_handler,
    request_validation_exception_handler,
)
from model.system_user_model import SystemUserRole
from router.agent_session_router import router as agent_session_router
from router.sandbox_image_router import router as sandbox_image_router
from router.system_user_router import router as system_user_router
from router.work_project_router import router as work_project_router
from schema.response_schema import CommonResponse
from service.system_user_service import create_system_user, query_system_users


logger = get_logger(__name__)

WEB_DIST_PATH = ROOT_PATH / "web" / "dist"
API_PREFIX = "/api"


async def _create_default_admin() -> None:
    """create default admin user"""
    exists = await query_system_users(page=1, size=1, keyword="admin")
    if exists:
        logger.info("default admin user already exists")
        return

    await create_system_user(
        username="admin",
        password="123456",
        email="admin@z3r0.fans",
        role=SystemUserRole.ADMIN,
    )
    logger.info("default admin user created")


def _mount_frontend(app: FastAPI) -> None:
    """serve built frontend assets when web/dist exists"""
    index_path = WEB_DIST_PATH / "index.html"
    if not index_path.is_file():
        logger.info("frontend static route skipped: %s not found", index_path)
        return

    assets_path = WEB_DIST_PATH / "assets"
    if assets_path.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_path), name="web-assets")

    async def serve_frontend(path: str = "") -> FileResponse:
        return FileResponse(index_path)

    app.add_api_route("/", serve_frontend, methods=["GET"], include_in_schema=False)
    app.add_api_route("/{path:path}", serve_frontend, methods=["GET"], include_in_schema=False)


def _mount_api_not_found(app: FastAPI) -> None:
    """return CommonResponse 404s for unmatched API routes before SPA fallback"""

    async def api_not_found(path: str = "") -> CommonResponse[None]:
        return CommonResponse(code=404, message="not found")

    methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    app.add_api_route(API_PREFIX, auth_whitelist(api_not_found), methods=methods, include_in_schema=False)
    app.add_api_route(
        f"{API_PREFIX}/{{path:path}}",
        auth_whitelist(api_not_found),
        methods=methods,
        include_in_schema=False,
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    """ fastapi lifespan"""
    try:
        init_engine()
        await create_all_tables()
        await _create_default_admin()

        set_tracing_disabled(True)
        await get_z3r0_agent_pool().start()

        yield
    finally:
        await get_z3r0_agent_pool().stop()
        await close_engine()


def create_app() -> FastAPI:
    """create fastapi application instance"""
    app = FastAPI(title="Z3r0 - AI + Security Attack Platform", lifespan=lifespan)

    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    logger.info("exception handlers added")

    app.add_middleware(CommonResponseStatusMiddleware)
    app.add_middleware(RoleAuthMiddleware)
    app.add_middleware(JwtAuthMiddleware)
    logger.info("middleware added")

    app.include_router(system_user_router, prefix=API_PREFIX)
    app.include_router(sandbox_image_router, prefix=API_PREFIX)
    app.include_router(work_project_router, prefix=API_PREFIX)
    app.include_router(agent_session_router, prefix=API_PREFIX)
    logger.info("api router added")

    _mount_api_not_found(app)
    _mount_frontend(app)
    return app
