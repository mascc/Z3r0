---
name: dev-browser
description: Browser automation with persistent page state. Use for any browser interaction request, but ONLY by connecting to the already running browser. Before browser work, load this skill. Every dev-browser command MUST include --connect. Starting, launching, installing, or opening another browser process is forbidden. Trigger phrases include "go to [url]", "click on", "fill out the form", "take a screenshot", "scrape", "automate", "test the website", "log into", or any browser interaction request.
---

# Dev Browser

A CLI for controlling the already running browser with sandboxed JavaScript scripts.

## When to use

Use this skill for browser interaction requests, including navigation, clicking, form filling, screenshots, data extraction, website testing, login flows, and browser workflow automation.

## Help

Run `dev-browser --help` to learn more.

Reading help is allowed for CLI discovery. Browser interaction commands still must follow the connection rules below.

## Connection rules

Follow this protocol for every browser task:

1. Connect to the existing browser only.
2. Run browser interaction commands as `dev-browser --connect ...`.
3. If `dev-browser --connect ...` cannot complete the task, stop and report the blocker instead of opening another browser.

## Browser command pattern

The only allowed browser automation command pattern is:

```sh
dev-browser --connect ...
```

## Forbidden actions

- Do not run browser interactions with `dev-browser` unless the command includes `--connect`.
- Do not start, launch, install, or open any separate browser process.
- Do not use `google-chrome`, `chrome`, `chromium`, `chromium-browser`, `firefox`, Playwright, Selenium, or any equivalent launcher to create a new browser session.
- Do not work around a failed connection by starting a new browser.

## Screenshots

- Generally, screenshots are not required unless explicitly requested by the user.
