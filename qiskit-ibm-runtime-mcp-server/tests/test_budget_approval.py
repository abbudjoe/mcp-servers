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

"""W1-08 preflight budget, canonical hash, and approval-boundary tests."""

from __future__ import annotations

import io
import inspect
import multiprocessing
import os
import stat
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Literal

import pytest
import qiskit
from qiskit import QuantumCircuit, qpy
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime.fake_provider import FakeAthensV2

from qiskit_ibm_runtime_mcp_server.core.artifacts import LocalArtifactCAS
from qiskit_ibm_runtime_mcp_server.core.approvals import (
    ApprovalConsumptionError,
    ApprovalReplayError,
    LocalApprovalConsumptionLedger,
)
from qiskit_ibm_runtime_mcp_server.core import approvals as approval_module
from qiskit_ibm_runtime_mcp_server.core import budgeting as budgeting_module
from qiskit_ibm_runtime_mcp_server.core.budgeting import (
    ESTIMATION_METHOD,
    ESTIMATION_VERSION,
    ApprovalError,
    ApprovedBatchExecutor,
    ApprovedSubmissionStep,
    BudgetContractError,
    BudgetLimitError,
    IncompleteSubmissionError,
    ResolvedRuntimeTarget,
    ServiceRuntimeResourceResolver,
    SubmissionPlanner,
    SubmissionRequest,
    create_approval_receipt,
    require_fully_submitted,
    submission_plan_payload,
    validate_approval,
)
from qiskit_ibm_runtime_mcp_server.core.circuits import ResolvedTarget, ingest_circuit
from qiskit_ibm_runtime_mcp_server.core.models import (
    ApprovalReceipt,
    ApprovedSubmission,
    BatchJobReceipt,
    BatchJobUsage,
    BatchSubmissionFailure,
    BatchSubmissionReceipt,
    BatchUsage,
    BudgetPolicy,
    EstimatorPubSpec,
    PauliObservables,
    SamplerPubSpec,
    SparsePauliHamiltonian,
    SubmissionPlan,
)
from qiskit_ibm_runtime_mcp_server.core.serialization import canonical_json_hash
from qiskit_ibm_runtime_mcp_server.core.snapshots import build_backend_snapshot


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)


def _consume_approval_in_process(root: str, barrier: Any, queue: Any) -> None:
    """Contend for one durable approval from an independently spawned process."""
    ledger = LocalApprovalConsumptionLedger(root)
    barrier.wait(timeout=15)
    try:
        ledger.consume(
            plan_hash=f"sha256:{'a' * 64}",
            approval_hash=f"sha256:{'b' * 64}",
            submission_key="atomic-key",
            consumed_at=NOW,
        )
    except ApprovalReplayError:
        queue.put("replayed")
    else:
        queue.put("consumed")


def _qpy_bytes(circuit: QuantumCircuit) -> bytes:
    buffer = io.BytesIO()
    qpy.dump(circuit, buffer)
    return buffer.getvalue()


class RecordingResolver:
    def __init__(self, *, plan_type: str = "open") -> None:
        self.backend = FakeAthensV2()
        self.snapshot = build_backend_snapshot(
            self.backend,
            instance_id="crn:test",
            properties=None,
            retrieved_at=NOW,
        )
        self.plan_type = plan_type
        self.calls = 0

    def resolve(self, instance_id: str, backend_name: str) -> ResolvedRuntimeTarget:
        self.calls += 1
        assert instance_id == "crn:test"
        assert backend_name == self.backend.name
        return ResolvedRuntimeTarget(
            instance_id=instance_id,
            instance_plan_type=self.plan_type,  # type: ignore[arg-type]
            target=ResolvedTarget(self.backend, self.snapshot),
        )


class AuthorityService:
    def __init__(self, *, plan: str = "open") -> None:
        self.resolved_backend = FakeAthensV2()
        self.plan = plan
        self.backend_calls: list[tuple[str, dict[str, Any]]] = []

    def instances(self) -> list[dict[str, str]]:
        return [{"crn": "crn:test", "plan": self.plan, "name": "test"}]

    def backend(self, name: str, **kwargs: Any) -> Any:
        self.backend_calls.append((name, kwargs))
        return self.resolved_backend


class RecordingLifecycle:
    def __init__(self) -> None:
        self.submissions: list[tuple[SubmissionPlan, Any]] = []

    def _submit_resolved_plan(
        self,
        batch_id: str,
        plan: SubmissionPlan,
        *,
        submission_key: str,
        limits: Any,
        duplicate_policy: str,
    ) -> BatchSubmissionReceipt:
        assert batch_id == "batch-1"
        assert submission_key == "approved-key"
        assert duplicate_policy == "reject"
        self.submissions.append((plan, limits))
        return BatchSubmissionReceipt(
            schema_version="1.0",
            submission_key=submission_key,
            batch_id=batch_id,
            plan_hash=plan.plan_hash,
            pub_ids=tuple(pub.pub_id for pub in plan.pubs),
            jobs=(
                BatchJobReceipt(
                    schema_version="1.0",
                    partition_id=plan.partitions[0].partition_id,
                    job_id="job-1",
                    pub_ids=tuple(plan.partitions[0].pub_ids),
                    submitted_at=NOW,
                ),
            ),
            state="submitted",
            reserved_at=NOW,
            completed_at=NOW,
        )

    def batch_usage(self, batch_id: str) -> BatchUsage:
        return BatchUsage(
            schema_version="1.0",
            batch_id=batch_id,
            batch_seconds=1.5,
            jobs=(
                BatchJobUsage(
                    schema_version="1.0",
                    job_id="job-1",
                    quantum_seconds=1.5,
                ),
                BatchJobUsage(
                    schema_version="1.0",
                    job_id="unrelated-job",
                    quantum_seconds=9.0,
                ),
            ),
            retrieved_at=NOW,
        )


