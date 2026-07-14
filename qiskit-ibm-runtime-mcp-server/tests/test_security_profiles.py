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

"""Registration and negative-security tests for the research profile."""

import inspect
import logging
import os
from unittest.mock import patch

import pytest

from qiskit_ibm_runtime_mcp_server import ibm_runtime
from qiskit_ibm_runtime_mcp_server.profiles import (
    DEFAULT_TOOL_PROFILE,
    RESEARCH_TOOL_NAMES,
    ToolProfile,
)
from qiskit_ibm_runtime_mcp_server.security import (
    REDACTED,
    install_secret_redaction,
    redact_data,
    redact_text,
)
from qiskit_ibm_runtime_mcp_server.server import mcp, tool_profile
from qiskit_ibm_runtime_mcp_server.utils import with_sync


@pytest.mark.asyncio
async def test_research_profile_registers_exact_allowlist() -> None:
    """The concrete FastMCP registration must match the security manifest."""
    tools = await mcp.list_tools()
    registered = {tool.name for tool in tools}

    assert tool_profile is DEFAULT_TOOL_PROFILE is ToolProfile.RESEARCH
    assert registered == RESEARCH_TOOL_NAMES


@pytest.mark.asyncio
async def test_research_tool_schemas_have_no_secret_arguments() -> None:
    """No registered tool may accept credential material."""
    forbidden = {"token", "api_key", "apikey", "password", "secret", "credential"}

    for tool in await mcp.list_tools():
        argument_names = {
            str(name).lower() for name in tool.parameters.get("properties", {})
        }
        assert argument_names.isdisjoint(forbidden), tool.name


@pytest.mark.asyncio
async def test_legacy_submission_tools_advertise_the_disabled_approval_path() -> None:
    """FastMCP descriptions must not promise submission through disabled stubs."""
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    for name in ("run_sampler_tool", "run_estimator_tool"):
        description = tools[name].description or ""
        assert "without submitting" in description
        assert "deprecated compatibility stub" in description
        assert "ApprovalReceipt" in description
        assert "ApprovedBatchExecutor" in description
        assert "Jobs run asynchronously" not in description
        assert "Job submission status" not in description


def test_no_admin_or_account_mutation_profile_is_available() -> None:
    """Administrative credential operations are intentionally not shipped."""
    assert {profile.value for profile in ToolProfile} == {"research"}
    assert not hasattr(ibm_runtime, "setup_ibm_quantum_account")
    assert not hasattr(ibm_runtime, "delete_saved_account")
    assert not any(
        marker in name
        for name in RESEARCH_TOOL_NAMES
        for marker in ("setup", "save_account", "delete_account", "delete_saved")
    )


def test_registered_wrappers_have_no_token_parameter() -> None:
    """The ordinary Python adapter surface mirrors the MCP schema contract."""
    import qiskit_ibm_runtime_mcp_server.server as server

    for name in RESEARCH_TOOL_NAMES:
        parameters = inspect.signature(getattr(server, name)).parameters
        assert "token" not in parameters, name


def test_runtime_instance_is_required_before_client_construction() -> None:
    """Missing instance configuration fails closed without touching Runtime."""
    with (
        patch.dict(os.environ, {}, clear=True),
        patch.object(ibm_runtime, "QiskitRuntimeService") as runtime_service,
        pytest.raises(ValueError, match="explicit IBM Quantum Runtime instance"),
    ):
        ibm_runtime.initialize_service()

    runtime_service.assert_not_called()


def test_environment_authentication_is_ephemeral() -> None:
    """Environment credentials are passed in memory and never saved to disk."""
    sensitive_value = "sensitive-" + ("x" * 32)
    with (
        patch.dict(
            os.environ,
            {
                "QISKIT_IBM_RUNTIME_MCP_INSTANCE": "test-instance",
                "QISKIT_IBM_TOKEN": sensitive_value,
            },
            clear=True,
        ),
        patch.object(ibm_runtime, "QiskitRuntimeService") as runtime_service,
    ):
        ibm_runtime.initialize_service()

    runtime_service.assert_called_once_with(
        channel="ibm_quantum_platform",
        instance="test-instance",
        token=sensitive_value,
    )
    runtime_service.save_account.assert_not_called()


def test_saved_credentials_are_used_without_credential_arguments() -> None:
    """Omitting the environment secret delegates to Qiskit's saved credentials."""
    with (
        patch.dict(
            os.environ,
            {"QISKIT_IBM_RUNTIME_MCP_INSTANCE": "test-instance"},
            clear=True,
        ),
        patch.object(ibm_runtime, "QiskitRuntimeService") as runtime_service,
    ):
        ibm_runtime.initialize_service()

    runtime_service.assert_called_once_with(
        channel="ibm_quantum_platform", instance="test-instance"
    )
    runtime_service.save_account.assert_not_called()


def test_secret_redaction_covers_strings_and_nested_fields() -> None:
    """Token-like values cannot cross the public result boundary."""
    sensitive_value = "sensitive-" + ("y" * 32)
    text = redact_text(f"request failed: token={sensitive_value}")
    data = redact_data(
        {
            "account": {
                "token": sensitive_value,
                "client_secret": sensitive_value,
                "refresh-token": sensitive_value,
            },
            "message": f"Authorization: Bearer {sensitive_value}",
        }
    )

    assert sensitive_value not in text
    assert sensitive_value not in str(data)
    assert data["account"]["token"] == REDACTED
    assert data["account"]["client_secret"] == REDACTED
    assert data["account"]["refresh-token"] == REDACTED
    assert REDACTED in data["message"]


def test_secret_redaction_filter_sanitizes_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Secret-bearing exception text is sanitized before handler emission."""
    sensitive_value = "sensitive-" + ("z" * 32)
    test_logger = logging.getLogger("qiskit-runtime-security-test")
    install_secret_redaction(test_logger)

    with (
        patch.dict(os.environ, {"QISKIT_IBM_TOKEN": sensitive_value}),
        caplog.at_level(logging.ERROR, logger=test_logger.name),
    ):
        test_logger.error("authentication failed for %s", sensitive_value)

    assert sensitive_value not in caplog.text
    assert REDACTED in caplog.text


@pytest.mark.asyncio
async def test_public_async_boundary_strips_secret_exception_chain() -> None:
    """Unexpected failures are sanitized and detached from their original cause."""
    sensitive_value = "sensitive-" + ("q" * 32)

    @with_sync
    async def failing_operation() -> dict[str, str]:
        raise ValueError(f"request rejected for {sensitive_value}")

    with (
        patch.dict(os.environ, {"QISKIT_IBM_TOKEN": sensitive_value}),
        pytest.raises(RuntimeError) as exc_info,
    ):
        await failing_operation()

    assert sensitive_value not in str(exc_info.value)
    assert REDACTED in str(exc_info.value)
    assert exc_info.value.__cause__ is None
