<!--
This code is part of Qiskit.

(C) Copyright IBM 2026.

This code is licensed under the Apache License, Version 2.0. You may
obtain a copy of this license in the LICENSE file in the root directory
of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
-->

# W1-09 Assembly Ledger

## Control plane

- Item: W1-09 — Generic Live QPU Contract Smoke
- Authoritative spec:
  `qiskit_wrapper_workstream_build_package/prompts/W1-09_GENERIC_QPU_SMOKE.md`
- Supporting contracts: `04_DEFINITIONS_OF_DONE.md`,
  `07_BUDGET_AND_LIVE_EXECUTION_POLICY.md`, and
  `docs/runtime-research/w1-08-budget-approval.md`
- Release candidate: `d5aced961e53e2a932ddba2a7c33c58ed643f878`
- Root `uv.lock` SHA-256:
  `08d742daad084ae27e0a22c6b63e0597c0dbfd8fccff67fadea5344495df704e`
- Status: `successful`
- Scope: Runtime wrapper contract validation only; no scientific hypothesis or
  experiment campaign

## Consumed attempt-1 live contract

- Instance: explicit provider-validated Open/free instance
- Backend: `ibm_marrakesh`
- Sampler plan:
  `sha256:4e0fd94279ee696009a30a9358cf9708faba78bc94ede4b66d89f181df6136ac`
- Estimator plan:
  `sha256:57fbc3decff2bb775a35e82cd8b1c1bb111c62991e109e42cd9917c3e7f1c29e`
- Estimated QPU seconds: Sampler `0.096`, Estimator `0.2`, aggregate `0.296`
- Approved caps: Sampler `30`, Estimator `30`, aggregate `60` QPU seconds
- Per-job `max_execution_time`: `30` seconds
- Paid fallback: disabled
- Permitted treatments: none
- Cleanup: close the Batch after both accepted submissions; persist and verify all
  receipts, PUB results, metadata, usage, and report artifacts

The attempt-1 approval receipts are consumed and must not be reused.

## Executed replacement contract

- Backend: `ibm_marrakesh` on the same provider-validated Open/free instance
- Sampler plan:
  `sha256:613c82a609b07f1f1b54629424ab78619db1a39a39a8d4fb95b4fd89015d0174`
- Estimator plan:
  `sha256:3e68678e000655892842fa9b51ba76791fb5277ab66c916fb229cf65d67ab7ec`
- Fresh submission keys: `w1-09/d5aced9/ibm_marrakesh/sampler/v3` and
  `w1-09/d5aced9/ibm_marrakesh/estimator/v3`
- Estimated QPU seconds: Sampler `0.096`, Estimator `0.2`, aggregate `0.296`
- Approved caps: Sampler `30`, Estimator `30`, aggregate `60` QPU seconds
- Paid fallback: disabled; treatments: none
- Approval state: consumed by the guarded live submission

## DoD checklist

| DoD item | Status | Evidence |
|---|---|---|
| Human approves immutable smoke plans and an aggregate cap no greater than 60 QPU seconds. | met | Owner approved both exact `/v3` plan hashes with 30-second per-job and 60-second aggregate caps; matching short-lived receipts were consumed once. |
| Resolved instance is explicitly allowed and Open/non-paid. | met | Immediate provider validation reported `plan=open`, `pricing_type=free`, zero seconds consumed, and 600 seconds remaining before launch; target identities matched both plans. |
| Re-run all tests from the release candidate before submission. | met | On RC `d5aced9`, five isolated workspace runs produced 921 selected outcomes: 916 passed, one skipped, three xfailed, one xpassed, and zero failures/errors. The docs suite discovered and deselected three additional integration cases, for 924 discovered cases. |
| At least one small Sampler and one small Estimator job complete. | met | Batch `e8ae2ce9-1e0b-4ba3-bcf8-38d360908ee1`; Sampler `d9b7ks6g26ic73dfjk8g` and Estimator `d9b7ksug26ic73dfjk9g` both reached `DONE`. |
| Multi-PUB/result shapes are compared with the W1-06 contracts and golden fixtures. | met | Live Sampler shapes `[]`, `[2]` and Estimator shape `[2]` match both immutable plans and golden envelope/PUB schemas; no fixture update is required. |
| Every PUB/result/metadata field and actual usage is retrieved and persisted. | met | Threshold-zero typed envelopes retain every DataBin field and PUB/job metadata field with CAS artifacts; provider job inventories and execution spans are persisted. |
| Actual usage is reconciled against estimate and the aggregate cap. | met | Sampler actual `2.0` vs estimate `0.096`; Estimator actual `2.0` vs estimate `0.2`; aggregate actual `4.0` vs estimate `0.296` and cap `60`. Batch, job, and instance usage agree. |
| No scientific experiment claim is made from smoke data. | met | Scope is explicitly limited to wrapper Runtime contracts. |
| No paid fallback, ZNE, PEC, twirling, or dynamical decoupling is used. | met | Policy and both resolved plans have paid fallback disabled and empty treatment sets. |
| Stop immediately on plan, provider identity, quota, target, or budget mismatch. | met | `ApprovedBatchExecutor.submit_in_order()` now requires `state=submitted` and a nonempty job list after every step. A Sampler-to-Estimator spy regression proves a failed Sampler prevents the Estimator call while preserving typed failure evidence. |
| Independent spec-conformance review is clean. | met | Plan, tag, ordered-submit, live `ExecutionSpans` metadata, final evidence, and report reviews are independently clean; the final reviewer classified every DoD item `met`. |

