from agents.extensions.memory import SQLAlchemySession
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_config
from logger import get_logger
from model.agent_session_meta_model import AgentSessionMeta
from model.sandbox_image_model import SandboxImage
from model.system_user_model import SystemUser
from model.work_project_model import WorkProject
from utils.sdk_tables import BOOTSTRAP_SESSION_ID


logger = get_logger(__name__)

# registered so SQLModel.metadata picks every table up at create_all time
_registered_models = [SystemUser, SandboxImage, WorkProject, AgentSessionMeta]

_engine: AsyncEngine | None = None


async def create_all_tables() -> None:
    """create application + SDK session storage tables"""
    global _engine
    if _engine is None:
        raise RuntimeError("database engine is not initialized")

    sdk_metadata = SQLAlchemySession(session_id=BOOTSTRAP_SESSION_ID, engine=_engine)._metadata

    async with _engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        await conn.run_sync(sdk_metadata.create_all)

    logger.info("all tables created")


async def close_engine() -> None:
    """close async postgres engine instance"""
    global _engine

    if _engine is not None:
        await _engine.dispose()
        _engine = None


def init_engine() -> None:
    """initialize async postgres engine"""
    global _engine
    if _engine is not None:
        return

    cfg = get_config()
    dsn = f"postgresql+asyncpg://{cfg.database.username}:{cfg.database.password}@{cfg.database.host}:{cfg.database.port}/{cfg.database.database}"

    _engine = create_async_engine(url=dsn)
    logger.info("async postgres engine initialized")


def get_engine() -> AsyncEngine:
    """get async postgres engine instance"""
    global _engine
    if _engine is None:
        raise RuntimeError("database engine is not initialized")
    return _engine


def get_async_session() -> AsyncSession:
    """open a new async session bound to the global engine"""
    return AsyncSession(get_engine())
