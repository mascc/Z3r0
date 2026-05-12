from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from sqlmodel import select

from database import get_async_session
from logger import get_logger
from model.agent_async_job_model import SandboxAsyncJob
from schema.agent_async_job_schema import SandboxAsyncJobSnapshot, SandboxAsyncJobStatus


logger = get_logger(__name__)

_job_waiters: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
_job_waiters_lock = asyncio.Lock()

TERMINAL_ASYNC_JOB_STATUSES = {
    SandboxAsyncJobStatus.COMPLETED,
    SandboxAsyncJobStatus.FAILED,
    SandboxAsyncJobStatus.CANCELED,
}


async def create_async_job(
    *,
    run_id: str,
    session_id: str,
    agent_code: str,
    agent_instance_id: str,
    command: str,
    output_file: str,
    nested_for_agent_code: str,
    nested_call_id: str,
    sandbox_container_id: int | None,
    sandbox_container_generation: int,
    sandbox_skill_metadata: tuple[str, ...],
) -> SandboxAsyncJobSnapshot:
    now = datetime.now()
    job = SandboxAsyncJob(
        run_id=run_id,
        session_id=session_id,
        agent_code=agent_code,
        agent_instance_id=agent_instance_id,
        command=command,
        output_file=output_file,
        status=SandboxAsyncJobStatus.RUNNING.value,
        nested_for_agent_code=nested_for_agent_code,
        nested_call_id=nested_call_id,
        sandbox_container_id=sandbox_container_id,
        sandbox_container_generation=sandbox_container_generation,
        sandbox_skill_metadata=list(sandbox_skill_metadata),
        created_at=now,
        updated_at=now,
        started_at=now,
    )
    async with get_async_session() as session:
        session.add(job)
        await session.commit()
        await session.refresh(job)
    logger.info("sandbox async job created: %s", job.run_id)
    return snapshot_from_job(job)


async def get_async_job(run_id: str, *, session_id: str) -> SandboxAsyncJobSnapshot | None:
    async with get_async_session() as session:
        job = await session.get(SandboxAsyncJob, run_id)
        if job is None or job.session_id != session_id:
            return None
        return snapshot_from_job(job)


async def wait_async_job_terminal(run_id: str, *, session_id: str) -> SandboxAsyncJobSnapshot | None:
    snapshot = await get_async_job(run_id, session_id=session_id)
    if snapshot is None or snapshot.status in TERMINAL_ASYNC_JOB_STATUSES:
        return snapshot

    waiter = await _get_job_waiter(run_id)
    snapshot = await get_async_job(run_id, session_id=session_id)
    if snapshot is None or snapshot.status in TERMINAL_ASYNC_JOB_STATUSES:
        await _forget_job_waiter(run_id, waiter)
        return snapshot

    await waiter.wait()
    return await get_async_job(run_id, session_id=session_id)


async def complete_async_job(
    run_id: str,
    *,
    exit_code: int,
    output_bytes: int,
    output_lines: int,
) -> SandboxAsyncJobSnapshot | None:
    return await _finish_async_job(
        run_id,
        SandboxAsyncJobStatus.COMPLETED,
        exit_code=exit_code,
        output_bytes=output_bytes,
        output_lines=output_lines,
    )


async def fail_async_job(run_id: str, error: str) -> SandboxAsyncJobSnapshot | None:
    return await _finish_async_job(run_id, SandboxAsyncJobStatus.FAILED, error=error)


async def cancel_async_job(run_id: str, error: str = "") -> SandboxAsyncJobSnapshot | None:
    return await _finish_async_job(run_id, SandboxAsyncJobStatus.CANCELED, error=error)


async def cancel_running_async_jobs_for_session(session_id: str, error: str = "") -> list[SandboxAsyncJobSnapshot]:
    return await _cancel_running_async_jobs(session_id=session_id, error=error)


async def cancel_running_async_jobs_for_agent(
    *,
    session_id: str,
    agent_instance_id: str,
    error: str = "",
) -> list[SandboxAsyncJobSnapshot]:
    return await _cancel_running_async_jobs(
        session_id=session_id,
        agent_instance_id=agent_instance_id,
        error=error,
    )


async def cancel_running_async_jobs_for_container(container_id: int, error: str = "") -> list[SandboxAsyncJobSnapshot]:
    return await _cancel_running_async_jobs(sandbox_container_id=container_id, error=error)


async def cancel_running_async_jobs(error: str = "") -> list[SandboxAsyncJobSnapshot]:
    return await _cancel_running_async_jobs(error=error)