class RecordingApprovalLedger:
    def __init__(self) -> None:
        self.consumed: set[str] = set()

    def consume(
        self,
        *,
        plan_hash: str,
        approval_hash: str,
        submission_key: str,
        consumed_at: datetime,
    ) -> None:
        assert approval_hash.startswith("sha256:")
        assert submission_key
        assert consumed_at == NOW
        if plan_hash in self.consumed:
            raise ApprovalReplayError(
                "approved SubmissionPlan has already been consumed"
            )
        self.consumed.add(plan_hash)


@pytest.fixture
def policy() -> BudgetPolicy:
    return BudgetPolicy(
        schema_version="1.0",
        dry_run=False,
        allow_live_qpu=True,
        allow_paid_fallback=False,
        max_estimated_qpu_seconds=10,
        max_execution_seconds=60,
        max_jobs=2,
        max_pubs=4,
        max_circuits=32,
        max_partitions=2,
        max_pubs_per_job=2,
        max_shots_per_pub=1024,
        batch_max_time_seconds=300,
        ttl_margin_seconds=60,
        approval_ttl_seconds=600,
        allowed_instance_ids=("crn:test",),
        allowed_backends=("fake_athens",),
        permitted_primitives=("sampler", "estimator"),
        permitted_treatments=(),
    )


@pytest.fixture
def planner_bundle(
    tmp_path: Any,
) -> tuple[SubmissionPlanner, RecordingResolver, SubmissionRequest]:
    sink = LocalArtifactCAS(tmp_path)
    resolver = RecordingResolver()
    circuit = QuantumCircuit(5, 5)
    circuit.x(0)
    circuit.measure(range(5), range(5))
    isa = generate_preset_pass_manager(
        optimization_level=0,
        target=resolver.backend.target,
        seed_transpiler=11,
    ).run(circuit)
    artifact = ingest_circuit(_qpy_bytes(isa), circuit_format="qpy", sink=sink).artifact
    pub = SamplerPubSpec(
        schema_version="1.0",
        pub_id="sampler-a",
        circuit=artifact,
        parameter_values=None,
        shots=100,
    )
    request = SubmissionRequest(
        plan_id="plan-safety-boundary",
        submission_key="approved-key",
        instance_id="crn:test",
        backend_name="fake_athens",
        primitive="sampler",
        pubs=(pub,),
        options={},
        maximum_execution_seconds=60,
    )
    return SubmissionPlanner(resolver, sink), resolver, request


def _approval(plan: SubmissionPlan, *, cap: float = 10) -> ApprovalReceipt:
    return create_approval_receipt(
        plan,
        approved_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
        max_qpu_seconds=cap,
        allowed_instance_ids=("crn:test",),
        allowed_backends=("fake_athens",),
    )


def test_normal_public_api_has_no_unapproved_submit_or_boolean_confirmation() -> None:
    import qiskit_ibm_runtime_mcp_server.core as core

    assert not hasattr(core, "submit_sampler_pubs")
    assert not hasattr(core, "submit_estimator_pubs")
    assert not hasattr(core.BatchLifecycle, "submit_plan")
    parameters = inspect.signature(ApprovedBatchExecutor.submit).parameters
    assert "confirm" not in parameters
    assert "duplicate_policy" not in parameters
    assert "submission_key" not in parameters


def test_public_executor_owns_one_service_for_resolution_and_submission(
    tmp_path: Any,
) -> None:
    service = AuthorityService(plan="premium")
    sink = LocalArtifactCAS(tmp_path)

    executor = ApprovedBatchExecutor(
        service, instance_id="crn:test", sink=sink, clock=lambda: NOW
    )
    resolved = ServiceRuntimeResourceResolver(service, clock=lambda: NOW).resolve(
        "crn:test", "fake_athens"
    )

    assert resolved.instance_plan_type == "paid"
    assert resolved.target.backend is service.resolved_backend
    assert service.backend_calls[-1] == (
        "fake_athens",
        {"instance": "crn:test", "use_fractional_gates": False},
    )
    assert executor._lifecycle._service is service  # noqa: SLF001
    assert executor._approval_ledger.path.parent == sink.root  # noqa: SLF001


