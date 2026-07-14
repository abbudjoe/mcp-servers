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

"""Contract, compatibility, and security tests for W1-03."""

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
from qiskit_ibm_runtime.execution_span import DoubleSliceSpan, ExecutionSpans

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
    ApprovedSubmission,
    ArtifactRef,
    BackendSnapshot,
    BatchExecutionLimits,
    BatchJobReceipt,
    BatchJobStatus,
    BatchJobUsage,
    BatchReference,
    BatchStatus,
    BatchSubmissionFailure,
    BatchSubmissionReceipt,
    BatchUsage,
    BudgetPolicy,
    CircuitArtifact,
    EstimatorPubResult,
    EstimatorPubSpec,
    InlineJsonValue,
    PauliObservables,
    ParameterBindings,
    PrimitiveResultEnvelope,
    PubExecutionEstimate,
    PubShape,
    PUBLIC_MODELS,
    RecoveredSubmissionStatus,
    RuntimeUsage,
    SamplerPubResult,
    SamplerPubSpec,
    ScheduledPubEstimate,
    SamplerRegisterResult,
    ShapedResultValue,
    SparsePauliHamiltonian,
    SubmissionPartition,
    SubmissionPlan,
    SubmissionKeyStatus,
    UsageReconciliation,
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
        circuit_hash=HASH_A,
        num_qubits=2,
        num_clbits=2,
        size=3,
        depth=2,
        parameter_names=["theta"],
        registers=[
            {"kind": "quantum", "name": "q", "size": 2, "bit_indices": [0, 1]},
            {"kind": "classical", "name": "c", "size": 2, "bit_indices": [0, 1]},
        ],
        metadata={"experiment": "fixture"},
        qiskit_version="2.4.2",
        reader_qiskit_version="2.4.2",
        qpy_version=17,
        qpy_symbolic_encoding="p",
        layout={"physical_qubits": [0, 1]},
        provenance={
            "transformation": "source",
            "software_versions": {"qiskit": "2.4.2"},
        },
    )


