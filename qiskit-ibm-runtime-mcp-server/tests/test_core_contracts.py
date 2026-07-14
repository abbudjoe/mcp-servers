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

"""Contract, compatibility, and security tests for Runtime data models."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from enum import Enum, IntEnum
from pathlib import Path

import numpy as np
import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel, ValidationError
from qiskit.primitives.containers import BitArray

from qiskit_ibm_runtime_mcp_server.core.artifacts import (
    ArtifactCollisionError,
    ArtifactIntegrityError,
    ArtifactPathError,
    LocalArtifactCAS,
    artifactize,
    content_id,
)
from qiskit_ibm_runtime_mcp_server.core.models import (
    ApprovalReceipt,
    ArtifactRef,
    BackendSnapshot,
    CircuitArtifact,
    EstimatorPubResult,
    EstimatorPubSpec,
    InlineJsonValue,
    PauliObservables,
    PrimitiveResultEnvelope,
    PUBLIC_MODELS,
    RuntimeUsage,
    SamplerPubResult,
    SamplerPubSpec,
    SamplerRegisterResult,
    SparsePauliHamiltonian,
    SubmissionPartition,
    SubmissionPlan,
)
from qiskit_ibm_runtime_mcp_server.core.schemas import (
    generated_schemas,
    schemas_directory,
)
from qiskit_ibm_runtime_mcp_server.core.serialization import (
    JsonConversionError,
    canonical_json,
    canonical_json_hash,
)


HASH_A = f"sha256:{'a' * 64}"
HASH_B = f"sha256:{'b' * 64}"
NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


class FutureState(Enum):
    READY = "ready"


class FutureCode(IntEnum):
    READY = 7


def _artifact_ref() -> ArtifactRef:
    return ArtifactRef(
        schema_version="1.0",
        artifact_id=HASH_A,
        kind="circuit",
        media_type="application/qpy",
        size_bytes=128,
        storage_uri="s3://research-artifacts/circuits/example.qpy",
    )


def _circuit() -> CircuitArtifact:
    return CircuitArtifact(
        schema_version="1.0",
        artifact=_artifact_ref(),
        format="qpy",
        circuit_hash=HASH_B,
        num_qubits=2,
        num_clbits=2,
        size=3,
        depth=2,
        parameter_names=["theta"],
        qiskit_version="2.4.2",
        qpy_version=17,
        layout={"physical_qubits": [0, 1]},
    )


def _public_instances() -> list[object]:
    sampler_pub = SamplerPubSpec(
        schema_version="1.0",
        pub_id="sampler-0",
        circuit=_circuit(),
        parameter_values=[[0.25]],
        shots=100,
    )
    estimator_pub = EstimatorPubSpec(
        schema_version="1.0",
        pub_id="estimator-0",
        circuit=_circuit(),
        observables=PauliObservables(
            schema_version="1.0", kind="pauli_observables", values=["ZZ", "XX"]
        ),
        parameter_values=[[0.25]],
        precision=0.01,
    )
    partition = SubmissionPartition(
        schema_version="1.0", partition_id="part-0", pub_ids=["sampler-0"]
    )
    sampler_register = SamplerRegisterResult(
        schema_version="1.0",
        register_name="meas",
        pub_shape=[],
        num_shots=100,
        num_bits=2,
        counts_by_location=[{"00": 50, "11": 50}],
    )
    sampler_result = SamplerPubResult(
        schema_version="1.0",
        pub_id="sampler-0",
        pub_index=0,
        registers=[sampler_register],
    )
    estimator_result = EstimatorPubResult(
        schema_version="1.0",
        pub_id="estimator-0",
        pub_index=0,
        expectation_values=InlineJsonValue(
            schema_version="1.0",
            kind="inline_json",
            value=np.array([0.5, -0.25]),
        ),
        standard_deviations=InlineJsonValue(
            schema_version="1.0", kind="inline_json", value=np.array([0.1, 0.2])
        ),
    )
    usage = RuntimeUsage(schema_version="1.0", quantum_seconds=1.25, job_id="job-1")
    return [
        _artifact_ref(),
        _circuit(),
        BackendSnapshot(
            schema_version="1.0",
            backend_name="ibm_test",
            instance_id="crn:test",
            retrieved_at=NOW,
            properties_at=None,
            target_hash=HASH_A,
            snapshot_hash=HASH_B,
            qubits=[{"index": 0, "t1": np.float64(10.5)}],
            instructions=[{"name": "x", "qubits": [0]}],
            coupling_edges=[[0, 1]],
            faulty_qubits=[],
            faulty_instructions=[],
            software_versions={"qiskit": "2.4.2"},
        ),
        PauliObservables(
            schema_version="1.0", kind="pauli_observables", values=["ZZ", "XX"]
        ),
        SparsePauliHamiltonian(
            schema_version="1.0",
            kind="sparse_pauli_hamiltonian",
            terms=[("ZZ", 0.5), ("XX", -0.3)],
        ),
        sampler_pub,
        estimator_pub,
        partition,
        SubmissionPlan(
            schema_version="1.0",
            plan_id="plan-1",
            plan_hash=HASH_A,
            instance_id="crn:test",
            backend_name="ibm_test",
            primitive="sampler",
            pubs=[sampler_pub],
            resolved_options={"max_execution_time": 60},
            partitions=[partition],
            estimated_qpu_seconds=2.5,
            maximum_execution_seconds=60,
        ),
        ApprovalReceipt(
            schema_version="1.0",
            plan_hash=HASH_A,
            approved_at=NOW,
            expires_at=NOW + timedelta(hours=1),
            max_qpu_seconds=60,
            allowed_instance_ids=["crn:test"],
            allowed_backends=["ibm_test"],
        ),
        usage,
        sampler_register,
        sampler_result,
        InlineJsonValue(
            schema_version="1.0", kind="inline_json", value={"future": [1, 2]}
        ),
        estimator_result,
        PrimitiveResultEnvelope(
            schema_version="1.0",
            primitive="sampler",
            job_id="job-1",
            backend_name="ibm_test",
            pub_results=[sampler_result],
            job_metadata={"status": "DONE"},
            actual_qpu_seconds=1.25,
            usage=usage,
        ),
    ]


def test_every_public_model_has_a_published_valid_schema() -> None:
    generated = generated_schemas()
    published = sorted(schemas_directory().glob("*.schema.json"))

    assert len(generated) == len(PUBLIC_MODELS)
    assert {path.name for path in published} == set(generated)
    for path in published:
        checked_in = json.loads(path.read_text(encoding="utf-8"))
        assert checked_in == generated[path.name]
        assert checked_in["x-schema-version"] == "1.0"
        Draft202012Validator.check_schema(checked_in)


def test_every_public_model_round_trips_and_validates_against_schema() -> None:
    instances = _public_instances()

    assert {type(instance) for instance in instances} == set(PUBLIC_MODELS)
    for instance in instances:
        model_type = type(instance)
        payload = instance.model_dump(mode="json")
        filename = next(
            name
            for name, schema in generated_schemas().items()
            if schema["title"] == model_type.__name__
        )
        Draft202012Validator(generated_schemas()[filename]).validate(payload)
        restored = model_type.model_validate_json(instance.model_dump_json())
        assert restored.model_dump(mode="json") == payload


def test_schema_version_is_required_and_rejects_unsupported_versions() -> None:
    instances = _public_instances()
    schemas = generated_schemas()

    for instance in instances:
        model_type = type(instance)
        payload = instance.model_dump(mode="json")
        schema = next(
            item for item in schemas.values() if item["title"] == model_type.__name__
        )
        assert "schema_version" in schema["required"]

        missing = {
            key: value for key, value in payload.items() if key != "schema_version"
        }
        with pytest.raises(ValidationError):
            model_type.model_validate(missing)
        with pytest.raises(JsonSchemaValidationError):
            Draft202012Validator(schema).validate(missing)

        unsupported = {**payload, "schema_version": "2.0"}
        with pytest.raises(ValidationError):
            model_type.model_validate(unsupported)
        with pytest.raises(JsonSchemaValidationError):
            Draft202012Validator(schema).validate(unsupported)


@pytest.mark.parametrize(
    ("model_type", "payload", "schema_name"),
    [
        (
            PauliObservables,
            {"schema_version": "1.0", "values": ["ZZ"]},
            "pauli-observables.schema.json",
        ),
        (
            SparsePauliHamiltonian,
            {"schema_version": "1.0", "terms": [["ZZ", 1.0]]},
            "sparse-pauli-hamiltonian.schema.json",
        ),
        (
            InlineJsonValue,
            {"schema_version": "1.0", "value": [1, 2]},
            "inline-json-value.schema.json",
        ),
    ],
)
def test_tagged_forms_require_their_literal_tag(
    model_type: type[BaseModel], payload: dict[str, object], schema_name: str
) -> None:
    schema = generated_schemas()[schema_name]
    assert "kind" in schema["required"]
    with pytest.raises(ValidationError):
        model_type.model_validate(payload)
    with pytest.raises(JsonSchemaValidationError):
        Draft202012Validator(schema).validate(payload)

    wrong = {**payload, "kind": "wrong"}
    with pytest.raises(ValidationError):
        model_type.model_validate(wrong)
    with pytest.raises(JsonSchemaValidationError):
        Draft202012Validator(schema).validate(wrong)


def test_estimator_pub_requires_an_explicit_observable_tag() -> None:
    payload = {
        "schema_version": "1.0",
        "pub_id": "estimator-0",
        "circuit": _circuit().model_dump(mode="json"),
        "observables": {"schema_version": "1.0", "values": ["ZZ"]},
        "parameter_values": None,
        "precision": None,
    }
    with pytest.raises(ValidationError):
        EstimatorPubSpec.model_validate(payload)
    with pytest.raises(JsonSchemaValidationError):
        Draft202012Validator(
            generated_schemas()["estimator-pub-spec.schema.json"]
        ).validate(payload)


def test_unknown_extension_fields_are_preserved_and_json_safe() -> None:
    usage = RuntimeUsage(
        schema_version="1.0",
        quantum_seconds=np.float64(1.5),
        future_array=np.array([[1, 2], [3, 4]], dtype=np.int64),
        future_timestamp=datetime(
            2026, 7, 13, 8, 0, tzinfo=timezone(timedelta(hours=-4))
        ),
        future_state=FutureState.READY,
        future_code=FutureCode.READY,
    )

    payload = usage.model_dump(mode="json")
    assert payload["future_array"] == [[1, 2], [3, 4]]
    assert payload["future_timestamp"] == "2026-07-13T12:00:00.000000Z"
    assert payload["future_state"] == "ready"
    assert payload["future_code"] == 7
    assert (
        RuntimeUsage.model_validate_json(usage.model_dump_json()).model_dump(
            mode="json"
        )
        == payload
    )


def test_canonical_json_and_hash_are_deterministic_across_supported_types() -> None:
    first = {
        "z": np.array([np.int64(1), np.int64(2)]),
        "at": datetime(2026, 7, 13, 8, 0, tzinfo=timezone(timedelta(hours=-4))),
        "state": FutureState.READY,
    }
    second = {
        "state": "ready",
        "at": NOW,
        "z": [1, 2],
    }

    assert canonical_json(first) == canonical_json(second)
    assert canonical_json_hash(first) == canonical_json_hash(second)
    assert canonical_json_hash(first).startswith("sha256:")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (np.bool_(True), b"true"),
        (np.int8(-2), b"-2"),
        (np.uint64(2**63), str(2**63).encode()),
        (np.float32(1.5), b"1.5"),
        (np.float64(2.5), b"2.5"),
        (np.str_("future"), b'"future"'),
    ],
)
def test_canonical_json_handles_numpy_scalar_families(
    value: np.generic, expected: bytes
) -> None:
    assert canonical_json(value) == expected


def test_canonical_json_handles_or_rejects_numpy_longdouble_without_recursion() -> None:
    scalar = np.longdouble("1.25")
    array = np.asarray([scalar], dtype=np.longdouble)
    if scalar.dtype.itemsize > np.dtype(np.float64).itemsize:
        with pytest.raises(JsonConversionError, match="losslessly"):
            canonical_json(scalar)
        with pytest.raises(JsonConversionError, match="losslessly"):
            canonical_json(array)
    else:
        assert canonical_json(scalar) == b"1.25"
        assert canonical_json(array) == b"[1.25]"


@pytest.mark.parametrize("unit", ["D", "s", "us", "ns"])
def test_numpy_datetime64_has_a_unit_stable_iso_representation(unit: str) -> None:
    value = np.datetime64("2026-07-13T00:00:00", unit)
    assert canonical_json(value) == b'"2026-07-13T00:00:00.000000000Z"'
    assert canonical_json(np.asarray([value])) == b'["2026-07-13T00:00:00.000000000Z"]'

    with pytest.raises(JsonConversionError, match="NaT"):
        canonical_json(np.datetime64("NaT", unit))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {1: "bad"}, object()])
def test_canonical_json_rejects_non_json_values(value: object) -> None:
    with pytest.raises(JsonConversionError):
        canonical_json(value)


def test_observable_forms_cannot_be_ambiguously_interchanged() -> None:
    with pytest.raises(ValidationError):
        EstimatorPubSpec(
            schema_version="1.0",
            pub_id="ambiguous",
            circuit=_circuit(),
            observables=["ZZ", "XX"],
            parameter_values=None,
            precision=None,
        )


def test_plan_rejects_primitive_mismatch_and_partition_drift() -> None:
    estimator = EstimatorPubSpec(
        schema_version="1.0",
        pub_id="estimator-0",
        circuit=_circuit(),
        observables=PauliObservables(
            schema_version="1.0", kind="pauli_observables", values=["ZZ"]
        ),
        parameter_values=None,
        precision=None,
    )
    with pytest.raises(ValidationError, match="matching PUB specs"):
        SubmissionPlan(
            schema_version="1.0",
            plan_id="plan",
            plan_hash=HASH_A,
            instance_id="crn:test",
            backend_name="ibm_test",
            primitive="sampler",
            pubs=[estimator],
            resolved_options={},
            partitions=[
                SubmissionPartition(
                    schema_version="1.0", partition_id="p", pub_ids=["estimator-0"]
                )
            ],
            estimated_qpu_seconds=0,
            maximum_execution_seconds=60,
        )


def test_estimator_artifact_values_round_trip_as_typed_references() -> None:
    result = EstimatorPubResult(
        schema_version="1.0",
        pub_id="estimator-0",
        pub_index=0,
        expectation_values=_artifact_ref(),
        standard_deviations=InlineJsonValue(
            schema_version="1.0", kind="inline_json", value=[0.1]
        ),
    )

    restored = EstimatorPubResult.model_validate_json(result.model_dump_json())
    assert isinstance(restored.expectation_values, ArtifactRef)
    assert isinstance(restored.standard_deviations, InlineJsonValue)
    schema = generated_schemas()["estimator-pub-result.schema.json"]
    invalid = result.model_dump(mode="json")
    invalid["expectation_values"] = {"untyped": [1, 2, 3]}
    with pytest.raises(JsonSchemaValidationError):
        Draft202012Validator(schema).validate(invalid)


def test_sampler_register_preserves_locked_bitarray_shape_and_shots() -> None:
    packed = np.asarray(
        [
            [[0], [1], [0]],
            [[1], [1], [0]],
        ],
        dtype=np.uint8,
    )
    bit_array = BitArray(packed, num_bits=1)
    locations = list(np.ndindex(bit_array.shape))

    result = SamplerRegisterResult(
        schema_version="1.0",
        register_name="meas",
        pub_shape=list(bit_array.shape),
        num_shots=bit_array.num_shots,
        num_bits=bit_array.num_bits,
        counts_by_location=[bit_array.get_counts(location) for location in locations],
        bitstrings_by_location=[
            bit_array.get_bitstrings(location) for location in locations
        ],
    )

    assert result.pub_shape == [2]
    assert result.num_shots == 3
    assert len(result.counts_by_location or []) == 2
    assert SamplerRegisterResult.model_validate_json(result.model_dump_json()) == result

    with pytest.raises(ValidationError, match="one row-major entry"):
        SamplerRegisterResult(
            schema_version="1.0",
            register_name="meas",
            pub_shape=[2],
            num_shots=3,
            num_bits=1,
            counts_by_location=[{"0": 3}],
        )


def test_local_cas_round_trip_and_deduplication(tmp_path: Path) -> None:
    sink = LocalArtifactCAS(tmp_path / "cas")
    first = sink.put_bytes(
        b"payload", kind="test", media_type="application/octet-stream"
    )
    second = sink.put_bytes(
        b"payload", kind="test", media_type="application/octet-stream"
    )

    assert first.artifact_id == second.artifact_id
    assert first.storage_uri.startswith("file://")
    assert sink.get_bytes(first) == b"payload"


def test_local_cas_detects_digest_path_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import qiskit_ibm_runtime_mcp_server.core.artifacts as artifacts

    sink = LocalArtifactCAS(tmp_path / "cas")
    existing = sink.put_bytes(
        b"first", kind="test", media_type="application/octet-stream"
    )
    monkeypatch.setattr(artifacts, "content_id", lambda _: existing.artifact_id)

    with pytest.raises(ArtifactCollisionError):
        sink.put_bytes(b"different", kind="test", media_type="application/octet-stream")


def test_local_cas_rejects_traversal_symlinks_and_tampering(tmp_path: Path) -> None:
    sink = LocalArtifactCAS(tmp_path / "cas")
    invalid = ArtifactRef.model_construct(
        schema_version="1.0",
        artifact_id="sha256:../../outside",
        kind="test",
        media_type="application/octet-stream",
        size_bytes=0,
        storage_uri="cas://sha256/../../outside",
        metadata={},
    )
    with pytest.raises(ArtifactPathError):
        sink.get_bytes(invalid)

    blocked = b"blocked"
    target_name = f"sha256-{content_id(blocked).removeprefix('sha256:')}"
    outside_file = tmp_path / "outside"
    outside_file.write_bytes(blocked)
    (sink.root / target_name).symlink_to(outside_file)
    with pytest.raises(ArtifactCollisionError):
        sink.put_bytes(blocked, kind="test", media_type="application/octet-stream")

    safe_sink = LocalArtifactCAS(tmp_path / "safe-cas")
    artifact = safe_sink.put_bytes(
        b"original", kind="test", media_type="application/octet-stream"
    )
    digest = artifact.artifact_id.removeprefix("sha256:")
    stored_path = safe_sink.root / f"sha256-{digest}"
    stored_path.write_bytes(b"tampered")
    with pytest.raises(ArtifactIntegrityError):
        safe_sink.get_bytes(artifact)


def test_local_cas_directory_swap_cannot_escape_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import qiskit_ibm_runtime_mcp_server.core.artifacts as artifacts

    sink = LocalArtifactCAS(tmp_path / "cas")
    moved_root = tmp_path / "moved-cas"
    original_link = artifacts.os.link
    swapped = False

    def swap_before_link(*args: object, **kwargs: object) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            sink.root.rename(moved_root)
            sink.root.mkdir(mode=0o700)
        original_link(*args, **kwargs)

    monkeypatch.setattr(artifacts.os, "link", swap_before_link)
    with pytest.raises(ArtifactPathError, match="replaced"):
        sink.put_bytes(b"race", kind="test", media_type="application/octet-stream")

    assert not list(moved_root.glob("sha256-*"))
    assert not list(moved_root.glob(".incoming-*"))


def test_artifactize_enforces_configurable_byte_threshold(tmp_path: Path) -> None:
    sink = LocalArtifactCAS(tmp_path / "cas")
    value = {"samples": np.arange(20, dtype=np.int64)}
    encoded = canonical_json(value)

    inline = artifactize(value, sink, threshold_bytes=len(encoded))
    referenced = artifactize(
        value,
        sink,
        threshold_bytes=len(encoded) - 1,
        metadata={"encoding": "caller-cannot-override"},
    )

    assert isinstance(inline, InlineJsonValue)
    assert inline.value == {"samples": list(range(20))}
    assert isinstance(referenced, ArtifactRef)
    assert referenced.metadata["encoding"] == "canonical-json"
    assert sink.get_bytes(referenced) == encoded
    with pytest.raises(ValueError, match="non-negative"):
        artifactize(value, sink, threshold_bytes=-1)


def test_artifactize_composes_with_estimator_values_at_exact_threshold(
    tmp_path: Path,
) -> None:
    sink = LocalArtifactCAS(tmp_path / "cas")
    value = [0.5, -0.25]
    encoded = canonical_json(value)
    inline = artifactize(value, sink, threshold_bytes=len(encoded))
    referenced = artifactize(value, sink, threshold_bytes=len(encoded) - 1)

    inline_result = EstimatorPubResult(
        schema_version="1.0",
        pub_id="estimator-inline",
        pub_index=0,
        expectation_values=inline,
        standard_deviations=InlineJsonValue(
            schema_version="1.0", kind="inline_json", value=[0.1, 0.2]
        ),
    )
    referenced_result = EstimatorPubResult(
        schema_version="1.0",
        pub_id="estimator-artifact",
        pub_index=0,
        expectation_values=referenced,
        standard_deviations=InlineJsonValue(
            schema_version="1.0", kind="inline_json", value=[0.1, 0.2]
        ),
    )

    assert isinstance(inline_result.expectation_values, InlineJsonValue)
    assert isinstance(referenced_result.expectation_values, ArtifactRef)
    assert isinstance(
        EstimatorPubResult.model_validate_json(
            referenced_result.model_dump_json()
        ).expectation_values,
        ArtifactRef,
    )
