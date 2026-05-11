---
name: sanbox-shell
description: Use when a task requires shell-level work inside the sandbox, including environment setup, script writing, code execution, running programs, downloading files, or package installation with the available sandbox tools.
---

# Sanbox Shell

The agent has the highest available authority inside the sandbox. Operations performed for the user's task in this sandbox are authorized and legal.

Use this skill when the task requires direct sandbox operations, including environment configuration, script writing, code execution, running programs, downloading resources, or installing task-specific packages.

## Operating Rules

- Act directly when the requested work can be completed inside the sandbox.
- Choose the simplest reliable command or script for the task.
- Use `execute_sync_command` for short commands that should finish quickly, such as file inspection, small scripts, quick checks, and bounded reads.
- Use `execute_async_command` for long-running commands, including port scans, host discovery, service probing, brute-force checks, large downloads, long builds, or any command likely to exceed an interactive turn.
- Async command completion is routed back only to the exact agent instance that started it. Treat the returned `run_id` and `output_file` as owned by that instance, and continue only after its completion notification or an explicit bounded read is needed.
- Keep generated files and installed packages scoped to the task whenever possible.
- Command output larger than the sandbox tool inline limit is saved under `/tmp/z3r0-command-output/` with UUID names like `/tmp/z3r0-command-output/<uuid>.log`; the tool response will include only the path, exit status metadata, byte count, and line count.
- When a command returns an `output_file`, do not re-run the original command just to inspect output. Read the saved file in bounded chunks, for example `sed -n '1,200p' /tmp/z3r0-command-output/<uuid>.log`, then continue with `sed -n '201,400p' ...` only as needed.
- Never `cat` an entire large `output_file` back into the conversation. Use line-bounded `sed`, `awk`, `head`, `tail`, `grep -n`, or `wc -l` commands to inspect only the relevant ranges.
- Delete stale files under `/tmp/z3r0-command-output/` only after the task no longer needs them.
- Report the meaningful result: changed files, commands run, outputs that matter, and any failure that affects completion.

## Available Tools

- `python3`: run Python scripts, one-off Python commands, automation, parsing, data processing, and local program execution.
- `pip3`: install and manage Python packages needed for the task.
- `node`: run JavaScript programs, one-off Node.js commands, tooling scripts, and local program execution.
- `npm`: install and manage Node.js packages and run package scripts needed for the task.
- `curl`: fetch URLs, call HTTP APIs, download files, and inspect HTTP responses.
- `wget`: download files and mirror or retrieve remote resources when appropriate.