def _public_instances() -> list[object]:
    bindings = ParameterBindings(
        schema_version="1.0",
        parameter_names=["theta"],
        shape=[1],
        values=[[0.25]],
    )
    sampler_pub = SamplerPubSpec(
        schema_version="1.0",
        pub_id="sampler-0",
        circuit=_circuit(),
        parameter_values=bindings,
        shots=100,
    )
    estimator_pub = EstimatorPubSpec(
        schema_version="1.0",
        pub_id="estimator-0",
        circuit=_circuit(),
        observables=PauliObservables(
            schema_version="1.0",
            kind="pauli_observables",
            shape=[2],
            values=["ZZ", "XX"],
        ),
        parameter_values=bindings,
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
        packed_shape=[100, 1],
        packed_bytes=InlineJsonValue(
            schema_version="1.0", kind="inline_json", value=[[0]] * 100
        ),
        counts_by_location=InlineJsonValue(
            schema_version="1.0",
            kind="inline_json",
            value=[{"00": 50, "11": 50}],
        ),
        bitstrings_by_location=InlineJsonValue(
            schema_version="1.0",
            kind="inline_json",
            value=[["00"] * 50 + ["11"] * 50],
        ),
        quasi_distributions_by_location=InlineJsonValue(
            schema_version="1.0",
            kind="inline_json",
            value=[{"00": 0.5, "11": 0.5}],
        ),
    )
    sampler_result = SamplerPubResult(
        schema_version="1.0",
        pub_id="sampler-0",
        pub_index=0,
        data_bin_shape=[],
        registers=[sampler_register],
    )
    expectation_values = ShapedResultValue(
        schema_version="1.0",
        shape=[2],
        dtype="float64",
        value=InlineJsonValue(
            schema_version="1.0",
            kind="inline_json",
            value=np.array([0.5, -0.25]),
        ),
    )
    estimator_result = EstimatorPubResult(
        schema_version="1.0",
        pub_id="estimator-0",
        pub_index=0,
        data_bin_shape=[2],
        expectation_values=expectation_values,
        standard_deviations=ShapedResultValue(
            schema_version="1.0",
            shape=[2],
            dtype="float64",
            value=InlineJsonValue(
                schema_version="1.0", kind="inline_json", value=np.array([0.1, 0.2])
            ),
        ),
    )
    usage = RuntimeUsage(schema_version="1.0", quantum_seconds=1.25, job_id="job-1")
    batch_limits = BatchExecutionLimits(
        schema_version="1.0",
        max_jobs=2,
        max_pubs_per_job=10,
        max_estimated_qpu_seconds_per_job=60,
        max_execution_seconds_per_job=60,
        batch_max_time_seconds=600,
        ttl_margin_seconds=60,
    )
    batch_job = BatchJobStatus(
        schema_version="1.0",
        batch_id="batch-1",
        job_id="job-1",
        status="DONE",
        created_at=NOW,
        tags=("fixture",),
    )
    batch_status = BatchStatus(
        schema_version="1.0",
        batch_id="batch-1",
        status="Closed",
        accepting_jobs=False,
        maximum_time_seconds=600,
        interactive_timeout_seconds=60,
        started_at=NOW,
        closed_at=NOW + timedelta(minutes=1),
        observed_at=NOW + timedelta(minutes=1),
    )
    batch_job_receipt = BatchJobReceipt(
        schema_version="1.0",
        partition_id="part-0",
        job_id="job-1",
        pub_ids=("sampler-0",),
        submitted_at=NOW,
    )
    submission_receipt = BatchSubmissionReceipt(
        schema_version="1.0",
        submission_key="fixture-key",
        batch_id="batch-1",
        plan_hash=HASH_A,
        pub_ids=("sampler-0",),
        jobs=(batch_job_receipt,),
        state="submitted",
        reserved_at=NOW,
        completed_at=NOW,
    )
    return [
        _artifact_ref(),
        _circuit(),
        BackendSnapshot(
            schema_version="1.0",
            backend_name="ibm_test",
            instance_id="crn:test",
            retrieved_at=NOW,
            properties_at=None,
            properties_last_update=NOW,
            properties_available=True,
            fractional_gate_mode="disabled",
            backend_version="1.2.3",
            processor={
                "family": "Heron",
                "revision": "2",
                "segment": "A",
                "raw": {"family": "Heron", "revision": 2, "segment": "A"},
            },
            backend_status={
                "operational": True,
                "pending_jobs": 0,
                "status_message": "active",
            },
            target={
                "num_qubits": 2,
                "physical_qubits": [0, 1],
                "operation_names": ["x"],
                "global_operations": [],
                "dt": 5e-10,
                "granularity": 1,
                "min_length": 1,
                "pulse_alignment": 1,
                "acquire_alignment": 1,
                "concurrent_measurements": None,
            },
            target_hash=HASH_A,
            snapshot_hash=HASH_B,
            qubits=[
                {
                    "index": 0,
                    "operational": True,
                    "parameters": [
                        {"name": "T1", "value": np.float64(10.5), "unit": "us"}
                    ],
                },
                {"index": 1, "operational": True, "parameters": []},
            ],
            instructions=[
                {
                    "name": "x",
                    "qubits": [0],
                    "error": 0.001,
                    "duration": 6e-8,
                    "operational": True,
                    "operation_parameters": [],
                    "calibration_parameters": [],
                }
            ],
            coupling_edges=[[0, 1]],
            faulty_qubits=[],
            faulty_instructions=[],
            general_parameters=[],
            general_qlists=[],
            software_versions={"qiskit": "2.4.2"},
        ),
        PauliObservables(
            schema_version="1.0",
            kind="pauli_observables",
            shape=[2],
            values=["ZZ", "XX"],
        ),
        SparsePauliHamiltonian(
            schema_version="1.0",
            kind="sparse_pauli_hamiltonian",
            terms=[("ZZ", 0.5), ("XX", -0.3)],
        ),
        sampler_pub,
        estimator_pub,
        bindings,
        partition,
        SubmissionPlan(
            schema_version="1.0",
            plan_id="plan-1",
            submission_key="fixture-key",
            plan_hash=HASH_A,
            policy_hash=HASH_B,
            instance_id="crn:test",
            instance_plan_type="open",
            backend_name="ibm_test",
            target_hash=HASH_A,
            compiler_target_hash=HASH_B,
            primitive="sampler",
            pubs=[sampler_pub],
            pub_shapes=[
                PubShape(
                    schema_version="1.0",
                    pub_id="sampler-0",
                    parameter_shape=[1],
                    observable_shape=None,
                    result_shape=[1],
                    circuit_executions=1,
                )
            ],
            resolved_options={"max_execution_time": 60},
            treatments=[],
            partitions=[partition],
            scheduled_estimates=[
                ScheduledPubEstimate(
                    schema_version="1.0",
                    pub_id="sampler-0",
                    scheduled_circuit_seconds=0.001,
                    conservative_cycle_seconds=0.001,
                    circuit_executions=1,
                    physical_circuit_executions=1,
                    repetitions_per_execution=100,
                    treatment_multiplier=1,
                    estimated_qpu_seconds=2.5,
                )
            ],
            total_circuit_executions=1,
            estimated_qpu_seconds=2.5,
            maximum_execution_seconds=60,
            estimation_method="fixture",
            estimation_version="1.0",
            estimation_software_versions={"qiskit": "2.4.2"},
        ),
        PubShape(
            schema_version="1.0",
            pub_id="sampler-0",
            parameter_shape=[1],
            observable_shape=None,
            result_shape=[1],
            circuit_executions=1,
        ),
        ScheduledPubEstimate(
            schema_version="1.0",
            pub_id="sampler-0",
            scheduled_circuit_seconds=0.001,
            conservative_cycle_seconds=0.001,
            circuit_executions=1,
            physical_circuit_executions=1,
            repetitions_per_execution=100,
            treatment_multiplier=1,
            estimated_qpu_seconds=2.5,
        ),
        BudgetPolicy(
            schema_version="1.0",
            max_estimated_qpu_seconds=60,
            max_execution_seconds=60,
            max_jobs=2,
            max_pubs=10,
            max_circuits=10,
            max_partitions=2,
            max_pubs_per_job=10,
            max_shots_per_pub=1024,
            batch_max_time_seconds=600,
            approval_ttl_seconds=3600,
            allowed_instance_ids=("crn:test",),
            allowed_backends=("ibm_test",),
            permitted_primitives=("sampler",),
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
        batch_limits,
        PubExecutionEstimate(
            schema_version="1.0",
            pub_id="sampler-0",
            estimated_qpu_seconds=1.25,
        ),
        BatchReference(
            schema_version="1.0",
            batch_id="batch-1",
            instance_id="crn:test",
            backend_name="ibm_test",
            maximum_time_seconds=600,
            observed_at=NOW,
        ),
        batch_status,
        batch_job,
        BatchJobUsage(schema_version="1.0", job_id="job-1", quantum_seconds=1.25),
        BatchUsage(
            schema_version="1.0",
            batch_id="batch-1",
            batch_seconds=1.25,
            jobs=(
                BatchJobUsage(
                    schema_version="1.0", job_id="job-1", quantum_seconds=1.25
                ),
            ),
            retrieved_at=NOW,
        ),
        batch_job_receipt,
        BatchSubmissionFailure(
            schema_version="1.0",
            partition_id="part-1",
            error_type="RuntimeError",
            message="fixture failure",
            failed_at=NOW,
        ),
        submission_receipt,
        ApprovedSubmission(
            schema_version="1.0",
            plan_hash=HASH_A,
            estimated_qpu_seconds=2.5,
            approval_max_qpu_seconds=60,
            receipt=submission_receipt,
        ),
        UsageReconciliation(
            schema_version="1.0",
            plan_hash=HASH_A,
            estimated_qpu_seconds=2.5,
            approval_max_qpu_seconds=60,
            actual_qpu_seconds=1.25,
            batch_usage=BatchUsage(
                schema_version="1.0",
                batch_id="batch-1",
                batch_seconds=1.25,
                jobs=(
                    BatchJobUsage(
                        schema_version="1.0",
                        job_id="job-1",
                        quantum_seconds=1.25,
                    ),
                ),
                retrieved_at=NOW,
            ),
        ),
        RecoveredSubmissionStatus(
            schema_version="1.0",
            receipt=submission_receipt,
            batch=batch_status,
            jobs=(batch_job,),
            observed_at=NOW + timedelta(minutes=1),
        ),
        SubmissionKeyStatus(
            schema_version="1.0",
            submission_key="fixture-key",
            jobs=(batch_job,),
            observed_at=NOW,
        ),
        sampler_register,
        sampler_result,
        InlineJsonValue(
            schema_version="1.0", kind="inline_json", value={"future": [1, 2]}
        ),
        expectation_values,
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


def test_canonical_json_preserves_runtime_execution_spans() -> None:
    span = DoubleSliceSpan(
        NOW,
        NOW + timedelta(seconds=2),
        {0: ((2, 3), slice(0, 2), slice(1, 3))},
    )

    converted = json.loads(canonical_json(ExecutionSpans([span])))

    assert converted == {
        "$runtime_type": "ExecutionSpans",
        "start": "2026-07-13T12:00:00.000000Z",
        "stop": "2026-07-13T12:00:02.000000Z",
        "duration": 2.0,
        "pub_idxs": [0],
        "spans": [
            {
                "$runtime_type": "DoubleSliceSpan",
                "start": "2026-07-13T12:00:00.000000Z",
                "stop": "2026-07-13T12:00:02.000000Z",
                "duration": 2.0,
                "size": 4,
                "pub_idxs": [0],
                "masks": {
                    "0": [[False, True, True], [False, True, True]],
                },
            }
        ],
    }


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
            schema_version="1.0",
            kind="pauli_observables",
            shape=[1],
            values=["ZZ"],
        ),
        parameter_values=ParameterBindings(
            schema_version="1.0",
            parameter_names=["theta"],
            shape=[],
            values=[0.25],
        ),
        precision=None,
    )
    with pytest.raises(ValidationError, match="matching PUB specs"):
        SubmissionPlan(
            schema_version="1.0",
            plan_id="plan",
            submission_key="negative-key",
            plan_hash=HASH_A,
            policy_hash=HASH_B,
            instance_id="crn:test",
            instance_plan_type="open",
            backend_name="ibm_test",
            target_hash=HASH_A,
            compiler_target_hash=HASH_B,
            primitive="sampler",
            pubs=[estimator],
            pub_shapes=[
                PubShape(
                    schema_version="1.0",
                    pub_id="estimator-0",
                    parameter_shape=[],
                    observable_shape=[1],
                    result_shape=[1],
                    circuit_executions=1,
                )
            ],
            resolved_options={},
            treatments=[],
            partitions=[
                SubmissionPartition(
                    schema_version="1.0", partition_id="p", pub_ids=["estimator-0"]
                )
            ],
            scheduled_estimates=[
                ScheduledPubEstimate(
                    schema_version="1.0",
                    pub_id="estimator-0",
                    scheduled_circuit_seconds=0.001,
                    conservative_cycle_seconds=0.001,
                    circuit_executions=1,
                    physical_circuit_executions=1,
                    repetitions_per_execution=100,
                    treatment_multiplier=1,
                    estimated_qpu_seconds=0.1,
                )
            ],
            total_circuit_executions=1,
            estimated_qpu_seconds=0.1,
            maximum_execution_seconds=60,
            estimation_method="fixture",
            estimation_version="1.0",
            estimation_software_versions={"qiskit": "2.4.2"},
        )


