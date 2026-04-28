from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


class SystemUserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


class SystemUser(SQLModel, table=True):
    __tablename__ = "system_users"

    id: int | None = Field(default=None, primary_key=True)
    role: SystemUserRole = Field(default=SystemUserRole.USER)
    email: str = Field(default="")
    username: str = Field(default="")
    password: str = Field(default="")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
