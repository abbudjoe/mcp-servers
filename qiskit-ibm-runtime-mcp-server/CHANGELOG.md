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

## Unreleased

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
- Runtime credentials are environment/saved-account inputs only; MCP token and
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
