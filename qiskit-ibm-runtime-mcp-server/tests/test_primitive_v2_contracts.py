# This code is part of Qiskit.
#
# (C) Copyright IBM 2026.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Golden and contract tests for W1-06 locked Primitive V2 semantics."""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import numpy as np
import pytest
from pydantic import ValidationError
from qiskit import QuantumCircuit, qpy
from qiskit.circuit import ParameterVector
from qiskit.primitives.containers import (
    BitArray,
    DataBin,
    PrimitiveResult,
    PubResult,
    SamplerPubResult as QiskitSamplerPubResult,
)
from qiskit_ibm_runtime.execution_span import DoubleSliceSpan, ExecutionSpans

from qiskit_ibm_runtime_mcp_server.core import (
    ArtifactRef,
    EstimatorPubSpec,
    LocalArtifactCAS,
    ParameterBindings,
    PauliObservables,
    PrimitiveContractError,
    SamplerPubSpec,
    SparsePauliHamiltonian,
    canonical_json,
    ingest_circuit,
    parse_primitive_result,
    prepare_estimator_pubs,
    prepare_sampler_pubs,
)
from qiskit_ibm_runtime_mcp_server.core.primitives import (
    _submit_estimator_pubs_unchecked,
    _submit_sampler_pubs_unchecked,
)
from qiskit_ibm_runtime_mcp_server.core import primitives as primitive_module


FIXTURES = Path(__file__).with_name("fixtures") / "primitive_v2"


def _artifact(circuit: QuantumCircuit, sink: LocalArtifactCAS):
    payload = io.BytesIO()
    qpy.dump(circuit, payload)
    return ingest_circuit(payload.getvalue(), circuit_format="qpy", sink=sink).artifact


def _parameterized_artifact(sink: LocalArtifactCAS):
    parameters = ParameterVector("theta", 2)
    circuit = QuantumCircuit(2)
    circuit.ry(parameters[0], 0)
    circuit.rz(parameters[1], 1)
    return _artifact(circuit, sink)


def _bindings(shape: list[int], values: Any) -> ParameterBindings:
    return ParameterBindings(
        schema_version="1.0",
        parameter_names=["theta[0]", "theta[1]"],
        shape=shape,
        values=values,
    )


class RecordingPrimitive:
    def __init__(self) -> None:
        self.calls: list[list[Any]] = []
        self.job = object()

    def run(self, pubs: list[Any]) -> object:
        self.calls.append(pubs)
        return self.job


def test_primitive_parser_rejects_invalid_envelope_boundaries(tmp_path: Path) -> None:
    """Envelope identity, count, threshold, and primitive checks fail early."""
    sink = LocalArtifactCAS(tmp_path / "cas")
    empty = PrimitiveResult([], metadata={})
    cases = (
        ({"primitive": "unsupported"}, object(), "unsupported primitive kind"),
        ({"threshold_bytes": -1}, object(), "threshold_bytes"),
        (
            {"pub_ids": (), "expected_pub_shapes": ((),)},
            empty,
            "identities and expected shapes",
        ),
        (
            {"pub_ids": ("one",), "expected_pub_shapes": ((),)},
            empty,
            "returned 0 PUBs",
        ),
        (
            {
                "pub_ids": ("duplicate", "duplicate"),
                "expected_pub_shapes": ((), ()),
            },
            [object(), object()],
            "pub_id values must be unique",
        ),
    )
    defaults: dict[str, Any] = {
        "primitive": "sampler",
        "pub_ids": (),
        "expected_pub_shapes": (),
        "job_id": "job",
        "backend_name": "backend",
        "sink": sink,
        "threshold_bytes": 1024,
    }
    for overrides, result, message in cases:
        with pytest.raises(PrimitiveContractError, match=message):
            parse_primitive_result(result, **(defaults | overrides))


