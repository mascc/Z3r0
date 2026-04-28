import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import docker
from docker.utils import parse_repository_tag
from sqlalchemy import String, cast, or_
from sqlmodel import select

from database import get_async_session
from logger import get_logger
from model.sandbox_image_model import SandboxImage, SandboxImageStatus


logger = get_logger(__name__)


@dataclass
class PullJob:
    task: asyncio.Task[None]
    cancel_event: asyncio.Event
    client: docker.DockerClient | None = None


_pull_jobs: dict[int, PullJob] = {}


def _hash_value(value: str) -> str:
    digest = value.rsplit("@", 1)[-1]
    return digest.rsplit(":", 1)[-1]


def _docker_image_id(image_hash: str) -> str:
    return image_hash if image_hash.startswith("sha256:") else f"sha256:{image_hash}"


def _image_hash(attrs: dict[str, Any]) -> str:
    image_id = attrs.get("Id")
    return _hash_value(image_id) if isinstance(image_id, str) else ""


def _image_size(client: docker.DockerClient, image_id: str, attrs: dict[str, Any]) -> int:
    for image in client.images.list():
        if image.id == image_id:
            return _positive_size(image.attrs.get("Size"))

    return _positive_size(attrs.get("Size"))


def _positive_size(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _cancel_pull_job(job: PullJob) -> None:
    job.cancel_event.set()
    job.task.cancel()
    if job.client is not None:
        job.client.close()


async def _save_pull_result(
    id: int,
    image_name: str,
    status: SandboxImageStatus,
    image_hash: str = "",
    image_size: int = 0,
) -> None:
    async with get_async_session() as session:
        sandbox_image = await session.get(SandboxImage, id)
        if sandbox_image is None or sandbox_image.image_name != image_name:
            logger.info("sandbox image pull result ignored: %s", id)
            return

        sandbox_image.status = status
        sandbox_image.image_hash = image_hash
        sandbox_image.image_size = image_size
        sandbox_image.updated_at = datetime.now()
        session.add(sandbox_image)
        await session.commit()


def _pull_image_sync(id: int, image_name: str) -> tuple[str, int]:
    job = _pull_jobs[id]
    client = docker.from_env()
    job.client = client
    try:
        repository, tag = parse_repository_tag(image_name)
        image_id: str | None = None

        for event in client.api.pull(repository, tag=tag, stream=True, decode=True):
            if job.cancel_event.is_set():
                raise asyncio.CancelledError
            if not isinstance(event, dict):
                continue
            if event.get("error"):
                raise RuntimeError(str(event["error"]))
            aux = event.get("aux")
            if isinstance(aux, dict) and isinstance(aux.get("ID"), str):
                image_id = aux["ID"]

        if image_id is None:
            raise docker.errors.ImageNotFound(image_name)

        attrs = client.api.inspect_image(image_id)
        return _image_hash(attrs), _image_size(client, image_id, attrs)
    finally:
        job.client = None
        client.close()


def _remove_image_sync(image_hash: str) -> None:
    client = docker.from_env()
    try:
        client.images.remove(image=_docker_image_id(image_hash), force=True, noprune=False)
    except docker.errors.ImageNotFound:
        logger.info("sandbox image file already absent: %s", image_hash)
    finally:
        client.close()


async def _pull_image(id: int, image_name: str) -> tuple[str, int]:
    return await asyncio.to_thread(_pull_image_sync, id, image_name)


async def _remove_image(image_hash: str) -> None:
    if image_hash:
        await asyncio.to_thread(_remove_image_sync, image_hash)


async def _pull_and_update_sandbox_image(id: int, image_name: str) -> None:
    try:
        image_hash, image_size = await _pull_image(id, image_name)
        await _save_pull_result(id, image_name, SandboxImageStatus.READY, image_hash, image_size)
        logger.info("sandbox image pulled: %s", id)
    except asyncio.CancelledError:
        await _save_pull_result(id, image_name, SandboxImageStatus.CANCELED)
        logger.info("sandbox image pull canceled: %s", id)
    except Exception:
        logger.exception("sandbox image pull failed: %s", id)
        await _save_pull_result(id, image_name, SandboxImageStatus.FAILED)
    finally:
        current = _pull_jobs.get(id)
        if current is not None and current.task is asyncio.current_task():
            _pull_jobs.pop(id, None)


def _schedule_pull(id: int, image_name: str) -> None:
    current = _pull_jobs.pop(id, None)
    if current is not None:
        _cancel_pull_job(current)

    cancel_event = asyncio.Event()
    task = asyncio.create_task(_pull_and_update_sandbox_image(id, image_name))
    _pull_jobs[id] = PullJob(task=task, cancel_event=cancel_event)


async def create_sandbox_image(image_name: str) -> SandboxImage:
    """create sandbox image and start docker pull in background"""
    now = datetime.now()
    sandbox_image = SandboxImage(
        image_name=image_name,
        image_size=0,
        image_hash="",
        status=SandboxImageStatus.PULLING,
        created_at=now,
        updated_at=now,
    )

    async with get_async_session() as session:
        session.add(sandbox_image)
        await session.commit()
        await session.refresh(sandbox_image)

    if sandbox_image.id is None:
        raise RuntimeError("sandbox image id was not generated")

    _schedule_pull(sandbox_image.id, image_name)
    logger.info("sandbox image created: %s", sandbox_image.id)
    return sandbox_image


async def cancel_sandbox_image_pull(id: int) -> tuple[SandboxImage | None, bool]:
    """cancel an active sandbox image pull"""
    async with get_async_session() as session:
        sandbox_image = await session.get(SandboxImage, id)
        if sandbox_image is None:
            return None, False
        if sandbox_image.status != SandboxImageStatus.PULLING:
            return sandbox_image, False

        sandbox_image.status = SandboxImageStatus.CANCELED
        sandbox_image.updated_at = datetime.now()
        session.add(sandbox_image)
        await session.commit()
        await session.refresh(sandbox_image)

    job = _pull_jobs.get(id)
    if job is not None:
        _cancel_pull_job(job)

    logger.info("sandbox image pull cancel requested: %s", id)
    return sandbox_image, True


async def delete_sandbox_image(id: int) -> bool:
    """delete sandbox image"""
    job = _pull_jobs.pop(id, None)
    if job is not None:
        _cancel_pull_job(job)

    async with get_async_session() as session:
        sandbox_image = await session.get(SandboxImage, id)
        if sandbox_image is None:
            return False

        image_hash = sandbox_image.image_hash
        await _remove_image(image_hash)
        await session.delete(sandbox_image)
        await session.commit()

    logger.info("sandbox image deleted: %s", id)
    return True


async def retry_sandbox_image(id: int) -> tuple[SandboxImage | None, bool]:
    """retry a failed or canceled sandbox image pull"""
    async with get_async_session() as session:
        sandbox_image = await session.get(SandboxImage, id)
        if sandbox_image is None:
            return None, False
        if sandbox_image.status not in {SandboxImageStatus.FAILED, SandboxImageStatus.CANCELED}:
            return sandbox_image, False

        sandbox_image.image_size = 0
        sandbox_image.image_hash = ""
        sandbox_image.status = SandboxImageStatus.PULLING
        sandbox_image.updated_at = datetime.now()
        session.add(sandbox_image)
        await session.commit()
        await session.refresh(sandbox_image)

    _schedule_pull(id, sandbox_image.image_name)
    logger.info("sandbox image pull retried: %s", sandbox_image.id)
    return sandbox_image, True


async def query_sandbox_images(page: int = 1, size: int = 100, keyword: str = "") -> list[SandboxImage]:
    """query sandbox images"""
    statement = select(SandboxImage).order_by(SandboxImage.id).offset((page - 1) * size).limit(size)

    keyword = keyword.strip()
    if keyword:
        pattern = f"%{keyword}%"
        statement = statement.where(
            or_(
                SandboxImage.image_name.ilike(pattern),
                SandboxImage.image_hash.ilike(pattern),
                cast(SandboxImage.status, String).ilike(pattern),
            )
        )

    async with get_async_session() as session:
        result = await session.exec(statement)
        return list(result.all())
