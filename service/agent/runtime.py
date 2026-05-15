import asyncio
import shlex
from datetime import datetime

from core.runtime.context import AgentRuntimeContext, AgentUserContext, main_agent_instance_id
from core.runtime.session import get_agent_pool
from core.tools.knowledge import current_knowledge_generation
from core.tools.sandbox import SANDBOX_SKILLS_DIR
from logger import get_logger
from middleware.auth import AuthUser
from schema.agent.events import DoneEvent, ErrorEvent
from service.agent import sessions as agent_sessions
from service.sandbox.commands import execute_sandbox_container_command
from service.sandbox.status import resolve_sandbox_container_tool_binding


logger = get_logger(__name__)

_MAX_SANDBOX_SKILLS = 32


async def submit_turn(
    *,
    session_id: str,
    text: str,
    user: AuthUser,
    sandbox_container_id: int | None,
    requested_agent_code: str | None,
) -> None:
    agent_code = await agent_sessions.ensure_chat_session_meta(
        session_id,
        text,
        requested_agent_code,
        user_id=user.id,
        user_role=user.role,
    )
    context = await build_runtime_context(session_id, user, sandbox_container_id, agent_code)
    runtime = await get_agent_pool().get_or_create(session_id)
    await runtime.start_turn(text, agent_code, context)


async def interrupt_turn(*, session_id: str, user: AuthUser) -> bool:
    await _raise_unless_can_access(session_id, user)
    return await get_agent_pool().try_interrupt(session_id)


async def cancel_all_tasks(*, session_id: str, user: AuthUser) -> bool:
    await _raise_unless_can_access(session_id, user)
    return await get_agent_pool().cancel_all(session_id)


def not_found_error() -> ErrorEvent:
    return ErrorEvent(created_at=datetime.now(), message="agent session not found", code="not_found")


def done_event() -> DoneEvent:
    return DoneEvent(created_at=datetime.now())


async def _raise_unless_can_access(session_id: str, user: AuthUser) -> None:
    if not await agent_sessions.can_access_session(session_id, user.id, user.role):
        raise PermissionError("agent session not found")


async def build_runtime_context(
    session_id: str,
    user: AuthUser,
    sandbox_container_id: int | None,
    agent_code: str = "",
) -> AgentRuntimeContext:
    selected_container_id = None
    selected_container_generation = 0
    sandbox_skill_metadata: tuple[str, ...] = ()
    if sandbox_container_id is not None:
        binding = await resolve_sandbox_container_tool_binding(
            id=sandbox_container_id,
            user_id=user.id,
            user_role=user.role,
        )
        if binding is not None:
            selected_container_id = binding.id
            selected_container_generation = binding.generation
            sandbox_skill_metadata = await _load_sandbox_skill_metadata(binding.id)

    return AgentRuntimeContext(
        session_id=session_id,
        user=_agent_user_context(user),
        agent_code=agent_code,
        agent_instance_id=main_agent_instance_id(session_id, user.id, agent_code) if agent_code else "",
        knowledge_generation=current_knowledge_generation(),
        sandbox_container_id=selected_container_id,
        sandbox_container_generation=selected_container_generation,
        sandbox_skill_metadata=sandbox_skill_metadata,
    )


def build_base_runtime_context(session_id: str, user: AuthUser, agent_code: str = "") -> AgentRuntimeContext:
    return AgentRuntimeContext(
        session_id=session_id,
        user=_agent_user_context(user),
        agent_code=agent_code,
        agent_instance_id=main_agent_instance_id(session_id, user.id, agent_code) if agent_code else "",
        knowledge_generation=current_knowledge_generation(),
    )


def _agent_user_context(user: AuthUser) -> AgentUserContext:
    return AgentUserContext(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
    )


async def _load_sandbox_skill_metadata(container_id: int) -> tuple[str, ...]:
    try:
        result = await execute_sandbox_container_command(
            id=container_id,
            command=_build_skill_metadata_command(),
            timeout_seconds=30,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.debug("failed to load sandbox skill metadata: %s", container_id, exc_info=True)
        return ()
    if result.exit_code != 0 or not result.output.strip():
        return ()
    return tuple(_parse_skill_metadata_output(result.output))


def _build_skill_metadata_command() -> str:
    skills_dir = shlex.quote(SANDBOX_SKILLS_DIR)
    return f"""
if [ -d {skills_dir} ]; then
  find {skills_dir} -mindepth 2 -maxdepth 2 -name SKILL.md -type f | sort | head -n {_MAX_SANDBOX_SKILLS} | while IFS= read -r skill_file; do
    skill_name=$(basename "$(dirname "$skill_file")")
    printf '===SKILL:%s===\n' "$skill_name"
    awk '
      NR == 1 && $0 == "---" {{ print; in_fm = 1; next }}
      in_fm {{ print; if ($0 == "---") exit }}
    ' "$skill_file"
  done
fi
""".strip()


def _parse_skill_metadata_output(output: str) -> list[str]:
    blocks: list[str] = []
    current_name = ""
    current_lines: list[str] = []
    for raw_line in output.splitlines():
        if raw_line.startswith("===SKILL:") and raw_line.endswith("==="):
            _append_skill_metadata(blocks, current_name, current_lines)
            current_name = raw_line.removeprefix("===SKILL:").removesuffix("===").strip()
            current_lines = []
            continue
        current_lines.append(raw_line)
    _append_skill_metadata(blocks, current_name, current_lines)
    return blocks


def _append_skill_metadata(blocks: list[str], name: str, lines: list[str]) -> None:
    if not name or not lines:
        return
    front_matter = _front_matter_from_lines(lines)
    if front_matter is None:
        return
    blocks.append(f"## {name}\n\n```yaml\n{front_matter}\n```")


def _front_matter_from_lines(lines: list[str]) -> str | None:
    if not lines or lines[0] != "---":
        return None
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            return "\n".join(lines[:index + 1]).strip()
    return None
