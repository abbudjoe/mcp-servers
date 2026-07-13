<!--
This code is part of Qiskit.

(C) Copyright IBM 2026.

This code is licensed under the Apache License, Version 2.0. You may
obtain a copy of this license in the LICENSE file in the root directory
of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
-->

# W1-03 Typed Models and Artifact Interface

## Assembly ledger

| Field | Value |
|---|---|
| Task | W1-03 — Typed Models and Artifact Interface |
| Status | `successful` — implementation, review/fix loops, post-review smoke, and publication evidence passed |
| Source contract | `qiskit_wrapper_workstream_build_package/05_API_AND_DATA_CONTRACTS.md`, reconciled with `docs/runtime-research/stack-compatibility-report.md` |
| Target contract | Version 1 Pydantic models and published schemas; canonical JSON SHA-256; an MCP-independent artifact protocol; secure local CAS; configurable large-value replacement. |
| Boundary | No campaign SQLite state, scientific manifests, analyses, network access, Batch creation, primitive submission, or QPU activity. |

## Extracted DoD

| DoD item | Status | Evidence |
|---|---|---|
| Versioned typed models exist for circuits, snapshots, PUB specs, results, plans, usage, and approvals. | `met` | All independently persisted models require `schema_version == "1.0"`; tagged observable and inline-value forms require literal tags. Model/schema negative tests reject missing and unsupported versions/tags. Locked Qiskit `BitArray` compatibility covers PUB shape, shot count, bit width, and row-major per-location data. |
| Every model exports JSON Schema. | `met` | Sixteen Draft 2020-12 schemas are checked in under `core/json_schemas/v1.0`, exactly match deterministic generation, validate structurally, and ship in the wheel. |
| JSON-safe conversion handles NumPy scalars/arrays and unknown extension fields. | `met` | Tests cover NumPy bool/signed/unsigned/floating/string/datetime scalars and arrays, `D`/`s`/`us`/`ns` datetime stability, `NaT`, long-double handling, Python datetimes, enums/`IntEnum`, and preserved future fields. Compact sorted canonical JSON produces `sha256:<hex>` identifiers and rejects non-finite or unsupported values. |
| `ArtifactSink` protocol and local content-addressed implementation are tested. | `met` | Generic sink-owned URIs and the local CAS pass byte round-trip, deduplication, collision, traversal, static symlink, tamper, locator, and integrity checks. Local writes are anchored to an owned mode-0700 root with `O_DIRECTORY`/`O_NOFOLLOW` and dirfd-relative I/O. A deterministic root-swap race creates no digest or temporary file outside the configured root. |
| Large payloads are replaced by artifact references at a configurable threshold. | `met` | `artifactize` returns the typed `InlineJsonValue | ArtifactRef` contract: values at the exact byte threshold remain inline and values one byte over become CAS references. Both branches compose with and round-trip through Estimator result fields. |

## Published contract surface

- `core/models.py`: required v1 models, explicit observable semantics, ordered PUB results,
  Runtime usage, plans, approvals, and generic artifact references.
- `core/serialization.py`: JSON-safe normalization, canonical UTF-8 JSON, and SHA-256 hashing.
- `core/artifacts.py`: `ArtifactSink`, secure `LocalArtifactCAS`, and threshold artifactization.
- `core/schemas.py`: deterministic schema generation/export.
- `core/json_schemas/v1.0/*.schema.json`: 16 generated schemas included in wheel/sdist.

## Evidence

| Gate | Result |
|---|---|
| Focused correctness | `uv run --locked pytest qiskit-ibm-runtime-mcp-server/tests/test_core_contracts.py -q`: 34 passed. Covers schema drift/validity, every-model round-trip, compatibility, hashing, threshold, collision, and path safety. |
| Tokenless package smoke | `env -u QISKIT_IBM_TOKEN uv run --locked pytest qiskit-ibm-runtime-mcp-server/tests -q`: 227 passed before review completion and again as the post-review smoke. |
| Static and security | Runtime-package Ruff lint/format, strict mypy (11 source files), Bandit, and `git diff --check` passed. Bandit emitted only its existing comment-token parser warnings and no findings. |
| Build/publication | `uv build --package qiskit-ibm-runtime-mcp-server` produced wheel and sdist. Wheel inspection found all 16 generated v1 schema files. |
| Lock control plane | `uv lock --check --python 3.12.12` and `shasum -a 256 -c uv.lock.sha256` pass. W1-03 directly declared NumPy and JSON Schema ownership without changing resolved versions; lock SHA-256 is `08d742daad084ae27e0a22c6b63e0597c0dbfd8fccff67fadea5344495df704e`. |
| Independent review | Initial assembly review classified five DoD areas partial and found six contract/safety defects; all were fixed. First rereview found three remaining tag/composition/datetime alignment defects; all were fixed. Final rereview independently reran the 34 focused tests and returned clean, classifying every W1-03 DoD and the Workstream 2 boundary `met`. |
| Forbidden operations | No network call, Runtime service resolution, Batch creation, primitive submission, cloud mutation, or QPU call occurred. |

## Boundary result

No campaign SQLite state, scientific manifest, analysis, experiment policy, or campaign-level
ownership was added. Those remain exclusively in Workstream 2.
