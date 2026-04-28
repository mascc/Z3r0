import asyncio
from http import HTTPStatus
from typing import Any

import jwt
from fastapi import WebSocket, WebSocketDisconnect, status as ws_status

from config import get_config
from core.agents import get_z3r0_agent_pool
from logger import get_logger
from schema.agent_event_schema import AgentEventSchema, DoneEvent, ErrorEvent
from schema.agent_session_schema import (
    CreateAgentSessionResponse,
    ListAgentEventsResponse,
    ListAgentSessionsResponse,
)
from schema.response_schema import CommonResponse
from service import agent_session_service


logger = get_logger(__name__)

_MAX_SESSION_LIMIT = 100
_ACTION_SEND = "send"
_ACTION_INTERRUPT = "interrupt"


async def create_agent_session_handler() -> CommonResponse:
    """allocate a fresh session_id; the row materializes when the first turn lands"""
    session_id = agent_session_service.create_session()
    return CommonResponse(data=CreateAgentSessionResponse(session_id=session_id))


async def delete_agent_session_handler(session_id: str) -> CommonResponse:
    """delete an agent session and discard its pooled agent"""
    await get_z3r0_agent_pool().discard(session_id)
    deleted = await agent_session_service.delete_session(session_id=session_id)
    if not deleted:
        return CommonResponse(
            code=HTTPStatus.NOT_FOUND.value,
            message="agent session not found",
        )
    return CommonResponse(message="agent session deleted")


async def list_agent_sessions_handler(limit: int = _MAX_SESSION_LIMIT) -> CommonResponse:
    """list the most recent agent sessions for the sidebar"""
    if limit < 1 or limit > _MAX_SESSION_LIMIT:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message=f"limit must be between 1 and {_MAX_SESSION_LIMIT}",
        )
    sessions = await agent_session_service.list_sessions(limit=limit)
    return CommonResponse(data=ListAgentSessionsResponse(items=sessions))


async def list_agent_events_handler(session_id: str) -> CommonResponse:
    """replay SDK session messages as content events"""
    events = await agent_session_service.replay_session_events(session_id=session_id)
    return CommonResponse(data=ListAgentEventsResponse(session_id=session_id, items=events))


def _decode_ws_token(token: str) -> dict[str, Any] | None:
    if not token:
        return None
    cfg = get_config()
    try:
        return jwt.decode(
            token,
            key=cfg.system.encrypt_key,
            algorithms=["HS256"],
            options={"require": ["exp", "id", "role", "email", "username", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None


async def _send_event(websocket: WebSocket, event: AgentEventSchema) -> None:
    await websocket.send_text(event.model_dump_json())


async def _safe_send(websocket: WebSocket, event: AgentEventSchema) -> None:
    try:
        await _send_event(websocket, event)
    except Exception:
        logger.debug("failed to send agent event to websocket", exc_info=True)


async def _run_completion(websocket: WebSocket, session_id: str, text: str) -> None:
    terminal_event: AgentEventSchema | None = None
    runtime = get_z3r0_agent_pool().get_or_create(session_id)
    try:
        async for event in runtime.complete(text):
            terminal_event = event
            await _send_event(websocket, event)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("agent completion failed for session=%s", session_id)
        error_event = ErrorEvent(message=str(exc) or "agent completion failed")
        terminal_event = error_event
        await _safe_send(websocket, error_event)
    finally:
        if not isinstance(terminal_event, DoneEvent):
            await _safe_send(websocket, DoneEvent(agent_name=""))


async def _cancel_task(task: asyncio.Task | None) -> None:
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def handle_agent_stream(websocket: WebSocket, session_id: str, token: str) -> None:
    """drive one websocket connection: receive commands and stream events back"""
    if _decode_ws_token(token) is None:
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    current: asyncio.Task | None = None

    try:
        while True:
            message = await websocket.receive_json()
            action = message.get("action")

            if action == _ACTION_INTERRUPT:
                had_local_task = current is not None and not current.done()
                interrupted = await get_z3r0_agent_pool().get_or_create(session_id).interrupt()
                await _cancel_task(current)
                current = None
                if interrupted and not had_local_task:
                    await _safe_send(websocket, DoneEvent(agent_name=""))
                continue

            if action == _ACTION_SEND:
                text = str(message.get("text", "")).strip()
                if not text:
                    continue
                await _cancel_task(current)
                current = asyncio.create_task(_run_completion(websocket, session_id, text))
                continue

            logger.info("agent stream ignored unknown action: %r", action)
    except WebSocketDisconnect:
        await _cancel_task(current)
    except Exception:
        logger.exception("agent stream failed for session=%s", session_id)
        await _cancel_task(current)
        try:
            await websocket.close(code=ws_status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
