"""Normalize SDK stream events and stored items into our wire schema."""

import json
from datetime import datetime
from typing import Any

from agents.items import ToolCallItem, ToolCallOutputItem
from agents.stream_events import RawResponsesStreamEvent, RunItemStreamEvent
from openai.types.responses.response_error_event import ResponseErrorEvent
from openai.types.responses.response_reasoning_summary_text_delta_event import (
    ResponseReasoningSummaryTextDeltaEvent,
)
from openai.types.responses.response_reasoning_summary_text_done_event import (
    ResponseReasoningSummaryTextDoneEvent,
)
from openai.types.responses.response_reasoning_text_delta_event import ResponseReasoningTextDeltaEvent
from openai.types.responses.response_reasoning_text_done_event import ResponseReasoningTextDoneEvent
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent
from openai.types.responses.response_text_done_event import ResponseTextDoneEvent
from pydantic import BaseModel

from schema.agent_event_schema import (
    AgentEventSchema,
    ErrorEvent,
    TextCompleteEvent,
    TextDeltaEvent,
    ThinkingCompleteEvent,
    ThinkingDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
    SubagentTaskEvent,
    UserMessageEvent,
)
from schema.agent_subordinate_schema import AgentSubordinateStatus


# `incomplete` is a partial output, not an error
_TOOL_ERROR_STATUSES = {"failed", "error"}

# disambiguate reasoning body text vs per-summary segments at the same item_id
_THINKING_TEXT_SUFFIX = "#text"
_THINKING_SUMMARY_SUFFIX = "#summary"

_TEXT_CONTENT_TYPES = {"input_text", "output_text", "text"}
_PLACEHOLDER_ITEM_IDS = {"", "__fake_id__"}


def event_from_sdk_stream(sdk_event: Any, current_agent: str) -> AgentEventSchema | None:
    created_at = datetime.now()
    if isinstance(sdk_event, RawResponsesStreamEvent):
        return _from_raw_response(sdk_event.data, current_agent, created_at)
    if isinstance(sdk_event, RunItemStreamEvent):
        return _from_run_item(sdk_event, current_agent, created_at)
    return None


def events_from_sdk_message(
    message: Any,
    fallback_id: str,
    *,
    created_at: datetime,
    owner_code: str = "",
    agent_name: str = "",
    nested_for: str = "",
    nested_call_id: str = "",
) -> list[AgentEventSchema]:
    if not isinstance(message, dict):
        return []

    item_id = _stored_item_id(message, fallback_id)
    scope = _scope(agent_name, nested_for, nested_call_id)
    match message.get("type"):
        case "message":
            return _events_from_stored_message(message, item_id, created_at, scope, owner_code)
        case "reasoning":
            text = _stored_reasoning_text(message)
            if not text:
                return []
            return [ThinkingCompleteEvent(created_at=created_at, item_id=item_id + _THINKING_TEXT_SUFFIX, text=text, **scope)]
        case "function_call":
            return [ToolCallEvent(
                created_at=created_at,
                call_id=str(message.get("call_id") or message.get("id") or ""),
                name=str(message.get("name") or ""),
                arguments=_parse_tool_arguments(message.get("arguments")),
                **scope,
            )]
        case "function_call_output":
            return [ToolResultEvent(
                created_at=created_at,
                call_id=str(message.get("call_id") or ""),
                output=_normalize_to_str(message.get("output")),
                is_error=_is_tool_error(message.get("status")),
                **scope,
            )]
    return []


def event_from_subagent_task(
    *,
    run_id: str,
    parent_agent_code: str,
    parent_agent_instance_id: str = "",
    agent_code: str,
    agent_name: str,
    status: AgentSubordinateStatus,
    result: str = "",
    error: str = "",
    progress: str = "",
    nested_call_id: str = "",
    created_at: datetime | None = None,
) -> SubagentTaskEvent:
    return SubagentTaskEvent(
        created_at=created_at or datetime.now(),
        agent_name=agent_name,
        nested_for=parent_agent_code,
        nested_call_id=nested_call_id,
        run_id=run_id,
        parent_agent_code=parent_agent_code,
        parent_agent_instance_id=parent_agent_instance_id,
        agent_code=agent_code,
        status=status,
        result=result,
        error=error,
        progress=progress,
    )


