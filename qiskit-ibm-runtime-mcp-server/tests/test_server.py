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

"""Unit tests for IBM Runtime MCP Server functions."""

import os
from unittest.mock import Mock, patch

import pytest

from qiskit_ibm_runtime_mcp_server.ibm_runtime import (
    active_account_info,
    active_instance_info,
    available_instances,
    cancel_job,
    get_backend_calibration,
    get_backend_properties,
    get_bell_state_circuit,
    get_ghz_state_circuit,
    get_instance_from_env,
    get_job_results,
    get_job_status,
    get_quantum_random_circuit,
    get_service_status,
    get_superposition_circuit,
    _get_token_from_env,
    initialize_service,
    least_busy_backend,
    list_backends,
    list_my_jobs,
    list_saved_accounts,
    run_estimator,
    run_sampler,
    usage_info,
)
from qiskit_ibm_runtime_mcp_server.server import mcp
from qiskit_ibm_runtime_mcp_server.server import (
    active_account_info_tool,
    active_instance_info_tool,
    available_instances_tool,
    list_saved_accounts_tool,
    usage_info_tool,
)


class TestGetTokenFromEnv:
    """Test get_token_from_env function."""

    def test_get_token_from_env_valid(self):
        """Test getting valid token from environment."""
        with patch.dict(os.environ, {"QISKIT_IBM_TOKEN": "valid_token_123"}):
            token = _get_token_from_env()
            assert token == "valid_token_123"

    def test_get_token_from_env_empty(self):
        """Test getting token when environment variable is not set."""
        with patch.dict(os.environ, {}, clear=True):
            token = _get_token_from_env()
            assert token is None

    def test_get_token_from_env_placeholder(self):
        """Test that placeholder tokens are rejected."""
        with patch.dict(os.environ, {"QISKIT_IBM_TOKEN": "<PASSWORD>"}):
            token = _get_token_from_env()
            assert token is None

    def test_get_token_from_env_whitespace(self):
        """Test that whitespace-only tokens return None."""
        with patch.dict(os.environ, {"QISKIT_IBM_TOKEN": "   "}):
            token = _get_token_from_env()
            assert token is None


class TestGetInstanceFromEnv:
    """Test get_instance_from_env function."""

    def test_get_instance_from_env_valid(self):
        """Test getting valid instance from environment."""
        with patch.dict(
            os.environ, {"QISKIT_IBM_RUNTIME_MCP_INSTANCE": "my-instance-crn"}
        ):
            instance = get_instance_from_env()
            assert instance == "my-instance-crn"

    def test_get_instance_from_env_empty(self):
        """Test getting instance when environment variable is not set."""
        with patch.dict(os.environ, {}, clear=True):
            instance = get_instance_from_env()
            assert instance is None

    def test_get_instance_from_env_whitespace(self):
        """Test that whitespace-only instance returns None."""
        with patch.dict(os.environ, {"QISKIT_IBM_RUNTIME_MCP_INSTANCE": "   "}):
            instance = get_instance_from_env()
            assert instance is None

    def test_get_instance_from_env_strips_whitespace(self):
        """Test that instance value is stripped of whitespace."""
        with patch.dict(
            os.environ, {"QISKIT_IBM_RUNTIME_MCP_INSTANCE": "  my-instance  "}
        ):
            instance = get_instance_from_env()
            assert instance == "my-instance"


class TestInitializeService:
    """Test secure service initialization."""

    def test_initialize_service_uses_saved_credentials(self, mock_runtime_service):
        """Saved credentials are used with the required configured instance."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.QiskitRuntimeService"
        ) as mock_qrs:
            mock_qrs.return_value = mock_runtime_service

            result = initialize_service()

            assert result == mock_runtime_service
            mock_qrs.assert_called_once_with(
                channel="ibm_quantum_platform", instance="test-instance"
            )
            mock_qrs.save_account.assert_not_called()

    def test_initialize_service_with_explicit_instance(self, mock_runtime_service):
        """An explicit Python argument overrides environment configuration."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.QiskitRuntimeService"
        ) as mock_qrs:
            mock_qrs.return_value = mock_runtime_service

            result = initialize_service(instance="explicit-instance")

            assert result == mock_runtime_service
            mock_qrs.assert_called_once_with(
                channel="ibm_quantum_platform", instance="explicit-instance"
            )


class TestListBackends:
    """Test list_backends function."""

    @pytest.mark.asyncio
    async def test_list_backends_success(self, mock_runtime_service):
        """Test successful backends listing."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            result = await list_backends()

            assert result["status"] == "success"
            assert result["total_backends"] == 2
            assert len(result["backends"]) == 2

            backend = result["backends"][0]
            assert "name" in backend
            assert "num_qubits" in backend
            assert "simulator" in backend

    @pytest.mark.asyncio
    async def test_list_backends_no_service(self):
        """Test backends listing when service is None."""
        with (
            patch("qiskit_ibm_runtime_mcp_server.ibm_runtime.service", None),
            patch(
                "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
            ) as mock_init,
        ):
            mock_init.side_effect = Exception("Service initialization failed")

            result = await list_backends()

            assert result["status"] == "error"
            assert "Failed to list backends" in result["message"]


class TestLeastBusyBackend:
    """Test least_busy_backend function."""

    @pytest.mark.asyncio
    async def test_least_busy_backend_success(self, mock_runtime_service):
        """Test successful least busy backend retrieval."""
        with (
            patch(
                "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
            ) as mock_init,
            patch(
                "qiskit_ibm_runtime_mcp_server.ibm_runtime.least_busy"
            ) as mock_least_busy,
        ):
            mock_init.return_value = mock_runtime_service

            # Create a mock backend for least_busy to return
            mock_backend = Mock()
            mock_backend.name = "ibm_brisbane"
            mock_backend.num_qubits = 127
            mock_backend.status.return_value = Mock(
                operational=True, pending_jobs=2, status_msg="active"
            )
            mock_least_busy.return_value = mock_backend

            result = await least_busy_backend()

            assert result["status"] == "success"
            assert result["backend_name"] == "ibm_brisbane"
            assert result["pending_jobs"] == 2
            assert result["operational"] is True

    @pytest.mark.asyncio
    async def test_least_busy_backend_no_operational(self, mock_runtime_service):
        """Test least busy backend when no operational backends available."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service
            mock_runtime_service.backends.return_value = []  # No operational backends

            result = await least_busy_backend()

            assert result["status"] == "error"
            assert "No quantum backends available" in result["message"]


