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

"""Exact circuit ingestion, target validation, and explicit transpilation."""

from __future__ import annotations

import base64
import binascii
import io
import platform
import struct
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Any, Literal

import qiskit
from qiskit import QuantumCircuit, qpy
from qiskit.circuit import Gate, Instruction
from qiskit.circuit.controlflow import ControlFlowOp
from qiskit.qasm3 import loads as qasm3_loads
from qiskit.transpiler import Target
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

from .artifacts import ArtifactSink, content_id
from .models import BackendSnapshot, CircuitArtifact, CircuitProvenance, CircuitRegister
from .serialization import canonical_json_hash, to_json_safe
from .snapshots import target_content_hash


CircuitFormat = Literal["qpy", "qasm3"]
CircuitMode = Literal["exact", "validate", "transpile"]
IsaValidationReason = Literal[
    "unsupported_operation",
    "unsupported_qubit_tuple",
    "unsupported_parameters_or_variant",
]
_QPY_HEADER_PRE_V10 = struct.Struct("!6sBBBBQ")
_QPY_HEADER_V10 = struct.Struct("!6sBBBBQc")
_QPY_MAGIC = b"QISKIT"


class CircuitContractError(ValueError):
    """Base error for rejected circuit-boundary requests."""


class CircuitLimitError(CircuitContractError):
    """Raised when encoded, decoded, or structural circuit limits are exceeded."""


class CircuitFormatError(CircuitContractError):
    """Raised when circuit serialization is malformed or unsupported."""


class TargetIdentityError(CircuitContractError):
    """Raised when backend identity and target structure no longer match."""


class CircuitWidthError(CircuitContractError):
    """Raised when a circuit contains physical wires outside the target."""


@dataclass(frozen=True)
class CircuitLimits:
    """Resource limits applied at the earliest observable boundary."""

    max_payload_bytes: int = 10 * 1024 * 1024
    max_qubits: int = 127
    max_operations: int = 100_000
    max_registers: int = 256
    max_parameters: int = 10_000

    def __post_init__(self) -> None:
        for field_name, value in vars(self).items():
            if value < 1:
                raise ValueError(f"{field_name} must be at least 1")


@dataclass(frozen=True)
class QpyHeader:
    """Security-relevant QPY header fields inspected before deserialization."""

    qpy_version: int
    qiskit_version: str
    num_programs: int
    symbolic_encoding: str | None


@dataclass(frozen=True)
class IngestedCircuit:
    """A parsed circuit paired with its exact immutable source artifact."""

    circuit: QuantumCircuit
    artifact: CircuitArtifact
    serialized_bytes: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if content_id(self.serialized_bytes) != self.artifact.circuit_hash:
            raise CircuitContractError(
                "serialized source bytes do not match the circuit artifact hash"
            )


@dataclass(frozen=True)
class IsaValidationIssue:
    """One unsupported operation or physical qubit tuple."""

    instruction_index: int
    instruction_path: tuple[int, ...]
    operation_name: str
    qubits: tuple[int, ...]
    reason: IsaValidationReason


@dataclass(frozen=True)
class CircuitValidationReport:
    """Evidence that target validation observed an unchanged artifact hash."""

    target_hash: str
    compiler_target_hash: str
    circuit_hash_before: str
    circuit_hash_after: str
    instruction_count: int


class CircuitIsaError(CircuitContractError):
    """Raised when a circuit contains instructions outside the supplied target."""

    def __init__(self, issues: tuple[IsaValidationIssue, ...]) -> None:
        self.issues = issues
        details = "; ".join(
            f"#{issue.instruction_index} path={issue.instruction_path} "
            f"{issue.operation_name}{issue.qubits} "
            f"({issue.reason})"
            for issue in issues
        )
        super().__init__(f"circuit is not compatible with the target: {details}")


@dataclass(frozen=True)
class CircuitBoundaryResult:
    """The exact output selected by one explicit compilation mode."""

    mode: CircuitMode
    circuit: QuantumCircuit
    artifact: CircuitArtifact
    validation: CircuitValidationReport | None


