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

"""Bounded Runtime Batch lifecycle and idempotent submission receipts."""

from __future__ import annotations

import copy
import hashlib
import math
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Protocol, Sequence, cast

from qiskit_ibm_runtime import Batch, EstimatorV2, SamplerV2

from ..security import redact_text
from .artifacts import ArtifactSink
from .models import (
    LOCKED_MAX_JOB_EXECUTION_SECONDS,
    BatchExecutionLimits,
    BatchJobReceipt,
    BatchJobStatus,
    BatchJobUsage,
    BatchReference,
    BatchStatus,
    BatchSubmissionFailure,
    BatchSubmissionReceipt,
    BatchUsage,
    EstimatorPubSpec,
    PubExecutionEstimate,
    RecoveredJobReceipt,
    RecoveredSubmissionStatus,
    SamplerPubSpec,
    SubmissionRecovery,
    SubmissionPartition,
    SubmissionPlan,
)
from .primitives import (
    PrimitiveKind,
    PrimitiveRunner,
    _submit_estimator_pubs_unchecked,
    _submit_sampler_pubs_unchecked,
)


DuplicatePolicy = Literal["reject", "allow_if_terminal", "allow_live"]
_VALID_SUBMISSION_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_RUNTIME_JOB_TAG_MAX_CHARACTERS = 86
_RUNTIME_JOB_TAG_MAX_ITEMS = 8
_INTERNAL_TAG_PREFIX = "qiskit-mcp-"
_IDEMPOTENCY_TAG_PREFIX = "qiskit-mcp-idempotency:"
_PLAN_TAG_PREFIX = "qiskit-mcp-plan:"
_PARTITION_TAG_PREFIX = "qiskit-mcp-partition:"
_SUBMISSION_ATTEMPTED_AT_TAG_PREFIX = "qiskit-mcp-attempted-at:"
_TERMINAL_JOB_STATES = frozenset({"DONE", "ERROR", "CANCELLED"})
_KNOWN_JOB_STATES = frozenset(
    {
        "INITIALIZING",
        "QUEUED",
        "VALIDATING",
        "RUNNING",
        *_TERMINAL_JOB_STATES,
    }
)


class BatchContractError(ValueError):
    """Raised when a Batch request contradicts the typed source contract."""


class BatchLimitError(BatchContractError):
    """Raised when a plan or partition exceeds an explicit Runtime bound."""


class DuplicateSubmissionError(BatchContractError):
    """Raised before submission when an idempotency key is already owned."""


class BatchRecoveryError(BatchContractError):
    """Raised when remote evidence cannot safely reconstruct job receipts."""


class BatchHandle(Protocol):
    """Locked public subset of ``qiskit_ibm_runtime.Batch``."""

    @property
    def session_id(self) -> str | None:
        """Return the remote Batch identifier."""
        ...

    def backend(self) -> str | None:
        """Return the owning backend name."""
        ...

    def close(self) -> None:
        """Stop accepting new jobs while allowing accepted jobs to finish."""
        ...

    def status(self) -> str | None:
        """Return the provider Batch status."""
        ...

    def details(self) -> dict[str, Any] | None:
        """Return provider Batch details."""
        ...

    def usage(self) -> float | None:
        """Return aggregate QPU usage seconds."""
        ...


class RuntimeService(Protocol):
    """Runtime service operations needed by the generic Batch control plane."""

    def backend(self, name: str, *, instance: str) -> Any:
        """Resolve one explicit backend in one explicit Runtime instance."""
        ...

    def jobs(self, **kwargs: Any) -> Sequence[Any]:
        """List jobs using public Runtime filters."""
        ...

    def job(self, job_id: str) -> Any:
        """Recover one job by identifier."""
        ...

    def active_instance(self) -> str:
        """Return the CRN of the service's currently active Runtime instance."""
        ...


class BatchFactory(Protocol):
    """Injectable constructor used to keep lifecycle tests fully mocked."""

    def __call__(self, backend: Any, max_time: int) -> BatchHandle:
        """Create a remote Batch."""
        ...


class BatchOpenFactory(Protocol):
    """Injectable Batch reattachment factory."""

    def __call__(self, batch_id: str, service: RuntimeService) -> BatchHandle:
        """Reattach to an existing remote Batch."""
        ...


class PrimitiveFactory(Protocol):
    """Construct a locked primitive in Batch mode with resolved options."""

    def __call__(
        self,
        primitive: PrimitiveKind,
        batch: BatchHandle,
        options: dict[str, Any],
    ) -> PrimitiveRunner:
        """Return a SamplerV2 or EstimatorV2 runner."""
        ...


@dataclass(frozen=True)
class _Reservation:
    plan_hash: str
    generation: int


