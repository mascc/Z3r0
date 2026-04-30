import asyncio
import socket as py_socket
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import docker
from docker.utils import socket as docker_socket
from sqlalchemy import String, cast, or_
from sqlmodel import select

from database import get_async_session
from logger import get_logger
from model.sandbox_container_model import SandboxContainer
from model.sandbox_image_model import SandboxImage
from model.system_user_model import SystemUser
from schema.sandbox_container_schema import (
    DEFAULT_SANDBOX_CONTAINER_COMMAND,
    SandboxContainerPortMapping,
    SandboxContainerStatus,
)
from schema.sandbox_image_schema import SandboxImageStatus
from schema.system_user_schema import SystemUserRole


logger = get_logger(__name__)

_SHELL_CANDIDATES = (("/bin/bash", "-l"), ("/bin/sh",))
_DEFAULT_SHELL_ROWS = 24
_DEFAULT_SHELL_COLS = 80
_STATUS_MONITOR_INTERVAL_SECONDS = 5
_status_monitor_task: asyncio.Task[None] | None = None


@dataclass(frozen=True)
class SandboxContainerRecord:
    container: SandboxContainer
    image_name: str
    owner_username: str


@dataclass(frozen=True)
class SandboxContainerMutationResult:
    record: SandboxContainerRecord | None
    changed: bool
    message: str = ""
    not_found: bool = False


@dataclass(frozen=True)
class SandboxContainerCommandResult:
    output: str
    exit_code: int


@dataclass(frozen=True)
class _ContainerStatusSnapshot:
    id: int
    container_hash: str
    status: SandboxContainerStatus


@dataclass(frozen=True)
class _DockerContainerState:
    exists: bool
    status: str = ""


@dataclass
class ContainerShellSession:
    client: docker.DockerClient
    socket: object
    raw_socket: object
    response: object | None
    exec_id: str
    shutdown_started: bool = False
    closed: bool = False

    def shutdown(self) -> None:
        if self.shutdown_started:
            return
        self.shutdown_started = True

        if self.raw_socket is not self.socket:
            _shutdown_shell_socket_sync(self.raw_socket)
        _shutdown_shell_socket_sync(self.socket)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True

        try:
            self.shutdown()
            _close_shell_response_sync(self.socket, self.response)
            self.response = None
            if self.raw_socket is not self.socket:
                _close_shell_socket_sync(self.raw_socket)
            _close_shell_socket_sync(self.socket)
        finally:
            self.client.close()


def _generate_container_name(image_id: int) -> str:
    return f"sandbox-{image_id}-{uuid4().hex[:12]}"


def _image_ref(image: SandboxImage) -> str:
    if image.image_hash:
        return f"sha256:{image.image_hash}"
    return image.image_name


def _serialize_port_mappings(port_mappings: list[SandboxContainerPortMapping]) -> list[dict]:
    return [mapping.model_dump() for mapping in port_mappings]


def _to_docker_ports(port_mappings: list[SandboxContainerPortMapping]) -> dict[str, int] | None:
    if not port_mappings:
        return None
    return {
        f"{mapping.container_port}/{mapping.protocol}": mapping.host_port
        for mapping in port_mappings
    }


def _create_container_sync(
    image_ref: str,
    container_name: str,
    container_command: str,
    port_mappings: list[SandboxContainerPortMapping],
) -> str:
    client = docker.from_env()
    try:
        container = client.containers.create(
            image=image_ref,
            name=container_name,
            entrypoint=["/bin/sh", "-lc"],
            command=[container_command],
            ports=_to_docker_ports(port_mappings),
            stdin_open=True,
            tty=True,
        )
        return container.id
    finally:
        client.close()


def _inspect_container_state_sync(container_hash: str) -> _DockerContainerState:
    client = docker.from_env()
    try:
        container = client.containers.get(container_hash)
        container.reload()
        return _DockerContainerState(exists=True, status=str(container.status or ""))
    except docker.errors.NotFound:
        return _DockerContainerState(exists=False)
    finally:
        client.close()


