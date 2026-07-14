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

"""W1-05 semantic, metamorphic, and negative circuit-boundary contracts."""

from __future__ import annotations

import base64
import copy
import io
import math
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, qpy
from qiskit.circuit import Gate, Parameter
from qiskit.circuit.library import RXGate, XGate
from qiskit.transpiler import Target
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime.fake_provider import FakeAthensV2, FakeSherbrooke

from qiskit_ibm_runtime_mcp_server.core.artifacts import LocalArtifactCAS, content_id
from qiskit_ibm_runtime_mcp_server.core.circuits import (
    CircuitContractError,
    CircuitFormatError,
    CircuitIsaError,
    CircuitLimitError,
    CircuitLimits,
    CircuitWidthError,
    ResolvedTarget,
    TargetIdentityError,
    apply_circuit_mode,
    ingest_circuit,
    target_fingerprint,
    validate_circuit_isa,
)
from qiskit_ibm_runtime_mcp_server.core.models import BackendSnapshot
from qiskit_ibm_runtime_mcp_server.core.snapshots import build_backend_snapshot


def _qpy_bytes(circuit: QuantumCircuit | list[QuantumCircuit]) -> bytes:
    buffer = io.BytesIO()
    qpy.dump(circuit, buffer)
    return buffer.getvalue()


