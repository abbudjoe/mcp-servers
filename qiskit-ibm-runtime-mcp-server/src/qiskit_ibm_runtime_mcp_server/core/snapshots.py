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

"""Complete deterministic snapshots built from locked Qiskit public APIs."""

from __future__ import annotations

import platform
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal

from pydantic import JsonValue

from .models import (
    SCHEMA_VERSION,
    BackendSnapshot,
    BackendStatusSnapshot,
    CalibrationDatum,
    FaultyInstruction,
    InstructionSnapshot,
    ProcessorMetadata,
    QubitSnapshot,
    TargetMetadata,
)
from .serialization import canonical_json_hash, to_json_safe


FractionalGateMode = Literal["disabled", "enabled", "all"]
_FRACTIONAL_FLAGS: dict[FractionalGateMode, bool | None] = {
    "disabled": False,
    "enabled": True,
    "all": None,
}
_ZERO_HASH = f"sha256:{'0' * 64}"


class SnapshotContractError(ValueError):
    """Raised when a request cannot produce an unambiguous snapshot."""


def validate_snapshot_request(
    *,
    backend_name: str,
    instance_id: str,
    properties_at: datetime | None,
    fractional_gate_mode: FractionalGateMode,
    dynamic_circuits: bool,
    pec: bool,
    pea: bool,
    gate_twirling: bool,
) -> None:
    """Validate explicit backend ownership and fractional-gate incompatibilities."""
    if not backend_name.strip():
        raise SnapshotContractError("backend_name must be explicit and non-empty")
    if not instance_id.strip():
        raise SnapshotContractError("instance_id must be explicit and non-empty")
    if properties_at is not None and (
        properties_at.tzinfo is None or properties_at.utcoffset() is None
    ):
        raise SnapshotContractError("properties_at must be timezone-aware")
    if fractional_gate_mode not in _FRACTIONAL_FLAGS:
        raise SnapshotContractError(
            "fractional_gate_mode must be 'disabled', 'enabled', or 'all'"
        )
    if fractional_gate_mode == "enabled":
        incompatible = [
            name
            for name, enabled in (
                ("dynamic_circuits", dynamic_circuits),
                ("pec", pec),
                ("pea", pea),
                ("gate_twirling", gate_twirling),
            )
            if enabled
        ]
        if incompatible:
            raise SnapshotContractError(
                "fractional gates are incompatible with: " + ", ".join(incompatible)
            )


def _package_versions() -> dict[str, str]:
    result = {"python": platform.python_version()}
    for distribution in (
        "qiskit",
        "qiskit-ibm-runtime",
        "qiskit-ibm-runtime-mcp-server",
    ):
        try:
            result[distribution] = version(distribution)
        except PackageNotFoundError:
            result[distribution] = "source-tree"
    return result


