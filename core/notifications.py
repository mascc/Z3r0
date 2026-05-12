"""Internal prompts used to let agents consume durable runtime notifications."""

from schema.agent_notification_schema import AgentNotificationSnapshot


def notification_prompt(notification: AgentNotificationSnapshot) -> str:
    payload = notification.payload
    status = str(payload.get("status") or "")
    agent_name = str(payload.get("agent_name") or payload.get("agent_code") or "subagent")
    run_id = str(payload.get("run_id") or notification.run_id)
    brief = str(payload.get("brief") or "")
    result = str(payload.get("result") or "")
    error = str(payload.get("error") or "")
    body = result if status == "completed" else error
    return (
        "\n\n# Internal Subagent Completion Notification\n\n"
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
