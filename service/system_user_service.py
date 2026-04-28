import hmac
from hashlib import sha256
from datetime import datetime, timedelta

import jwt
from sqlalchemy import or_
from sqlmodel import select

from config import get_config
from database import get_async_session
from logger import get_logger
from model.system_user_model import SystemUser, SystemUserRole


logger = get_logger(__name__)


def _encrypt_password(password: str) -> str:
    """encrypt user password"""
    cfg = get_config()
    return hmac.new(cfg.system.encrypt_key.encode(), password.encode(), sha256).hexdigest()


async def create_system_user(
    username: str,
    password: str,
    email: str = "",
    role: SystemUserRole = SystemUserRole.USER,
) -> SystemUser:
    """create system user"""
    now = datetime.now()
    system_user = SystemUser(
        role=role,
        email=email,
        username=username,
        password=_encrypt_password(password),
        created_at=now,
        updated_at=now,
    )

    async with get_async_session() as session:
        session.add(system_user)
        await session.commit()
        await session.refresh(system_user)

    logger.info("system user created: %s", system_user.id)
    return system_user


async def delete_system_user(id: int) -> bool:
    """delete system user"""
    async with get_async_session() as session:
        system_user = await session.get(SystemUser, id)
        if system_user is None:
            return False

        await session.delete(system_user)
        await session.commit()

    logger.info("system user deleted: %s", id)
    return True


async def update_system_user(
    id: int,
    username: str | None = None,
    password: str | None = None,
    email: str | None = None,
    role: SystemUserRole | None = None,
) -> SystemUser | None:
    """update system user"""
    async with get_async_session() as session:
        system_user = await session.get(SystemUser, id)
        if system_user is None:
            return None

        if role is not None:
            system_user.role = role
        if email is not None:
            system_user.email = email
        if username is not None:
            system_user.username = username
        if password is not None:
            system_user.password = _encrypt_password(password)

        system_user.updated_at = datetime.now()
        session.add(system_user)
        await session.commit()
        await session.refresh(system_user)

    logger.info("system user updated: %s", system_user.id)
    return system_user


async def query_system_users(page: int = 1, size: int = 100, keyword: str = "") -> list[SystemUser]:
    """query system users"""
    offset = (page - 1) * size
    statement = select(SystemUser).order_by(SystemUser.id).offset(offset).limit(size)
    
    keyword = keyword.strip()
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(
                SystemUser.email.ilike(pattern),
                SystemUser.username.ilike(pattern),
            )
        )

    async with get_async_session() as session:
        result = await session.exec(statement)
        return list(result.all())


async def system_user_login(email: str, password: str) -> str | None:
    """system user login"""
    cfg = get_config()

    async with get_async_session() as session:
        result = await session.exec(select(SystemUser).where(SystemUser.email == email))
        system_user = result.first()
        if system_user is None:
            return None

        if system_user.password != _encrypt_password(password):
            return None

        token = jwt.encode(
            payload={
                "id": system_user.id,
                "role": system_user.role,
                "email": system_user.email,
                "username": system_user.username,
                "sub": "z3r0",
                "exp": datetime.now() + timedelta(days=30),
            },
            key=cfg.system.encrypt_key,
            algorithm="HS256",
        )
        return token