def test_primitive_helper_error_branches_are_fail_closed(tmp_path: Path) -> None:
    """Metadata, shaped values, PUB identity, and artifact flattening are guarded."""
    sink = LocalArtifactCAS(tmp_path / "cas")
    with pytest.raises(PrimitiveContractError, match="at least one PUB"):
        primitive_module._require_unique_pubs([])  # noqa: SLF001
    duplicate = [SimpleNamespace(pub_id="same"), SimpleNamespace(pub_id="same")]
    with pytest.raises(PrimitiveContractError, match="must be unique"):
        primitive_module._require_unique_pubs(duplicate)  # type: ignore[arg-type] # noqa: SLF001

    with pytest.raises(TypeError, match="keys must be strings"):
        primitive_module._metadata_json(  # noqa: SLF001
            {1: "value"}, sink=sink, threshold_bytes=1024
        )
    assert primitive_module._metadata_json(  # noqa: SLF001
        ("a", ["b"]), sink=sink, threshold_bytes=1024
    ) == ["a", ["b"]]
    with pytest.raises(PrimitiveContractError, match="metadata must be a JSON object"):
        primitive_module._safe_metadata(  # noqa: SLF001
            "not-an-object", name="test", sink=sink, threshold_bytes=1024
        )
    with pytest.raises(PrimitiveContractError, match="homogeneous"):
        primitive_module._shaped_result(  # noqa: SLF001
            np.asarray([object()], dtype=object),
            sink=sink,
            threshold_bytes=1024,
            kind="object-array",
        )

    artifact_value = primitive_module._artifact_value(  # noqa: SLF001
        np.arange(32), sink=sink, threshold_bytes=0, kind="forced-artifact"
    )
    with pytest.raises(PrimitiveContractError, match="artifact-backed"):
        primitive_module.inline_value(artifact_value)
    inline = primitive_module._artifact_value(  # noqa: SLF001
        "small", sink=sink, threshold_bytes=1024, kind="inline-value"
    )
    assert primitive_module.inline_value(inline) == "small"


def test_estimator_parser_rejects_missing_or_misaligned_fields(tmp_path: Path) -> None:
    """Estimator DataBins require values, uncertainty, and aligned shapes."""
    sink = LocalArtifactCAS(tmp_path / "cas")

    def pub_result(shape: tuple[int, ...], **fields: Any) -> Any:
        data = SimpleNamespace(shape=shape, items=lambda: fields.items())
        return SimpleNamespace(data=data, metadata={})

    with pytest.raises(PrimitiveContractError, match="missing required DataBin key"):
        primitive_module._parse_estimator_pub(  # noqa: SLF001
            pub_result(()),
            pub_id="missing",
            pub_index=0,
            expected_shape=(),
            sink=sink,
            threshold_bytes=1024,
        )
    with pytest.raises(PrimitiveContractError, match="neither stds"):
        primitive_module._parse_estimator_pub(  # noqa: SLF001
            pub_result((), evs=np.asarray(0.5)),
            pub_id="no-error",
            pub_index=0,
            expected_shape=(),
            sink=sink,
            threshold_bytes=1024,
        )
    with pytest.raises(PrimitiveContractError, match="shapes must match"):
        primitive_module._parse_estimator_pub(  # noqa: SLF001
            pub_result((2,), evs=np.asarray([0.5]), stds=np.asarray([0.1])),
            pub_id="misaligned",
            pub_index=0,
            expected_shape=(2,),
            sink=sink,
            threshold_bytes=1024,
        )


def test_sampler_scalar_vector_and_multidimensional_pubs_are_coerced_in_order(
    tmp_path: Path,
) -> None:
    sink = LocalArtifactCAS(tmp_path / "cas")
    circuit = _parameterized_artifact(sink)
    specs = [
        SamplerPubSpec(
            schema_version="1.0",
            pub_id="scalar",
            circuit=circuit,
            parameter_values=_bindings([], [0.1, 0.2]),
            shots=16,
        ),
        SamplerPubSpec(
            schema_version="1.0",
            pub_id="vector",
            circuit=circuit,
            parameter_values=_bindings([2], [[0.1, 0.2], [0.3, 0.4]]),
            shots=32,
        ),
        SamplerPubSpec(
            schema_version="1.0",
            pub_id="matrix",
            circuit=circuit,
            parameter_values=_bindings([2, 1], [[[0.1, 0.2]], [[0.3, 0.4]]]),
            shots=64,
        ),
    ]

    prepared = prepare_sampler_pubs(specs, sink=sink)
    assert [pub.shape for pub in prepared] == [(), (2,), (2, 1)]
    assert [pub.shots for pub in prepared] == [16, 32, 64]

    runner = RecordingPrimitive()
    submitted = _submit_sampler_pubs_unchecked(runner, specs, sink=sink)
    assert len(runner.calls) == 1
    assert runner.calls[0][0].parameter_values.as_array().tolist() == [0.1, 0.2]
    assert submitted.pub_ids == ("scalar", "vector", "matrix")
    assert submitted.pub_shapes == ((), (2,), (2, 1))
    assert submitted.job is runner.job


