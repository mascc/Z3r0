from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter


class AgentEventTypeSchema(StrEnum):
    USER_MESSAGE = "user_message"
    THINKING_DELTA = "thinking_delta"
    THINKING_COMPLETE = "thinking_complete"
    TEXT_DELTA = "text_delta"
    TEXT_COMPLETE = "text_complete"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    HANDOFF = "handoff"
    DONE = "done"
    ERROR = "error"


class _AgentScopedEvent(BaseModel):
    agent_name: str = ""


class UserMessageEvent(BaseModel):
    type: Literal[AgentEventTypeSchema.USER_MESSAGE] = AgentEventTypeSchema.USER_MESSAGE
    text: str


class TextDeltaEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.TEXT_DELTA] = AgentEventTypeSchema.TEXT_DELTA
    item_id: str
    delta: str


class TextCompleteEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.TEXT_COMPLETE] = AgentEventTypeSchema.TEXT_COMPLETE
    item_id: str
    text: str


class ThinkingDeltaEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.THINKING_DELTA] = AgentEventTypeSchema.THINKING_DELTA
    item_id: str
    delta: str


class ThinkingCompleteEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.THINKING_COMPLETE] = AgentEventTypeSchema.THINKING_COMPLETE
    item_id: str
    text: str


class ToolCallEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.TOOL_CALL] = AgentEventTypeSchema.TOOL_CALL
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResultEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.TOOL_RESULT] = AgentEventTypeSchema.TOOL_RESULT
    call_id: str
    output: str = ""
    is_error: bool = False


class HandoffEvent(BaseModel):
    type: Literal[AgentEventTypeSchema.HANDOFF] = AgentEventTypeSchema.HANDOFF
    source_agent: str
    target_agent: str


class DoneEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.DONE] = AgentEventTypeSchema.DONE


class ErrorEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.ERROR] = AgentEventTypeSchema.ERROR
    message: str
    code: str = ""


AgentContentEventSchema = Annotated[
    UserMessageEvent
    | TextDeltaEvent
    | TextCompleteEvent
    | ThinkingDeltaEvent
    | ThinkingCompleteEvent
    | ToolCallEvent
    | ToolResultEvent
    | HandoffEvent
    | ErrorEvent,
    Field(discriminator="type"),
]

AgentEventSchema = Annotated[
    UserMessageEvent
    | TextDeltaEvent
    | TextCompleteEvent
    | ThinkingDeltaEvent
    | ThinkingCompleteEvent
    | ToolCallEvent
    | ToolResultEvent
    | HandoffEvent
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="type"),
]


agent_content_event_adapter: TypeAdapter[AgentContentEventSchema] = TypeAdapter(AgentContentEventSchema)
agent_event_adapter: TypeAdapter[AgentEventSchema] = TypeAdapter(AgentEventSchema)
