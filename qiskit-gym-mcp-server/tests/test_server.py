# This code is part of Qiskit.
#
# (C) Copyright IBM 2026.
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

"""Tests for MCP server registration and configuration."""

from qiskit_gym_mcp_server.server import mcp


class TestServerRegistration:
    """Test that tools, resources, prompts, and templates are registered."""

    def test_server_name(self):
        """Test the server name is correct."""
        assert mcp.name == "Qiskit Gym"

    def test_server_instructions(self):
        """Test the MCP server has instructions set."""
        assert mcp.instructions is not None
        assert isinstance(mcp.instructions, str)
        assert len(mcp.instructions) > 0
        # Verify instructions mention key workflow concepts
        assert "create_permutation_env_tool" in mcp.instructions
        assert "start_training_tool" in mcp.instructions
        assert "synthesize_permutation_tool" in mcp.instructions
        assert "qiskit-gym://" in mcp.instructions

    async def test_resources_registered(self):
        """Test that all expected static resources are registered."""
        resources = await mcp.list_resources()
        resource_uris = {str(r.uri) for r in resources}
        expected_resources = {
            "qiskit-gym://presets/coupling-maps",
            "qiskit-gym://algorithms",
            "qiskit-gym://policies",
            "qiskit-gym://environments",
            "qiskit-gym://training/sessions",
            "qiskit-gym://models",
            "qiskit-gym://server/config",
            "qiskit-gym://workflows",
        }
        assert expected_resources.issubset(resource_uris), (
            f"Missing resources: {expected_resources - resource_uris}"
        )

    async def test_resource_count(self):
        """Test the expected number of static resources."""
        resources = await mcp.list_resources()
        assert len(resources) == 8

    async def test_prompts_registered(self):
        """Test that all expected prompts are registered."""
        prompts = await mcp.list_prompts()
        prompt_names = {p.name for p in prompts}
        expected_prompts = {
            "train_synthesis_model",
            "synthesize_circuit",
            "explore_hardware_topology",
        }
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
            "qiskit-gym://environments/{env_id}",
            "qiskit-gym://models/{model_name}",
            "qiskit-gym://training/{session_id}",
        }
        assert expected_templates.issubset(template_uris), (
            f"Missing resource templates: {expected_templates - template_uris}"
        )

    async def test_resource_template_count(self):
        """Test the expected number of resource templates."""
        templates = await mcp.list_resource_templates()
        assert len(templates) == 3
