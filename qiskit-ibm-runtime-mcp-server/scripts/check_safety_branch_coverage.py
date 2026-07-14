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

"""Enforce per-module branch coverage for Runtime safety boundaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


MINIMUM_BRANCH_PERCENT = 90.0
SAFETY_MODULES = (
    "core/approvals.py",
    "core/budgeting.py",
    "core/primitives.py",
    "security.py",
)


def _matching_file(files: dict[str, Any], suffix: str) -> dict[str, Any]:
    matches = [details for name, details in files.items() if name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(
            f"coverage report must contain exactly one file ending in {suffix!r}; "
            f"found {len(matches)}"
        )
    return matches[0]


def branch_percent(details: dict[str, Any]) -> float:
    """Return branch-only coverage, failing when branch data is absent."""
    summary = details["summary"]
    total = int(summary["num_branches"])
    missing = int(summary["missing_branches"])
    if total <= 0:
        raise ValueError("coverage report has no branch data")
    return 100.0 * (total - missing) / total


def check_report(path: Path) -> list[str]:
    """Return formatted failures for safety modules below the contract."""
    report = json.loads(path.read_text(encoding="utf-8"))
    files = report.get("files")
    if not isinstance(files, dict):
        raise ValueError("coverage report has no file map")
    failures: list[str] = []
    for suffix in SAFETY_MODULES:
        percent = branch_percent(_matching_file(files, suffix))
        print(f"{suffix}: {percent:.2f}% branch coverage")
        if percent < MINIMUM_BRANCH_PERCENT:
            failures.append(f"{suffix}: {percent:.2f}% < {MINIMUM_BRANCH_PERCENT:.2f}%")
    return failures


def main(argv: list[str]) -> int:
    """Validate a coverage.py JSON report supplied on the command line."""
    if len(argv) != 2:
        print(f"usage: {Path(argv[0]).name} COVERAGE.json", file=sys.stderr)
        return 2
    try:
        failures = check_report(Path(argv[1]))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"invalid coverage report: {exc}", file=sys.stderr)
        return 2
    if failures:
        print("safety branch coverage gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
