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

"""Version 1 public data contracts for deterministic Runtime workflows."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    JsonValue,
    field_validator,
    model_serializer,
    model_validator,
)

from .serialization import to_json_safe


SCHEMA_VERSION: Literal["1.0"] = "1.0"
SchemaVersion = Literal["1.0"]
Sha256Id = str


class ContractModel(BaseModel):
    """Base contract that preserves future fields and serializes them safely."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)

    @model_serializer(mode="wrap")
    def _serialize_contract(self, _handler: Any) -> dict[str, Any]:
        values = {
            field_name: getattr(self, field_name)
            for field_name in type(self).model_fields
        }
        values.update(self.__pydantic_extra__ or {})
        safe = to_json_safe(values)
        if not isinstance(safe, dict):  # pragma: no cover - guaranteed by construction
            raise TypeError("contract serialization must produce a JSON object")
        return safe


class VersionedContractModel(ContractModel):
    """Base for every independently persisted public contract."""

    schema_version: SchemaVersion


class ArtifactRef(VersionedContractModel):
    """Portable reference to immutable content-addressed bytes."""

    artifact_id: Sha256Id = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    kind: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    size_bytes: NonNegativeInt
    storage_uri: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CircuitRegister(ContractModel):
    """One named register and its exact positions in the circuit bit arrays."""

    kind: Literal["quantum", "classical"]
    name: str = Field(min_length=1)
    size: NonNegativeInt
    bit_indices: list[NonNegativeInt]

    @model_validator(mode="after")
    def _register_positions_match_size(self) -> CircuitRegister:
        if len(self.bit_indices) != self.size:
            raise ValueError("register bit_indices length must equal register size")
        if len(set(self.bit_indices)) != len(self.bit_indices):
            raise ValueError("register bit_indices must not contain duplicates")
        return self


class CircuitProvenance(ContractModel):
    """Typed origin and transformation record for immutable circuit bytes."""

    transformation: Literal["source", "transpile"]
    source_circuit_hash: Sha256Id | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    source_artifact_id: Sha256Id | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    target_hash: Sha256Id | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    compiler_target_hash: Sha256Id | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    target_name: str | None = None
    transpiler_name: str | None = None
    transpiler_options: dict[str, Any] = Field(default_factory=dict)
    software_versions: dict[str, str]

    @model_validator(mode="after")
    def _transformation_fields_are_aligned(self) -> CircuitProvenance:
        transformed_fields = (
            self.source_circuit_hash,
            self.source_artifact_id,
            self.target_hash,
            self.compiler_target_hash,
            self.target_name,
            self.transpiler_name,
        )
        if self.transformation == "source":
            if any(value is not None for value in transformed_fields):
                raise ValueError(
                    "source provenance cannot claim a target or transformation parent"
                )
            if self.transpiler_options:
                raise ValueError("source provenance cannot contain transpiler options")
        elif any(value is None for value in transformed_fields):
            raise ValueError(
                "transpile provenance requires source, target, and transpiler identity"
            )
        return self


class CircuitArtifact(VersionedContractModel):
    """Exact serialized circuit plus structural and writer provenance."""

    artifact: ArtifactRef
    format: Literal["qpy", "qasm3"]
    circuit_hash: Sha256Id = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    num_qubits: NonNegativeInt
    num_clbits: NonNegativeInt
    size: NonNegativeInt
    depth: NonNegativeInt | None
    parameter_names: list[str]
    registers: list[CircuitRegister]
    metadata: dict[str, Any]
    qiskit_version: str | None = Field(min_length=1)
    reader_qiskit_version: str = Field(min_length=1)
    qpy_version: NonNegativeInt | None
    qpy_symbolic_encoding: str | None = Field(min_length=1, max_length=1)
    layout: dict[str, Any] | None
    provenance: CircuitProvenance

    @model_validator(mode="after")
    def _format_version_contract(self) -> CircuitArtifact:
        if self.format == "qpy" and self.qpy_version is None:
            raise ValueError("qpy artifacts require qpy_version")
        if self.format == "qpy" and self.qiskit_version is None:
            raise ValueError("qpy artifacts require Qiskit writer version metadata")
        if (
            self.format == "qpy"
            and self.qpy_version is not None
            and self.qpy_version >= 10
            and self.qpy_symbolic_encoding is None
        ):
            raise ValueError(
                "QPY version 10 or newer requires symbolic encoding metadata"
            )
        if self.format == "qasm3" and self.qpy_version is not None:
            raise ValueError("qasm3 artifacts cannot declare qpy_version")
        if self.format == "qasm3" and self.qpy_symbolic_encoding is not None:
            raise ValueError("qasm3 artifacts cannot declare QPY symbolic encoding")
        if self.circuit_hash != self.artifact.artifact_id:
            raise ValueError("circuit_hash must identify the exact artifact bytes")
        expected_media_type = (
            "application/qpy" if self.format == "qpy" else "text/qasm3"
        )
        if self.artifact.kind != "circuit":
            raise ValueError("circuit artifacts require artifact kind 'circuit'")
        if self.artifact.media_type != expected_media_type:
            raise ValueError(
                f"{self.format} circuit artifacts require media type {expected_media_type}"
            )
        if any(
            bit_index >= self.num_qubits
            for register in self.registers
            if register.kind == "quantum"
            for bit_index in register.bit_indices
        ):
            raise ValueError("quantum register bits must belong to the circuit")
        if any(
            bit_index >= self.num_clbits
            for register in self.registers
            if register.kind == "classical"
            for bit_index in register.bit_indices
        ):
            raise ValueError("classical register bits must belong to the circuit")
        return self