def _start_container_sync(container_hash: str) -> None:
    client = docker.from_env()
    try:
        container = client.containers.get(container_hash)
        container.start()
    finally:
        client.close()


def _stop_container_sync(container_hash: str) -> None:
    client = docker.from_env()
    try:
        container = client.containers.get(container_hash)
        container.stop()
    finally:
        client.close()


def _remove_container_sync(container_hash: str) -> None:
    client = docker.from_env()
    try:
        container = client.containers.get(container_hash)
        container.remove(force=True)
    except docker.errors.NotFound:
        logger.info("sandbox container instance already absent: %s", container_hash)
    finally:
        client.close()


def _execute_container_command_sync(container_hash: str, command: str) -> SandboxContainerCommandResult:
    client = docker.from_env()
    try:
        container = client.containers.get(container_hash)
        result = container.exec_run(
            cmd=["/bin/sh", "-lc", command],
            stdout=True,
            stderr=True,
            stdin=False,
            tty=False,
            demux=True,
        )
        stdout: bytes | str | None = None
        stderr: bytes | str | None = None
        if isinstance(result.output, tuple):
            stdout, stderr = result.output
        else:
            stdout = result.output
        exit_code = result.exit_code if isinstance(result.exit_code, int) else 1
        return SandboxContainerCommandResult(
            output=_decode_command_output(stdout) + _decode_command_output(stderr),
            exit_code=exit_code,
        )
    finally:
        client.close()


def _decode_command_output(output: bytes | str | None) -> str:
    if output is None:
        return ""
    if isinstance(output, bytes):
        return output.decode(errors="replace")
    return output


async def _load_sandbox_container_record(id: int) -> SandboxContainerRecord | None:
    statement = (
        select(SandboxContainer, SandboxImage.image_name, SystemUser.username)
        .join(SandboxImage, SandboxContainer.image_id == SandboxImage.id)
        .join(SystemUser, SandboxContainer.owner_id == SystemUser.id)
        .where(SandboxContainer.id == id)
    )

    async with get_async_session() as session:
        result = await session.exec(statement)
        row = result.first()
        if row is None:
            return None
        return SandboxContainerRecord(container=row[0], image_name=row[1], owner_username=row[2])


async def _save_sandbox_container_status(
    id: int,
    status: SandboxContainerStatus,
) -> SandboxContainerRecord | None:
    async with get_async_session() as session:
        sandbox_container = await session.get(SandboxContainer, id)
        if sandbox_container is None:
            return None

        sandbox_container.status = status
        sandbox_container.updated_at = datetime.now()
        session.add(sandbox_container)
        await session.commit()

    return await _load_sandbox_container_record(id)


def _docker_status_to_sandbox_status(status: str) -> SandboxContainerStatus:
    normalized = status.strip().lower()
    if normalized == "running":
        return SandboxContainerStatus.RUNNING
    if normalized == "created":
        return SandboxContainerStatus.CREATED
    if normalized == "exited":
        return SandboxContainerStatus.STOPPED
    return SandboxContainerStatus.ERROR


async def _load_container_status_snapshots() -> list[_ContainerStatusSnapshot]:
    statement = select(SandboxContainer.id, SandboxContainer.container_hash, SandboxContainer.status).where(
        SandboxContainer.container_hash != ""
    )
    async with get_async_session() as session:
        result = await session.exec(statement)
        return [
            _ContainerStatusSnapshot(id=row[0], container_hash=row[1], status=row[2])
            for row in result.all()
        ]


async def _sync_container_status(snapshot: _ContainerStatusSnapshot) -> None:
    state = await asyncio.to_thread(_inspect_container_state_sync, snapshot.container_hash)
    next_status = SandboxContainerStatus.ERROR if not state.exists else _docker_status_to_sandbox_status(state.status)
    if next_status == snapshot.status:
        return

    await _save_sandbox_container_status(snapshot.id, next_status)
    logger.info(
        "sandbox container status synced: %s %s -> %s",
        snapshot.id,
        snapshot.status,
        next_status,
    )


async def sync_sandbox_container_statuses() -> None:
    snapshots = await _load_container_status_snapshots()
    for snapshot in snapshots:
        try:
            await _sync_container_status(snapshot)
        except Exception:
            logger.exception("sandbox container status sync failed: %s", snapshot.id)


