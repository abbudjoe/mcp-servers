# W1-05 Exact Circuit Boundary Assembly Ledger

## Control plane

| Field | Value |
|---|---|
| Status | `successful` |
| Authoritative prompt | `qiskit_wrapper_workstream_build_package/prompts/W1-05_EXACT_CIRCUIT_BOUNDARY.md` |
| Definition of Done | `qiskit_wrapper_workstream_build_package/04_DEFINITIONS_OF_DONE.md`, section W1-05 |
| Target contract | An approved serialized circuit is reconstructed from immutable, hash-bound bytes and either executed exactly, validated without mutation, or explicitly transpiled into a new artifact with complete provenance. |
| Forbidden paths | No QPU or primitive calls. No hidden pass manager in `exact` or `validate` mode. |

## Final DoD checklist

| DoD item | Final status | Evidence |
|---|---|---|
| Decoded-size, qubit, operation, register, and parameter limits are enforced. | `met` | Pre-parse spies prove oversized QPY/QASM payloads fail before parsing; structural-limit negatives cover every required dimension. |
| Multi-circuit QPY is never silently truncated. | `met` | QPY header cardinality is checked before `qpy.load`; a two-circuit payload is rejected explicitly. |
| `exact`, `validate`, and `transpile` are behaviorally distinct. | `met` | Mode tests cover required and contradictory arguments and prove only `transpile` can construct a pass manager. |
| ISA validation checks operations and physical qubit tuples without mutation. | `met` | Target positives and negatives cover fixed variants, recursive control flow, circuit width, unsupported operations, unsupported tuples, and custom operation definitions. |
| Circuit state and serialization provenance are preserved. | `met` | Exact QPY bytes, SHA-256, writer/reader versions, QPY version/encoding, layout, parameter order, registers, and metadata are recorded and round-tripped. |
| Explicit transpilation has complete provenance. | `met` | The output artifact binds source hash/artifact, backend snapshot target hash, compiler target hash, backend name, transpiler/options, and software versions. |
| Unsupported and forward-incompatible inputs fail closed. | `met` | Negative tests cover malformed/forward QPY, excessive sizes, unsupported operations and tuples, opaque target state, snapshot mismatch, and target drift. |
| Validation demonstrates hash stability. | `met` | Validation reports identical before/after circuit hashes; stored source bytes remain byte-for-byte unchanged. |

## Implementation mapping

- `core/circuits.py` owns bounded ingestion, immutable reconstruction, target identity, ISA validation, explicit modes, and transpilation.
- `core/models.py` owns typed circuit register, writer metadata, and provenance contracts.
- Checked-in JSON schemas and `core/__init__.py` keep the public contract synchronized.
- `tests/test_circuit_boundary.py` supplies semantic, metamorphic, pass-manager, and negative evidence.

## Architectural guarantees

- Encoded and decoded limits are enforced at the earliest observable boundary; structural limits follow immediately after parsing.
- QPY file cardinality and forward compatibility are inspected before deserialization.
- Parsed convenience objects are never approval authority. Every mode reconstructs from immutable bytes whose digest equals `CircuitArtifact.circuit_hash`.
- `ResolvedTarget` derives identity from one live backend and an authoritative `BackendSnapshot`; caller-supplied target names or hashes are not accepted independently.
- `BackendSnapshot.target_hash` retains the W1-04 content definition. A distinct `compiler_target_hash` includes compiler-visible semantics such as recursive custom-operation definitions.
- Validation uses target queries only and does not mutate or transpile the circuit.
- Transpilation reloads emitted QPY before artifact metadata, validation, and returned executable state are constructed.

## Assembly gates

1. Focused W1-05 smoke: 46 passed; focused Ruff and mypy passed.
2. Package-scoped coverage: `core/circuits.py` reached 92% branch coverage.
3. Initial review findings were repaired at their contracts: target ownership, circuit width, emitted-QPY reconstruction, fixed variants, and QASM writer identity.
4. Rereview findings were repaired: custom-definition semantics, post-reload artifact summaries, and distinct W1-04/compiler target hashes.
5. Final spec-conformance review: `PASS`; no actionable findings and every W1-05 DoD item classified `met`.
6. Post-review Runtime suite: 287 passed, 1 G3-skipped.
7. Post-review Ruff format/check, mypy, schema synchronization, coverage, and diff hygiene passed.

No QPU, primitive, network, cloud, or paid-compute call occurred.
