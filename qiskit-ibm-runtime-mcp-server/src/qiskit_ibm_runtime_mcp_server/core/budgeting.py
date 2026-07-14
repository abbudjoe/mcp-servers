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

"""Locked preflight estimation and plan-bound QPU approval enforcement."""

from __future__ import annotations

import copy
import dataclasses
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version as package_version
from typing import Any, Callable, Literal, Protocol, cast

import numpy as np
from qiskit import QuantumCircuit
from qiskit.transpiler import PassManager
from qiskit.transpiler.passes import ALAPScheduleAnalysis
from qiskit_ibm_runtime import EstimatorOptions, SamplerOptions
from qiskit_ibm_runtime.options.utils import UnsetType

from .approvals import (
    ApprovalConsumptionError,
    ApprovalConsumptionLedger,
    LocalApprovalConsumptionLedger,
)
from .artifacts import ArtifactSink, LocalArtifactCAS
from .batches import (
    BatchLifecycle,
    BatchLimitError as BatchPartitionLimitError,
    plan_batch_partitions,
)
from .circuits import ResolvedTarget, apply_circuit_mode, load_circuit_artifact
from .models import (
    ApprovalReceipt,
    ApprovedSubmission,
    BatchExecutionLimits,
    BudgetPolicy,
    EstimatorPubSpec,
    PauliObservables,
    PubExecutionEstimate,
    PubShape,
    SamplerPubSpec,
    ScheduledPubEstimate,
    SubmissionPlan,
    UsageReconciliation,
)
from .serialization import canonical_json_hash, to_json_safe
from .snapshots import build_backend_snapshot


ESTIMATION_METHOD = "qiskit-alap-critical-path"
ESTIMATION_VERSION = "1.0"
CONSERVATIVE_MINIMUM_CYCLE_SECONDS = 0.001
RUNTIME_UNSET_SENTINEL: dict[str, str] = {"$runtime_default": "Unset"}

Treatment = Literal[
    "dynamical_decoupling",
    "gate_twirling",
    "measure_twirling",
    "measure_mitigation",
    "zne_mitigation",
    "pec_mitigation",
    "resilience_level_1",
    "resilience_level_2",
]


class BudgetContractError(ValueError):
    """Raised when a request cannot produce one deterministic execution plan."""


class BudgetLimitError(BudgetContractError):
    """Raised before submission when a policy or receipt limit is exceeded."""


class ApprovalError(BudgetContractError):
    """Raised before submission when approval is absent, stale, or mismatched."""


@dataclass(frozen=True)
class ResolvedRuntimeTarget:
    """One resolver-owned Runtime instance, plan class, backend, and target."""

    instance_id: str
    instance_plan_type: Literal["open", "paid"]
    target: ResolvedTarget


class RuntimeResourceResolver(Protocol):
    """Re-resolve the paid-resource boundary from authoritative Runtime state."""

    def resolve(self, instance_id: str, backend_name: str) -> ResolvedRuntimeTarget:
        """Return the exact current target and provider plan type."""
        ...


class RuntimeAuthorityService(Protocol):
    """Authoritative read/submit service shared by planning and Batch execution."""

    def instances(self) -> Sequence[dict[str, Any]]:
        """Return provider instance records containing ``crn`` and ``plan``."""
        ...

    def backend(self, name: str, **kwargs: Any) -> Any:
        """Resolve one backend in one explicit instance."""
        ...


