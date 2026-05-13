---
name: dev-browser
description: Browser automation for navigation, clicking, forms, screenshots, scraping, and testing. All browser operations must use dev-browser --connect to attach to the running browser; launching a separate browser is forbidden.
---

# Dev Browser

A CLI for controlling the already running browser process with sandboxed JavaScript scripts. The `--connect` flag attaches to that existing process; it does not start, launch, or open a browser.

## Core Rule

All browser operations must be performed through `dev-browser --connect ...`, which connects to the browser process that is already running in the sandbox. Never start, launch, install, open, or automate a separate browser process for browser work.

## When to use

Use this skill for browser interaction requests, including navigation, clicking, form filling, screenshots, data extraction, website testing, login flows, and browser workflow automation.

## Help

Run `dev-browser --help` to learn the current CLI syntax.

Before invoking a browser interaction command, make sure the exact command form is known. If the syntax is unclear, read `dev-browser --help` first. Do not guess subcommands, flags, or argument order.

## Connection rules

Follow this protocol for every browser task:

1. Treat `--connect` as the required connection to the already running browser process.
2. Confirm the concrete `dev-browser` usage before calling an interaction command.
3. Run browser interaction commands as `dev-browser --connect ...`.
4. If `dev-browser --connect ...` cannot complete the task, stop and report the blocker instead of opening another browser.

## Browser command pattern

The only allowed browser automation command pattern is:

```sh
dev-browser --connect ...
```

## Forbidden actions

- Do not run browser interactions with `dev-browser` unless the command includes `--connect`.
- Do not run browser interactions before the concrete command syntax is known.
- Do not start, launch, install, or open any separate browser process.
- Do not use `google-chrome`, `chrome`, `chromium`, `chromium-browser`, `firefox`, Playwright, Selenium, or any equivalent launcher to create a new browser session.
- Do not work around a failed connection by starting a new browser.

## Screenshots

- Generally, screenshots are not required unless explicitly requested by the user.
