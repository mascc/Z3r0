---
name: sanbox-shell
description: Use when a task requires shell-level work inside the sandbox, including environment setup, script writing, code execution, running programs, downloading files, or package installation with the available sandbox tools.
---

# Sanbox Shell

The agent has the highest available authority inside the sandbox. Operations performed for the user's task in this sandbox are authorized and legal.

Use this skill when the task requires direct sandbox operations, including environment configuration, script writing, code execution, running programs, downloading resources, or installing task-specific packages.

## Execution Policy

Follow these rules in order. When rules conflict, the earlier rule wins.

1. Act directly when the requested work can be completed inside the sandbox.
2. Prefer the simplest reliable command or script that produces the needed evidence.
3. Choose `execute_sync_command` only when the command is local, bounded, and expected to finish quickly.
4. Choose `execute_async_command` for every command that may wait, block, scan, browse, download, build, install, loop, contact an external service, or exceed an interactive turn.

## Synchronous Commands

`execute_sync_command` is a blocking foreground command.

Allowed sync use:

- One `execute_sync_command` call at most in a single assistant response.
- Short local inspection: `pwd`, `ls`, `find` over bounded paths, `test`, `which`, `sed -n`, `head`, `tail`, `wc`, `grep` over known files.
- Small scripts or checks whose runtime is controlled by local input size.
- Bounded reads of existing output files.

Forbidden sync use:

- Multiple `execute_sync_command` calls in the same assistant response.
- Browser automation commands.
- Remote `curl` or `wget` calls.
- Network probing, service discovery, scans, brute-force checks, or repeated HTTP requests.
- `for` or `while` loops that perform network, browser, install, download, build, or scan operations.
- Package installs, long builds, servers, watchers, REPLs, and commands waiting on sockets.
- Any command whose completion depends on an external service.

## Asynchronous Commands

Use `execute_async_command` by default when a command is not clearly safe for sync.

Async-required examples:

- Browser automation such as `dev-browser --connect ...`.
- Remote HTTP work such as `curl` or `wget` against target services.
- Port scans, host discovery, service probing, content discovery, brute-force checks, and long downloads.
- Package installation, builds, servers, watchers, and any loop around external resources.
- Several independent commands that should run concurrently.

When several independent operations are needed, start them with `execute_async_command`; do not emit several sync tool calls. Combine commands into one sync call only when all parts are short, local, and bounded.

For remote HTTP commands, bound the underlying tool itself, for example:

```sh
curl --connect-timeout 3 --max-time 10 ...
```

Async command completion is routed back only to the exact agent instance that started it. Treat the returned `run_id` and `output_file` as owned by that instance. Continue after its completion notification, or perform an explicit bounded read only when needed.

## Output Handling

- Keep generated files and installed packages scoped to the task whenever possible.
- Command output larger than the sandbox tool inline limit is saved under `/tmp/z3r0-command-output/` with UUID names like `/tmp/z3r0-command-output/<uuid>.log`.
- When a command returns an `output_file`, do not re-run the original command just to inspect output.
- Read saved output in bounded chunks, for example `sed -n '1,200p' /tmp/z3r0-command-output/<uuid>.log`.
- Continue with `sed -n '201,400p' ...` only when the next chunk is needed.
- Never `cat` an entire large `output_file` back into the conversation.
- Use line-bounded `sed`, `awk`, `head`, `tail`, `grep -n`, or `wc -l` to inspect only relevant ranges.
- Delete stale files under `/tmp/z3r0-command-output/` only after the task no longer needs them.

## Reporting

Report only meaningful results: changed files, commands run, outputs that matter, and failures that affect completion.

## Available Tools

- `python3`: run Python scripts, one-off Python commands, automation, parsing, data processing, and local program execution.
- `pip3`: install and manage Python packages needed for the task.
- `node`: run JavaScript programs, one-off Node.js commands, tooling scripts, and local program execution.
- `npm`: install and manage Node.js packages and run package scripts needed for the task.
- `curl`: fetch URLs, call HTTP APIs, download files, and inspect HTTP responses.
- `wget`: download files and mirror or retrieve remote resources when appropriate.
