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

"""Typed, MCP-independent contracts for the Runtime research core."""

from .artifacts import ArtifactSink, LocalArtifactCAS, artifactize
from .circuits import (
    CircuitBoundaryResult,
    CircuitContractError,
    CircuitFormatError,
    CircuitIsaError,
    CircuitLimitError,
    CircuitLimits,
    CircuitValidationReport,
    CircuitWidthError,
    IngestedCircuit,
    IsaValidationIssue,
    ResolvedTarget,
    TargetIdentityError,
    apply_circuit_mode,
    ingest_circuit,
    target_fingerprint,
    validate_circuit_isa,
)
from .models import (
    ApprovalReceipt,
    ArtifactRef,
    BackendSnapshot,
    BackendStatusSnapshot,
    CalibrationDatum,
    CircuitArtifact,
    CircuitProvenance,
    CircuitRegister,
    EstimatorPubResult,
    EstimatorPubSpec,
    FaultyInstruction,
    InlineJsonValue,
    InstructionSnapshot,
    PauliObservables,
    PrimitiveResultEnvelope,
    ProcessorMetadata,
    QubitSnapshot,
    RuntimeUsage,
    SamplerPubResult,
    SamplerPubSpec,
    SparsePauliHamiltonian,
    SubmissionPartition,
    SubmissionPlan,
    TargetMetadata,
)
from .serialization import canonical_json, canonical_json_hash, to_json_safe
from .snapshots import (
    FractionalGateMode,
    SnapshotContractError,
    build_backend_snapshot,
    resolve_backend_snapshot,
    snapshot_content_hash,
    target_content_hash,
    validate_snapshot_request,
)


__all__ = [
    "ApprovalReceipt",
    "ArtifactRef",
    "ArtifactSink",
    "BackendSnapshot",
    "BackendStatusSnapshot",
    "CalibrationDatum",
    "CircuitArtifact",
    "CircuitBoundaryResult",
    "CircuitContractError",
    "CircuitFormatError",
    "CircuitIsaError",
    "CircuitLimitError",
    "CircuitLimits",
    "CircuitProvenance",
    "CircuitRegister",
    "CircuitValidationReport",
    "CircuitWidthError",
    "EstimatorPubResult",
    "EstimatorPubSpec",
    "FaultyInstruction",
    "InlineJsonValue",
    "InstructionSnapshot",
    "IngestedCircuit",
    "IsaValidationIssue",
    "LocalArtifactCAS",
    "PauliObservables",
    "PrimitiveResultEnvelope",
    "ProcessorMetadata",
    "QubitSnapshot",
    "ResolvedTarget",
    "RuntimeUsage",
    "SamplerPubResult",
    "SamplerPubSpec",
    "SparsePauliHamiltonian",
    "SubmissionPartition",
    "SubmissionPlan",
    "TargetMetadata",
    "TargetIdentityError",
    "FractionalGateMode",
    "SnapshotContractError",
    "artifactize",
    "apply_circuit_mode",
    "build_backend_snapshot",
    "canonical_json",
    "canonical_json_hash",
    "ingest_circuit",
    "resolve_backend_snapshot",
    "snapshot_content_hash",
    "target_fingerprint",
    "target_content_hash",
    "to_json_safe",
    "validate_circuit_isa",
    "validate_snapshot_request",
]