async def _status_monitor_loop() -> None:
    while True:
        try:
            await sync_sandbox_container_statuses()
            await asyncio.sleep(_STATUS_MONITOR_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("sandbox container status monitor iteration failed")
            await asyncio.sleep(_STATUS_MONITOR_INTERVAL_SECONDS)


async def start_sandbox_container_status_monitor() -> None:
    global _status_monitor_task
    if _status_monitor_task is not None and not _status_monitor_task.done():
        return
    _status_monitor_task = asyncio.create_task(
        _status_monitor_loop(),
        name="sandbox-container-status-monitor",
    )
    logger.info("sandbox container status monitor started")


async def stop_sandbox_container_status_monitor() -> None:
    global _status_monitor_task
    task, _status_monitor_task = _status_monitor_task, None
    if task is None or task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    logger.info("sandbox container status monitor stopped")


async def create_sandbox_container(
    image_id: int,
    owner_id: int,
    port_mappings: list[SandboxContainerPortMapping],
    container_command: str = DEFAULT_SANDBOX_CONTAINER_COMMAND,
) -> SandboxContainerMutationResult:
    async with get_async_session() as session:
        sandbox_image = await session.get(SandboxImage, image_id)
        if sandbox_image is None:
            return SandboxContainerMutationResult(
                record=None,
                changed=False,
                message="sandbox image not found",
                not_found=True,
            )
        if sandbox_image.status != SandboxImageStatus.READY:
            return SandboxContainerMutationResult(
                record=None,
                changed=False,
                message="only ready sandbox images can create containers",
            )

        owner = await session.get(SystemUser, owner_id)
        if owner is None:
            return SandboxContainerMutationResult(
                record=None,
                changed=False,
                message="system user not found",
                not_found=True,
            )

        image_ref = _image_ref(sandbox_image)

    container_name = _generate_container_name(image_id)
    try:
        container_hash = await asyncio.to_thread(
            _create_container_sync,
            image_ref,
            container_name,
            container_command,
            port_mappings,
        )
    except Exception:
        logger.exception("sandbox container create failed for image: %s", image_id)
        return SandboxContainerMutationResult(
            record=None,
            changed=False,
            message="failed to create sandbox container",
        )

    now = datetime.now()
    sandbox_container = SandboxContainer(
        container_name=container_name,
        container_hash=container_hash,
        container_command=container_command,
        owner_id=owner_id,
        image_id=image_id,
        port_mappings=_serialize_port_mappings(port_mappings),
        status=SandboxContainerStatus.CREATED,
        created_at=now,
        updated_at=now,
    )

    try:
        async with get_async_session() as session:
            session.add(sandbox_container)
            await session.commit()
            await session.refresh(sandbox_container)
    except Exception:
        await asyncio.to_thread(_remove_container_sync, container_hash)
        raise

    if sandbox_container.id is None:
        await asyncio.to_thread(_remove_container_sync, container_hash)
        raise RuntimeError("sandbox container id was not generated")

    logger.info("sandbox container created: %s", sandbox_container.id)
    return SandboxContainerMutationResult(
        record=await _load_sandbox_container_record(sandbox_container.id),
        changed=True,
        message="sandbox container created",
    )


async def start_sandbox_container(id: int) -> SandboxContainerMutationResult:
    record = await _load_sandbox_container_record(id)
    if record is None:
        return SandboxContainerMutationResult(
            record=None,
            changed=False,
            message="sandbox container not found",
            not_found=True,
        )
    if record.container.status not in {SandboxContainerStatus.CREATED, SandboxContainerStatus.STOPPED}:
        return SandboxContainerMutationResult(
            record=record,
            changed=False,
            message="only created or stopped sandbox containers can be started",
        )

    try:
        await asyncio.to_thread(_start_container_sync, record.container.container_hash)
        await asyncio.sleep(1)
        await _sync_container_status(_ContainerStatusSnapshot(
            id=record.container.id or id,
            container_hash=record.container.container_hash,
            status=record.container.status,
        ))
    except docker.errors.NotFound:
        logger.info("sandbox container instance not found while starting: %s", id)
        return SandboxContainerMutationResult(
            record=await _save_sandbox_container_status(id, SandboxContainerStatus.ERROR),
            changed=False,
            message="sandbox container instance not found",
        )
    except Exception:
        logger.exception("sandbox container start failed: %s", id)
        return SandboxContainerMutationResult(
            record=await _save_sandbox_container_status(id, SandboxContainerStatus.ERROR),
            changed=False,
            message="failed to start sandbox container",
        )

    next_record = await _load_sandbox_container_record(id)
    if next_record is not None and next_record.container.status == SandboxContainerStatus.RUNNING:
        logger.info("sandbox container started: %s", id)
        return SandboxContainerMutationResult(
            record=next_record,
            changed=True,
            message="sandbox container started",
        )

    logger.info("sandbox container exited after start: %s", id)
    return SandboxContainerMutationResult(
        record=next_record,
        changed=False,
        message="sandbox container is not running after start",
    )


async def stop_sandbox_container(id: int) -> SandboxContainerMutationResult:
    record = await _load_sandbox_container_record(id)
    if record is None:
        return SandboxContainerMutationResult(
            record=None,
            changed=False,
            message="sandbox container not found",
            not_found=True,
        )
    if record.container.status != SandboxContainerStatus.RUNNING:
        return SandboxContainerMutationResult(
            record=record,
            changed=False,
            message="only running sandbox containers can be stopped",
        )

    try:
        await asyncio.to_thread(_stop_container_sync, record.container.container_hash)
    except docker.errors.NotFound:
        logger.info("sandbox container instance not found while stopping: %s", id)
        return SandboxContainerMutationResult(
            record=await _save_sandbox_container_status(id, SandboxContainerStatus.ERROR),
            changed=False,
            message="sandbox container instance not found",
        )
    except Exception:
        logger.exception("sandbox container stop failed: %s", id)
        return SandboxContainerMutationResult(
            record=await _save_sandbox_container_status(id, SandboxContainerStatus.ERROR),
            changed=False,
            message="failed to stop sandbox container",
        )

    logger.info("sandbox container stopped: %s", id)
    return SandboxContainerMutationResult(
        record=await _save_sandbox_container_status(id, SandboxContainerStatus.STOPPED),
        changed=True,
        message="sandbox container stopped",
    )


async def delete_sandbox_container(id: int) -> bool:
    async with get_async_session() as session:
        sandbox_container = await session.get(SandboxContainer, id)
        if sandbox_container is None:
            return False

        await asyncio.to_thread(_remove_container_sync, sandbox_container.container_hash)
        await session.delete(sandbox_container)
        await session.commit()

    logger.info("sandbox container deleted: %s", id)
    return True


async def query_sandbox_containers(
    page: int = 1,
    size: int = 100,
    keyword: str = "",
) -> list[SandboxContainerRecord]:
    statement = (
        select(SandboxContainer, SandboxImage.image_name, SystemUser.username)
        .join(SandboxImage, SandboxContainer.image_id == SandboxImage.id)
        .join(SystemUser, SandboxContainer.owner_id == SystemUser.id)
        .order_by(SandboxContainer.id)
        .offset((page - 1) * size)
        .limit(size)
    )

    keyword = keyword.strip()
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(
                SandboxContainer.container_name.ilike(pattern),
                SandboxContainer.container_hash.ilike(pattern),
                SandboxImage.image_name.ilike(pattern),
                SystemUser.username.ilike(pattern),
                cast(SandboxContainer.status, String).ilike(pattern),
                cast(SandboxContainer.port_mappings, String).ilike(pattern),
            )
        )

    async with get_async_session() as session:
        result = await session.exec(statement)
        return [
            SandboxContainerRecord(container=row[0], image_name=row[1], owner_username=row[2])
            for row in result.all()
        ]


