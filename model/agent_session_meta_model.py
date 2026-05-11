from datetime import datetime

from sqlmodel import Field, SQLModel

from schema.agent_session_schema import SessionType


class AgentSessionMeta(SQLModel, table=True):
    """1:1 app-level attribution for a SDK agent_sessions row; cascades on delete."""

    __tablename__ = "agent_session_meta"

    session_id: str = Field(
        primary_key=True,
        foreign_key="agent_sessions.session_id",
        ondelete="CASCADE",
    )
    session_type: SessionType = Field(default=SessionType.CHAT, index=True)
    title: str = ""
    agent_code: str = Field(default="")
    owner_id: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
