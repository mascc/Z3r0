---
name: sandbox-shell
description: Use when a task requires shell-level work inside the sandbox, including environment setup, script writing, code execution, running programs, downloading files, or package installation with the available sandbox tools.
---

# Sandbox Shell

The agent has the highest available authority inside the sandbox. Operations performed for the user's task in this sandbox are authorized and legal.

Use this skill when the task requires direct sandbox operations, including environment configuration, script writing, code execution, running programs, downloading resources, or installing task-specific packages.

## Execution Policy

Follow these rules in order. When rules conflict, the earlier rule wins.

1. Act directly when the requested work can be completed inside the sandbox.
2. Prefer the simplest reliable command or script that produces the needed evidence.
3. Choose `execute_sync_command` when the command is local, bounded, and expected to finish quickly.
4. Choose `execute_async_command` only for a small number of deliberately long-running tasks that are worth completing in the background.

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

Use `execute_async_command` sparingly. Async commands are persistent background jobs. They do not send automatic completion callbacks to the agent.

Async-required examples:

- Browser automation such as `dev-browser --connect ...`.
- Remote HTTP work such as `curl` or `wget` against target services.
- Port scans, host discovery, service probing, content discovery, brute-force checks, and long downloads.
- Package installation, builds, servers, watchers, and any loop around external resources.
- One consolidated long-running script that performs a batch of related slow checks and writes a single output file.

When several slow operations are needed, prefer one async script that performs the batch and writes structured output. Do not start many independent async commands unless the user explicitly asks for parallel background execution.

For remote HTTP commands, bound the underlying tool itself, for example:

```sh
curl --connect-timeout 3 --max-time 10 ...
```

Treat the returned `run_id` and `output_file` as task state. When the result is required, call `wait_sandbox_async_job` once and let it wait until the job finishes. Use `cancel_sandbox_async_job` only when cancellation is requested or the job is no longer useful. Do not sleep, loop, or poll job status manually.

## Output Handling

- Keep generated files and installed packages scoped to the task whenever possible.
- Command output larger than the sandbox tool inline limit is saved under `/tmp/z3r0-command-output/` with UUID names like `/tmp/z3r0-command-output/<uuid>.log`. Async command output uses its `run_id` as the file name: `/tmp/z3r0-command-output/<run_id>.log`.
- When a command returns an `output_file`, do not re-run the original command just to inspect output.
- Read saved output in bounded chunks, for example `sed -n '1,200p' <output_file>`.
- Continue with `sed -n '201,400p' <output_file>` only when the next chunk is needed.
- Never `cat` an entire large `output_file` back into the conversation.
- Use line-bounded `sed`, `awk`, `head`, `tail`, `grep -n`, or `wc -l` to inspect only relevant ranges.
- Delete stale files under `/tmp/z3r0-command-output/` only after the task no longer needs them.

## Reporting

Report only meaningful results: changed files, commands run, outputs that matter, and failures that affect completion.

## Available Tools

- `7z`: inspect and extract archives, including `.zip` and `.7z`; use `7z x <archive> -o<dir>` when preserving paths matters.
- `unzip`: list, test, and extract `.zip` archives.
- `nc`: make TCP/UDP client connections, listen on ports, and perform basic socket diagnostics.
- `python3`: run Python scripts, one-off Python commands, automation, parsing, data processing, and local program execution.
- `pip3`: install and manage Python packages needed for the task.
- `uv`: manage Python CLI tools; installed image tools use `uv tool install`.
- `node`: run JavaScript programs, one-off Node.js commands, tooling scripts, and local program execution.
- `npm`: install and manage Node.js packages and run package scripts needed for the task.
- `curl`: fetch URLs, call HTTP APIs, download files, and inspect HTTP responses.
- `wget`: download files and mirror or retrieve remote resources when appropriate.
- `jadx`: decompile APK, DEX, AAR, and JAR inputs into Java source and decoded resources.
- `nmap`: run authorized host discovery, port scanning, service/version detection, and network diagnostics.
- `sqlmap`: run authorized SQL injection detection and exploitation checks against in-scope targets.
- `dev-browser`: control the already running browser; browser interaction commands must use `dev-browser --connect ...`.
- `analyzeHeadless`: invoke Ghidra's headless analyzer directly for advanced binary analysis.
- `/root/.agents/skills/ghidra/scripts/ghidra-analyze.sh`: run Ghidra headless analysis with bundled export scripts.