class CalibrationDatum(ContractModel):
    """One timestamped backend calibration value in its source unit."""

    name: str = Field(min_length=1)
    value: JsonValue
    unit: str | None = None
    timestamp: AwareDatetime | None = None


class QubitSnapshot(ContractModel):
    """Complete properties record for one physical backend qubit."""

    index: NonNegativeInt
    operational: bool | None
    parameters: list[CalibrationDatum]


class InstructionSnapshot(ContractModel):
    """One exact instruction/qargs entry from a Qiskit target."""

    name: str = Field(min_length=1)
    qubits: list[NonNegativeInt] | None
    error: NonNegativeFloat | None
    duration: NonNegativeFloat | None
    operational: bool | None
    operation_parameters: list[JsonValue]
    calibration_parameters: list[CalibrationDatum]


class FaultyInstruction(ContractModel):
    """One instruction/qargs tuple reported faulty by backend properties."""

    name: str = Field(min_length=1)
    qubits: list[NonNegativeInt]


class BackendStatusSnapshot(ContractModel):
    """Backend-wide status observed when the snapshot was retrieved."""

    operational: bool | None
    pending_jobs: NonNegativeInt | None
    status_message: str | None


class ProcessorMetadata(ContractModel):
    """Stable processor identity with the provider's source metadata preserved."""

    family: str | None = None
    revision: str | None = None
    segment: str | None = None
    raw: JsonValue | None = None


class TargetMetadata(ContractModel):
    """Backend-wide Qiskit Target structure not repeated per instruction tuple."""

    num_qubits: NonNegativeInt
    physical_qubits: list[NonNegativeInt]
    operation_names: list[str]
    global_operations: list[str]
    dt: NonNegativeFloat | None
    granularity: PositiveInt
    min_length: PositiveInt
    pulse_alignment: PositiveInt
    acquire_alignment: PositiveInt
    concurrent_measurements: list[list[NonNegativeInt]] | None