def _aware_datetime(value: Any, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise SnapshotContractError(f"{field_name} must be a datetime when provided")
    if value.tzinfo is None or value.utcoffset() is None:
        raise SnapshotContractError(f"{field_name} must be timezone-aware")
    return value


def _calibration_data(values: Any) -> list[CalibrationDatum]:
    if values is None:
        return []
    if not isinstance(values, list):
        raise SnapshotContractError("backend calibration parameters must be a list")
    result: list[CalibrationDatum] = []
    for value in values:
        if not isinstance(value, dict) or "name" not in value or "value" not in value:
            raise SnapshotContractError(
                "each backend calibration parameter requires name and value"
            )
        result.append(
            CalibrationDatum(
                name=str(value["name"]),
                value=to_json_safe(value["value"]),
                unit=None if value.get("unit") is None else str(value["unit"]),
                timestamp=_aware_datetime(value.get("date"), "calibration timestamp"),
            )
        )
    return sorted(
        result,
        key=lambda item: (
            item.name,
            item.unit or "",
            "" if item.timestamp is None else item.timestamp.isoformat(),
        ),
    )


def _properties_payload(properties: Any | None) -> dict[str, Any]:
    if properties is None:
        return {"qubits": [], "gates": [], "general": [], "general_qlists": []}
    payload = properties.to_dict()
    if not isinstance(payload, dict):
        raise SnapshotContractError("backend properties must serialize to a dictionary")
    return payload


def _faulty_components(
    properties: Any | None,
) -> tuple[list[int], list[FaultyInstruction]]:
    if properties is None:
        return [], []
    faulty_qubits = sorted(int(qubit) for qubit in properties.faulty_qubits())
    faulty_instructions = sorted(
        (
            FaultyInstruction(name=str(gate.gate), qubits=list(gate.qubits))
            for gate in properties.faulty_gates()
        ),
        key=lambda item: (item.name, tuple(item.qubits)),
    )
    return faulty_qubits, faulty_instructions


def _qubit_snapshots(
    *,
    num_qubits: int,
    properties: Any | None,
    properties_payload: dict[str, Any],
) -> list[QubitSnapshot]:
    raw_qubits = properties_payload.get("qubits", [])
    if raw_qubits and len(raw_qubits) != num_qubits:
        raise SnapshotContractError(
            "backend properties qubit count does not match target.num_qubits"
        )
    result: list[QubitSnapshot] = []
    for index in range(num_qubits):
        operational: bool | None = None
        if properties is not None:
            operational = bool(properties.is_qubit_operational(index))
        parameters = _calibration_data(raw_qubits[index]) if raw_qubits else []
        result.append(
            QubitSnapshot(
                index=index,
                operational=operational,
                parameters=parameters,
            )
        )
    return result


def _gate_calibrations(
    properties_payload: dict[str, Any],
) -> dict[tuple[str, tuple[int, ...]], list[CalibrationDatum]]:
    result: dict[tuple[str, tuple[int, ...]], list[CalibrationDatum]] = {}
    for gate in properties_payload.get("gates", []):
        if not isinstance(gate, dict) or "gate" not in gate or "qubits" not in gate:
            raise SnapshotContractError(
                "backend gate properties require gate and qubits"
            )
        key = (str(gate["gate"]), tuple(int(qubit) for qubit in gate["qubits"]))
        if key in result:
            raise SnapshotContractError(
                f"duplicate backend gate properties for {key[0]}{key[1]}"
            )
        result[key] = _calibration_data(gate.get("parameters", []))
    return result


def _operation_parameters(operation: Any) -> list[JsonValue]:
    parameters = getattr(operation, "params", ())
    if not isinstance(parameters, (list, tuple)):
        return []
    result: list[JsonValue] = []
    for parameter in parameters:
        try:
            result.append(to_json_safe(parameter))
        except TypeError:
            module = type(parameter).__module__
            if not module.startswith("qiskit."):
                raise SnapshotContractError(
                    "target operation parameter has no stable JSON representation: "
                    f"{module}.{type(parameter).__qualname__}"
                ) from None
            result.append(str(parameter))
    return result


def _property_float(
    properties: Any,
    method_name: str,
    instruction_name: str,
    qargs: tuple[int, ...],
) -> float | None:
    try:
        value = getattr(properties, method_name)(instruction_name, qargs)
    except Exception:  # Qiskit raises several lookup-specific exception types.
        return None
    return None if value is None else float(value)


def _gate_operational(
    properties: Any,
    instruction_name: str,
    qargs: tuple[int, ...],
    fallback: bool,
) -> bool:
    """Require both provider gate status and fault-derived component status."""
    try:
        return fallback and bool(
            properties.is_gate_operational(instruction_name, qargs)
        )
    except Exception:  # Qiskit raises for non-gate target instructions.
        return fallback


def _instruction_snapshots(
    *,
    target: Any,
    properties: Any | None,
    properties_payload: dict[str, Any],
    faulty_qubits: list[int],
    faulty_instructions: list[FaultyInstruction],
) -> list[InstructionSnapshot]:
    calibrations = _gate_calibrations(properties_payload)
    faulty_keys = {
        (instruction.name, tuple(instruction.qubits))
        for instruction in faulty_instructions
    }
    faulty_qubit_set = set(faulty_qubits)
    result: list[InstructionSnapshot] = []
    for name in sorted(target.operation_names):
        operation = target.operation_from_name(name)
        operation_parameters = _operation_parameters(operation)
        entries = sorted(
            target[name].items(),
            key=lambda item: () if item[0] is None else tuple(item[0]),
        )
        for qargs_value, target_properties in entries:
            qargs = None if qargs_value is None else tuple(int(q) for q in qargs_value)
            error = (
                None
                if target_properties is None or target_properties.error is None
                else float(target_properties.error)
            )
            duration = (
                None
                if target_properties is None or target_properties.duration is None
                else float(target_properties.duration)
            )
            operational: bool | None = None
            calibration_parameters: list[CalibrationDatum] = []
            if qargs is not None:
                key = (name, qargs)
                calibration_parameters = calibrations.get(key, [])
                if properties is not None:
                    historical_error = _property_float(
                        properties, "gate_error", name, qargs
                    )
                    historical_duration = _property_float(
                        properties, "gate_length", name, qargs
                    )
                    if historical_error is not None:
                        error = historical_error
                    if historical_duration is not None:
                        duration = historical_duration
                    operational = key not in faulty_keys and not (
                        set(qargs) & faulty_qubit_set
                    )
                    operational = _gate_operational(
                        properties, name, qargs, operational
                    )
            result.append(
                InstructionSnapshot(
                    name=name,
                    qubits=None if qargs is None else list(qargs),
                    error=error,
                    duration=duration,
                    operational=operational,
                    operation_parameters=operation_parameters,
                    calibration_parameters=calibration_parameters,
                )
            )
    return result


def _target_metadata(target: Any) -> TargetMetadata:
    timing = target.timing_constraints()
    concurrent = target.concurrent_measurements
    return TargetMetadata(
        num_qubits=int(target.num_qubits),
        physical_qubits=[int(qubit) for qubit in target.physical_qubits],
        operation_names=sorted(str(name) for name in target.operation_names),
        global_operations=sorted(
            str(name) for name in target.operation_names if None in target[name]
        ),
        dt=None if target.dt is None else float(target.dt),
        granularity=int(timing.granularity),
        min_length=int(timing.min_length),
        pulse_alignment=int(timing.pulse_alignment),
        acquire_alignment=int(timing.acquire_alignment),
        concurrent_measurements=None
        if concurrent is None
        else [sorted(int(qubit) for qubit in group) for group in concurrent],
    )


def _coupling_edges(backend: Any, target: Any) -> list[list[int]]:
    coupling_map = getattr(backend, "coupling_map", None)
    if coupling_map is None:
        coupling_map = target.build_coupling_map()
    if coupling_map is None:
        return []
    return sorted(
        ([int(edge[0]), int(edge[1])] for edge in coupling_map.get_edges()),
        key=lambda edge: (edge[0], edge[1]),
    )


def _processor_metadata(backend: Any) -> ProcessorMetadata:
    raw = getattr(backend, "processor_type", None)
    if raw is None:
        try:
            raw = getattr(backend.configuration(), "processor_type", None)
        except Exception:
            raw = None
    if isinstance(raw, dict):
        return ProcessorMetadata(
            family=None if raw.get("family") is None else str(raw["family"]),
            revision=None if raw.get("revision") is None else str(raw["revision"]),
            segment=None if raw.get("segment") is None else str(raw["segment"]),
            raw=to_json_safe(raw),
        )
    return ProcessorMetadata(
        family=None if raw is None else str(raw),
        raw=None if raw is None else to_json_safe(raw),
    )


def _backend_status(backend: Any) -> BackendStatusSnapshot:
    try:
        status = backend.status()
    except Exception:
        return BackendStatusSnapshot(
            operational=None, pending_jobs=None, status_message=None
        )
    pending_jobs = getattr(status, "pending_jobs", None)
    return BackendStatusSnapshot(
        operational=None
        if getattr(status, "operational", None) is None
        else bool(status.operational),
        pending_jobs=None if pending_jobs is None else int(pending_jobs),
        status_message=None
        if getattr(status, "status_msg", None) is None
        else str(status.status_msg),
    )


def target_content_hash(snapshot: BackendSnapshot) -> str:
    """Hash the complete target structure and per-tuple target properties."""
    return canonical_json_hash(
        {
            "target": snapshot.target,
            "instructions": snapshot.instructions,
            "coupling_edges": snapshot.coupling_edges,
        }
    )


def snapshot_content_hash(snapshot: BackendSnapshot) -> str:
    """Hash reproducible target/calibration content, not live observations.

    ``backend_status`` remains part of the complete snapshot artifact, but its
    queue depth, availability, and status text are volatile scheduling evidence.
    They must not change the scientific/calibration identity used by callers to
    bind compilation and execution.
    """
    payload = snapshot.model_dump(mode="python")
    for observation_field in ("snapshot_hash", "retrieved_at", "backend_status"):
        payload.pop(observation_field)
    return canonical_json_hash(payload)


def build_backend_snapshot(
    backend: Any,
    *,
    instance_id: str,
    properties: Any | None,
    properties_at: datetime | None = None,
    fractional_gate_mode: FractionalGateMode = "disabled",
    retrieved_at: datetime | None = None,
) -> BackendSnapshot:
    """Build a complete snapshot from one already-resolved backend and properties."""
    backend_name = str(getattr(backend, "name", ""))
    validate_snapshot_request(
        backend_name=backend_name,
        instance_id=instance_id,
        properties_at=properties_at,
        fractional_gate_mode=fractional_gate_mode,
        dynamic_circuits=False,
        pec=False,
        pea=False,
        gate_twirling=False,
    )
    retrieved_at = retrieved_at or datetime.now(timezone.utc)
    _aware_datetime(retrieved_at, "retrieved_at")
    target = backend.target
    properties_payload = _properties_payload(properties)
    faulty_qubits, faulty_instructions = _faulty_components(properties)
    target_metadata = _target_metadata(target)
    instructions = _instruction_snapshots(
        target=target,
        properties=properties,
        properties_payload=properties_payload,
        faulty_qubits=faulty_qubits,
        faulty_instructions=faulty_instructions,
    )
    coupling_edges = _coupling_edges(backend, target)
    backend_version = getattr(backend, "backend_version", None)
    snapshot = BackendSnapshot(
        schema_version=SCHEMA_VERSION,
        backend_name=backend_name,
        instance_id=instance_id.strip(),
        retrieved_at=retrieved_at,
        properties_at=properties_at,
        properties_last_update=_aware_datetime(
            None if properties is None else properties.last_update_date,
            "properties.last_update_date",
        ),
        properties_available=properties is not None,
        fractional_gate_mode=fractional_gate_mode,
        backend_version=None if backend_version is None else str(backend_version),
        processor=_processor_metadata(backend),
        backend_status=_backend_status(backend),
        target=target_metadata,
        target_hash=_ZERO_HASH,
        snapshot_hash=_ZERO_HASH,
        qubits=_qubit_snapshots(
            num_qubits=target_metadata.num_qubits,
            properties=properties,
            properties_payload=properties_payload,
        ),
        instructions=instructions,
        coupling_edges=coupling_edges,
        faulty_qubits=faulty_qubits,
        faulty_instructions=faulty_instructions,
        general_parameters=_calibration_data(properties_payload.get("general", [])),
        general_qlists=[
            to_json_safe(value)
            for value in properties_payload.get("general_qlists", [])
        ],
        software_versions=_package_versions(),
    )
    snapshot.target_hash = target_content_hash(snapshot)
    snapshot.snapshot_hash = snapshot_content_hash(snapshot)
    return snapshot


def resolve_backend_snapshot(
    runtime_service: Any,
    *,
    backend_name: str,
    instance_id: str,
    properties_at: datetime | None = None,
    fractional_gate_mode: FractionalGateMode = "disabled",
    dynamic_circuits: bool = False,
    pec: bool = False,
    pea: bool = False,
    gate_twirling: bool = False,
    retrieved_at: datetime | None = None,
) -> BackendSnapshot:
    """Resolve one explicit backend and read current or historical metadata only."""
    validate_snapshot_request(
        backend_name=backend_name,
        instance_id=instance_id,
        properties_at=properties_at,
        fractional_gate_mode=fractional_gate_mode,
        dynamic_circuits=dynamic_circuits,
        pec=pec,
        pea=pea,
        gate_twirling=gate_twirling,
    )
    backend = runtime_service.backend(
        backend_name.strip(),
        instance=instance_id.strip(),
        use_fractional_gates=_FRACTIONAL_FLAGS[fractional_gate_mode],
    )
    properties = backend.properties(refresh=False, datetime=properties_at)
    return build_backend_snapshot(
        backend,
        instance_id=instance_id,
        properties=properties,
        properties_at=properties_at,
        fractional_gate_mode=fractional_gate_mode,
        retrieved_at=retrieved_at,
    )
