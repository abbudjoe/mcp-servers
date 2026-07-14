<!--
This code is part of Qiskit.

(C) Copyright IBM 2026.

This code is licensed under the Apache License, Version 2.0. You may
obtain a copy of this license in the LICENSE file in the root directory
of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
-->

# W1-09 Live Runtime Contract Smoke Report

## Outcome

W1-09 completed successfully as a wrapper-contract smoke on the explicit
Open/free instance and `ibm_marrakesh`. One two-PUB SamplerV2 job and one
separate-observable EstimatorV2 job completed. Their ordered result shapes,
metadata, DataBin fields, provider usage, and typed wrapper envelopes were
persisted. No scientific inference is made from the returned values.

Submission release candidate:
`d5aced961e53e2a932ddba2a7c33c58ed643f878`.

Post-live metadata-contract fix:
`6682faef72e35e0211ba267ef9f21b229699d39c`.

## Approved immutable contract

| Primitive | Plan hash | Estimated QPU seconds | Approved cap | Treatments |
|---|---|---:|---:|---|
| Sampler | `sha256:613c82a609b07f1f1b54629424ab78619db1a39a39a8d4fb95b4fd89015d0174` | 0.096 | 30 | none |
| Estimator | `sha256:3e68678e000655892842fa9b51ba76791fb5277ab66c916fb229cf65d67ab7ec` | 0.2 | 30 | none |
| Aggregate | n/a | 0.296 | 60 | none |

Paid fallback was disabled. Dynamical decoupling, gate and measurement
twirling, ZNE, PEC, and measurement mitigation were disabled. Both plans used
`max_execution_time=30`; the Batch maximum time was 120 seconds.

## Provider identities

- Batch: `e8ae2ce9-1e0b-4ba3-bcf8-38d360908ee1`
- Sampler job: `d9b7ks6g26ic73dfjk8g`
- Estimator job: `d9b7ksug26ic73dfjk9g`
- Backend: `ibm_marrakesh`, 156 qubits
- Instance: explicit `open` / `free` provider record
- Final Batch state after submission: not accepting new jobs
- Final job states: `DONE`, `DONE`

## Live shapes and fields

| Primitive / PUB | Planned shape | Live DataBin shape | Live fields |
|---|---|---|---|
| Sampler `sampler-scalar` | `[]` | `[]` | register `c`: BitArray, 32 shots, 1 bit |
| Sampler `sampler-vector` | `[2]` | `[2]` | register `c`: BitArray, 32 shots, 1 bit |
| Estimator `estimator-separate-observables` | `[2]` | `[2]` | `evs`, `stds`, `ensemble_standard_error` |

Every public PUB DataBin field and PUB/job metadata field was retained. Sampler
packed bytes, counts, bitstrings, and quasi distributions, and Estimator values
and error arrays were written to the private content-addressed store with
threshold zero. The result envelopes retain the corresponding artifact IDs,
sizes, media types, shapes, and dtypes.

The live envelope top-level keys and primitive-specific PUB keys match the
checked-in W1-06 golden contracts. The planned and observed shapes match
exactly. No golden fixture update is required: provider timestamps, execution
spans, and numerical results are live evidence rather than deterministic golden
constants; fixture-only matrix and future-extension cases remain unit coverage.

## Usage reconciliation

| Primitive | Estimate | Provider actual | Cap | Actual / estimate |
|---|---:|---:|---:|---:|
| Sampler | 0.096 s | 2.0 s | 30 s | 20.83x |
| Estimator | 0.2 s | 2.0 s | 30 s | 10.00x |
| Aggregate | 0.296 s | 4.0 s | 60 s | 13.51x |

Batch usage, per-job metrics, wrapper reconciliation, and instance usage agree:
four seconds consumed and 596 of 600 Open-plan seconds remaining. Actual usage
is safely within every approved cap, but the schedule-based estimate materially
underpredicts provider-accounted quantum time for these tiny jobs. The estimate
is therefore a preflight bound for workload intent, not a predictor of Runtime's
minimum/accounted quantum seconds.

## Evidence and hashes

Private evidence root:
`/Users/joseph/.qiskit/w1-09-contract-smoke/d5aced9`.

| Artifact | SHA-256 |
|---|---|
| `owner-approval-v3.json` | `11c92c196cac2c77d3f36b3caf28a1fd5538e59385a7e55fde52b8735e98a191` |
| `batch-reference-v3.json` | `f760911c25eb162aaa2364a2c0f9c5aa3c7283f98d3262c8e674a3d4a029327b` |
| `live-submissions-v3.json` | `39f9f856e6ce1c2da2922856f6af0a8307aa602eae48b0b97d17f9cd5be0947b` |
| `sampler-result-envelope-v3.json` | `fcb8e4e725a462fc60788d40b3dff7ccd2879395a7ecbe9c9cd79e89dc64a6f7` |
| `estimator-result-envelope-v3.json` | `023704f604974713458f8fbf154b39829507531ea7fb4acb22f4d93a673d0eaf` |
| `job-provider-evidence-v3.json` | `6c230e5c186bd9cfc8557c2bac439bf917f245ef772dac07e6190e6b60f08124` |
| `usage-reconciliation-v3.json` | `1992db1ff1506bdd5328fb9c188b0eca2e7982882d6cb4fb6cd36fa484f90180` |
| `golden-shape-comparison-v3.json` | `aab72dc7271fdd3271be7fac9f36238aab150ad62e0bb74ffdcaa26f12692b35` |
| `live-result-manifest-v3.json` | `61388a52eaf9232b5bf5ed5d9186c3e5d52c96f3d41cbc99ed9fae797f22637d` |

## Limitations and live findings

1. Attempt 1 created no jobs and consumed zero QPU seconds. It exposed IBM's
   86-character job-tag limit; the wrapper now enforces that limit before the
   primitive call.
2. The attempt-1 harness continued after a typed failed Sampler receipt. The
   production `submit_in_order()` path now blocks the next primitive unless the
   preceding receipt is fully submitted with a nonempty job list.
3. Live Sampler job metadata contained Qiskit Runtime `ExecutionSpans`, which
   the previous generic JSON boundary rejected. The post-live fix serializes
   the complete public span timing, PUB indices, types, sizes, ordering, and
   dependency masks; the completed provider result was then parsed without a
   new QPU submission.
4. The live RC materialized execution-span masks inline. Release hardening commit
   `d6de645` resolved this finding: masks now honor the configured artifact
   threshold while span timing, PUB indices, ordering, types, and sizes remain
   visible in metadata.
5. The configured documentation-server test suite deselected three integration
   cases. All 921 selected preflight outcomes completed with zero failures or
   errors; the post-live Runtime suite completed with 357 passed and one skip.
6. This smoke validates wrapper and provider contracts only. It is not an
   experiment campaign and does not test ZNE, PEC, twirling, DD, or a scientific
   hypothesis.
