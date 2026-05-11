import asyncio
import re
import shlex
from uuid import uuid4

from agents import RunContextWrapper, function_tool

from core.context import AgentRuntimeContext
from core.jobs import start_async_sandbox_command
from schema.tool_result_schema import ToolResultSchema, ToolResultStatusSchema, ToolResultTypeSchema
from service.sandbox_container_service import execute_sandbox_container_command
from utils.markdown import markdown_body_without_front_matter


_SKILL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SANDBOX_SKILLS_DIR = "/root/.agents/skills"
_COMMAND_INLINE_OUTPUT_MAX_BYTES = 32 * 1024
_COMMAND_OUTPUT_CHUNK_LINE_COUNT = 200
_COMMAND_OUTPUT_DIR = "/tmp/z3r0-command-output"


def _command_required_error() -> str:
    return ToolResultSchema(
        status=ToolResultStatusSchema.ERROR,
        type=ToolResultTypeSchema.COMMAND_EXECUTION,
        output="sandbox container command is required",
    ).model_dump_json()


def _no_container_error() -> str:
    return ToolResultSchema(
        status=ToolResultStatusSchema.ERROR,
        type=ToolResultTypeSchema.COMMAND_EXECUTION,
        output="No sandbox container selected.",
    ).model_dump_json()


def _build_output_filtered_command(command: str, output_path: str) -> str:
    quoted_command = shlex.quote(command)
    quoted_output_dir = shlex.quote(_COMMAND_OUTPUT_DIR)
    quoted_output_path = shlex.quote(output_path)
    first_chunk_end = _COMMAND_OUTPUT_CHUNK_LINE_COUNT
    second_chunk_start = first_chunk_end + 1
    second_chunk_end = first_chunk_end + _COMMAND_OUTPUT_CHUNK_LINE_COUNT
    return "\n".join(
        (
            "set +e",
            f"output_dir={quoted_output_dir}",
            f"output_path={quoted_output_path}",
            f"inline_limit={_COMMAND_INLINE_OUTPUT_MAX_BYTES}",
            "mkdir -p \"$output_dir\" || exit 125",
            "rm -f \"$output_path\"",
            ": > \"$output_path\" || exit 125",
            f"/bin/sh -lc {quoted_command} > \"$output_path\" 2>&1 &",
            "command_pid=$!",
            "trap 'kill -TERM \"$command_pid\" 2>/dev/null' TERM INT HUP",
            "wait \"$command_pid\"",
            "command_exit_code=$?",
            "trap - TERM INT HUP",
            "output_bytes=$(wc -c < \"$output_path\" 2>/dev/null | tr -d '[:space:]')",
            "output_lines=$(sed -n '$=' \"$output_path\" 2>/dev/null | tr -d '[:space:]')",
            "case \"$output_bytes\" in ''|*[!0-9]*) output_bytes=0 ;; esac",
            "case \"$output_lines\" in ''|*[!0-9]*) output_lines=0 ;; esac",
            "if [ \"$output_bytes\" -le \"$inline_limit\" ]; then",
            "  cat \"$output_path\"",
            "  rm -f \"$output_path\"",
            "else",
            "  printf '%s\\n' 'Command output was too large to inline.'",
            "  printf 'output_file: %s\\n' \"$output_path\"",
            "  printf 'bytes: %s\\n' \"$output_bytes\"",
            "  printf 'lines: %s\\n' \"$output_lines\"",
            "  printf 'inline_limit_bytes: %s\\n' \"$inline_limit\"",
            f"  printf \"read_chunks: sed -n '1,{first_chunk_end}p' %s\\n\" \"$output_path\"",
            f"  printf \"next_chunk: sed -n '{second_chunk_start},{second_chunk_end}p' %s\\n\" \"$output_path\"",
            "fi",
            "exit \"$command_exit_code\"",
        )
    )


def _new_command_output_path() -> str:
    return f"{_COMMAND_OUTPUT_DIR}/{uuid4().hex}.log"


def _build_async_command(command: str, output_path: str) -> str:
    quoted_command = shlex.quote(command)
    quoted_output_dir = shlex.quote(_COMMAND_OUTPUT_DIR)
    quoted_output_path = shlex.quote(output_path)
    return "\n".join(
        (
            "set +e",
            f"output_dir={quoted_output_dir}",
            f"output_path={quoted_output_path}",
            "mkdir -p \"$output_dir\" || exit 125",
            "rm -f \"$output_path\"",
            ": > \"$output_path\" || exit 125",
            f"/bin/sh -lc {quoted_command} > \"$output_path\" 2>&1 &",
            "command_pid=$!",
            "trap 'kill -TERM \"$command_pid\" 2>/dev/null' TERM INT HUP",
            "wait \"$command_pid\"",
            "command_exit_code=$?",
            "trap - TERM INT HUP",
            "exit \"$command_exit_code\"",
        )
    )


def _build_output_stat_command(output_path: str) -> str:
    return (
        f"test -f {shlex.quote(output_path)} || exit 0; "
        f"bytes=$(wc -c < {shlex.quote(output_path)} 2>/dev/null | tr -d '[:space:]'); "
        f"lines=$(sed -n '$=' {shlex.quote(output_path)} 2>/dev/null | tr -d '[:space:]'); "
        "case \"$bytes\" in ''|*[!0-9]*) bytes=0 ;; esac; "
        "case \"$lines\" in ''|*[!0-9]*) lines=0 ;; esac; "
        "printf '%s %s\\n' \"$bytes\" \"$lines\""
    )


