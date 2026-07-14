# W1-06 Primitive V2 PUB and Result Contract Report

## Outcome

W1-06 implements a versioned, MCP-independent Primitive V2 contract for the locked
Qiskit 2.4.2 and Qiskit IBM Runtime 0.45.1 stack. The implementation performs no
QPU calls. Submission tests use recording doubles; result tests use Qiskit container
objects and checked-in golden JSON.

## Contract surface

- `ParameterBindings` names every circuit parameter in exact serialized-circuit order,
  records the PUB shape separately from the parameter axis, and rejects ragged or
  mismatched values.
- `PauliObservables` is a shaped collection of separate operators.
  `SparsePauliHamiltonian` is one scalar weighted operator. They are distinct tagged
  models and take distinct Qiskit coercion paths.
- `prepare_sampler_pubs` and `prepare_estimator_pubs` reconstruct circuits from verified
  artifact bytes, validate parameter identity, invoke the locked public PUB coercers,
  and compare the resulting shapes with the declared broadcast contract.
- `submit_sampler_pubs` and `submit_estimator_pubs` make one ordered `run(pubs)` call and
  return caller-owned PUB IDs and expected shapes alongside the job handle.
- `parse_primitive_result` requires ordered PUB IDs and expected shapes, rejects result
  cardinality or shape drift, and parses every PUB and every DataBin key.
- Sampler registers retain the DataBin/PUB shape, bit width, shot count, packed-byte shape
  and data, row-major counts, bitstrings, and quasi distributions. Multiple classical
  registers remain separate and ordered.
- Estimator results retain shaped/dtyped expectation values and the locked error form:
  `stds`, `ensemble_standard_error`, or both, plus PUB metadata and job metadata. This
  matches the IBM V2 output contract, where resilience can replace `stds` with the
  ensemble field: <https://quantum.cloud.ibm.com/docs/en/guides/estimator-input-output>.
- Unknown DataBin keys are retained in typed extension maps. Known and future large
  values cross the configurable `ArtifactSink` threshold without losing shape metadata.
- `get_job_results` accepts explicit primitive/PUB identity for complete retrieval.
  Calls that omit identity receive synthetic legacy IDs plus a migration warning.
- Legacy single-PUB submission helpers emit deprecation warnings. A legacy list of Pauli
  strings now remains a vector of separate observables; weighted pairs remain one
  Hamiltonian. Flat legacy parameter values bind one scalar location rather than adding
  an accidental length-one PUB axis.

## Fixture matrix

| Fixture | Primitive | PUB/result shape | Registers / observables | Multi-PUB | Extensions | Artifact gate |
|---|---|---:|---|---|---|---|
| `sampler-result-golden.json` PUB 0 | Sampler | scalar `[]` | `alpha`, `beta` BitArrays | Yes (index 0/3) | scalar mapping | Inline golden plus threshold-zero test |
| `sampler-result-golden.json` PUB 1 | Sampler | vector `[2]` | `meas` BitArray | Yes (index 1/3) | vector array | Inline golden plus threshold-zero test |
| `sampler-result-golden.json` PUB 2 | Sampler | matrix `[2,2]` | `meas` BitArray | Yes (index 2/3) | none | Packed/count/bitstring/quasi artifacts |
| `estimator-result-golden.json` PUB 0 | Estimator | scalar `[]` | weighted Hamiltonian result | Yes (index 0/3) | scalar mapping | Ensemble-only error covered |
| `estimator-result-golden.json` PUB 1 | Estimator | vector `[2]` | separate observables | Yes (index 1/3) | none | Inline golden |
| `estimator-result-golden.json` PUB 2 | Estimator | matrix `[2,2]` | observable `[2,1]` × parameter `[1,2]` broadcast | Yes (index 2/3) | matrix array | Known and extension arrays artifactized |
| Sampler PUB coercion matrix | Sampler | `[]`, `[2]`, `[2,1]` | named two-parameter bindings | One three-PUB call | n/a | No Runtime service |
| Estimator PUB coercion matrix | Estimator | `[2]`, `[]`, `[2,2]` | separate, Hamiltonian, multidimensional broadcast | One three-PUB call | n/a | No Runtime service |
| Negative contract fixtures | Both | ragged/name/order/broadcast/cardinality/shape mismatches | explicit errors | n/a | n/a | Fail before submission or flattening |

## Evidence

Pre-review correctness smoke:

```text
uv run --project qiskit-ibm-runtime-mcp-server pytest qiskit-ibm-runtime-mcp-server/tests -q
295 passed, 1 skipped

uv run ruff check qiskit-ibm-runtime-mcp-server/src qiskit-ibm-runtime-mcp-server/tests
All checks passed

uv run --project qiskit-ibm-runtime-mcp-server mypy qiskit-ibm-runtime-mcp-server/src
Success: no issues found in 14 source files
```

Post-review evidence also includes `7 passed` locked-stack compatibility guards, Ruff
check and format check, mypy with no issues in 14 source files, and Bandit exit 0. The
skipped backend snapshot integration case is pre-existing and is not part of W1-06. No
live Runtime primitive was instantiated and no QPU call occurred.

## DoD status

All seven W1-06 DoD items are `met`. Independent assembly spec-conformance review was
clean, and the post-review smoke and quality gates passed. W1-06 status is `successful`.