def test_estimator_separate_observables_and_hamiltonian_keep_distinct_shapes(
    tmp_path: Path,
) -> None:
    sink = LocalArtifactCAS(tmp_path / "cas")
    circuit = _parameterized_artifact(sink)
    specs = [
        EstimatorPubSpec(
            schema_version="1.0",
            pub_id="separate",
            circuit=circuit,
            observables=PauliObservables(
                schema_version="1.0",
                kind="pauli_observables",
                shape=[2],
                values=["ZZ", "XX"],
            ),
            parameter_values=_bindings([], [0.1, 0.2]),
            precision=0.01,
        ),
        EstimatorPubSpec(
            schema_version="1.0",
            pub_id="hamiltonian",
            circuit=circuit,
            observables=SparsePauliHamiltonian(
                schema_version="1.0",
                kind="sparse_pauli_hamiltonian",
                terms=[("ZZ", 0.5), ("XX", -0.3)],
            ),
            parameter_values=_bindings([], [0.3, 0.4]),
            precision=0.02,
        ),
        EstimatorPubSpec(
            schema_version="1.0",
            pub_id="broadcast-matrix",
            circuit=circuit,
            observables=PauliObservables(
                schema_version="1.0",
                kind="pauli_observables",
                shape=[2, 1],
                values=[["ZZ"], ["XX"]],
            ),
            parameter_values=_bindings([1, 2], [[[0.1, 0.2], [0.3, 0.4]]]),
            precision=None,
        ),
    ]

    prepared = prepare_estimator_pubs(specs, sink=sink)
    assert [pub.shape for pub in prepared] == [(2,), (), (2, 2)]
    assert prepared[0].observables.shape == (2,)
    assert prepared[1].observables.shape == ()

    runner = RecordingPrimitive()
    submitted = _submit_estimator_pubs_unchecked(runner, specs, sink=sink)
    assert len(runner.calls) == 1
    assert submitted.pub_ids == ("separate", "hamiltonian", "broadcast-matrix")
    assert submitted.pub_shapes == ((2,), (), (2, 2))


def test_parameter_identity_and_broadcast_fail_before_submission(
    tmp_path: Path,
) -> None:
    sink = LocalArtifactCAS(tmp_path / "cas")
    circuit = _parameterized_artifact(sink)
    with pytest.raises(ValidationError, match="deterministic order"):
        SamplerPubSpec(
            schema_version="1.0",
            pub_id="wrong-order",
            circuit=circuit,
            parameter_values=ParameterBindings(
                schema_version="1.0",
                parameter_names=["theta[1]", "theta[0]"],
                shape=[],
                values=[0.1, 0.2],
            ),
            shots=10,
        )
    incompatible = EstimatorPubSpec(
        schema_version="1.0",
        pub_id="incompatible",
        circuit=circuit,
        observables=PauliObservables(
            schema_version="1.0",
            kind="pauli_observables",
            shape=[2],
            values=["ZZ", "XX"],
        ),
        parameter_values=_bindings([3], [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]),
        precision=None,
    )
    with pytest.raises(PrimitiveContractError, match="do not broadcast"):
        prepare_estimator_pubs([incompatible], sink=sink)


def _sampler_result_fixture() -> PrimitiveResult[Any]:
    scalar_a = BitArray.from_samples(["0", "1"], num_bits=1)
    scalar_b = BitArray.from_samples(["00", "11"], num_bits=2)
    vector = BitArray(np.asarray([[[0], [1]], [[1], [1]]], dtype=np.uint8), num_bits=1)
    matrix = BitArray(
        np.asarray(
            [
                [[[0], [1]], [[1], [0]]],
                [[[1], [1]], [[0], [0]]],
            ],
            dtype=np.uint8,
        ),
        num_bits=1,
    )
    return PrimitiveResult(
        [
            QiskitSamplerPubResult(
                DataBin(
                    alpha=scalar_a,
                    beta=scalar_b,
                    future_scalar={"calibration": "v2"},
                ),
                metadata={"case": "scalar-multi-register"},
            ),
            QiskitSamplerPubResult(
                DataBin(shape=(2,), meas=vector, future_vector=np.asarray([10, 20])),
                metadata={"case": "vector"},
            ),
            QiskitSamplerPubResult(
                DataBin(shape=(2, 2), meas=matrix),
                metadata={"case": "multidimensional"},
            ),
        ],
        metadata={"primitive_version": 2, "fixture": "sampler"},
    )