@function_tool
async def execute_sync_command(ctx: RunContextWrapper[AgentRuntimeContext], command: str) -> str:
    """Execute a short command in the selected sandbox container and wait for completion.
    
    Args:
        command: The command to execute.

    Returns:
        The result of the command execution.
    """
    container_id = ctx.context.sandbox_container_id
    if container_id is None:
        return _no_container_error()
    if not command.strip():
        return _command_required_error()

    try:
        result = await execute_sandbox_container_command(
            id=container_id,
            command=_build_output_filtered_command(command, _new_command_output_path()),
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return ToolResultSchema(
            status=ToolResultStatusSchema.ERROR,
            type=ToolResultTypeSchema.COMMAND_EXECUTION,
            output=str(exc) or "Command execution failed.",
        ).model_dump_json()

    return ToolResultSchema(
        status=ToolResultStatusSchema.SUCCESS if result.exit_code == 0 else ToolResultStatusSchema.ERROR,
        type=ToolResultTypeSchema.COMMAND_EXECUTION,
        output=result.output,
        exit_code=result.exit_code,
    ).model_dump_json()


@function_tool
async def execute_async_command(ctx: RunContextWrapper[AgentRuntimeContext], command: str) -> str:
    """Start a long-running command in the selected sandbox container and return immediately.
    
    Args:
        command: The long-running command to execute.

    Returns:
        JSON status including run_id and output_file. A completion notification is sent to this exact agent instance.
    """
    container_id = ctx.context.sandbox_container_id
    if container_id is None:
        return _no_container_error()
    if not command.strip():
        return _command_required_error()
    if not ctx.context.agent_instance_id:
        return ToolResultSchema(
            status=ToolResultStatusSchema.ERROR,
            type=ToolResultTypeSchema.COMMAND_EXECUTION,
            output="agent instance id is required for async command execution",
        ).model_dump_json()

    run_id = str(uuid4())
    output_path = _new_command_output_path()
    task_context = AgentRuntimeContext(
        session_id=ctx.context.session_id,
        user=ctx.context.user,
        agent_code=ctx.context.agent_code,
        agent_instance_id=ctx.context.agent_instance_id,
        nested_for_agent_code=ctx.context.nested_for_agent_code,
        nested_call_id=ctx.context.nested_call_id,
        knowledge_generation=ctx.context.knowledge_generation,
        sandbox_container_id=ctx.context.sandbox_container_id,
        sandbox_container_generation=ctx.context.sandbox_container_generation,
        sandbox_skill_metadata=ctx.context.sandbox_skill_metadata,
    )
    command_text = command.strip()
    start_async_sandbox_command(
        run_id=run_id,
        context=task_context,
        command=command_text,
        output_path=output_path,
        wrapped_command=_build_async_command(command_text, output_path),
        stat_command=_build_output_stat_command(output_path),
    )
    output = "\n".join(
        (
            "Async command started.",
            f"run_id: {run_id}",
            f"output_file: {output_path}",
            f"agent_instance_id: {ctx.context.agent_instance_id}",
            "status: running",
            f"read_chunks: sed -n '1,{_COMMAND_OUTPUT_CHUNK_LINE_COUNT}p' {output_path}",
            "completion: this exact agent instance will receive an internal notification when the command finishes",
        )
    )
    return ToolResultSchema(
        status=ToolResultStatusSchema.SUCCESS,
        type=ToolResultTypeSchema.COMMAND_EXECUTION,
        output=output,
    ).model_dump_json()


@function_tool
async def load_skill(ctx: RunContextWrapper[AgentRuntimeContext], name: str) -> str:
    """Load the body of a named skill from the selected sandbox container.

    Args:
        name: Skill directory name under /root/.agents/skills.

    Returns:
        The skill detail markdown body without YAML Front Matter.
    """
    container_id = ctx.context.sandbox_container_id
    if container_id is None:
        return ToolResultSchema(
            status=ToolResultStatusSchema.ERROR,
            type=ToolResultTypeSchema.SKILL_DETAIL,
            output="No sandbox container selected.",
        ).model_dump_json()

    skill_name = name.strip()
    if not _SKILL_NAME_PATTERN.fullmatch(skill_name):
        return ToolResultSchema(
            status=ToolResultStatusSchema.ERROR,
            type=ToolResultTypeSchema.SKILL_DETAIL,
            output="Skill name must contain only letters, numbers, dot, underscore, or dash.",
        ).model_dump_json()

    skill_path = f"{SANDBOX_SKILLS_DIR}/{skill_name}/SKILL.md"
    command = f"test -f {shlex.quote(skill_path)} && cat {shlex.quote(skill_path)}"
    try:
        result = await execute_sandbox_container_command(id=container_id, command=command)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return ToolResultSchema(
            status=ToolResultStatusSchema.ERROR,
            type=ToolResultTypeSchema.SKILL_DETAIL,
            output=str(exc) or "Skill loading failed.",
        ).model_dump_json()

    if result.exit_code != 0:
        return ToolResultSchema(
            status=ToolResultStatusSchema.ERROR,
            type=ToolResultTypeSchema.SKILL_DETAIL,
            output=f"Skill not found: {skill_name}",
            exit_code=result.exit_code,
        ).model_dump_json()

    return ToolResultSchema(
        status=ToolResultStatusSchema.SUCCESS,
        type=ToolResultTypeSchema.SKILL_DETAIL,
        output=markdown_body_without_front_matter(result.output),
        exit_code=result.exit_code,
    ).model_dump_json()
