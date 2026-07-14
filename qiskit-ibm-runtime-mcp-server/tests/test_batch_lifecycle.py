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

"""Fully mocked W1-07 Batch lifecycle and idempotency contract tests."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import pytest
from pydantic import ValidationError
from qiskit import QuantumCircuit, qpy
from qiskit.providers import JobStatus

from qiskit_ibm_runtime_mcp_server.core import (
    BatchContractError,
    BatchExecutionLimits,
    BatchLifecycle,
    BatchLimitError,
    BatchRecoveryError,
    DuplicateSubmissionError,
    EstimatorPubSpec,
    LocalArtifactCAS,
    PauliObservables,
    PubExecutionEstimate,
    PubShape,
    SamplerPubSpec,
    ScheduledPubEstimate,
    SubmissionPlan,
    SubmissionReceiptRegistry,
    ingest_circuit,
    plan_batch_partitions,
    submission_plan_hash,
)


NOW = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
PLAN_HASH = f"sha256:{'7' * 64}"
PLAN_TAG = f"qiskit-mcp-plan:{'7' * 64}"


def _limits(**overrides: Any) -> BatchExecutionLimits:
    values: dict[str, Any] = {
        "schema_version": "1.0",
        "max_jobs": 4,
        "max_pubs_per_job": 2,
        "max_estimated_qpu_seconds_per_job": 3,
        "max_execution_seconds_per_job": 5,
        "batch_max_time_seconds": 10,
        "ttl_margin_seconds": 1,
    }
    values.update(overrides)
    return BatchExecutionLimits(**values)


def _estimates(values: Sequence[tuple[str, float]]) -> list[PubExecutionEstimate]:
    return [
        PubExecutionEstimate(
            schema_version="1.0", pub_id=pub_id, estimated_qpu_seconds=seconds
        )
        for pub_id, seconds in values
    ]


def _artifact(sink: LocalArtifactCAS, *, measured: bool = True):
    circuit = QuantumCircuit(2)
    circuit.h(0)
    circuit.cx(0, 1)
    if measured:
        circuit.measure_all()
    payload = io.BytesIO()
    qpy.dump(circuit, payload)
    return ingest_circuit(payload.getvalue(), circuit_format="qpy", sink=sink).artifact


def _plan(
    sink: LocalArtifactCAS,
    limits: BatchExecutionLimits,
    values: Sequence[tuple[str, float]] = (("pub-a", 1), ("pub-b", 2), ("pub-c", 1)),
) -> SubmissionPlan:
    artifact = _artifact(sink)
    pubs = [
        SamplerPubSpec(
            schema_version="1.0",
            pub_id=pub_id,
            circuit=artifact,
            parameter_values=None,
            shots=16,
        )
        for pub_id, _ in values
    ]
    partitions = plan_batch_partitions(_estimates(values), limits)
    return SubmissionPlan(
        schema_version="1.0",
        plan_id="plan-batch-lifecycle",
        submission_key="batch-lifecycle-key",
        plan_hash=PLAN_HASH,
        policy_hash=f"sha256:{'6' * 64}",
        instance_id="crn:test",
        instance_plan_type="open",
        backend_name="ibm_test",
        target_hash=f"sha256:{'5' * 64}",
        compiler_target_hash=f"sha256:{'4' * 64}",
        primitive="sampler",
        pubs=pubs,
        pub_shapes=[
            PubShape(
                schema_version="1.0",
                pub_id=pub_id,
                parameter_shape=[],
                observable_shape=None,
                result_shape=[],
                circuit_executions=1,
            )
            for pub_id, _ in values
        ],
        resolved_options={
            "max_execution_time": limits.max_execution_seconds_per_job,
            "environment": {"job_tags": ["caller-tag"]},
        },
        treatments=[],
        partitions=list(partitions),
        scheduled_estimates=[
            ScheduledPubEstimate(
                schema_version="1.0",
                pub_id=pub_id,
                scheduled_circuit_seconds=0.001,
                conservative_cycle_seconds=0.001,
                circuit_executions=1,
                physical_circuit_executions=1,
                repetitions_per_execution=16,
                treatment_multiplier=1,
                estimated_qpu_seconds=seconds,
            )
            for pub_id, seconds in values
        ],
        total_circuit_executions=len(values),
        estimated_qpu_seconds=sum(seconds for _, seconds in values),
        maximum_execution_seconds=limits.max_execution_seconds_per_job,
        estimation_method="fixture",
        estimation_version="1.0",
        estimation_software_versions={"qiskit": "2.4.2"},
    )


def _estimator_plan(
    sink: LocalArtifactCAS, limits: BatchExecutionLimits
) -> SubmissionPlan:
    pub = EstimatorPubSpec(
        schema_version="1.0",
        pub_id="estimator-a",
        circuit=_artifact(sink, measured=False),
        observables=PauliObservables(
            schema_version="1.0",
            kind="pauli_observables",
            shape=[1],
            values=["ZZ"],
        ),
        parameter_values=None,
        precision=0.1,
    )
    partitions = plan_batch_partitions(_estimates((("estimator-a", 1),)), limits)
    return SubmissionPlan(
        schema_version="1.0",
        plan_id="plan-batch-estimator",
        submission_key="batch-estimator-key",
        plan_hash=PLAN_HASH,
        policy_hash=f"sha256:{'6' * 64}",
        instance_id="crn:test",
        instance_plan_type="open",
        backend_name="ibm_test",
        target_hash=f"sha256:{'5' * 64}",
        compiler_target_hash=f"sha256:{'4' * 64}",
        primitive="estimator",
        pubs=[pub],
        pub_shapes=[
            PubShape(
                schema_version="1.0",
                pub_id=pub.pub_id,
                parameter_shape=[],
                observable_shape=[1],
                result_shape=[1],
                circuit_executions=1,
            )
        ],
        resolved_options={"max_execution_time": limits.max_execution_seconds_per_job},
        treatments=[],
        partitions=list(partitions),
        scheduled_estimates=[
            ScheduledPubEstimate(
                schema_version="1.0",
                pub_id=pub.pub_id,
                scheduled_circuit_seconds=0.001,
                conservative_cycle_seconds=0.001,
                circuit_executions=1,
                physical_circuit_executions=1,
                repetitions_per_execution=100,
                treatment_multiplier=1,
                estimated_qpu_seconds=1,
            )
        ],
        total_circuit_executions=1,
        estimated_qpu_seconds=1,
        maximum_execution_seconds=limits.max_execution_seconds_per_job,
        estimation_method="fixture",
        estimation_version="1.0",
        estimation_software_versions={"qiskit": "2.4.2"},
    )


class FakeBackend:
    name = "ibm_test"


class FakeBatch:
    def __init__(self, batch_id: str = "batch-1", backend_name: str = "ibm_test"):
        self._batch_id = batch_id
        self._backend_name = backend_name
        self._closed = False
        self.max_time: int | None = 10

    @property
    def session_id(self) -> str:
        return self._batch_id

    def backend(self) -> str:
        return self._backend_name

    def close(self) -> None:
        self._closed = True

    def status(self) -> str:
        return (
            "In progress, not accepting new jobs"
            if self._closed
            else "In progress, accepting new jobs"
        )

    def details(self) -> dict[str, Any]:
        return {
            "id": self._batch_id,
            "backend_name": self._backend_name,
            "max_time": self.max_time,
            "interactive_timeout": 60,
            "accepting_jobs": not self._closed,
            "started_at": "2026-07-13T11:59:00Z",
            "closed_at": "2026-07-13T12:01:00Z" if self._closed else None,
        }

    def usage(self) -> float:
        return 3.0


class FakeJob:
    def __init__(
        self,
        job_id: str,
        *,
        status: Any = "RUNNING",
        seconds: float = 1.0,
        tags: Sequence[str] = (),
        session_id: str = "batch-1",
    ) -> None:
        self._job_id = job_id
        self._status = status
        self._seconds = seconds
        self.tags = list(tags)
        self.session_id = session_id
        self.creation_date = "2026-07-13T12:00:00Z"

    def job_id(self) -> str:
        return self._job_id

    def status(self) -> Any:
        return self._status

    def metrics(self) -> dict[str, Any]:
        return {"usage": {"quantum_seconds": self._seconds}}


class FakeService:
    def __init__(self) -> None:
        self.backend_calls: list[tuple[str, str]] = []
        self.jobs_calls: list[dict[str, Any]] = []
        self.batch_jobs: list[FakeJob] = []
        self.tagged_jobs: list[FakeJob] = []
        self.jobs_by_id: dict[str, FakeJob] = {}
        self.active_instance_id = "crn:test"

    def backend(self, name: str, *, instance: str) -> FakeBackend:
        self.backend_calls.append((name, instance))
        return FakeBackend()

    def jobs(self, **kwargs: Any) -> Sequence[FakeJob]:
        self.jobs_calls.append(kwargs)
        if kwargs.get("job_tags") is not None:
            return list(self.tagged_jobs)
        return list(self.batch_jobs)

    def job(self, job_id: str) -> FakeJob:
        return self.jobs_by_id[job_id]

    def active_instance(self) -> str:
        return self.active_instance_id


class RecordingPrimitiveFactory:
    def __init__(self, *, fail_call: int | None = None) -> None:
        self.fail_call = fail_call
        self.options: list[dict[str, Any]] = []
        self.run_calls: list[list[Any]] = []
        self.jobs: list[FakeJob] = []
        self.primitives: list[str] = []

    def __call__(self, primitive: str, batch: FakeBatch, options: dict[str, Any]):
        assert batch.session_id == "batch-1"
        self.primitives.append(primitive)
        self.options.append(options)
        owner = self

        class Runner:
            def run(self, pubs: Sequence[Any]) -> FakeJob:
                owner.run_calls.append(list(pubs))
                call_number = len(owner.run_calls)
                if owner.fail_call == call_number:
                    raise RuntimeError("synthetic second-partition failure")
                job = FakeJob(
                    f"job-{call_number}",
                    tags=options["environment"]["job_tags"],
                    session_id=batch.session_id,
                )
                owner.jobs.append(job)
                return job

        return Runner()


def _lifecycle(
    tmp_path: Path,
    *,
    service: FakeService | None = None,
    batch: FakeBatch | None = None,
    primitive_factory: RecordingPrimitiveFactory | None = None,
) -> tuple[
    BatchLifecycle,
    FakeService,
    FakeBatch,
    RecordingPrimitiveFactory,
    LocalArtifactCAS,
    list[tuple[Any, int]],
]:
    fake_service = service or FakeService()
    fake_batch = batch or FakeBatch()
    fake_primitive_factory = primitive_factory or RecordingPrimitiveFactory()
    sink = LocalArtifactCAS(tmp_path / "cas")
    create_calls: list[tuple[Any, int]] = []

    def create_batch(backend: Any, max_time: int) -> FakeBatch:
        create_calls.append((backend, max_time))
        fake_batch.max_time = max_time
        return fake_batch

    lifecycle = BatchLifecycle(
        fake_service,
        instance_id="crn:test",
        sink=sink,
        batch_factory=create_batch,
        batch_open_factory=lambda batch_id, runtime: fake_batch,
        primitive_factory=fake_primitive_factory,
        receipt_registry=SubmissionReceiptRegistry(),
        clock=lambda: NOW,
    )
    return (
        lifecycle,
        fake_service,
        fake_batch,
        fake_primitive_factory,
        sink,
        create_calls,
    )


def test_partition_planner_is_deterministic_and_honors_pub_and_time_limits() -> None:
    limits = _limits()
    estimates = _estimates((("pub-a", 1), ("pub-b", 2), ("pub-c", 1), ("pub-d", 2)))

    first = plan_batch_partitions(estimates, limits)
    second = plan_batch_partitions(estimates, limits)

    assert first == second
    assert [partition.pub_ids for partition in first] == [
        ["pub-a", "pub-b"],
        ["pub-c", "pub-d"],
    ]
    assert [partition.estimated_qpu_seconds for partition in first] == [3, 3]
    assert all(partition.maximum_execution_seconds == 5 for partition in first)

    execution_limited = plan_batch_partitions(
        _estimates((("pub-a", 3), ("pub-b", 3))),
        _limits(
            max_estimated_qpu_seconds_per_job=8,
            max_execution_seconds_per_job=5,
        ),
    )
    assert [partition.pub_ids for partition in execution_limited] == [
        ["pub-a"],
        ["pub-b"],
    ]


@pytest.mark.parametrize(
    ("limits", "estimates", "message"),
    [
        (_limits(max_jobs=1, max_pubs_per_job=1), (("a", 1), ("b", 1)), "max_jobs"),
        (_limits(), (("a", 4),), "per-job estimated-time"),
        (
            _limits(
                max_estimated_qpu_seconds_per_job=8,
                max_execution_seconds_per_job=5,
            ),
            (("a", 6),),
            "execution-time",
        ),
        (
            _limits(
                batch_max_time_seconds=5,
                ttl_margin_seconds=1,
                max_execution_seconds_per_job=4,
            ),
            (("a", 3), ("b", 2)),
            "TTL",
        ),
    ],
)
def test_partition_planner_rejects_every_configured_limit(
    limits: BatchExecutionLimits,
    estimates: Sequence[tuple[str, float]],
    message: str,
) -> None:
    with pytest.raises(BatchLimitError, match=message):
        plan_batch_partitions(_estimates(estimates), limits)


def test_locked_runtime_ceilings_and_ttl_margin_are_model_invariants() -> None:
    with pytest.raises(ValidationError, match="three-hour"):
        _limits(
            max_execution_seconds_per_job=10_801,
            batch_max_time_seconds=20_000,
        )
    with pytest.raises(ValidationError, match="eight-hour"):
        _limits(batch_max_time_seconds=28_801)
    with pytest.raises(ValidationError, match="positive usable Batch TTL"):
        _limits(ttl_margin_seconds=10)


def test_create_open_close_status_jobs_and_usage_are_typed_and_filtered(
    tmp_path: Path,
) -> None:
    lifecycle, service, batch, _, _, create_calls = _lifecycle(tmp_path)
    limits = _limits()
    jobs = [
        FakeJob("job-1", status="DONE", seconds=1.25, tags=["a"]),
        FakeJob("job-2", status="RUNNING", seconds=1.75, tags=["b"]),
    ]
    service.batch_jobs = jobs

    reference = lifecycle.create_batch("ibm_test", limits)
    status = lifecycle.batch_status(reference.batch_id)
    listed = lifecycle.list_batch_jobs(reference.batch_id)
    usage = lifecycle.batch_usage(reference.batch_id)
    closed = lifecycle.close_batch(reference.batch_id)

    assert reference.batch_id == "batch-1"
    assert reference.instance_id == "crn:test"
    assert len(create_calls) == 1
    assert create_calls[0][1] == 10
    assert service.backend_calls == [("ibm_test", "crn:test")]
    assert status.interactive_timeout_seconds == 60
    assert [job.job_id for job in listed] == ["job-1", "job-2"]
    assert usage.batch_seconds == 3
    assert [job.quantum_seconds for job in usage.jobs] == [1.25, 1.75]
    assert closed.accepting_jobs is False
    assert batch._closed is True
    assert any(call.get("session_id") == "batch-1" for call in service.jobs_calls)


def test_create_batch_records_a_lower_provider_effective_ttl(tmp_path: Path) -> None:
    service = FakeService()
    batch = FakeBatch()
    batch.max_time = 6
    sink = LocalArtifactCAS(tmp_path / "cas")
    lifecycle = BatchLifecycle(
        service,
        instance_id="crn:test",
        sink=sink,
        batch_factory=lambda backend, max_time: batch,
        batch_open_factory=lambda batch_id, runtime: batch,
        primitive_factory=RecordingPrimitiveFactory(),
        receipt_registry=SubmissionReceiptRegistry(),
        clock=lambda: NOW,
    )

    reference = lifecycle.create_batch("ibm_test", _limits())

    assert reference.maximum_time_seconds == 6


def test_open_batch_reattaches_and_verifies_backend_identity(tmp_path: Path) -> None:
    lifecycle, _, _, _, _, create_calls = _lifecycle(tmp_path)

    reference = lifecycle.open_batch("batch-1", expected_backend_name="ibm_test")

    assert reference.batch_id == "batch-1"
    assert reference.backend_name == "ibm_test"
    assert reference.maximum_time_seconds == 10
    assert create_calls == []
    with pytest.raises(BatchContractError, match="expected_backend_name"):
        lifecycle.open_batch("batch-1", expected_backend_name="ibm_other")


def test_open_batch_rejects_cross_instance_reattachment(tmp_path: Path) -> None:
    service = FakeService()
    service.active_instance_id = "crn:other"
    lifecycle, _, _, _, _, _ = _lifecycle(tmp_path, service=service)

    with pytest.raises(BatchContractError, match="different active instance"):
        lifecycle.open_batch("batch-1", expected_backend_name="ibm_test")


def test_open_batch_rejects_unknown_provider_effective_ttl(tmp_path: Path) -> None:
    batch = FakeBatch()
    batch.max_time = None
    lifecycle, _, _, _, _, _ = _lifecycle(tmp_path, batch=batch)

    with pytest.raises(BatchContractError, match="positive effective maximum TTL"):
        lifecycle.open_batch("batch-1", expected_backend_name="ibm_test")


def test_reattached_lower_effective_ttl_rebounds_submission(tmp_path: Path) -> None:
    batch = FakeBatch()
    batch.max_time = 6
    lifecycle, _, _, primitive_factory, sink, _ = _lifecycle(tmp_path, batch=batch)
    limits = _limits()
    plan = _plan(sink, limits)
    plan.submission_key = "lower-effective-ttl"
    reference = lifecycle.open_batch("batch-1", expected_backend_name="ibm_test")

    receipt = lifecycle._submit_resolved_plan(
        reference.batch_id,
        plan,
        submission_key="lower-effective-ttl",
        limits=limits,
    )

    assert reference.maximum_time_seconds == 6
    assert receipt.state == "submitted"
    assert len(primitive_factory.run_calls) == 2
    oversized = _plan(sink, limits, (("pub-x", 3), ("pub-y", 3)))
    oversized.submission_key = "too-large-for-effective-ttl"
    with pytest.raises(BatchLimitError, match="effective Batch TTL"):
        lifecycle._submit_resolved_plan(
            reference.batch_id,
            oversized,
            submission_key="too-large-for-effective-ttl",
            limits=limits,
        )


def test_submission_returns_immutable_complete_receipt_and_enforced_tags(
    tmp_path: Path,
) -> None:
    lifecycle, _, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    plan = _plan(sink, limits)
    plan.submission_key = "submission-001"
    lifecycle.create_batch("ibm_test", limits)

    receipt = lifecycle._submit_resolved_plan(
        "batch-1",
        plan,
        submission_key="submission-001",
        limits=limits,
    )

    assert receipt.state == "submitted"
    assert receipt.batch_id == "batch-1"
    assert receipt.plan_hash == PLAN_HASH
    assert receipt.pub_ids == ("pub-a", "pub-b", "pub-c")
    assert [job.job_id for job in receipt.jobs] == ["job-1", "job-2"]
    assert receipt.reserved_at == NOW == receipt.completed_at
    assert [len(call) for call in primitive_factory.run_calls] == [2, 1]
    assert all(
        options["max_execution_time"] == 5 for options in primitive_factory.options
    )
    assert all(
        any(
            tag.startswith("qiskit-mcp-idempotency:")
            for tag in options["environment"]["job_tags"]
        )
        for options in primitive_factory.options
    )
    assert all(
        all(len(tag) <= 86 for tag in options["environment"]["job_tags"])
        for options in primitive_factory.options
    )
    assert all(
        len(
            next(
                tag
                for tag in options["environment"]["job_tags"]
                if tag.startswith("qiskit-mcp-idempotency:")
            )
        )
        == 86
        for options in primitive_factory.options
    )
    assert all(
        "caller-tag" in options["environment"]["job_tags"]
        for options in primitive_factory.options
    )
    assert all(
        any(
            tag == "qiskit-mcp-attempted-at:20260713T120000.000000Z"
            for tag in options["environment"]["job_tags"]
        )
        for options in primitive_factory.options
    )
    with pytest.raises(ValidationError, match="frozen"):
        receipt.state = "failed"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="frozen"):
        receipt.jobs[0].job_id = "changed"  # type: ignore[misc]


def test_submission_rejects_oversized_caller_job_tag_before_primitive_run(
    tmp_path: Path,
) -> None:
    lifecycle, _, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    plan = _plan(sink, limits)
    plan.submission_key = "oversized-caller-tag"
    plan.resolved_options["environment"] = {"job_tags": ["x" * 87]}
    lifecycle.create_batch("ibm_test", limits)

    receipt = lifecycle._submit_resolved_plan(
        "batch-1",
        plan,
        submission_key="oversized-caller-tag",
        limits=limits,
    )

    assert receipt.state == "failed"
    assert receipt.jobs == ()
    assert receipt.failure is not None
    assert receipt.failure.error_type == "BatchContractError"
    assert "must not exceed 86 characters" in receipt.failure.message
    assert primitive_factory.run_calls == []


def test_submission_rejects_caller_spoofing_reserved_recovery_tags(
    tmp_path: Path,
) -> None:
    lifecycle, _, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    plan = _plan(sink, limits)
    plan.submission_key = "reserved-tag-spoof"
    plan.resolved_options["environment"] = {
        "job_tags": ["qiskit-mcp-attempted-at:spoofed"]
    }
    lifecycle.create_batch("ibm_test", limits)

    receipt = lifecycle._submit_resolved_plan(
        "batch-1",
        plan,
        submission_key="reserved-tag-spoof",
        limits=limits,
    )

    assert receipt.state == "failed"
    assert receipt.failure is not None
    assert "reserved qiskit-mcp- namespace" in receipt.failure.message
    assert primitive_factory.run_calls == []


def test_submission_key_must_match_the_plan_before_remote_lookup(
    tmp_path: Path,
) -> None:
    lifecycle, service, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    plan = _plan(sink, _limits())

    with pytest.raises(BatchContractError, match="exactly match"):
        lifecycle._submit_resolved_plan(
            "batch-1",
            plan,
            submission_key="not-the-plan-key",
            limits=_limits(),
        )

    assert service.jobs_calls == []
    assert primitive_factory.run_calls == []


def test_submission_enforces_the_provider_eight_tag_limit(tmp_path: Path) -> None:
    lifecycle, _, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    lifecycle.create_batch("ibm_test", limits)
    allowed = _plan(sink, limits, (("pub-a", 1),))
    allowed.submission_key = "four-caller-tags"
    allowed.resolved_options["environment"] = {
        "job_tags": [f"caller-{index}" for index in range(4)]
    }

    accepted = lifecycle._submit_resolved_plan(
        "batch-1", allowed, submission_key=allowed.submission_key, limits=limits
    )

    assert accepted.state == "submitted"
    assert len(primitive_factory.options[0]["environment"]["job_tags"]) == 8

    rejected = _plan(sink, limits, (("pub-b", 1),))
    rejected.submission_key = "five-caller-tags"
    rejected.resolved_options["environment"] = {
        "job_tags": [f"caller-{index}" for index in range(5)]
    }
    failed = lifecycle._submit_resolved_plan(
        "batch-1", rejected, submission_key=rejected.submission_key, limits=limits
    )

    assert failed.state == "failed"
    assert failed.failure is not None
    assert "no more than 8 items" in failed.failure.message
    assert len(primitive_factory.run_calls) == 1


def test_estimator_partitions_use_the_same_batch_receipt_contract(
    tmp_path: Path,
) -> None:
    lifecycle, _, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    lifecycle.create_batch("ibm_test", limits)
    plan = _estimator_plan(sink, limits)
    plan.submission_key = "estimator-key"

    receipt = lifecycle._submit_resolved_plan(
        "batch-1",
        plan,
        submission_key="estimator-key",
        limits=limits,
    )

    assert receipt.state == "submitted"
    assert receipt.pub_ids == ("estimator-a",)
    assert primitive_factory.primitives == ["estimator"]
    assert len(primitive_factory.run_calls) == 1


def test_duplicate_submission_key_is_refused_before_a_second_primitive_call(
    tmp_path: Path,
) -> None:
    lifecycle, _, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    plan = _plan(sink, limits)
    plan.submission_key = "duplicate-key"
    lifecycle.create_batch("ibm_test", limits)
    first = lifecycle._submit_resolved_plan(
        "batch-1", plan, submission_key="duplicate-key", limits=limits
    )

    with pytest.raises(DuplicateSubmissionError, match="no second live submission"):
        lifecycle._submit_resolved_plan(
            "batch-1", plan, submission_key="duplicate-key", limits=limits
        )

    assert first.state == "submitted"
    assert len(primitive_factory.run_calls) == 2
    assert lifecycle.receipt("duplicate-key") == first


def test_in_flight_reservation_is_atomic_and_plan_bound() -> None:
    registry = SubmissionReceiptRegistry()
    registry.reserve(
        "in-flight-key", PLAN_HASH, policy="reject", existing_is_terminal=False
    )

    with pytest.raises(DuplicateSubmissionError, match="already reserved"):
        registry.reserve(
            "in-flight-key", PLAN_HASH, policy="reject", existing_is_terminal=False
        )
    with pytest.raises(DuplicateSubmissionError, match="different plan_hash"):
        registry.reserve(
            "in-flight-key",
            f"sha256:{'8' * 64}",
            policy="allow_live",
            existing_is_terminal=False,
        )


def test_remote_live_duplicate_is_refused_after_local_registry_loss(
    tmp_path: Path,
) -> None:
    service = FakeService()
    service.tagged_jobs = [FakeJob("remote-live", status="RUNNING")]
    lifecycle, _, _, primitive_factory, sink, _ = _lifecycle(tmp_path, service=service)
    limits = _limits()
    plan = _plan(sink, limits)
    plan.submission_key = "restart-key"
    lifecycle.create_batch("ibm_test", limits)

    with pytest.raises(DuplicateSubmissionError, match="remote jobs"):
        lifecycle._submit_resolved_plan(
            "batch-1", plan, submission_key="restart-key", limits=limits
        )

    assert primitive_factory.run_calls == []


def test_explicit_allow_live_policy_is_the_only_live_duplicate_override(
    tmp_path: Path,
) -> None:
    lifecycle, _, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    plan = _plan(sink, limits, (("pub-a", 1),))
    plan.submission_key = "override-key"
    lifecycle.create_batch("ibm_test", limits)
    lifecycle._submit_resolved_plan(
        "batch-1", plan, submission_key="override-key", limits=limits
    )

    second = lifecycle._submit_resolved_plan(
        "batch-1",
        plan,
        submission_key="override-key",
        limits=limits,
        duplicate_policy="allow_live",
    )

    assert second.state == "submitted"
    assert len(primitive_factory.run_calls) == 2


def test_allow_if_terminal_accepts_real_locked_job_status_enums(
    tmp_path: Path,
) -> None:
    lifecycle, service, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    plan = _plan(sink, limits, (("pub-a", 1),))
    plan.submission_key = "terminal-key"
    lifecycle.create_batch("ibm_test", limits)
    first = lifecycle._submit_resolved_plan(
        "batch-1", plan, submission_key="terminal-key", limits=limits
    )
    first_job = primitive_factory.jobs[0]
    first_job._status = JobStatus.DONE
    service.jobs_by_id[first.jobs[0].job_id] = first_job

    second = lifecycle._submit_resolved_plan(
        "batch-1",
        plan,
        submission_key="terminal-key",
        limits=limits,
        duplicate_policy="allow_if_terminal",
    )

    assert second.state == "submitted"
    assert len(primitive_factory.run_calls) == 2


@pytest.mark.parametrize(
    "status",
    [JobStatus.DONE, JobStatus.ERROR, JobStatus.CANCELLED],
)
def test_remote_terminal_enum_allows_explicit_terminal_override(
    tmp_path: Path, status: JobStatus
) -> None:
    service = FakeService()
    service.tagged_jobs = [FakeJob("remote-terminal", status=status, tags=[PLAN_TAG])]
    lifecycle, _, _, primitive_factory, sink, _ = _lifecycle(tmp_path, service=service)
    limits = _limits()
    plan = _plan(sink, limits, (("pub-a", 1),))
    plan.submission_key = f"terminal-{status.name.lower()}"
    lifecycle.create_batch("ibm_test", limits)

    receipt = lifecycle._submit_resolved_plan(
        "batch-1",
        plan,
        submission_key=f"terminal-{status.name.lower()}",
        limits=limits,
        duplicate_policy="allow_if_terminal",
    )

    assert receipt.state == "submitted"
    assert len(primitive_factory.run_calls) == 1


def test_real_job_status_enums_are_recovered_as_canonical_names(
    tmp_path: Path,
) -> None:
    lifecycle, service, _, _, _, _ = _lifecycle(tmp_path)
    lifecycle.create_batch("ibm_test", _limits())
    service.batch_jobs = [
        FakeJob("done", status=JobStatus.DONE),
        FakeJob("running", status=JobStatus.RUNNING),
    ]

    jobs = lifecycle.list_batch_jobs("batch-1")

    assert [job.status for job in jobs] == ["DONE", "RUNNING"]


def test_partial_failure_receipt_and_status_recovery_preserve_accepted_jobs(
    tmp_path: Path,
) -> None:
    primitive_factory = RecordingPrimitiveFactory(fail_call=2)
    lifecycle, service, batch, _, sink, _ = _lifecycle(
        tmp_path, primitive_factory=primitive_factory
    )
    limits = _limits()
    plan = _plan(sink, limits)
    plan.submission_key = "partial-key"
    lifecycle.create_batch("ibm_test", limits)

    receipt = lifecycle._submit_resolved_plan(
        "batch-1", plan, submission_key="partial-key", limits=limits
    )
    accepted = primitive_factory.jobs[0]
    accepted._status = "DONE"
    service.jobs_by_id[accepted.job_id()] = accepted

    recovered = lifecycle.recover_submission(receipt)

    assert receipt.state == "partial_failure"
    assert [job.job_id for job in receipt.jobs] == ["job-1"]
    assert receipt.failure is not None
    assert receipt.failure.partition_id == plan.partitions[1].partition_id
    assert receipt.failure.error_type == "RuntimeError"
    assert recovered.receipt == receipt
    assert recovered.jobs[0].status == "DONE"
    assert recovered.batch.batch_id == batch.session_id


def test_crash_recovery_returns_plan_bound_receipts_without_local_state(
    tmp_path: Path,
) -> None:
    lifecycle, service, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    plan = _plan(sink, limits)
    plan.submission_key = "lost-receipt-key"
    plan.plan_hash = submission_plan_hash(plan)
    lifecycle.create_batch("ibm_test", limits)
    receipt = lifecycle._submit_resolved_plan(
        "batch-1", plan, submission_key=plan.submission_key, limits=limits
    )
    primitive_factory.jobs[1].creation_date = None
    service.tagged_jobs = list(reversed(primitive_factory.jobs))
    restarted, _, _, _, _, _ = _lifecycle(tmp_path, service=service)

    recovered = restarted.recover_jobs_by_submission_key("lost-receipt-key", plan)

    assert recovered.submission_key == "lost-receipt-key"
    assert recovered.plan_id == plan.plan_id
    assert recovered.plan_hash == plan.plan_hash
    assert recovered.primitive == "sampler"
    assert recovered.batch_id == "batch-1"
    assert recovered.state == "complete"
    assert recovered.missing_partition_ids == ()
    assert [
        (job.partition_id, job.job_id, job.pub_ids, job.submitted_at)
        for job in recovered.jobs
    ] == [
        (
            plan.partitions[0].partition_id,
            "job-1",
            tuple(plan.partitions[0].pub_ids),
            receipt.jobs[0].submitted_at,
        ),
        (
            plan.partitions[1].partition_id,
            "job-2",
            tuple(plan.partitions[1].pub_ids),
            receipt.jobs[1].submitted_at,
        ),
    ]
    assert all(
        job.submission_time_source == "wrapper_pre_submit_job_tag"
        for job in recovered.jobs
    )
    assert [job.provider_created_at for job in recovered.jobs] == [NOW, None]
    assert all(job.status == "RUNNING" for job in recovered.jobs)


def test_crash_recovery_reports_a_typed_partition_prefix(tmp_path: Path) -> None:
    lifecycle, service, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    plan = _plan(sink, limits)
    plan.submission_key = "partial-recovery-key"
    plan.plan_hash = submission_plan_hash(plan)
    lifecycle.create_batch("ibm_test", limits)
    lifecycle._submit_resolved_plan(
        "batch-1", plan, submission_key=plan.submission_key, limits=limits
    )
    service.tagged_jobs = primitive_factory.jobs[:1]

    recovered = lifecycle.recover_jobs_by_submission_key(plan.submission_key, plan)

    assert recovered.state == "partial"
    assert [job.partition_id for job in recovered.jobs] == [
        plan.partitions[0].partition_id
    ]
    assert recovered.missing_partition_ids == (plan.partitions[1].partition_id,)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda tags, plan: [
                tag for tag in tags if not tag.startswith("qiskit-mcp-attempted-at:")
            ],
            "submission-attempt tag",
        ),
        (
            lambda tags, plan: [
                "qiskit-mcp-attempted-at:not-a-timestamp"
                if tag.startswith("qiskit-mcp-attempted-at:")
                else tag
                for tag in tags
            ],
            "invalid wrapper submission-attempt tag",
        ),
        (
            lambda tags, plan: [
                f"qiskit-mcp-plan:{'8' * 64}"
                if tag.startswith("qiskit-mcp-plan:")
                else tag
                for tag in tags
            ],
            "canonical SubmissionPlan",
        ),
        (
            lambda tags, plan: [*tags, f"qiskit-mcp-plan:{'8' * 64}"],
            "bound only to the canonical SubmissionPlan",
        ),
        (
            lambda tags, plan: [
                "qiskit-mcp-partition:not-in-plan"
                if tag.startswith("qiskit-mcp-partition:")
                else tag
                for tag in tags
            ],
            "not present",
        ),
    ],
)
def test_crash_recovery_fails_closed_on_untrusted_remote_identity(
    tmp_path: Path,
    mutate: Any,
    message: str,
) -> None:
    lifecycle, service, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    plan = _plan(sink, limits, (("pub-a", 1),))
    plan.submission_key = "untrusted-recovery-key"
    plan.plan_hash = submission_plan_hash(plan)
    lifecycle.create_batch("ibm_test", limits)
    lifecycle._submit_resolved_plan(
        "batch-1", plan, submission_key=plan.submission_key, limits=limits
    )
    job = primitive_factory.jobs[0]
    job.tags = mutate(job.tags, plan)
    service.tagged_jobs = [job]

    with pytest.raises(BatchRecoveryError, match=message):
        lifecycle.recover_jobs_by_submission_key(plan.submission_key, plan)


def test_crash_recovery_rejects_a_mutated_or_mismatched_plan(tmp_path: Path) -> None:
    lifecycle, _, _, _, sink, _ = _lifecycle(tmp_path)
    plan = _plan(sink, _limits(), (("pub-a", 1),))
    plan.submission_key = "canonical-recovery-key"
    plan.plan_hash = submission_plan_hash(plan)
    plan.plan_id = "mutated-after-hash"

    with pytest.raises(BatchRecoveryError, match="canonical hash"):
        lifecycle.recover_jobs_by_submission_key(plan.submission_key, plan)

    plan.plan_id = "plan-batch-lifecycle"
    plan.plan_hash = submission_plan_hash(plan)
    with pytest.raises(BatchRecoveryError, match="does not match the recovery key"):
        lifecycle.recover_jobs_by_submission_key("different-key", plan)


def test_crash_recovery_not_found_is_typed(tmp_path: Path) -> None:
    lifecycle, _, _, _, sink, _ = _lifecycle(tmp_path)
    plan = _plan(sink, _limits(), (("pub-a", 1),))
    plan.plan_hash = submission_plan_hash(plan)

    recovered = lifecycle.recover_jobs_by_submission_key(plan.submission_key, plan)

    assert recovered.state == "not_found"
    assert recovered.batch_id is None
    assert recovered.jobs == ()
    assert recovered.missing_partition_ids == (plan.partitions[0].partition_id,)


def test_crash_recovery_rejects_partition_gaps_duplicates_and_batch_drift(
    tmp_path: Path,
) -> None:
    lifecycle, service, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    plan = _plan(sink, limits)
    plan.plan_hash = submission_plan_hash(plan)
    lifecycle.create_batch("ibm_test", limits)
    lifecycle._submit_resolved_plan(
        "batch-1", plan, submission_key=plan.submission_key, limits=limits
    )
    first, second = primitive_factory.jobs

    service.tagged_jobs = [second]
    with pytest.raises(BatchRecoveryError, match="partition prefix"):
        lifecycle.recover_jobs_by_submission_key(plan.submission_key, plan)

    duplicate = FakeJob(
        "duplicate-partition-job",
        tags=first.tags,
        session_id=first.session_id,
    )
    service.tagged_jobs = [first, duplicate]
    with pytest.raises(BatchRecoveryError, match="same plan partition"):
        lifecycle.recover_jobs_by_submission_key(plan.submission_key, plan)

    second.session_id = "different-batch"
    service.tagged_jobs = [first, second]
    with pytest.raises(BatchRecoveryError, match="multiple Runtime batches"):
        lifecycle.recover_jobs_by_submission_key(plan.submission_key, plan)

    second.session_id = first.session_id
    second._job_id = first._job_id
    service.tagged_jobs = [first, second]
    with pytest.raises(BatchRecoveryError, match="same provider job_id"):
        lifecycle.recover_jobs_by_submission_key(plan.submission_key, plan)


def test_submission_rejects_unhashed_execution_option_drift(tmp_path: Path) -> None:
    lifecycle, _, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    plan = _plan(sink, limits)
    plan.submission_key = "drift-key"
    plan.resolved_options["max_execution_time"] = 4
    lifecycle.create_batch("ibm_test", limits)

    with pytest.raises(BatchContractError, match="must exactly match"):
        lifecycle._submit_resolved_plan(
            "batch-1", plan, submission_key="drift-key", limits=limits
        )

    assert primitive_factory.run_calls == []


def test_submission_rejects_fractional_sdk_execution_timeout(tmp_path: Path) -> None:
    lifecycle, _, _, primitive_factory, sink, _ = _lifecycle(tmp_path)
    limits = _limits()
    plan = _plan(sink, limits)
    plan.submission_key = "fractional-key"
    plan.maximum_execution_seconds = 4.5
    plan.resolved_options["max_execution_time"] = 4.5
    lifecycle.create_batch("ibm_test", limits)

    with pytest.raises(BatchContractError, match="must be an integer"):
        lifecycle._submit_resolved_plan(
            "batch-1", plan, submission_key="fractional-key", limits=limits
        )

    assert primitive_factory.run_calls == []
