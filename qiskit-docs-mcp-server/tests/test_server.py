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

from qiskit_docs_mcp_server.server import mcp


class TestServerRegistration:
    """Test that tools and resources are registered on the MCP server."""

    def test_server_name(self):
        """Test the MCP server has the correct name."""
        assert mcp.name == "Qiskit Documentation"

    def test_server_instructions(self):
        """Test the MCP server has instructions set."""
        assert mcp.instructions is not None
        assert isinstance(mcp.instructions, str)
        assert len(mcp.instructions) > 0
        # Verify instructions mention key workflow concepts
        assert "search_docs_tool" in mcp.instructions
        assert "get_page_tool" in mcp.instructions
        assert "lookup_error_code_tool" in mcp.instructions
        assert "qiskit-docs://" in mcp.instructions

    async def test_tools_registered(self):
        """Test that all expected tools are registered."""
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        expected_tools = {
            "search_docs_tool",
            "get_page_tool",
            "lookup_error_code_tool",
        }
        assert expected_tools.issubset(tool_names), f"Missing tools: {expected_tools - tool_names}"

    async def test_resources_registered(self):
        """Test that all expected resources are registered."""
        resources = await mcp.list_resources()
        resource_uris = {str(r.uri) for r in resources}
        expected_resources = {
            "qiskit-docs://modules",
            "qiskit-docs://addons",
            "qiskit-docs://guides",
            "qiskit-docs://tutorials",
            "qiskit-docs://api-packages",
            "qiskit-docs://error-codes",
        }
        assert expected_resources.issubset(resource_uris), (
            f"Missing resources: {expected_resources - resource_uris}"
        )

    async def test_tool_count(self):
        """Test the expected number of tools."""
        tools = await mcp.list_tools()
        assert len(tools) == 3

    async def test_resource_count(self):
        """Test the expected number of resources."""
        resources = await mcp.list_resources()
        assert len(resources) == 6

    async def test_old_tools_removed(self):
        """Test that old category-specific tools are no longer registered."""
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}
        removed_tools = {
            "get_sdk_module_docs_tool",
            "get_addon_docs_tool",
            "get_guide_tool",
        }
        assert removed_tools.isdisjoint(tool_names), (
            f"Old tools still registered: {removed_tools & tool_names}"
        )

    async def test_prompts_registered(self):
        """Test that all expected prompts are registered."""
        prompts = await mcp.list_prompts()
        prompt_names = {p.name for p in prompts}
        expected_prompts = {
            "explain_error",
            "module_overview",
            "how_to",
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
            "qiskit-docs://modules/{module_name}",
            "qiskit-docs://guides/{guide_name}",
            "qiskit-docs://addons/{addon_name}",
        }
        assert expected_templates.issubset(template_uris), (
            f"Missing resource templates: {expected_templates - template_uris}"
        )
