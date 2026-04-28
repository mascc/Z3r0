from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel

from schema.agent_event_schema import AgentContentEventSchema


# public mirror of model.agent_session_meta_model.SessionType
class SessionTypeSchema(StrEnum):
    CHAT = "chat"
    PROJECT = "project"


# agent session summary composed from SDK sessions + session metadata
class AgentSessionSummarySchema(BaseModel):
    session_id: str
    session_type: SessionTypeSchema = SessionTypeSchema.CHAT
    title: str = ""
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