def _estimator_result_fixture() -> PrimitiveResult[Any]:
    return PrimitiveResult(
        [
            PubResult(
                DataBin(
                    evs=np.asarray(0.5),
                    ensemble_standard_error=np.asarray(0.02),
                    future_scalar={"calibration": "v2"},
                ),
                metadata={"case": "scalar-hamiltonian"},
            ),
            PubResult(
                DataBin(
                    shape=(2,),
                    evs=np.asarray([0.1, 0.2]),
                    stds=np.asarray([0.01, 0.02]),
                ),
                metadata={"case": "vector-observables"},
            ),
            PubResult(
                DataBin(
                    shape=(2, 2),
                    evs=np.asarray([[0.1, 0.2], [0.3, 0.4]]),
                    stds=np.asarray([[0.01, 0.02], [0.03, 0.04]]),
                    future_matrix=np.asarray([[1, 2], [3, 4]]),
                ),
                metadata={"case": "broadcast-matrix"},
            ),
        ],
        metadata={"primitive_version": 2, "fixture": "estimator"},
    )


@pytest.mark.parametrize(
    ("primitive", "result", "pub_ids", "shapes", "golden_name"),
    [
        (
            "sampler",
            _sampler_result_fixture,
            ["s-scalar", "s-vector", "s-matrix"],
            [[], [2], [2, 2]],
            "sampler-result-golden.json",
        ),
        (
            "estimator",
            _estimator_result_fixture,
            ["e-scalar", "e-vector", "e-matrix"],
            [[], [2], [2, 2]],
            "estimator-result-golden.json",
        ),
    ],
)
def test_complete_multi_pub_results_match_golden_fixtures(
    tmp_path: Path,
    primitive: str,
    result: Any,
    pub_ids: list[str],
    shapes: list[list[int]],
    golden_name: str,
) -> None:
    sink = LocalArtifactCAS(tmp_path / "cas")
    envelope = parse_primitive_result(
        result(),
        primitive=primitive,
        pub_ids=pub_ids,
        expected_pub_shapes=shapes,
        job_id=f"job-{primitive}",
        backend_name="ibm_fixture",
        sink=sink,
        threshold_bytes=1_000_000,
        actual_qpu_seconds=1.25,
    )
    expected = json.loads((FIXTURES / golden_name).read_text(encoding="utf-8"))
    assert envelope.model_dump(mode="json") == expected


def test_large_known_and_future_arrays_use_artifact_sink(tmp_path: Path) -> None:
    sink = LocalArtifactCAS(tmp_path / "cas")
    envelope = parse_primitive_result(
        _estimator_result_fixture(),
        primitive="estimator",
        pub_ids=["e-scalar", "e-vector", "e-matrix"],
        expected_pub_shapes=[[], [2], [2, 2]],
        job_id="job-artifacts",
        backend_name="ibm_fixture",
        sink=sink,
        threshold_bytes=0,
    )
    matrix = envelope.pub_results[2]
    assert isinstance(matrix.expectation_values.value, ArtifactRef)
    assert matrix.expectation_values.value.metadata["shape"] == [2, 2]
    assert matrix.expectation_values.value.metadata["dtype"] == "float64"
    assert isinstance(matrix.extensions["future_matrix"], ArtifactRef)
    assert json.loads(
        sink.get_bytes(matrix.extensions["future_matrix"]).decode("utf-8")
    ) == [[1, 2], [3, 4]]

    sampler = parse_primitive_result(
        _sampler_result_fixture(),
        primitive="sampler",
        pub_ids=["s-scalar", "s-vector", "s-matrix"],
        expected_pub_shapes=[[], [2], [2, 2]],
        job_id="job-sampler-artifacts",
        backend_name="ibm_fixture",
        sink=sink,
        threshold_bytes=0,
    )
    register = sampler.pub_results[2].registers[0]
    assert isinstance(register.packed_bytes, ArtifactRef)
    assert isinstance(register.counts_by_location, ArtifactRef)
    assert isinstance(register.bitstrings_by_location, ArtifactRef)
    assert isinstance(register.quasi_distributions_by_location, ArtifactRef)