def _scope(agent_name: str, nested_for: str, nested_call_id: str) -> dict[str, str]:
    return {
        "agent_name": agent_name,
        "nested_for": nested_for,
        "nested_call_id": nested_call_id,
    }


def _from_raw_response(data: Any, current_agent: str, created_at: datetime) -> AgentEventSchema | None:
    if isinstance(data, ResponseTextDeltaEvent):
        return TextDeltaEvent(created_at=created_at, agent_name=current_agent, item_id=data.item_id, delta=data.delta)
    if isinstance(data, ResponseTextDoneEvent):
        return TextCompleteEvent(created_at=created_at, agent_name=current_agent, item_id=data.item_id, text=data.text)
    if isinstance(data, ResponseReasoningTextDeltaEvent):
        return ThinkingDeltaEvent(
            created_at=created_at,
            agent_name=current_agent,
            item_id=data.item_id + _THINKING_TEXT_SUFFIX,
            delta=data.delta,
        )
    if isinstance(data, ResponseReasoningTextDoneEvent):
        return ThinkingCompleteEvent(
            created_at=created_at,
            agent_name=current_agent,
            item_id=data.item_id + _THINKING_TEXT_SUFFIX,
            text=data.text,
        )
    if isinstance(data, ResponseReasoningSummaryTextDeltaEvent):
        return ThinkingDeltaEvent(
            created_at=created_at,
            agent_name=current_agent,
            item_id=f"{data.item_id}{_THINKING_SUMMARY_SUFFIX}{getattr(data, 'summary_index', 0)}",
            delta=data.delta,
        )
    if isinstance(data, ResponseReasoningSummaryTextDoneEvent):
        return ThinkingCompleteEvent(
            created_at=created_at,
            agent_name=current_agent,
            item_id=f"{data.item_id}{_THINKING_SUMMARY_SUFFIX}{getattr(data, 'summary_index', 0)}",
            text=data.text,
        )
    if isinstance(data, ResponseErrorEvent):
        return ErrorEvent(created_at=created_at, agent_name=current_agent, message=data.message, code=data.code or "")
    return None


def _from_run_item(event: RunItemStreamEvent, current_agent: str, created_at: datetime) -> AgentEventSchema | None:
    item = event.item
    agent_name = item.agent.name if item.agent is not None else current_agent

    if event.name == "tool_called" and isinstance(item, ToolCallItem):
        raw = item.raw_item
        return ToolCallEvent(
            created_at=created_at,
            agent_name=agent_name,
            call_id=_read_field(raw, "call_id") or _read_field(raw, "id") or "",
            name=_read_field(raw, "name") or item.title or "",
            arguments=_parse_tool_arguments(_read_field(raw, "arguments")),
        )
    if event.name == "tool_output" and isinstance(item, ToolCallOutputItem):
        raw = item.raw_item
        return ToolResultEvent(
            created_at=created_at,
            agent_name=agent_name,
            call_id=_read_field(raw, "call_id") or "",
            output=_normalize_to_str(item.output),
            is_error=_is_tool_error(_read_field(raw, "status")),
        )
    return None


def _events_from_stored_message(
    message: dict[str, Any], item_id: str, created_at: datetime, scope: dict[str, str], owner_code: str,
) -> list[AgentEventSchema]:
    text = _stored_message_text(message.get("content"))
    if not text:
        return []
    role = message.get("role")
    if role == "user" and text.lstrip().startswith("# Internal "):
        return []
    if role == "user" and scope.get("nested_for"):
        return []
    if role == "user":
        return [UserMessageEvent(created_at=created_at, text=text, target_agent_code=owner_code)]
    if role == "assistant":
        return [TextCompleteEvent(created_at=created_at, item_id=item_id, text=text, **scope)]
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
        if isinstance(text, str) and item.get("type") in _TEXT_CONTENT_TYPES:
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
    item_id = str(message.get("id") or "")
    if item_id and item_id not in _PLACEHOLDER_ITEM_IDS:
        return item_id
    call_id = str(message.get("call_id") or "")
    return call_id or fallback_id


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
