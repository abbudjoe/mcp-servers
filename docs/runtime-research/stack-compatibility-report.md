<!--
This code is part of Qiskit.

(C) Copyright IBM 2026.

This code is licensed under the Apache License, Version 2.0. You may
obtain a copy of this license in the LICENSE file in the root directory
of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
-->

# W1-01 Canonical Stack and Compatibility Report

## Task ledger

| Field | Value |
|---|---|
| Task | W1-01 — Lock the Qiskit Stack |
| Objective | Qualify and lock one Python/Qiskit/Runtime/FastMCP scientific reference while retaining bounded, publishable package ranges. |
| Evidence date | 2026-07-13 |
| Status | `successful` — implementation, evidence, independent review, and post-review smoke passed |
| Target contract | One root workspace lock on CPython 3.12.12; exact contract-sensitive versions; public package metadata uses tested ranges; deterministic guards cover every API shape listed in the W1-01 prompt. |
| QPU policy | Forbidden; no authenticated Runtime or primitive submission is needed. |

The authoritative DoD is
`qiskit_wrapper_workstream_build_package/04_DEFINITIONS_OF_DONE.md`, section W1-01.
This report is both the compatibility handoff and the assembly ledger for that checklist.

## Decision

The canonical scientific reference is:

| Component | Exact version | Why this version |
|---|---:|---|
| CPython | 3.12.12 | Workstream-selected Python 3.12, pinned to an exact patch for reproducibility. |
| uv | 0.11.7 | Lock generator and CI installer used for the evidence run. |
| Qiskit | 2.4.2 | Newest Qiskit release that imports with IBM Transpiler 0.18.0; QPY format 17. |
| Qiskit IBM Runtime | 0.45.1 | Newest Runtime version compatible with the complete workspace dependency graph. |
| FastMCP | 3.4.4 | Current stable FastMCP release when qualified; exact-pinned because FastMCP permits breaking minor releases. |
| Qiskit IBM Transpiler | 0.18.0 | Current workspace integration line. |
| Qiskit Gym | 0.4.1 | Current workspace integration line and Qiskit 2.x consumer. |
| Qiskit Serverless | 0.30.1 | Transitive IBM Transpiler dependency that defines the Runtime ceiling. |
| Qiskit QASM3 Import | 0.6.0 | Current parser used by the circuit serialization boundary. |
| NumPy | 2.4.6 on Python 3.11+; 2.2.6 on Python 3.10 | Latest compatible minor per Python row; avoids NumPy 2.5's Python 3.12-only stubs contradicting the repository's mypy 3.10 target. |