def test_durable_approval_consumption_is_atomic_across_processes(
    tmp_path: Any,
) -> None:
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    queue = context.Queue()
    processes = [
        context.Process(
            target=_consume_approval_in_process,
            args=(str(tmp_path), barrier, queue),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
    for process in processes:
        assert not process.is_alive()
        assert process.exitcode == 0
    outcomes = sorted(queue.get(timeout=5) for _ in processes)
    queue.close()

    assert outcomes == ["consumed", "replayed"]
    with pytest.raises(ApprovalReplayError, match="already been consumed"):
        LocalApprovalConsumptionLedger(tmp_path).consume(
            plan_hash=f"sha256:{'a' * 64}",
            approval_hash=f"sha256:{'b' * 64}",
            submission_key="atomic-key",
            consumed_at=NOW,
        )


@pytest.mark.parametrize(
    ("mode", "owner_offset", "message"),
    [
        (stat.S_IFDIR | 0o700, 0, "regular file"),
        (stat.S_IFREG | 0o600, 1, "owned by the current user"),
    ],
)
def test_approval_ledger_rejects_unsafe_file_identity(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
    mode: int,
    owner_offset: int,
    message: str,
) -> None:
    """The durable one-time ledger must fail closed on file substitution."""
    ledger = LocalApprovalConsumptionLedger.__new__(LocalApprovalConsumptionLedger)
    ledger._path = tmp_path / "approval-ledger.sqlite3"  # noqa: SLF001
    current_uid = os.getuid()
    monkeypatch.setattr(
        approval_module.os,
        "fstat",
        lambda _descriptor: SimpleNamespace(
            st_mode=mode,
            st_uid=current_uid + owner_offset,
        ),
    )

    with pytest.raises(ApprovalConsumptionError, match=message):
        ledger._prepare_database_file()  # noqa: SLF001


def test_dry_run_resolves_locked_schedule_complete_options_and_shapes(
    planner_bundle: tuple[SubmissionPlanner, RecordingResolver, SubmissionRequest],
    policy: BudgetPolicy,
) -> None:
    planner, resolver, request = planner_bundle

    plan = planner.resolve(request, policy)

    assert resolver.calls == 1
    assert plan.instance_id == "crn:test"
    assert plan.backend_name == "fake_athens"
    assert plan.target_hash == resolver.snapshot.target_hash
    assert plan.compiler_target_hash
    assert plan.pub_shapes[0].result_shape == []
    assert plan.pub_shapes[0].circuit_executions == 1
    assert plan.scheduled_estimates[0].scheduled_circuit_seconds > 0
    assert plan.scheduled_estimates[0].conservative_cycle_seconds == 0.001
    assert plan.scheduled_estimates[0].repetitions_per_execution == 100
    assert plan.estimated_qpu_seconds == pytest.approx(0.1)
    assert plan.resolved_options["max_execution_time"] == 60
    assert plan.resolved_options["dynamical_decoupling"]["enable"] is False
    assert plan.resolved_options["twirling"]["enable_gates"] is False
    assert plan.estimation_method == ESTIMATION_METHOD
    assert plan.estimation_version == ESTIMATION_VERSION
    assert plan.estimation_software_versions["qiskit"] == qiskit.__version__
    assert canonical_json_hash(submission_plan_payload(plan)) == plan.plan_hash


def test_estimator_precision_broadcast_and_zne_multiplier_are_resolved(
    tmp_path: Any, policy: BudgetPolicy
) -> None:
    sink = LocalArtifactCAS(tmp_path)
    resolver = RecordingResolver()
    circuit = QuantumCircuit(5)
    circuit.x(0)
    isa = generate_preset_pass_manager(
        optimization_level=0, target=resolver.backend.target, seed_transpiler=3
    ).run(circuit)
    artifact = ingest_circuit(_qpy_bytes(isa), circuit_format="qpy", sink=sink).artifact
    pub = EstimatorPubSpec(
        schema_version="1.0",
        pub_id="estimator-a",
        circuit=artifact,
        observables=PauliObservables(
            schema_version="1.0",
            kind="pauli_observables",
            shape=[2],
            values=["IIIII", "IIIIZ"],
        ),
        parameter_values=None,
        precision=0.1,
    )
    request = SubmissionRequest(
        plan_id="estimator-plan",
        submission_key="estimator-key",
        instance_id="crn:test",
        backend_name="fake_athens",
        primitive="estimator",
        pubs=(pub,),
        options={
            "resilience": {
                "zne_mitigation": True,
                "zne": {
                    "amplifier": "gate_folding",
                    "noise_factors": [1, 3, 9],
                },
            }
        },
        maximum_execution_seconds=60,
    )
    zne_policy = policy.model_copy(update={"permitted_treatments": ("zne_mitigation",)})

    plan = SubmissionPlanner(resolver, sink).resolve(request, zne_policy)

    assert plan.pub_shapes[0].observable_shape == [2]
    assert plan.pub_shapes[0].result_shape == [2]
    assert plan.pub_shapes[0].circuit_executions == 2
    assert plan.scheduled_estimates[0].repetitions_per_execution == 100
    assert plan.scheduled_estimates[0].treatment_multiplier == pytest.approx(13)
    assert plan.scheduled_estimates[0].physical_circuit_executions == 6
    assert plan.total_circuit_executions == 6
    assert plan.estimated_qpu_seconds == pytest.approx(2.6)
    assert plan.treatments == ["zne_mitigation"]

    approval = _approval(plan)
    for path, value in (
        (("pubs", 0, "observables", "shape"), [1, 2]),
        (("pubs", 0, "observables", "values"), ["IIIII", "IIIIX"]),
        (("pubs", 0, "parameter_values"), {"shape": [1], "values": [[0.5]]}),
        (("pubs", 0, "precision"), 0.2),
    ):
        payload = plan.model_dump(mode="python")
        _set(path, value)(payload)
        mutated = SubmissionPlan.model_construct(**payload)
        with pytest.raises(ApprovalError, match="canonical hash"):
            validate_approval(mutated, approval, zne_policy, now=NOW)

    pea_request = replace(
        request,
        options={
            "resilience": {
                "zne_mitigation": True,
                "zne": {"amplifier": "pea", "noise_factors": [1, 3, 9]},
            }
        },
    )
    with pytest.raises(BudgetContractError, match="explicit gate_folding"):
        SubmissionPlanner(resolver, sink).resolve(pea_request, zne_policy)

    hamiltonian_pub = pub.model_copy(
        update={
            "observables": SparsePauliHamiltonian(
                schema_version="1.0",
                kind="sparse_pauli_hamiltonian",
                terms=[("IIIII", 1.0), ("IIIIZ", 1.0), ("IIIIX", 1.0)],
            )
        }
    )
    with pytest.raises(BudgetContractError, match="weighted Hamiltonians"):
        SubmissionPlanner(resolver, sink).resolve(
            replace(request, pubs=(hamiltonian_pub,)), zne_policy
        )


@pytest.mark.parametrize(
    ("requested", "message"),
    [
        ({"max_execution_time": 59}, "must match"),
        ({"experimental": {"image": "unsupported"}}, "experimental"),
        ({"simulator": {"seed_simulator": 1}}, "simulator"),
        ({"unknown_option": True}, "invalid locked Runtime options"),
    ],
)
def test_runtime_option_resolution_rejects_unbounded_inputs(
    requested: dict[str, Any], message: str
) -> None:
    """Unsupported or contradictory options fail before estimation."""
    with pytest.raises(BudgetContractError, match=message):
        budgeting_module._resolve_options(  # noqa: SLF001
            "sampler", requested, 60, 0.001
        )


@pytest.mark.parametrize("value", [True, 0, "1"])
def test_positive_treatment_counts_are_explicit_integers(value: Any) -> None:
    with pytest.raises(BudgetContractError, match="positive integer"):
        budgeting_module._positive_int_option(value, "count")  # noqa: SLF001


def test_treatment_multiplier_branches_are_bounded() -> None:
    """Twirling expands deterministically; unsupported mitigations fail closed."""
    twirled = budgeting_module._resolve_options(  # noqa: SLF001
        "sampler",
        {
            "twirling": {
                "enable_gates": True,
                "enable_measure": True,
                "num_randomizations": 3,
                "shots_per_randomization": 16,
            }
        },
        60,
        0.001,
    )
    treatments, multiplier, variants = budgeting_module._treatments_and_multiplier(  # noqa: SLF001
        "sampler", twirled
    )
    assert treatments == ["gate_twirling", "measure_twirling"]
    assert multiplier == 3
    assert variants == 3

    estimator_cases = (
        ({"resilience_level": 1}, "resilience levels"),
        ({"resilience": {"measure_mitigation": True}}, "measurement mitigation"),
        ({"resilience": {"pec_mitigation": True}}, "PEC"),
    )
    for requested, message in estimator_cases:
        options = budgeting_module._resolve_options(  # noqa: SLF001
            "estimator", requested, 60, 0.001
        )
        with pytest.raises(BudgetContractError, match=message):
            budgeting_module._treatments_and_multiplier(  # noqa: SLF001
                "estimator", options
            )


@pytest.mark.parametrize(
    "noise_factors",
    [None, [], [True], [float("nan")], [0.5]],
)
def test_zne_noise_factors_are_explicit_finite_bounds(noise_factors: Any) -> None:
    options = {
        "dynamical_decoupling": {"enable": False},
        "twirling": {"enable_gates": False, "enable_measure": False},
        "resilience_level": 0,
        "resilience": {
            "measure_mitigation": False,
            "zne_mitigation": True,
            "pec_mitigation": False,
            "zne": {
                "amplifier": "gate_folding",
                "noise_factors": noise_factors,
            },
        },
    }
    with pytest.raises(BudgetContractError, match="explicit finite values"):
        budgeting_module._treatments_and_multiplier(  # noqa: SLF001
            "estimator", options
        )


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({}, "execution.rep_delay"),
        ({"execution": {"rep_delay": {"$runtime_default": "Unset"}}}, "rep_delay"),
        ({"execution": {"rep_delay": True}}, "non-negative"),
        ({"execution": {"rep_delay": -0.1}}, "non-negative"),
    ],
)
def test_repetition_delay_requires_a_nonnegative_number(
    options: dict[str, Any], message: str
) -> None:
    with pytest.raises(BudgetContractError, match=message):
        budgeting_module._rep_delay(options)  # noqa: SLF001