## Successful live attempt

- Submission RC: `d5aced961e53e2a932ddba2a7c33c58ed643f878`
- Batch: `e8ae2ce9-1e0b-4ba3-bcf8-38d360908ee1`, closed to new jobs
- Sampler: `d9b7ks6g26ic73dfjk8g`, `DONE`, actual `2.0` QPU seconds
- Estimator: `d9b7ksug26ic73dfjk9g`, `DONE`, actual `2.0` QPU seconds
- Aggregate actual: `4.0` QPU seconds; remaining Open quota: `596`
- Shapes: Sampler `[]`, `[2]`; Estimator `[2]`
- Golden comparison: schemas and shapes match; fixtures unchanged
- Live retrieval finding: Runtime `ExecutionSpans` were not JSON-safe. Commit
  `6682faef72e35e0211ba267ef9f21b229699d39c` adds a typed public-field
  representation; post-fix Runtime suite: `357 passed, 1 skipped`
- Report: `docs/runtime-research/live-contract-smoke-report.md`
- Durable archive:
  `/Volumes/Macintosh HD - Data/codex-cloud-artifacts/w1-09-d5aced9-ibm-marrakesh`
- Archive verification: APFS volume UUID
  `8478609D-FA37-4ED5-875D-47AE912B9151`; atomic promotion, file/directory
  `fsync`, independent rehash; 45 files / 263,893 bytes; evidence index
  `sha256:1eb9ef89ca17e1ea6848e07ea3c1919c464619a34cb0f9534cd0ab4d91a77e8a`

## Attempt 1 — provider job-tag rejection

- Batch: `76e83d35-fc69-440b-af16-73d7d5df879d`
- Batch state: closed, never started, accepting no new jobs
- Sampler result: provider HTTP 400 / code 1205 before job creation
- Estimator result: provider HTTP 400 / code 1205 before job creation
- Root cause: `qiskit-mcp-idempotency:<64 hex>` was 87 characters while
  IBM Runtime permits at most 86 characters per job tag
- QPU jobs created: `0`
- Actual QPU usage: `0` seconds; Open-plan quota remains `600` seconds
- Retry policy: no retry under consumed approvals; repair the primitive, test and
  review it, then generate new submission keys, plan hashes, and receipts
- Root-cause repair: explicitly bind every Runtime job tag to the provider's
  86-character limit, retain a 252-bit idempotency digest, and reject oversized
  caller tags before `primitive.run()`
- Focused repair smoke: `28 passed`
- Full Runtime post-repair smoke: `352 passed, 1 skipped`
- Final replacement RC: `d5aced961e53e2a932ddba2a7c33c58ed643f878`
- Final-RC full workspace smoke: 921 selected outcomes, `916` passed, zero
  failures/errors, one skip, three xfails, one xpass; 924 cases were discovered
  including three docs integration cases deselected by the configured default
- Durable attempt-1 archive:
  `/Volumes/Macintosh HD - Data/codex-cloud-artifacts/w1-09-6b1239d-ibm-marrakesh`
- Archive verification: atomic promotion, file and directory `fsync`, independent
  rehash, 33 files / 328,977 bytes; lifecycle ledger corrected and terminated

## Evidence artifacts

Private preflight root:
`/Users/joseph/.qiskit/w1-09-contract-smoke/d5aced9`

- `budget-policy.json`
- `sampler-submission-plan.json`
- `estimator-submission-plan.json`
- `preflight-manifest.json`
- `provider-validation.json`
- `rc-test-summary.json`
- `tests/*.xml`
- `owner-approval-v3.json`
- `sampler-approval-receipt-v3.json`
- `estimator-approval-receipt-v3.json`
- `batch-reference-v3.json`
- `live-submissions-v3.json`
- `sampler-result-envelope-v3.json`
- `estimator-result-envelope-v3.json`
- `job-provider-evidence-v3.json`
- `usage-reconciliation-v3.json`
- `golden-shape-comparison-v3.json`
- `live-result-manifest-v3.json`

Evidence hashes:

- `provider-validation.json`:
  `sha256:164cf321c6d05992d4ddd4d46c6ab0d66927904eca1e3f0348dc76321401d549`
- `rc-test-summary.json`:
  `sha256:c9b3e33fc739e3951c48fac34ce28f859186db92a7294d57235b22877c941e02`

Attempt-1 evidence remains at
`/Users/joseph/.qiskit/w1-09-contract-smoke/6b1239d` and in its durable archive.

The cloud/job lifecycle ledger is
`/Users/joseph/.codex/cloud_runs/ledger.jsonl`.