class BackendSnapshot(VersionedContractModel):
    """Complete reproducible backend target and calibration snapshot."""

    backend_name: str = Field(min_length=1)
    instance_id: str = Field(min_length=1)
    retrieved_at: AwareDatetime
    properties_at: AwareDatetime | None
    properties_last_update: AwareDatetime | None
    properties_available: bool
    fractional_gate_mode: Literal["disabled", "enabled", "all"]
    backend_version: str | None
    processor: ProcessorMetadata
    backend_status: BackendStatusSnapshot
    target: TargetMetadata
    target_hash: Sha256Id = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    snapshot_hash: Sha256Id = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    qubits: list[QubitSnapshot]
    instructions: list[InstructionSnapshot]
    coupling_edges: list[list[int]]
    faulty_qubits: list[NonNegativeInt]
    faulty_instructions: list[FaultyInstruction]
    general_parameters: list[CalibrationDatum]
    general_qlists: list[JsonValue]
    software_versions: dict[str, str]

    @field_validator("coupling_edges")
    @classmethod
    def _two_qubit_edges(cls, value: list[list[int]]) -> list[list[int]]:
        if any(len(edge) != 2 or any(qubit < 0 for qubit in edge) for edge in value):
            raise ValueError(
                "each coupling edge must contain exactly two non-negative qubits"
            )
        return value

    @model_validator(mode="after")
    def _complete_target_contract(self) -> BackendSnapshot:
        expected_indices = list(range(self.target.num_qubits))
        if [qubit.index for qubit in self.qubits] != expected_indices:
            raise ValueError(
                "qubits must contain every physical index exactly once in order"
            )
        if self.target.physical_qubits != expected_indices:
            raise ValueError(
                "target.physical_qubits must contain every physical index in order"
            )
        instruction_keys = [
            (
                instruction.name,
                None if instruction.qubits is None else tuple(instruction.qubits),
            )
            for instruction in self.instructions
        ]
        if len(instruction_keys) != len(set(instruction_keys)):
            raise ValueError("instruction name/qubit tuples must be unique")
        if any(
            qubit >= self.target.num_qubits
            for instruction in self.instructions
            for qubit in (instruction.qubits or [])
        ):
            raise ValueError("instruction qubits must belong to the target")
        if any(
            qubit >= self.target.num_qubits
            for edge in self.coupling_edges
            for qubit in edge
        ):
            raise ValueError("coupling edge qubits must belong to the target")
        if any(qubit >= self.target.num_qubits for qubit in self.faulty_qubits):
            raise ValueError("faulty qubits must belong to the target")
        return self


class PauliObservables(VersionedContractModel):
    """A broadcast collection of separate Pauli observables."""

    kind: Literal["pauli_observables"]
    values: list[str] = Field(min_length=1)


class SparsePauliHamiltonian(VersionedContractModel):
    """One weighted Hamiltonian, kept distinct from separate observables."""

    kind: Literal["sparse_pauli_hamiltonian"]
    terms: list[tuple[str, float]] = Field(min_length=1)


ObservableSpec = PauliObservables | SparsePauliHamiltonian


class SamplerPubSpec(VersionedContractModel):
    """Validated SamplerV2 PUB input."""

    pub_id: str = Field(min_length=1)
    circuit: CircuitArtifact
    parameter_values: list[list[float]] | None
    shots: PositiveInt


class EstimatorPubSpec(VersionedContractModel):
    """Validated EstimatorV2 PUB input with explicit observable semantics."""

    pub_id: str = Field(min_length=1)
    circuit: CircuitArtifact
    observables: ObservableSpec = Field(discriminator="kind")
    parameter_values: list[list[float]] | None
    precision: PositiveFloat | None


class SubmissionPartition(VersionedContractModel):
    """Deterministic grouping of PUB identities for one Runtime job."""

    partition_id: str = Field(min_length=1)
    pub_ids: list[str] = Field(min_length=1)
    estimated_qpu_seconds: NonNegativeFloat | None = None
    maximum_execution_seconds: PositiveFloat | None = None


class SubmissionPlan(VersionedContractModel):
    """Immutable-by-hash resolved dry-run submission plan."""

    plan_id: str = Field(min_length=1)
    plan_hash: Sha256Id = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    instance_id: str = Field(min_length=1)
    backend_name: str = Field(min_length=1)
    primitive: Literal["sampler", "estimator"]
    pubs: list[SamplerPubSpec | EstimatorPubSpec] = Field(min_length=1)
    resolved_options: dict[str, Any]
    partitions: list[SubmissionPartition] = Field(min_length=1)
    estimated_qpu_seconds: NonNegativeFloat
    maximum_execution_seconds: PositiveFloat

    @model_validator(mode="after")
    def _pub_types_match_primitive(self) -> SubmissionPlan:
        expected_type = (
            SamplerPubSpec if self.primitive == "sampler" else EstimatorPubSpec
        )
        if any(not isinstance(pub, expected_type) for pub in self.pubs):
            raise ValueError(
                f"{self.primitive} plans may only contain matching PUB specs"
            )
        pub_ids = [pub.pub_id for pub in self.pubs]
        if len(pub_ids) != len(set(pub_ids)):
            raise ValueError("pub_id values must be unique within a plan")
        partitioned_ids = [
            pub_id for partition in self.partitions for pub_id in partition.pub_ids
        ]
        if sorted(partitioned_ids) != sorted(pub_ids):
            raise ValueError("partitions must contain every plan PUB exactly once")
        return self


