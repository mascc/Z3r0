from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, SQLModel


class SessionType(StrEnum):
    CHAT = "chat"
    PROJECT = "project"


class AgentSessionMeta(SQLModel, table=True):
    """one metadata row per agent session"""

    __tablename__ = "agent_session_meta"

    session_id: str = Field(primary_key=True)
    session_type: SessionType = Field(default=SessionType.CHAT, index=True)
    title: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
