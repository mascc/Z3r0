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
    DONE = "done"
    ERROR = "error"


class AgentStreamActionSchema(StrEnum):
    SEND = "send"
    INTERRUPT = "interrupt"


class _AgentScopedEvent(BaseModel):
    agent_name: str = ""
    # when set, this event was streamed from inside a nested subagent call.
    # `nested_for` is the parent agent code; `nested_call_id` matches the
    # parent's function_call.call_id so the UI can attach the event to the
    # corresponding ToolCard
    nested_for: str = ""
    nested_call_id: str = ""


class UserMessageEvent(BaseModel):
    type: Literal[AgentEventTypeSchema.USER_MESSAGE] = AgentEventTypeSchema.USER_MESSAGE
    text: str
    # the agent this message was @-mentioned to; UI renders it as a "@<name>" chip
    target_agent_code: str = ""


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


class DoneEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.DONE] = AgentEventTypeSchema.DONE


class ErrorEvent(_AgentScopedEvent):
    type: Literal[AgentEventTypeSchema.ERROR] = AgentEventTypeSchema.ERROR
    message: str
    code: str = ""


# everything that shows up in stored history (DoneEvent is a stream control signal only)
AgentContentEventSchema = Annotated[
    UserMessageEvent
    | TextDeltaEvent
    | TextCompleteEvent
    | ThinkingDeltaEvent
    | ThinkingCompleteEvent
    | ToolCallEvent
    | ToolResultEvent
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
    | DoneEvent
    | ErrorEvent,
    Field(discriminator="type"),
]


class AgentStreamSendCommand(BaseModel):
    action: Literal[AgentStreamActionSchema.SEND] = AgentStreamActionSchema.SEND
    text: str
    sandbox_container_id: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Selected running sandbox container. Backend mounts sandbox tools "
            "only when this container is still usable by the current user."
        ),
    )
    # optional @-mention override; null => keep the session's sticky agent
    agent_code: str | None = Field(default=None)


class AgentStreamInterruptCommand(BaseModel):
    action: Literal[AgentStreamActionSchema.INTERRUPT] = AgentStreamActionSchema.INTERRUPT


AgentStreamCommandSchema = Annotated[
    AgentStreamSendCommand | AgentStreamInterruptCommand,
    Field(discriminator="action"),
]


agent_content_event_adapter: TypeAdapter[AgentContentEventSchema] = TypeAdapter(AgentContentEventSchema)
agent_event_adapter: TypeAdapter[AgentEventSchema] = TypeAdapter(AgentEventSchema)
agent_stream_command_adapter: TypeAdapter[AgentStreamCommandSchema] = TypeAdapter(AgentStreamCommandSchema)
