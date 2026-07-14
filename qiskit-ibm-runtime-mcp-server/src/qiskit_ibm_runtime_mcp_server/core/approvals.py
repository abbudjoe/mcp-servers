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

"""Durable one-time consumption for plan-bound QPU approvals."""

from __future__ import annotations

import os
import sqlite3
import stat
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Protocol


class ApprovalConsumptionError(RuntimeError):
    """Raised when durable approval state cannot be safely consumed."""


class ApprovalReplayError(ApprovalConsumptionError):
    """Raised when an approved plan hash has already crossed the submit boundary."""


class ApprovalConsumptionLedger(Protocol):
    """Atomic one-time authority required immediately before primitive submission."""

    def consume(
        self,
        *,
        plan_hash: str,
        approval_hash: str,
        submission_key: str,
        consumed_at: datetime,
    ) -> None:
        """Atomically consume one plan hash or reject its replay."""
        ...


class LocalApprovalConsumptionLedger:
    """SQLite-backed approval ledger shared by every process using one CAS root.

    The plan hash is the one-time key. Consumption intentionally happens before
    the provider call: a crash may require a fresh plan and approval, but can
    never make the original approval available for a second QPU submission.
    """

    _FILENAME = ".qpu-approval-consumption.sqlite3"

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root).expanduser().resolve(strict=True)
        self._path = self._root / self._FILENAME
        self._prepare_database_file()
        try:
            with closing(self._connect()) as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS consumed_approvals (
                        plan_hash TEXT PRIMARY KEY NOT NULL,
                        approval_hash TEXT NOT NULL,
                        submission_key TEXT NOT NULL,
                        consumed_at TEXT NOT NULL
                    ) WITHOUT ROWID
                    """
                )
        except sqlite3.Error as exc:
            raise ApprovalConsumptionError(
                "durable approval ledger could not be initialized"
            ) from exc

    @property
    def path(self) -> Path:
        """Return the fixed ledger path for operational inspection."""
        return self._path

    def _prepare_database_file(self) -> None:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self._path, flags, 0o600)
        except OSError as exc:
            raise ApprovalConsumptionError(
                "durable approval ledger path is unavailable or unsafe"
            ) from exc
        try:
            file_stat = os.fstat(descriptor)
            if not stat.S_ISREG(file_stat.st_mode):
                raise ApprovalConsumptionError(
                    "durable approval ledger must be a regular file"
                )
            if hasattr(os, "getuid") and file_stat.st_uid != os.getuid():
                raise ApprovalConsumptionError(
                    "durable approval ledger must be owned by the current user"
                )
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=30.0, isolation_level=None)
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA trusted_schema = OFF")
        return connection

    def consume(
        self,
        *,
        plan_hash: str,
        approval_hash: str,
        submission_key: str,
        consumed_at: datetime,
    ) -> None:
        """Atomically consume one plan hash using a cross-process SQLite lock."""
        try:
            with closing(self._connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        """
                        INSERT INTO consumed_approvals (
                            plan_hash, approval_hash, submission_key, consumed_at
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            plan_hash,
                            approval_hash,
                            submission_key,
                            consumed_at.isoformat(),
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    connection.execute("ROLLBACK")
                    raise ApprovalReplayError(
                        "approved SubmissionPlan has already been consumed"
                    ) from exc
                connection.execute("COMMIT")
        except ApprovalReplayError:
            raise
        except sqlite3.Error as exc:
            raise ApprovalConsumptionError(
                "durable approval ledger failed closed before submission"
            ) from exc
