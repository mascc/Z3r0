from core.tools.knowledge import load_knowledge_metadata


MARKDOWN_OUTPUT_INSTRUCTIONS = """# Response Formatting

Always write user-facing responses as valid GitHub-Flavored Markdown.

- Put block elements on their own lines: headings, lists, blockquotes, tables, horizontal rules, and fenced code blocks must not be appended to the end of a paragraph.
- Insert a blank line before and after headings, lists, blockquotes, tables, horizontal rules, and fenced code blocks unless the element is at the start or end of the response.
- Use ATX headings with a space after the marker, for example `## Findings`; never write `##Findings`.
- Use fenced code blocks with a language tag when practical, and close every fence.
- Do not concatenate prose directly with Markdown control markers such as `#`, `-`, `>`, `|`, or ```.
"""


SANDBOX_COMMAND_INSTRUCTIONS = """# Sandbox Command Execution

When calling sandbox command tools, pass `timeout_seconds` explicitly.

- `execute_sync_command`: maximum 30 seconds.
- `execute_async_command`: maximum 300 seconds.
"""


def build_instructions(
    soul: str,
    rules: str,
    agent_code: str,
    sandbox_skill_metadata: tuple[str, ...],
    *,
    has_sandbox_container: bool,
    include_sandbox_commands: bool,
    include_sandbox_skills: bool,
    include_agent_knowledges: bool,
) -> str:
    parts = [soul, rules, MARKDOWN_OUTPUT_INSTRUCTIONS]
    if include_sandbox_commands and has_sandbox_container:
        parts.append(SANDBOX_COMMAND_INSTRUCTIONS)
    if include_agent_knowledges:
        parts.append(_build_agent_knowledge_instructions(load_knowledge_metadata(agent_code)))
    if include_sandbox_skills and has_sandbox_container:
        parts.append(_build_sandbox_skill_instructions(sandbox_skill_metadata))
    return "\n\n".join(part.strip() for part in parts if part.strip())


def _build_agent_knowledge_instructions(knowledge_metadata: tuple[str, ...]) -> str:
    if not knowledge_metadata:
        return (
            "# Knowledges\n\n"
            "No knowledge metadata."
        )

    return (
        "# Knowledges\n\n"
        "Available metadata only; each item includes body_line_count. "
        "Use `find_knowledge` to locate relevant body lines by keyword, "
        "then `load_knowledge` with line ranges before use or edit.\n\n"
        + "\n\n".join(knowledge_metadata)
    )


def _build_sandbox_skill_instructions(skill_metadata: tuple[str, ...]) -> str:
    if not skill_metadata:
        return (
            "# Sandbox Skills\n\n"
            "No sandbox skill metadata is available."
        )

    usage = (
        "Use matching sandbox skills to complete tasks. Metadata is only an index; "
        "load the full skill body before applying any skill.\n\n"
        "Rules:\n\n"
        "- Before executing any command, first call `load_skill` for `sandbox-shell` if it is listed.\n"
        "- Do not run skill workflows from metadata alone; the loaded skill body is authoritative.\n"
        "- After loading a skill, follow its workflow and constraints exactly.\n"
    )
    return (
        "# Sandbox Skills\n\n"
        + usage
        + "\nAvailable skill metadata:\n\n"
        + "\n\n".join(skill_metadata)
    )
