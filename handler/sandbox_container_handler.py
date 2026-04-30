import asyncio
import json
from http import HTTPStatus
from typing import Any

import jwt
from fastapi import WebSocket, WebSocketDisconnect, status as ws_status
from fastapi.websockets import WebSocketState

from config import get_config
from logger import get_logger
from schema.response_schema import CommonResponse
from schema.sandbox_container_schema import (
    CreateSandboxContainerRequest,
    DeleteSandboxContainerResponse,
    QuerySandboxContainersResponse,
    SandboxContainerSchema,
)
from schema.system_user_schema import SystemUserRole
from service.sandbox_container_service import (
    ContainerShellSession,
    SandboxContainerMutationResult,
    SandboxContainerRecord,
    create_sandbox_container,
    delete_sandbox_container,
    open_container_shell,
    query_available_sandbox_containers,
    query_sandbox_containers,
    read_container_shell,
    resize_container_shell,
    resolve_shell_container,
    start_sandbox_container,
    stop_sandbox_container,
    write_container_shell,
)


logger = get_logger(__name__)


def _sandbox_container_schema(record: SandboxContainerRecord) -> SandboxContainerSchema:
    container = record.container
    return SandboxContainerSchema(
        id=container.id or 0,
        container_name=container.container_name,
        container_hash=container.container_hash,
        image_id=container.image_id,
        image_name=record.image_name,
        container_command=container.container_command,
        port_mappings=container.port_mappings,
        status=container.status,
        owner_id=container.owner_id,
        owner_username=record.owner_username,
        created_at=container.created_at,
        updated_at=container.updated_at,
    )


def _mutation_response(result: SandboxContainerMutationResult) -> CommonResponse:
    if result.record is None:
        status = HTTPStatus.NOT_FOUND if result.not_found else HTTPStatus.BAD_REQUEST
        return CommonResponse(code=status.value, message=result.message)
    if not result.changed:
        return CommonResponse(
            code=HTTPStatus.BAD_REQUEST.value,
            message=result.message,
            data=_sandbox_container_schema(result.record),
        )
    return CommonResponse(
        message=result.message,
        data=_sandbox_container_schema(result.record),
    )


async def create_sandbox_container_handler(
    request: CreateSandboxContainerRequest,
    owner_id: int,
) -> CommonResponse:
    result = await create_sandbox_container(
        image_id=request.image_id,
        owner_id=owner_id,
        container_command=request.container_command,
        port_mappings=request.port_mappings,
    )
    return _mutation_response(result)


async def start_sandbox_container_handler(id: int) -> CommonResponse:
    return _mutation_response(await start_sandbox_container(id))


async def stop_sandbox_container_handler(id: int) -> CommonResponse:
    return _mutation_response(await stop_sandbox_container(id))


async def delete_sandbox_container_handler(id: int) -> CommonResponse:
    if not await delete_sandbox_container(id):
        return CommonResponse(code=HTTPStatus.NOT_FOUND.value, message="sandbox container not found")
    return CommonResponse(data=DeleteSandboxContainerResponse(id=id))


async def query_sandbox_containers_handler(page: int, size: int, keyword: str) -> CommonResponse:
    sandbox_containers = await query_sandbox_containers(page=page, size=size, keyword=keyword)
    return CommonResponse(data=QuerySandboxContainersResponse(
        page=page,
        size=size,
        items=[_sandbox_container_schema(record) for record in sandbox_containers],
    ))


async def query_available_sandbox_containers_handler(
    page: int,
    size: int,
    keyword: str,
    user_id: int,
    user_role: SystemUserRole,
) -> CommonResponse:
    sandbox_containers = await query_available_sandbox_containers(
        page=page,
        size=size,
        keyword=keyword,
        user_id=user_id,
        user_role=user_role,
    )
    return CommonResponse(data=QuerySandboxContainersResponse(
        page=page,
        size=size,
        items=[_sandbox_container_schema(record) for record in sandbox_containers],
    ))


async def handle_container_shell_stream(websocket: WebSocket, container_hash: str, token: str) -> None:
    if not _is_admin_ws_token(token):
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    sandbox_container = await resolve_shell_container(container_hash)
    if sandbox_container is None:
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    shell: ContainerShellSession | None = None
    reader: asyncio.Task | None = None
    receiver: asyncio.Task | None = None

    try:
        shell = await open_container_shell(container_hash)
        reader = asyncio.create_task(_forward_shell_output(websocket, shell))

        while True:
            receiver = asyncio.create_task(websocket.receive_text())
            done, _ = await asyncio.wait(
                {receiver, reader},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if reader in done:
                await reader
                await _close_silently(websocket, ws_status.WS_1000_NORMAL_CLOSURE)
                return

            message = receiver.result()
            receiver = None
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                await write_container_shell(shell, message)
                continue

            if not isinstance(payload, dict):
                continue
            message_type = payload.get("type")
            if message_type == "input":
                await write_container_shell(shell, str(payload.get("data", "")))
            elif message_type == "resize":
                rows = _bounded_int(payload.get("rows"), default=24, minimum=1, maximum=300)
                cols = _bounded_int(payload.get("cols"), default=80, minimum=1, maximum=500)
                await resize_container_shell(shell, rows=rows, cols=cols)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("container shell stream failed: %s", container_hash)
        await _close_silently(websocket)
    finally:
        try:
            if shell is not None:
                shell.shutdown()
            await _cancel_task(receiver)
            await _finish_reader_task(reader)
        finally:
            if shell is not None:
                await asyncio.to_thread(shell.close)


async def _forward_shell_output(websocket: WebSocket, shell: ContainerShellSession) -> None:
    while True:
        data = await read_container_shell(shell)
        if not data:
            return
        if websocket.client_state != WebSocketState.CONNECTED or websocket.application_state != WebSocketState.CONNECTED:
            return
        await websocket.send_bytes(data)


async def _cancel_task(task: asyncio.Task | None) -> None:
    if task is None:
        return
    if task.done():
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _finish_reader_task(task: asyncio.Task | None) -> None:
    if task is None:
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=1)
    except asyncio.TimeoutError:
        await _cancel_task(task)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("container shell reader stopped with error", exc_info=True)


async def _close_silently(websocket: WebSocket, code: int = ws_status.WS_1011_INTERNAL_ERROR) -> None:
    try:
        await websocket.close(code=code)
    except Exception:
        pass


def _is_admin_ws_token(token: str) -> bool:
    payload = _decode_ws_token(token)
    return payload is not None and payload.get("role") == SystemUserRole.ADMIN.value


def _decode_ws_token(token: str) -> dict | None:
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
    if payload.get("sub") != "z3r0":
        return None
    return payload


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(number, maximum))