async def query_available_sandbox_containers(
    user_id: int,
    user_role: SystemUserRole,
    page: int = 1,
    size: int = 100,
    keyword: str = "",
) -> list[SandboxContainerRecord]:
    statement = (
        select(SandboxContainer, SandboxImage.image_name, SystemUser.username)
        .join(SandboxImage, SandboxContainer.image_id == SandboxImage.id)
        .join(SystemUser, SandboxContainer.owner_id == SystemUser.id)
        .order_by(SandboxContainer.id)
        .offset((page - 1) * size)
        .limit(size)
    )

    if user_role != SystemUserRole.ADMIN:
        statement = statement.where(SandboxContainer.owner_id == user_id)
    statement = statement.where(SandboxContainer.status == SandboxContainerStatus.RUNNING)

    keyword = keyword.strip()
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(
                SandboxContainer.container_name.ilike(pattern),
                SandboxContainer.container_hash.ilike(pattern),
                SandboxImage.image_name.ilike(pattern),
                SystemUser.username.ilike(pattern),
                cast(SandboxContainer.status, String).ilike(pattern),
                cast(SandboxContainer.port_mappings, String).ilike(pattern),
            )
        )

    async with get_async_session() as session:
        result = await session.exec(statement)
        return [
            SandboxContainerRecord(container=row[0], image_name=row[1], owner_username=row[2])
            for row in result.all()
        ]


