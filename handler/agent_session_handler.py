import asyncio
from http import HTTPStatus

from fastapi.websockets import WebSocketState
import jwt
from fastapi import WebSocket, WebSocketDisconnect, status as ws_status
from pydantic import ValidationError

from config import get_config
from core.context import AgentRuntimeContext, AgentUserContext
from core.runtime import get_agent_pool
from logger import get_logger
from middleware.auth import AuthUser
from schema.agent_event_schema import (
    AgentEventSchema,
    AgentStreamActionSchema,
    DoneEvent,
    ErrorEvent,
    agent_stream_command_adapter,
)
from schema.agent_session_schema import (
    CreateAgentSessionResponse,
    ListAgentEventsResponse,
    ListAgentSessionsResponse,
)
from schema.response_schema import CommonResponse
from service import agent_session_service
from service.sandbox_container_service import resolve_sandbox_container_tool_binding


logger = get_logger(__name__)


async def create_agent_session_handler(user: AuthUser) -> CommonResponse:
    session_id = await agent_session_service.create_session(user_id=user.id)
    return CommonResponse(data=CreateAgentSessionResponse(session_id=session_id))


async def delete_agent_session_handler(session_id: str, user: AuthUser) -> CommonResponse:
    deleted = await agent_session_service.delete_session(
        session_id,
        user_id=user.id,
        user_role=user.role,
    )
    if not deleted:
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="agent session not found")
    return CommonResponse(message="agent session deleted")


async def list_agent_sessions_handler(limit: int, user: AuthUser) -> CommonResponse:
    sessions = await agent_session_service.list_sessions(
        limit=limit,
        user_id=user.id,
        user_role=user.role,
    )
    return CommonResponse(data=ListAgentSessionsResponse(items=sessions))


async def list_agent_events_handler(session_id: str, user: AuthUser) -> CommonResponse:
    events = await agent_session_service.replay_session_events(
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

    await websocket.accept()
    runner: asyncio.Task | None = None

    try:
        while True:
            payload = await websocket.receive_json()
            try:
                command = agent_stream_command_adapter.validate_python(payload)
            except ValidationError:
                logger.info("agent stream ignored invalid payload: %r", payload)
                continue

            if command.action == AgentStreamActionSchema.INTERRUPT:
                await _interrupt_turn(websocket, session_id, runner, user)
                runner = None
                continue

            text = command.text.strip()
            if not text:
                continue
            await _cancel_task(runner)
            runner = asyncio.create_task(_run_turn(
                websocket=websocket,
                session_id=session_id,
                text=text,
                user=user,
                sandbox_container_id=command.sandbox_container_id,
                requested_agent_code=command.agent_code,
            ))
    except WebSocketDisconnect:
        await _cancel_task(runner)
    except Exception:
        logger.exception("agent stream failed for session=%s", session_id)
        await _cancel_task(runner)
        await _close_silently(websocket)


async def _run_turn(
    websocket: WebSocket,
    session_id: str,
    text: str,
    user: AuthUser,
    sandbox_container_id: int | None,
    requested_agent_code: str | None,
) -> None:
    # always emits a DoneEvent so the client exits streaming
    saw_done = False
    try:
        agent_code = await agent_session_service.ensure_chat_session_meta(
            session_id,
            text,
            requested_agent_code,
            user_id=user.id,
            user_role=user.role,
        )
        context = await _build_runtime_context(session_id, user, sandbox_container_id)
        runtime = get_agent_pool().get_or_create(session_id)
        async for event in runtime.stream_turn(text, agent_code, context):
            if isinstance(event, DoneEvent):
                saw_done = True
            if not await _send_event(websocket, event):
                return
    except asyncio.CancelledError:
        raise
    except PermissionError:
        await _send_event(websocket, ErrorEvent(message="agent session not found", code="not_found"))
    except Exception as exc:
        logger.exception("agent turn failed for session=%s", session_id)
        await _send_event(websocket, ErrorEvent(message=str(exc) or "agent turn failed"))
    finally:
        if not saw_done:
            await _send_event(websocket, DoneEvent())


async def _interrupt_turn(
    websocket: WebSocket,
    session_id: str,
    runner: asyncio.Task | None,
    user: AuthUser,
) -> None:
    if not await agent_session_service.can_access_session(session_id, user.id, user.role):
        await _send_event(websocket, ErrorEvent(message="agent session not found", code="not_found"))
        await _send_event(websocket, DoneEvent())
        return

    had_local_runner = runner is not None and not runner.done()
    interrupted = await get_agent_pool().try_interrupt(session_id)
    await _cancel_task(runner)
    if interrupted and not had_local_runner:
        await _send_event(websocket, DoneEvent())


async def _send_event(websocket: WebSocket, event: AgentEventSchema) -> bool:
    if (
        websocket.client_state != WebSocketState.CONNECTED
        or websocket.application_state != WebSocketState.CONNECTED
    ):
        return False
    try:
        await websocket.send_text(event.model_dump_json())
        return True
    except Exception:
        logger.debug("failed to send agent event to websocket", exc_info=True)
        return False


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


async def _build_runtime_context(
    session_id: str,
    user: AuthUser,
    sandbox_container_id: int | None,
) -> AgentRuntimeContext:
    selected_container_id = None
    selected_container_generation = 0
    if sandbox_container_id is not None:
        binding = await resolve_sandbox_container_tool_binding(
            id=sandbox_container_id,
            user_id=user.id,
            user_role=user.role,
        )
        if binding is not None:
            selected_container_id = binding.id
            selected_container_generation = binding.generation

    return AgentRuntimeContext(
        session_id=session_id,
        user=AgentUserContext(
            id=user.id,
            username=user.username,
            email=user.email,
            role=user.role,
        ),
        sandbox_container_id=selected_container_id,
        sandbox_container_generation=selected_container_generation,
    )


def _decode_ws_token(token: str) -> AuthUser | None:
    if not token:
        return None
    cfg = get_config()
    try:
        payload = jwt.decode(
            token,
            key=cfg.system.encrypt_key,
            algorithms=["HS256"],
            options={"require": ["exp", "id", "role", "email", "username", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None
    try:
        if payload.get("sub") != "z3r0":
            return None
        return AuthUser.from_payload(payload)
    except (KeyError, ValueError, TypeError):
        return None
