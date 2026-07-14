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

"""Backend snapshot completeness, history, mode, and read-only contracts."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from qiskit_ibm_runtime import QiskitRuntimeService
from qiskit_ibm_runtime.fake_provider import FakeAthensV2, FakeSherbrooke

from qiskit_ibm_runtime_mcp_server.core.snapshots import (
    SnapshotContractError,
    build_backend_snapshot,
    resolve_backend_snapshot,
    snapshot_content_hash,
    target_content_hash,
    validate_snapshot_request,
)


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


def _target_keys(target: object) -> set[tuple[str, tuple[int, ...] | None]]:
    return {
        (name, None if qargs is None else tuple(qargs))
        for name in target.operation_names  # type: ignore[attr-defined]
        for qargs in target[name]  # type: ignore[index]
    }


def _snapshot_keys(snapshot: object) -> set[tuple[str, tuple[int, ...] | None]]:
    return {
        (
            instruction.name,
            None if instruction.qubits is None else tuple(instruction.qubits),
        )
        for instruction in snapshot.instructions  # type: ignore[attr-defined]
    }


def test_fake_backend_snapshot_is_complete_over_locked_target() -> None:
    backend = FakeAthensV2()
    properties = backend.properties()
    snapshot = build_backend_snapshot(
        backend,
        instance_id="offline:fake-provider",
        properties=properties,
        retrieved_at=NOW,
    )

    expected_instruction_count = sum(
        len(backend.target[name]) for name in backend.target.operation_names
    )
    assert snapshot.target.num_qubits == backend.target.num_qubits
    assert [qubit.index for qubit in snapshot.qubits] == list(
        range(backend.target.num_qubits)
    )
    assert len(snapshot.instructions) == expected_instruction_count
    assert _snapshot_keys(snapshot) == _target_keys(backend.target)
    assert snapshot.target.operation_names == sorted(backend.target.operation_names)
    assert snapshot.target.physical_qubits == list(range(backend.target.num_qubits))
    assert next(
        instruction
        for instruction in snapshot.instructions
        if instruction.name == "rz" and instruction.qubits == [0]
    ).operation_parameters == ["λ"]

    properties_payload = properties.to_dict()
    assert [len(qubit.parameters) for qubit in snapshot.qubits] == [
        len(parameters) for parameters in properties_payload["qubits"]
    ]
    calibration_by_key = {
        (instruction.name, tuple(instruction.qubits or ())): instruction
        for instruction in snapshot.instructions
    }
    for gate in properties_payload["gates"]:
        instruction = calibration_by_key[(gate["gate"], tuple(gate["qubits"]))]
        assert len(instruction.calibration_parameters) == len(gate["parameters"])
        parameter_names = {parameter["name"] for parameter in gate["parameters"]}
        if "gate_error" in parameter_names:
            assert instruction.error is not None
        if "gate_length" in parameter_names:
            assert instruction.duration is not None
        assert instruction.operational is not None

    assert snapshot.properties_last_update == properties.last_update_date
    assert snapshot.faulty_qubits == sorted(properties.faulty_qubits())
    assert snapshot.backend_version == backend.backend_version
    assert snapshot.processor.family == backend.processor_type["family"]
    assert snapshot.coupling_edges == sorted(
        [list(edge) for edge in backend.coupling_map.get_edges()]
    )


def test_fake_backend_snapshot_preserves_global_target_instructions() -> None:
    backend = FakeSherbrooke()
    snapshot = build_backend_snapshot(
        backend,
        instance_id="offline:fake-provider",
        properties=backend.properties(),
        retrieved_at=NOW,
    )
    expected_keys = _target_keys(backend.target)
    expected_globals = {name for name, qargs in expected_keys if qargs is None}

    assert expected_globals == {"for_loop", "if_else", "switch_case"}
    assert len(snapshot.instructions) == sum(
        len(backend.target[name]) for name in backend.target.operation_names
    )
    assert _snapshot_keys(snapshot) == expected_keys
    assert {
        instruction.name
        for instruction in snapshot.instructions
        if instruction.qubits is None
    } == expected_globals
    assert set(snapshot.target.global_operations) == expected_globals


def test_snapshot_and_target_hashes_are_stable_and_content_sensitive() -> None:
    backend = FakeAthensV2()
    properties = backend.properties()
    first = build_backend_snapshot(
        backend,
        instance_id="offline:fake-provider",
        properties=properties,
        retrieved_at=NOW,
    )
    second = build_backend_snapshot(
        backend,
        instance_id="offline:fake-provider",
        properties=properties,
        retrieved_at=NOW + timedelta(minutes=5),
    )

    assert first.target_hash == second.target_hash == target_content_hash(first)
    assert first.snapshot_hash == second.snapshot_hash == snapshot_content_hash(first)
    assert first.software_versions["qiskit"]
    assert first.software_versions["qiskit-ibm-runtime"]
    assert first.software_versions["qiskit-ibm-runtime-mcp-server"]
    assert first.software_versions["python"]

    changed = first.model_copy(deep=True)
    changed.instructions[0].error = (changed.instructions[0].error or 0.0) + 0.001
    assert target_content_hash(changed) != first.target_hash
    assert snapshot_content_hash(changed) != first.snapshot_hash


def test_faulty_qubit_forces_every_touching_instruction_non_operational() -> None:
    backend = FakeAthensV2()
    current_properties = backend.properties()
    properties = Mock(wraps=current_properties)
    properties.last_update_date = current_properties.last_update_date
    properties.faulty_qubits.return_value = [0]
    properties.is_qubit_operational.side_effect = lambda qubit: qubit != 0
    properties.is_gate_operational.return_value = True

    snapshot = build_backend_snapshot(
        backend,
        instance_id="offline:fake-provider",
        properties=properties,
        retrieved_at=NOW,
    )

    assert snapshot.qubits[0].operational is False
    touching_instructions = [
        instruction
        for instruction in snapshot.instructions
        if instruction.qubits is not None and 0 in instruction.qubits
    ]
    assert touching_instructions
    assert all(
        instruction.operational is False for instruction in touching_instructions
    )


def test_historical_lookup_passes_timezone_aware_datetime_to_locked_api() -> None:
    backend = FakeAthensV2()
    current_properties = backend.properties()
    historical_properties = Mock(wraps=current_properties)
    historical_properties.last_update_date = datetime(
        2025, 2, 10, 8, 0, tzinfo=timezone(timedelta(hours=-5))
    )
    historical_properties.gate_error.side_effect = lambda gate, qubits: (
        0.123
        if gate == "cx" and tuple(qubits) == (0, 1)
        else current_properties.gate_error(gate, qubits)
    )
    historical_properties.gate_length.side_effect = lambda gate, qubits: (
        2.5e-7
        if gate == "cx" and tuple(qubits) == (0, 1)
        else current_properties.gate_length(gate, qubits)
    )
    backend.properties = Mock(return_value=historical_properties)  # type: ignore[method-assign]
    service = Mock()
    service.backend.return_value = backend
    requested_at = datetime(2025, 2, 10, 9, 30, tzinfo=timezone(timedelta(hours=-5)))

    snapshot = resolve_backend_snapshot(
        service,
        backend_name="fake_athens",
        instance_id="crn:test:instance",
        properties_at=requested_at,
        fractional_gate_mode="disabled",
        retrieved_at=NOW,
    )

    service.backend.assert_called_once_with(
        "fake_athens",
        instance="crn:test:instance",
        use_fractional_gates=False,
    )
    backend.properties.assert_called_once_with(refresh=False, datetime=requested_at)
    assert snapshot.properties_at == requested_at
    assert snapshot.properties_last_update == historical_properties.last_update_date
    historical_cx = next(
        instruction
        for instruction in snapshot.instructions
        if instruction.name == "cx" and instruction.qubits == [0, 1]
    )
    assert historical_cx.error == 0.123
    assert historical_cx.duration == 2.5e-7


def test_historical_lookup_rejects_naive_datetime_before_resolution() -> None:
    service = Mock()
    with pytest.raises(SnapshotContractError, match="timezone-aware"):
        resolve_backend_snapshot(
            service,
            backend_name="ibm_test",
            instance_id="crn:test:instance",
            properties_at=datetime(2025, 2, 10, 9, 30),
        )
    service.backend.assert_not_called()


@pytest.mark.parametrize("option", ["dynamic_circuits", "pec", "pea", "gate_twirling"])
def test_fractional_gate_mode_rejects_each_incompatible_option(option: str) -> None:
    options = {
        "dynamic_circuits": False,
        "pec": False,
        "pea": False,
        "gate_twirling": False,
    }
    options[option] = True
    with pytest.raises(SnapshotContractError, match=option):
        validate_snapshot_request(
            backend_name="ibm_test",
            instance_id="crn:test:instance",
            properties_at=None,
            fractional_gate_mode="enabled",
            **options,
        )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("disabled", False), ("enabled", True), ("all", None)],
)
def test_fractional_gate_mode_is_explicitly_forwarded(
    mode: str, expected: bool | None
) -> None:
    backend = FakeAthensV2()
    backend.properties = Mock(return_value=backend.properties())  # type: ignore[method-assign]
    service = Mock()
    service.backend.return_value = backend

    snapshot = resolve_backend_snapshot(
        service,
        backend_name="fake_athens",
        instance_id="crn:test:instance",
        fractional_gate_mode=mode,  # type: ignore[arg-type]
        retrieved_at=NOW,
    )

    assert service.backend.call_args.kwargs["use_fractional_gates"] is expected
    assert snapshot.fractional_gate_mode == mode


@pytest.mark.g3
@pytest.mark.integration
@pytest.mark.skipif(
    not (
        os.getenv("QISKIT_RUNTIME_G3_READ_ONLY") == "1"
        and os.getenv("QISKIT_RUNTIME_G3_BACKEND")
        and os.getenv("QISKIT_IBM_RUNTIME_MCP_INSTANCE")
    ),
    reason="G3 or its explicit backend/instance metadata is not configured",
)
def test_g3_read_only_current_snapshot() -> None:
    """Read named backend metadata only; never construct or submit a primitive."""
    backend_name = os.environ["QISKIT_RUNTIME_G3_BACKEND"]
    instance_id = os.environ["QISKIT_IBM_RUNTIME_MCP_INSTANCE"]
    runtime_service = QiskitRuntimeService(instance=instance_id)

    snapshot = resolve_backend_snapshot(
        runtime_service,
        backend_name=backend_name,
        instance_id=instance_id,
        fractional_gate_mode="disabled",
    )

    assert snapshot.backend_name == backend_name
    assert len(snapshot.qubits) == snapshot.target.num_qubits
    assert len(snapshot.instructions) > 0
    assert snapshot.target_hash == target_content_hash(snapshot)
    assert snapshot.snapshot_hash == snapshot_content_hash(snapshot)