@pytest.mark.parametrize("value", [True, None, -0.1])
def test_backend_default_repetition_delay_is_validated(value: Any) -> None:
    resolved = SimpleNamespace(backend=SimpleNamespace(default_rep_delay=value))
    with pytest.raises(BudgetContractError, match="non-negative default_rep_delay"):
        budgeting_module._backend_default_rep_delay(resolved)  # type: ignore[arg-type] # noqa: SLF001


def test_planning_enforces_pub_and_shot_limits(
    planner_bundle: tuple[SubmissionPlanner, RecordingResolver, SubmissionRequest],
    policy: BudgetPolicy,
) -> None:
    planner, _, request = planner_bundle
    too_many_pubs = SubmissionRequest(
        plan_id=request.plan_id,
        submission_key=request.submission_key,
        instance_id=request.instance_id,
        backend_name=request.backend_name,
        primitive=request.primitive,
        pubs=request.pubs * 5,
        options=request.options,
        maximum_execution_seconds=request.maximum_execution_seconds,
    )
    with pytest.raises(BudgetLimitError, match="max_pubs"):
        planner.resolve(too_many_pubs, policy)

    low_shot_policy = policy.model_copy(update={"max_shots_per_pub": 99})
    with pytest.raises(BudgetLimitError, match="max_shots_per_pub"):
        planner.resolve(request, low_shot_policy)

    second_pub = request.pubs[0].model_copy(update={"pub_id": "sampler-b"})
    two_job_request = SubmissionRequest(
        plan_id=request.plan_id,
        submission_key=request.submission_key,
        instance_id=request.instance_id,
        backend_name=request.backend_name,
        primitive=request.primitive,
        pubs=(request.pubs[0], second_pub),
        options=request.options,
        maximum_execution_seconds=request.maximum_execution_seconds,
    )
    one_job_policy = policy.model_copy(update={"max_jobs": 1, "max_pubs_per_job": 1})
    with pytest.raises(BudgetLimitError, match="max_jobs"):
        planner.resolve(two_job_request, one_job_policy)

    one_partition_policy = policy.model_copy(
        update={"max_jobs": 2, "max_partitions": 1, "max_pubs_per_job": 1}
    )
    with pytest.raises(BudgetLimitError, match="max_partitions"):
        planner.resolve(two_job_request, one_partition_policy)

    one_circuit_policy = policy.model_copy(update={"max_circuits": 1})
    with pytest.raises(BudgetLimitError, match="max_circuits"):
        planner.resolve(two_job_request, one_circuit_policy)

    dd_request = replace(
        request,
        options={"dynamical_decoupling": {"enable": True, "sequence_type": "XX"}},
    )
    dd_policy = policy.model_copy(
        update={"permitted_treatments": ("dynamical_decoupling",)}
    )
    with pytest.raises(BudgetContractError, match="no locked conservative estimator"):
        planner.resolve(dd_request, dd_policy)