def _target_parameter(value: Any) -> object:
    """Normalize Qiskit-owned target parameters without accepting foreign objects."""
    try:
        return to_json_safe(value)
    except TypeError:
        if not type(value).__module__.startswith("qiskit."):
            raise TargetIdentityError(
                "target operation parameter has no deterministic representation"
            ) from None
        return str(value)


def _operation_class(operation: Instruction) -> type[Instruction]:
    """Return Qiskit's canonical class instead of ephemeral singleton subclasses."""
    base_class = operation.base_class
    return base_class if isinstance(base_class, type) else type(operation)


def _requires_definition_identity(operation: Instruction) -> bool:
    """Return whether class identity alone is insufficient for semantics."""
    operation_class = _operation_class(operation)
    module = operation_class.__module__ or ""
    return operation_class in (Gate, Instruction) or not module.startswith("qiskit.")


def _operation_descriptor(
    operation: Instruction,
    *,
    active_definitions: set[int] | None = None,
) -> dict[str, object]:
    """Describe operation semantics, recursively including custom definitions."""
    operation_class = _operation_class(operation)
    descriptor: dict[str, object] = {
        "operation_name": operation.name,
        "operation_class": (
            f"{operation_class.__module__}.{operation_class.__qualname__}"
        ),
        "num_qubits": operation.num_qubits,
        "num_clbits": operation.num_clbits,
        "parameters": [_target_parameter(value) for value in operation.params],
    }
    if not _requires_definition_identity(operation):
        return descriptor
    definition = operation.definition
    if definition is None:
        raise TargetIdentityError(
            f"operation {operation.name!r} has no deterministic semantic definition"
        )
    active = active_definitions if active_definitions is not None else set()
    marker = id(operation)
    if marker in active:
        raise TargetIdentityError("recursive operation definitions are not supported")
    active.add(marker)
    try:
        definition_instructions = []
        for instruction in definition.data:
            if isinstance(instruction.operation, ControlFlowOp):
                raise TargetIdentityError(
                    "custom operation definitions containing control flow are opaque"
                )
            definition_instructions.append(
                {
                    "operation": _operation_descriptor(
                        instruction.operation,
                        active_definitions=active,
                    ),
                    "qubits": [
                        definition.find_bit(qubit).index for qubit in instruction.qubits
                    ],
                    "clbits": [
                        definition.find_bit(clbit).index for clbit in instruction.clbits
                    ],
                }
            )
        descriptor["definition"] = {
            "num_qubits": definition.num_qubits,
            "num_clbits": definition.num_clbits,
            "global_phase": _target_parameter(definition.global_phase),
            "instructions": definition_instructions,
        }
    finally:
        active.remove(marker)
    return descriptor


def target_fingerprint(target: Target) -> str:
    """Hash the complete public ISA/compiler structure of the locked Qiskit Target."""
    if target.has_angle_bounds():
        raise TargetIdentityError(
            "targets with opaque angle-bound state cannot be fingerprinted exactly"
        )
    timing = target.timing_constraints()
    instructions: list[dict[str, object]] = []
    for name in sorted(target.operation_names):
        operation = target.operation_from_name(name)
        operation_class = (
            operation if isinstance(operation, type) else _operation_class(operation)
        )
        operation_identity = (
            {
                "operation_name": name,
                "operation_class": (
                    f"{operation_class.__module__}.{operation_class.__qualname__}"
                ),
                "num_qubits": None,
                "num_clbits": None,
                "parameters": [],
            }
            if isinstance(operation, type)
            else _operation_descriptor(operation)
        )
        for qargs, properties in sorted(
            target[name].items(),
            key=lambda item: () if item[0] is None else tuple(item[0]),
        ):
            if (
                properties is not None
                and getattr(properties, "calibration", None) is not None
            ):
                raise TargetIdentityError(
                    "targets with opaque instruction calibrations cannot be "
                    "fingerprinted exactly"
                )
            instructions.append(
                {
                    **operation_identity,
                    "registered_name": name,
                    "qubits": None if qargs is None else list(qargs),
                    "duration": None if properties is None else properties.duration,
                    "error": None if properties is None else properties.error,
                }
            )
    qubit_properties = None
    if target.qubit_properties is not None:
        qubit_properties = [
            {
                "t1": properties.t1,
                "t2": properties.t2,
                "frequency": properties.frequency,
            }
            for properties in target.qubit_properties
        ]
    return canonical_json_hash(
        {
            "num_qubits": target.num_qubits,
            "physical_qubits": list(target.physical_qubits),
            "dt": target.dt,
            "granularity": timing.granularity,
            "min_length": timing.min_length,
            "pulse_alignment": timing.pulse_alignment,
            "acquire_alignment": timing.acquire_alignment,
            "concurrent_measurements": target.concurrent_measurements,
            "qubit_properties": qubit_properties,
            "instructions": instructions,
        }
    )


