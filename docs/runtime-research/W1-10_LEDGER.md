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
- Status: `review-pending`
- Live-compute policy: no QPU submission or paid-compute mutation is authorized
  or required for this workstream

## DoD checklist

| DoD item | Status | Planned evidence |
|---|---|---|
| Resolve every W1-09 smoke finding. | met | Provider tag limit and ordered-submit failures were fixed before W1-09; live `ExecutionSpans` serialization is covered; release commit `d6de645` adds threshold-backed masks. Focused release smoke: 44 passed; plan/security/result smoke: 74 passed. The three docs integration cases remain an explicit read-only network gate, not ordinary tokenless CI. |
| Run clean-install, package-build, full CI, security, and schema-compatibility gates. | met | Wheel and sdist builds plus isolated installs passed. Canonical lock/schema gates passed. Runtime passed on Python 3.10–3.14 (362 passed, 1 skipped per interpreter); qiskit and docs passed on 3.10–3.14 (103 and 173 passed per interpreter); transpiler and gym passed on 3.10–3.13 (139 and 97 passed per interpreter). Ruff, format, strict mypy, and Bandit passed for all five packages with zero Bandit findings. |
| Update version, changelog, migration guide, README, API docs, and generic examples. | met | Runtime 0.7.0, meta-package 0.12.0, `CHANGELOG.md`, `MIGRATION.md`, rewritten Runtime README, `docs/API.md`, and offline `examples/research_contracts.py`; example executed successfully and exported all 35 schemas. |
| Tag the exact tested commit and record lock/package hashes. | met | Annotated tag `runtime-research-v0.7.0` peels to tested commit `a24f67a869a7f9279f98440b21214987e14f3c42`; the annotation and release manifest record the lock, wheel, and sdist hashes. |
| Make the pinned release accessible to Workstream 2. | met | The tag is published at `https://github.com/abbudjoe/mcp-servers.git`; an isolated Python 3.12 install from the exact tag resolved to the tested commit and verified package `0.7.0`, all 35 schemas, and empty execution-span serialization. |
| Publish an experiment compatibility document. | met | `qiskit-ibm-runtime-mcp-server/docs/EXPERIMENT_COMPATIBILITY.md` records import paths, Python/stack requirements, environment variables, schema versions, modes, limitations, exact tag pin, and 4-second W1-09 usage. |
| Split upstreamable changes into dependency-ordered PRs without experiment-specific content. | met | Ten cumulative branches based on upstream `8c1abce` are published to the fork. Each branch is one commit over its predecessor; added-line and whole-tip audits reject workstream IDs, experiment tag/pin text, fork URLs, and the experiment-specific schema namespace. See `W1-10_UPSTREAM_SERIES.md`. |
| Independent spec-conformance review is clean. | pending | Final assembly reviewer audit requested after the immutable tag, remote pin install, and upstream series publication. |
| Provide the exact Workstream 2 dependency pin. | met | `qiskit-ibm-runtime-mcp-server @ git+https://github.com/abbudjoe/mcp-servers.git@runtime-research-v0.7.0#subdirectory=qiskit-ibm-runtime-mcp-server` |

## Gate evidence

- Exact tested release commit:
  `a24f67a869a7f9279f98440b21214987e14f3c42`.
- Annotated tag object: `90378ab69b260bf74d0afbb647a31281dd7c762d`;
  peeled tag target: the exact tested release commit above.
- Canonical compatibility: 7 passed on CPython 3.12.12; `uv lock --check`
  and `shasum -a 256 -c uv.lock.sha256` passed.
- Runtime canonical suite: 362 passed, 1 skipped. The skip is the explicitly
  gated read-only historical-provider integration case.
- Other canonical suites: qiskit 103 passed; docs 173 passed with 3 read-only
  network integrations deselected; transpiler 139 passed with 52 integrations
  deselected; gym 97 passed.
- Package builds and isolated wheel/sdist installs passed. The wheel contained
  version `0.7.0`, the license, and all 35 schemas; the sdist contained the
  changelog, migration guide, API reference, and experiment compatibility
  contract.
- Remote tag install gate: `REMOTE_PIN_INSTALL_OK 0.7.0 35`.
- No QPU or paid-compute mutation was performed during W1-10.
