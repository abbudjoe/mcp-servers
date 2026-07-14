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
| Run clean-install, package-build, full CI, security, and schema-compatibility gates. | met | Runtime 0.7.2 passed on Python 3.10–3.14 (405 passed, 1 skipped per interpreter) with enforced per-module branch coverage: approvals 100%, budgeting 91.07%, parsing 90.91%, secret handling 100%. Reproducible wheel/sdist builds and isolated installs passed. Canonical lock/schema gates, qiskit/docs/transpiler/gym suites, Ruff, format, strict mypy, and Bandit passed. |
| Update version, changelog, migration guide, README, API docs, and generic examples. | met | Runtime 0.7.2, meta-package 0.12.2, `CHANGELOG.md`, `MIGRATION.md`, Runtime README, `docs/API.md`, experiment compatibility contract, and offline generic examples are synchronized with all 37 schemas. |
| Tag the exact tested commit and record lock/package hashes. | met | Annotated tag `runtime-research-v0.7.2` has tag object `0182e8b254b7e357b3738161d0cd9a6a720d3f01` and peels to tested commit `de40ebfcc28946c6424e6d54a8399aac111b2daa`; the annotation and release manifest record the lock, wheel, and sdist hashes. |
| Make the pinned release accessible to Workstream 2. | met | The immutable tag and formal GitHub Release are published at `https://github.com/abbudjoe/mcp-servers`; an isolated Python 3.12 install from the exact tag resolved to the tested commit and verified package `0.7.2`, all 37 schemas, and the typed recovery models. |
| Publish an experiment compatibility document. | met | `qiskit-ibm-runtime-mcp-server/docs/EXPERIMENT_COMPATIBILITY.md` records import paths, Python/stack requirements, environment variables, schema versions, modes, recovery trust boundary and limitations, exact tag pin, and W1-09 usage. |
| Split upstreamable changes into dependency-ordered PRs without experiment-specific content. | met | PRs 1–10 were merged to `main` in dependency order after ancestry, content, Runtime/coverage, and offline-example gates passed. Generic recovery PR 11 passed the complete GitHub matrix and was merged as `b836d71f42045528023a3d0a9fc2f1a97f5d0796`; its added-line audit contains no workstream, release-pin, fork, campaign, or experiment-specific content. |
| Independent spec-conformance review is clean. | met | Independent rereview found no blocking findings after 77 focused tests and duplicate identity, timestamp provenance, complete-state, provider-tag-ceiling, quality/security/schema, release-build, and remote-pin checks. |
| Provide the exact Workstream 2 dependency pin. | met | `qiskit-ibm-runtime-mcp-server @ git+https://github.com/abbudjoe/mcp-servers.git@runtime-research-v0.7.2#subdirectory=qiskit-ibm-runtime-mcp-server` |

## Gate evidence

- Exact tested release commit:
  `de40ebfcc28946c6424e6d54a8399aac111b2daa`.
- Annotated tag object: `0182e8b254b7e357b3738161d0cd9a6a720d3f01`;
  peeled tag target: the exact tested release commit above.
- Canonical compatibility: 7 passed on CPython 3.12.12; `uv lock --check`
  and `shasum -a 256 -c uv.lock.sha256` passed.
- Runtime canonical suite: 405 passed, 1 skipped. The skip is the explicitly
  gated read-only historical-provider integration case.
- Other canonical suites: qiskit 103 passed; docs 173 passed with 3 read-only
  network integrations deselected; transpiler 139 passed with 52 integrations
  deselected; gym 97 passed.
- Reproducible package builds and isolated wheel/sdist installs passed. The wheel
  contained version `0.7.2`, the license, and all 37 schemas; the sdist contained the
  changelog, migration guide, API reference, and experiment compatibility
  contract.
- Remote tag install gate: `REMOTE_PIN_INSTALL_OK 0.7.2 37
  de40ebfcc28946c6424e6d54a8399aac111b2daa`.
- Independent assembly rereview: clean, with all nine W1-10 DoD rows
  classified `met`; the immutable annotation's expanded-SHA typo was classified
  non-blocking because the tag object, peeled remote ref, resolver, and manifest
  all identify the exact tested commit.
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
