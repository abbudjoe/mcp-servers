<!--
This code is part of Qiskit.

(C) Copyright IBM 2026.

This code is licensed under the Apache License, Version 2.0. You may
obtain a copy of this license in the LICENSE file in the root directory
of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
-->

# Migrating from 0.6.x

The next release intentionally breaks implicit live-execution and flattened-result
contracts. Migrate the control plane before moving experiment code.

## Crash recovery

Persist the exact canonical `SubmissionPlan` before live submission. After a
process crash, pass that plan back to the recovery boundary:

```python
recovery = lifecycle.recover_jobs_by_submission_key(
    plan.submission_key,
    plan,
)
```

The returned `SubmissionRecovery` contains typed `RecoveredJobReceipt` values
ordered by the plan. Each job carries `plan_id`, `plan_hash`, primitive,
`batch_id`, `partition_id`, ordered `pub_ids`, `job_id`, status, and a required
`submitted_at` sourced from the wrapper's pre-submit job tag. Remote job
existence proves the provider accepted the call after that lower-bound time.
Optional `provider_created_at` preserves the SDK's nullable `creation_date` as
corroboration only. Treat `complete` as a fully reconstructed accepted partition
set, `partial` as an accepted prefix, and `not_found` as no visible accepted job.

Recovery fails closed when the plan hash is stale, the recovery key differs
from the plan, tags are missing or contradictory, partitions are duplicated or
gapped, Batch identity differs, or the timestamp tag is invalid. The legacy
`SubmissionKeyStatus` model is provider inventory only and must not be used to
construct receipts.

Jobs submitted before the wrapper submission-time tag was introduced cannot
satisfy this contract. Keep their original `BatchSubmissionReceipt`; recovery
intentionally refuses to invent a receipt timestamp from nullable
`creation_date` metadata.

Runtime job tags are mutable by principals with write access to the same IBM
Quantum account. Recovery detects missing, duplicate, and contradictory wrapper
tags but is not a cryptographic attestation against a malicious account writer.
Keep provider write access constrained and persist the returned immutable
receipt immediately whenever the original process survives.

## Authentication and instance ownership

- Remove tokens from MCP arguments and application manifests.
- Set `QISKIT_IBM_RUNTIME_MCP_INSTANCE` to the one intended instance.
- Supply `QISKIT_IBM_TOKEN` through the environment, or use existing saved
  Qiskit credentials. The server will not create, overwrite, or delete them.

## Submission

Do not call `run_sampler_tool`, `run_estimator_tool`, `run_sampler`, or
`run_estimator` to submit work. They are non-submitting compatibility stubs.

The replacement sequence is:

1. Store and validate an exact circuit with `LocalArtifactCAS` and
   `ingest_circuit`.
2. Construct ordered `SamplerPubSpec` or `EstimatorPubSpec` values.
3. Create a `BudgetPolicy` and use `SubmissionPlanner` to resolve the exact
   instance, backend, options, shapes, partitions, and QPU estimate.
4. Persist and human-review the immutable plan hash.
5. Create a matching, expiring `ApprovalReceipt` with explicit instance/backend
   allowlists and a QPU-second cap.
6. Submit only through `ApprovedBatchExecutor`; persist its immutable receipts.
7. Retrieve results with explicit primitive, PUB identities, and PUB shapes.

Approval receipts are one-time capabilities. Changing any execution-relevant
plan field changes the plan hash and requires a new approval.

## Circuit inputs

- Choose `qpy` or `qasm3` explicitly; format guessing is not part of the core API.
- QPY must contain exactly one circuit.
- `exact` and `validate` never transpile. `validate` checks the target instruction
  and qubit tuples without changing the circuit. Use `transpile` explicitly when
  transformation is intended.
- Preserve the returned circuit hash, writer version, layout, parameters, and
  provenance with the experiment record.

## Results and artifacts

`get_job_results` now returns a `PrimitiveResultEnvelope` when primitive and PUB
identity are supplied. Consume every `pub_results` entry in order. Sampler
registers, Estimator arrays/errors, unknown DataBin fields, job/PUB metadata,
and usage are retained.

Payloads at or above the configured threshold may be `ArtifactRef` objects.
Resolve them through the same `ArtifactSink`; do not assume every value is
inline. Runtime execution-span masks follow this rule in the next release.

## Schemas

The next package release uses wire-schema version `1.0`. Validate persisted inputs at
ingress and preserve unknown extension fields. Package upgrades do not imply a
schema upgrade, and schema upgrades require separate compatibility review.
