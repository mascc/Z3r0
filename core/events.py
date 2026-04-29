import json
from typing import Any

from agents.items import (
    HandoffCallItem,
    HandoffOutputItem,
    ToolCallItem,
    ToolCallOutputItem,
)
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent
from openai.types.responses.response_error_event import ResponseErrorEvent
from openai.types.responses.response_reasoning_summary_text_delta_event import (
    ResponseReasoningSummaryTextDeltaEvent,
)
from openai.types.responses.response_reasoning_summary_text_done_event import (
    ResponseReasoningSummaryTextDoneEvent,
)
from openai.types.responses.response_reasoning_text_delta_event import (
    ResponseReasoningTextDeltaEvent,
)
from openai.types.responses.response_reasoning_text_done_event import (
    ResponseReasoningTextDoneEvent,
)
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent
from openai.types.responses.response_text_done_event import ResponseTextDoneEvent
from pydantic import BaseModel

from schema.agent_event_schema import (
    AgentEventSchema,
    ErrorEvent,
    HandoffEvent,
    TextCompleteEvent,
    TextDeltaEvent,
    ThinkingCompleteEvent,
    ThinkingDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
    UserMessageEvent,
)


# `incomplete` is a partial output, not an error
_TOOL_ERROR_STATUSES = {"failed", "error"}

# tag reasoning items so body text and per-summary segments do not collide
# under the same item_id in the frontend reducer
_THINKING_TEXT_SUFFIX = "#text"
_THINKING_SUMMARY_SUFFIX = "#summary"


def event_from_sdk_stream(sdk_event: Any, current_agent: str) -> AgentEventSchema | None:
    """live SDK stream event -> normalized event (None when suppressed)"""
    if isinstance(sdk_event, RawResponsesStreamEvent):
        return _from_raw_response(sdk_event.data, current_agent)
    if isinstance(sdk_event, RunItemStreamEvent):
        return _from_run_item(sdk_event, current_agent)
    return None


def events_from_sdk_message(message: Any, fallback_id: str) -> list[AgentEventSchema]:
    """stored SDK message -> 0..N replay events (agent_name not stored)"""
    if not isinstance(message, dict):
        return []

    item_id = _stored_item_id(message, fallback_id)
    match message.get("type"):
        case "message":
            return _events_from_stored_message(message, item_id)
        case "reasoning":
            text = _stored_reasoning_text(message)
            return [ThinkingCompleteEvent(item_id=item_id + _THINKING_TEXT_SUFFIX, text=text)] if text else []
        case "function_call":
            return [ToolCallEvent(
                call_id=str(message.get("call_id") or message.get("id") or ""),
                name=str(message.get("name") or ""),
                arguments=_parse_tool_arguments(message.get("arguments")),
            )]
        case "function_call_output":
            return [ToolResultEvent(
                call_id=str(message.get("call_id") or ""),
                output=_normalize_to_str(message.get("output")),
                is_error=_is_tool_error(message.get("status")),
            )]
    return []


def _from_raw_response(data: Any, current_agent: str) -> AgentEventSchema | None:
    if isinstance(data, ResponseTextDeltaEvent):
        return TextDeltaEvent(agent_name=current_agent, item_id=data.item_id, delta=data.delta)
    if isinstance(data, ResponseTextDoneEvent):
        return TextCompleteEvent(agent_name=current_agent, item_id=data.item_id, text=data.text)
    if isinstance(data, ResponseReasoningTextDeltaEvent):
        return ThinkingDeltaEvent(
            agent_name=current_agent,
            item_id=data.item_id + _THINKING_TEXT_SUFFIX,
            delta=data.delta,
        )
    if isinstance(data, ResponseReasoningTextDoneEvent):
        return ThinkingCompleteEvent(
            agent_name=current_agent,
            item_id=data.item_id + _THINKING_TEXT_SUFFIX,
            text=data.text,
        )
    if isinstance(data, ResponseReasoningSummaryTextDeltaEvent):
        return ThinkingDeltaEvent(
            agent_name=current_agent,
            item_id=f"{data.item_id}{_THINKING_SUMMARY_SUFFIX}{getattr(data, 'summary_index', 0)}",
            delta=data.delta,
        )
    if isinstance(data, ResponseReasoningSummaryTextDoneEvent):
        return ThinkingCompleteEvent(
            agent_name=current_agent,
            item_id=f"{data.item_id}{_THINKING_SUMMARY_SUFFIX}{getattr(data, 'summary_index', 0)}",
            text=data.text,
        )
    if isinstance(data, ResponseErrorEvent):
        return ErrorEvent(agent_name=current_agent, message=data.message, code=data.code or "")
    return None


def _from_run_item(event: RunItemStreamEvent, current_agent: str) -> AgentEventSchema | None:
    item = event.item
    agent_name = item.agent.name if item.agent is not None else current_agent

    if event.name == "tool_called" and isinstance(item, ToolCallItem):
        raw = item.raw_item
        return ToolCallEvent(
            agent_name=agent_name,
            call_id=_read_field(raw, "call_id") or _read_field(raw, "id") or "",
            name=_read_field(raw, "name") or item.title or "",
            arguments=_parse_tool_arguments(_read_field(raw, "arguments")),
        )

    if event.name == "tool_output" and isinstance(item, ToolCallOutputItem):
        raw = item.raw_item
        return ToolResultEvent(
            agent_name=agent_name,
            call_id=_read_field(raw, "call_id") or "",
            output=_normalize_to_str(item.output),
            is_error=_is_tool_error(_read_field(raw, "status")),
        )

    if event.name == "handoff_occured" and isinstance(item, HandoffOutputItem):
        return HandoffEvent(
            source_agent=item.source_agent.name if item.source_agent else current_agent,
            target_agent=item.target_agent.name if item.target_agent else "",
        )

    # handoff_requested duplicates handoff_occured; suppress
    if event.name == "handoff_requested" and isinstance(item, HandoffCallItem):
        return None

    return None


def _events_from_stored_message(message: dict[str, Any], item_id: str) -> list[AgentEventSchema]:
    text = _stored_message_text(message.get("content"))
    if not text:
        return []
    role = message.get("role")
    if role == "user":
        return [UserMessageEvent(text=text)]
    if role == "assistant":
        return [TextCompleteEvent(item_id=item_id, text=text)]
    return []


def _stored_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and item.get("type") in {"input_text", "output_text", "text"}:
            parts.append(text)
    return "".join(parts)


def _stored_reasoning_text(message: dict[str, Any]) -> str:
    summary = message.get("summary")
    if isinstance(summary, str):
        return summary
    if not isinstance(summary, list):
        return ""
    parts: list[str] = []
    for item in summary:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "".join(parts)


def _stored_item_id(message: dict[str, Any], fallback_id: str) -> str:
    return str(message.get("id") or message.get("call_id") or fallback_id)


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
    return decoded if isinstance(decoded, dict) else {"_value": decoded}


def _normalize_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, BaseModel):
        return value.model_dump_json()
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _is_tool_error(status: Any) -> bool:
    return isinstance(status, str) and status.lower() in _TOOL_ERROR_STATUSES


def _read_field(raw: Any, key: str) -> Any:
    if isinstance(raw, dict):
        return raw.get(key)
    return getattr(raw, key, None)
