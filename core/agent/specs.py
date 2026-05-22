from dataclasses import dataclass

from agents import Tool

from core.tools.knowledge import create_knowledge, find_knowledge, load_knowledge, update_knowledge
from core.tools.sandbox import (
    cancel_sandbox_async_job,
    execute_async_command,
    execute_sync_command,
    load_skill,
    wait_sandbox_async_job,
)


@dataclass(frozen=True, slots=True)
class ToolMount:
    tool: Tool
    requires_sandbox_container: bool = False


@dataclass(frozen=True, slots=True)
class SubagentMount:
    code: str


@dataclass(frozen=True, slots=True)
class AgentSpec:
    code: str
    tools: tuple[ToolMount, ...] = ()
    subagents: tuple[SubagentMount, ...] = ()


KNOWLEDGE_TOOLS = (
    ToolMount(find_knowledge),
    ToolMount(load_knowledge),
    ToolMount(create_knowledge),
    ToolMount(update_knowledge),
)


AGENT_SPECS: tuple[AgentSpec, ...] = (
    AgentSpec(
        code="cso",
        tools=KNOWLEDGE_TOOLS,
        subagents=(
            SubagentMount(code="cce"),
            SubagentMount(code="cie"),
            SubagentMount(code="cpe"),
            SubagentMount(code="cre"),
        ),
    ),
    AgentSpec(
        code="cce",
        tools=(
            ToolMount(execute_sync_command, requires_sandbox_container=True),
            ToolMount(execute_async_command, requires_sandbox_container=True),
            ToolMount(wait_sandbox_async_job, requires_sandbox_container=True),
            ToolMount(cancel_sandbox_async_job, requires_sandbox_container=True),
            ToolMount(load_skill, requires_sandbox_container=True),
            *KNOWLEDGE_TOOLS,
        ),
    ),
    AgentSpec(
        code="cie",
        tools=(
            ToolMount(execute_sync_command, requires_sandbox_container=True),
            ToolMount(execute_async_command, requires_sandbox_container=True),
            ToolMount(wait_sandbox_async_job, requires_sandbox_container=True),
            ToolMount(cancel_sandbox_async_job, requires_sandbox_container=True),
            ToolMount(load_skill, requires_sandbox_container=True),
            *KNOWLEDGE_TOOLS,
        ),
    ),
    AgentSpec(
        code="cpe",
        tools=(
            ToolMount(execute_sync_command, requires_sandbox_container=True),
            ToolMount(execute_async_command, requires_sandbox_container=True),
            ToolMount(wait_sandbox_async_job, requires_sandbox_container=True),
            ToolMount(cancel_sandbox_async_job, requires_sandbox_container=True),
            ToolMount(load_skill, requires_sandbox_container=True),
            *KNOWLEDGE_TOOLS,
        ),
    ),
    AgentSpec(
        code="cre",
        tools=(
            ToolMount(execute_sync_command, requires_sandbox_container=True),
            ToolMount(execute_async_command, requires_sandbox_container=True),
            ToolMount(wait_sandbox_async_job, requires_sandbox_container=True),
            ToolMount(cancel_sandbox_async_job, requires_sandbox_container=True),
            ToolMount(load_skill, requires_sandbox_container=True),
            *KNOWLEDGE_TOOLS,
        ),
    ),
)


DEFAULT_AGENT_CODE = AGENT_SPECS[0].code
