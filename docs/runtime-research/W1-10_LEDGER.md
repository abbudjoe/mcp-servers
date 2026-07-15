<!--
This code is part of Qiskit.

(C) Copyright IBM 2026.

This code is licensed under the Apache License, Version 2.0. You may
obtain a copy of this license in the LICENSE file in the root directory
of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
-->

# W1-10 Assembly Ledger

## Control plane

- Item: W1-10 — Release and Upstream PR Series
- Authoritative spec:
  `qiskit_wrapper_workstream_build_package/prompts/W1-10_RELEASE_UPSTREAM.md`
- Supporting contracts: `04_DEFINITIONS_OF_DONE.md`,
  `06_TEST_CI_SECURITY_PLAN.md`, and `08_RELEASE_AND_UPSTREAM_STRATEGY.md`
- Target contract: an immutable, clean-installable Runtime wrapper release with
  versioned schemas, an exact Workstream 2 dependency pin, and a generic,
  dependency-ordered upstream contribution series
- Status: `met`
- Live-compute policy: no QPU submission or paid-compute mutation is authorized
  or required for this workstream

## DoD checklist

| DoD item | Status | Planned evidence |
|---|---|---|
| Resolve every W1-09 smoke finding. | met | Provider tag limit and ordered-submit failures were fixed before W1-09; live `ExecutionSpans` serialization is covered; release commit `d6de645` adds threshold-backed masks. Focused release smoke: 44 passed; plan/security/result smoke: 74 passed. The three docs integration cases remain an explicit read-only network gate, not ordinary tokenless CI. |
| Run clean-install, package-build, full CI, security, and schema-compatibility gates. | met | Runtime 0.7.3 passed on Python 3.10–3.14 (408 passed, 1 skipped per interpreter) with enforced per-module branch coverage: approvals 100%, budgeting 91.07%, parsing 90.91%, secret handling 100%. Reproducible wheel/sdist builds and isolated installs passed. Canonical lock/schema gates, qiskit/docs/transpiler/gym suites, Ruff, format, strict mypy, and Bandit passed. |
| Update version, changelog, migration guide, README, API docs, and generic examples. | met | Runtime 0.7.3, meta-package 0.12.3, `CHANGELOG.md`, `MIGRATION.md`, Runtime README, `docs/API.md`, experiment compatibility contract, and offline generic examples are synchronized with all 37 schemas. |
| Tag the exact tested commit and record lock/package hashes. | met | Annotated tag `runtime-research-v0.7.3` has tag object `66a9b66ac91e0031ba51e5576f28a6bd7410862a` and peels to tested commit `19dfc32862f99002e12bd6de824e5967c5227a85`; the annotation and release manifest record the lock, wheel, and sdist hashes. |
| Make the pinned release accessible to Workstream 2. | met | The immutable 0.7.3 tag and formal GitHub Release are published at `https://github.com/abbudjoe/mcp-servers`; an isolated Python 3.12 install from the exact public tag resolved to the tested commit and verified package `0.7.3`, all 37 schemas, typed recovery, and corrected snapshot identity. |
| Publish an experiment compatibility document. | met | `qiskit-ibm-runtime-mcp-server/docs/EXPERIMENT_COMPATIBILITY.md` records import paths, Python/stack requirements, environment variables, schema versions, modes, recovery trust boundary and limitations, exact tag pin, and W1-09 usage. |
| Split upstreamable changes into dependency-ordered PRs without experiment-specific content. | met | PRs 1–10 were merged to `main` in dependency order after ancestry, content, Runtime/coverage, and offline-example gates passed. Generic recovery PR 11 passed the complete GitHub matrix and was merged as `b836d71f42045528023a3d0a9fc2f1a97f5d0796`; its added-line audit contains no workstream, release-pin, fork, campaign, or experiment-specific content. |
| Independent spec-conformance review is clean. | met | Independent rereview found no blocking findings after 77 focused tests and duplicate identity, timestamp provenance, complete-state, provider-tag-ceiling, quality/security/schema, release-build, and remote-pin checks. |
| Provide the exact Workstream 2 dependency pin. | met | `qiskit-ibm-runtime-mcp-server @ git+https://github.com/abbudjoe/mcp-servers.git@runtime-research-v0.7.3#subdirectory=qiskit-ibm-runtime-mcp-server` |