Official release metadata was inspected for [Qiskit 2.4.2](https://pypi.org/project/qiskit/2.4.2/),
[Runtime 0.45.1](https://pypi.org/project/qiskit-ibm-runtime/0.45.1/),
[FastMCP 3.4.4](https://pypi.org/project/fastmcp/3.4.4/),
[IBM Transpiler 0.18.0](https://pypi.org/project/qiskit-ibm-transpiler/0.18.0/), and
[Qiskit Gym 0.4.1](https://pypi.org/project/qiskit-gym/0.4.1/).

Qiskit 2.5.0 was initially selected because IBM Transpiler declares `qiskit>=1.4.2,<3`.
The first workspace smoke disproved that metadata contract: importing IBM Transpiler 0.18.0
failed because it imports the removed private module
`qiskit.synthesis.linear.linear_matrix_utils`. A clean candidate environment with Qiskit
2.4.2 imports the same IBM Transpiler stack successfully. The wrapper therefore declares the
missing `qiskit>=2.1,<2.5` bound so published users cannot resolve the known-broken pair.

Runtime 0.47.0 is also newer, but it cannot be the canonical Runtime while IBM Transpiler is a
workspace member. IBM Transpiler 0.18.0 requires Qiskit Serverless 0.30.x; Serverless 0.30.1
requires `qiskit-ibm-runtime>=0.40.1,<0.46.0`. Selecting Runtime 0.45.1 therefore honors the
whole control plane instead of allowing the Runtime server and Transpiler server to describe
contradictory environments. An isolated CPython 3.12.12 environment resolved and imported all
seven exact contract-sensitive distributions together before the final repository lock was generated.

## Constraint and workspace inventory

### Python and lock ownership

| Scope | Supported Python | Lock behavior |
|---|---|---|
| Root meta-package and complete workspace | `>=3.10,<3.14` | One checked-in root `uv.lock`; canonical execution is exactly 3.12.12. |
| Core Qiskit, Docs, Runtime servers | `>=3.10,<3.15` | Published packages remain installable and matrix-tested on 3.10–3.14. |
| IBM Transpiler and Gym servers | `>=3.10,<3.14` | Published packages remain matrix-tested on 3.10–3.13 because upstream IBM Transpiler excludes 3.14. |

The root meta-package was corrected from `<3.15` to `<3.14`: it installs IBM Transpiler by
default, so advertising Python 3.14 contradicted its own dependency closure. Four tracked
member-local lockfiles were removed and `/*/uv.lock` is ignored. uv workspace discovery had
already ignored those stale locks, so keeping them created a second, misleading dependency
control plane. Package builds do not include or need a lockfile.

### Published production constraints

| Package | Production constraints after W1-01 |
|---|---|
| `qiskit-mcp-servers` | Qiskit wrapper `>=0.3,<0.4`; Docs `>=0.2,<0.3`; Runtime `>=0.6,<0.7`; IBM Transpiler `>=0.4,<0.5`; optional Gym `>=0.4,<0.5`. |
| `qiskit-mcp-server` | FastMCP `>=3.2,<3.5`; Qiskit `>=1.3,<2.6`; QASM3 Import `>=0.5,<0.7`; Pydantic `>=2`; python-dotenv `>=1`. |
| `qiskit-docs-mcp-server` | Beautiful Soup `>=4.12`; defusedxml `>=0.7.1`; FastMCP `>=3.2,<3.5`; html2text `>=2020.1.16`; HTTPX `>=0.28.1`. |
| `qiskit-ibm-runtime-mcp-server` | FastMCP `>=3.2,<3.5`; NumPy `>=1.26`; Runtime `>=0.40.1,<0.46`; Qiskit wrapper `>=0.3,<0.4`; Pydantic `>=2`; python-dotenv `>=1`. |
| `qiskit-ibm-transpiler-mcp-server` | FastMCP `>=3.2,<3.5`; Qiskit `>=2.1,<2.5`; IBM Transpiler `>=0.18,<0.19`; Qiskit wrapper `>=0.3,<0.4`. |
| `qiskit-gym-mcp-server` | FastMCP `>=3.2,<3.5`; Qiskit Gym `>=0.4,<0.5`; Qiskit `>=2.1,<2.6`; Runtime `>=0.40.1,<0.46`; Qiskit wrapper `>=0.3,<0.4`; Pydantic `>=2`. |

Upper bounds are applied to contract-sensitive Qiskit, Runtime, FastMCP, wrapper, and
workspace integration packages. They stop an unqualified API minor from entering a published
installation while avoiding exact pins in wheel metadata. Lower-only bounds remain on generic
utilities and developer/example dependencies where an arbitrary ceiling would not represent a
qualified public API contract. The root lock still pins every transitive distribution and hash.

The four direct `nest-asyncio` dependencies were removed. Core and Runtime previously applied
`nest_asyncio.apply()` during module import, globally changing event-loop ownership for every
FastMCP request in the process. On Python 3.14 that made AnyIO observe no host task and broke
all FastMCP listing APIs. The `.sync` boundary now owns a fresh loop only for synchronous
callers and fails clearly inside an active loop, where callers must use `await`. This preserves
the supported Python 3.14 package rows without a process-wide monkeypatch. The lock may still
contain independently named notebook-loop helpers pulled by example tooling; no server imports
or applies them.

### Development, test, and example constraints

The remaining direct constraints were inventoried and intentionally left as package-local
compatibility inputs:

| Scope | Constraints |
|---|---|
| Root dev | mypy `>=1.18.2`; Ruff `>=0.14.6`. |
| Root examples | deepagents `>=0.1` on Python 3.11+; LangChain `>=1.2`; MCP adapters `>=0.1`; Anthropic `>=1`; python-dotenv `>=1`. |
| Core/Runtime dev | Ruff `>=0.11.13`; mypy `>=1.15`; pre-commit `>=3.5`; Bandit `>=1.7` in extras and `>=1.9.2` in the uv group. |
| Core/Runtime tests | JSON Schema `>=4`; pytest `>=7.4`; pytest-asyncio `>=0.21`; pytest-mock `>=3.11`; pytest-cov `>=4.1`. |
| Docs dev/tests | Bandit `>=1.8.2`; mypy `>=1.15`; pre-commit `>=4.1`; Ruff `>=0.9.4`; types-defusedxml `>=0.7`; pytest family at the same lower bounds as Core. |
| IBM Transpiler/Gym dev/tests | Ruff `>=0.11.13`; mypy `>=1.15`; Bandit `>=1.9.2`; pytest `>=8.4.2`; pytest-asyncio `>=1.2`; pytest-mock `>=3.15.1`; pytest-cov `>=4.1`. |
| Member examples | LangChain/provider/adapters/python-dotenv lower bounds as recorded in each member `pyproject.toml`; these do not define the scientific Runtime API. |

`[tool.uv].constraint-dependencies` is the non-published scientific control plane. It pins the
seven contract-sensitive packages and the Python-specific NumPy line exactly in the workspace lock. Wheel/sdist metadata contains
the ranges above, so the packages remain independently publishable.

## Qualified public API contracts

### Primitive V2 PUBs and results

Runtime 0.45.1 exposes `SamplerV2.run(self, pubs, *, shots=None)` and
`EstimatorV2.run(self, pubs, *, precision=None)`. Qiskit 2.4.2 provides `SamplerPub.coerce`
and `EstimatorPub.coerce`, and returns per-PUB objects through iterable/indexable
`PrimitiveResult`. Sampler data is a `DataBin` whose named classical-register fields are
`BitArray` objects; Estimator data carries broadcast `evs` and `stds`. Unknown `DataBin`
fields remain accessible and must be preserved by the later typed result envelope. The guard
constructs multiple synthetic PUB results, validates order/indexing, named sampler data,
Estimator arrays, metadata, and an unknown extension field. No primitive is instantiated or
submitted. See IBM's [V2 primitives migration contract](https://quantum.cloud.ibm.com/docs/en/guides/v2-primitives)
and the versioned [Runtime 0.45 API](https://quantum.cloud.ibm.com/docs/en/api/qiskit-ibm-runtime/0.45).

### Batch

The qualified constructor is `Batch(backend, max_time=None, *, create_new=True)` and the
reattachment class method is `Batch.from_id(session_id, service)`. A real `BackendV2` object,
not a backend-name string, owns the execution mode. These are signature guards only; constructing
a Batch would create remote state and is forbidden in W1-01. IBM's
[Batch guide](https://quantum.cloud.ibm.com/docs/en/guides/run-jobs-batch) confirms backend-object
ownership and explicit close behavior.

### Backend properties and target

`QiskitRuntimeService.backend(name, instance=None, use_fractional_gates=False,
calibration_id=None)` returns `BackendV2`. `IBMBackend.properties(refresh=False,
datetime=None)` returns Runtime's `BackendProperties` model or `None`, and `IBMBackend.target`
is a property. Target qualification uses the public
`Target.instruction_supported(...)` contract with instruction name and exact qargs. The guard
uses a synthetic `Target` and never resolves an IBM service.

### QPY

Qiskit 2.4.2 writes QPY format 17 by default and can load through format 17. `qpy.dump` accepts
one program or a list; `qpy.load` always returns a list. The guard asserts the public signatures,
the default writer format, single-item list semantics, circuit equality, and metadata fidelity.
QPY is backwards-compatible but not forwards-compatible; consumers on older Qiskit versions
cannot be assumed to read format 17. The official
[QPY compatibility table](https://quantum.cloud.ibm.com/docs/en/api/qiskit/qpy) is the source
contract.

### Runtime options

`SamplerOptions` and `EstimatorOptions` are structured dataclasses with public `update(**kwargs)`.
The qualified common fields include `max_execution_time`, execution, twirling, dynamical
decoupling, and experimental options; Sampler adds `default_shots`; Estimator adds
`default_precision`, `default_shots`, resilience level, and resilience. The guard checks these
fields and bulk update behavior. Later work must not pass legacy flattened option dictionaries.

### FastMCP

The supported surface is `from fastmcp import FastMCP`, `FastMCP(...)`, `@mcp.tool`,
`@mcp.resource(uri)`, `@mcp.prompt`, and async `list_tools()`, `list_resources()`,
`list_resource_templates()`, and `list_prompts()`. The guard registers and lists deterministic
tool, static-resource, resource-template, and prompt fixtures without touching private managers. FastMCP's
[server documentation](https://gofastmcp.com/servers/server) identifies these as public APIs.
Its [versioning policy](https://gofastmcp.com/getting-started/installation) explicitly recommends
exact production pins because breaking changes can occur in minor versions; this justifies the
publish ceiling `<3.5` and exact workspace pin 3.4.4.

## Upgrade revalidation checklist

Any change to Python, uv, Qiskit, Runtime, FastMCP, IBM Transpiler, Qiskit Gym, Qiskit
Serverless, or QASM3 Import must update the root constraints, regenerate the lock and digest,
and revalidate all of the following before merge:

1. Sampler and Estimator `run` keyword-only defaults and PUB coercion/broadcast behavior.
2. `PrimitiveResult`, per-PUB result, `DataBin`, `BitArray`, Estimator `evs`/`stds`, metadata,
   and unknown extension-field shapes.
3. Batch constructor, `from_id`, backend-object ownership, context/close semantics, status,
   details, jobs, and usage fields.
4. `QiskitRuntimeService.backend`, `IBMBackend.properties` current/historical parameters,
   `IBMBackend.target`, fractional-gate/calibration selection, and exact-qargs Target checks.
5. QPY writer version, maximum reader version, list semantics, annotations, metadata, and
   cross-version fixtures; never assume forward compatibility.
6. Sampler/Estimator structured option fields, `update`, unset semantics, and Runtime option
   serialization.
7. FastMCP constructor/decorator/listing public APIs and every server's tool/resource registration.
8. The IBM Transpiler → Serverless → Runtime constraint intersection and every supported Python
   row, including the separate Python 3.14 package jobs.

## CI and guard design

The canonical CI job installs uv 0.11.7 and CPython 3.12.12, verifies `uv.lock.sha256`, performs
an all-package/all-group `uv sync --locked`, and runs `tests/compat/test_canonical_stack.py`.
The guard emits targeted failures for exact-version drift, nested locks, PUB/results, Batch,
backend properties/target, QPY, options, and FastMCP public APIs.

Package compatibility jobs remain a supported matrix rather than reusing the exact scientific
lock. They build isolated environments from publishable metadata on Python 3.10–3.14 where the
package declares support. Ordinary Runtime tests receive no token. IBM Transpiler integration
tests are excluded from ordinary CI because the W1-00 baseline proved they can resolve live
services; local/unit coverage remains in the matrix. No CI guard submits a primitive job.

## Evidence ledger

| Gate | Result |
|---|---|
| Root lock digest | The original W1-01 lock SHA-256 was `1bab4b2a6fbd0578c5212d0b7250dbe3d4350af10b16b747e0ef5ac362d536c6`. W1-03 added direct Runtime-package ownership of its NumPy contract and JSON Schema test dependency; the regenerated `uv.lock` SHA-256 is `08d742daad084ae27e0a22c6b63e0597c0dbfd8fccff67fadea5344495df704e`, and `shasum -a 256 -c uv.lock.sha256` passes. The resolved versions and artifact hashes did not change. |
| Clean regeneration | During W1-01, a repository copy excluding `.git`, `.venv`, and every `uv.lock` ran `uv lock --python 3.12.12`; it resolved 336 packages and the generated lock was byte-identical to that W1-01 lock. After W1-03 declared already-resolved NumPy and JSON Schema dependencies directly, `uv lock --check --python 3.12.12` and the updated digest check pass; no resolved package version or distribution artifact changed. |
| Clean install | A new external virtual environment ran `uv sync --active --locked --python 3.12.12 --all-packages --all-groups` against the clean copy and installed 296 packages. It reported Qiskit 2.4.2, Runtime 0.45.1, FastMCP 3.4.4, IBM Transpiler 0.18.0, and Qiskit Gym 0.4.1. |
| Publishability | `uv build --all-packages` produced wheel and sdist artifacts for all six workspace packages. Wheel metadata contains the documented ranges rather than workspace-only exact constraints. |
| Canonical guards | The clean environment passed all 7 compatibility guards. |
| Hermetic suites | The post-review CPython 3.12.12 exact-lock run passed 726 tests: Core plus guards 110, Runtime 207, IBM Transpiler 139, Gym 97, and Docs 173. Intentional exclusions were 52 credential-bearing Transpiler integration cases and 3 network Docs integration cases. |
| Supported-matrix boundary | Independently resolved publishable environments on CPython 3.14.4 passed Core 103/103 and Runtime 207/207. This scout first exposed the import-time `nest_asyncio` failure and passed only after the event-loop ownership fix. Transpiler and Gym remain capped below 3.14 by upstream metadata. |
| Static/security checks | Ruff format and lint passed on 70 files; mypy passed on 34 source files; Bandit scanned all five source trees with no findings; workflow YAML parsed successfully. |
| Forbidden operations | No IBM token was supplied, no Runtime service was resolved, no Batch was constructed, and no primitive or QPU job was submitted. |
| Independent review | A separate assembly reviewer independently regenerated the lock, verified the digest, guards, Python 3.14 Core endpoint, and six package builds. Two documentation control-plane contradictions were fixed and re-reviewed; no actionable findings remain. |

Residual risks are deliberate and bounded: published ranges are broader than the exact scientific
lock; the matrix resolves representative current versions rather than every lower-bound
combination; and Batch/Runtime behavior is limited to signatures and synthetic objects because
remote construction and QPU activity are forbidden for W1-01.

## W1-01 Definition of Done

| DoD item | Status | Evidence |
|---|---|---|
| Canonical Python, Qiskit, Runtime, FastMCP, and related versions are documented. | `met` | Exact decision table and official source links above. |
| `uv.lock` is reproducible from a clean checkout. | `met` | Clean-copy regeneration was byte-identical; SHA-256 verification and a fresh all-package/all-group locked install passed. |
| CI verifies the canonical lock and supported Python matrix. | `met` | Workflow has an exact 3.12.12/hash/locked guard job plus isolated publish-metadata jobs for each declared Python row; YAML and representative 3.14 endpoints passed locally. |
| Runtime/PUB/QPY compatibility assumptions are covered by guard tests. | `met` | Seven targeted guards passed both the canonical environment and the clean installation. |
| Compatibility report identifies APIs requiring revalidation at the next upgrade. | `met` | Eight-item upgrade checklist above. |

**QPU calls made: none.**