async def can_use_sandbox_container(
    id: int,
    user_id: int,
    user_role: SystemUserRole,
) -> bool:
    async with get_async_session() as session:
        sandbox_container = await session.get(SandboxContainer, id)
        if sandbox_container is None:
            return False
        return (
            sandbox_container.status == SandboxContainerStatus.RUNNING
            and (user_role == SystemUserRole.ADMIN or sandbox_container.owner_id == user_id)
        )


async def resolve_shell_container(container_hash: str) -> SandboxContainer | None:
    async with get_async_session() as session:
        result = await session.exec(
            select(SandboxContainer).where(SandboxContainer.container_hash == container_hash)
        )
        sandbox_container = result.first()
        if sandbox_container is None or sandbox_container.status != SandboxContainerStatus.RUNNING:
            return None

    state = await asyncio.to_thread(_inspect_container_state_sync, container_hash)
    status = SandboxContainerStatus.ERROR if not state.exists else _docker_status_to_sandbox_status(state.status)
    if status != SandboxContainerStatus.RUNNING:
        if sandbox_container.id is not None:
            await _save_sandbox_container_status(sandbox_container.id, status)
        return None

    return sandbox_container


async def open_container_shell(
    container_hash: str,
    rows: int = _DEFAULT_SHELL_ROWS,
    cols: int = _DEFAULT_SHELL_COLS,
) -> ContainerShellSession:
    return await asyncio.to_thread(_open_container_shell_sync, container_hash, rows, cols)


async def resize_container_shell(session: ContainerShellSession, rows: int, cols: int) -> None:
    rows = max(1, min(rows, 300))
    cols = max(1, min(cols, 500))
    await asyncio.to_thread(session.client.api.exec_resize, session.exec_id, height=rows, width=cols)


async def read_container_shell(session: ContainerShellSession) -> bytes:
    return await asyncio.to_thread(_read_shell_sync, session.raw_socket)


async def write_container_shell(session: ContainerShellSession, data: str) -> None:
    if not data:
        return
    await asyncio.to_thread(_write_shell_sync, session.raw_socket, data.encode())


def _open_container_shell_sync(container_hash: str, rows: int, cols: int) -> ContainerShellSession:
    client = docker.from_env()
    try:
        container = client.containers.get(container_hash)
        exec_id = _create_shell_exec(client, container.id)
        socket, response = _start_shell_exec_socket(client, exec_id)
        raw_socket = getattr(socket, "_sock", socket)
        try:
            client.api.exec_resize(exec_id, height=rows, width=cols)
        except Exception:
            logger.debug("failed to resize shell exec during open", exc_info=True)
        return ContainerShellSession(
            client=client,
            socket=socket,
            raw_socket=raw_socket,
            response=response,
            exec_id=exec_id,
        )
    except Exception:
        client.close()
        raise