async def mark_stale_running_async_jobs_failed() -> list[SandboxAsyncJobSnapshot]:
    now = datetime.now()
    async with get_async_session() as session:
        rows = (await session.exec(
            select(SandboxAsyncJob).where(SandboxAsyncJob.status == SandboxAsyncJobStatus.RUNNING.value)
        )).all()
        for job in rows:
            job.status = SandboxAsyncJobStatus.FAILED.value
            job.error = "Sandbox async job was interrupted by backend restart."
            job.updated_at = now
            job.finished_at = now
            session.add(job)
        if rows:
            await session.commit()
            for job in rows:
                await session.refresh(job)
            logger.info("stale sandbox async jobs marked failed: %d", len(rows))
        snapshots = [snapshot_from_job(job) for job in rows]
    for snapshot in snapshots:
        await _notify_job_finished(snapshot.run_id)
    return snapshots


def snapshot_from_job(job: SandboxAsyncJob) -> SandboxAsyncJobSnapshot:
    return SandboxAsyncJobSnapshot(
        run_id=job.run_id,
        session_id=job.session_id,
        agent_code=job.agent_code,
        agent_instance_id=job.agent_instance_id,
        command=job.command,
        output_file=job.output_file,
        status=_coerce_status(job.status),
        exit_code=job.exit_code,
        output_bytes=job.output_bytes,
        output_lines=job.output_lines,
        error=job.error,
        nested_for_agent_code=job.nested_for_agent_code,
        nested_call_id=job.nested_call_id,
        sandbox_container_id=job.sandbox_container_id,
        sandbox_container_generation=job.sandbox_container_generation,
        sandbox_skill_metadata=_coerce_string_tuple(job.sandbox_skill_metadata),
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


async def _finish_async_job(
    run_id: str,
    status: SandboxAsyncJobStatus,
    *,
    exit_code: int | None = None,
    output_bytes: int = 0,
    output_lines: int = 0,
    error: str = "",
) -> SandboxAsyncJobSnapshot | None:
    now = datetime.now()
    async with get_async_session() as session:
        job = await session.get(SandboxAsyncJob, run_id)
        if job is None:
            return None
        if _coerce_status(job.status) in TERMINAL_ASYNC_JOB_STATUSES:
            return snapshot_from_job(job)
        job.status = status.value
        job.exit_code = exit_code
        job.output_bytes = output_bytes
        job.output_lines = output_lines
        job.error = error
        job.updated_at = now
        job.finished_at = now
        session.add(job)
        await session.commit()
        await session.refresh(job)
        snapshot = snapshot_from_job(job)
    await _notify_job_finished(run_id)
    return snapshot


async def _cancel_running_async_jobs(
    *,
    session_id: str | None = None,
    agent_instance_id: str | None = None,
    sandbox_container_id: int | None = None,
    error: str = "",
) -> list[SandboxAsyncJobSnapshot]:
    now = datetime.now()
    async with get_async_session() as session:
        statement = select(SandboxAsyncJob).where(SandboxAsyncJob.status == SandboxAsyncJobStatus.RUNNING.value)
        if session_id is not None:
            statement = statement.where(SandboxAsyncJob.session_id == session_id)
        if agent_instance_id is not None:
            statement = statement.where(SandboxAsyncJob.agent_instance_id == agent_instance_id)
        if sandbox_container_id is not None:
            statement = statement.where(SandboxAsyncJob.sandbox_container_id == sandbox_container_id)
        rows = (await session.exec(statement)).all()
        for job in rows:
            job.status = SandboxAsyncJobStatus.CANCELED.value
            job.error = error
            job.updated_at = now
            job.finished_at = now
            session.add(job)
        if not rows:
            return []
        await session.commit()
        for job in rows:
            await session.refresh(job)
        snapshots = [snapshot_from_job(job) for job in rows]
    for snapshot in snapshots:
        await _notify_job_finished(snapshot.run_id)
    return snapshots


async def _get_job_waiter(run_id: str) -> asyncio.Event:
    async with _job_waiters_lock:
        return _job_waiters[run_id]


async def _forget_job_waiter(run_id: str, waiter: asyncio.Event) -> None:
    async with _job_waiters_lock:
        if _job_waiters.get(run_id) is waiter:
            _job_waiters.pop(run_id, None)


async def _notify_job_finished(run_id: str) -> None:
    async with _job_waiters_lock:
        waiter = _job_waiters.pop(run_id, None)
    if waiter is not None:
        waiter.set()


def _coerce_status(status: SandboxAsyncJobStatus | str) -> SandboxAsyncJobStatus:
    if isinstance(status, SandboxAsyncJobStatus):
        return status
    return SandboxAsyncJobStatus(str(status).lower())


def _coerce_string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(item for item in value if isinstance(item, str))