def test_planner_rejects_each_request_and_resolver_identity_mismatch(
    planner_bundle: tuple[SubmissionPlanner, RecordingResolver, SubmissionRequest],
    policy: BudgetPolicy,
) -> None:
    """Dry-run validation rejects malformed intent before circuit scheduling."""
    planner, resolver, request = planner_bundle
    cases = (
        (replace(request, plan_id=""), policy, "plan_id"),
        (replace(request, pubs=()), policy, "at least one PUB"),
        (
            replace(request, maximum_execution_seconds=61),
            policy,
            "max_execution_seconds",
        ),
        (
            request,
            policy.model_copy(update={"permitted_primitives": ("estimator",)}),
            "primitive is not permitted",
        ),
        (
            replace(request, primitive="estimator"),
            policy,
            "PUB types do not match",
        ),
        (
            replace(
                request,
                options={
                    "twirling": {
                        "enable_gates": True,
                        "num_randomizations": 2,
                        "shots_per_randomization": 50,
                    }
                },
            ),
            policy,
            "treatments are not permitted",
        ),
    )
    for active_request, active_policy, message in cases:
        with pytest.raises((BudgetContractError, BudgetLimitError), match=message):
            planner.resolve(active_request, active_policy)

    class StaticResolver:
        def __init__(self, resolved: ResolvedRuntimeTarget) -> None:
            self.resolved = resolved

        def resolve(
            self, _instance_id: str, _backend_name: str
        ) -> ResolvedRuntimeTarget:
            return self.resolved

    target = ResolvedTarget(resolver.backend, resolver.snapshot)
    wrong_instance = ResolvedRuntimeTarget(
        instance_id="crn:other", instance_plan_type="open", target=target
    )
    with pytest.raises(BudgetContractError, match="different Runtime instance"):
        SubmissionPlanner(StaticResolver(wrong_instance), planner._sink).resolve(  # type: ignore[arg-type] # noqa: SLF001
            request, policy
        )

    mismatched_snapshot = resolver.snapshot.model_copy(
        update={"instance_id": "crn:other"}
    )
    wrong_snapshot = ResolvedRuntimeTarget(
        instance_id="crn:test",
        instance_plan_type="open",
        target=ResolvedTarget(resolver.backend, mismatched_snapshot),
    )
    with pytest.raises(BudgetContractError, match="snapshot belongs"):
        SubmissionPlanner(StaticResolver(wrong_snapshot), planner._sink).resolve(  # type: ignore[arg-type] # noqa: SLF001
            request, policy
        )


Mutation = Callable[[dict[str, Any]], None]


def _set(path: tuple[str | int, ...], value: Any) -> Mutation:
    def mutate(payload: dict[str, Any]) -> None:
        cursor: Any = payload
        for part in path[:-1]:
            cursor = cursor[part]
        cursor[path[-1]] = value

    return mutate


@pytest.mark.parametrize(
    ("name", "mutate"),
    [
        ("plan_id", _set(("plan_id",), "changed-plan")),
        ("submission_key", _set(("submission_key",), "changed-key")),
        ("policy_hash", _set(("policy_hash",), f"sha256:{'1' * 64}")),
        ("instance", _set(("instance_id",), "crn:other")),
        ("instance_plan", _set(("instance_plan_type",), "paid")),
        ("backend", _set(("backend_name",), "other_backend")),
        ("target", _set(("target_hash",), f"sha256:{'2' * 64}")),
        ("compiler_target", _set(("compiler_target_hash",), f"sha256:{'3' * 64}")),
        ("primitive", _set(("primitive",), "estimator")),
        ("pub_id", _set(("pubs", 0, "pub_id"), "changed-pub")),
        (
            "circuit_hash",
            _set(("pubs", 0, "circuit", "circuit_hash"), f"sha256:{'4' * 64}"),
        ),
        (
            "artifact_hash",
            _set(
                ("pubs", 0, "circuit", "artifact", "artifact_id"),
                f"sha256:{'5' * 64}",
            ),
        ),
        ("parameter_values", _set(("pubs", 0, "parameter_values"), {"shape": []})),
        ("shots", _set(("pubs", 0, "shots"), 101)),
        ("parameter_shape", _set(("pub_shapes", 0, "parameter_shape"), [2])),
        ("result_shape", _set(("pub_shapes", 0, "result_shape"), [2])),
        ("pub_executions", _set(("pub_shapes", 0, "circuit_executions"), 2)),
        ("options", _set(("resolved_options", "execution", "rep_delay"), 0.002)),
        ("treatments", _set(("treatments",), ["dynamical_decoupling"])),
        ("partition", _set(("partitions", 0, "pub_ids"), ["changed-pub"])),
        (
            "partition_estimate",
            _set(("partitions", 0, "estimated_qpu_seconds"), 0.2),
        ),
        (
            "partition_execution_limit",
            _set(("partitions", 0, "maximum_execution_seconds"), 59),
        ),
        (
            "scheduled_duration",
            _set(("scheduled_estimates", 0, "scheduled_circuit_seconds"), 0.5),
        ),
        (
            "conservative_cycle",
            _set(("scheduled_estimates", 0, "conservative_cycle_seconds"), 0.5),
        ),
        (
            "scheduled_executions",
            _set(("scheduled_estimates", 0, "circuit_executions"), 2),
        ),
        (
            "physical_circuits",
            _set(("scheduled_estimates", 0, "physical_circuit_executions"), 2),
        ),
        (
            "repetitions",
            _set(("scheduled_estimates", 0, "repetitions_per_execution"), 101),
        ),
        (
            "treatment_multiplier",
            _set(("scheduled_estimates", 0, "treatment_multiplier"), 2.0),
        ),
        (
            "pub_estimated_usage",
            _set(("scheduled_estimates", 0, "estimated_qpu_seconds"), 0.2),
        ),
        ("total_circuits", _set(("total_circuit_executions",), 2)),
        ("estimated_usage", _set(("estimated_qpu_seconds",), 0.2)),
        ("execution_limit", _set(("maximum_execution_seconds",), 59)),
        ("estimation_method", _set(("estimation_method",), "other")),
        ("estimation_version", _set(("estimation_version",), "2.0")),
        (
            "software_version",
            _set(("estimation_software_versions", "qiskit"), "999.0.0"),
        ),
    ],
)
def test_every_canonical_execution_field_mutation_invalidates_approval(
    name: str,
    mutate: Mutation,
    planner_bundle: tuple[SubmissionPlanner, RecordingResolver, SubmissionRequest],
    policy: BudgetPolicy,
) -> None:
    planner, _, request = planner_bundle
    plan = planner.resolve(request, policy)
    approval = _approval(plan)
    payload = plan.model_dump(mode="python")
    mutate(payload)
    mutated = SubmissionPlan.model_construct(**payload)

    with pytest.raises(ApprovalError, match="canonical hash"):
        validate_approval(mutated, approval, policy, now=NOW)