@dataclass(frozen=True)
class ResolvedTarget:
    """Bind a live compiler target to its authoritative backend snapshot."""

    backend: object = field(repr=False)
    snapshot: BackendSnapshot
    target: Target = field(init=False)
    backend_name: str = field(init=False)
    target_hash: str = field(init=False)
    compiler_target_hash: str = field(init=False)

    @staticmethod
    def _backend_identity(backend: object) -> tuple[str, Target]:
        """Read the two backend-owned values callers must not supply separately."""
        backend_name = getattr(backend, "name", None)
        if callable(backend_name):
            backend_name = backend_name()
        target = getattr(backend, "target", None)
        if not isinstance(backend_name, str) or not backend_name:
            raise TargetIdentityError("resolved target requires a named backend")
        if not isinstance(target, Target):
            raise TargetIdentityError("resolved target requires backend.target")
        return backend_name, target

    @staticmethod
    def _assert_snapshot_matches_target(
        snapshot: BackendSnapshot,
        backend_name: str,
        target: Target,
    ) -> None:
        """Verify snapshot integrity and its public structural link to the target."""
        if snapshot.backend_name != backend_name:
            raise TargetIdentityError(
                "backend snapshot name does not match the resolved backend"
            )
        if target_content_hash(snapshot) != snapshot.target_hash:
            raise TargetIdentityError(
                "backend snapshot target hash failed verification"
            )

        timing = target.timing_constraints()
        concurrent = target.concurrent_measurements
        target_metadata = {
            "num_qubits": target.num_qubits,
            "physical_qubits": list(target.physical_qubits),
            "operation_names": sorted(target.operation_names),
            "global_operations": sorted(
                name for name in target.operation_names if None in target[name]
            ),
            "dt": target.dt,
            "granularity": timing.granularity,
            "min_length": timing.min_length,
            "pulse_alignment": timing.pulse_alignment,
            "acquire_alignment": timing.acquire_alignment,
            "concurrent_measurements": (
                None if concurrent is None else [sorted(group) for group in concurrent]
            ),
        }
        if snapshot.target.model_dump(mode="python") != target_metadata:
            raise TargetIdentityError(
                "backend snapshot target metadata does not match backend.target"
            )

        live_instructions = []
        for name in sorted(target.operation_names):
            operation = target.operation_from_name(name)
            parameters = (
                []
                if isinstance(operation, type)
                else [_target_parameter(value) for value in operation.params]
            )
            for qargs in sorted(
                target[name], key=lambda value: () if value is None else tuple(value)
            ):
                live_instructions.append(
                    {
                        "name": name,
                        "qubits": None if qargs is None else list(qargs),
                        "operation_parameters": parameters,
                    }
                )
        snapshot_instructions = [
            {
                "name": instruction.name,
                "qubits": instruction.qubits,
                "operation_parameters": instruction.operation_parameters,
            }
            for instruction in snapshot.instructions
        ]
        if snapshot_instructions != live_instructions:
            raise TargetIdentityError(
                "backend snapshot instructions do not match backend.target"
            )

    def __post_init__(self) -> None:
        backend_name, target = self._backend_identity(self.backend)
        self._assert_snapshot_matches_target(self.snapshot, backend_name, target)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "backend_name", backend_name)
        object.__setattr__(self, "target_hash", self.snapshot.target_hash)
        object.__setattr__(self, "compiler_target_hash", target_fingerprint(target))

    def verify_current(self) -> None:
        """Reject backend/target replacement or mutation after resolution."""
        backend_name, target = self._backend_identity(self.backend)
        if backend_name != self.backend_name:
            raise TargetIdentityError("backend name changed after target resolution")
        if target is not self.target:
            raise TargetIdentityError("backend target changed after target resolution")
        if self.snapshot.target_hash != self.target_hash:
            raise TargetIdentityError(
                "backend snapshot target hash changed after resolution"
            )
        self._assert_snapshot_matches_target(self.snapshot, backend_name, target)
        if target_fingerprint(self.target) != self.compiler_target_hash:
            raise TargetIdentityError(
                "target structure changed after target resolution"
            )


