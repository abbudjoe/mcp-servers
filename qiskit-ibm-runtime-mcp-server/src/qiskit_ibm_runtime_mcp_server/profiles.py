# This code is part of Qiskit.
#
# (C) Copyright IBM 2025.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Explicit MCP tool-profile contracts."""

from enum import Enum


class ToolProfile(str, Enum):
    """Supported tool profiles.

    Administrative account operations are intentionally not implemented: they
    are unnecessary for research and belong in Qiskit's credential-management
    interfaces rather than an MCP research server.
    """

    RESEARCH = "research"


DEFAULT_TOOL_PROFILE = ToolProfile.RESEARCH

RESEARCH_TOOL_NAMES = frozenset(
    {
        "active_account_info_tool",
        "active_instance_info_tool",
        "available_instances_tool",
        "cancel_job_tool",
        "find_optimal_qubit_chains_tool",
        "find_optimal_qv_qubits_tool",
        "get_backend_calibration_tool",
        "get_backend_properties_tool",
        "get_backend_snapshot_tool",
        "get_coupling_map_tool",
        "get_job_results_tool",
        "get_job_status_tool",
        "least_busy_backend_tool",
        "list_backends_tool",
        "list_my_jobs_tool",
        "list_saved_accounts_tool",
        "run_estimator_tool",
        "run_sampler_tool",
        "usage_info_tool",
    }
)
