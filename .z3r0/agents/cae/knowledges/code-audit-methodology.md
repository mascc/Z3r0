---
name: code-audit-methodology
description: Code audit methodology for source review, data-flow analysis, dependency and configuration review, vulnerability triage, and remediation verification.
---

# Code Audit Methodology

- Start by defining audit scope: repository path, branch or commit, language stack, framework, trust boundaries, entry points, privileged operations, sensitive data, and expected deployment model.
- Build an attack-surface map from routes, controllers, handlers, jobs, CLI commands, deserializers, webhooks, parsers, upload paths, authentication middleware, authorization checks, storage calls, and outbound requests.
- Trace data flow from untrusted sources to sensitive sinks: SQL/NoSQL queries, command execution, template rendering, file paths, SSRF-capable clients, deserialization, dynamic evaluation, redirects, logging, and secret use.
- Review authorization as a separate control plane: identity source, session state, tenant boundary, object ownership, role checks, default-deny behavior, bypass paths, and confused-deputy risks.
- Check authentication and session code for credential handling, password reset, MFA, token lifetime, cookie flags, CSRF protection, replay resistance, account recovery, and lockout or throttling behavior.
- Inspect dependency and supply-chain posture through manifest files, lockfiles, build scripts, vendored code, package sources, postinstall hooks, known vulnerable versions, abandoned packages, and integrity controls.
- Review configuration and deployment artifacts: environment defaults, Dockerfiles, compose files, CI/CD workflows, IaC, exposed ports, debug flags, CORS, CSP, secret injection, logging, and production hardening.
- Treat secret findings carefully: record exact location and evidence, avoid unnecessary disclosure, distinguish test fixtures from live secrets, and recommend rotation when exposure is plausible.
- Validate suspected findings with the least invasive evidence available: reachable code path, controllable input, missing guard, affected sink, exploit preconditions, impact, and false-positive counterchecks.
- Separate confirmed vulnerabilities, plausible risks, hardening recommendations, and unresolved questions. Do not promote a lead to a finding without code evidence and a clear exploit or abuse path.
- For remediation review, verify the patch at the source and sink, check regression coverage, search for sibling patterns, and confirm the fix does not only block one payload or one route.
- Report findings with file path, function or route, vulnerable flow, evidence, impact, prerequisites, confidence, remediation guidance, and verification steps.
