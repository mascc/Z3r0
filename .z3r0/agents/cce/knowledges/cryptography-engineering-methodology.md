---
name: cryptography-engineering-methodology
description: Cryptography engineering methodology for scoped cryptographic design review, protocol analysis, key-management assessment, implementation review, vulnerability discovery, controlled proof, and reporting.
---

# Cryptography Engineering Methodology

- Confirm objective, scope, authorization basis, artifact or system boundary, data sensitivity, permitted tooling, disclosure constraints, cleanup duties, and stop conditions before analysis.
- Build a cryptographic asset model covering protected data, trust boundaries, threat actors, secrets, keys, certificates, tokens, algorithms, protocols, endpoints, storage, rotation paths, and failure modes.
- Separate cryptographic goals explicitly: confidentiality, integrity, authenticity, freshness, non-repudiation, unlinkability, forward secrecy, key separation, misuse resistance, and recovery.
- Inventory primitives and parameters with exact algorithm, mode, curve, padding, digest, tag length, nonce or IV rules, salt size, KDF settings, randomness source, library version, and protocol version.
- Trace key lifecycle from generation, entropy source, derivation, exchange, wrapping, storage, access control, use context, rotation, revocation, backup, destruction, and incident recovery.
- Convert observations into cryptographic hypotheses with target component, suspected misuse or weakness, precondition, expected signal, disproof condition, exploitability limit, and risk note.
- Prioritize review by data sensitivity, exposed attack surface, key reuse, custom cryptography, legacy primitives, unauthenticated encryption, nonce control, padding behavior, downgrade path, and validation cost.
- For protocol review, reason across handshake state, authentication binding, transcript integrity, replay resistance, downgrade resistance, channel binding, identity validation, and error behavior.
- For token and signature schemes, reason across canonicalization, algorithm confusion, key confusion, audience and issuer binding, expiry, replay, nonce use, detached content, and verification strictness.
- For password and secret handling, reason across hashing or KDF choice, work factor, salt uniqueness, pepper handling, online throttling, reset flows, storage exposure, and migration path.
- For implementation review, trace source, sink, key material handling, error paths, constant-time requirements, randomness calls, serialization, side effects, dependency assumptions, and test coverage.
- Validate findings one variable at a time with minimal, reversible, observable actions; separate design weakness, implementation defect, exploit precondition, practical impact, and confidence.
- Treat cryptanalytic claims conservatively: distinguish known broken primitives, unsafe constructions, parameter weakness, side-channel risk, and theoretical attacks from practical exploitability.
- Controlled proof should demonstrate capability with least-sensitive evidence, deterministic reproduction where possible, minimum state change, bounded execution, clear timestamps, and verification artifacts.
- Report each result with scope basis, cryptographic goal affected, primitive or protocol context, root cause, evidence, exploit conditions, impact, limitations, remediation guidance, confidence, and verification steps.
