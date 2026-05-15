import asyncio
from datetime import datetime
from http import HTTPStatus

from fastapi.websockets import WebSocketState
from fastapi import WebSocket, WebSocketDisconnect, status as ws_status
from pydantic import ValidationError

from core.delegation.subagents import subscribe_session_events, unsubscribe_session_events
from core.runtime.session import get_agent_pool
from logger import get_logger
from middleware.auth import AuthUser, decode_access_token
from schema.agent.events import (
    AgentEventSchema,
    AgentStreamActionSchema,
    ErrorEvent,
    agent_stream_command_adapter,
)
from schema.agent.sessions import (
    CreateAgentSessionResponse,
    ListAgentEventsResponse,
    ListAgentSessionsResponse,
)
from schema.common.responses import CommonResponse
from service.agent import runtime as agent_runtime
from service.agent import sessions as agent_sessions


logger = get_logger(__name__)


async def create_agent_session_handler(user: AuthUser) -> CommonResponse:
    session_id = await agent_sessions.create_session(user_id=user.id)
    return CommonResponse(data=CreateAgentSessionResponse(session_id=session_id))


async def delete_agent_session_handler(session_id: str, user: AuthUser) -> CommonResponse:
    deleted = await agent_sessions.delete_session(
        session_id,
        user_id=user.id,
        user_role=user.role,
    )
    if not deleted:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="agent session not found")
    return CommonResponse(message="agent session deleted")


async def list_agent_sessions_handler(limit: int, user: AuthUser) -> CommonResponse:
    sessions = await agent_sessions.list_sessions(
        limit=limit,
        user_id=user.id,
        user_role=user.role,
    )
    return CommonResponse(data=ListAgentSessionsResponse(items=sessions))


async def list_agent_events_handler(session_id: str, user: AuthUser) -> CommonResponse:
    events = await agent_sessions.replay_session_events(
        session_id=session_id,
        user_id=user.id,
        user_role=user.role,
    )
    if events is None:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="agent session not found")
    return CommonResponse(data=ListAgentEventsResponse(session_id=session_id, items=events))


async def handle_agent_stream(websocket: WebSocket, session_id: str, token: str) -> None:
    user = _decode_ws_token(token)
    if user is None:
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return
    if not await agent_sessions.can_access_session(session_id, user.id, user.role):
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    send_lock = asyncio.Lock()
    runtime = None
    runtime_events: asyncio.Queue[AgentEventSchema] | None = None
    subscriber: asyncio.Queue[AgentEventSchema] | None = None
    runtime_forwarder: asyncio.Task | None = None
    subagent_forwarder: asyncio.Task | None = None

    try:
        runtime, runtime_events = await get_agent_pool().subscribe(session_id)
        subscriber = await subscribe_session_events(session_id)
        runtime_forwarder = asyncio.create_task(_forward_events(websocket, runtime_events, send_lock))
        subagent_forwarder = asyncio.create_task(_forward_events(websocket, subscriber, send_lock))

        while True:
            payload = await websocket.receive_json()
            try:
                command = agent_stream_command_adapter.validate_python(payload)
            except ValidationError:
                logger.debug("agent stream ignored invalid payload: %r", payload)
                continue

            if command.action == AgentStreamActionSchema.INTERRUPT:
                await _interrupt_turn(websocket, session_id, user, send_lock)
                continue

            if command.action == AgentStreamActionSchema.CANCEL_ALL:
                await _cancel_all_tasks(websocket, session_id, user, send_lock)
                continue

            text = command.text.strip()
            if not text:
                continue
            await _start_turn(
                websocket=websocket,
                session_id=session_id,
                text=text,
                user=user,
                sandbox_container_id=command.sandbox_container_id,
                requested_agent_code=command.agent_code,
                send_lock=send_lock,
            )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("agent stream failed for session=%s", session_id)
        await _close_silently(websocket)
    finally:
        if runtime is not None and runtime_events is not None:
            runtime.unsubscribe(runtime_events)
        if subscriber is not None:
            await unsubscribe_session_events(session_id, subscriber)
        await _cancel_task(runtime_forwarder)
        await _cancel_task(subagent_forwarder)


async def _start_turn(
    websocket: WebSocket,
    session_id: str,
    text: str,
    user: AuthUser,
    sandbox_container_id: int | None,
    requested_agent_code: str | None,
    send_lock: asyncio.Lock,
) -> None:
    try:
        await agent_runtime.submit_turn(
            session_id=session_id,
            text=text,
            user=user,
            sandbox_container_id=sandbox_container_id,
            requested_agent_code=requested_agent_code,
        )
    except PermissionError:
        await _send_event(websocket, agent_runtime.not_found_error(), send_lock)
        await _send_event(websocket, agent_runtime.done_event(), send_lock)
    except Exception as exc:
        logger.exception("agent turn failed for session=%s", session_id)
        await _send_event(websocket, ErrorEvent(created_at=datetime.now(), message=str(exc) or "agent turn failed"), send_lock)
        await _send_event(websocket, agent_runtime.done_event(), send_lock)


async def _interrupt_turn(
    websocket: WebSocket,
    session_id: str,
    user: AuthUser,
    send_lock: asyncio.Lock,
) -> None:
    try:
        interrupted = await agent_runtime.interrupt_turn(session_id=session_id, user=user)
    except PermissionError:
        await _send_event(websocket, agent_runtime.not_found_error(), send_lock)
        await _send_event(websocket, agent_runtime.done_event(), send_lock)
        return
    if not interrupted:
        await _send_event(websocket, agent_runtime.done_event(), send_lock)


async def _cancel_all_tasks(
    websocket: WebSocket,
    session_id: str,
    user: AuthUser,
    send_lock: asyncio.Lock,
) -> None:
    try:
        await agent_runtime.cancel_all_tasks(session_id=session_id, user=user)
    except PermissionError:
        await _send_event(websocket, agent_runtime.not_found_error(), send_lock)
    await _send_event(websocket, agent_runtime.done_event(), send_lock)


async def _send_event(
    websocket: WebSocket,
    event: AgentEventSchema,
    send_lock: asyncio.Lock | None = None,
) -> bool:
    if (
        websocket.client_state != WebSocketState.CONNECTED
        or websocket.application_state != WebSocketState.CONNECTED
    ):
        return False
    try:
        if send_lock is None:
            await websocket.send_text(event.model_dump_json())
        else:
            async with send_lock:
                await websocket.send_text(event.model_dump_json())
        return True
    except Exception:
        logger.debug("failed to send agent event to websocket", exc_info=True)
        return False


async def _forward_events(
    websocket: WebSocket,
    queue: asyncio.Queue[AgentEventSchema],
    send_lock: asyncio.Lock,
) -> None:
    try:
        while True:
            event = await queue.get()
            if not await _send_event(websocket, event, send_lock):
                return
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("agent event forwarding stopped", exc_info=True)


async def _cancel_task(task: asyncio.Task | None) -> None:
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _close_silently(websocket: WebSocket) -> None:
    try:
        await websocket.close(code=ws_status.WS_1011_INTERNAL_ERROR)
    except Exception:
        pass


def _decode_ws_token(token: str) -> AuthUser | None:
    try:
        return decode_access_token(token)
    except Exception:
        return None