## Gate evidence

- Exact tested release commit:
  `19dfc32862f99002e12bd6de824e5967c5227a85`.
- Annotated tag object: `66a9b66ac91e0031ba51e5576f28a6bd7410862a`;
  peeled tag target: the exact tested release commit above.
- Canonical compatibility: 7 passed on CPython 3.12.12; `uv lock --check`
  and `shasum -a 256 -c uv.lock.sha256` passed.
- Runtime canonical suite: 408 passed, 1 skipped. The skip is the explicitly
  gated read-only historical-provider integration case.
- Other canonical suites: qiskit 103 passed; docs 173 passed with 3 read-only
  network integrations deselected; transpiler 139 passed with 52 integrations
  deselected; gym 97 passed.
- Reproducible package builds and isolated wheel/sdist installs passed. The wheel
  contained version `0.7.3`, the license, and all 37 schemas; the sdist contained the
  changelog, migration guide, API reference, and experiment compatibility
  contract.
- Remote tag install gate: `REMOTE_PIN_AUDIT_OK 0.7.3 37
  19dfc32862f99002e12bd6de824e5967c5227a85`.
- Independent release-candidate rereview was clean before publication. The
  post-publication review verified the tag, peeled commit, release assets,
  exact public install, schemas, typed recovery, and corrected snapshot
  identity; its sole ledger-pin conflict was corrected before final rereview.
- No QPU or paid-compute mutation was performed during W1-10.
- Upstream recovery contribution: PR
  `https://github.com/abbudjoe/mcp-servers/pull/11`, merged to `main` as
  `b836d71f42045528023a3d0a9fc2f1a97f5d0796` after every GitHub check passed.

## Recovery-contract amendment

- Finding: release `0.7.1` recovery by submission key exposes provider job
  statuses with raw tags and nullable `created_at`, but does not return typed
  plan, partition, and PUB identity with a trustworthy submission timestamp.
- Root cause: restart recovery treated provider inventory as a receipt boundary
  instead of requiring and validating the caller-owned immutable
  `SubmissionPlan` against provider tags.
- Target contract: recovery requires the exact persisted plan, validates its
  canonical hash and every provider identity tag, returns ordered typed
  `RecoveredJobReceipt` values with required wrapper-owned UTC pre-submit
  timestamps, and fails closed on missing, ambiguous, duplicate, non-prefix, or
  contradictory evidence. Nullable provider creation time is corroboration only;
  the trust boundary explicitly includes provider-account tag writers.
- Mapped DoD: W1-07 typed recovery and immutable receipts; W1-10 smoke-finding
  resolution, release gates, immutable tested tag, accessible W2 pin, and
  independent spec-conformance review.
- Implementation evidence: 77 focused lifecycle/schema tests passed; the full
  Runtime suite passed on Python 3.10–3.14 with 405 passed and one gated skip
  per interpreter; all 37 schemas matched generated output; safety branch
  coverage remained 100%/91.07%/90.91%/100%; exact CI lint/format/mypy/Bandit,
  canonical compatibility, and the other four package suites passed.
- Package evidence: reproducible 0.7.2 wheel and sdist builds passed isolated
  Python 3.12 installs. Lock/wheel/sdist SHA-256 values are recorded in
  `W1-10_RELEASE_MANIFEST.md`.
- Independent rereview: clean after duplicate job identity, timestamp provenance,
  complete-state validation, and the provider eight-tag ceiling were fixed.
- Publication evidence: annotated tag object
  `0182e8b254b7e357b3738161d0cd9a6a720d3f01` peels remotely to tested commit
  `de40ebfcc28946c6424e6d54a8399aac111b2daa`; the formal GitHub Release is
  `https://github.com/abbudjoe/mcp-servers/releases/tag/runtime-research-v0.7.2`.
- Status: `met`; release `0.7.1` remains immutable but is not the W2
  recovery-safe pin. No QPU or cloud mutation was performed for this repair.

## Stable snapshot-identity amendment

- Status: `met`; immutable patch-release 0.7.3 is published and its exact
  public dependency pin passed the post-publication install audit.