def _software_versions() -> dict[str, str]:
    """Return the package identities needed to reproduce circuit handling."""
    versions = {"python": platform.python_version()}
    for distribution in (
        "qiskit",
        "qiskit-ibm-runtime",
        "qiskit-ibm-runtime-mcp-server",
    ):
        try:
            versions[distribution] = package_version(distribution)
        except PackageNotFoundError:  # pragma: no cover - source trees are supported
            versions[distribution] = "source-tree"
    return versions


def _parse_qpy_header(data: bytes) -> QpyHeader:
    """Inspect compatibility and cardinality before invoking ``qpy.load``."""
    if len(data) < 7:
        raise CircuitFormatError("QPY payload is too short to contain a header")
    if data[:6] != _QPY_MAGIC:
        raise CircuitFormatError("QPY payload has an invalid magic header")
    qpy_version = data[6]
    if qpy_version > qpy.QPY_VERSION:
        raise CircuitFormatError(
            f"QPY version {qpy_version} is newer than supported version "
            f"{qpy.QPY_VERSION}; upgrade Qiskit before ingesting this artifact"
        )
    header_format = _QPY_HEADER_PRE_V10 if qpy_version < 10 else _QPY_HEADER_V10
    if len(data) < header_format.size:
        raise CircuitFormatError("QPY payload contains a truncated file header")
    unpacked = header_format.unpack_from(data)
    writer_version = ".".join(str(part) for part in unpacked[2:5])
    symbolic_encoding = None
    if qpy_version >= 10:
        try:
            symbolic_encoding = unpacked[6].decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise CircuitFormatError(
                "QPY header has an invalid symbolic encoding marker"
            ) from exc
    return QpyHeader(
        qpy_version=qpy_version,
        qiskit_version=writer_version,
        num_programs=unpacked[5],
        symbolic_encoding=symbolic_encoding,
    )


