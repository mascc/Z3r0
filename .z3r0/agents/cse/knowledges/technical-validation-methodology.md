---
name: technical-validation-methodology
description: Foundational red-team engineering methodology for vulnerability probing, code audit, attack validation, authorized persistence, remediation, and verification.
---

# Red-Team Engineering Methodology

- Define the technical hypothesis before testing: condition, target, expected signal, disproof condition, stop condition.
- Confirm scope, authorization, environment, account context, data rules, and impact limit before active validation.
- Inspect before acting; prefer minimal, reversible, observable tests for vulnerability probing and discovery.
- Establish baseline behavior before changing inputs or state.
- Validate one variable at a time; avoid exploit chaining until each condition is understood and authorized.
- Code audit must identify source, sink, trust boundary, exploit precondition, affected path, and root cause.
- Attack validation must prove capability with the least sensitive evidence and minimum operational change.
- Authorized persistence must be reversible, time-bounded, documented, monitored, and removed or handed off at stop condition.
- Preserve stability: no destructive payloads, uncontrolled persistence, data modification, excessive concurrency, or uncontrolled breadth.
- Use the least sensitive evidence that proves or disproves the condition.
- Classify precisely: negative, informational, suspected, confirmed, blocked, out of scope.
- Tie impact only to demonstrated capability and reachable data or function.
- Remediation must address root cause, preserve intended behavior, and include focused verification.
- Record target, scope basis, hypothesis, method, evidence, environment, observed effect, classification, confidence, residual risk.