- Live finding: W2-09 plan
  `sha256:ad3854dab33ff40ac61bef12949e37b24a20ec78bb8ca716c42df9604810eaf9`
  stopped before submission because `backend_status.pending_jobs` changed from
  0 to 2 even though target and calibration content were unchanged. Actual QPU
  usage and primitive submissions were both zero.
- Root cause: `snapshot_content_hash()` excluded retrieval time but still owned
  backend availability/queue observations as reproducible snapshot identity.
  That made a scheduling observation silently override the scientific target
  and calibration contract.
- Target contract: retain the complete typed `backend_status` observation in
  every snapshot artifact, but exclude the entire backend-status object from
  the stable snapshot content hash. Queue depth, operational availability, and
  status text are execution-time observations; target/calibration mutations
  must continue to change identity.
- Mapped DoD: W1-04 stable snapshot content hash and complete metadata capture;
  W1-10 smoke-finding resolution, patch-release gates, exact immutable pin, and
  independent spec-conformance review.
- Evidence: focused regressions mutate every backend-status field and
  retrieval time without changing identity, prove the full serialized snapshot
  still captures those observations, and prove calibration mutation still
  changes identity.
- Focused snapshot smoke: 16 passed, one separately gated read-only provider
  test skipped. Full Runtime suite: 408 passed, one gated skip. Ruff, format,
  strict mypy, Bandit, lock check, and `git diff --check` passed.
- Package evidence: wheel and sdist built successfully; the wheel contains the
  corrected snapshot implementation and the sdist contains source, tests, and
  changelog. An offline clean install reproduced the queue-depth regression and
  returned `CLEAN_INSTALL_SNAPSHOT_IDENTITY_OK`.
- Candidate 0.7.3 release matrix: Runtime 408 passed / one gated skip on each
  Python 3.10–3.14; safety branch coverage on every interpreter remained
  100.00% approvals, 91.07% budgeting, 90.91% Primitive parsing, and 100.00%
  secret handling. Companion suites passed: qiskit 103, docs 173 with three
  read-only integrations deselected, transpiler 139 with 52 integrations
  deselected, and gym 97.
- Candidate quality/release evidence: all-package Ruff, format, mypy, and Bandit
  passed; the lock and its checksum passed; 37 generated schemas exactly match
  the package; the offline example exported all 37. Two fixed-epoch builds were
  byte-identical. Wheel and sdist each passed isolated Python 3.12 probes for
  version, schemas, typed recovery, status-insensitive identity, and
  calibration-sensitive identity.
- Independent exact-candidate review: initially found one premature claim that
  the not-yet-published tag had passed a remote-pin install. The manifest now
  distinguishes completed local wheel/sdist probes from the pending
  post-publication tag probe. Rereview result: `CLEAN`; all pre-publication rows
  are met, with only tag identity and remote accessibility correctly blocked
  until publication.
- Independent assembly review: `CLEAN`; all four mapped amendment items met,
  no schema/model change or status-evidence loss, and 0.7.2 compatibility
  handling is explicit. Post-review source-contract smoke: 142 passed, one
  gated skip; Ruff, format, and diff checks passed.
- Publication evidence: annotated tag object
  `66a9b66ac91e0031ba51e5576f28a6bd7410862a` peels locally and remotely to
  tested commit `19dfc32862f99002e12bd6de824e5967c5227a85`; the formal
  GitHub Release is
  `https://github.com/abbudjoe/mcp-servers/releases/tag/runtime-research-v0.7.3`.
  An isolated public-tag install returned `REMOTE_PIN_AUDIT_OK 0.7.3 37
  19dfc32862f99002e12bd6de824e5967c5227a85`, and downloaded release assets
  matched the recorded wheel and sdist SHA-256 values.
- Exact W2 dependency pin:
  `qiskit-ibm-runtime-mcp-server @ git+https://github.com/abbudjoe/mcp-servers.git@runtime-research-v0.7.3#subdirectory=qiskit-ibm-runtime-mcp-server`.
  Existing 0.7.2 plans, snapshots, approvals, and receipts remain stale and
  must not be reused with 0.7.3.
- No provider, primitive, cloud, or QPU mutation was performed for this
  amendment. Actual QPU usage was zero seconds and primitive submissions were
  zero; network access was limited to Git/GitHub publication and public-pin
  installation verification.