def test_live_submit_reresolves_then_requires_bound_receipt(
    planner_bundle: tuple[SubmissionPlanner, RecordingResolver, SubmissionRequest],
    policy: BudgetPolicy,
) -> None:
    planner, resolver, request = planner_bundle
    lifecycle = RecordingLifecycle()
    executor = ApprovedBatchExecutor._from_test_components(  # type: ignore[arg-type]
        planner,
        lifecycle,
        approval_ledger=RecordingApprovalLedger(),
        clock=lambda: NOW,
    )
    dry_run = executor.dry_run(request, policy)
    approval = _approval(dry_run)

    submitted = executor.submit(
        "batch-1",
        request,
        policy,
        approval,
    )

    assert resolver.calls == 2
    assert submitted.plan_hash == dry_run.plan_hash
    assert len(lifecycle.submissions) == 1
    submitted_plan, submitted_limits = lifecycle.submissions[0]
    assert submitted_plan.resolved_options["max_execution_time"] == 60
    assert all(
        partition.maximum_execution_seconds == 60
        for partition in submitted_plan.partitions
    )
    assert submitted_limits.max_execution_seconds_per_job == 60


def _failed_approved_submission(
    *,
    state: Literal["failed", "partial_failure"] = "failed",
    with_job: bool = False,
) -> ApprovedSubmission:
    failure = BatchSubmissionFailure(
        schema_version="1.0",
        partition_id="partition-1",
        error_type="IBMInputValueError",
        message="provider rejected the Sampler job before creation",
        failed_at=NOW,
    )
    receipt = BatchSubmissionReceipt(
        schema_version="1.0",
        submission_key="sampler-key",
        batch_id="batch-1",
        plan_hash=f"sha256:{'a' * 64}",
        pub_ids=("sampler-scalar", "sampler-vector"),
        jobs=(
            (
                BatchJobReceipt(
                    schema_version="1.0",
                    partition_id="partition-1",
                    job_id="job-1",
                    pub_ids=("sampler-scalar",),
                    submitted_at=NOW,
                ),
            )
            if with_job
            else ()
        ),
        state=state,
        reserved_at=NOW,
        completed_at=NOW,
        failure=failure,
    )
    return ApprovedSubmission(
        schema_version="1.0",
        plan_hash=receipt.plan_hash,
        estimated_qpu_seconds=0.096,
        approval_max_qpu_seconds=30,
        receipt=receipt,
    )


