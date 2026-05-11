"""Background sandbox command execution and completion notifications."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from core.context import AgentRuntimeContext
from logger import get_logger
from service import agent_notification_service
from service.sandbox_container_service import execute_sandbox_container_command


logger = get_logger(__name__)


@dataclass
class _AsyncCommandJob:
    task: asyncio.Task[None]
    session_id: str
    agent_instance_id: str
    sandbox_container_id: int | None
    notifying: bool = False


_jobs: dict[str, _AsyncCommandJob] = {}


def start_async_sandbox_command(
    *,
    run_id: str,
    context: AgentRuntimeContext,
    command: str,
    output_path: str,
    wrapped_command: str,
    stat_command: str,
) -> None:
    task = asyncio.create_task(
        _run_async_sandbox_command(
            run_id=run_id,
            context=context,
            command=command,
            output_path=output_path,
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


def has_pending_async_sandbox_commands(
    *,
    session_id: str,
    agent_instance_id: str,
) -> bool:
    return any(
        job.session_id == session_id
        and job.agent_instance_id == agent_instance_id
        and (job.notifying or not job.task.done())
        for job in _jobs.values()
    )


async def cancel_agent_async_sandbox_commands(
    *,
    session_id: str,
    agent_instance_id: str,
) -> bool:
    tasks = [
        _jobs.pop(run_id).task
        for run_id, job in list(_jobs.items())
        if job.session_id == session_id and job.agent_instance_id == agent_instance_id
    ]
    if not tasks:
        return False
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    return True


async def cancel_sandbox_async_sandbox_commands(container_id: int) -> bool:
    tasks = [
        _jobs.pop(run_id).task
        for run_id, job in list(_jobs.items())
        if job.sandbox_container_id == container_id
    ]
    if not tasks:
        return False
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    return True


async def cancel_session_async_sandbox_commands(session_id: str) -> bool:
    tasks = [
        _jobs.pop(run_id).task
        for run_id, job in list(_jobs.items())
        if job.session_id == session_id
    ]
    if not tasks:
        return False
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    return True


async def stop_async_sandbox_commands() -> None:
    tasks = [job.task for job in _jobs.values()]
    _jobs.clear()
    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _run_async_sandbox_command(
    *,
    run_id: str,
    context: AgentRuntimeContext,
    command: str,
    output_path: str,
    wrapped_command: str,
    stat_command: str,
) -> None:
    if context.sandbox_container_id is None:
        return

    exit_code = 1
    try:
        result = await execute_sandbox_container_command(
            id=context.sandbox_container_id,
            command=wrapped_command,
        )
        exit_code = result.exit_code
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("async sandbox command execution failed: %s", run_id)

    _mark_async_sandbox_command_notifying(run_id)
    output_bytes, output_lines = await _stat_output_file(context.sandbox_container_id, stat_command)
    await agent_notification_service.enqueue_async_command_finished_notification(
        session_id=context.session_id,
        target_agent_code=context.agent_code,
        target_agent_instance_id=context.agent_instance_id,
        run_id=run_id,
        command=command,
        output_file=output_path,
        exit_code=exit_code,
        output_bytes=output_bytes,
        output_lines=output_lines,
        nested_for_agent_code=context.nested_for_agent_code,
        nested_call_id=context.nested_call_id,
        sandbox_container_id=context.sandbox_container_id,
        sandbox_container_generation=context.sandbox_container_generation,
        sandbox_skill_metadata=context.sandbox_skill_metadata,
    )


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


def _mark_async_sandbox_command_notifying(run_id: str) -> None:
    job = _jobs.get(run_id)
    if job is not None:
        job.notifying = True


def _finish_async_sandbox_command(run_id: str, task: asyncio.Task[None]) -> None:
    _jobs.pop(run_id, None)
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("async sandbox command task failed: %s", run_id)