def _backend_snapshot(backend: object) -> BackendSnapshot:
    return build_backend_snapshot(
        backend,
        instance_id="offline:test",
        properties=None,
        retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _resolved_target(backend: object | None = None) -> ResolvedTarget:
    resolved_backend = backend or FakeAthensV2()
    return ResolvedTarget(resolved_backend, _backend_snapshot(resolved_backend))


class _SyntheticBackend:
    def __init__(self, name: str, target: Target) -> None:
        self.name = name
        self.target = target


def _isa_circuit(*, metadata_value: str = "approved") -> QuantumCircuit:
    qreg = QuantumRegister(2, "logical")
    creg = ClassicalRegister(2, "readout")
    circuit = QuantumCircuit(
        qreg,
        creg,
        name="parameterized_isa",
        metadata={"approval": metadata_value, "nested": {"sequence": [1, 2]}},
    )
    theta = Parameter("theta")
    circuit.rz(theta, qreg[0])
    circuit.sx(qreg[0])
    circuit.cx(qreg[0], qreg[1])
    circuit.measure(qreg, creg)
    return circuit


def _compiled_rich_circuit() -> QuantumCircuit:
    return generate_preset_pass_manager(
        optimization_level=0,
        target=FakeAthensV2().target,
        seed_transpiler=11,
    ).run(_isa_circuit())


def test_qpy_ingestion_preserves_exact_bytes_and_rich_qiskit_state(
    tmp_path: object,
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    circuit = _compiled_rich_circuit()
    raw = _qpy_bytes(circuit)

    ingested = ingest_circuit(raw, circuit_format="qpy", sink=sink)

    assert sink.get_bytes(ingested.artifact.artifact) == raw
    assert ingested.artifact.circuit_hash == content_id(raw)
    assert ingested.artifact.artifact.artifact_id == content_id(raw)
    assert ingested.artifact.qiskit_version == "2.4.2"
    assert ingested.artifact.reader_qiskit_version == "2.4.2"
    assert ingested.artifact.qpy_version == qpy.QPY_VERSION
    assert ingested.artifact.qpy_symbolic_encoding in {"p", "e"}
    assert ingested.artifact.parameter_names == ["theta"]
    assert ingested.artifact.metadata == circuit.metadata
    assert [
        (register.kind, register.name, register.bit_indices)
        for register in ingested.artifact.registers
    ] == [
        ("quantum", "q", [0, 1, 2, 3, 4]),
        ("classical", "readout", [0, 1]),
    ]
    assert ingested.artifact.layout == {
        "initial_index_layout": [0, 1, 2, 3, 4],
        "final_index_layout": [0, 1, 2, 3, 4],
        "routing_permutation": [0, 1, 2, 3, 4],
        "num_input_qubits": 2,
    }
    assert ingested.artifact.provenance.transformation == "source"
    assert ingested.circuit == circuit


def test_exact_and_validate_never_construct_a_pass_manager_and_hash_is_stable(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    source = ingest_circuit(
        _qpy_bytes(_compiled_rich_circuit()), circuit_format="qpy", sink=sink
    )

    def forbidden_pass_manager(*args: object, **kwargs: object) -> object:
        raise AssertionError("pass manager invoked outside transpile mode")

    monkeypatch.setattr(
        "qiskit_ibm_runtime_mcp_server.core.circuits.generate_preset_pass_manager",
        forbidden_pass_manager,
    )
    stored_bytes_before = sink.get_bytes(source.artifact.artifact)
    semantic_copy = copy.deepcopy(source.circuit)
    exact = apply_circuit_mode(source, mode="exact")
    validated = apply_circuit_mode(
        source,
        mode="validate",
        resolved_target=_resolved_target(),
    )
    stored_bytes_after = sink.get_bytes(source.artifact.artifact)

    assert exact.circuit == source.circuit
    assert exact.circuit is not source.circuit
    assert exact.artifact is source.artifact
    assert validated.circuit == source.circuit
    assert validated.circuit is not source.circuit
    assert validated.artifact is source.artifact
    assert validated.validation is not None
    assert validated.validation.target_hash == _resolved_target().target_hash
    assert (
        validated.validation.compiler_target_hash
        == _resolved_target().compiler_target_hash
    )
    assert validated.validation.circuit_hash_before == source.artifact.circuit_hash
    assert validated.validation.circuit_hash_after == source.artifact.circuit_hash
    assert stored_bytes_before == stored_bytes_after
    assert content_id(stored_bytes_before) == source.artifact.circuit_hash
    assert source.circuit == semantic_copy


def test_mutating_cached_circuit_cannot_cross_exact_or_validation_boundary(
    tmp_path: object,
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    source = ingest_circuit(
        _qpy_bytes(_compiled_rich_circuit()), circuit_format="qpy", sink=sink
    )
    approved_operation_count = len(source.circuit.data)
    approved_hash = source.artifact.circuit_hash

    source.circuit.h(0)
    assert len(source.circuit.data) == approved_operation_count + 1

    exact = apply_circuit_mode(source, mode="exact")
    validated = apply_circuit_mode(
        source,
        mode="validate",
        resolved_target=_resolved_target(),
    )

    assert len(exact.circuit.data) == approved_operation_count
    assert len(validated.circuit.data) == approved_operation_count
    assert "h" not in exact.circuit.count_ops()
    assert exact.artifact.circuit_hash == approved_hash
    assert validated.artifact.circuit_hash == approved_hash


@pytest.mark.parametrize("metadata_value", ["approved-a", "approved-b"])
def test_validation_is_semantically_invariant_to_non_isa_metadata(
    tmp_path: object, metadata_value: str
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    compiled = generate_preset_pass_manager(
        optimization_level=0,
        target=FakeAthensV2().target,
        seed_transpiler=17,
    ).run(_isa_circuit(metadata_value=metadata_value))
    source = ingest_circuit(_qpy_bytes(compiled), circuit_format="qpy", sink=sink)

    result = apply_circuit_mode(
        source,
        mode="validate",
        resolved_target=_resolved_target(),
    )

    assert result.validation is not None
    assert result.validation.instruction_count == len(compiled.data)
    assert result.artifact.metadata["approval"] == metadata_value


def test_explicit_transpile_emits_new_qpy_with_complete_provenance(
    tmp_path: object,
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    logical = QuantumCircuit(2, name="logical")
    logical.h(0)
    logical.cx(0, 1)
    source = ingest_circuit(_qpy_bytes(logical), circuit_format="qpy", sink=sink)
    resolved_target = _resolved_target()

    result = apply_circuit_mode(
        source,
        mode="transpile",
        resolved_target=resolved_target,
        sink=sink,
        optimization_level=1,
        seed_transpiler=23,
    )

    provenance = result.artifact.provenance
    assert result.artifact.format == "qpy"
    assert result.artifact.circuit_hash != source.artifact.circuit_hash
    assert result.validation is not None
    assert provenance.transformation == "transpile"
    assert provenance.source_circuit_hash == source.artifact.circuit_hash
    assert provenance.source_artifact_id == source.artifact.artifact.artifact_id
    assert provenance.target_hash == resolved_target.target_hash
    assert provenance.compiler_target_hash == resolved_target.compiler_target_hash
    assert provenance.target_name == resolved_target.backend_name
    assert provenance.transpiler_name == (
        "qiskit.transpiler.preset_passmanagers.generate_preset_pass_manager"
    )
    assert provenance.transpiler_options == {
        "optimization_level": 1,
        "seed_transpiler": 23,
    }
    assert provenance.software_versions["qiskit"] == "2.4.2"
    assert sink.get_bytes(result.artifact.artifact)


def test_transpile_returns_circuit_reloaded_from_emitted_qpy(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    logical = QuantumCircuit(1)
    logical.h(0)
    source = ingest_circuit(_qpy_bytes(logical), circuit_format="qpy", sink=sink)
    real_load = qpy.load
    loaded_payloads = 0

    def load_spy(stream: object) -> list[QuantumCircuit]:
        nonlocal loaded_payloads
        loaded_payloads += 1
        return real_load(stream)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "qiskit_ibm_runtime_mcp_server.core.circuits.qpy.load", load_spy
    )
    result = apply_circuit_mode(
        source,
        mode="transpile",
        resolved_target=_resolved_target(),
        sink=sink,
        optimization_level=0,
        seed_transpiler=31,
    )

    assert loaded_payloads == 2
    reloaded = real_load(io.BytesIO(sink.get_bytes(result.artifact.artifact)))[0]
    assert result.circuit == reloaded
    assert result.artifact.parameter_names == [
        parameter.name for parameter in reloaded.parameters
    ]
    assert result.artifact.metadata == (reloaded.metadata or {})
    assert result.artifact.layout == (
        None
        if reloaded.layout is None
        else {
            "initial_index_layout": reloaded.layout.initial_index_layout(
                filter_ancillas=False
            ),
            "final_index_layout": reloaded.layout.final_index_layout(
                filter_ancillas=False
            ),
            "routing_permutation": reloaded.layout.routing_permutation(),
            "num_input_qubits": len(
                reloaded.layout.initial_index_layout(filter_ancillas=True)
            ),
        }
    )


def test_resolved_target_binds_backend_name_structure_and_hash(
    tmp_path: object,
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    target = Target(num_qubits=1)
    target.add_instruction(XGate(), {(0,): None})
    backend = _SyntheticBackend("synthetic", target)
    snapshot = _backend_snapshot(backend)
    resolved = ResolvedTarget(backend, snapshot)
    source = ingest_circuit(
        _qpy_bytes(QuantumCircuit(1)), circuit_format="qpy", sink=sink
    )

    assert resolved.target_hash == snapshot.target_hash
    assert resolved.compiler_target_hash == target_fingerprint(target)
    backend.target = Target(num_qubits=1)
    with pytest.raises(TargetIdentityError, match="backend target changed"):
        validate_circuit_isa(source, resolved_target=resolved)


@pytest.mark.parametrize("active_out_of_range", [False, True])
def test_validation_rejects_circuit_wider_than_target_even_if_extra_wires_are_idle(
    tmp_path: object, active_out_of_range: bool
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    circuit = QuantumCircuit(6)
    circuit.x(5 if active_out_of_range else 0)
    source = ingest_circuit(_qpy_bytes(circuit), circuit_format="qpy", sink=sink)

    with pytest.raises(CircuitWidthError, match="6 qubits.*5"):
        apply_circuit_mode(
            source,
            mode="validate",
            resolved_target=_resolved_target(),
        )


@pytest.mark.parametrize(
    ("angle", "qubit", "expected_reason"),
    [
        (math.pi / 4, 0, None),
        (math.pi / 2, 0, "unsupported_parameters_or_variant"),
        (math.pi / 4, 1, "unsupported_qubit_tuple"),
    ],
)
def test_validation_supports_fixed_custom_named_target_variants(
    tmp_path: object,
    angle: float,
    qubit: int,
    expected_reason: str | None,
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    target = Target(num_qubits=2)
    target.add_instruction(RXGate(math.pi / 4), {(0,): None}, name="rx_pi_4")
    backend = _SyntheticBackend("fixed-rx", target)
    resolved = _resolved_target(backend)
    circuit = QuantumCircuit(2)
    circuit.rx(angle, qubit)
    source = ingest_circuit(_qpy_bytes(circuit), circuit_format="qpy", sink=sink)

    if expected_reason is None:
        result = apply_circuit_mode(
            source,
            mode="validate",
            resolved_target=resolved,
        )
        assert result.validation is not None
    else:
        with pytest.raises(CircuitIsaError) as exc_info:
            apply_circuit_mode(
                source,
                mode="validate",
                resolved_target=resolved,
            )
        assert exc_info.value.issues[0].reason == expected_reason


def _custom_gate(basis_operation: str) -> Gate:
    definition = QuantumCircuit(1)
    getattr(definition, basis_operation)(0)
    operation = Gate("semantic_gate", 1, [])
    operation.definition = definition
    return operation


def test_custom_operation_validation_binds_definition_semantics(
    tmp_path: object,
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    target = Target(num_qubits=1)
    target.add_instruction(_custom_gate("x"), {(0,): None})
    resolved = _resolved_target(_SyntheticBackend("custom", target))

    matching = QuantumCircuit(1)
    matching.append(_custom_gate("x"), [0])
    matching_source = ingest_circuit(
        _qpy_bytes(matching), circuit_format="qpy", sink=sink
    )
    assert (
        apply_circuit_mode(
            matching_source,
            mode="validate",
            resolved_target=resolved,
        ).validation
        is not None
    )

    conflicting = QuantumCircuit(1)
    conflicting.append(_custom_gate("h"), [0])
    conflicting_source = ingest_circuit(
        _qpy_bytes(conflicting), circuit_format="qpy", sink=sink
    )
    with pytest.raises(CircuitIsaError) as exc_info:
        apply_circuit_mode(
            conflicting_source,
            mode="validate",
            resolved_target=resolved,
        )
    assert exc_info.value.issues[0].reason == "unsupported_parameters_or_variant"


def test_custom_operation_definition_drift_changes_compiler_target_hash() -> None:
    target = Target(num_qubits=1)
    target.add_instruction(_custom_gate("x"), {(0,): None})
    resolved = _resolved_target(_SyntheticBackend("custom", target))

    operation = target.operation_from_name("semantic_gate")
    assert isinstance(operation, Gate)
    operation.definition = _custom_gate("h").definition

    with pytest.raises(TargetIdentityError, match="target structure changed"):
        resolved.verify_current()


def _unsupported_h_circuit() -> QuantumCircuit:
    circuit = QuantumCircuit(1)
    circuit.h(0)
    return circuit


def _unsupported_cx_tuple_circuit() -> QuantumCircuit:
    circuit = QuantumCircuit(3)
    circuit.cx(0, 2)
    return circuit


@pytest.mark.parametrize(
    ("circuit_factory", "reason", "qubits"),
    [
        (_unsupported_h_circuit, "unsupported_operation", (0,)),
        (
            _unsupported_cx_tuple_circuit,
            "unsupported_qubit_tuple",
            (0, 2),
        ),
    ],
)
def test_validation_rejects_unsupported_operations_and_qubit_tuples(
    tmp_path: object,
    circuit_factory: Callable[[], QuantumCircuit],
    reason: str,
    qubits: tuple[int, ...],
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    source = ingest_circuit(
        _qpy_bytes(circuit_factory()), circuit_format="qpy", sink=sink
    )

    with pytest.raises(CircuitIsaError) as exc_info:
        apply_circuit_mode(
            source,
            mode="validate",
            resolved_target=_resolved_target(),
        )

    assert exc_info.value.issues[0].reason == reason
    assert exc_info.value.issues[0].qubits == qubits


@pytest.mark.parametrize("gate_name", ["x", "rz"])
def test_validation_recurses_through_supported_dynamic_control_flow(
    tmp_path: object, gate_name: str
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    circuit = QuantumCircuit(2, 1)
    with circuit.if_test((circuit.clbits[0], True)):
        if gate_name == "x":
            circuit.x(1)
        else:
            circuit.rz(Parameter("phi"), 1)
    source = ingest_circuit(_qpy_bytes(circuit), circuit_format="qpy", sink=sink)

    result = apply_circuit_mode(
        source,
        mode="validate",
        resolved_target=_resolved_target(FakeSherbrooke()),
    )

    assert result.validation is not None
    assert result.validation.instruction_count == 2


def test_validation_rejects_unsupported_operation_inside_control_flow(
    tmp_path: object,
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    circuit = QuantumCircuit(2, 1)
    with circuit.if_test((circuit.clbits[0], True)):
        circuit.h(1)
    source = ingest_circuit(_qpy_bytes(circuit), circuit_format="qpy", sink=sink)

    with pytest.raises(CircuitIsaError) as exc_info:
        apply_circuit_mode(
            source,
            mode="validate",
            resolved_target=_resolved_target(FakeSherbrooke()),
        )

    nested_issue = next(
        issue for issue in exc_info.value.issues if issue.operation_name == "h"
    )
    assert nested_issue.instruction_path == (0, 0, 0)
    assert nested_issue.qubits == (1,)
    assert nested_issue.reason == "unsupported_operation"


def test_decoded_size_limit_precedes_qpy_parser(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    parser_called = False

    def parser_spy(stream: object) -> list[QuantumCircuit]:
        nonlocal parser_called
        parser_called = True
        return []

    monkeypatch.setattr(
        "qiskit_ibm_runtime_mcp_server.core.circuits.qpy.load", parser_spy
    )
    payload = base64.b64encode(
        b"QISKIT" + bytes([qpy.QPY_VERSION]) + b"x" * 64
    ).decode()
    with pytest.raises(CircuitLimitError, match="encoded limit"):
        ingest_circuit(
            payload,
            circuit_format="qpy",
            sink=sink,
            limits=CircuitLimits(max_payload_bytes=16),
        )
    assert parser_called is False


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "too short"),
        (b"WRONG!" + bytes([qpy.QPY_VERSION]) + b"x" * 32, "magic"),
        (b"QISKIT" + bytes([qpy.QPY_VERSION]) + b"x", "truncated"),
    ],
)
def test_malformed_qpy_headers_fail_before_parser(
    tmp_path: object, payload: bytes, message: str
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    with pytest.raises(CircuitFormatError, match=message):
        ingest_circuit(payload, circuit_format="qpy", sink=sink)


def test_invalid_base64_and_invalid_qpy_body_fail_closed(tmp_path: object) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    with pytest.raises(CircuitFormatError, match="valid base64"):
        ingest_circuit("!!!!", circuit_format="qpy", sink=sink)

    header_only = _qpy_bytes(QuantumCircuit(1))[:19]
    with pytest.raises(CircuitFormatError, match="deserialization failed"):
        ingest_circuit(header_only, circuit_format="qpy", sink=sink)


@pytest.mark.parametrize("encoded", [False, True])
def test_oversized_decoded_qpy_is_rejected_before_parser(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch, encoded: bool
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    raw = b"QISKIT" + bytes([qpy.QPY_VERSION]) + b"x" * 10
    payload: bytes | str = base64.b64encode(raw).decode() if encoded else raw
    parser_called = False

    def parser_spy(stream: object) -> list[QuantumCircuit]:
        nonlocal parser_called
        parser_called = True
        return []

    monkeypatch.setattr(
        "qiskit_ibm_runtime_mcp_server.core.circuits.qpy.load", parser_spy
    )
    with pytest.raises(CircuitLimitError, match="decoded QPY payload"):
        ingest_circuit(
            payload,
            circuit_format="qpy",
            sink=sink,
            limits=CircuitLimits(max_payload_bytes=16),
        )
    assert parser_called is False


def test_qasm_size_limit_precedes_parser(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    parser_called = False

    def parser_spy(text: str) -> QuantumCircuit:
        nonlocal parser_called
        parser_called = True
        return QuantumCircuit(1)

    monkeypatch.setattr(
        "qiskit_ibm_runtime_mcp_server.core.circuits.qasm3_loads", parser_spy
    )
    with pytest.raises(CircuitLimitError, match="QASM3 payload"):
        ingest_circuit(
            "OPENQASM 3.0;" + " " * 64,
            circuit_format="qasm3",
            sink=sink,
            limits=CircuitLimits(max_payload_bytes=16),
        )
    assert parser_called is False


@pytest.mark.parametrize(
    ("payload", "message", "limit"),
    [
        (b"x" * 17, "payload exceeds", 16),
        (b"\xff", "valid UTF-8", 16),
        ("é" * 10, "payload exceeds", 15),
        ("not qasm", "deserialization failed", 16),
    ],
)
def test_qasm_encoding_and_parse_failures_are_explicit(
    tmp_path: object, payload: bytes | str, message: str, limit: int
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    with pytest.raises((CircuitFormatError, CircuitLimitError), match=message):
        ingest_circuit(
            payload,
            circuit_format="qasm3",
            sink=sink,
            limits=CircuitLimits(max_payload_bytes=limit),
        )


def test_multi_circuit_qpy_is_rejected_before_deserialization(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    parser_called = False

    def parser_spy(stream: object) -> list[QuantumCircuit]:
        nonlocal parser_called
        parser_called = True
        return []

    monkeypatch.setattr(
        "qiskit_ibm_runtime_mcp_server.core.circuits.qpy.load", parser_spy
    )
    raw = _qpy_bytes([QuantumCircuit(1), QuantumCircuit(1)])
    with pytest.raises(CircuitFormatError, match="exactly one circuit; found 2"):
        ingest_circuit(raw, circuit_format="qpy", sink=sink)
    assert parser_called is False


def test_forward_qpy_is_rejected_before_deserialization(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    raw = bytearray(_qpy_bytes(QuantumCircuit(1)))
    raw[6] = qpy.QPY_VERSION + 1
    parser_called = False

    def parser_spy(stream: object) -> list[QuantumCircuit]:
        nonlocal parser_called
        parser_called = True
        return []

    monkeypatch.setattr(
        "qiskit_ibm_runtime_mcp_server.core.circuits.qpy.load", parser_spy
    )
    with pytest.raises(CircuitFormatError, match="newer than supported"):
        ingest_circuit(bytes(raw), circuit_format="qpy", sink=sink)
    assert parser_called is False


def test_ingested_source_rejects_bytes_that_do_not_match_artifact(
    tmp_path: object,
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    source = ingest_circuit(
        _qpy_bytes(QuantumCircuit(1)), circuit_format="qpy", sink=sink
    )
    with pytest.raises(CircuitContractError, match="do not match"):
        replace(source, serialized_bytes=b"different")


def _circuit_over_limit(kind: str) -> tuple[QuantumCircuit, CircuitLimits]:
    if kind == "qubits":
        return QuantumCircuit(2), CircuitLimits(max_qubits=1)
    if kind == "operations":
        circuit = QuantumCircuit(1)
        circuit.x(0)
        circuit.x(0)
        return circuit, CircuitLimits(max_operations=1)
    if kind == "registers":
        circuit = QuantumCircuit(QuantumRegister(1, "a"), QuantumRegister(1, "b"))
        return circuit, CircuitLimits(max_registers=1)
    circuit = QuantumCircuit(1)
    circuit.rz(Parameter("alpha"), 0)
    circuit.rz(Parameter("beta"), 0)
    return circuit, CircuitLimits(max_parameters=1)


@pytest.mark.parametrize("kind", ["qubits", "operations", "registers", "parameters"])
def test_structural_limits_fail_closed(tmp_path: object, kind: str) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    circuit, limits = _circuit_over_limit(kind)
    with pytest.raises(CircuitLimitError, match=kind):
        ingest_circuit(
            _qpy_bytes(circuit), circuit_format="qpy", sink=sink, limits=limits
        )


def test_operation_limit_counts_nested_control_flow_instructions(
    tmp_path: object,
) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    circuit = QuantumCircuit(1, 1)
    with circuit.if_test((circuit.clbits[0], True)):
        circuit.x(0)
        circuit.x(0)

    with pytest.raises(CircuitLimitError, match="operations=3 exceeds 2"):
        ingest_circuit(
            _qpy_bytes(circuit),
            circuit_format="qpy",
            sink=sink,
            limits=CircuitLimits(max_operations=2),
        )


def test_qasm3_ingestion_and_exact_mode_preserve_source_bytes(tmp_path: object) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    qasm = """OPENQASM 3.0;
include \"stdgates.inc\";
qubit[1] q;
x q[0];
"""
    source = ingest_circuit(qasm, circuit_format="qasm3", sink=sink)
    result = apply_circuit_mode(source, mode="exact")

    assert result.artifact.format == "qasm3"
    assert result.artifact.qiskit_version is None
    assert result.artifact.qpy_version is None
    assert sink.get_bytes(result.artifact.artifact) == qasm.encode()
    assert result.artifact.circuit_hash == content_id(qasm.encode())


def test_modes_reject_contradictory_control_arguments(tmp_path: object) -> None:
    sink = LocalArtifactCAS(tmp_path)  # type: ignore[arg-type]
    source = ingest_circuit(
        _qpy_bytes(QuantumCircuit(1)), circuit_format="qpy", sink=sink
    )
    with pytest.raises(CircuitContractError, match="exact mode rejects"):
        apply_circuit_mode(
            source,
            mode="exact",
            resolved_target=_resolved_target(),
        )
    with pytest.raises(CircuitContractError, match="validate mode rejects"):
        apply_circuit_mode(
            source,
            mode="validate",
            resolved_target=_resolved_target(),
            sink=sink,
        )
    with pytest.raises(CircuitContractError, match="transpile mode requires"):
        apply_circuit_mode(
            source,
            mode="transpile",
            resolved_target=_resolved_target(),
            sink=sink,
            optimization_level=1,
        )
    with pytest.raises(CircuitContractError, match="requires a ResolvedTarget"):
        apply_circuit_mode(source, mode="validate")
    with pytest.raises(CircuitContractError, match="unsupported circuit mode"):
        apply_circuit_mode(
            source,
            mode="unsupported",  # type: ignore[arg-type]
            resolved_target=_resolved_target(),
        )
    with pytest.raises(CircuitContractError, match="optimization_level"):
        apply_circuit_mode(
            source,
            mode="transpile",
            resolved_target=_resolved_target(),
            sink=sink,
            optimization_level=4,
            seed_transpiler=1,
        )


def test_resolved_target_rejects_missing_or_drifting_identity() -> None:
    valid_snapshot = _backend_snapshot(FakeAthensV2())
    with pytest.raises(TargetIdentityError, match="named backend"):
        ResolvedTarget(_SyntheticBackend("", Target(num_qubits=1)), valid_snapshot)
    missing_target = _SyntheticBackend("missing", Target(num_qubits=1))
    missing_target.target = None  # type: ignore[assignment]
    with pytest.raises(TargetIdentityError, match="backend.target"):
        ResolvedTarget(missing_target, valid_snapshot)

    backend = _SyntheticBackend("original", Target(num_qubits=1))
    resolved = _resolved_target(backend)
    backend.name = "changed"
    with pytest.raises(TargetIdentityError, match="backend name changed"):
        resolved.verify_current()


def test_resolved_target_rejects_mismatched_or_mutated_snapshot() -> None:
    backend = _SyntheticBackend("synthetic", Target(num_qubits=1))
    with pytest.raises(TargetIdentityError, match="snapshot name"):
        ResolvedTarget(backend, _backend_snapshot(FakeAthensV2()))

    resolved = _resolved_target(backend)
    resolved.snapshot.target_hash = content_id(b"mutated snapshot hash")
    with pytest.raises(TargetIdentityError, match="snapshot target hash changed"):
        resolved.verify_current()


def test_target_fingerprint_rejects_opaque_angle_bounds() -> None:
    target = Target(num_qubits=1)
    theta = Parameter("theta")
    target.add_instruction(
        RXGate(theta),
        {(0,): None},
        angle_bounds=[(0.0, math.pi)],
    )
    with pytest.raises(TargetIdentityError, match="angle-bound"):
        target_fingerprint(target)


def test_circuit_limits_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_qubits"):
        CircuitLimits(max_qubits=0)