def test_failed_submission_stops_before_the_next_primitive(
    planner_bundle: tuple[SubmissionPlanner, RecordingResolver, SubmissionRequest],
    policy: BudgetPolicy,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planner, _, sampler_request = planner_bundle
    executor = ApprovedBatchExecutor._from_test_components(  # type: ignore[arg-type]
        planner,
        RecordingLifecycle(),
        approval_ledger=RecordingApprovalLedger(),
        clock=lambda: NOW,
    )
    approval = _approval(executor.dry_run(sampler_request, policy))
    estimator_request = replace(
        sampler_request,
        plan_id="estimator-plan",
        submission_key="estimator-key",
        primitive="estimator",
    )
    primitive_calls: list[str] = []
    failed = _failed_approved_submission()

    def submit_spy(
        batch_id: str,
        request: SubmissionRequest,
        active_policy: BudgetPolicy,
        active_approval: ApprovalReceipt | None,
    ) -> ApprovedSubmission:
        assert batch_id == "batch-1"
        assert active_policy is policy
        assert active_approval is approval
        primitive_calls.append(request.primitive)
        return failed

    monkeypatch.setattr(executor, "submit", submit_spy)

    with pytest.raises(
        IncompleteSubmissionError, match="state=failed, jobs=0"
    ) as caught:
        executor.submit_in_order(
            "batch-1",
            (
                ApprovedSubmissionStep(sampler_request, policy, approval),
                ApprovedSubmissionStep(estimator_request, policy, approval),
            ),
        )

    assert primitive_calls == ["sampler"]
    assert caught.value.submission is failed
    assert failed.receipt.state == "failed"
    assert failed.receipt.failure is not None
    assert failed.receipt.failure.error_type == "IBMInputValueError"


def test_partial_failure_is_not_fully_submitted() -> None:
    submission = _failed_approved_submission(state="partial_failure", with_job=True)

    with pytest.raises(
        IncompleteSubmissionError, match="state=partial_failure, jobs=1"
    ):
        require_fully_submitted(submission)


def test_successful_submission_guard_preserves_object_identity() -> None:
    receipt = BatchSubmissionReceipt(
        schema_version="1.0",
        submission_key="sampler-key",
        batch_id="batch-1",
        plan_hash=f"sha256:{'a' * 64}",
        pub_ids=("sampler-scalar",),
        jobs=(
            BatchJobReceipt(
                schema_version="1.0",
                partition_id="partition-1",
                job_id="job-1",
                pub_ids=("sampler-scalar",),
                submitted_at=NOW,
            ),
        ),
        state="submitted",
        reserved_at=NOW,
        completed_at=NOW,
    )
    submission = ApprovedSubmission(
        schema_version="1.0",
        plan_hash=receipt.plan_hash,
        estimated_qpu_seconds=0.096,
        approval_max_qpu_seconds=30,
        receipt=receipt,
    )

    assert require_fully_submitted(submission) is submission


def test_submission_sequence_guard_is_publicly_exported() -> None:
    from qiskit_ibm_runtime_mcp_server import core

    assert core.require_fully_submitted is require_fully_submitted
    assert core.ApprovedSubmissionStep is ApprovedSubmissionStep


def test_approved_plan_cannot_be_replayed_under_a_different_submission_key(
    planner_bundle: tuple[SubmissionPlanner, RecordingResolver, SubmissionRequest],
    policy: BudgetPolicy,
) -> None:
    planner, _, request = planner_bundle
    lifecycle = RecordingLifecycle()
    executor = ApprovedBatchExecutor._from_test_components(  # type: ignore[arg-type]
        planner,
        lifecycle,
        approval_ledger=RecordingApprovalLedger(),
        clock=lambda: NOW,
    )
    approval = _approval(executor.dry_run(request, policy))

    with pytest.raises(ApprovalError, match="different plan hash"):
        executor.submit(
            "batch-1",
            replace(request, submission_key="replay-key"),
            policy,
            approval,
        )

    assert lifecycle.submissions == []


def test_consumed_approval_cannot_submit_the_same_plan_twice(
    planner_bundle: tuple[SubmissionPlanner, RecordingResolver, SubmissionRequest],
    policy: BudgetPolicy,
) -> None:
    planner, _, request = planner_bundle
    lifecycle = RecordingLifecycle()
    executor = ApprovedBatchExecutor._from_test_components(  # type: ignore[arg-type]
        planner,
        lifecycle,
        approval_ledger=RecordingApprovalLedger(),
        clock=lambda: NOW,
    )
    approval = _approval(executor.dry_run(request, policy))

    executor.submit("batch-1", request, policy, approval)
    with pytest.raises(ApprovalError, match="already been consumed"):
        executor.submit("batch-1", request, policy, approval)

    assert len(lifecycle.submissions) == 1


@pytest.mark.parametrize(
    ("case", "approval_factory", "match"),
    [
        ("missing", lambda plan: None, "requires an ApprovalReceipt"),
        ("over_budget", lambda plan: _approval(plan, cap=0.05), "approved QPU-second"),
        (
            "expired",
            lambda plan: create_approval_receipt(
                plan,
                approved_at=NOW - timedelta(minutes=10),
                expires_at=NOW - timedelta(minutes=1),
                max_qpu_seconds=10,
                allowed_instance_ids=("crn:test",),
                allowed_backends=("fake_athens",),
            ),
            "expired",
        ),
        (
            "wrong_instance",
            lambda plan: create_approval_receipt(
                plan,
                approved_at=NOW,
                expires_at=NOW + timedelta(minutes=5),
                max_qpu_seconds=10,
                allowed_instance_ids=("crn:other",),
                allowed_backends=("fake_athens",),
            ),
            "instance is not allowed by approval",
        ),
        (
            "wrong_backend",
            lambda plan: create_approval_receipt(
                plan,
                approved_at=NOW,
                expires_at=NOW + timedelta(minutes=5),
                max_qpu_seconds=10,
                allowed_instance_ids=("crn:test",),
                allowed_backends=("other_backend",),
            ),
            "backend is not allowed by approval",
        ),
    ],
)
def test_refusals_never_reach_internal_submission(
    case: str,
    approval_factory: Callable[[SubmissionPlan], ApprovalReceipt | None],
    match: str,
    planner_bundle: tuple[SubmissionPlanner, RecordingResolver, SubmissionRequest],
    policy: BudgetPolicy,
) -> None:
    del case
    planner, _, request = planner_bundle
    lifecycle = RecordingLifecycle()
    executor = ApprovedBatchExecutor._from_test_components(  # type: ignore[arg-type]
        planner,
        lifecycle,
        approval_ledger=RecordingApprovalLedger(),
        clock=lambda: NOW,
    )
    plan = executor.dry_run(request, policy)

    with pytest.raises((ApprovalError, BudgetLimitError), match=match):
        executor.submit(
            "batch-1",
            request,
            policy,
            approval_factory(plan),
        )

    assert lifecycle.submissions == []


def _rehash_plan(plan: SubmissionPlan, **updates: Any) -> SubmissionPlan:
    updated = plan.model_copy(update=updates)
    return updated.model_copy(
        update={"plan_hash": budgeting_module.submission_plan_hash(updated)}
    )


def test_validation_exercises_every_safety_limit_branch(
    planner_bundle: tuple[SubmissionPlanner, RecordingResolver, SubmissionRequest],
    policy: BudgetPolicy,
) -> None:
    """Every policy/plan limit is independently enforced after canonical hashing."""
    planner, _, request = planner_bundle
    original = planner.resolve(request, policy)
    approval = _approval(original)

    with pytest.raises(ApprovalError, match="timezone-aware"):
        validate_approval(original, approval, policy, now=NOW.replace(tzinfo=None))
    with pytest.raises(ApprovalError, match="does not permit"):
        validate_approval(
            original,
            approval,
            policy.model_copy(update={"dry_run": True}),
            now=NOW,
        )
    with pytest.raises(ApprovalError, match="policy hash no longer matches"):
        validate_approval(
            original,
            approval,
            policy.model_copy(update={"max_jobs": policy.max_jobs + 1}),
            now=NOW,
        )

    future = approval.model_copy(
        update={
            "approved_at": NOW + timedelta(minutes=1),
            "expires_at": NOW + timedelta(minutes=2),
        }
    )
    with pytest.raises(ApprovalError, match="in the future"):
        validate_approval(original, future, policy, now=NOW)
    excessive_ttl = approval.model_copy(
        update={"expires_at": NOW + timedelta(seconds=policy.approval_ttl_seconds + 1)}
    )
    with pytest.raises(ApprovalError, match="exceeds policy approval TTL"):
        validate_approval(original, excessive_ttl, policy, now=NOW)

    cases: tuple[tuple[dict[str, Any], dict[str, Any], str], ...] = (
        (
            {"allowed_instance_ids": ("crn:other",)},
            {},
            "instance is not allowed by policy",
        ),
        (
            {"allowed_backends": ("other_backend",)},
            {},
            "backend is not allowed by policy",
        ),
        (
            {"permitted_primitives": ("estimator",)},
            {},
            "primitive is no longer permitted",
        ),
        ({}, {"treatments": ["zne_mitigation"]}, "treatments are no longer permitted"),
        ({"max_pubs": 0}, {}, "max_pubs"),
        ({"max_jobs": 0}, {}, "max_jobs"),
        ({"max_partitions": 0}, {}, "max_partitions"),
        ({"max_circuits": 0}, {}, "max_circuits"),
        ({"max_shots_per_pub": 99}, {}, "max_shots_per_pub"),
        ({"max_estimated_qpu_seconds": 0.05}, {}, "QPU-second limit"),
        ({"max_execution_seconds": 59}, {}, "max_execution_seconds"),
        (
            {},
            {
                "resolved_options": original.resolved_options
                | {"max_execution_time": 59}
            },
            "max_execution_time is not canonical",
        ),
    )
    for policy_updates, plan_updates, message in cases:
        active_policy = policy.model_copy(update=policy_updates)
        active_plan = _rehash_plan(
            original,
            policy_hash=budgeting_module.budget_policy_hash(active_policy),
            **plan_updates,
        )
        active_approval = _approval(active_plan)
        with pytest.raises((ApprovalError, BudgetLimitError), match=message):
            validate_approval(
                active_plan,
                active_approval,
                active_policy,
                now=NOW,
            )


def test_ordered_submission_and_failure_detail_empty_branches(
    planner_bundle: tuple[SubmissionPlanner, RecordingResolver, SubmissionRequest],
) -> None:
    planner, _, _ = planner_bundle
    executor = ApprovedBatchExecutor._from_test_components(  # type: ignore[arg-type]
        planner,
        RecordingLifecycle(),
        approval_ledger=RecordingApprovalLedger(),
        clock=lambda: NOW,
    )
    with pytest.raises(BudgetContractError, match="at least one step"):
        executor.submit_in_order("batch-1", ())

    failed = _failed_approved_submission()
    receipt_without_detail = failed.receipt.model_copy(update={"failure": None})
    submission = failed.model_copy(update={"receipt": receipt_without_detail})
    with pytest.raises(IncompleteSubmissionError, match="no provider failure detail"):
        require_fully_submitted(submission)


def test_paid_instance_is_refused_without_dual_explicit_allowance(
    tmp_path: Any, policy: BudgetPolicy
) -> None:
    sink = LocalArtifactCAS(tmp_path)
    resolver = RecordingResolver(plan_type="paid")
    circuit = QuantumCircuit(5, 5)
    circuit.measure(range(5), range(5))
    isa = generate_preset_pass_manager(
        optimization_level=0, target=resolver.backend.target, seed_transpiler=1
    ).run(circuit)
    artifact = ingest_circuit(_qpy_bytes(isa), circuit_format="qpy", sink=sink).artifact
    request = SubmissionRequest(
        plan_id="paid-plan",
        submission_key="approved-key",
        instance_id="crn:test",
        backend_name="fake_athens",
        primitive="sampler",
        pubs=(
            SamplerPubSpec(
                schema_version="1.0",
                pub_id="paid-pub",
                circuit=artifact,
                parameter_values=None,
                shots=10,
            ),
        ),
        options={},
        maximum_execution_seconds=60,
    )
    planner = SubmissionPlanner(resolver, sink)
    lifecycle = RecordingLifecycle()
    executor = ApprovedBatchExecutor._from_test_components(  # type: ignore[arg-type]
        planner,
        lifecycle,
        approval_ledger=RecordingApprovalLedger(),
        clock=lambda: NOW,
    )
    plan = executor.dry_run(request, policy)
    approval = _approval(plan)

    with pytest.raises(ApprovalError, match="paid Runtime instance"):
        executor.submit(
            "batch-1",
            request,
            policy,
            approval,
        )

    assert lifecycle.submissions == []


def test_usage_reconciliation_returns_actual_per_job_and_aggregate_fields(
    planner_bundle: tuple[SubmissionPlanner, RecordingResolver, SubmissionRequest],
    policy: BudgetPolicy,
) -> None:
    planner, _, request = planner_bundle
    lifecycle = RecordingLifecycle()
    executor = ApprovedBatchExecutor._from_test_components(  # type: ignore[arg-type]
        planner,
        lifecycle,
        approval_ledger=RecordingApprovalLedger(),
        clock=lambda: NOW,
    )
    plan = executor.dry_run(request, policy)
    approval = _approval(plan)
    submission = executor.submit("batch-1", request, policy, approval)

    usage = executor.reconcile_usage(submission)

    assert usage.estimated_qpu_seconds == pytest.approx(0.1)
    assert usage.approval_max_qpu_seconds == 10
    assert usage.actual_qpu_seconds == 1.5
    assert len(usage.batch_usage.jobs) == 1
    assert usage.batch_usage.jobs[0].quantum_seconds == 1.5
