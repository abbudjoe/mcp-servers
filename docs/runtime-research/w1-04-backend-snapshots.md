# W1-04 Backend Snapshots Assembly Ledger

## Control plane

| Field | Value |
|---|---|
| Status | `successful` |
| Authoritative prompt | `qiskit_wrapper_workstream_build_package/prompts/W1-04_BACKEND_SNAPSHOTS.md` |
| Definition of Done | `qiskit_wrapper_workstream_build_package/04_DEFINITIONS_OF_DONE.md`, section W1-04 |
| Locked source contract | Qiskit 2.4.2 `BackendV2.target` and `Target` mappings; Qiskit IBM Runtime 0.45.1 `QiskitRuntimeService.backend(..., use_fractional_gates=...)` and `IBMBackend.properties(refresh=False, datetime=...)` |
| Target contract | An explicit backend and instance produce a versioned, complete snapshot of every physical qubit and every target instruction/qargs mapping, with current or timezone-aware historical properties, explicit fractional-gate mode, deterministic hashes, and software/backend provenance. |
| Forbidden paths | No primitive or QPU submission. No implicit backend selection. No network access without G3 authorization. |

## Final DoD checklist

| DoD item | Final status | Evidence |
|---|---|---|
| Snapshot covers all requested qubits and every target instruction/qubit tuple. | `met` | Exact count and set equality: FakeAthens 5/5 qubits and 43/43 tuples; FakeSherbrooke 127/127 qubits and 1036/1036 tuples, including all three global `qargs=None` entries. |
| Errors, durations, operational flags, faulty components, timestamps, and target structure are captured. | `met` | Typed qubit/instruction/target/backend/processor models retain source parameters and timestamps. Fake-property tests compare every raw qubit/gate parameter count. A fault regression proves every tuple touching a faulty qubit remains non-operational. |
| Historical property lookup accepts a timezone-aware timestamp. | `met` | Mock verifies exact `properties(refresh=False, datetime=requested_at)` forwarding and historical error/duration overlay; naive timestamps fail before backend resolution. |
| Snapshot has a stable content hash and package-version provenance. | `met` | Repeated content with different retrieval observations has identical hashes; content mutation changes both relevant hashes; recomputation and Qiskit/Runtime/wrapper/Python version fields are asserted. |
| Fractional-gate mode and incompatibilities are explicit. | `met` | `disabled`/`enabled`/`all` map to `False`/`True`/`None`; parameterized tests reject dynamic circuits, PEC, PEA, and gate twirling with enabled fractional gates. |
| Metadata-only integration tests are read-only and separately gated. | `met` | Test is marked `g3` and `integration`, requires explicit G3/backend/instance environment values, and calls only the named-backend metadata resolver. It remained skipped because G3 was not authorized. |

## Implementation mapping

- Typed snapshot submodels and versioned `BackendSnapshot` fields map to complete target/calibration structure and provenance.
- A dedicated MCP-independent snapshot builder maps locked target/properties APIs to the contract and owns canonical hashing.
- A Runtime resolver maps explicit instance/backend/fractional options to the locked service and historical properties calls.
- The MCP adapter exposes the resolver without backend selection or submission behavior.
- Fake, mocked historical, and optional G3 tests provide the required evidence.

## Evidence

### Changed contract and implementation

- `core/models.py` and the regenerated `backend-snapshot.schema.json` define the complete versioned wire contract.
- `core/snapshots.py` owns request validation, locked target/properties traversal, historical overlays, provenance capture, and canonical hashes without depending on MCP.
- `ibm_runtime.py`, `server.py`, and `profiles.py` expose an allowlisted metadata-only tool while preserving explicit instance/backend ownership.
- Legacy calibration defaults no longer sample the first ten qubits or first five edges; only an explicitly requested subset is partial.
- `tests/test_backend_snapshots.py` supplies fake-backend completeness, history, hashing, mode-validation, fault propagation, and G3 coverage.

### Completeness artifacts

| Backend | Qubits | Target tuples | Global tuples | Target hash | Snapshot hash |
|---|---:|---:|---|---|---|
| `fake_athens` | 5/5 | 43/43 | none | `sha256:56998fc3e47af9e30eb14c33bdd1f51dbe70d6bfcf5675fcfd5f3b6e223d097f` | `sha256:1fc349f412f6ff35c4c4a03d6a43d87dc8846000a144358220c083b4f57521a8` |
| `fake_sherbrooke` | 127/127 | 1036/1036 | `for_loop`, `if_else`, `switch_case` | `sha256:99358c8b59a780674aa4e6727309f16dbcdd8342d3da9267377e535d00329c00` | `sha256:d834b7b613543f825169661c24222ea13ee3fb9025852bc77fc01d47a13ac6d6` |

### Assembly gates

1. Initial focused smoke: 45 passed, one G3-skipped.
2. Initial full Runtime suite: 238 passed, one G3-skipped.
3. Spec-conformance review found a valid operational-state composition bug: provider gate status could overwrite a faulty-qubit result. The implementation now requires both states; the new regression passes.
4. Rereview found only missing proof for global `qargs=None` entries. FakeSherbrooke exact-set/count evidence was added and passed.
5. Final subagent review: clean; every DoD item classified `met`; no primitive, submission, implicit-selection, network, cloud, or QPU path found.
6. Post-review evidence: `uv run --locked --python 3.12 pytest qiskit-ibm-runtime-mcp-server/tests -q` — 241 passed, one G3-skipped.
7. Post-review quality: schema regeneration, Ruff check/format, mypy, Bandit, and `git diff --check` all passed.

No 1024-step scout applies to this deterministic metadata item. The item-specific evidence run is the exact fake-target completeness comparison above. No network or QPU call was made.
