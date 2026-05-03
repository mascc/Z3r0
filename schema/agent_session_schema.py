from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from schema.agent_event_schema import AgentContentEventSchema


# canonical agent session type; reused by the model and by the public schema
class SessionType(StrEnum):
    CHAT = "chat"
    PROJECT = "project"


# agent session summary composed from SDK sessions + session metadata
class AgentSessionSummarySchema(BaseModel):
    session_id: str
    session_type: SessionType = SessionType.CHAT
    title: str = ""
    agent_code: str = ""
    owner_id: int = 0
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


# list agent sessions response schema
class ListAgentSessionsResponse(BaseModel):
    items: list[AgentSessionSummarySchema]


# replay SDK session messages as content events
class ListAgentEventsResponse(BaseModel):
    session_id: str
    items: list[AgentContentEventSchema]


# create agent session response schema (server-allocated session_id)
class CreateAgentSessionResponse(BaseModel):
    session_id: str


# one available agent; surfaced to the @-mention picker in the chat input
class AgentInfoSchema(BaseModel):
    code: str
    name: str
    description: str = ""


# list of agents + the default agent for brand-new sessions
class ListAgentsResponse(BaseModel):
    items: list[AgentInfoSchema]
    default_code: str
