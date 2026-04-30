from dataclasses import dataclass

from schema.system_user_schema import SystemUserRole


@dataclass(frozen=True)
class AgentUserContext:
    id: int
    username: str
    email: str
    role: SystemUserRole


@dataclass(frozen=True)
class AgentRuntimeContext:
    session_id: str
    user: AgentUserContext
    sandbox_container_id: int | None = None
