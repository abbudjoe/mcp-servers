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
from .models import (
    ApprovalReceipt,
    ArtifactRef,
    BackendSnapshot,
    CircuitArtifact,
    EstimatorPubResult,
    EstimatorPubSpec,
    InlineJsonValue,
    PauliObservables,
    PrimitiveResultEnvelope,
    RuntimeUsage,
    SamplerPubResult,
    SamplerPubSpec,
    SparsePauliHamiltonian,
    SubmissionPartition,
    SubmissionPlan,
)
from .serialization import canonical_json, canonical_json_hash, to_json_safe


__all__ = [
    "ApprovalReceipt",
    "ArtifactRef",
    "ArtifactSink",
    "BackendSnapshot",
    "CircuitArtifact",
    "EstimatorPubResult",
    "EstimatorPubSpec",
    "InlineJsonValue",
    "LocalArtifactCAS",
    "PauliObservables",
    "PrimitiveResultEnvelope",
    "RuntimeUsage",
    "SamplerPubResult",
    "SamplerPubSpec",
    "SparsePauliHamiltonian",
    "SubmissionPartition",
    "SubmissionPlan",
    "artifactize",
    "canonical_json",
    "canonical_json_hash",
    "to_json_safe",
]
