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
- Status: `in-progress`
- Live-compute policy: no QPU submission or paid-compute mutation is authorized
  or required for this workstream

## DoD checklist

| DoD item | Status | Planned evidence |
|---|---|---|
| Resolve every W1-09 smoke finding. | met | Provider tag limit and ordered-submit failures were fixed before W1-09; live `ExecutionSpans` serialization is covered; release commit `d6de645` adds threshold-backed masks. Focused release smoke: 44 passed; plan/security/result smoke: 74 passed. The three docs integration cases remain an explicit read-only network gate, not ordinary tokenless CI. |
| Run clean-install, package-build, full CI, security, and schema-compatibility gates. | met | Runtime 0.7.1 passed on Python 3.10–3.14 (392 passed, 1 skipped per interpreter) with enforced per-module branch coverage: approvals 100%, budgeting 91.07%, parsing 90.91%, secret handling 100%. Wheel/sdist builds and isolated installs passed. Canonical lock/schema gates, qiskit/docs/transpiler/gym suites, Ruff, format, strict mypy, and Bandit passed. |
| Update version, changelog, migration guide, README, API docs, and generic examples. | met | Runtime 0.7.1, meta-package 0.12.1, `CHANGELOG.md`, `MIGRATION.md`, rewritten Runtime README, `docs/API.md`, and offline `examples/research_contracts.py`; example executed successfully and exported all 35 schemas. |
| Tag the exact tested commit and record lock/package hashes. | met | Annotated tag `runtime-research-v0.7.1` peels to tested commit `664a44c086f49c15279f814e205b15970e689fe0`; the annotation and release manifest record the lock, wheel, and sdist hashes. The immutable annotation contains a mistyped expanded commit string, explicitly corrected by the peeled target and release manifest. |
| Make the pinned release accessible to Workstream 2. | met | The tag is published at `https://github.com/abbudjoe/mcp-servers.git`; an isolated Python 3.12 install from the exact tag resolved to the tested commit and verified package `0.7.1`, all 35 schemas, and empty execution-span serialization. |
| Publish an experiment compatibility document. | met | `qiskit-ibm-runtime-mcp-server/docs/EXPERIMENT_COMPATIBILITY.md` records import paths, Python/stack requirements, environment variables, schema versions, modes, limitations, exact tag pin, and 4-second W1-09 usage. |
| Split upstreamable changes into dependency-ordered PRs without experiment-specific content. | met | Draft PRs 1–10 were restacked from preserved upstream base `8c1abce`. Every PR is one commit over its predecessor; generic fixture IDs, version-neutral PR 10 docs, whole-tip content audit, full Runtime/coverage gate at PR 9, and offline example gate at PR 10 all pass. |
| Independent spec-conformance review is clean. | met | Independent rereview found no blocking findings after reproducing the Runtime suite and safety coverage gate, quality/security/schema checks, release hashes and remote pin install, and live PR ancestry/content audits. |
| Provide the exact Workstream 2 dependency pin. | met | `qiskit-ibm-runtime-mcp-server @ git+https://github.com/abbudjoe/mcp-servers.git@runtime-research-v0.7.1#subdirectory=qiskit-ibm-runtime-mcp-server` |

## Gate evidence

- Exact tested release commit:
  `664a44c086f49c15279f814e205b15970e689fe0`.
- Annotated tag object: `6ae1ff73b3a5541f5f49e7ce97ef2fbcd6ca9351`;
  peeled tag target: the exact tested release commit above.
- Canonical compatibility: 7 passed on CPython 3.12.12; `uv lock --check`
  and `shasum -a 256 -c uv.lock.sha256` passed.
- Runtime canonical suite: 392 passed, 1 skipped. The skip is the explicitly
  gated read-only historical-provider integration case.
- Other canonical suites: qiskit 103 passed; docs 173 passed with 3 read-only
  network integrations deselected; transpiler 139 passed with 52 integrations
  deselected; gym 97 passed.
- Package builds and isolated wheel/sdist installs passed. The wheel contained
  version `0.7.1`, the license, and all 35 schemas; the sdist contained the
  changelog, migration guide, API reference, and experiment compatibility
  contract.
- Remote tag install gate: `REMOTE_PIN_INSTALL_OK 0.7.1 35`.
- Independent assembly rereview: clean, with all nine W1-10 DoD rows
  classified `met`; the immutable annotation's expanded-SHA typo was classified
  non-blocking because the tag object, peeled remote ref, resolver, and manifest
  all identify the exact tested commit.
- No QPU or paid-compute mutation was performed during W1-10.

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
- Status: `release-candidate`; release `0.7.1` remains immutable but is not the
  W2 recovery-safe pin. No QPU or cloud mutation was performed for this repair.
