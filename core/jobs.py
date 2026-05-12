"""Background sandbox command execution."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from core.context import AgentRuntimeContext
from logger import get_logger
from service import sandbox_async_job_service
from service.sandbox_container_service import execute_sandbox_container_command


logger = get_logger(__name__)


@dataclass
class _AsyncCommandJob:
    task: asyncio.Task[None]
    session_id: str
    agent_instance_id: str
    sandbox_container_id: int | None


_jobs: dict[str, _AsyncCommandJob] = {}
_AsyncCommandJobPredicate = Callable[[str, _AsyncCommandJob], bool]


async def start_async_sandbox_runtime() -> None:
    await sandbox_async_job_service.mark_stale_running_async_jobs_failed()


def start_async_sandbox_command(
    *,
    run_id: str,
    context: AgentRuntimeContext,
    wrapped_command: str,
    stat_command: str,
) -> None:
    task = asyncio.create_task(
        _run_async_sandbox_command(
            run_id=run_id,
            context=context,
            wrapped_command=wrapped_command,
            stat_command=stat_command,
        ),
        name=f"sandbox-async-command-{run_id}",
    )
    _jobs[run_id] = _AsyncCommandJob(
        task=task,
        session_id=context.session_id,
        agent_instance_id=context.agent_instance_id,
        sandbox_container_id=context.sandbox_container_id,
    )
    task.add_done_callback(lambda completed: _finish_async_sandbox_command(run_id, completed))


async def cancel_agent_async_sandbox_commands(
    *,
    session_id: str,
    agent_instance_id: str,
) -> bool:
    runtime_canceled = await _cancel_runtime_jobs(
        lambda _, job: job.session_id == session_id and job.agent_instance_id == agent_instance_id
    )
    snapshots = await sandbox_async_job_service.cancel_running_async_jobs_for_agent(
        session_id=session_id,
        agent_instance_id=agent_instance_id,
        error="Sandbox async job canceled.",
    )
    return runtime_canceled or bool(snapshots)


async def cancel_async_sandbox_command(run_id: str) -> bool:
    runtime_canceled = await _cancel_runtime_jobs(lambda candidate, _: candidate == run_id)
    snapshot = await sandbox_async_job_service.cancel_async_job(run_id, "Sandbox async job cancel requested.")
    return runtime_canceled or snapshot is not None


async def cancel_sandbox_async_commands(container_id: int) -> bool:
    runtime_canceled = await _cancel_runtime_jobs(lambda _, job: job.sandbox_container_id == container_id)
    snapshots = await sandbox_async_job_service.cancel_running_async_jobs_for_container(
        container_id,
        "Sandbox async job canceled.",
    )
    return runtime_canceled or bool(snapshots)


async def cancel_session_async_sandbox_commands(session_id: str) -> bool:
    runtime_canceled = await _cancel_runtime_jobs(lambda _, job: job.session_id == session_id)
    snapshots = await sandbox_async_job_service.cancel_running_async_jobs_for_session(
        session_id,
        "Sandbox async job canceled.",
    )
    return runtime_canceled or bool(snapshots)


async def stop_async_sandbox_commands() -> None:
    await _cancel_runtime_jobs(lambda _, __: True)
    await sandbox_async_job_service.cancel_running_async_jobs("Sandbox async job canceled by runtime shutdown.")


async def _cancel_runtime_jobs(predicate: _AsyncCommandJobPredicate) -> bool:
    tasks: list[asyncio.Task[None]] = []
    for run_id, job in list(_jobs.items()):
        if not predicate(run_id, job):
            continue
        _jobs.pop(run_id, None)
        if not job.task.done():
            job.task.cancel()
        tasks.append(job.task)
    if not tasks:
        return False
    await asyncio.gather(*tasks, return_exceptions=True)
    return True


async def _run_async_sandbox_command(
    *,
    run_id: str,
    context: AgentRuntimeContext,
    wrapped_command: str,
    stat_command: str,
) -> None:
    if context.sandbox_container_id is None:
        await sandbox_async_job_service.fail_async_job(run_id, "No sandbox container selected.")
        return

    try:
        result = await execute_sandbox_container_command(
            id=context.sandbox_container_id,
            command=wrapped_command,
        )
        output_bytes, output_lines = await _stat_output_file(context.sandbox_container_id, stat_command)
        await sandbox_async_job_service.complete_async_job(
            run_id,
            exit_code=result.exit_code,
            output_bytes=output_bytes,
            output_lines=output_lines,
        )
    except asyncio.CancelledError:
        await sandbox_async_job_service.cancel_async_job(run_id, "Sandbox async job canceled.")
        raise
    except Exception as exc:
        logger.exception("async sandbox command execution failed: %s", run_id)
        await sandbox_async_job_service.fail_async_job(run_id, str(exc) or "Sandbox async job failed.")


async def _stat_output_file(container_id: int, stat_command: str) -> tuple[int, int]:
    try:
        result = await execute_sandbox_container_command(id=container_id, command=stat_command)
    except Exception:
        logger.debug("failed to stat async sandbox command output", exc_info=True)
        return 0, 0
    parts = result.output.strip().split()
    if len(parts) < 2:
        return 0, 0
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return 0, 0


def _finish_async_sandbox_command(run_id: str, task: asyncio.Task[None]) -> None:
    _jobs.pop(run_id, None)
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("async sandbox command task failed: %s", run_id)
