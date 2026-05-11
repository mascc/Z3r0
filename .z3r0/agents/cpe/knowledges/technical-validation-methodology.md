---
name: technical-validation-methodology
description: Foundational penetration-engineering methodology for exposure validation, vulnerability probing, controlled exploitation, authorized post-exploitation, remediation, and verification.
---

# Penetration Engineering Methodology

- Define the technical hypothesis before testing: condition, target, expected signal, disproof condition, stop condition.
- Confirm scope, authorization, environment, account context, data rules, impact limit, persistence rules, cleanup rules, and stop condition before active validation.
- Start from exposed surface and intelligence evidence; inspect before acting.
- Prefer minimal, reversible, observable tests for vulnerability probing and discovery.
- Establish baseline behavior before changing inputs or state.
- Validate one variable at a time; avoid exploit chaining until each condition is understood and authorized.
- Code audit must identify source, sink, trust boundary, exploit precondition, affected path, and root cause.
- Controlled exploitation must prove capability with the least sensitive evidence and minimum operational change.
- Authorized post-exploitation must stay bounded to the stated objective, avoid unnecessary data access, and document each material action.
- Authorized persistence must be reversible, time-bounded, documented, monitored, and removed or handed off at stop condition.
- Cleanup should remove or restore test artifacts created by the authorized work and record what changed.
- Preserve stability: no destructive payloads, uncontrolled persistence, data modification, excessive concurrency, or uncontrolled breadth.
- Use the least sensitive evidence that proves or disproves the condition.
- Classify precisely: negative, informational, suspected, confirmed, blocked, out of scope.
- Tie impact only to demonstrated capability and reachable data or function.
- Remediation must address root cause, preserve intended behavior, and include focused verification.
- Record target, scope basis, hypothesis, method, evidence, environment, observed effect, classification, confidence, cleanup, and residual risk.
