<!--
This code is part of Qiskit.

(C) Copyright IBM 2026.

This code is licensed under the Apache License, Version 2.0. You may
obtain a copy of this license in the LICENSE file in the root directory
of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
-->

# Runtime Research API 0.7.0

The supported Python contract lives under
`qiskit_ibm_runtime_mcp_server.core`. Private names and the unchecked primitive
submission helpers are not API.

## Circuits and artifacts

- `ArtifactSink`, `LocalArtifactCAS`, `ArtifactRef`, `artifactize`
- `CircuitLimits`, `ingest_circuit`, `load_circuit_artifact`
- `apply_circuit_mode`, `validate_circuit_isa`, `target_fingerprint`
- `CircuitArtifact`, `CircuitProvenance`, `CircuitValidationReport`

`ingest_circuit` accepts an explicit `qpy` or `qasm3` format, applies decoded
size and structural limits before use, and binds metadata to immutable bytes.
Modes `exact` and `validate` do not invoke a pass manager.

## Backend snapshots

- `build_backend_snapshot`, `resolve_backend_snapshot`
- `snapshot_content_hash`, `target_content_hash`
- `BackendSnapshot`, `FractionalGateMode`

Snapshots include requested qubits, instruction/qubit tuples, properties,
faults, target structure, timestamps, and package provenance. Historical reads
require timezone-aware timestamps.

## Primitive V2 contracts

- `SamplerPubSpec`, `EstimatorPubSpec`, `ParameterBindings`
- `PauliObservables`, `SparsePauliHamiltonian`
- `prepare_sampler_pubs`, `prepare_estimator_pubs`
- `parse_primitive_result`, `PrimitiveResultEnvelope`

PUB IDs and shapes are explicit and ordered. Separate observables remain
separate; a weighted Hamiltonian remains one operator. Results preserve every
PUB, Sampler register, Estimator value/error array, metadata field, and unknown
DataBin extension. Large values and execution-span masks become `ArtifactRef`s.

## Batch lifecycle and recovery

- `BatchLifecycle`, `BatchExecutionLimits`, `plan_batch_partitions`
- `SubmissionReceiptRegistry`, `BatchSubmissionReceipt`
- `RecoveredSubmissionStatus`, `SubmissionKeyStatus`

Submission keys are deterministic and receipts immutable. Reusing the same key
cannot create another live submission unless an explicit duplicate policy says
otherwise. Provider job tags are bounded before submission.

## Planning, budget, and approval

- `SubmissionRequest`, `SubmissionPlanner`, `SubmissionPlan`
- `BudgetPolicy`, `budget_policy_hash`, `submission_plan_hash`
- `ApprovalReceipt`, `create_approval_receipt`, `validate_approval`
- `ApprovedBatchExecutor`, `ApprovedSubmissionStep`
- `UsageReconciliation`, `require_fully_submitted`

The planner resolves the exact instance/backend/target, execution options, PUB
shapes, partitions, and schedule-derived QPU estimate without submitting. The
executor accepts only a valid, unexpired, matching approval and revalidates
provider identity immediately before the primitive call. Ordered execution
stops on the first failed or empty receipt.

## JSON schemas

`qiskit_ibm_runtime_mcp_server.core.schemas` provides:

- `generated_schemas()` for deterministic in-memory schemas;
- `schemas_directory()` for packaged checked-in schemas;
- `export_json_schemas(destination)` for explicit export.

All 0.7.0 public models use schema version `1.0` and JSON Schema draft 2020-12.

## MCP surface

The MCP server exposes metadata discovery, snapshot, job status/result,
cancellation, account/instance/usage inspection, and circuit resources.
`run_sampler_tool` and `run_estimator_tool` are deprecated non-submitting stubs;
the approved plan/Batch API is intentionally a Python control-plane boundary.