def test_estimator_artifact_values_round_trip_as_typed_references() -> None:
    result = EstimatorPubResult(
        schema_version="1.0",
        pub_id="estimator-0",
        pub_index=0,
        data_bin_shape=[1],
        expectation_values=ShapedResultValue(
            schema_version="1.0", shape=[1], dtype="float64", value=_artifact_ref()
        ),
        standard_deviations=ShapedResultValue(
            schema_version="1.0",
            shape=[1],
            dtype="float64",
            value=InlineJsonValue(
                schema_version="1.0", kind="inline_json", value=[0.1]
            ),
        ),
    )

    restored = EstimatorPubResult.model_validate_json(result.model_dump_json())
    assert isinstance(restored.expectation_values.value, ArtifactRef)
    assert isinstance(restored.standard_deviations.value, InlineJsonValue)
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
        packed_shape=list(bit_array.array.shape),
        packed_bytes=InlineJsonValue(
            schema_version="1.0", kind="inline_json", value=bit_array.array
        ),
        counts_by_location=InlineJsonValue(
            schema_version="1.0",
            kind="inline_json",
            value=[bit_array.get_counts(location) for location in locations],
        ),
        bitstrings_by_location=InlineJsonValue(
            schema_version="1.0",
            kind="inline_json",
            value=[bit_array.get_bitstrings(location) for location in locations],
        ),
        quasi_distributions_by_location=InlineJsonValue(
            schema_version="1.0",
            kind="inline_json",
            value=[
                {
                    bitstring: count / bit_array.num_shots
                    for bitstring, count in bit_array.get_counts(location).items()
                }
                for location in locations
            ],
        ),
    )

    assert result.pub_shape == [2]
    assert result.num_shots == 3
    assert isinstance(result.counts_by_location, InlineJsonValue)
    assert len(result.counts_by_location.value) == 2
    assert SamplerRegisterResult.model_validate_json(result.model_dump_json()) == result

    with pytest.raises(ValidationError, match="one row-major entry"):
        SamplerRegisterResult(
            schema_version="1.0",
            register_name="meas",
            pub_shape=[2],
            num_shots=3,
            num_bits=1,
            packed_shape=[2, 3, 1],
            packed_bytes=InlineJsonValue(
                schema_version="1.0", kind="inline_json", value=packed
            ),
            counts_by_location=InlineJsonValue(
                schema_version="1.0", kind="inline_json", value=[{"0": 3}]
            ),
            bitstrings_by_location=InlineJsonValue(
                schema_version="1.0",
                kind="inline_json",
                value=[["0", "0", "0"], ["0", "0", "0"]],
            ),
            quasi_distributions_by_location=InlineJsonValue(
                schema_version="1.0",
                kind="inline_json",
                value=[{"0": 1.0}, {"0": 1.0}],
            ),
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
        data_bin_shape=[2],
        expectation_values=ShapedResultValue(
            schema_version="1.0", shape=[2], dtype="float64", value=inline
        ),
        standard_deviations=ShapedResultValue(
            schema_version="1.0",
            shape=[2],
            dtype="float64",
            value=InlineJsonValue(
                schema_version="1.0", kind="inline_json", value=[0.1, 0.2]
            ),
        ),
    )
    referenced_result = EstimatorPubResult(
        schema_version="1.0",
        pub_id="estimator-artifact",
        pub_index=0,
        data_bin_shape=[2],
        expectation_values=ShapedResultValue(
            schema_version="1.0", shape=[2], dtype="float64", value=referenced
        ),
        standard_deviations=ShapedResultValue(
            schema_version="1.0",
            shape=[2],
            dtype="float64",
            value=InlineJsonValue(
                schema_version="1.0", kind="inline_json", value=[0.1, 0.2]
            ),
        ),
    )

    assert isinstance(inline_result.expectation_values.value, InlineJsonValue)
    assert isinstance(referenced_result.expectation_values.value, ArtifactRef)
    assert isinstance(
        EstimatorPubResult.model_validate_json(
            referenced_result.model_dump_json()
        ).expectation_values.value,
        ArtifactRef,
    )
