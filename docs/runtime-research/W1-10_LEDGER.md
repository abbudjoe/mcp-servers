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
| Run clean-install, package-build, full CI, security, and schema-compatibility gates. | not-started | Recorded commands, test counts, and immutable evidence hashes. |
| Update version, changelog, migration guide, README, API docs, and generic examples. | met | Runtime 0.7.0, meta-package 0.12.0, `CHANGELOG.md`, `MIGRATION.md`, rewritten Runtime README, `docs/API.md`, and offline `examples/research_contracts.py`; example executed successfully and exported all 35 schemas. |
| Tag the exact tested commit and record lock/package hashes. | not-started | Annotated tag, commit identity, `uv.lock` SHA-256, wheel/sdist SHA-256. |
| Make the pinned release accessible to Workstream 2. | not-started | Published immutable tag and verified remote ref. |
| Publish an experiment compatibility document. | met | `qiskit-ibm-runtime-mcp-server/docs/EXPERIMENT_COMPATIBILITY.md` records import paths, Python/stack requirements, environment variables, schema versions, modes, limitations, exact tag pin, and 4-second W1-09 usage. |
| Split upstreamable changes into dependency-ordered PRs without experiment-specific content. | not-started | Reviewable branch/commit map and content audit. |
| Independent spec-conformance review is clean. | not-started | Reviewer classification for every checklist entry, followed by post-review gate reruns. |
| Provide the exact Workstream 2 dependency pin. | partial | Tag-bound VCS requirement is documented; remote tag publication and commit verification remain gated on final evidence. |