def _decode_qpy(data: bytes | str, limits: CircuitLimits) -> bytes:
    """Decode QPY only after bounding the base64 and decoded representations."""
    if isinstance(data, bytes):
        if len(data) > limits.max_payload_bytes:
            raise CircuitLimitError(
                f"decoded QPY payload exceeds {limits.max_payload_bytes} bytes"
            )
        return data

    max_encoded_bytes = 4 * ((limits.max_payload_bytes + 2) // 3)
    if len(data) > max_encoded_bytes:
        raise CircuitLimitError(
            f"base64 QPY payload exceeds the encoded limit for "
            f"{limits.max_payload_bytes} decoded bytes"
        )
    compact = "".join(data.split())
    try:
        decoded = base64.b64decode(compact, validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError) as exc:
        raise CircuitFormatError("QPY payload is not valid base64") from exc
    if len(decoded) > limits.max_payload_bytes:
        raise CircuitLimitError(
            f"decoded QPY payload exceeds {limits.max_payload_bytes} bytes"
        )
    return decoded


def _decode_qasm3(data: bytes | str, limits: CircuitLimits) -> tuple[bytes, str]:
    """Bound QASM bytes before UTF-8 decoding and parser invocation."""
    if isinstance(data, str):
        if len(data) > limits.max_payload_bytes:
            raise CircuitLimitError(
                f"QASM3 payload exceeds {limits.max_payload_bytes} bytes"
            )
        encoded = data.encode("utf-8")
        text = data
    else:
        if len(data) > limits.max_payload_bytes:
            raise CircuitLimitError(
                f"QASM3 payload exceeds {limits.max_payload_bytes} bytes"
            )
        encoded = data
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CircuitFormatError("QASM3 payload must be valid UTF-8") from exc
    if len(encoded) > limits.max_payload_bytes:
        raise CircuitLimitError(
            f"QASM3 payload exceeds {limits.max_payload_bytes} bytes"
        )
    return encoded, text


def _operation_count(circuit: QuantumCircuit) -> int:
    """Count control-flow containers and every recursively nested instruction."""
    total = 0
    pending = [circuit]
    while pending:
        current = pending.pop()
        total += len(current.data)
        for instruction in current.data:
            if isinstance(instruction.operation, ControlFlowOp):
                pending.extend(instruction.operation.blocks)
    return total


def _enforce_structural_limits(circuit: QuantumCircuit, limits: CircuitLimits) -> None:
    """Reject parsed circuits before they enter validation or compilation."""
    observed = {
        "qubits": (circuit.num_qubits, limits.max_qubits),
        "operations": (_operation_count(circuit), limits.max_operations),
        "registers": (len(circuit.qregs) + len(circuit.cregs), limits.max_registers),
        "parameters": (len(circuit.parameters), limits.max_parameters),
    }
    exceeded = [
        f"{name}={actual} exceeds {maximum}"
        for name, (actual, maximum) in observed.items()
        if actual > maximum
    ]
    if exceeded:
        raise CircuitLimitError(
            "circuit structural limits exceeded: " + ", ".join(exceeded)
        )


def _registers(circuit: QuantumCircuit) -> list[CircuitRegister]:
    """Capture names, kinds, and exact positions for every Qiskit register."""
    registers = [
        CircuitRegister(
            kind="quantum",
            name=register.name,
            size=register.size,
            bit_indices=[circuit.find_bit(bit).index for bit in register],
        )
        for register in circuit.qregs
    ]
    registers.extend(
        CircuitRegister(
            kind="classical",
            name=register.name,
            size=register.size,
            bit_indices=[circuit.find_bit(bit).index for bit in register],
        )
        for register in circuit.cregs
    )
    return registers


def _layout(circuit: QuantumCircuit) -> dict[str, object] | None:
    """Return a stable summary while exact QPY bytes retain the full layout object."""
    layout = circuit.layout
    if layout is None:
        return None
    return {
        "initial_index_layout": layout.initial_index_layout(filter_ancillas=False),
        "final_index_layout": layout.final_index_layout(filter_ancillas=False),
        "routing_permutation": layout.routing_permutation(),
        "num_input_qubits": len(layout.initial_index_layout(filter_ancillas=True)),
    }


def _build_artifact(
    *,
    circuit: QuantumCircuit,
    raw_bytes: bytes,
    circuit_format: CircuitFormat,
    sink: ArtifactSink,
    writer_qiskit_version: str | None,
    qpy_version: int | None,
    qpy_symbolic_encoding: str | None,
    provenance: CircuitProvenance,
) -> CircuitArtifact:
    """Persist exact bytes and bind all structural metadata to their digest."""
    digest = content_id(raw_bytes)
    artifact = sink.put_bytes(
        raw_bytes,
        kind="circuit",
        media_type=("application/qpy" if circuit_format == "qpy" else "text/qasm3"),
        metadata={
            "format": circuit_format,
            "circuit_hash": digest,
            "writer_qiskit_version": writer_qiskit_version,
            "qpy_version": qpy_version,
        },
    )
    metadata = to_json_safe(circuit.metadata or {})
    if not isinstance(metadata, dict):  # pragma: no cover - Qiskit contract
        raise CircuitFormatError("circuit metadata must be a JSON object")
    return CircuitArtifact(
        schema_version="1.0",
        artifact=artifact,
        format=circuit_format,
        circuit_hash=digest,
        num_qubits=circuit.num_qubits,
        num_clbits=circuit.num_clbits,
        size=circuit.size(),
        depth=circuit.depth(),
        parameter_names=[parameter.name for parameter in circuit.parameters],
        registers=_registers(circuit),
        metadata=metadata,
        qiskit_version=writer_qiskit_version,
        reader_qiskit_version=qiskit.__version__,
        qpy_version=qpy_version,
        qpy_symbolic_encoding=qpy_symbolic_encoding,
        layout=_layout(circuit),
        provenance=provenance,
    )


def ingest_circuit(
    data: bytes | str,
    *,
    circuit_format: CircuitFormat,
    sink: ArtifactSink,
    limits: CircuitLimits | None = None,
) -> IngestedCircuit:
    """Ingest one circuit without format guessing or silent collection selection."""
    active_limits = limits or CircuitLimits()
    header: QpyHeader | None = None
    if circuit_format == "qpy":
        raw_bytes = _decode_qpy(data, active_limits)
        header = _parse_qpy_header(raw_bytes)
        if header.num_programs != 1:
            raise CircuitFormatError(
                "QPY payload must contain exactly one circuit; "
                f"found {header.num_programs}"
            )
        try:
            programs = qpy.load(io.BytesIO(raw_bytes))
        except Exception as exc:
            raise CircuitFormatError(f"QPY deserialization failed: {exc}") from exc
        if len(programs) != 1 or not isinstance(programs[0], QuantumCircuit):
            raise CircuitFormatError(
                "QPY payload did not deserialize to one QuantumCircuit"
            )
        circuit = programs[0]
        writer_qiskit_version = header.qiskit_version
        qpy_version = header.qpy_version
        symbolic_encoding = header.symbolic_encoding
    else:
        raw_bytes, text = _decode_qasm3(data, active_limits)
        try:
            circuit = qasm3_loads(text)
        except Exception as exc:
            raise CircuitFormatError(f"QASM3 deserialization failed: {exc}") from exc
        writer_qiskit_version = None
        qpy_version = None
        symbolic_encoding = None

    _enforce_structural_limits(circuit, active_limits)
    provenance = CircuitProvenance(
        transformation="source",
        software_versions=_software_versions(),
    )
    artifact = _build_artifact(
        circuit=circuit,
        raw_bytes=raw_bytes,
        circuit_format=circuit_format,
        sink=sink,
        writer_qiskit_version=writer_qiskit_version,
        qpy_version=qpy_version,
        qpy_symbolic_encoding=symbolic_encoding,
        provenance=provenance,
    )
    return IngestedCircuit(
        circuit=circuit,
        artifact=artifact,
        serialized_bytes=raw_bytes,
    )


def _circuit_from_immutable_source(source: IngestedCircuit) -> QuantumCircuit:
    """Reconstruct executable state from hash-bound bytes, never mutable cache state."""
    if content_id(source.serialized_bytes) != source.artifact.circuit_hash:
        raise CircuitContractError("circuit source bytes failed integrity verification")
    if source.artifact.format == "qpy":
        return _load_single_qpy(source.serialized_bytes)
    try:
        text = source.serialized_bytes.decode("utf-8")
        return qasm3_loads(text)
    except Exception as exc:
        raise CircuitFormatError(f"QASM3 deserialization failed: {exc}") from exc


def _load_single_qpy(raw_bytes: bytes) -> QuantumCircuit:
    """Reload one QPY circuit after independently checking its file cardinality."""
    header = _parse_qpy_header(raw_bytes)
    if header.num_programs != 1:
        raise CircuitFormatError(
            "immutable QPY source must contain exactly one circuit"
        )
    try:
        programs = qpy.load(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise CircuitFormatError(f"QPY deserialization failed: {exc}") from exc
    if len(programs) != 1 or not isinstance(programs[0], QuantumCircuit):
        raise CircuitFormatError(
            "immutable QPY source did not deserialize to one QuantumCircuit"
        )
    return programs[0]


def _validate_circuit_isa(
    circuit: QuantumCircuit,
    artifact: CircuitArtifact,
    *,
    resolved_target: ResolvedTarget,
) -> CircuitValidationReport:
    """Validate one immutable-source circuit without mutation."""
    resolved_target.verify_current()
    target = resolved_target.target
    if circuit.num_qubits > target.num_qubits:
        raise CircuitWidthError(
            f"circuit has {circuit.num_qubits} qubits but target "
            f"{resolved_target.backend_name} has {target.num_qubits}"
        )
    issues: list[IsaValidationIssue] = []
    operation_names = target.operation_names
    next_instruction_index = 0
    pending: list[tuple[QuantumCircuit, tuple[int, ...], tuple[int, ...]]] = [
        (circuit, tuple(range(circuit.num_qubits)), ())
    ]
    while pending:
        current, physical_qubits, parent_path = pending.pop()
        nested_blocks: list[
            tuple[QuantumCircuit, tuple[int, ...], tuple[int, ...]]
        ] = []
        for local_index, instruction in enumerate(current.data):
            operation = instruction.operation
            instruction_path = parent_path + (local_index,)
            qubits = tuple(
                physical_qubits[current.find_bit(qubit).index]
                for qubit in instruction.qubits
            )
            reason: IsaValidationReason | None = None
            if isinstance(operation, ControlFlowOp):
                if operation.name not in operation_names:
                    reason = "unsupported_operation"
                elif not target.instruction_supported(
                    operation_name=operation.name,
                    qargs=qubits,
                ):
                    reason = "unsupported_qubit_tuple"
            else:
                parameters = list(operation.params)
                if _requires_definition_identity(operation):
                    circuit_descriptor = _operation_descriptor(operation)
                    semantic_names = [
                        name
                        for name in operation_names
                        if not isinstance(target.operation_from_name(name), type)
                        and _operation_descriptor(target.operation_from_name(name))
                        == circuit_descriptor
                    ]
                    if any(
                        target.instruction_supported(
                            operation_name=name,
                            qargs=qubits,
                            parameters=parameters,
                        )
                        for name in semantic_names
                    ):
                        pass
                    elif not semantic_names:
                        reason = "unsupported_parameters_or_variant"
                    elif not any(
                        target.instruction_supported(
                            operation_name=name,
                            qargs=qubits,
                        )
                        for name in semantic_names
                    ):
                        reason = "unsupported_qubit_tuple"
                    else:
                        reason = "unsupported_parameters_or_variant"
                else:
                    name_supports_parameters = (
                        operation.name in operation_names
                        and target.instruction_supported(
                            operation_name=operation.name,
                            qargs=qubits,
                            parameters=parameters,
                        )
                    )
                    operation_class = _operation_class(operation)
                    class_supports_parameters = target.instruction_supported(
                        operation_class=operation_class,
                        qargs=qubits,
                        parameters=parameters,
                    )
                    if name_supports_parameters or class_supports_parameters:
                        pass
                    elif operation.name not in operation_names and not (
                        target.instruction_supported(operation_class=operation_class)
                    ):
                        reason = "unsupported_operation"
                    elif not (
                        (
                            operation.name in operation_names
                            and target.instruction_supported(
                                operation_name=operation.name,
                                qargs=qubits,
                            )
                        )
                        or target.instruction_supported(
                            operation_class=operation_class,
                            qargs=qubits,
                        )
                    ):
                        reason = "unsupported_qubit_tuple"
                    else:
                        reason = "unsupported_parameters_or_variant"
            if reason is not None:
                issues.append(
                    IsaValidationIssue(
                        instruction_index=next_instruction_index,
                        instruction_path=instruction_path,
                        operation_name=operation.name,
                        qubits=qubits,
                        reason=reason,
                    )
                )
            if isinstance(operation, ControlFlowOp):
                nested_blocks.extend(
                    (block, qubits, instruction_path + (block_index,))
                    for block_index, block in enumerate(operation.blocks)
                )
            next_instruction_index += 1
        pending.extend(reversed(nested_blocks))
    if issues:
        raise CircuitIsaError(tuple(issues))
    return CircuitValidationReport(
        target_hash=resolved_target.target_hash,
        compiler_target_hash=resolved_target.compiler_target_hash,
        circuit_hash_before=artifact.circuit_hash,
        circuit_hash_after=artifact.circuit_hash,
        instruction_count=_operation_count(circuit),
    )


def validate_circuit_isa(
    source: IngestedCircuit,
    *,
    resolved_target: ResolvedTarget,
) -> CircuitValidationReport:
    """Check every target operation/qargs pair from immutable source bytes."""
    circuit = _circuit_from_immutable_source(source)
    return _validate_circuit_isa(
        circuit,
        source.artifact,
        resolved_target=resolved_target,
    )


def _dump_current_qpy(circuit: QuantumCircuit) -> tuple[bytes, QpyHeader]:
    buffer = io.BytesIO()
    qpy.dump(circuit, buffer, version=qpy.QPY_VERSION)
    raw_bytes = buffer.getvalue()
    return raw_bytes, _parse_qpy_header(raw_bytes)


def apply_circuit_mode(
    source: IngestedCircuit,
    *,
    mode: CircuitMode,
    resolved_target: ResolvedTarget | None = None,
    sink: ArtifactSink | None = None,
    optimization_level: int | None = None,
    seed_transpiler: int | None = None,
) -> CircuitBoundaryResult:
    """Apply one explicit mode; only ``transpile`` may construct a pass manager."""
    target_arguments_present = resolved_target is not None
    transpiler_arguments_present = any(
        value is not None for value in (sink, optimization_level, seed_transpiler)
    )
    if mode == "exact":
        if target_arguments_present or transpiler_arguments_present:
            raise CircuitContractError(
                "exact mode rejects target and transpiler arguments instead of ignoring them"
            )
        return CircuitBoundaryResult(
            mode=mode,
            circuit=_circuit_from_immutable_source(source),
            artifact=source.artifact,
            validation=None,
        )

    if resolved_target is None:
        raise CircuitContractError(f"{mode} mode requires a ResolvedTarget")
    resolved_target.verify_current()

    if mode == "validate":
        if transpiler_arguments_present:
            raise CircuitContractError(
                "validate mode rejects transpiler arguments instead of ignoring them"
            )
        circuit = _circuit_from_immutable_source(source)
        validation = _validate_circuit_isa(
            circuit,
            source.artifact,
            resolved_target=resolved_target,
        )
        return CircuitBoundaryResult(
            mode=mode,
            circuit=circuit,
            artifact=source.artifact,
            validation=validation,
        )

    if mode != "transpile":
        raise CircuitContractError(f"unsupported circuit mode: {mode}")
    if sink is None or optimization_level is None or seed_transpiler is None:
        raise CircuitContractError(
            "transpile mode requires sink, optimization_level, and seed_transpiler"
        )
    if optimization_level not in (0, 1, 2, 3):
        raise CircuitContractError("optimization_level must be one of 0, 1, 2, or 3")
    pass_manager = generate_preset_pass_manager(
        optimization_level=optimization_level,
        target=resolved_target.target,
        seed_transpiler=seed_transpiler,
    )
    transpiled = pass_manager.run(_circuit_from_immutable_source(source))
    raw_bytes, header = _dump_current_qpy(transpiled)
    executable = _load_single_qpy(raw_bytes)
    provenance = CircuitProvenance(
        transformation="transpile",
        source_circuit_hash=source.artifact.circuit_hash,
        source_artifact_id=source.artifact.artifact.artifact_id,
        target_hash=resolved_target.target_hash,
        compiler_target_hash=resolved_target.compiler_target_hash,
        target_name=resolved_target.backend_name,
        transpiler_name=(
            "qiskit.transpiler.preset_passmanagers.generate_preset_pass_manager"
        ),
        transpiler_options={
            "optimization_level": optimization_level,
            "seed_transpiler": seed_transpiler,
        },
        software_versions=_software_versions(),
    )
    artifact = _build_artifact(
        circuit=executable,
        raw_bytes=raw_bytes,
        circuit_format="qpy",
        sink=sink,
        writer_qiskit_version=header.qiskit_version,
        qpy_version=header.qpy_version,
        qpy_symbolic_encoding=header.symbolic_encoding,
        provenance=provenance,
    )
    validation = _validate_circuit_isa(
        executable,
        artifact,
        resolved_target=resolved_target,
    )
    return CircuitBoundaryResult(
        mode=mode,
        circuit=executable,
        artifact=artifact,
        validation=validation,
    )
