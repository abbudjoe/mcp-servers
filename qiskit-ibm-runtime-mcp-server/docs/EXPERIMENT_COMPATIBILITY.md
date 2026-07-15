<!--
This code is part of Qiskit.

(C) Copyright IBM 2026.

This code is licensed under the Apache License, Version 2.0. You may
obtain a copy of this license in the LICENSE file in the root directory
of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
-->

# Experiment Compatibility — Runtime Research 0.7.3

This document is the Workstream 2 handoff contract for the immutable
`runtime-research-v0.7.3` release.

## Exact dependency pin

Use this PEP 508 requirement; do not depend on a branch:

```text
qiskit-ibm-runtime-mcp-server @ git+https://github.com/abbudjoe/mcp-servers.git@runtime-research-v0.7.3#subdirectory=qiskit-ibm-runtime-mcp-server
```

Expected installed distribution/version:
`qiskit-ibm-runtime-mcp-server==0.7.3`.

## Runtime environment

- Supported Python: 3.10–3.14.
- Canonical release/test interpreter: Python 3.12.
- Canonical locked stack: Qiskit 2.4.2, qiskit-ibm-runtime 0.45.1,
  FastMCP 3.4.4, NumPy 2.4.6 on Python 3.11+.
- Required for provider operations:
  `QISKIT_IBM_RUNTIME_MCP_INSTANCE`.
- Credential source: `QISKIT_IBM_TOKEN` or existing saved Qiskit credentials.
- Artifact storage is caller-owned; use a durable private path with
  `LocalArtifactCAS` and persist returned references.

## Import paths

Import stable research contracts from
`qiskit_ibm_runtime_mcp_server.core`. Use
`qiskit_ibm_runtime_mcp_server.core.schemas` for schema generation/export.
`qiskit_ibm_runtime_mcp_server.ibm_runtime` contains MCP adapters and deprecated
compatibility shims, not the experiment execution contract.

## Schema contract

- Result schema: `PrimitiveResultEnvelope` version `1.0`.
- Submission plan schema: `SubmissionPlan` version `1.0`.
- Budget policy schema: `BudgetPolicy` version `1.0`.
- Approval schema: `ApprovalReceipt` version `1.0`.
- Batch and usage schemas: version `1.0`.
- Crash recovery schemas: `RecoveredJobReceipt` and `SubmissionRecovery`
  version `1.0`.
- Estimation method/version: `qiskit-schedule-estimate` / `1.0`.

Validate persisted documents against the packaged draft 2020-12 schemas. Keep
package version and schema version as separate provenance fields.

## Snapshot identity

`BackendSnapshot` continues to serialize the complete typed `backend_status`
observation. `snapshot_content_hash` excludes that observation and
`retrieved_at`, so queue movement, temporary availability, and status text do
not invalidate unchanged target/calibration identity. Target structure,
calibration data, historical-property time, and software/backend provenance
remain hash-bound.

Do not reuse a snapshot hash, plan, or approval created by 0.7.2 with 0.7.3.
Preserve the old artifacts under their exact release pin, then perform a fresh
metadata resolution, plan generation, and approval cycle.

## Supported execution modes

- Circuit boundary: `exact`, `validate`, `transpile`.
- Primitive: SamplerV2 and EstimatorV2 ordered PUB jobs.
- Runtime mode: bounded Batch lifecycle with partitioned submission.
- Planning: deterministic, non-submitting dry run.
- Live execution: matching approval receipt plus `ApprovedBatchExecutor` only.
- Result storage: inline JSON below threshold, content-addressed artifacts above
  threshold, including large Runtime execution-span masks.

Direct Sampler/Estimator MCP tools are non-submitting compatibility stubs and
must not be used by Workstream 2.

Persist every canonical `SubmissionPlan` before calling the approved execution
boundary. After a crash, call
`recover_jobs_by_submission_key(plan.submission_key, plan)`. Accept only its
typed plan-ordered identities and required wrapper-tagged `submitted_at`; never
reconstruct a receipt from `SubmissionKeyStatus.tags` or nullable provider
`creation_date`. The required time is the wrapper's UTC pre-submit lower bound;
optional `provider_created_at` is corroboration. Runtime tags are mutable by
provider-account writers, so constrain write access and persist recovered
receipts immediately.

## Known limitations

- Schedule-derived QPU estimates are workload-intent bounds, not predictors of
  Runtime minimum/accounted quantum seconds. Approval caps must leave margin.
- Result artifact locators are local-CAS URIs; moving an experiment requires an
  explicit artifact-copy/verification step.
- The release smoke did not exercise ZNE, PEC, twirling, dynamical decoupling,
  measurement mitigation, or a scientific hypothesis.
- Read-only network integration tests are separately gated and are not part of
  ordinary tokenless CI.

## QPU smoke evidence

W1-09 used the explicit Open/free instance and `ibm_marrakesh`. One two-PUB
SamplerV2 job and one separate-observable EstimatorV2 job completed with ordered
shapes matching the version 1.0 contracts. Provider-accounted usage was 2.0
seconds per job, 4.0 seconds total, against a 60-second aggregate approval cap.
No scientific claim was made. No additional QPU run was used for this release.

Provider identities and evidence hashes are recorded in
`docs/runtime-research/live-contract-smoke-report.md` in the tagged repository.