class TestGetBackendProperties:
    """Test get_backend_properties function."""

    @pytest.mark.asyncio
    async def test_get_backend_properties_success(self, mock_runtime_service):
        """Test successful backend properties retrieval."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            # Mock backend configuration
            mock_config = Mock()
            mock_config.coupling_map = [[0, 1], [1, 2]]
            mock_config.basis_gates = ["cx", "id", "rz"]
            mock_config.max_shots = 8192
            mock_config.max_experiments = 300

            mock_backend = mock_runtime_service.backend.return_value
            mock_backend.configuration.return_value = mock_config

            result = await get_backend_properties("ibm_brisbane")

            assert result["status"] == "success"
            assert "backend_name" in result
            assert result["backend_name"] == "ibm_brisbane"
            assert result["coupling_map"] == [[0, 1], [1, 2]]
            assert result["basis_gates"] == ["cx", "id", "rz"]

    @pytest.mark.asyncio
    async def test_get_backend_properties_failure(self):
        """Test backend properties retrieval failure."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.side_effect = Exception("Service initialization failed")

            result = await get_backend_properties("nonexistent_backend")

            assert result["status"] == "error"
            assert "Failed to get backend properties" in result["message"]

    @pytest.mark.asyncio
    async def test_get_backend_properties_processor_type_string(
        self, mock_runtime_service
    ):
        """Test properties includes processor_type when it's a string."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            mock_config = Mock()
            mock_config.coupling_map = [[0, 1]]
            mock_config.basis_gates = ["cx", "id", "rz"]
            mock_config.max_shots = 8192
            mock_config.max_experiments = 300
            mock_config.processor_type = "Heron"
            mock_config.backend_version = "2.0.0"

            mock_backend = mock_runtime_service.backend.return_value
            mock_backend.configuration.return_value = mock_config

            result = await get_backend_properties("ibm_brisbane")

            assert result["status"] == "success"
            assert result["processor_type"] == "Heron"
            assert result["backend_version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_get_backend_properties_processor_type_dict(
        self, mock_runtime_service
    ):
        """Test properties handles processor_type as dict with family and revision."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            mock_config = Mock()
            mock_config.coupling_map = [[0, 1]]
            mock_config.basis_gates = ["cx", "id", "rz"]
            mock_config.max_shots = 8192
            mock_config.max_experiments = 300
            mock_config.processor_type = {"family": "Eagle", "revision": "3"}
            mock_config.backend_version = "1.5.2"

            mock_backend = mock_runtime_service.backend.return_value
            mock_backend.configuration.return_value = mock_config

            result = await get_backend_properties("ibm_brisbane")

            assert result["status"] == "success"
            assert result["processor_type"] == "Eagle r3"
            assert result["backend_version"] == "1.5.2"

    @pytest.mark.asyncio
    async def test_get_backend_properties_missing_config_attrs(
        self, mock_runtime_service
    ):
        """Test properties handles missing config attributes gracefully."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            mock_config = Mock(spec=[])  # Empty spec means no attributes
            mock_config.coupling_map = [[0, 1]]
            mock_config.basis_gates = ["cx", "id", "rz"]
            mock_config.max_shots = 8192
            mock_config.max_experiments = 300
            # Don't set processor_type or backend_version

            mock_backend = mock_runtime_service.backend.return_value
            mock_backend.configuration.return_value = mock_config

            result = await get_backend_properties("ibm_brisbane")

            assert result["status"] == "success"
            # Should have the keys but with None values
            assert result["processor_type"] is None
            assert result["backend_version"] is None


class TestListMyJobs:
    """Test list_my_jobs function."""

    @pytest.mark.asyncio
    async def test_list_my_jobs_success(self, mock_runtime_service):
        """Test successful jobs listing."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            result = await list_my_jobs(5)

            assert result["status"] == "success"
            assert result["total_jobs"] == 1
            assert len(result["jobs"]) == 1

            job = result["jobs"][0]
            assert job["job_id"] == "job_123"
            assert job["status"] == "DONE"

    @pytest.mark.asyncio
    async def test_list_my_jobs_default_limit(self, mock_runtime_service):
        """Test jobs listing with default limit."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            result = await list_my_jobs()

            assert result["status"] == "success"
            # Check that the service was called with default limit
            mock_runtime_service.jobs.assert_called_with(limit=10)


class TestGetJobStatus:
    """Test get_job_status function."""

    @pytest.mark.asyncio
    async def test_get_job_status_success(self, mock_runtime_service):
        """Test successful job status retrieval."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.service", mock_runtime_service
        ):
            result = await get_job_status("job_123")

            assert result["status"] == "success"
            assert result["job_id"] == "job_123"
            assert result["job_status"] == "DONE"

    @pytest.mark.asyncio
    async def test_get_job_status_no_service(self, mock_runtime_service):
        """Test job status auto-initializes service when None."""
        with (
            patch("qiskit_ibm_runtime_mcp_server.ibm_runtime.service", None),
            patch(
                "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
            ) as mock_init,
        ):
            mock_init.return_value = mock_runtime_service
            result = await get_job_status("job_123")

            mock_init.assert_called_once()
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_job_status_job_not_found(self, mock_runtime_service):
        """Test job status retrieval for non-existent job."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.service", mock_runtime_service
        ):
            mock_runtime_service.job.side_effect = Exception("Job not found")

            result = await get_job_status("nonexistent_job")

            assert result["status"] == "error"
            assert "Failed to get job status" in result["message"]


class TestGetJobResults:
    """Test get_job_results function."""

    @pytest.mark.asyncio
    async def test_get_job_results_success(self, mock_runtime_service):
        """Test successful job results retrieval."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.service", mock_runtime_service
        ):
            result = await get_job_results("job_123")

            assert result["status"] == "success"
            assert result["job_id"] == "job_123"
            assert result["job_status"] == "DONE"
            assert result["counts"] == {"00": 2048, "11": 2048}
            assert result["shots"] == 4096
            assert result["backend"] == "ibm_brisbane"
            assert result["execution_time"] == 1.5

    @pytest.mark.asyncio
    async def test_get_job_results_no_service(self, mock_runtime_service):
        """Test job results auto-initializes service when None."""
        with (
            patch("qiskit_ibm_runtime_mcp_server.ibm_runtime.service", None),
            patch(
                "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
            ) as mock_init,
        ):
            mock_init.return_value = mock_runtime_service
            result = await get_job_results("job_123")

            mock_init.assert_called_once()
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_get_job_results_job_pending(self, mock_runtime_service):
        """Test job results retrieval for pending job."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.service", mock_runtime_service
        ):
            mock_job = mock_runtime_service.job.return_value
            mock_job.status.return_value = "RUNNING"

            result = await get_job_results("job_123")

            assert result["status"] == "pending"
            assert result["job_status"] == "RUNNING"
            assert "still running" in result["message"]

    @pytest.mark.asyncio
    async def test_get_job_results_job_queued(self, mock_runtime_service):
        """Test job results retrieval for queued job."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.service", mock_runtime_service
        ):
            mock_job = mock_runtime_service.job.return_value
            mock_job.status.return_value = "QUEUED"

            result = await get_job_results("job_123")

            assert result["status"] == "pending"
            assert result["job_status"] == "QUEUED"
            assert "still queued" in result["message"]

    @pytest.mark.asyncio
    async def test_get_job_results_job_initializing(self, mock_runtime_service):
        """Test job results retrieval for initializing job."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.service", mock_runtime_service
        ):
            mock_job = mock_runtime_service.job.return_value
            mock_job.status.return_value = "INITIALIZING"

            result = await get_job_results("job_123")

            assert result["status"] == "pending"
            assert result["job_status"] == "INITIALIZING"
            assert "still initializing" in result["message"]

    @pytest.mark.asyncio
    async def test_get_job_results_job_failed(self, mock_runtime_service):
        """Test job results retrieval for failed job."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.service", mock_runtime_service
        ):
            mock_job = mock_runtime_service.job.return_value
            mock_job.status.return_value = "ERROR"
            mock_job.error_message.return_value = "Circuit validation failed"

            result = await get_job_results("job_123")

            assert result["status"] == "error"
            assert result["job_status"] == "ERROR"
            assert "Circuit validation failed" in result["message"]

    @pytest.mark.asyncio
    async def test_get_job_results_job_cancelled(self, mock_runtime_service):
        """Test job results retrieval for cancelled job."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.service", mock_runtime_service
        ):
            mock_job = mock_runtime_service.job.return_value
            mock_job.status.return_value = "CANCELLED"

            result = await get_job_results("job_123")

            assert result["status"] == "error"
            assert result["job_status"] == "CANCELLED"
            assert "cancelled" in result["message"]

    @pytest.mark.asyncio
    async def test_get_job_results_job_not_found(self, mock_runtime_service):
        """Test job results retrieval for non-existent job."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.service", mock_runtime_service
        ):
            mock_runtime_service.job.side_effect = Exception("Job not found")

            result = await get_job_results("nonexistent_job")

            assert result["status"] == "error"
            assert "Failed to get job results" in result["message"]