class ServiceRuntimeResourceResolver:
    """Production resolver backed by the same Runtime service used to submit."""

    def __init__(
        self,
        service: RuntimeAuthorityService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._service = service
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def resolve(self, instance_id: str, backend_name: str) -> ResolvedRuntimeTarget:
        records = [
            record
            for record in self._service.instances()
            if record.get("crn") == instance_id
        ]
        if len(records) != 1:
            raise BudgetContractError(
                "Runtime instance must resolve to exactly one provider record"
            )
        raw_plan = records[0].get("plan")
        if not isinstance(raw_plan, str) or not raw_plan.strip():
            raise BudgetContractError("Runtime instance record has no plan type")
        plan_type: Literal["open", "paid"] = (
            "open" if raw_plan.strip().lower() == "open" else "paid"
        )
        backend = self._service.backend(
            backend_name,
            instance=instance_id,
            use_fractional_gates=False,
        )
        properties_method = getattr(backend, "properties", None)
        if not callable(properties_method):
            raise BudgetContractError("resolved Runtime backend has no properties API")
        properties = properties_method()
        snapshot = build_backend_snapshot(
            backend,
            instance_id=instance_id,
            properties=properties,
            retrieved_at=self._clock(),
            fractional_gate_mode="disabled",
        )
        return ResolvedRuntimeTarget(
            instance_id=instance_id,
            instance_plan_type=plan_type,
            target=ResolvedTarget(backend, snapshot),
        )


@dataclass(frozen=True)
class SubmissionRequest:
    """Caller intent that must be resolved again immediately before submission."""

    plan_id: str
    submission_key: str
    instance_id: str
    backend_name: str
    primitive: Literal["sampler", "estimator"]
    pubs: tuple[SamplerPubSpec | EstimatorPubSpec, ...]
    options: Mapping[str, Any]
    maximum_execution_seconds: int


def _software_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
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


def _canonical_runtime_value(value: Any) -> Any:
    if isinstance(value, UnsetType):
        return dict(RUNTIME_UNSET_SENTINEL)
    if isinstance(value, Mapping):
        return {str(key): _canonical_runtime_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_runtime_value(item) for item in value]
    return to_json_safe(value)


def _configured(value: Any) -> bool:
    return bool(value != RUNTIME_UNSET_SENTINEL)


def _resolve_options(
    primitive: Literal["sampler", "estimator"],
    requested: Mapping[str, Any],
    maximum_execution_seconds: int,
    default_rep_delay: float,
) -> dict[str, Any]:
    raw = copy.deepcopy(dict(requested))
    requested_limit = raw.get("max_execution_time")
    if requested_limit is not None and requested_limit != maximum_execution_seconds:
        raise BudgetContractError(
            "options.max_execution_time must match maximum_execution_seconds"
        )
    raw["max_execution_time"] = maximum_execution_seconds
    if raw.get("experimental") not in (None, {}):
        raise BudgetContractError(
            "experimental Runtime options are not supported by the locked estimator"
        )
    if raw.get("simulator") not in (None, {}):
        raise BudgetContractError("simulator options are not valid for a QPU plan")

    if primitive == "sampler":
        options: SamplerOptions | EstimatorOptions = SamplerOptions()
        baseline: dict[str, Any] = {
            "dynamical_decoupling": {"enable": False},
            "execution": {
                "init_qubits": True,
                "rep_delay": default_rep_delay,
                "meas_type": "classified",
            },
            "twirling": {"enable_gates": False, "enable_measure": False},
        }
    else:
        options = EstimatorOptions()
        baseline = {
            "resilience_level": 0,
            "dynamical_decoupling": {"enable": False},
            "execution": {"init_qubits": True, "rep_delay": default_rep_delay},
            "twirling": {"enable_gates": False, "enable_measure": False},
            "resilience": {
                "measure_mitigation": False,
                "zne_mitigation": False,
                "pec_mitigation": False,
            },
        }
    try:
        options.update(**baseline)
        options.update(**raw)
    except (TypeError, ValueError) as exc:
        raise BudgetContractError(f"invalid locked Runtime options: {exc}") from exc
    resolved = _canonical_runtime_value(dataclasses.asdict(options))
    if not isinstance(resolved, dict):  # pragma: no cover - dataclass invariant
        raise BudgetContractError("resolved Runtime options must be an object")
    return resolved


def _positive_int_option(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise BudgetContractError(f"{name} must be an explicit positive integer")
    return value


def _treatments_and_multiplier(
    primitive: Literal["sampler", "estimator"], options: Mapping[str, Any]
) -> tuple[list[str], float, int]:
    treatments: list[str] = []
    multiplier = 1.0
    physical_variants = 1
    dd = cast(Mapping[str, Any], options["dynamical_decoupling"])
    if dd.get("enable") is True:
        raise BudgetContractError(
            "dynamical decoupling has no locked conservative estimator; disable it"
        )

    twirling = cast(Mapping[str, Any], options["twirling"])
    twirling_enabled = False
    if twirling.get("enable_gates") is True:
        treatments.append("gate_twirling")
        twirling_enabled = True
    if twirling.get("enable_measure") is True:
        treatments.append("measure_twirling")
        twirling_enabled = True
    if twirling_enabled:
        randomizations = _positive_int_option(
            twirling.get("num_randomizations"), "twirling.num_randomizations"
        )
        _positive_int_option(
            twirling.get("shots_per_randomization"),
            "twirling.shots_per_randomization",
        )
        multiplier *= randomizations
        physical_variants *= randomizations

    if primitive == "estimator":
        resilience_level = options.get("resilience_level")
        if resilience_level in (1, 2):
            raise BudgetContractError(
                "resilience levels have no locked conservative estimator; use explicit "
                "individually estimated treatments"
            )
        resilience = cast(Mapping[str, Any], options["resilience"])
        if resilience.get("measure_mitigation") is True:
            raise BudgetContractError(
                "measurement mitigation calibration has no locked conservative estimator"
            )
        if resilience.get("zne_mitigation") is True:
            treatments.append("zne_mitigation")
            zne = cast(Mapping[str, Any], resilience["zne"])
            if zne.get("amplifier") != "gate_folding":
                raise BudgetContractError(
                    "ZNE requires explicit gate_folding for bounded estimation"
                )
            noise_factors = zne.get("noise_factors")
            if (
                not isinstance(noise_factors, list)
                or not noise_factors
                or any(
                    isinstance(factor, bool)
                    or not isinstance(factor, (int, float))
                    or not math.isfinite(float(factor))
                    or factor < 1
                    for factor in noise_factors
                )
            ):
                raise BudgetContractError(
                    "zne.noise_factors must be explicit finite values at least 1"
                )
            # Local gate folding expands the scheduled gate contribution by at most
            # each factor; charging the sum to the entire cycle also overcounts
            # measurement and repetition delay, so this is a conservative bound.
            multiplier *= math.fsum(float(factor) for factor in noise_factors)
            physical_variants *= len(noise_factors)
        if resilience.get("pec_mitigation") is True:
            raise BudgetContractError(
                "PEC and its noise-learning calibration have no locked conservative estimator"
            )
    return treatments, multiplier, physical_variants


def _pub_shape(pub: SamplerPubSpec | EstimatorPubSpec) -> PubShape:
    parameter_shape = [] if pub.parameter_values is None else pub.parameter_values.shape
    if isinstance(pub, SamplerPubSpec):
        observable_shape = None
        result_shape = list(parameter_shape)
    else:
        if not isinstance(pub.observables, PauliObservables):
            raise BudgetContractError(
                "weighted Hamiltonians have no locked conservative measurement-group "
                "estimator; submit explicit Pauli observables"
            )
        observable_shape = (
            pub.observables.shape
            if isinstance(pub.observables, PauliObservables)
            else []
        )
        try:
            result_shape = list(
                np.broadcast_shapes(tuple(parameter_shape), tuple(observable_shape))
            )
        except ValueError as exc:
            raise BudgetContractError(
                f"PUB {pub.pub_id!r} parameter and observable shapes do not broadcast"
            ) from exc
    circuit_executions = math.prod(result_shape) if result_shape else 1
    return PubShape(
        schema_version="1.0",
        pub_id=pub.pub_id,
        parameter_shape=list(parameter_shape),
        observable_shape=(None if observable_shape is None else list(observable_shape)),
        result_shape=result_shape,
        circuit_executions=circuit_executions,
    )


def _scheduled_seconds(circuit: QuantumCircuit, target: ResolvedTarget) -> float:
    target.verify_current()
    if target.target.dt is None or target.target.dt <= 0:
        raise BudgetContractError("locked scheduling requires a positive target.dt")
    durations = target.target.durations()
    try:
        scheduled = PassManager([ALAPScheduleAnalysis(durations)]).run(circuit)
        starts = scheduled.op_start_times
    except Exception as exc:
        raise BudgetContractError(
            f"circuit cannot be scheduled by {ESTIMATION_METHOD} {ESTIMATION_VERSION}: {exc}"
        ) from exc
    ends: list[float] = []
    for index, instruction in enumerate(scheduled.data):
        qargs = tuple(scheduled.find_bit(qubit).index for qubit in instruction.qubits)
        try:
            duration = float(durations.get(instruction.operation, qargs, unit="s"))
        except Exception as exc:
            raise BudgetContractError(
                f"missing locked duration for {instruction.operation.name}{qargs}"
            ) from exc
        ends.append(float(starts[index]) * target.target.dt + duration)
    scheduled_seconds = max(ends, default=0.0)
    if scheduled_seconds <= 0:
        raise BudgetContractError("scheduled circuit duration must be positive")
    return scheduled_seconds


def _rep_delay(options: Mapping[str, Any]) -> float:
    execution = options.get("execution")
    if not isinstance(execution, Mapping):
        raise BudgetContractError("resolved options require execution.rep_delay")
    value = execution.get("rep_delay")
    if not _configured(value):
        raise BudgetContractError("resolved options require execution.rep_delay")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise BudgetContractError("execution.rep_delay must be non-negative seconds")
    return float(value)


def _backend_default_rep_delay(resolved_target: ResolvedTarget) -> float:
    value = getattr(resolved_target.backend, "default_rep_delay", None)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise BudgetContractError(
            "resolved backend requires a non-negative default_rep_delay"
        )
    return float(value)


def _repetitions(pub: SamplerPubSpec | EstimatorPubSpec) -> int:
    if isinstance(pub, SamplerPubSpec):
        return pub.shots
    if pub.precision is None:
        raise BudgetContractError(
            f"Estimator PUB {pub.pub_id!r} requires explicit precision"
        )
    return math.ceil(1.0 / float(pub.precision) ** 2)


def budget_policy_hash(policy: BudgetPolicy) -> str:
    """Hash the complete fail-closed policy used to resolve a plan."""
    return canonical_json_hash(policy.model_dump(mode="python"))


def submission_plan_payload(plan: SubmissionPlan) -> dict[str, Any]:
    """Return the canonical plan payload; ``plan_hash`` cannot hash itself."""
    payload = plan.model_dump(mode="python")
    payload.pop("plan_hash", None)
    return payload


def submission_plan_hash(plan: SubmissionPlan) -> str:
    """Hash every persisted execution-relevant plan field except the digest itself."""
    return canonical_json_hash(submission_plan_payload(plan))


def validate_submission_plan_hash(plan: SubmissionPlan) -> None:
    """Fail closed when a plan was constructed or mutated outside the planner."""
    if submission_plan_hash(plan) != plan.plan_hash:
        raise ApprovalError("SubmissionPlan canonical hash is invalid")


class SubmissionPlanner:
    """Resolve exact resources and produce deterministic, non-submitting plans."""

    def __init__(self, resolver: RuntimeResourceResolver, sink: ArtifactSink) -> None:
        self._resolver = resolver
        self._sink = sink

    @staticmethod
    def _limits(policy: BudgetPolicy) -> BatchExecutionLimits:
        return BatchExecutionLimits(
            schema_version="1.0",
            max_jobs=policy.max_jobs,
            max_pubs_per_job=policy.max_pubs_per_job,
            max_estimated_qpu_seconds_per_job=policy.max_estimated_qpu_seconds,
            max_execution_seconds_per_job=policy.max_execution_seconds,
            batch_max_time_seconds=policy.batch_max_time_seconds,
            ttl_margin_seconds=policy.ttl_margin_seconds,
        )

    def resolve(
        self, request: SubmissionRequest, policy: BudgetPolicy
    ) -> SubmissionPlan:
        """Perform one complete current-state dry-run without creating a job."""
        if not request.plan_id:
            raise BudgetContractError("plan_id must not be empty")
        if not request.pubs:
            raise BudgetContractError("at least one PUB is required")
        if len(request.pubs) > policy.max_pubs:
            raise BudgetLimitError("request exceeds policy max_pubs")
        if request.maximum_execution_seconds > policy.max_execution_seconds:
            raise BudgetLimitError("request exceeds policy max_execution_seconds")
        if request.primitive not in policy.permitted_primitives:
            raise BudgetLimitError("primitive is not permitted by policy")

        resolved = self._resolver.resolve(request.instance_id, request.backend_name)
        if resolved.instance_id != request.instance_id:
            raise BudgetContractError("resolver returned a different Runtime instance")
        if resolved.target.backend_name != request.backend_name:
            raise BudgetContractError("resolver returned a different backend")
        if resolved.target.snapshot.instance_id != resolved.instance_id:
            raise BudgetContractError(
                "backend snapshot belongs to a different instance"
            )
        resolved.target.verify_current()

        pubs = [pub.model_copy(deep=True) for pub in request.pubs]
        expected_pub_type = (
            SamplerPubSpec if request.primitive == "sampler" else EstimatorPubSpec
        )
        if any(not isinstance(pub, expected_pub_type) for pub in pubs):
            raise BudgetContractError("request primitive and PUB types do not match")
        resolved_options = _resolve_options(
            request.primitive,
            request.options,
            request.maximum_execution_seconds,
            _backend_default_rep_delay(resolved.target),
        )
        treatments, treatment_multiplier, physical_variants = (
            _treatments_and_multiplier(request.primitive, resolved_options)
        )
        forbidden_treatments = sorted(
            set(treatments).difference(policy.permitted_treatments)
        )
        if forbidden_treatments:
            raise BudgetLimitError(
                "treatments are not permitted by policy: "
                + ", ".join(forbidden_treatments)
            )

        shapes: list[PubShape] = []
        scheduled_estimates: list[ScheduledPubEstimate] = []
        partition_estimates: list[PubExecutionEstimate] = []
        total_circuit_executions = 0
        rep_delay = _rep_delay(resolved_options)
        for pub in pubs:
            shape = _pub_shape(pub)
            repetitions = _repetitions(pub)
            if repetitions > policy.max_shots_per_pub:
                raise BudgetLimitError(
                    f"PUB {pub.pub_id!r} exceeds policy max_shots_per_pub"
                )
            loaded = load_circuit_artifact(pub.circuit, sink=self._sink)
            validated = apply_circuit_mode(
                loaded, mode="validate", resolved_target=resolved.target
            )
            scheduled_seconds = _scheduled_seconds(validated.circuit, resolved.target)
            cycle_seconds = max(
                scheduled_seconds + rep_delay,
                CONSERVATIVE_MINIMUM_CYCLE_SECONDS,
            )
            estimate = (
                cycle_seconds
                * shape.circuit_executions
                * repetitions
                * treatment_multiplier
            )
            physical_circuit_executions = shape.circuit_executions * physical_variants
            total_circuit_executions += physical_circuit_executions
            if total_circuit_executions > policy.max_circuits:
                raise BudgetLimitError("plan exceeds policy max_circuits")
            shapes.append(shape)
            scheduled_estimates.append(
                ScheduledPubEstimate(
                    schema_version="1.0",
                    pub_id=pub.pub_id,
                    scheduled_circuit_seconds=scheduled_seconds,
                    conservative_cycle_seconds=cycle_seconds,
                    circuit_executions=shape.circuit_executions,
                    physical_circuit_executions=physical_circuit_executions,
                    repetitions_per_execution=repetitions,
                    treatment_multiplier=treatment_multiplier,
                    estimated_qpu_seconds=estimate,
                )
            )
            partition_estimates.append(
                PubExecutionEstimate(
                    schema_version="1.0",
                    pub_id=pub.pub_id,
                    estimated_qpu_seconds=estimate,
                )
            )

        estimated_total = math.fsum(
            float(estimate.estimated_qpu_seconds) for estimate in scheduled_estimates
        )
        if estimated_total > policy.max_estimated_qpu_seconds:
            raise BudgetLimitError("plan exceeds policy max_estimated_qpu_seconds")
        try:
            partitions = plan_batch_partitions(
                partition_estimates, self._limits(policy)
            )
        except BatchPartitionLimitError as exc:
            raise BudgetLimitError(str(exc)) from exc
        if len(partitions) > policy.max_jobs:
            raise BudgetLimitError("plan exceeds policy max_jobs")
        if len(partitions) > policy.max_partitions:
            raise BudgetLimitError("plan exceeds policy max_partitions")

        placeholder_hash = f"sha256:{'0' * 64}"
        plan = SubmissionPlan(
            schema_version="1.0",
            plan_id=request.plan_id,
            submission_key=request.submission_key,
            plan_hash=placeholder_hash,
            policy_hash=budget_policy_hash(policy),
            instance_id=resolved.instance_id,
            instance_plan_type=resolved.instance_plan_type,
            backend_name=resolved.target.backend_name,
            target_hash=resolved.target.target_hash,
            compiler_target_hash=resolved.target.compiler_target_hash,
            primitive=request.primitive,
            pubs=pubs,
            pub_shapes=shapes,
            resolved_options=resolved_options,
            treatments=treatments,
            partitions=list(partitions),
            scheduled_estimates=scheduled_estimates,
            total_circuit_executions=total_circuit_executions,
            estimated_qpu_seconds=estimated_total,
            maximum_execution_seconds=request.maximum_execution_seconds,
            estimation_method=ESTIMATION_METHOD,
            estimation_version=ESTIMATION_VERSION,
            estimation_software_versions=_software_versions(),
        )
        return plan.model_copy(update={"plan_hash": submission_plan_hash(plan)})


def validate_approval(
    plan: SubmissionPlan,
    approval: ApprovalReceipt | None,
    policy: BudgetPolicy,
    *,
    now: datetime,
) -> None:
    """Validate all policy and receipt constraints immediately before submission."""
    validate_submission_plan_hash(plan)
    if approval is None:
        raise ApprovalError("live QPU submission requires an ApprovalReceipt")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ApprovalError("approval validation clock must be timezone-aware")
    if policy.dry_run or not policy.allow_live_qpu:
        raise ApprovalError("policy does not permit live QPU submission")
    if plan.policy_hash != budget_policy_hash(policy):
        raise ApprovalError("SubmissionPlan policy hash no longer matches")
    if approval.plan_hash != plan.plan_hash:
        raise ApprovalError("ApprovalReceipt is bound to a different plan hash")
    if approval.approved_at > now:
        raise ApprovalError("ApprovalReceipt approval time is in the future")
    if approval.expires_at <= now:
        raise ApprovalError("ApprovalReceipt has expired")
    if approval.expires_at > approval.approved_at + timedelta(
        seconds=policy.approval_ttl_seconds
    ):
        raise ApprovalError("ApprovalReceipt exceeds policy approval TTL")
    if plan.instance_id not in policy.allowed_instance_ids:
        raise ApprovalError("plan instance is not allowed by policy")
    if plan.instance_id not in approval.allowed_instance_ids:
        raise ApprovalError("plan instance is not allowed by approval")
    if plan.backend_name not in policy.allowed_backends:
        raise ApprovalError("plan backend is not allowed by policy")
    if plan.backend_name not in approval.allowed_backends:
        raise ApprovalError("plan backend is not allowed by approval")
    if plan.instance_plan_type == "paid" and not (
        policy.allow_paid_fallback
        and approval.allow_paid_fallback
        and plan.instance_id in policy.allowed_paid_instance_ids
    ):
        raise ApprovalError("paid Runtime instance execution is not explicitly allowed")
    if plan.primitive not in policy.permitted_primitives:
        raise ApprovalError("plan primitive is no longer permitted")
    if set(plan.treatments).difference(policy.permitted_treatments):
        raise ApprovalError("plan treatments are no longer permitted")
    if len(plan.pubs) > policy.max_pubs:
        raise BudgetLimitError("plan exceeds policy max_pubs")
    if len(plan.partitions) > policy.max_jobs:
        raise BudgetLimitError("plan exceeds policy max_jobs")
    if len(plan.partitions) > policy.max_partitions:
        raise BudgetLimitError("plan exceeds policy max_partitions")
    if plan.total_circuit_executions > policy.max_circuits:
        raise BudgetLimitError("plan exceeds policy max_circuits")
    if any(
        estimate.repetitions_per_execution > policy.max_shots_per_pub
        for estimate in plan.scheduled_estimates
    ):
        raise BudgetLimitError("plan exceeds policy max_shots_per_pub")
    if plan.estimated_qpu_seconds > policy.max_estimated_qpu_seconds:
        raise BudgetLimitError("plan exceeds policy QPU-second limit")
    if plan.estimated_qpu_seconds > approval.max_qpu_seconds:
        raise BudgetLimitError("plan exceeds approved QPU-second limit")
    if plan.maximum_execution_seconds > policy.max_execution_seconds:
        raise BudgetLimitError("plan exceeds policy max_execution_seconds")
    if plan.resolved_options.get("max_execution_time") != int(
        plan.maximum_execution_seconds
    ):
        raise ApprovalError("plan max_execution_time is not canonical")


def create_approval_receipt(
    plan: SubmissionPlan,
    *,
    approved_at: datetime,
    expires_at: datetime,
    max_qpu_seconds: float,
    allowed_instance_ids: Sequence[str],
    allowed_backends: Sequence[str],
    allow_paid_fallback: bool = False,
) -> ApprovalReceipt:
    """Create a typed receipt for an already reviewed immutable plan."""
    validate_submission_plan_hash(plan)
    return ApprovalReceipt(
        schema_version="1.0",
        plan_hash=plan.plan_hash,
        approved_at=approved_at,
        expires_at=expires_at,
        max_qpu_seconds=max_qpu_seconds,
        allowed_instance_ids=tuple(allowed_instance_ids),
        allowed_backends=tuple(allowed_backends),
        allow_paid_fallback=allow_paid_fallback,
    )


class ApprovedBatchExecutor:
    """Only public live-submit boundary: re-resolve, approve, then delegate once."""

    def __init__(
        self,
        service: RuntimeAuthorityService,
        *,
        instance_id: str,
        sink: LocalArtifactCAS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._planner = SubmissionPlanner(
            ServiceRuntimeResourceResolver(service, clock=self._clock), sink
        )
        self._lifecycle = BatchLifecycle(
            cast(Any, service),
            instance_id=instance_id,
            sink=sink,
            clock=self._clock,
        )
        self._approval_ledger: ApprovalConsumptionLedger = (
            LocalApprovalConsumptionLedger(sink.root)
        )

    @classmethod
    def _from_test_components(
        cls,
        planner: SubmissionPlanner,
        lifecycle: BatchLifecycle,
        *,
        approval_ledger: ApprovalConsumptionLedger,
        clock: Callable[[], datetime] | None = None,
    ) -> ApprovedBatchExecutor:
        """Build a no-QPU test harness without weakening the public constructor."""
        executor = cls.__new__(cls)
        executor._clock = clock or (lambda: datetime.now(timezone.utc))
        executor._planner = planner
        executor._lifecycle = lifecycle
        executor._approval_ledger = approval_ledger
        return executor

    def dry_run(
        self, request: SubmissionRequest, policy: BudgetPolicy
    ) -> SubmissionPlan:
        """Return the exact plan without creating a Batch or primitive job."""
        return self._planner.resolve(request, policy)

    def submit(
        self,
        batch_id: str,
        request: SubmissionRequest,
        policy: BudgetPolicy,
        approval: ApprovalReceipt | None,
    ) -> ApprovedSubmission:
        """Re-resolve and validate immediately before the internal submit call."""
        plan = self._planner.resolve(request, policy)
        validate_approval(plan, approval, policy, now=self._clock())
        if approval is None:  # pragma: no cover - narrowed by validate_approval
            raise ApprovalError("live QPU submission requires an ApprovalReceipt")
        try:
            self._approval_ledger.consume(
                plan_hash=plan.plan_hash,
                approval_hash=canonical_json_hash(approval.model_dump(mode="python")),
                submission_key=plan.submission_key,
                consumed_at=self._clock(),
            )
        except ApprovalConsumptionError as exc:
            raise ApprovalError(str(exc)) from exc
        receipt = self._lifecycle._submit_resolved_plan(  # noqa: SLF001
            batch_id,
            plan,
            submission_key=plan.submission_key,
            limits=SubmissionPlanner._limits(policy),
            duplicate_policy="reject",
        )
        return ApprovedSubmission(
            schema_version="1.0",
            plan_hash=plan.plan_hash,
            estimated_qpu_seconds=plan.estimated_qpu_seconds,
            approval_max_qpu_seconds=approval.max_qpu_seconds,
            receipt=receipt,
        )

    def reconcile_usage(
        self,
        submission: ApprovedSubmission,
    ) -> UsageReconciliation:
        """Return provider actuals beside the immutable estimate and approval cap."""
        if submission.receipt.plan_hash != submission.plan_hash:
            raise ApprovalError("submission receipt is bound to a different plan hash")
        usage = self._lifecycle.batch_usage(submission.receipt.batch_id)
        if usage.batch_id != submission.receipt.batch_id:
            raise ApprovalError("usage belongs to a different Batch")
        expected_job_ids = tuple(job.job_id for job in submission.receipt.jobs)
        usage_by_job = {job.job_id: job for job in usage.jobs}
        if len(usage_by_job) != len(usage.jobs):
            raise ApprovalError("Batch usage returned duplicate job IDs")
        if any(job_id not in usage_by_job for job_id in expected_job_ids):
            raise ApprovalError("Batch usage is missing approved submission jobs")
        jobs = tuple(usage_by_job[job_id] for job_id in expected_job_ids)
        actual = None
        if all(job.quantum_seconds is not None for job in jobs):
            actual = math.fsum(
                float(job.quantum_seconds)
                for job in jobs
                if job.quantum_seconds is not None
            )
        submission_usage = type(usage)(
            schema_version="1.0",
            batch_id=usage.batch_id,
            batch_seconds=actual,
            jobs=jobs,
            retrieved_at=usage.retrieved_at,
        )
        return UsageReconciliation(
            schema_version="1.0",
            plan_hash=submission.plan_hash,
            estimated_qpu_seconds=submission.estimated_qpu_seconds,
            approval_max_qpu_seconds=submission.approval_max_qpu_seconds,
            actual_qpu_seconds=actual,
            batch_usage=submission_usage,
        )
