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

"""Locked Primitive V2 PUB coercion, submission, and complete result parsing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol, Sequence

import numpy as np
from qiskit.primitives.containers import BitArray, EstimatorPub, SamplerPub
from qiskit.quantum_info import SparsePauliOp

from .artifacts import ArtifactSink, artifactize
from .circuits import load_circuit_artifact
from .models import (
    ArtifactValue,
    EstimatorPubResult,
    EstimatorPubSpec,
    InlineJsonValue,
    PauliObservables,
    PrimitiveResultEnvelope,
    RuntimeUsage,
    SamplerPubResult,
    SamplerPubSpec,
    SamplerRegisterResult,
    ShapedResultValue,
)
from .serialization import to_json_safe


PrimitiveKind = Literal["sampler", "estimator"]


class PrimitiveContractError(ValueError):
    """Raised when a PUB or result violates the locked Primitive V2 contract."""


class PrimitiveRunner(Protocol):
    """The locked common subset of SamplerV2 and EstimatorV2 used for submission."""

    def run(self, pubs: Sequence[Any]) -> Any:
        """Submit already-coerced PUBs and return a Runtime job."""
        ...


@dataclass(frozen=True)
class SubmittedPrimitiveJob:
    """In-process job handle paired with caller-owned PUB identity and shape."""

    primitive: PrimitiveKind
    pub_ids: tuple[str, ...]
    pub_shapes: tuple[tuple[int, ...], ...]
    job: Any


def _require_unique_pubs(pubs: Sequence[SamplerPubSpec | EstimatorPubSpec]) -> None:
    if not pubs:
        raise PrimitiveContractError("at least one PUB is required")
    pub_ids = [pub.pub_id for pub in pubs]
    if len(pub_ids) != len(set(pub_ids)):
        raise PrimitiveContractError("pub_id values must be unique within one job")


def _parameter_values(pub: SamplerPubSpec | EstimatorPubSpec) -> Any | None:
    if pub.parameter_values is None:
        return None
    return pub.parameter_values.values


def prepare_sampler_pubs(
    pubs: Sequence[SamplerPubSpec], *, sink: ArtifactSink
) -> list[SamplerPub]:
    """Validate and coerce ordered Sampler PUBs against exact artifact circuits."""
    _require_unique_pubs(pubs)
    prepared: list[SamplerPub] = []
    for pub in pubs:
        circuit = load_circuit_artifact(pub.circuit, sink=sink).circuit
        actual_names = [parameter.name for parameter in circuit.parameters]
        if actual_names != pub.circuit.parameter_names:
            raise PrimitiveContractError(
                f"PUB {pub.pub_id!r} circuit parameter order changed after reconstruction"
            )
        values = _parameter_values(pub)
        pub_like: Any = circuit if values is None else (circuit, values)
        try:
            coerced = SamplerPub.coerce(pub_like, shots=pub.shots)
        except Exception as exc:
            raise PrimitiveContractError(
                f"Sampler PUB {pub.pub_id!r} failed locked-version coercion: {exc}"
            ) from exc
        expected_shape = tuple(
            pub.parameter_values.shape if pub.parameter_values is not None else []
        )
        if coerced.shape != expected_shape:
            raise PrimitiveContractError(
                f"Sampler PUB {pub.pub_id!r} shape mismatch: "
                f"declared {expected_shape}, coerced {coerced.shape}"
            )
        prepared.append(coerced)
    return prepared


def _observable_value(pub: EstimatorPubSpec) -> tuple[Any, tuple[int, ...]]:
    if isinstance(pub.observables, PauliObservables):
        return pub.observables.values, tuple(pub.observables.shape)
    try:
        return SparsePauliOp.from_list(pub.observables.terms), ()
    except Exception as exc:
        raise PrimitiveContractError(
            f"Estimator PUB {pub.pub_id!r} has an invalid weighted Hamiltonian: {exc}"
        ) from exc


def prepare_estimator_pubs(
    pubs: Sequence[EstimatorPubSpec], *, sink: ArtifactSink
) -> list[EstimatorPub]:
    """Validate observable/parameter broadcasting and coerce ordered Estimator PUBs."""
    _require_unique_pubs(pubs)
    prepared: list[EstimatorPub] = []
    for pub in pubs:
        circuit = load_circuit_artifact(pub.circuit, sink=sink).circuit
        actual_names = [parameter.name for parameter in circuit.parameters]
        if actual_names != pub.circuit.parameter_names:
            raise PrimitiveContractError(
                f"PUB {pub.pub_id!r} circuit parameter order changed after reconstruction"
            )
        observables, observable_shape = _observable_value(pub)
        parameter_shape = tuple(
            pub.parameter_values.shape if pub.parameter_values is not None else []
        )
        try:
            expected_shape = np.broadcast_shapes(observable_shape, parameter_shape)
        except ValueError as exc:
            raise PrimitiveContractError(
                f"Estimator PUB {pub.pub_id!r} observable shape {observable_shape} "
                f"and parameter shape {parameter_shape} do not broadcast"
            ) from exc
        values = _parameter_values(pub)
        pub_like: Any = (
            (circuit, observables) if values is None else (circuit, observables, values)
        )
        try:
            coerced = EstimatorPub.coerce(pub_like, precision=pub.precision)
        except Exception as exc:
            raise PrimitiveContractError(
                f"Estimator PUB {pub.pub_id!r} failed locked-version coercion: {exc}"
            ) from exc
        if coerced.shape != expected_shape:
            raise PrimitiveContractError(
                f"Estimator PUB {pub.pub_id!r} shape mismatch: "
                f"declared broadcast {expected_shape}, coerced {coerced.shape}"
            )
        prepared.append(coerced)
    return prepared


def _submit_sampler_pubs_unchecked(
    sampler: PrimitiveRunner,
    pubs: Sequence[SamplerPubSpec],
    *,
    sink: ArtifactSink,
) -> SubmittedPrimitiveJob:
    """Submit every ordered Sampler PUB in one locked-version job call."""
    prepared = prepare_sampler_pubs(pubs, sink=sink)
    job = sampler.run(prepared)
    return SubmittedPrimitiveJob(
        primitive="sampler",
        pub_ids=tuple(pub.pub_id for pub in pubs),
        pub_shapes=tuple(pub.shape for pub in prepared),
        job=job,
    )


def _submit_estimator_pubs_unchecked(
    estimator: PrimitiveRunner,
    pubs: Sequence[EstimatorPubSpec],
    *,
    sink: ArtifactSink,
) -> SubmittedPrimitiveJob:
    """Submit every ordered Estimator PUB in one locked-version job call."""
    prepared = prepare_estimator_pubs(pubs, sink=sink)
    job = estimator.run(prepared)
    return SubmittedPrimitiveJob(
        primitive="estimator",
        pub_ids=tuple(pub.pub_id for pub in pubs),
        pub_shapes=tuple(pub.shape for pub in prepared),
        job=job,
    )


def _artifact_value(
    value: Any,
    *,
    sink: ArtifactSink,
    threshold_bytes: int,
    kind: str,
) -> ArtifactValue:
    array = np.asarray(value) if isinstance(value, (np.ndarray, np.generic)) else None
    metadata: dict[str, Any] = {}
    if array is not None:
        metadata = {"shape": list(array.shape), "dtype": str(array.dtype)}
    return artifactize(
        value,
        sink,
        threshold_bytes=threshold_bytes,
        kind=kind,
        media_type="application/json",
        metadata=metadata,
    )


def _shaped_result(
    value: Any,
    *,
    sink: ArtifactSink,
    threshold_bytes: int,
    kind: str,
) -> ShapedResultValue:
    array = np.asarray(value)
    if array.dtype.hasobject:
        raise PrimitiveContractError(f"{kind} must be a homogeneous scalar or array")
    return ShapedResultValue(
        schema_version="1.0",
        shape=list(array.shape),
        dtype=str(array.dtype),
        value=_artifact_value(
            array,
            sink=sink,
            threshold_bytes=threshold_bytes,
            kind=kind,
        ),
    )


def _safe_metadata(value: Any, *, name: str) -> dict[str, Any]:
    safe = to_json_safe(value or {})
    if not isinstance(safe, dict):
        raise PrimitiveContractError(f"{name} metadata must be a JSON object")
    return safe


def _parse_sampler_pub(
    pub_result: Any,
    *,
    pub_id: str,
    pub_index: int,
    expected_shape: tuple[int, ...],
    sink: ArtifactSink,
    threshold_bytes: int,
) -> SamplerPubResult:
    data = pub_result.data
    data_shape = tuple(data.shape)
    if data_shape != expected_shape:
        raise PrimitiveContractError(
            f"Sampler PUB {pub_id!r} returned shape {data_shape}; "
            f"expected {expected_shape}"
        )
    registers: list[SamplerRegisterResult] = []
    extensions: dict[str, ArtifactValue] = {}
    for key, value in data.items():
        if not isinstance(value, BitArray):
            extensions[key] = _artifact_value(
                value,
                sink=sink,
                threshold_bytes=threshold_bytes,
                kind=f"sampler-databin-extension:{key}",
            )
            continue
        if value.shape != data_shape:
            raise PrimitiveContractError(
                f"Sampler register {key!r} shape {value.shape} does not match "
                f"DataBin shape {data_shape}"
            )
        locations = list(np.ndindex(value.shape))
        counts = [value.get_counts(location) for location in locations]
        bitstrings = [value.get_bitstrings(location) for location in locations]
        quasi = [
            {bitstring: count / value.num_shots for bitstring, count in row.items()}
            for row in counts
        ]
        registers.append(
            SamplerRegisterResult(
                schema_version="1.0",
                register_name=key,
                pub_shape=list(value.shape),
                num_shots=value.num_shots,
                num_bits=value.num_bits,
                packed_shape=list(value.array.shape),
                packed_bytes=_artifact_value(
                    value.array,
                    sink=sink,
                    threshold_bytes=threshold_bytes,
                    kind=f"sampler-packed-register:{key}",
                ),
                counts_by_location=_artifact_value(
                    counts,
                    sink=sink,
                    threshold_bytes=threshold_bytes,
                    kind=f"sampler-counts:{key}",
                ),
                bitstrings_by_location=_artifact_value(
                    bitstrings,
                    sink=sink,
                    threshold_bytes=threshold_bytes,
                    kind=f"sampler-bitstrings:{key}",
                ),
                quasi_distributions_by_location=_artifact_value(
                    quasi,
                    sink=sink,
                    threshold_bytes=threshold_bytes,
                    kind=f"sampler-quasi:{key}",
                ),
            )
        )
    return SamplerPubResult(
        schema_version="1.0",
        pub_id=pub_id,
        pub_index=pub_index,
        data_bin_shape=list(data_shape),
        registers=registers,
        metadata=_safe_metadata(pub_result.metadata, name=f"PUB {pub_id}"),
        extensions=extensions,
    )


def _parse_estimator_pub(
    pub_result: Any,
    *,
    pub_id: str,
    pub_index: int,
    expected_shape: tuple[int, ...],
    sink: ArtifactSink,
    threshold_bytes: int,
) -> EstimatorPubResult:
    data = pub_result.data
    data_shape = tuple(data.shape)
    if data_shape != expected_shape:
        raise PrimitiveContractError(
            f"Estimator PUB {pub_id!r} returned shape {data_shape}; "
            f"expected {expected_shape}"
        )
    fields = dict(data.items())
    if "evs" not in fields:
        raise PrimitiveContractError(
            f"Estimator PUB {pub_id!r} is missing required DataBin key: evs"
        )
    evs = _shaped_result(
        fields.pop("evs"),
        sink=sink,
        threshold_bytes=threshold_bytes,
        kind="estimator-expectation-values",
    )
    stds_value = fields.pop("stds", None)
    stds = (
        None
        if stds_value is None
        else _shaped_result(
            stds_value,
            sink=sink,
            threshold_bytes=threshold_bytes,
            kind="estimator-standard-deviations",
        )
    )
    ensemble_value = fields.pop("ensemble_standard_error", None)
    ensemble = (
        None
        if ensemble_value is None
        else _shaped_result(
            ensemble_value,
            sink=sink,
            threshold_bytes=threshold_bytes,
            kind="estimator-ensemble-standard-error",
        )
    )
    if stds is None and ensemble is None:
        raise PrimitiveContractError(
            f"Estimator PUB {pub_id!r} has neither stds nor ensemble_standard_error"
        )
    shaped_errors = [value for value in (stds, ensemble) if value is not None]
    if tuple(evs.shape) != data_shape or any(
        tuple(value.shape) != data_shape for value in shaped_errors
    ):
        raise PrimitiveContractError(
            f"Estimator PUB {pub_id!r} value/error shapes must match DataBin shape"
        )
    extensions = {
        key: _artifact_value(
            value,
            sink=sink,
            threshold_bytes=threshold_bytes,
            kind=f"estimator-databin-extension:{key}",
        )
        for key, value in fields.items()
    }
    return EstimatorPubResult(
        schema_version="1.0",
        pub_id=pub_id,
        pub_index=pub_index,
        data_bin_shape=list(data_shape),
        expectation_values=evs,
        standard_deviations=stds,
        ensemble_standard_error=ensemble,
        metadata=_safe_metadata(pub_result.metadata, name=f"PUB {pub_id}"),
        extensions=extensions,
    )


def parse_primitive_result(
    result: Any,
    *,
    primitive: PrimitiveKind,
    pub_ids: Sequence[str],
    expected_pub_shapes: Sequence[Sequence[int]],
    job_id: str,
    backend_name: str,
    sink: ArtifactSink,
    threshold_bytes: int,
    actual_qpu_seconds: float | None = None,
    usage: RuntimeUsage | None = None,
) -> PrimitiveResultEnvelope:
    """Parse every ordered PUB and every DataBin key into a versioned envelope."""
    if primitive not in ("sampler", "estimator"):
        raise PrimitiveContractError(f"unsupported primitive kind: {primitive!r}")
    if threshold_bytes < 0:
        raise PrimitiveContractError("threshold_bytes must be non-negative")
    pub_results = list(result)
    if len(pub_ids) != len(expected_pub_shapes):
        raise PrimitiveContractError("PUB identities and expected shapes must align")
    if len(pub_results) != len(pub_ids):
        raise PrimitiveContractError(
            f"result returned {len(pub_results)} PUBs for {len(pub_ids)} submitted PUBs"
        )
    if len(pub_ids) != len(set(pub_ids)):
        raise PrimitiveContractError("pub_id values must be unique")

    parsed: list[SamplerPubResult | EstimatorPubResult] = []
    for index, (pub_result, pub_id, expected_shape) in enumerate(
        zip(pub_results, pub_ids, expected_pub_shapes, strict=True)
    ):
        common = {
            "pub_result": pub_result,
            "pub_id": pub_id,
            "pub_index": index,
            "expected_shape": tuple(expected_shape),
            "sink": sink,
            "threshold_bytes": threshold_bytes,
        }
        parsed.append(
            _parse_sampler_pub(**common)
            if primitive == "sampler"
            else _parse_estimator_pub(**common)
        )

    return PrimitiveResultEnvelope(
        schema_version="1.0",
        primitive=primitive,
        job_id=job_id,
        backend_name=backend_name,
        pub_results=parsed,
        job_metadata=_safe_metadata(result.metadata, name="job result"),
        actual_qpu_seconds=actual_qpu_seconds,
        usage=usage,
    )


def inline_value(value: ArtifactValue) -> Any:
    """Return inline JSON for migration adapters and reject artifact flattening."""
    if not isinstance(value, InlineJsonValue):
        raise PrimitiveContractError(
            "legacy flattened output is unavailable because this value is artifact-backed"
        )
    return value.value
