<!--
This code is part of Qiskit.

(C) Copyright IBM 2026.

This code is licensed under the Apache License, Version 2.0. You may
obtain a copy of this license in the LICENSE file in the root directory
of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
-->

# Changelog

All notable changes to `qiskit-ibm-runtime-mcp-server` are documented here.
Package versions and JSON wire-schema versions are independent.

## 0.7.2 — 2026-07-14

### Fixed

- Replaced unsafe restart inventory with plan-bound `SubmissionRecovery` and
  `RecoveredJobReceipt` contracts. Crash recovery now requires the exact
  persisted `SubmissionPlan`, validates its canonical hash and every remote
  identity tag, restores ordered plan/partition/PUB/job identity, and returns a
  required wrapper-owned UTC pre-submit timestamp. Nullable provider
  `creation_date` is retained only as optional corroboration.
- Added fail-closed checks for submission-key drift, caller spoofing of reserved
  tags, missing or contradictory recovery tags, duplicate/gapped partitions,
  duplicate job IDs, jobs spanning multiple Runtime batches, and the provider's
  eight-tag limit.

### Compatibility

- Jobs submitted by 0.7.0 or 0.7.1 do not contain the new wrapper submission-time
  tag and therefore cannot satisfy typed crash recovery in 0.7.2. Preserve their
  original local receipts; do not infer missing timestamps from nullable provider
  metadata.
- Added `RecoveredJobReceipt` and `SubmissionRecovery` schemas at wire-schema
  version `1.0`; existing 1.0 schemas remain available.

## 0.7.1 — 2026-07-14

### Changed

- Added behavior-focused regressions and an enforced per-module branch-coverage
  gate for budgeting, approval consumption, primitive parsing, and secret
  handling. Each safety-critical module must remain at or above 90% branch
  coverage on every supported Python version.
- Replaced workstream-specific test fixture identifiers with generic contract
  names. Runtime APIs and wire-schema version `1.0` are unchanged from 0.7.0.

## 0.7.0 — 2026-07-14

### Added

- Versioned typed contracts and draft 2020-12 schemas for circuits, snapshots,
  Primitive V2 PUBs/results, batches, plans, budgets, approvals, and usage.
- Secure local content-addressed artifact storage with configurable inlining.
- Complete backend snapshots, historical calibration lookup, target fingerprints,
  and explicit fractional-gate mode.
- Exact/validate/transpile circuit modes with hard input limits and ISA checks.
- Complete ordered SamplerV2 and EstimatorV2 PUB/result preservation.
- Batch lifecycle, deterministic idempotency, recovery, and immutable receipts.
- Deterministic dry-run planning, budget policy, one-time approval consumption,
  provider identity validation, and actual-usage reconciliation.

### Changed

- Runtime operations require an explicit instance.
- Research credentials are environment/saved-account inputs only; MCP token and
  credential-mutation surfaces were removed.
- Primitive results use versioned envelopes and artifact references instead of
  lossy flattened counts/value responses.
- Large Runtime execution-span masks honor the result artifact threshold.

### Deprecated

- Direct Sampler/Estimator MCP submission tools remain discoverable only as
  non-submitting compatibility stubs. Use the plan/approval execution API.

### Compatibility

- Python: 3.10–3.14; canonical release evidence: Python 3.12.
- Wire schemas: `1.0`.
- Canonical stack: Qiskit 2.4.2, qiskit-ibm-runtime 0.45.1, FastMCP 3.4.4.
