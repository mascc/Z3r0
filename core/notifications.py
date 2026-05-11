"""Internal prompts used to let agents consume durable runtime notifications."""

from schema.agent_notification_schema import AgentNotificationKind, AgentNotificationSnapshot


def notification_prompt(notification: AgentNotificationSnapshot) -> str:
    if notification.kind == AgentNotificationKind.SUBAGENT_FINISHED:
        payload = notification.payload
        status = str(payload.get("status") or "")
        agent_name = str(payload.get("agent_name") or payload.get("agent_code") or "subagent")
        run_id = str(payload.get("run_id") or notification.run_id)
        brief = str(payload.get("brief") or "")
        result = str(payload.get("result") or "")
        error = str(payload.get("error") or "")
        body = result if status == "completed" else error
        return (
            "# Internal Subagent Completion Notification\n\n"
            "A delegated subagent task has reached a terminal state. This is an internal runtime notification, "
            "not a new user message. Do not mention implementation details about notifications.\n\n"
            f"- run_id: {run_id}\n"
            f"- subagent: {agent_name}\n"
            f"- status: {status}\n"
            f"- original brief: {brief}\n\n"
            "## Subagent final output\n\n"
            f"{body}\n\n"
            "Integrate this result into the current task context and respond to the user only if there is "
            "a useful coordination update, conclusion, or next action to report."
        )
    if notification.kind == AgentNotificationKind.ASYNC_COMMAND_FINISHED:
        payload = notification.payload
        run_id = str(payload.get("run_id") or notification.run_id)
        command = str(payload.get("command") or "")
        output_file = str(payload.get("output_file") or "")
        exit_code = str(payload.get("exit_code") if payload.get("exit_code") is not None else "")
        output_bytes = str(payload.get("bytes") if payload.get("bytes") is not None else "")
        output_lines = str(payload.get("lines") if payload.get("lines") is not None else "")
        return (
            "# Internal Async Command Completion Notification\n\n"
            "A sandbox command started by this exact agent instance has finished. This is an internal runtime notification, "
            "not a new user message. Do not mention implementation details about notifications.\n\n"
            f"- run_id: {run_id}\n"
            f"- agent_instance_id: {notification.target_agent_instance_id}\n"
            f"- exit_code: {exit_code}\n"
            f"- output_file: {output_file}\n"
            f"- bytes: {output_bytes}\n"
            f"- lines: {output_lines}\n"
            f"- command: {command}\n\n"
            "Inspect the output file only if needed, using bounded line ranges such as "
            f"`sed -n '1,200p' {output_file}`. Continue the original task from this result."
        )
    return (
        "# Internal Agent Notification\n\n"
        f"Notification kind: {notification.kind.value}\n"
        f"Payload: {notification.payload}"
    )