def test_large_execution_span_masks_use_artifact_sink(tmp_path: Path) -> None:
    sink = LocalArtifactCAS(tmp_path / "cas")
    result = _sampler_result_fixture()
    start = datetime(2026, 7, 14, 12, tzinfo=timezone.utc)
    span = DoubleSliceSpan(
        start,
        start + timedelta(seconds=2),
        {0: ((2, 3), slice(0, 2), slice(1, 3))},
    )
    result_with_spans = PrimitiveResult(
        list(result),
        metadata={"execution": {"execution_spans": ExecutionSpans([span])}},
    )

    envelope = parse_primitive_result(
        result_with_spans,
        primitive="sampler",
        pub_ids=["s-scalar", "s-vector", "s-matrix"],
        expected_pub_shapes=[[], [2], [2, 2]],
        job_id="job-span-artifacts",
        backend_name="ibm_fixture",
        sink=sink,
        threshold_bytes=0,
    )

    mask = envelope.job_metadata["execution"]["execution_spans"]["spans"][0]["masks"][
        "0"
    ]
    artifact = ArtifactRef.model_validate(mask)
    assert artifact.kind == "runtime-execution-span-mask:0"
    assert artifact.metadata["shape"] == [2, 3]
    assert artifact.metadata["dtype"] == "bool"
    assert json.loads(sink.get_bytes(artifact)) == [
        [False, True, True],
        [False, True, True],
    ]


def test_empty_execution_spans_match_canonical_metadata_contract(
    tmp_path: Path,
) -> None:
    sink = LocalArtifactCAS(tmp_path / "cas")
    result = _sampler_result_fixture()
    result_with_spans = PrimitiveResult(
        list(result),
        metadata={"execution_spans": ExecutionSpans([])},
    )

    envelope = parse_primitive_result(
        result_with_spans,
        primitive="sampler",
        pub_ids=["s-scalar", "s-vector", "s-matrix"],
        expected_pub_shapes=[[], [2], [2, 2]],
        job_id="job-empty-spans",
        backend_name="ibm_fixture",
        sink=sink,
        threshold_bytes=0,
    )

    assert envelope.job_metadata["execution_spans"] == json.loads(
        canonical_json(ExecutionSpans([]))
    )


def test_result_cardinality_and_shape_mismatches_fail_closed(tmp_path: Path) -> None:
    sink = LocalArtifactCAS(tmp_path / "cas")
    with pytest.raises(PrimitiveContractError, match="returned 3 PUBs for 2"):
        parse_primitive_result(
            _sampler_result_fixture(),
            primitive="sampler",
            pub_ids=["a", "b"],
            expected_pub_shapes=[[], [2]],
            job_id="job",
            backend_name="backend",
            sink=sink,
            threshold_bytes=100,
        )
    with pytest.raises(PrimitiveContractError, match="returned shape"):
        parse_primitive_result(
            _estimator_result_fixture(),
            primitive="estimator",
            pub_ids=["a", "b", "c"],
            expected_pub_shapes=[[1], [2], [2, 2]],
            job_id="job",
            backend_name="backend",
            sink=sink,
            threshold_bytes=100,
        )


@pytest.mark.asyncio
async def test_job_result_adapter_preserves_explicit_multi_pub_identity(
    tmp_path: Path,
) -> None:
    from qiskit_ibm_runtime_mcp_server.ibm_runtime import get_job_results

    backend = Mock(name="backend", name_attr="ibm_fixture")
    backend.name = "ibm_fixture"
    job = Mock()
    job.status.return_value = "DONE"
    job.backend.return_value = backend
    job.result.return_value = _estimator_result_fixture()
    job.metrics.return_value = {"usage": {"quantum_seconds": 1.25}}
    service = Mock()
    service.job.return_value = job

    with patch("qiskit_ibm_runtime_mcp_server.ibm_runtime.service", service):
        response = await get_job_results(
            "job-estimator",
            primitive="estimator",
            pub_ids=["e-scalar", "e-vector", "e-matrix"],
            pub_shapes=[[], [2], [2, 2]],
            artifact_directory=str(tmp_path / "artifacts"),
        )
        legacy_response = await get_job_results(
            "job-estimator",
            artifact_directory=str(tmp_path / "legacy-artifacts"),
        )

    assert response["status"] == "success"
    assert [pub["pub_id"] for pub in response["result"]["pub_results"]] == [
        "e-scalar",
        "e-vector",
        "e-matrix",
    ]
    assert "migration_warning" not in response
    assert legacy_response["status"] == "success"
    assert legacy_response["result"]["primitive"] == "estimator"
    assert [pub["pub_id"] for pub in legacy_response["result"]["pub_results"]] == [
        "legacy-pub-0",
        "legacy-pub-1",
        "legacy-pub-2",
    ]
    assert "migration_warning" in legacy_response
