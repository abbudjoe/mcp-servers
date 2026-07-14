# W1-07 Runtime Batch Lifecycle and Idempotent Receipts

## Outcome

W1-07 adds a typed, MCP-independent Runtime Batch control plane in
`core/batches.py`. It contains no experiment retry policy, randomization,
campaign database, scientific stop rule, or live-test path.

The implementation supports:

- explicit backend Batch creation and existing-Batch reattachment;
- deterministic ordered partition planning;
- bounded SamplerV2 and EstimatorV2 partition submission;
- explicit close, status, Batch-job listing, and usage retrieval;
- immutable submission, partial-failure, and recovery contracts;
- deterministic idempotency keys backed by atomic in-process reservations and
  restart-visible Runtime job tags.

## Source contract

The locked SDK surface is Qiskit Runtime 0.45.1:

- `Batch(backend: BackendV2, max_time=...)` creates a Batch;
- `Batch.from_id(batch_id, service)` reattaches;
- primitives receive the Batch through `mode=batch`;
- `Batch.close()`, `status()`, `details()`, and `usage()` own lifecycle metadata;
- `QiskitRuntimeService.jobs(session_id=...)` lists Batch jobs;
- Primitive V2 options accept integer `max_execution_time` and environment job
  tags.

The hard model ceilings are 10,800 seconds for one job and 28,800 seconds for a
Batch. The caller must choose an instance-specific Batch TTL no greater than the
hard ceiling. The provider's effective `details().max_time` is recorded after
creation, so an Open-plan or other lower cap cannot be mistaken for the requested
TTL. The provider-defined interactive TTL is 60 seconds and is the default safety
margin; callers may select a larger or smaller non-negative margin while leaving
positive usable TTL.

References:

- [IBM Runtime maximum execution time](https://quantum.cloud.ibm.com/docs/en/guides/max-execution-time)
- [IBM Runtime Batch guide](https://quantum.cloud.ibm.com/docs/en/guides/run-jobs-batch)
- [QiskitRuntimeService jobs filter](https://quantum.cloud.ibm.com/docs/en/api/qiskit-ibm-runtime/qiskit-runtime-service)

## Partition contract

`plan_batch_partitions()` consumes ordered `PubExecutionEstimate` values and a
frozen `BatchExecutionLimits` policy. It deterministically preserves PUB order
and greedily starts a new job when adding the next PUB would exceed either the
PUB count or the tighter of the estimated-time and execution-time caps.

Planning fails before submission when:

- one PUB exceeds the per-job estimated or execution limit;
- the resulting job count exceeds `max_jobs`;
- aggregate estimated QPU seconds exceed Batch TTL after the configured margin;
- any locked Runtime ceiling is exceeded.

Submission independently revalidates the caller's `SubmissionPlan`, including
exact PUB order, partition totals, instance/backend/Batch ownership, the provider
effective TTL, integer SDK timeout semantics, and exact alignment between
`resolved_options.max_execution_time`, plan timeout, and partition timeout.

## Idempotency and receipt contract

Each submission key is validated but never generated implicitly. Its SHA-256 is
attached to every Runtime job as a deterministic tag, together with the complete
plan hash and partition identity. The raw submission key, complete plan hash,
Batch ID, ordered PUB IDs, job IDs, reservation/completion timestamps, and each
job-submission timestamp are retained in `BatchSubmissionReceipt`.

Receipts and every nested receipt object are Pydantic-frozen and contain only
scalar or tuple state, preventing mutation through nested lists or dictionaries.

The default duplicate policy is `reject`:

1. Runtime jobs already visible under the deterministic tag are checked first.
2. A process-global, lock-protected registry atomically reserves the raw key.
3. A repeated reserved, submitted, or remotely live key fails before a second
   primitive call.
4. `allow_if_terminal` and `allow_live` are explicit typed overrides.
5. A key already bound to another plan hash is rejected even under an override.

Runtime does not expose a server-side atomic idempotency token. Therefore the
wrapper guarantees atomic refusal among threads and lifecycle instances in one
process, and detects serial/restart duplicates once their tagged jobs are visible.
It cannot eliminate the narrow race between truly simultaneous independent
processes that both query before either provider job becomes visible. A caller
requiring distributed serialization must own that orchestration boundary; W1-07
does not introduce campaign persistence.

## Partial failure and recovery

Submission stops at the first rejected partition. It does not retry. The returned
receipt is:

- `submitted` when every partition returned a job ID;
- `partial_failure` when at least one earlier partition returned a job ID;
- `failed` when no partition returned a job ID.

Failure evidence identifies the failed partition, redacted exception type/message,
and failure timestamp. Accepted jobs remain immutable in the receipt. Callers can
recover current Batch and job status from the receipt, recover tagged jobs from a
submission key after process-local receipt loss, list all Batch jobs, and retrieve
Batch-wide plus per-job QPU seconds. No recovery API decides whether scientific
work should be retried.

## Fully mocked evidence

`tests/test_batch_lifecycle.py` uses synthetic backends, Batches, primitives, jobs,
services, clocks, and QPY artifacts. Its duplicate evidence includes:

- sequential duplicate refusal with primitive-call count unchanged;
- atomic in-flight reservation refusal;
- live remote duplicate refusal after local registry loss;
- real `JobStatus` terminal-only override for local and remote duplicates;
- explicit `allow_live` override;
- plan-hash binding for reused keys.

The same suite covers every partition limit, provider-effective TTL, create/open,
close/status/jobs/usage, immutable receipts, partial failure, receipt-based status
recovery, tag-based restart recovery, and option/timeout drift.

No IBM token was supplied, no real Batch was created, no primitive was submitted,
and no QPU or paid compute operation occurred.

## Final gates

| Gate | Result |
|---|---|
| W1-07 lifecycle/idempotency suite | 27 passed; all services, Batches, primitives, and jobs mocked |
| Focused W1-07 plus schema contracts | 61 passed |
| Full Runtime package | 322 passed, 1 pre-existing read-only snapshot skip |
| Locked-stack compatibility | 7 passed |
| Static and security | Ruff lint/format, strict mypy (15 source files), Bandit, schema equality, and diff check passed |
| Independent assembly review | First review found three contract gaps; all were fixed and the rereview was clean with every W1-07 item `met` |
