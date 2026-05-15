import asyncio
import threading
from dataclasses import dataclass
from datetime import datetime

import docker
from docker.utils import parse_repository_tag
from sqlalchemy import String, cast, or_
from sqlmodel import select

from database import get_async_session
from logger import get_logger
from model.sandbox.containers import SandboxContainer
from model.sandbox.images import SandboxImage
from schema.sandbox.images import SandboxImageStatus


logger = get_logger(__name__)


@dataclass
class PullJob:
    cancel_event: threading.Event
    task: asyncio.Task[None] | None = None
    client: docker.DockerClient | None = None


_pull_jobs: dict[int, PullJob] = {}
_pull_jobs_lock = asyncio.Lock()


@dataclass(frozen=True)
class DeleteSandboxImageResult:
    deleted: bool
    not_found: bool = False
    message: str = ""


def _cancel_pull_job(job: PullJob) -> None:
    """flip the cancel flag, cancel the task, and tear down the docker socket
    so a blocked pull stream unblocks immediately"""
    job.cancel_event.set()
    if job.task is not None:
        job.task.cancel()
    if job.client is not None:
        job.client.close()


async def _save_pull_result(
    id: int,
    status: SandboxImageStatus,
    image_hash: str = "",
    image_size: int = 0,
) -> None:
    async with get_async_session() as session:
        sandbox_image = await session.get(SandboxImage, id)
        if sandbox_image is None:
            logger.debug("sandbox image pull result ignored: %s", id)
            return

        sandbox_image.status = status
        sandbox_image.image_hash = image_hash
        sandbox_image.image_size = image_size
        sandbox_image.updated_at = datetime.now()
        session.add(sandbox_image)
        await session.commit()


def _pull_image_sync(job: PullJob, image_name: str) -> tuple[str, int]:
    if job.cancel_event.is_set():
        raise asyncio.CancelledError
    client = docker.from_env()
    job.client = client
    try:
        try:
            attrs = client.api.inspect_image(image_name)
            logger.debug("sandbox image found locally: %s", image_name)
            return _image_metadata(attrs)
        except docker.errors.ImageNotFound:
            pass

        repository, tag = parse_repository_tag(image_name)
        for event in client.api.pull(repository, tag=tag, stream=True, decode=True):
            if job.cancel_event.is_set():
                raise asyncio.CancelledError
            if isinstance(event, dict) and event.get("error"):
                raise RuntimeError(str(event["error"]))

        attrs = client.api.inspect_image(image_name)
        return _image_metadata(attrs)
    finally:
        job.client = None
        client.close()


def _image_metadata(attrs: dict) -> tuple[str, int]:
    image_id: str = attrs["Id"]
    image_size = attrs.get("Size", 0)
    return image_id.removeprefix("sha256:"), max(int(image_size), 0)


def _remove_image_sync(image_hash: str) -> None:
    client = docker.from_env()
    try:
        client.images.remove(image=f"sha256:{image_hash}", force=True, noprune=False)
    except docker.errors.ImageNotFound:
        logger.debug("sandbox image file already absent: %s", image_hash)
    finally:
        client.close()


async def _pull_and_update_sandbox_image(id: int, image_name: str, job: PullJob) -> None:
    try:
        image_hash, image_size = await asyncio.to_thread(_pull_image_sync, job, image_name)
        await _save_pull_result(id, SandboxImageStatus.READY, image_hash, image_size)
        logger.info("sandbox image pulled: %s", id)
    except asyncio.CancelledError:
        await _save_pull_result(id, SandboxImageStatus.CANCELED)
        logger.info("sandbox image pull canceled: %s", id)
    except Exception:
        logger.exception("sandbox image pull failed: %s", id)
        await _save_pull_result(id, SandboxImageStatus.FAILED)
    finally:
        async with _pull_jobs_lock:
            current = _pull_jobs.get(id)
            if current is not None and current.task is asyncio.current_task():
                _pull_jobs.pop(id, None)


async def _schedule_pull(id: int, image_name: str) -> None:
    job = PullJob(cancel_event=threading.Event())
    async with _pull_jobs_lock:
        current = _pull_jobs.pop(id, None)
        _pull_jobs[id] = job
    if current is not None:
        _cancel_pull_job(current)

    async with _pull_jobs_lock:
        if _pull_jobs.get(id) is not job:
            _cancel_pull_job(job)
            return
        task = asyncio.create_task(_pull_and_update_sandbox_image(id, image_name, job))
        job.task = task
        if _pull_jobs.get(id) is not job:
            _cancel_pull_job(job)


async def start_sandbox_image_runtime() -> None:
    await _mark_stale_pulling_images_failed()


async def stop_sandbox_image_runtime() -> None:
    async with _pull_jobs_lock:
        jobs = list(_pull_jobs.values())
        _pull_jobs.clear()
    for job in jobs:
        _cancel_pull_job(job)
    tasks = [job.task for job in jobs if job.task is not None]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _mark_stale_pulling_images_failed() -> None:
    async with get_async_session() as session:
        rows = (await session.exec(
            select(SandboxImage).where(SandboxImage.status == SandboxImageStatus.PULLING)
        )).all()
        for sandbox_image in rows:
            sandbox_image.status = SandboxImageStatus.FAILED
            sandbox_image.updated_at = datetime.now()
            session.add(sandbox_image)
        if rows:
            await session.commit()
            logger.info("stale sandbox image pulls marked failed: %d", len(rows))


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

    await _schedule_pull(sandbox_image.id, image_name)
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

    async with _pull_jobs_lock:
        job = _pull_jobs.get(id)
    if job is not None:
        _cancel_pull_job(job)

    logger.debug("sandbox image pull cancel requested: %s", id)
    return sandbox_image, True


async def delete_sandbox_image(id: int) -> DeleteSandboxImageResult:
    """delete sandbox image"""
    async with _pull_jobs_lock:
        job = _pull_jobs.pop(id, None)
    if job is not None:
        _cancel_pull_job(job)

    async with get_async_session() as session:
        sandbox_image = await session.get(SandboxImage, id)
        if sandbox_image is None:
            return DeleteSandboxImageResult(deleted=False, not_found=True, message="sandbox image not found")

        result = await session.exec(select(SandboxContainer.id).where(SandboxContainer.image_id == id).limit(1))
        if result.first() is not None:
            return DeleteSandboxImageResult(
                deleted=False,
                message="sandbox image is used by sandbox containers",
            )

        if sandbox_image.image_hash:
            await asyncio.to_thread(_remove_image_sync, sandbox_image.image_hash)
        await session.delete(sandbox_image)
        await session.commit()

    logger.info("sandbox image deleted: %s", id)
    return DeleteSandboxImageResult(deleted=True)


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

    await _schedule_pull(id, sandbox_image.image_name)
    logger.debug("sandbox image pull retried: %s", sandbox_image.id)
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