def _start_shell_exec_socket(client: docker.DockerClient, exec_id: str) -> tuple[object, object | None]:
    api = client.api
    post_json = getattr(api, "_post_json", None)
    url = getattr(api, "_url", None)
    get_raw_response_socket = getattr(api, "_get_raw_response_socket", None)

    if callable(post_json) and callable(url) and callable(get_raw_response_socket):
        response = post_json(
            url(f"/exec/{exec_id}/start"),
            headers={"Connection": "Upgrade", "Upgrade": "tcp"},
            data={"Tty": True, "Detach": False},
            stream=True,
        )
        try:
            return get_raw_response_socket(response), response
        except Exception:
            _close_shell_response_sync(response, response)
            raise

    socket = api.exec_start(exec_id, tty=True, socket=True)
    return socket, getattr(socket, "_response", None)


def _create_shell_exec(client: docker.DockerClient, container_id: str) -> str:
    last_error: Exception | None = None
    for command in _SHELL_CANDIDATES:
        try:
            response = client.api.exec_create(
                container=container_id,
                cmd=list(command),
                stdin=True,
                stdout=True,
                stderr=True,
                tty=True,
                environment={"TERM": "xterm-256color"},
            )
            return str(response["Id"])
        except Exception as exc:
            last_error = exc
    raise RuntimeError("no supported shell found in container") from last_error


def _write_shell_sync(socket: object, data: bytes) -> None:
    if hasattr(socket, "sendall"):
        socket.sendall(data)
        return
    if hasattr(socket, "send"):
        socket.send(data)
        return
    if hasattr(socket, "write"):
        socket.write(data)
        flush = getattr(socket, "flush", None)
        if callable(flush):
            flush()
        return
    raise RuntimeError("docker exec socket is not writable")


def _read_shell_sync(socket: object) -> bytes:
    try:
        data = docker_socket.read(socket)
    except (OSError, ValueError):
        return b""
    if isinstance(data, str):
        return data.encode()
    return data or b""


def _shutdown_shell_socket_sync(socket: object) -> None:
    shutdown = getattr(socket, "shutdown", None)
    if callable(shutdown):
        try:
            shutdown(py_socket.SHUT_RDWR)
        except Exception:
            pass


def _close_shell_response_sync(socket: object, response: object | None) -> None:
    if response is None:
        response = getattr(socket, "_response", None)

    close = getattr(response, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass

    if response is not None:
        try:
            if getattr(socket, "_response", None) is response:
                setattr(socket, "_response", None)
        except Exception:
            pass


def _close_shell_socket_sync(socket: object) -> None:
    _shutdown_shell_socket_sync(socket)

    close = getattr(socket, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


async def execute_sandbox_container_command(id: int, command: str) -> SandboxContainerCommandResult:
    command = command.strip()
    if not command:
        raise ValueError("sandbox container command is required")

    async with get_async_session() as session:
        sandbox_container = await session.get(SandboxContainer, id)
        if sandbox_container is None:
            raise ValueError("sandbox container not found")
        if sandbox_container.status != SandboxContainerStatus.RUNNING:
            raise ValueError("only running sandbox containers can execute commands")

        container_hash = sandbox_container.container_hash

    try:
        state = await asyncio.to_thread(_inspect_container_state_sync, container_hash)
    except Exception:
        logger.exception("sandbox container inspect failed before command execution: %s", id)
        raise RuntimeError("failed to inspect sandbox container")

    status = SandboxContainerStatus.ERROR if not state.exists else _docker_status_to_sandbox_status(state.status)
    if status != SandboxContainerStatus.RUNNING:
        await _save_sandbox_container_status(id, status)
        raise RuntimeError("sandbox container is not running")

    try:
        return await asyncio.to_thread(_execute_container_command_sync, container_hash, command)
    except docker.errors.NotFound:
        logger.info("sandbox container instance not found while executing command: %s", id)
        await _save_sandbox_container_status(id, SandboxContainerStatus.ERROR)
        raise RuntimeError("sandbox container instance not found")
    except Exception:
        logger.exception("sandbox container command execution failed: %s", id)
        raise RuntimeError("failed to execute sandbox container command")