class ApprovalReceipt(VersionedContractModel):
    """Approval bound to an exact plan hash and explicit resource allowlists."""

    plan_hash: Sha256Id = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    approved_at: AwareDatetime
    expires_at: AwareDatetime
    max_qpu_seconds: PositiveFloat
    allowed_instance_ids: list[str] = Field(min_length=1)
    allowed_backends: list[str] = Field(min_length=1)
    allow_paid_fallback: bool = False

    @model_validator(mode="after")
    def _expiry_follows_approval(self) -> ApprovalReceipt:
        if self.expires_at <= self.approved_at:
            raise ValueError("expires_at must be later than approved_at")
        return self


class RuntimeUsage(VersionedContractModel):
    """Typed usage returned to callers for their own reconciliation."""

    quantum_seconds: NonNegativeFloat | None
    job_id: str | None = None
    usage_type: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)


class SamplerRegisterResult(VersionedContractModel):
    """One named classical register returned in a Sampler DataBin."""

    register_name: str = Field(min_length=1)
    pub_shape: list[NonNegativeInt]
    num_shots: PositiveInt
    num_bits: PositiveInt
    counts_by_location: list[dict[str, NonNegativeInt]] | ArtifactRef | None = None
    bitstrings_by_location: list[list[str]] | ArtifactRef | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _location_payloads_match_shape(self) -> SamplerRegisterResult:
        location_count = 1
        for extent in self.pub_shape:
            location_count *= extent
        for name, payload in (
            ("counts_by_location", self.counts_by_location),
            ("bitstrings_by_location", self.bitstrings_by_location),
        ):
            if isinstance(payload, list) and len(payload) != location_count:
                raise ValueError(
                    f"{name} must contain one row-major entry per PUB location"
                )
        if isinstance(self.bitstrings_by_location, list) and any(
            len(shots) != self.num_shots for shots in self.bitstrings_by_location
        ):
            raise ValueError(
                "each bitstring location must contain exactly num_shots entries"
            )
        return self


class SamplerPubResult(VersionedContractModel):
    """Ordered result for one Sampler PUB."""

    pub_id: str = Field(min_length=1)
    pub_index: NonNegativeInt
    registers: list[SamplerRegisterResult]
    metadata: dict[str, Any] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)


class InlineJsonValue(VersionedContractModel):
    """Explicit inline branch for values that may instead be artifact-backed."""

    kind: Literal["inline_json"]
    value: JsonValue

    @field_validator("value", mode="before")
    @classmethod
    def _json_safe_value(cls, value: Any) -> JsonValue:
        return to_json_safe(value)


ArtifactValue = InlineJsonValue | ArtifactRef


class EstimatorPubResult(VersionedContractModel):
    """Ordered result for one Estimator PUB without collapsing array shape."""

    pub_id: str = Field(min_length=1)
    pub_index: NonNegativeInt
    expectation_values: ArtifactValue
    standard_deviations: ArtifactValue
    ensemble_standard_error: ArtifactValue | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    extensions: dict[str, Any] = Field(default_factory=dict)


class PrimitiveResultEnvelope(VersionedContractModel):
    """Complete ordered Primitive V2 job result and unknown extension data."""

    primitive: Literal["sampler", "estimator"]
    job_id: str = Field(min_length=1)
    backend_name: str = Field(min_length=1)
    pub_results: list[SamplerPubResult | EstimatorPubResult]
    job_metadata: dict[str, Any]
    actual_qpu_seconds: NonNegativeFloat | None
    usage: RuntimeUsage | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _result_types_and_order_match(self) -> PrimitiveResultEnvelope:
        expected_type = (
            SamplerPubResult if self.primitive == "sampler" else EstimatorPubResult
        )
        if any(not isinstance(result, expected_type) for result in self.pub_results):
            raise ValueError(
                f"{self.primitive} envelopes may only contain matching PUB results"
            )
        indices = [result.pub_index for result in self.pub_results]
        if indices != list(range(len(indices))):
            raise ValueError(
                "pub_results must have contiguous zero-based pub_index values"
            )
        return self


PUBLIC_MODELS: tuple[type[BaseModel], ...] = (
    ArtifactRef,
    CircuitArtifact,
    BackendSnapshot,
    PauliObservables,
    SparsePauliHamiltonian,
    SamplerPubSpec,
    EstimatorPubSpec,
    SubmissionPartition,
    SubmissionPlan,
    ApprovalReceipt,
    RuntimeUsage,
    SamplerRegisterResult,
    SamplerPubResult,
    InlineJsonValue,
    EstimatorPubResult,
    PrimitiveResultEnvelope,
)