class SubmissionReceiptRegistry:
    """Process-owned, thread-safe submission-key reservation and receipt history.

    Runtime job tags provide restart recovery and cross-process duplicate detection.
    This registry provides the atomic in-process boundary that the provider API does
    not expose.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, list[_Reservation | BatchSubmissionReceipt]] = {}

    def reserve(
        self,
        submission_key: str,
        plan_hash: str,
        *,
        policy: DuplicatePolicy,
        existing_is_terminal: bool,
    ) -> _Reservation:
        """Atomically reserve a key or refuse an accidental duplicate."""
        with self._lock:
            history = self._entries.setdefault(submission_key, [])
            existing = history[-1] if history else None
            if existing is not None:
                existing_plan_hash = existing.plan_hash
                if existing_plan_hash != plan_hash:
                    raise DuplicateSubmissionError(
                        f"submission key {submission_key!r} is already bound to a "
                        "different plan_hash"
                    )
                permitted = policy == "allow_live" or (
                    policy == "allow_if_terminal"
                    and isinstance(existing, BatchSubmissionReceipt)
                    and existing_is_terminal
                )
                if not permitted:
                    state = (
                        "reserved"
                        if isinstance(existing, _Reservation)
                        else existing.state
                    )
                    raise DuplicateSubmissionError(
                        f"submission key {submission_key!r} is already {state}; "
                        "no second live submission was created"
                    )
            reservation = _Reservation(plan_hash=plan_hash, generation=len(history))
            history.append(reservation)
            return reservation

    def commit(
        self,
        submission_key: str,
        reservation: _Reservation,
        receipt: BatchSubmissionReceipt,
    ) -> None:
        """Replace exactly the caller's reservation with its immutable receipt."""
        with self._lock:
            history = self._entries.get(submission_key)
            if (
                not history
                or reservation.generation >= len(history)
                or history[reservation.generation] != reservation
            ):
                raise BatchContractError(
                    "submission-key reservation ownership changed before receipt commit"
                )
            history[reservation.generation] = receipt

    def receipt(self, submission_key: str) -> BatchSubmissionReceipt | None:
        """Return the most recent committed receipt for a key, if present."""
        with self._lock:
            for entry in reversed(self._entries.get(submission_key, [])):
                if isinstance(entry, BatchSubmissionReceipt):
                    return entry
        return None


_DEFAULT_RECEIPT_REGISTRY = SubmissionReceiptRegistry()


def _default_batch_factory(backend: Any, max_time: int) -> BatchHandle:
    return cast(BatchHandle, Batch(backend=backend, max_time=max_time))


def _default_batch_open_factory(batch_id: str, service: RuntimeService) -> BatchHandle:
    return cast(BatchHandle, Batch.from_id(batch_id, cast(Any, service)))


