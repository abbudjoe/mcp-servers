<!--
This code is part of Qiskit.

(C) Copyright IBM 2026.

This code is licensed under the Apache License, Version 2.0. You may
obtain a copy of this license in the LICENSE file in the root directory
of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
-->

# W1-08 Preflight Budget and Approval Contract

## Public execution boundary

`SubmissionPlanner.resolve()` is the non-submitting dry-run boundary.
`ApprovedBatchExecutor.submit()` is the only public core API that may reach primitive
submission. It accepts a `SubmissionRequest`, not a precomputed `SubmissionPlan`, and calls
the authoritative `RuntimeResourceResolver` again immediately before validation. It then
validates the new plan hash, `BudgetPolicy`, and mandatory `ApprovalReceipt` before calling
the private `BatchLifecycle._submit_resolved_plan()` primitive. Immediately before that call,
it atomically consumes `plan_hash` in a SQLite ledger fixed beneath the same
`LocalArtifactCAS` root. The primary-key transaction is shared across processes, so one plan
and receipt cannot be submitted twice during the provider job-tag visibility window. A crash
after consumption fails conservatively: a fresh plan and approval are required.

Legacy `run_sampler` and `run_estimator` adapters return an error before service
initialization. Raw Primitive V2 submit helpers and direct Batch plan submission are no longer
exported by the public core. There is no `confirm` boolean or equivalent bypass.

## Canonical `SubmissionPlan` field list

The canonical SHA-256 payload is deterministic sorted-key JSON containing every field below
except `plan_hash`, which is the digest of that payload:

1. `schema_version`
2. `plan_id`
3. `submission_key` — deterministic idempotency key bound by approval
4. `policy_hash` — hash of the complete `BudgetPolicy`
5. `instance_id`
6. `instance_plan_type` — `open` or `paid`, from the authoritative resolver
7. `backend_name`
8. `target_hash` — verified `BackendSnapshot.target_hash`
9. `compiler_target_hash` — complete compiler-visible target fingerprint
10. `primitive`
11. `pubs` — ordered complete Sampler/Estimator specs, including PUB IDs, immutable circuit
    artifact/hash metadata, parameter names/shapes/values, observable form/shapes/values,
    shots, and precision
12. `pub_shapes` — ordered parameter, observable, and broadcast result shapes plus exact
    circuit-execution cardinality
13. `resolved_options` — complete locked Runtime options tree; SDK `Unset` values are explicit
    `{"$runtime_default":"Unset"}` sentinels
14. `treatments` — ordered enabled mitigation/suppression treatment names
15. `partitions` — ordered partition IDs, PUB IDs, partition estimates, and per-job maximum
    execution seconds
16. `scheduled_estimates` — ordered scheduled duration, conservative cycle duration,
    broadcast and physical circuit-execution cardinalities, repetitions, treatment multiplier,
    and PUB QPU seconds
17. `total_circuit_executions`
18. `estimated_qpu_seconds`
19. `maximum_execution_seconds`
20. `estimation_method`
21. `estimation_version`
22. `estimation_software_versions`

Any mutation of any field above changes the digest. Live validation recomputes the canonical
hash before inspecting any receipt field, so a stale digest cannot authorize a mutated plan.

## Locked QPU-second estimate

Method `qiskit-alap-critical-path` version `1.0` is qualified against Qiskit 2.4.2 and
Qiskit IBM Runtime 0.45.1. For each PUB it:

1. reloads the immutable circuit bytes and verifies their content hash and declared metadata;
2. validates the exact ISA circuit against the current resolver-owned target without
   transpilation;
3. runs Qiskit's public `ALAPScheduleAnalysis` with `Target.durations()`;
4. computes the critical-path end time from scheduled start times, target `dt`, and instruction
   durations;
5. resolves the backend's authoritative `default_rep_delay`, hashes and passes it explicitly,
   and uses `max(scheduled_seconds + rep_delay, 0.001)` seconds per repetition;
6. multiplies by the exact broadcast circuit-execution count and by Sampler shots or
   `ceil(1 / precision**2)` Estimator repetitions; and
7. applies conservative treatment overhead.

Only treatments with a locked conservative bound are accepted. Gate/measurement twirling
requires explicit randomization and shots-per-randomization counts and charges the randomization
count once. ZNE requires explicit local `gate_folding`, finite factors at least one, and charges
the sum of factors to the entire scheduled cycle (conservatively overcounting measurement and
repetition delay). PEA, dynamical decoupling, resilience presets, measurement-mitigation
calibration, PEC/noise learning, and weighted Hamiltonians fail closed until a locked method can
bound their transformed circuits/calibration work. The plan records the method, version, exact
software versions, physical circuit count, and every per-PUB intermediate.

## Enforcement and reconciliation

Planning and live validation enforce explicit instance/backend allowlists, provider-resolved
paid/open plan type, dual policy-and-receipt paid authorization, primitives, treatments,
maximum PUBs/jobs/shots, estimated QPU seconds, Batch TTL, and per-job
`max_execution_time`, plus explicit maximum physical circuits and partitions. Receipts must
match the re-resolved hash, remain inside the policy TTL,
allow the exact instance/backend, and cap the estimate.

`ApprovedSubmission` returns the estimate, approved cap, immutable plan hash, and partitioned
job receipt. `ApprovedBatchExecutor.reconcile_usage()` returns those same estimate/approval
fields beside the approved submission's summed seconds and exact per-job `quantum_seconds`
values. Other jobs in the same Batch are excluded. The caller owns budget reconciliation and
experiment policy.

## Evidence boundary

All W1-08 tests use Qiskit fake backends, local content-addressed artifacts, synthetic
resolvers, recording lifecycle objects, and mocked Runtime jobs. No Runtime service, Batch,
primitive, paid instance, or QPU was created or mutated. Approval replay coverage uses two
independent SQLite connections contending for the same durable plan-hash key.