class TestCancelJob:
    """Test cancel_job function."""

    @pytest.mark.asyncio
    async def test_cancel_job_success(self, mock_runtime_service):
        """Test successful job cancellation."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.service", mock_runtime_service
        ):
            result = await cancel_job("job_123")

            assert result["status"] == "success"
            assert result["job_id"] == "job_123"
            assert "cancellation requested" in result["message"]

    @pytest.mark.asyncio
    async def test_cancel_job_no_service(self, mock_runtime_service):
        """Test job cancellation auto-initializes service when None."""
        with (
            patch("qiskit_ibm_runtime_mcp_server.ibm_runtime.service", None),
            patch(
                "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
            ) as mock_init,
        ):
            mock_init.return_value = mock_runtime_service
            result = await cancel_job("job_123")

            mock_init.assert_called_once()
            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_cancel_job_failure(self, mock_runtime_service):
        """Test job cancellation failure."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.service", mock_runtime_service
        ):
            mock_job = mock_runtime_service.job.return_value
            mock_job.cancel.side_effect = Exception("Cannot cancel job")

            result = await cancel_job("job_123")

            assert result["status"] == "error"
            assert "Failed to cancel job" in result["message"]


class TestGetServiceStatus:
    """Test get_service_status function."""

    @pytest.mark.asyncio
    async def test_get_service_status_connected(self, mock_runtime_service):
        """Test service status when connected."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            result = await get_service_status()

            assert "IBM Quantum Service Status" in result
            assert "connected" in result.lower()

    @pytest.mark.asyncio
    async def test_get_service_status_disconnected(self):
        """Test service status when disconnected."""
        with (
            patch("qiskit_ibm_runtime_mcp_server.ibm_runtime.service", None),
            patch(
                "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
            ) as mock_init,
        ):
            mock_init.side_effect = Exception("Connection failed")

            result = await get_service_status()

            assert "IBM Quantum Service Status" in result
            assert "error" in result


class TestGetBackendCalibration:
    """Test get_backend_calibration function."""

    @pytest.mark.asyncio
    async def test_get_calibration_success(self, mock_runtime_service):
        """Test successful calibration data retrieval."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            # Mock backend properties (calibration data)
            mock_properties = Mock()
            mock_properties.t1.return_value = 150.5  # microseconds
            mock_properties.t2.return_value = 80.2  # microseconds
            mock_properties.readout_error.return_value = 0.015
            mock_properties.prob_meas0_prep1.return_value = 0.012
            mock_properties.prob_meas1_prep0.return_value = 0.018
            mock_properties.gate_error.return_value = 0.001
            mock_properties.last_update_date = "2024-01-15T10:00:00Z"

            # Mock backend configuration
            mock_config = Mock()
            mock_config.coupling_map = [[0, 1], [1, 2], [2, 3]]

            mock_backend = mock_runtime_service.backend.return_value
            mock_backend.properties.return_value = mock_properties
            mock_backend.configuration.return_value = mock_config

            result = await get_backend_calibration("ibm_brisbane")

            assert result["status"] == "success"
            assert result["backend_name"] == "ibm_brisbane"
            assert "qubit_calibration" in result
            assert "gate_errors" in result
            assert "last_calibration" in result
            assert len(result["qubit_calibration"]) > 0

            # Check qubit data
            qubit_data = result["qubit_calibration"][0]
            assert "t1_us" in qubit_data
            assert "t2_us" in qubit_data
            assert "readout_error" in qubit_data

    @pytest.mark.asyncio
    async def test_get_calibration_specific_qubits(self, mock_runtime_service):
        """Test calibration data for specific qubits."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            mock_properties = Mock()
            mock_properties.t1.return_value = 100.0
            mock_properties.t2.return_value = 50.0
            mock_properties.readout_error.return_value = 0.02
            mock_properties.prob_meas0_prep1.return_value = None
            mock_properties.prob_meas1_prep0.return_value = None
            mock_properties.gate_error.return_value = 0.001
            mock_properties.last_update_date = "2024-01-15T10:00:00Z"

            mock_config = Mock()
            mock_config.coupling_map = [[0, 1]]

            mock_backend = mock_runtime_service.backend.return_value
            mock_backend.properties.return_value = mock_properties
            mock_backend.configuration.return_value = mock_config

            result = await get_backend_calibration(
                "ibm_brisbane", qubit_indices=[0, 5, 10]
            )

            assert result["status"] == "success"
            # Should have data for requested qubits (filtered by num_qubits)
            assert len(result["qubit_calibration"]) <= 3

    @pytest.mark.asyncio
    async def test_get_calibration_no_properties(self, mock_runtime_service):
        """Test calibration when properties are not available (e.g., simulator)."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            mock_backend = mock_runtime_service.backend.return_value
            mock_backend.properties.return_value = None

            result = await get_backend_calibration("ibmq_qasm_simulator")

            assert result["status"] == "error"
            assert "No calibration data available" in result["message"]

    @pytest.mark.asyncio
    async def test_get_calibration_properties_exception(self, mock_runtime_service):
        """Test calibration when properties() raises an exception."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            mock_backend = mock_runtime_service.backend.return_value
            mock_backend.properties.side_effect = Exception("Properties not available")

            result = await get_backend_calibration("ibm_brisbane")

            assert result["status"] == "error"
            assert "Calibration data not available" in result["message"]

    @pytest.mark.asyncio
    async def test_get_calibration_service_failure(self):
        """Test calibration when service initialization fails."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.side_effect = Exception("Service initialization failed")

            result = await get_backend_calibration("ibm_brisbane")

            assert result["status"] == "error"
            assert "Failed to get backend calibration" in result["message"]

    @pytest.mark.asyncio
    async def test_get_calibration_partial_data(self, mock_runtime_service):
        """Test calibration when some data points are missing."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            # Mock properties where some methods raise exceptions
            mock_properties = Mock()
            mock_properties.t1.return_value = 120.0
            mock_properties.t2.side_effect = Exception("T2 not available")
            mock_properties.readout_error.return_value = 0.01
            mock_properties.prob_meas0_prep1.side_effect = Exception("Not available")
            mock_properties.prob_meas1_prep0.side_effect = Exception("Not available")
            mock_properties.gate_error.side_effect = Exception("Not available")
            mock_properties.last_update_date = None
            mock_properties.faulty_qubits.return_value = []
            mock_properties.faulty_gates.return_value = []
            mock_properties.frequency.side_effect = Exception("Not available")

            mock_config = Mock()
            mock_config.coupling_map = []

            mock_backend = mock_runtime_service.backend.return_value
            mock_backend.properties.return_value = mock_properties
            mock_backend.configuration.return_value = mock_config

            result = await get_backend_calibration("ibm_brisbane")

            assert result["status"] == "success"
            # Should still return partial data
            qubit_data = result["qubit_calibration"][0]
            assert qubit_data["t1_us"] is not None
            assert qubit_data["t2_us"] is None  # Was exception

    @pytest.mark.asyncio
    async def test_get_calibration_faulty_qubits(self, mock_runtime_service):
        """Test calibration includes faulty_qubits data."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            mock_properties = Mock()
            mock_properties.t1.return_value = 100.0
            mock_properties.t2.return_value = 50.0
            mock_properties.readout_error.return_value = 0.02
            mock_properties.prob_meas0_prep1.return_value = None
            mock_properties.prob_meas1_prep0.return_value = None
            mock_properties.gate_error.return_value = 0.001
            mock_properties.frequency.return_value = 5.0e9  # 5 GHz in Hz
            mock_properties.last_update_date = "2024-01-15T10:00:00Z"
            mock_properties.faulty_qubits.return_value = [3, 7, 15]
            mock_properties.faulty_gates.return_value = []

            mock_config = Mock()
            mock_config.coupling_map = [[0, 1]]

            mock_backend = mock_runtime_service.backend.return_value
            mock_backend.properties.return_value = mock_properties
            mock_backend.configuration.return_value = mock_config

            result = await get_backend_calibration("ibm_brisbane")

            assert result["status"] == "success"
            assert "faulty_qubits" in result
            assert result["faulty_qubits"] == [3, 7, 15]

    @pytest.mark.asyncio
    async def test_get_calibration_faulty_gates(self, mock_runtime_service):
        """Test calibration includes faulty_gates data."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            mock_properties = Mock()
            mock_properties.t1.return_value = 100.0
            mock_properties.t2.return_value = 50.0
            mock_properties.readout_error.return_value = 0.02
            mock_properties.prob_meas0_prep1.return_value = None
            mock_properties.prob_meas1_prep0.return_value = None
            mock_properties.gate_error.return_value = 0.001
            mock_properties.frequency.return_value = 5.0e9
            mock_properties.last_update_date = "2024-01-15T10:00:00Z"
            mock_properties.faulty_qubits.return_value = []

            # Mock faulty gates
            mock_faulty_gate = Mock()
            mock_faulty_gate.gate = "cx"
            mock_faulty_gate.qubits = [5, 6]
            mock_properties.faulty_gates.return_value = [mock_faulty_gate]

            mock_config = Mock()
            mock_config.coupling_map = [[0, 1]]

            mock_backend = mock_runtime_service.backend.return_value
            mock_backend.properties.return_value = mock_properties
            mock_backend.configuration.return_value = mock_config

            result = await get_backend_calibration("ibm_brisbane")

            assert result["status"] == "success"
            assert "faulty_gates" in result
            assert len(result["faulty_gates"]) == 1
            assert result["faulty_gates"][0]["gate"] == "cx"
            assert result["faulty_gates"][0]["qubits"] == [5, 6]

    @pytest.mark.asyncio
    async def test_get_calibration_frequency(self, mock_runtime_service):
        """Test calibration includes qubit frequency in GHz."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            mock_properties = Mock()
            mock_properties.t1.return_value = 100.0
            mock_properties.t2.return_value = 50.0
            mock_properties.readout_error.return_value = 0.02
            mock_properties.prob_meas0_prep1.return_value = None
            mock_properties.prob_meas1_prep0.return_value = None
            mock_properties.gate_error.return_value = 0.001
            mock_properties.frequency.return_value = 5.123456e9  # 5.123456 GHz in Hz
            mock_properties.last_update_date = "2024-01-15T10:00:00Z"
            mock_properties.faulty_qubits.return_value = []
            mock_properties.faulty_gates.return_value = []

            mock_config = Mock()
            mock_config.coupling_map = [[0, 1]]

            mock_backend = mock_runtime_service.backend.return_value
            mock_backend.properties.return_value = mock_properties
            mock_backend.configuration.return_value = mock_config

            result = await get_backend_calibration("ibm_brisbane")

            assert result["status"] == "success"
            qubit_data = result["qubit_calibration"][0]
            assert "frequency_ghz" in qubit_data
            assert qubit_data["frequency_ghz"] == 5.123456  # Converted to GHz

    @pytest.mark.asyncio
    async def test_get_calibration_operational_status(self, mock_runtime_service):
        """Test calibration marks qubits as non-operational if in faulty_qubits list."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service

            mock_properties = Mock()
            mock_properties.t1.return_value = 100.0
            mock_properties.t2.return_value = 50.0
            mock_properties.readout_error.return_value = 0.02
            mock_properties.prob_meas0_prep1.return_value = None
            mock_properties.prob_meas1_prep0.return_value = None
            mock_properties.gate_error.return_value = 0.001
            mock_properties.frequency.return_value = 5.0e9
            mock_properties.last_update_date = "2024-01-15T10:00:00Z"
            # Mark qubit 0 as faulty
            mock_properties.faulty_qubits.return_value = [0]
            mock_properties.faulty_gates.return_value = []

            mock_config = Mock()
            mock_config.coupling_map = [[0, 1]]

            mock_backend = mock_runtime_service.backend.return_value
            mock_backend.properties.return_value = mock_properties
            mock_backend.configuration.return_value = mock_config

            result = await get_backend_calibration("ibm_brisbane", qubit_indices=[0, 1])

            assert result["status"] == "success"
            qubit_data = result["qubit_calibration"]

            # Qubit 0 should be marked as non-operational (in faulty_qubits)
            qubit_0 = next(q for q in qubit_data if q["qubit"] == 0)
            assert qubit_0["operational"] is False

            # Qubit 1 should be operational (not in faulty_qubits)
            qubit_1 = next(q for q in qubit_data if q["qubit"] == 1)
            assert qubit_1["operational"] is True


class TestLegacyPrimitiveSubmissionRefusal:
    """Legacy direct primitives cannot bypass W1-08 approval."""

    @pytest.mark.asyncio
    async def test_estimator_refuses_before_runtime_access(self):
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as initialize:
            result = await run_estimator("OPENQASM 3.0;", "Z")

        assert result["status"] == "error"
        assert "ApprovalReceipt" in result["message"]
        initialize.assert_not_called()

    @pytest.mark.asyncio
    async def test_sampler_refuses_before_runtime_access(self):
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as initialize:
            result = await run_sampler("OPENQASM 3.0;")

        assert result["status"] == "error"
        assert "ApprovalReceipt" in result["message"]
        initialize.assert_not_called()


class TestListSavedAccounts:
    """Test list_saved_accounts function."""

    @pytest.mark.asyncio
    async def test_list_saved_accounts_success(self):
        """Test successful listing of saved accounts with token masking."""
        mock_accounts = {
            "ibm_quantum_platform": {
                "channel": "ibm_quantum",
                "url": "https://auth.quantum-computing.ibm.com/api",
                "token": "secret_token_abc123",
            },
            "custom_account": {
                "channel": "ibm_cloud",
                "url": "https://cloud.ibm.com",
                "token": "another_secret_xyz789",
            },
        }

        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.QiskitRuntimeService.saved_accounts"
        ) as mock_saved:
            mock_saved.return_value = mock_accounts

            result = await list_saved_accounts()

            assert result["status"] == "success"
            assert "accounts" in result
            # Secret-bearing fields are fully redacted; no suffix is disclosed.
            assert result["accounts"]["ibm_quantum_platform"]["token"] == "[REDACTED]"
            assert result["accounts"]["custom_account"]["token"] == "[REDACTED]"
            # Verify other fields are unchanged
            assert (
                result["accounts"]["ibm_quantum_platform"]["channel"] == "ibm_quantum"
            )
            assert result["accounts"]["custom_account"]["channel"] == "ibm_cloud"

    @pytest.mark.asyncio
    async def test_list_saved_accounts_empty(self):
        """Test listing saved accounts when none exist."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.QiskitRuntimeService.saved_accounts"
        ) as mock_saved:
            mock_saved.return_value = {}

            result = await list_saved_accounts()

            assert result["status"] == "success"
            assert result["accounts"] == {}
            assert "No accounts found" in result["message"]

    @pytest.mark.asyncio
    async def test_list_saved_accounts_exception(self):
        """Test listing saved accounts with exception."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.QiskitRuntimeService.saved_accounts"
        ) as mock_saved:
            mock_saved.side_effect = Exception("File not found")

            result = await list_saved_accounts()

            assert result["status"] == "error"
            assert "File not found" in result["message"]


class TestActiveAccountInfo:
    """Test active_account_info function."""

    @pytest.mark.asyncio
    async def test_active_account_info_success(self, mock_runtime_service):
        """Test successful retrieval of active account info."""
        mock_account = {
            "channel": "ibm_quantum",
            "url": "https://auth.quantum-computing.ibm.com/api",
            "token": "test_token_123",
            "verify": True,
            "private_endpoint": False,
        }

        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service
            mock_runtime_service.active_account.return_value = mock_account

            result = await active_account_info()

            assert result["status"] == "success"
            assert "account_info" in result
            assert result["account_info"]["channel"] == "ibm_quantum"
            assert result["account_info"]["url"] == mock_account["url"]
            assert result["account_info"]["token"] == "[REDACTED]"

    @pytest.mark.asyncio
    async def test_active_account_info_none_value(self, mock_runtime_service):
        """Test active account info when service returns None."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service
            mock_runtime_service.active_account.return_value = None

            result = await active_account_info()

            # Function returns success with None value (doesn't validate)
            assert result["status"] == "success"
            assert result["account_info"] is None

    @pytest.mark.asyncio
    async def test_active_account_info_exception(self, mock_runtime_service):
        """Test active account info with exception."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service
            mock_runtime_service.active_account.side_effect = Exception(
                "Service not initialized"
            )

            result = await active_account_info()

            assert result["status"] == "error"
            assert "Service not initialized" in result["message"]


class TestActiveInstanceInfo:
    """Test active_instance_info function."""

    @pytest.mark.asyncio
    async def test_active_instance_info_success(self, mock_runtime_service):
        """Test successful retrieval of active instance info."""
        mock_instance = "crn:v1:bluemix:public:quantum-computing:us-east:a/123:456::"

        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service
            mock_runtime_service.active_instance.return_value = mock_instance

            result = await active_instance_info()

            assert result["status"] == "success"
            assert result["instance_crn"] == mock_instance

    @pytest.mark.asyncio
    async def test_active_instance_info_none_value(self, mock_runtime_service):
        """Test active instance info when service returns None."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service
            mock_runtime_service.active_instance.return_value = None

            result = await active_instance_info()

            # Function returns success with None value (doesn't validate)
            assert result["status"] == "success"
            assert result["instance_crn"] is None

    @pytest.mark.asyncio
    async def test_active_instance_info_exception(self, mock_runtime_service):
        """Test active instance info with exception."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service
            mock_runtime_service.active_instance.side_effect = Exception(
                "Instance lookup failed"
            )

            result = await active_instance_info()

            assert result["status"] == "error"
            assert "Instance lookup failed" in result["message"]


class TestAvailableInstances:
    """Test available_instances function."""

    @pytest.mark.asyncio
    async def test_available_instances_success(self, mock_runtime_service):
        """Test successful retrieval of available instances."""
        mock_instances = [
            {
                "crn": "crn:v1:bluemix:public:quantum-computing:us-east:a/123:456::",
                "plan": "open",
                "name": "My Instance",
                "tags": [],
                "pricing_type": "free",
            },
            {
                "crn": "crn:v1:bluemix:public:quantum-computing:us-east:a/123:789::",
                "plan": "premium",
                "name": "Premium Instance",
                "tags": ["production"],
                "pricing_type": "paid",
            },
        ]

        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service
            mock_runtime_service.instances.return_value = mock_instances

            result = await available_instances()

            assert result["status"] == "success"
            assert "instances" in result
            assert result["total_instances"] == 2
            assert len(result["instances"]) == 2
            assert result["instances"][0]["plan"] == "open"
            assert result["instances"][1]["plan"] == "premium"

    @pytest.mark.asyncio
    async def test_available_instances_empty(self, mock_runtime_service):
        """Test available instances when none exist."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service
            mock_runtime_service.instances.return_value = []

            result = await available_instances()

            assert result["status"] == "success"
            assert result["instances"] == []
            assert result["total_instances"] == 0

    @pytest.mark.asyncio
    async def test_available_instances_exception(self, mock_runtime_service):
        """Test available instances with exception."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service
            mock_runtime_service.instances.side_effect = Exception(
                "Failed to fetch instances"
            )

            result = await available_instances()

            assert result["status"] == "error"
            assert "Failed to fetch instances" in result["message"]


class TestUsageInfo:
    """Test usage_info function."""

    @pytest.mark.asyncio
    async def test_usage_info_success(self, mock_runtime_service):
        """Test successful retrieval of usage information."""
        mock_usage = {
            "instance_id": "crn:v1:bluemix:public:quantum-computing:us-east:a/123:456::",
            "plan_id": "open",
            "usage_consumed_seconds": 3600,
            "usage_period": "2025-01",
            "usage_limit_seconds": 36000,
            "usage_limit_reached": False,
            "usage_remaining_seconds": 32400,
        }

        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service
            mock_runtime_service.usage.return_value = mock_usage

            result = await usage_info()

            assert result["status"] == "success"
            assert "usage" in result
            assert result["usage"]["usage_consumed_seconds"] == 3600
            assert result["usage"]["usage_limit_reached"] is False
            assert result["usage"]["usage_remaining_seconds"] == 32400

    @pytest.mark.asyncio
    async def test_usage_info_limit_reached(self, mock_runtime_service):
        """Test usage info when limit is reached."""
        mock_usage = {
            "instance_id": "crn:v1:bluemix:public:quantum-computing:us-east:a/123:456::",
            "plan_id": "open",
            "usage_consumed_seconds": 36000,
            "usage_period": "2025-01",
            "usage_limit_seconds": 36000,
            "usage_limit_reached": True,
            "usage_remaining_seconds": 0,
        }

        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service
            mock_runtime_service.usage.return_value = mock_usage

            result = await usage_info()

            assert result["status"] == "success"
            assert result["usage"]["usage_limit_reached"] is True
            assert result["usage"]["usage_remaining_seconds"] == 0

    @pytest.mark.asyncio
    async def test_usage_info_exception(self, mock_runtime_service):
        """Test usage info with exception."""
        with patch(
            "qiskit_ibm_runtime_mcp_server.ibm_runtime.initialize_service"
        ) as mock_init:
            mock_init.return_value = mock_runtime_service
            mock_runtime_service.usage.side_effect = Exception("Usage data unavailable")

            result = await usage_info()

            assert result["status"] == "error"
            assert "Usage data unavailable" in result["message"]


class TestAccountManagementToolsExist:
    """Test that MCP tool wrappers for account management are properly registered."""

    def test_list_saved_accounts_tool_exists(self):
        """Test list_saved_accounts_tool is registered as MCP tool."""
        assert list_saved_accounts_tool is not None
        assert callable(list_saved_accounts_tool)

    def test_active_account_info_tool_exists(self):
        """Test active_account_info_tool is registered as MCP tool."""
        assert active_account_info_tool is not None
        assert callable(active_account_info_tool)

    def test_active_instance_info_tool_exists(self):
        """Test active_instance_info_tool is registered as MCP tool."""
        assert active_instance_info_tool is not None
        assert callable(active_instance_info_tool)

    def test_available_instances_tool_exists(self):
        """Test available_instances_tool is registered as MCP tool."""
        assert available_instances_tool is not None
        assert callable(available_instances_tool)

    def test_usage_info_tool_exists(self):
        """Test usage_info_tool is registered as MCP tool."""
        assert usage_info_tool is not None
        assert callable(usage_info_tool)


class TestExampleCircuits:
    """Test example circuit functions for LLM usability."""

    def test_bell_state_circuit_structure(self):
        """Test Bell state circuit has correct structure."""
        result = get_bell_state_circuit()

        assert "circuit" in result
        assert "name" in result
        assert "description" in result
        assert "expected_results" in result
        assert "num_qubits" in result
        assert "usage" in result

        assert result["name"] == "Bell State"
        assert result["num_qubits"] == 2
        assert "entanglement" in result["description"].lower()

    def test_bell_state_circuit_valid_qasm3(self):
        """Test Bell state circuit is valid QASM3."""
        result = get_bell_state_circuit()
        circuit = result["circuit"]

        assert "OPENQASM 3.0" in circuit
        assert 'include "stdgates.inc"' in circuit
        assert "qubit[2]" in circuit
        assert "bit[2]" in circuit
        assert "h q[0]" in circuit
        assert "cx q[0], q[1]" in circuit
        assert "measure" in circuit

    def test_ghz_state_circuit_default(self):
        """Test GHZ state circuit with default 3 qubits."""
        result = get_ghz_state_circuit()

        assert result["num_qubits"] == 3
        assert "GHZ" in result["name"]
        assert "000" in result["expected_results"]
        assert "111" in result["expected_results"]

    def test_ghz_state_circuit_custom_qubits(self):
        """Test GHZ state circuit with custom qubit count."""
        result = get_ghz_state_circuit(5)

        assert result["num_qubits"] == 5
        assert "5-qubit" in result["name"]
        assert "00000" in result["expected_results"]
        assert "11111" in result["expected_results"]

        circuit = result["circuit"]
        assert "qubit[5]" in circuit
        assert "bit[5]" in circuit
        # Should have 4 CNOT gates for 5 qubits
        assert circuit.count("cx q[") == 4

    def test_ghz_state_circuit_min_qubits(self):
        """Test GHZ state circuit enforces minimum 2 qubits."""
        result = get_ghz_state_circuit(1)
        assert result["num_qubits"] == 2

    def test_ghz_state_circuit_max_qubits(self):
        """Test GHZ state circuit enforces maximum 10 qubits."""
        result = get_ghz_state_circuit(15)
        assert result["num_qubits"] == 10

    def test_quantum_random_circuit_structure(self):
        """Test quantum random circuit has correct structure."""
        result = get_quantum_random_circuit()

        assert result["name"] == "Quantum Random Number Generator"
        assert result["num_qubits"] == 4
        assert "random" in result["description"].lower()
        assert "16" in result["expected_results"]  # 16 possible outcomes

    def test_quantum_random_circuit_valid_qasm3(self):
        """Test quantum random circuit is valid QASM3."""
        result = get_quantum_random_circuit()
        circuit = result["circuit"]

        assert "OPENQASM 3.0" in circuit
        assert "qubit[4]" in circuit
        # Should have 4 Hadamard gates
        assert circuit.count("h q[") == 4
        assert "measure" in circuit

    def test_superposition_circuit_structure(self):
        """Test superposition circuit has correct structure."""
        result = get_superposition_circuit()

        assert result["name"] == "Single Qubit Superposition"
        assert result["num_qubits"] == 1
        assert "simplest" in result["description"].lower()
        assert "50%" in result["expected_results"]

    def test_superposition_circuit_valid_qasm3(self):
        """Test superposition circuit is valid QASM3."""
        result = get_superposition_circuit()
        circuit = result["circuit"]

        assert "OPENQASM 3.0" in circuit
        assert "qubit[1]" in circuit
        assert "bit[1]" in circuit
        assert "h q[0]" in circuit
        assert "measure" in circuit

    def test_all_circuits_have_usage_instructions(self):
        """Test all example circuits include usage instructions."""
        circuits = [
            get_bell_state_circuit(),
            get_ghz_state_circuit(),
            get_quantum_random_circuit(),
            get_superposition_circuit(),
        ]

        for circuit in circuits:
            assert "usage" in circuit
            assert "run_sampler_tool" in circuit["usage"]


class TestServerRegistration:
    """Test that tools, resources, prompts, and templates are registered."""

    def test_server_name(self):
        """Test the server name is correct."""
        assert mcp.name == "Qiskit IBM Runtime"

    async def test_resources_registered(self):
        """Test that all expected static resources are registered."""
        resources = await mcp.list_resources()
        resource_uris = {str(r.uri) for r in resources}
        expected_resources = {
            "ibm://status",
            "circuits://bell-state",
            "circuits://ghz-state",
            "circuits://random",
            "circuits://superposition",
        }
        assert expected_resources.issubset(resource_uris), (
            f"Missing resources: {expected_resources - resource_uris}"
        )

    async def test_resource_count(self):
        """Test the expected number of static resources."""
        resources = await mcp.list_resources()
        assert len(resources) == 5

    async def test_prompts_registered(self):
        """Test that all expected prompts are registered."""
        prompts = await mcp.list_prompts()
        prompt_names = {p.name for p in prompts}
        expected_prompts = {"run_bell_state", "explore_backend", "monitor_job"}
        assert expected_prompts.issubset(prompt_names), (
            f"Missing prompts: {expected_prompts - prompt_names}"
        )

    async def test_prompt_count(self):
        """Test the expected number of prompts."""
        prompts = await mcp.list_prompts()
        assert len(prompts) == 3

    async def test_resource_templates_registered(self):
        """Test that all expected resource templates are registered."""
        templates = await mcp.list_resource_templates()
        template_uris = {str(t.uri_template) for t in templates}
        expected_templates = {
            "ibm://backends/{backend_name}",
            "ibm://jobs/{job_id}",
        }
        assert expected_templates.issubset(template_uris), (
            f"Missing resource templates: {expected_templates - template_uris}"
        )

    async def test_resource_template_count(self):
        """Test the expected number of resource templates."""
        templates = await mcp.list_resource_templates()
        assert len(templates) == 2


# Assisted by watsonx Code Assistant