def _default_primitive_factory(
    primitive: PrimitiveKind,
    batch: BatchHandle,
    options: dict[str, Any],
) -> PrimitiveRunner:
    if primitive == "sampler":
        return cast(PrimitiveRunner, SamplerV2(mode=cast(Any, batch), options=options))
    return cast(PrimitiveRunner, EstimatorV2(mode=cast(Any, batch), options=options))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _datetime_or_none(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _string_status(value: Any) -> str | None:
    if value is None:
        return None
    enum_name = getattr(value, "name", None)
    if isinstance(enum_name, str) and enum_name:
        return enum_name.upper()
    text = str(value).strip()
    candidate = text.removeprefix("JobStatus.").upper()
    if candidate in _KNOWN_JOB_STATES:
        return candidate
    return text


def _job_id(job: Any) -> str:
    candidate = getattr(job, "job_id", None)
    value = candidate() if callable(candidate) else candidate
    if not isinstance(value, str) or not value:
        raise BatchContractError("submitted Runtime job did not return a job_id")
    return value


def _backend_name(backend: Any) -> str | None:
    candidate = getattr(backend, "name", None)
    value = candidate() if callable(candidate) else candidate
    return value if isinstance(value, str) and value else None


def _submission_key_tag(submission_key: str) -> str:
    digest = hashlib.sha256(submission_key.encode("utf-8")).hexdigest()
    digest_characters = _RUNTIME_JOB_TAG_MAX_CHARACTERS - len(_IDEMPOTENCY_TAG_PREFIX)
    if digest_characters < 32:  # pragma: no cover - constant contract invariant
        raise BatchContractError("Runtime job-tag limit cannot hold a safe digest")
    return f"{_IDEMPOTENCY_TAG_PREFIX}{digest[:digest_characters]}"


def _plan_tag(plan_hash: str) -> str:
    return f"{_PLAN_TAG_PREFIX}{plan_hash.removeprefix('sha256:')}"


def _submission_attempt_time_tag(attempted_at: datetime) -> str:
    if attempted_at.tzinfo is None or attempted_at.utcoffset() is None:
        raise BatchContractError(
            "submission clock must return a timezone-aware datetime"
        )
    encoded = attempted_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{_SUBMISSION_ATTEMPTED_AT_TAG_PREFIX}{encoded}"


def _submission_attempted_at_from_tags(tags: Sequence[str]) -> datetime:
    matches = [
        tag for tag in tags if tag.startswith(_SUBMISSION_ATTEMPTED_AT_TAG_PREFIX)
    ]
    if len(matches) != 1:
        raise BatchRecoveryError(
            "remote job must contain exactly one wrapper submission-attempt tag"
        )
    encoded = matches[0].removeprefix(_SUBMISSION_ATTEMPTED_AT_TAG_PREFIX)
    try:
        return datetime.strptime(encoded, "%Y%m%dT%H%M%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as exc:
        raise BatchRecoveryError(
            "remote job contains an invalid wrapper submission-attempt tag"
        ) from exc


def _provider_creation_date(job: Any) -> datetime | None:
    candidate = getattr(job, "creation_date", None)
    value = candidate() if callable(candidate) else candidate
    if value is None:
        return None
    if isinstance(value, datetime):
        created_at = value
    elif isinstance(value, str):
        try:
            created_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise BatchRecoveryError(
                "remote job has an invalid provider creation_date"
            ) from exc
    else:
        raise BatchRecoveryError("remote job has an invalid provider creation_date")
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise BatchRecoveryError(
            "remote job provider creation_date must be timezone-aware"
        )
    return created_at.astimezone(timezone.utc)


def _runtime_submission_value(value: Any) -> Any:
    """Remove locked-SDK Unset sentinels from canonical plan options."""
    if value == {"$runtime_default": "Unset"}:
        return None
    if isinstance(value, dict):
        resolved = {
            key: converted
            for key, item in value.items()
            if key != "_VERSION"
            and (converted := _runtime_submission_value(item)) is not None
        }
        return resolved
    if isinstance(value, list):
        return [_runtime_submission_value(item) for item in value]
    return copy.deepcopy(value)


def _partition_id(index: int, pub_ids: Sequence[str]) -> str:
    digest = hashlib.sha256("\0".join(pub_ids).encode("utf-8")).hexdigest()
    return f"partition-{index:04d}-{digest[:12]}"


def plan_batch_partitions(
    estimates: Sequence[PubExecutionEstimate],
    limits: BatchExecutionLimits,
) -> tuple[SubmissionPartition, ...]:
    """Greedily partition ordered PUB estimates under every explicit Batch bound."""
    if not estimates:
        raise BatchLimitError("at least one PUB estimate is required")
    pub_ids = [estimate.pub_id for estimate in estimates]
    if len(pub_ids) != len(set(pub_ids)):
        raise BatchLimitError("PUB estimates require unique pub_id values")

    usable_batch_seconds = limits.batch_max_time_seconds - limits.ttl_margin_seconds
    total_seconds = math.fsum(
        float(estimate.estimated_qpu_seconds) for estimate in estimates
    )
    if total_seconds > usable_batch_seconds:
        raise BatchLimitError(
            "estimated Batch usage exceeds maximum TTL after the configured margin"
        )

    partitions: list[SubmissionPartition] = []
    current_ids: list[str] = []
    current_seconds = 0.0
    per_job_seconds = min(
        float(limits.max_estimated_qpu_seconds_per_job),
        float(limits.max_execution_seconds_per_job),
    )

    def flush() -> None:
        nonlocal current_ids, current_seconds
        if not current_ids:
            return
        partitions.append(
            SubmissionPartition(
                schema_version="1.0",
                partition_id=_partition_id(len(partitions), current_ids),
                pub_ids=list(current_ids),
                estimated_qpu_seconds=current_seconds,
                maximum_execution_seconds=limits.max_execution_seconds_per_job,
            )
        )
        current_ids = []
        current_seconds = 0.0

    for estimate in estimates:
        seconds = float(estimate.estimated_qpu_seconds)
        if seconds > limits.max_estimated_qpu_seconds_per_job:
            raise BatchLimitError(
                f"PUB {estimate.pub_id!r} exceeds the per-job estimated-time limit"
            )
        if seconds > limits.max_execution_seconds_per_job:
            raise BatchLimitError(
                f"PUB {estimate.pub_id!r} exceeds the per-job execution-time limit"
            )
        would_exceed_pubs = len(current_ids) >= limits.max_pubs_per_job
        would_exceed_time = (
            bool(current_ids) and current_seconds + seconds > per_job_seconds
        )
        if would_exceed_pubs or would_exceed_time:
            flush()
        current_ids.append(estimate.pub_id)
        current_seconds = math.fsum((current_seconds, seconds))
    flush()

    if len(partitions) > limits.max_jobs:
        raise BatchLimitError(
            f"partition plan requires {len(partitions)} jobs, exceeding max_jobs="
            f"{limits.max_jobs}"
        )
    return tuple(partitions)


class BatchLifecycle:
    """Typed generic Batch lifecycle bound to one explicit Runtime instance."""

    def __init__(
        self,
        service: RuntimeService,
        *,
        instance_id: str,
        sink: ArtifactSink,
        batch_factory: BatchFactory = _default_batch_factory,
        batch_open_factory: BatchOpenFactory = _default_batch_open_factory,
        primitive_factory: PrimitiveFactory = _default_primitive_factory,
        receipt_registry: SubmissionReceiptRegistry = _DEFAULT_RECEIPT_REGISTRY,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not instance_id.strip():
            raise BatchContractError("an explicit Runtime instance_id is required")
        self._service = service
        self._instance_id = instance_id.strip()
        self._sink = sink
        self._batch_factory = batch_factory
        self._batch_open_factory = batch_open_factory
        self._primitive_factory = primitive_factory
        self._registry = receipt_registry
        self._clock = clock
        self._batches: dict[str, BatchHandle] = {}
        self._references: dict[str, BatchReference] = {}

    def create_batch(
        self, backend_name: str, limits: BatchExecutionLimits
    ) -> BatchReference:
        """Create a bounded Runtime Batch on one explicit backend."""
        if not backend_name.strip():
            raise BatchContractError("an explicit backend_name is required")
        backend = self._service.backend(
            backend_name.strip(), instance=self._instance_id
        )
        actual_backend_name = _backend_name(backend)
        if actual_backend_name != backend_name.strip():
            raise BatchContractError(
                "resolved Runtime backend does not match the explicit backend_name"
            )
        batch = self._batch_factory(backend, limits.batch_max_time_seconds)
        batch_id = batch.session_id
        if not batch_id:
            raise BatchContractError(
                "Runtime Batch creation returned no batch_id; local/simulator modes "
                "cannot satisfy the remote receipt contract"
            )
        details = batch.details() or {}
        provider_maximum_time = details.get("max_time")
        if (
            isinstance(provider_maximum_time, bool)
            or not isinstance(provider_maximum_time, (int, float))
            or provider_maximum_time <= 0
        ):
            batch.close()
            raise BatchContractError(
                "Runtime Batch did not expose its effective maximum TTL; it was "
                "closed before any job submission"
            )
        effective_maximum_time = min(
            limits.batch_max_time_seconds, int(provider_maximum_time)
        )
        reference = BatchReference(
            schema_version="1.0",
            batch_id=batch_id,
            instance_id=self._instance_id,
            backend_name=backend_name.strip(),
            maximum_time_seconds=effective_maximum_time,
            observed_at=self._clock(),
        )
        self._batches[batch_id] = batch
        self._references[batch_id] = reference
        return reference

    def open_batch(
        self, batch_id: str, *, expected_backend_name: str | None = None
    ) -> BatchReference:
        """Reattach to an existing Batch and verify its explicit backend when given."""
        if not batch_id.strip():
            raise BatchContractError("an explicit batch_id is required")
        batch = self._batch_open_factory(batch_id, self._service)
        active_instance = self._service.active_instance()
        if active_instance != self._instance_id:
            raise BatchContractError(
                "reattached Runtime Batch belongs to a different active instance"
            )
        details = batch.details() or {}
        backend_name = details.get("backend_name") or batch.backend()
        if not isinstance(backend_name, str) or not backend_name:
            raise BatchContractError("reattached Runtime Batch has no backend identity")
        if expected_backend_name is not None and backend_name != expected_backend_name:
            raise BatchContractError(
                "reattached Runtime Batch backend does not match expected_backend_name"
            )
        maximum_time = details.get("max_time")
        if (
            isinstance(maximum_time, bool)
            or not isinstance(maximum_time, (int, float))
            or maximum_time <= 0
        ):
            raise BatchContractError(
                "reattached Runtime Batch did not expose a positive effective maximum TTL"
            )
        reference = BatchReference(
            schema_version="1.0",
            batch_id=batch_id,
            instance_id=self._instance_id,
            backend_name=backend_name,
            maximum_time_seconds=int(maximum_time),
            observed_at=self._clock(),
        )
        self._batches[batch_id] = batch
        self._references[batch_id] = reference
        return reference

    def _batch(self, batch_id: str) -> BatchHandle:
        batch = self._batches.get(batch_id)
        if batch is None:
            self.open_batch(batch_id)
            batch = self._batches[batch_id]
        return batch

    def close_batch(self, batch_id: str) -> BatchStatus:
        """Close a Batch to new jobs and return its current typed status."""
        self._batch(batch_id).close()
        return self.batch_status(batch_id)

    def batch_status(self, batch_id: str) -> BatchStatus:
        """Recover typed provider status and TTL details for a Batch."""
        batch = self._batch(batch_id)
        status = batch.status()
        details = batch.details() or {}
        maximum_time = details.get("max_time")
        interactive_timeout = details.get("interactive_timeout")
        return BatchStatus(
            schema_version="1.0",
            batch_id=batch_id,
            status=status,
            accepting_jobs=(
                details.get("accepting_jobs")
                if isinstance(details.get("accepting_jobs"), bool)
                else None
            ),
            maximum_time_seconds=(
                int(maximum_time) if isinstance(maximum_time, (int, float)) else None
            ),
            interactive_timeout_seconds=(
                int(interactive_timeout)
                if isinstance(interactive_timeout, (int, float))
                else None
            ),
            started_at=_datetime_or_none(details.get("started_at")),
            closed_at=_datetime_or_none(details.get("closed_at")),
            observed_at=self._clock(),
        )

    def _job_status(self, job: Any, batch_id: str) -> BatchJobStatus:
        job_id = _job_id(job)
        try:
            raw_status = job.status()
        except Exception:
            raw_status = "UNAVAILABLE"
        raw_tags = getattr(job, "tags", ()) or ()
        tags = tuple(str(tag) for tag in raw_tags)
        creation_date = getattr(job, "creation_date", None)
        if callable(creation_date):
            creation_date = creation_date()
        return BatchJobStatus(
            schema_version="1.0",
            batch_id=batch_id,
            job_id=job_id,
            status=_string_status(raw_status),
            created_at=_datetime_or_none(creation_date),
            tags=tags,
        )

    def list_batch_jobs(self, batch_id: str) -> tuple[BatchJobStatus, ...]:
        """List every job through the locked service ``session_id`` filter."""
        jobs = self._service.jobs(
            limit=None,
            session_id=batch_id,
            instance=self._instance_id,
            descending=False,
        )
        return tuple(self._job_status(job, batch_id) for job in jobs)

    def batch_usage(self, batch_id: str) -> BatchUsage:
        """Retrieve Batch-wide and per-job QPU usage without result interpretation."""
        batch_seconds = self._batch(batch_id).usage()
        jobs = self._service.jobs(
            limit=None,
            session_id=batch_id,
            instance=self._instance_id,
            descending=False,
        )
        usages: list[BatchJobUsage] = []
        for job in jobs:
            quantum_seconds: float | None = None
            try:
                metrics = job.metrics() or {}
                usage = metrics.get("usage", {})
                raw_seconds = usage.get("quantum_seconds")
                if isinstance(raw_seconds, (int, float)) and raw_seconds >= 0:
                    quantum_seconds = float(raw_seconds)
            except Exception:
                quantum_seconds = None
            usages.append(
                BatchJobUsage(
                    schema_version="1.0",
                    job_id=_job_id(job),
                    quantum_seconds=quantum_seconds,
                )
            )
        return BatchUsage(
            schema_version="1.0",
            batch_id=batch_id,
            batch_seconds=batch_seconds,
            jobs=tuple(usages),
            retrieved_at=self._clock(),
        )

    def _validate_plan(
        self,
        batch_id: str,
        plan: SubmissionPlan,
        limits: BatchExecutionLimits,
    ) -> None:
        reference = self._references.get(batch_id)
        if reference is None:
            reference = self.open_batch(
                batch_id, expected_backend_name=plan.backend_name
            )
        if plan.instance_id != self._instance_id:
            raise BatchContractError(
                "SubmissionPlan instance_id does not match lifecycle"
            )
        if plan.backend_name != reference.backend_name:
            raise BatchContractError("SubmissionPlan backend does not own this Batch")
        if len(plan.partitions) > limits.max_jobs:
            raise BatchLimitError("SubmissionPlan exceeds max_jobs")
        if plan.maximum_execution_seconds > limits.max_execution_seconds_per_job:
            raise BatchLimitError("SubmissionPlan exceeds per-job execution limit")
        if plan.maximum_execution_seconds > LOCKED_MAX_JOB_EXECUTION_SECONDS:
            raise BatchLimitError("SubmissionPlan exceeds locked Runtime job ceiling")
        if not float(plan.maximum_execution_seconds).is_integer():
            raise BatchContractError(
                "SubmissionPlan.maximum_execution_seconds must be an integer for "
                "the locked Runtime options contract"
            )
        effective_batch_seconds = min(
            reference.maximum_time_seconds, limits.batch_max_time_seconds
        )
        usable_batch_seconds = effective_batch_seconds - limits.ttl_margin_seconds
        if usable_batch_seconds <= 0:
            raise BatchLimitError(
                "effective Batch TTL does not leave a positive configured margin"
            )
        if plan.maximum_execution_seconds > usable_batch_seconds:
            raise BatchLimitError(
                "SubmissionPlan job timeout exceeds effective Batch TTL after margin"
            )
        if plan.estimated_qpu_seconds > usable_batch_seconds:
            raise BatchLimitError(
                "SubmissionPlan exceeds effective Batch TTL after margin"
            )

        option_limit = plan.resolved_options.get("max_execution_time")
        if (
            isinstance(option_limit, bool)
            or not isinstance(option_limit, (int, float))
            or float(option_limit) != float(plan.maximum_execution_seconds)
        ):
            raise BatchContractError(
                "resolved_options.max_execution_time must exactly match "
                "SubmissionPlan.maximum_execution_seconds"
            )

        pub_ids = [pub.pub_id for pub in plan.pubs]
        partitioned_ids = [
            pub_id for partition in plan.partitions for pub_id in partition.pub_ids
        ]
        if partitioned_ids != pub_ids:
            raise BatchContractError(
                "SubmissionPlan partitions must preserve exact PUB order"
            )
        estimated_total = 0.0
        for partition in plan.partitions:
            if len(partition.pub_ids) > limits.max_pubs_per_job:
                raise BatchLimitError(
                    f"partition {partition.partition_id!r} exceeds max_pubs_per_job"
                )
            estimate = partition.estimated_qpu_seconds
            execution_limit = partition.maximum_execution_seconds
            if estimate is None or execution_limit is None:
                raise BatchContractError(
                    "every Batch partition requires estimated and maximum execution seconds"
                )
            if estimate > limits.max_estimated_qpu_seconds_per_job:
                raise BatchLimitError(
                    f"partition {partition.partition_id!r} exceeds estimated-time limit"
                )
            if estimate > plan.maximum_execution_seconds:
                raise BatchLimitError(
                    f"partition {partition.partition_id!r} estimate exceeds its job timeout"
                )
            if execution_limit != plan.maximum_execution_seconds:
                raise BatchContractError(
                    "partition maximum_execution_seconds must match its plan"
                )
            estimated_total = math.fsum((estimated_total, float(estimate)))
        if not math.isclose(
            estimated_total,
            float(plan.estimated_qpu_seconds),
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise BatchContractError(
                "partition estimates must sum to SubmissionPlan.estimated_qpu_seconds"
            )

    def _remote_jobs_for_key(self, submission_key: str) -> tuple[Any, ...]:
        jobs = self._service.jobs(
            limit=None,
            instance=self._instance_id,
            job_tags=[_submission_key_tag(submission_key)],
            descending=False,
        )
        return tuple(jobs)

    def _jobs_are_terminal(self, jobs: Sequence[Any]) -> bool:
        if not jobs:
            return True
        for job in jobs:
            try:
                status = _string_status(job.status())
            except Exception:
                return False
            if status is None or status.upper() not in _TERMINAL_JOB_STATES:
                return False
        return True

    def _existing_receipt_is_terminal(
        self, receipt: BatchSubmissionReceipt | None
    ) -> bool:
        if receipt is None or not receipt.jobs:
            return receipt is not None and receipt.state == "failed"
        jobs: list[Any] = []
        for job_receipt in receipt.jobs:
            try:
                jobs.append(self._service.job(job_receipt.job_id))
            except Exception:
                return False
        return self._jobs_are_terminal(jobs)

    def _submission_options(
        self,
        plan: SubmissionPlan,
        submission_key: str,
        partition_id: str,
        submission_attempted_at: datetime,
    ) -> dict[str, Any]:
        options = _runtime_submission_value(plan.resolved_options)
        if not isinstance(options, dict):  # pragma: no cover - model invariant
            raise BatchContractError("resolved_options must materialize to an object")
        options["max_execution_time"] = int(plan.maximum_execution_seconds)
        environment = options.get("environment", {})
        if not isinstance(environment, dict):
            raise BatchContractError("resolved_options.environment must be an object")
        raw_tags = environment.get("job_tags", []) or []
        if not isinstance(raw_tags, list) or any(
            not isinstance(tag, str) for tag in raw_tags
        ):
            raise BatchContractError(
                "resolved_options.environment.job_tags must be strings"
            )
        reserved_tags = [
            tag for tag in raw_tags if tag.startswith(_INTERNAL_TAG_PREFIX)
        ]
        if reserved_tags:
            raise BatchContractError(
                "caller job tags must not use the reserved qiskit-mcp- namespace"
            )
        internal_tags = [
            _submission_key_tag(submission_key),
            _plan_tag(plan.plan_hash),
            f"{_PARTITION_TAG_PREFIX}{partition_id}",
            _submission_attempt_time_tag(submission_attempted_at),
        ]
        job_tags = list(dict.fromkeys([*raw_tags, *internal_tags]))
        if len(job_tags) > _RUNTIME_JOB_TAG_MAX_ITEMS:
            raise BatchContractError(
                "resolved Runtime job tags must contain no more than "
                f"{_RUNTIME_JOB_TAG_MAX_ITEMS} items"
            )
        oversized_tags = [
            tag for tag in job_tags if len(tag) > _RUNTIME_JOB_TAG_MAX_CHARACTERS
        ]
        if oversized_tags:
            raise BatchContractError(
                "resolved Runtime job tags must not exceed "
                f"{_RUNTIME_JOB_TAG_MAX_CHARACTERS} characters"
            )
        environment["job_tags"] = job_tags
        options["environment"] = environment
        return options

    def _submit_resolved_plan(
        self,
        batch_id: str,
        plan: SubmissionPlan,
        *,
        submission_key: str,
        limits: BatchExecutionLimits,
        duplicate_policy: DuplicatePolicy = "reject",
    ) -> BatchSubmissionReceipt:
        """Internal post-approval submit primitive used by the approval boundary."""
        if _VALID_SUBMISSION_KEY.fullmatch(submission_key) is None:
            raise BatchContractError(
                "submission_key must be 1-256 deterministic URL-safe characters"
            )
        if plan.submission_key != submission_key:
            raise BatchContractError(
                "submission_key must exactly match SubmissionPlan.submission_key"
            )
        if duplicate_policy not in ("reject", "allow_if_terminal", "allow_live"):
            raise BatchContractError("unsupported duplicate submission policy")
        self._validate_plan(batch_id, plan, limits)

        remote_jobs = self._remote_jobs_for_key(submission_key)
        remote_terminal = self._jobs_are_terminal(remote_jobs)
        expected_plan_tag = _plan_tag(plan.plan_hash)
        if (
            remote_jobs
            and duplicate_policy != "reject"
            and any(
                expected_plan_tag not in (getattr(job, "tags", ()) or ())
                for job in remote_jobs
            )
        ):
            raise DuplicateSubmissionError(
                f"submission key {submission_key!r} has remote jobs that are not "
                "verifiably bound to this plan_hash"
            )
        if remote_jobs and (
            duplicate_policy == "reject"
            or (duplicate_policy == "allow_if_terminal" and not remote_terminal)
        ):
            raise DuplicateSubmissionError(
                f"submission key {submission_key!r} already owns remote jobs; "
                "no second live submission was created"
            )
        existing_receipt = self._registry.receipt(submission_key)
        if (
            existing_receipt is not None
            and existing_receipt.plan_hash != plan.plan_hash
        ):
            raise DuplicateSubmissionError(
                f"submission key {submission_key!r} is already bound to a different "
                "plan_hash"
            )
        existing_terminal = self._existing_receipt_is_terminal(existing_receipt)
        reservation = self._registry.reserve(
            submission_key,
            plan.plan_hash,
            policy=duplicate_policy,
            existing_is_terminal=existing_terminal,
        )

        batch = self._batch(batch_id)
        reserved_at = self._clock()
        pub_by_id = {pub.pub_id: pub for pub in plan.pubs}
        receipts: list[BatchJobReceipt] = []
        failure: BatchSubmissionFailure | None = None

        for partition in plan.partitions:
            try:
                partition_pubs = [pub_by_id[pub_id] for pub_id in partition.pub_ids]
                submission_attempted_at = self._clock()
                runner = self._primitive_factory(
                    plan.primitive,
                    batch,
                    self._submission_options(
                        plan,
                        submission_key,
                        partition.partition_id,
                        submission_attempted_at,
                    ),
                )
                if plan.primitive == "sampler":
                    submitted = _submit_sampler_pubs_unchecked(
                        runner,
                        cast(Sequence[SamplerPubSpec], partition_pubs),
                        sink=self._sink,
                    )
                else:
                    submitted = _submit_estimator_pubs_unchecked(
                        runner,
                        cast(Sequence[EstimatorPubSpec], partition_pubs),
                        sink=self._sink,
                    )
                receipts.append(
                    BatchJobReceipt(
                        schema_version="1.0",
                        partition_id=partition.partition_id,
                        job_id=_job_id(submitted.job),
                        pub_ids=tuple(partition.pub_ids),
                        submitted_at=submission_attempted_at,
                    )
                )
            except Exception as exc:
                failure = BatchSubmissionFailure(
                    schema_version="1.0",
                    partition_id=partition.partition_id,
                    error_type=type(exc).__name__,
                    message=redact_text(exc) or type(exc).__name__,
                    failed_at=self._clock(),
                )
                break

        state: Literal["submitted", "partial_failure", "failed"]
        if failure is None:
            state = "submitted"
        elif receipts:
            state = "partial_failure"
        else:
            state = "failed"
        receipt = BatchSubmissionReceipt(
            schema_version="1.0",
            submission_key=submission_key,
            batch_id=batch_id,
            plan_hash=plan.plan_hash,
            pub_ids=tuple(pub.pub_id for pub in plan.pubs),
            jobs=tuple(receipts),
            state=state,
            reserved_at=reserved_at,
            completed_at=self._clock(),
            failure=failure,
        )
        self._registry.commit(submission_key, reservation, receipt)
        return receipt

    def receipt(self, submission_key: str) -> BatchSubmissionReceipt | None:
        """Return the latest in-process immutable receipt for a key."""
        return self._registry.receipt(submission_key)

    def recover_submission(
        self, receipt: BatchSubmissionReceipt
    ) -> RecoveredSubmissionStatus:
        """Recover current Batch and job status from an immutable receipt."""
        observed_at = self._clock()
        jobs: list[BatchJobStatus] = []
        for job_receipt in receipt.jobs:
            try:
                job = self._service.job(job_receipt.job_id)
                jobs.append(self._job_status(job, receipt.batch_id))
            except Exception:
                jobs.append(
                    BatchJobStatus(
                        schema_version="1.0",
                        batch_id=receipt.batch_id,
                        job_id=job_receipt.job_id,
                        status="UNAVAILABLE",
                        created_at=None,
                    )
                )
        return RecoveredSubmissionStatus(
            schema_version="1.0",
            receipt=receipt,
            batch=self.batch_status(receipt.batch_id),
            jobs=tuple(jobs),
            observed_at=observed_at,
        )

    def recover_jobs_by_submission_key(
        self, submission_key: str, plan: SubmissionPlan
    ) -> SubmissionRecovery:
        """Recover plan-bound job receipts after process-local state is lost.

        Provider inventory is not treated as caller identity. The caller must supply
        the exact persisted plan; its canonical hash binds plan, partition, and PUB
        identity to the tags written before each primitive call.
        """
        if _VALID_SUBMISSION_KEY.fullmatch(submission_key) is None:
            raise BatchContractError("invalid deterministic submission_key")
        if plan.submission_key != submission_key:
            raise BatchRecoveryError(
                "SubmissionPlan submission_key does not match the recovery key"
            )
        if plan.instance_id != self._instance_id:
            raise BatchRecoveryError(
                "SubmissionPlan instance_id does not match the recovery lifecycle"
            )
        # Imported lazily because budgeting owns the canonical plan hash and imports
        # this module for the submission boundary.
        from .budgeting import validate_submission_plan_hash

        try:
            validate_submission_plan_hash(plan)
        except ValueError as exc:
            raise BatchRecoveryError(
                "SubmissionPlan canonical hash is invalid"
            ) from exc

        partitions = {
            partition.partition_id: partition for partition in plan.partitions
        }
        if len(partitions) != len(plan.partitions):
            raise BatchRecoveryError(
                "SubmissionPlan partition_id values must be unique"
            )

        observed_at = self._clock()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise BatchRecoveryError(
                "recovery clock must return a timezone-aware datetime"
            )
        expected_key_tag = _submission_key_tag(submission_key)
        expected_plan_tag = _plan_tag(plan.plan_hash)
        recovered_by_partition: dict[str, RecoveredJobReceipt] = {}
        recovered_job_ids: set[str] = set()
        batch_ids: set[str] = set()

        for job in self._remote_jobs_for_key(submission_key):
            raw_tags = getattr(job, "tags", ()) or ()
            if not isinstance(raw_tags, (list, tuple)) or any(
                not isinstance(tag, str) for tag in raw_tags
            ):
                raise BatchRecoveryError("remote job tags must be a string sequence")
            tags = tuple(raw_tags)
            key_tags = [tag for tag in tags if tag.startswith(_IDEMPOTENCY_TAG_PREFIX)]
            if key_tags != [expected_key_tag]:
                raise BatchRecoveryError(
                    "remote job must be bound only to the requested submission_key"
                )
            plan_tags = [tag for tag in tags if tag.startswith(_PLAN_TAG_PREFIX)]
            if plan_tags != [expected_plan_tag]:
                raise BatchRecoveryError(
                    "remote job must be bound only to the canonical SubmissionPlan"
                )
            partition_tags = [
                tag for tag in tags if tag.startswith(_PARTITION_TAG_PREFIX)
            ]
            if len(partition_tags) != 1:
                raise BatchRecoveryError(
                    "remote job must contain exactly one partition identity tag"
                )
            partition_id = partition_tags[0].removeprefix(_PARTITION_TAG_PREFIX)
            partition = partitions.get(partition_id)
            if partition is None:
                raise BatchRecoveryError(
                    "remote job partition is not present in the canonical SubmissionPlan"
                )
            if partition_id in recovered_by_partition:
                raise BatchRecoveryError(
                    "multiple remote jobs claim the same plan partition"
                )

            batch_id_value = getattr(job, "session_id", None)
            batch_id = batch_id_value() if callable(batch_id_value) else batch_id_value
            if not isinstance(batch_id, str) or not batch_id:
                raise BatchRecoveryError("remote job has no trustworthy batch_id")
            submitted_at = _submission_attempted_at_from_tags(tags)
            provider_created_at = _provider_creation_date(job)
            if submitted_at > observed_at or (
                provider_created_at is not None and provider_created_at > observed_at
            ):
                raise BatchRecoveryError(
                    "remote job submission evidence is later than recovery observation"
                )
            job_id = _job_id(job)
            if job_id in recovered_job_ids:
                raise BatchRecoveryError(
                    "multiple recovered partitions claim the same provider job_id"
                )
            try:
                status = _string_status(job.status()) or "UNKNOWN"
            except Exception:
                status = "UNAVAILABLE"
            recovered_by_partition[partition_id] = RecoveredJobReceipt(
                schema_version="1.0",
                submission_key=submission_key,
                plan_id=plan.plan_id,
                plan_hash=plan.plan_hash,
                primitive=plan.primitive,
                batch_id=batch_id,
                partition_id=partition_id,
                job_id=job_id,
                pub_ids=tuple(partition.pub_ids),
                submitted_at=submitted_at,
                submission_time_source="wrapper_pre_submit_job_tag",
                provider_created_at=provider_created_at,
                status=status,
            )
            recovered_job_ids.add(job_id)
            batch_ids.add(batch_id)

        if len(batch_ids) > 1:
            raise BatchRecoveryError(
                "one submission key resolved to jobs in multiple Runtime batches"
            )
        ordered_partition_ids = [
            partition.partition_id for partition in plan.partitions
        ]
        recovered_partition_ids = [
            partition_id
            for partition_id in ordered_partition_ids
            if partition_id in recovered_by_partition
        ]
        if (
            recovered_partition_ids
            != ordered_partition_ids[: len(recovered_partition_ids)]
        ):
            raise BatchRecoveryError(
                "remote jobs do not preserve the canonical partition prefix"
            )
        missing_partition_ids = tuple(
            ordered_partition_ids[len(recovered_partition_ids) :]
        )
        recovered_jobs = tuple(
            recovered_by_partition[partition_id]
            for partition_id in recovered_partition_ids
        )
        state: Literal["not_found", "partial", "complete"]
        if not recovered_jobs:
            state = "not_found"
        elif missing_partition_ids:
            state = "partial"
        else:
            state = "complete"
        return SubmissionRecovery(
            schema_version="1.0",
            submission_key=submission_key,
            plan_id=plan.plan_id,
            plan_hash=plan.plan_hash,
            primitive=plan.primitive,
            batch_id=next(iter(batch_ids), None),
            state=state,
            jobs=recovered_jobs,
            missing_partition_ids=missing_partition_ids,
            observed_at=observed_at,
        )
