"""Comprehensive integration tests for SWAG MCP tool with real tool calls."""

from collections.abc import Callable
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp.types import TextContent
from swag_mcp.models.enums import SwagAction

pytestmark = pytest.mark.asyncio


class TestSwagToolIntegration:
    """Integration tests for the SWAG MCP tool using real tool calls."""

    # LIST Action Tests

    async def test_list_all_configurations(self, mcp_client: Client) -> None:
        """Test listing all configurations with comprehensive validation."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.LIST, "list_filter": "all"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for configuration data with detailed assertions
        # Ensure structured_content is not None
        assert result.structured_content is not None, "structured_content should not be None"
        assert "configs" in result.structured_content, "Missing 'configs' field in response"
        assert "total_count" in result.structured_content, "Missing 'total_count' field in response"
        assert "list_filter" in result.structured_content, "Missing 'list_filter' field in response"

        # Validate field types and values
        assert result.structured_content is not None
        configs = result.structured_content["configs"]
        assert isinstance(configs, list), f"'configs' should be a list, got {type(configs)}"

        assert result.structured_content is not None
        total_count = result.structured_content["total_count"]
        assert isinstance(total_count, int), (
            f"'total_count' should be an integer, got {type(total_count)}"
        )
        assert total_count >= 0, f"'total_count' should be non-negative, got {total_count}"
        assert total_count == len(configs), (
            f"'total_count' ({total_count}) should match config list length ({len(configs)})"
        )

        assert result.structured_content is not None
        list_filter = result.structured_content["list_filter"]
        assert list_filter == "all", f"Expected list_filter 'all', got '{list_filter}'"

    async def test_list_active_configurations(self, mcp_client: Client) -> None:
        """Test listing active configurations only."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.LIST, "list_filter": "active"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for configuration data
        assert result.structured_content is not None
        assert "configs" in result.structured_content
        assert result.structured_content is not None
        assert "total_count" in result.structured_content
        assert result.structured_content is not None
        assert "list_filter" in result.structured_content
        assert result.structured_content is not None
        assert isinstance(result.structured_content["configs"], list)
        assert result.structured_content is not None
        assert result.structured_content["list_filter"] == "active"
        assert result.structured_content is not None
        assert isinstance(result.structured_content["total_count"], int)

    async def test_list_sample_configurations(self, mcp_client: Client) -> None:
        """Test listing sample configurations."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.LIST, "list_filter": "samples"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for configuration data
        assert result.structured_content is not None
        assert "configs" in result.structured_content
        assert result.structured_content is not None
        assert "total_count" in result.structured_content
        assert result.structured_content is not None
        assert "list_filter" in result.structured_content
        assert result.structured_content is not None
        assert isinstance(result.structured_content["configs"], list)
        assert result.structured_content is not None
        assert result.structured_content["list_filter"] == "samples"
        assert result.structured_content is not None
        assert isinstance(result.structured_content["total_count"], int)

    async def test_list_invalid_filter(self, mcp_client: Client) -> None:
        """Test listing with invalid filter."""
        # Should raise ToolError for invalid filter
        with pytest.raises(ToolError) as exc_info:
            await mcp_client.call_tool(
                "swag", {"action": SwagAction.LIST, "list_filter": "invalid"}
            )

        # Check that the error message is about validation
        error_msg = str(exc_info.value).lower()
        assert "validation" in error_msg or "invalid" in error_msg or "not one of" in error_msg

    # CREATE Action Tests

    async def test_create_basic_subdomain_config(
        self,
        mcp_client: Client,
        test_config_name: str,
        test_domain: str,
        test_upstream: dict[str, Any],
        test_config_cleanup: Callable[[str], None],
    ) -> None:
        """Test creating a basic subdomain configuration."""
        config_name = f"{test_config_name}.subdomain.conf"
        test_config_cleanup(config_name)

        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.CREATE,
                "config_name": config_name,
                "server_name": test_domain,
                "upstream_app": test_upstream["app"],
                "upstream_port": test_upstream["port"],
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for successful creation
        assert result.structured_content is not None
        assert result.structured_content.get("success")
        assert result.structured_content is not None
        assert "filename" in result.structured_content
        assert result.structured_content is not None
        assert "backup_created" in result.structured_content
        assert result.structured_content is not None
        assert result.structured_content["filename"] == config_name
        assert result.structured_content is not None
        assert result.structured_content["backup_created"] is None  # No backup for new files

    async def test_create_mcp_subdomain_config(
        self,
        mcp_client: Client,
        test_config_name: str,
        test_domain: str,
        test_upstream: dict[str, Any],
        test_config_cleanup: Callable[[str], None],
    ) -> None:
        """Test creating an MCP-enabled subdomain configuration."""
        config_name = f"{test_config_name}-mcp.subdomain.conf"
        test_config_cleanup(config_name)

        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.CREATE,
                "config_name": config_name,
                "server_name": f"mcp-{test_domain}",
                "upstream_app": test_upstream["app"],
                "upstream_port": test_upstream["port"],
                "mcp_enabled": True,
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for successful MCP creation
        assert result.structured_content is not None
        assert result.structured_content.get("success")
        assert result.structured_content is not None
        assert "filename" in result.structured_content
        assert result.structured_content is not None
        assert "backup_created" in result.structured_content
        assert result.structured_content is not None
        assert result.structured_content["filename"] == config_name
        assert result.structured_content is not None
        assert result.structured_content["backup_created"] is None  # No backup for new files

    async def test_create_missing_required_params(self, mcp_client: Client) -> None:
        """Test creating config with missing required parameters."""
        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.CREATE,
                "config_name": "incomplete",
                # Missing server_name, upstream_app, upstream_port
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for validation error with specific validation
        assert result.structured_content is not None
        assert result.structured_content.get("success") is False, (
            "Operation should fail for missing parameters"
        )

        # Ensure error message is present and informative
        assert result.structured_content is not None
        has_error = "error" in result.structured_content or "message" in result.structured_content
        assert has_error, "Response should contain error message for missing parameters"

        # Check that error message mentions missing required fields
        assert result.structured_content is not None
        error_msg = result.structured_content.get(
            "error", result.structured_content.get("message", "")
        ).lower()
        expected_terms = ["required", "missing", "validation", "field", "server_name", "upstream"]
        found_terms = [term for term in expected_terms if term in error_msg]
        assert len(found_terms) > 0, (
            f"Expected error about missing required fields (terms: {expected_terms}), "
            f"got: {error_msg}"
        )

    async def test_create_invalid_port(self, mcp_client: Client, test_config_name: str) -> None:
        """Test creating config with invalid port number."""
        from fastmcp.exceptions import ToolError

        # Should raise ToolError for invalid port
        with pytest.raises(ToolError) as exc_info:
            await mcp_client.call_tool(
                "swag",
                {
                    "action": SwagAction.CREATE,
                    "config_name": f"{test_config_name}.subdomain.conf",
                    "server_name": "test.example.com",
                    "upstream_app": "test-app",
                    "upstream_port": 99999,  # Invalid port
                },
            )

        # Check that the error message is about validation
        error_msg = str(exc_info.value).lower()
        assert "validation" in error_msg or "maximum" in error_msg or "65535" in error_msg

    # VIEW Action Tests

    async def test_view_sample_configuration(self, mcp_client: Client) -> None:
        """Test viewing a sample configuration (read-only, safe)."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.VIEW, "config_name": "_template.subdomain.conf.sample"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for successful view operation
        assert result.structured_content is not None
        assert result.structured_content.get("success")
        assert result.structured_content is not None
        assert "config_name" in result.structured_content
        assert result.structured_content is not None
        assert "content" in result.structured_content
        assert result.structured_content is not None
        assert "character_count" in result.structured_content
        assert result.structured_content is not None
        assert result.structured_content["config_name"] == "_template.subdomain.conf.sample"
        assert result.structured_content is not None
        assert isinstance(result.structured_content["character_count"], int)

        # Check content contains nginx configuration keywords with specific validation
        assert result.structured_content is not None
        content = result.structured_content["content"]
        assert isinstance(content, str), f"Content should be a string, got {type(content)}"
        assert len(content) > 0, "Content should not be empty"

        nginx_keywords = ["server", "location", "proxy_pass"]
        found_keywords = [keyword for keyword in nginx_keywords if keyword in content]
        assert len(found_keywords) > 0, (
            f"Expected nginx config to contain at least one of {nginx_keywords}, "
            f"found none. Content preview: {content[:200]}..."
        )

    async def test_view_nonexistent_config(self, mcp_client: Client) -> None:
        """Test viewing a non-existent configuration."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.VIEW, "config_name": "nonexistent.subdomain.conf"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for error response
        assert result.structured_content is not None
        assert not result.structured_content.get("success")
        assert result.structured_content is not None
        assert "error" in result.structured_content or "message" in result.structured_content

    async def test_view_missing_config_name(self, mcp_client: Client) -> None:
        """Test viewing without providing config name."""
        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.VIEW
                # Missing config_name
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for validation error
        assert result.structured_content is not None
        assert not result.structured_content.get("success")
        assert result.structured_content is not None
        assert "error" in result.structured_content or "message" in result.structured_content

    # EDIT Action Tests

    async def test_edit_create_and_remove_config(
        self, mcp_client: Client, test_config_name: str, test_config_cleanup: Callable[[str], None]
    ) -> None:
        """Test full edit workflow: create, edit, remove."""
        config_name = f"{test_config_name}-edit.subdomain.conf"
        test_config_cleanup(config_name)

        # First create a config
        create_result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.CREATE,
                "config_name": config_name,
                "server_name": "edit-test.example.com",
                "upstream_app": "test-app",
                "upstream_port": 8080,
            },
        )
        assert create_result.is_error is False

        # Get the current content
        view_result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.VIEW, "config_name": config_name}
        )
        assert view_result.is_error is False

        # Extract the content and modify it slightly
        assert isinstance(view_result.content[0], TextContent)
        original_content = view_result.content[0].text
        # Add a comment to the content
        modified_content = f"# Modified by test\\n{original_content}"

        # Edit the config
        edit_result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.EDIT,
                "config_name": config_name,
                "new_content": modified_content,
                "create_backup": True,
            },
        )

        assert edit_result.is_error is False
        assert isinstance(edit_result.content[0], TextContent)

        # Check structured content for successful edit
        assert edit_result.structured_content is not None
        assert edit_result.structured_content.get("success")
        assert "backup_created" in edit_result.structured_content
        # Backup created should be a valid filename string with proper validation
        assert edit_result.structured_content is not None
        backup_created = edit_result.structured_content["backup_created"]
        assert isinstance(backup_created, str), (
            f"Expected backup filename as string, got: {type(backup_created)} = {backup_created}"
        )
        assert len(backup_created) > 0, "Backup filename should not be empty"

        # Backup filename should contain reference to original config
        config_base_name = config_name.replace('.conf', '')
        assert config_base_name in backup_created, (
            f"Expected backup filename to reference original config "
            f"'{config_base_name}', got: {backup_created}"
        )

        # Backup should have a timestamp or backup extension
        backup_indicators = ['.backup', '_backup', '.bak', '202']
        has_backup_indicator = any(indicator in backup_created for indicator in backup_indicators)
        assert has_backup_indicator, (
            f"Backup filename should contain timestamp or backup indicator, got: {backup_created}"
        )

    async def test_edit_missing_parameters(self, mcp_client: Client) -> None:
        """Test editing with missing parameters."""
        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.EDIT,
                "config_name": "test.conf",
                # Missing new_content
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for validation error
        assert result.structured_content is not None
        assert not result.structured_content.get("success")
        assert result.structured_content is not None
        assert "error" in result.structured_content or "message" in result.structured_content

    # UPDATE Action Tests

    async def test_update_port_field(
        self, mcp_client: Client, test_config_name: str, test_config_cleanup: Callable[[str], None]
    ) -> None:
        """Test updating the port field of a configuration."""
        config_name = f"{test_config_name}-update.subdomain.conf"
        test_config_cleanup(config_name)

        # First create a config
        create_result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.CREATE,
                "config_name": config_name,
                "server_name": "update-test.example.com",
                "upstream_app": "test-app",
                "upstream_port": 8080,
            },
        )
        assert create_result.is_error is False

        # Update the port
        update_result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.UPDATE,
                "config_name": config_name,
                "update_field": "port",
                "update_value": "9090",
                "create_backup": True,
            },
        )

        assert update_result.is_error is False
        assert isinstance(update_result.content[0], TextContent)

        # Check structured content for successful port update
        assert update_result.structured_content is not None
        assert update_result.structured_content.get("success")
        assert "backup_created" in update_result.structured_content
        # Should have health_check field for domains or other update-specific data
        # The exact structure may vary, but success and backup_created are standard

    async def test_update_upstream_field(
        self, mcp_client: Client, test_config_name: str, test_config_cleanup: Callable[[str], None]
    ) -> None:
        """Test updating the upstream field of a configuration."""
        config_name = f"{test_config_name}-update-upstream.subdomain.conf"
        test_config_cleanup(config_name)

        # First create a config
        create_result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.CREATE,
                "config_name": config_name,
                "server_name": "upstream-test.example.com",
                "upstream_app": "old-app",
                "upstream_port": 8080,
            },
        )
        assert create_result.is_error is False

        # Update the upstream app
        update_result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.UPDATE,
                "config_name": config_name,
                "update_field": "upstream",
                "update_value": "new-app",
                "create_backup": True,
            },
        )

        assert update_result.is_error is False
        assert isinstance(update_result.content[0], TextContent)

        # Check structured content for successful upstream update
        assert update_result.structured_content is not None
        assert update_result.structured_content.get("success")
        assert "backup_created" in update_result.structured_content
        # Should have health_check field for domains or other update-specific data

    async def test_update_add_mcp_location(
        self, mcp_client: Client, test_config_name: str, test_config_cleanup: Callable[[str], None]
    ) -> None:
        """Test adding a custom MCP location to an existing configuration.

        Note: SWAG-compliant templates already include /mcp location by default.
        This test adds a custom MCP endpoint at a different path.
        """
        config_name = f"{test_config_name}-mcp.subdomain.conf"
        test_config_cleanup(config_name)

        # First create a config
        create_result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.CREATE,
                "config_name": config_name,
                "server_name": "mcp-test.example.com",
                "upstream_app": "test-app",
                "upstream_port": 8080,
            },
        )
        assert create_result.is_error is False

        # Add custom MCP location (not /mcp, which is already included in SWAG-compliant templates)
        update_result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.UPDATE,
                "config_name": config_name,
                "update_field": "add_mcp",
                "update_value": "/ai-service",
                "create_backup": True,
            },
        )

        assert update_result.is_error is False
        assert isinstance(update_result.content[0], TextContent)

        # Check structured content for successful MCP location addition
        assert update_result.structured_content is not None
        assert update_result.structured_content.get("success")
        assert "backup_created" in update_result.structured_content
        # Should have health_check field for domains or other update-specific data

    async def test_update_invalid_field(self, mcp_client: Client, test_config_name: str) -> None:
        """Test updating with an invalid field name."""
        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.UPDATE,
                "config_name": f"{test_config_name}.subdomain.conf",
                "update_field": "invalid_field",
                "update_value": "some_value",
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for validation error
        assert result.structured_content is not None
        assert not result.structured_content.get("success")
        assert result.structured_content is not None
        assert "error" in result.structured_content or "message" in result.structured_content

    async def test_update_missing_parameters(self, mcp_client: Client) -> None:
        """Test updating with missing parameters."""
        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.UPDATE,
                "config_name": "test.conf",
                # Missing update_field and update_value
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for validation error
        assert result.structured_content is not None
        assert not result.structured_content.get("success")
        assert result.structured_content is not None
        assert "error" in result.structured_content or "message" in result.structured_content

    # REMOVE Action Tests

    async def test_remove_configuration(
        self, mcp_client: Client, test_config_name: str, test_config_cleanup: Callable[[str], None]
    ) -> None:
        """Test removing a configuration with backup."""
        config_name = f"{test_config_name}-remove.subdomain.conf"
        # Don't add to cleanup since we're testing removal

        # First create a config
        create_result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.CREATE,
                "config_name": config_name,
                "server_name": "remove-test.example.com",
                "upstream_app": "test-app",
                "upstream_port": 8080,
            },
        )
        assert create_result.is_error is False

        # Remove the config
        remove_result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.REMOVE, "config_name": config_name, "create_backup": True}
        )

        assert remove_result.is_error is False
        assert isinstance(remove_result.content[0], TextContent)

        # Check structured content for successful removal
        assert remove_result.structured_content is not None
        assert remove_result.structured_content.get("success")
        assert "backup_created" in remove_result.structured_content
        # Backup created should be a filename string when backup is requested
        assert remove_result.structured_content is not None
        if remove_result.structured_content["backup_created"]:
            assert remove_result.structured_content is not None
            assert isinstance(remove_result.structured_content["backup_created"], str)

    async def test_remove_nonexistent_config(self, mcp_client: Client) -> None:
        """Test removing a non-existent configuration."""
        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.REMOVE,
                "config_name": "nonexistent.subdomain.conf",
                "create_backup": False,
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for error response
        assert result.structured_content is not None
        assert not result.structured_content.get("success")
        assert result.structured_content is not None
        assert "error" in result.structured_content or "message" in result.structured_content

    async def test_remove_missing_config_name(self, mcp_client: Client) -> None:
        """Test removing without providing config name."""
        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.REMOVE
                # Missing config_name
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for validation error
        assert result.structured_content is not None
        assert not result.structured_content.get("success")
        assert result.structured_content is not None
        assert "error" in result.structured_content or "message" in result.structured_content

    # LOGS Action Tests

    async def test_get_nginx_error_logs(self, mcp_client: Client) -> None:
        """Test retrieving nginx error logs."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.LOGS, "log_type": "nginx-error", "lines": 10}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for log retrieval
        assert result.structured_content is not None
        assert "logs" in result.structured_content or "success" in result.structured_content
        assert result.structured_content is not None
        assert "character_count" in result.structured_content
        assert result.structured_content is not None
        if "logs" in result.structured_content:
            assert result.structured_content is not None
            assert isinstance(result.structured_content["logs"], str)

    async def test_get_nginx_access_logs(self, mcp_client: Client) -> None:
        """Test retrieving nginx access logs."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.LOGS, "log_type": "nginx-access", "lines": 10}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for log retrieval
        assert result.structured_content is not None
        assert "logs" in result.structured_content or "success" in result.structured_content
        assert result.structured_content is not None
        assert "character_count" in result.structured_content
        assert result.structured_content is not None
        if "logs" in result.structured_content:
            assert result.structured_content is not None
            assert isinstance(result.structured_content["logs"], str)

    async def test_get_logs_different_line_counts(self, mcp_client: Client) -> None:
        """Test retrieving logs with different line counts."""
        # Test with minimum lines
        result_min = await mcp_client.call_tool(
            "swag", {"action": SwagAction.LOGS, "log_type": "nginx-error", "lines": 1}
        )
        assert result_min.is_error is False

        # Test with more lines
        result_more = await mcp_client.call_tool(
            "swag", {"action": SwagAction.LOGS, "log_type": "nginx-error", "lines": 50}
        )
        assert result_more.is_error is False

    async def test_get_logs_invalid_type(self, mcp_client: Client) -> None:
        """Test retrieving logs with invalid log type."""
        # Should raise ToolError for invalid log type
        with pytest.raises(ToolError) as exc_info:
            await mcp_client.call_tool(
                "swag", {"action": SwagAction.LOGS, "log_type": "invalid-log-type", "lines": 10}
            )

        # Check that the error message is about validation
        assert any(
            k in str(exc_info.value).lower() for k in ("validation", "invalid", "not one of")
        )

    # BACKUPS Action Tests

    async def test_list_backup_files(self, mcp_client: Client) -> None:
        """Test listing backup files."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.BACKUPS, "backup_action": "list"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for backup listing
        assert result.structured_content is not None
        assert "backup_files" in result.structured_content
        assert result.structured_content is not None
        assert "total_count" in result.structured_content
        assert result.structured_content is not None
        assert isinstance(result.structured_content["backup_files"], list)
        assert result.structured_content is not None
        assert isinstance(result.structured_content["total_count"], int)

    async def test_cleanup_backups_default_retention(self, mcp_client: Client) -> None:
        """Test cleaning up backups with default retention.

        Note: retention_days must be > 0 to trigger cleanup action (not just backup_action).
        """
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.BACKUPS, "backup_action": "cleanup", "retention_days": 30}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for backup cleanup
        assert result.structured_content is not None
        assert "cleaned_count" in result.structured_content
        assert result.structured_content is not None
        assert "retention_days" in result.structured_content
        assert result.structured_content is not None
        assert isinstance(result.structured_content["cleaned_count"], int)
        assert result.structured_content is not None
        assert isinstance(result.structured_content["retention_days"], int)

    async def test_cleanup_backups_custom_retention(self, mcp_client: Client) -> None:
        """Test cleaning up backups with custom retention."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.BACKUPS, "backup_action": "cleanup", "retention_days": 7}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for backup cleanup
        assert result.structured_content is not None
        assert "cleaned_count" in result.structured_content
        assert result.structured_content is not None
        assert "retention_days" in result.structured_content
        assert result.structured_content is not None
        assert isinstance(result.structured_content["cleaned_count"], int)
        assert result.structured_content is not None
        assert result.structured_content["retention_days"] == 7

    async def test_backups_invalid_action(self, mcp_client: Client) -> None:
        """Test backups with invalid action."""
        # Should raise ToolError for invalid backup_action
        with pytest.raises(ToolError) as exc_info:
            await mcp_client.call_tool(
                "swag", {"action": SwagAction.BACKUPS, "backup_action": "invalid"}
            )

        # Check that the error message is about validation
        error_msg = str(exc_info.value).lower()
        assert "validation" in error_msg or "not one of" in error_msg

    async def test_backups_missing_action(self, mcp_client: Client) -> None:
        """Test backups with missing backup_action (should default to 'list')."""
        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.BACKUPS
                # Missing backup_action - should default to 'list'
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for backup listing (default action)
        assert result.structured_content is not None
        assert "backup_files" in result.structured_content
        assert result.structured_content is not None
        assert "total_count" in result.structured_content
        assert result.structured_content is not None
        assert isinstance(result.structured_content["backup_files"], list)
        assert result.structured_content is not None
        assert isinstance(result.structured_content["total_count"], int)

    # HEALTH_CHECK Action Tests

    @pytest.mark.slow
    async def test_health_check_localhost(self, mcp_client: Client) -> None:
        """Test health check on localhost (may be slow).

        Validates response structure without forcing success.
        """
        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.HEALTH_CHECK,
                "domain": "127.0.0.1",
                "timeout": 5,
                "follow_redirects": False,
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Validate structured content presence and types (robust - allows success or failure)
        assert result.structured_content is not None
        assert "success" in result.structured_content
        assert result.structured_content is not None
        assert isinstance(result.structured_content["success"], bool)

        # Required fields should always be present
        assert result.structured_content is not None
        assert "domain" in result.structured_content
        assert result.structured_content is not None
        assert "error" in result.structured_content
        assert result.structured_content is not None
        assert result.structured_content["domain"] == "127.0.0.1"

        # Optional fields that depend on whether connection succeeded
        assert result.structured_content is not None
        if result.structured_content.get("success"):
            # When successful, should have status code and response time
            assert result.structured_content is not None
            assert "status_code" in result.structured_content
            assert result.structured_content is not None
            assert "response_time_ms" in result.structured_content
            assert result.structured_content is not None
            assert isinstance(result.structured_content["status_code"], int)
            assert result.structured_content is not None
            assert isinstance(result.structured_content["response_time_ms"], int | float)
        else:
            # When failed, error should be a non-empty string
            assert result.structured_content is not None
            assert isinstance(result.structured_content["error"], str)
            assert result.structured_content is not None
            assert len(result.structured_content["error"]) > 0
            # status_code may be None for unreachable scenarios
            assert result.structured_content is not None
            if "status_code" in result.structured_content:
                assert result.structured_content is not None
                status_code = result.structured_content["status_code"]
                assert status_code is None or isinstance(status_code, int)

    @pytest.mark.slow
    async def test_health_check_invalid_domain(self, mcp_client: Client) -> None:
        """Test health check on invalid domain (may be slow)."""
        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.HEALTH_CHECK,
                "domain": "definitely-does-not-exist.invalid.tld",
                "timeout": 3,
                "follow_redirects": False,
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for failed health check
        assert result.structured_content is not None
        assert not result.structured_content.get("success")
        assert result.structured_content is not None
        assert "domain" in result.structured_content
        assert result.structured_content is not None
        assert "error" in result.structured_content
        assert result.structured_content is not None
        assert result.structured_content["domain"] == "definitely-does-not-exist.invalid.tld"
        assert result.structured_content is not None
        assert isinstance(result.structured_content["error"], str)

    async def test_health_check_missing_domain(self, mcp_client: Client) -> None:
        """Test health check without providing domain."""
        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.HEALTH_CHECK
                # Missing domain
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)

        # Check structured content for validation error
        assert result.structured_content is not None
        assert not result.structured_content.get("success")
        assert result.structured_content is not None
        assert "error" in result.structured_content or "message" in result.structured_content

    async def test_health_check_invalid_timeout(self, mcp_client: Client) -> None:
        """Test health check with invalid timeout."""
        from fastmcp.exceptions import ToolError

        # Should raise ToolError for invalid timeout
        with pytest.raises(ToolError) as exc_info:
            await mcp_client.call_tool(
                "swag",
                {
                    "action": SwagAction.HEALTH_CHECK,
                    "domain": "example.com",
                    "timeout": 999,  # Too high
                },
            )

        # Check that the error message is about validation
        error_msg = str(exc_info.value).lower()
        assert (
            "validation" in error_msg
            or "invalid" in error_msg
            or "less than or equal to" in error_msg
        )

    # Error Handling Tests

    async def test_invalid_action(self, mcp_client: Client) -> None:
        """Test with completely invalid action."""
        from fastmcp.exceptions import ToolError

        # Should raise ToolError for invalid action
        with pytest.raises(ToolError) as exc_info:
            await mcp_client.call_tool("swag", {"action": "totally_invalid_action"})

        # Check that the error message is about validation
        error_msg = str(exc_info.value).lower()
        assert (
            "validation" in error_msg
            or "invalid" in error_msg
            or "not one of" in error_msg
        )

    async def test_empty_parameters(self, mcp_client: Client) -> None:
        """Test with minimal parameters."""
        from fastmcp.exceptions import ToolError

        # Should raise ToolError for missing action
        with pytest.raises(ToolError) as exc_info:
            await mcp_client.call_tool("swag", {})

        # Check that the error message is about validation
        error_msg = str(exc_info.value).lower()
        assert (
            "required" in error_msg
            or "missing" in error_msg
            or "action" in error_msg
        )

    # Integration Tests

    async def test_full_config_lifecycle(
        self, mcp_client: Client, test_config_name: str, test_config_cleanup: Callable[[str], None]
    ) -> None:
        """Test complete configuration lifecycle: create, view, update, remove."""
        config_name = f"{test_config_name}-lifecycle.subdomain.conf"
        test_config_cleanup(config_name)

        # 1. Create configuration
        create_result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.CREATE,
                "config_name": config_name,
                "server_name": "lifecycle.example.com",
                "upstream_app": "lifecycle-app",
                "upstream_port": 3000,
            },
        )
        assert create_result.is_error is False

        # 2. View the created configuration
        view_result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.VIEW, "config_name": config_name}
        )
        assert view_result.is_error is False
        assert isinstance(view_result.content[0], TextContent)
        assert "server_name" in view_result.content[0].text

        # 3. Update the configuration
        update_result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.UPDATE,
                "config_name": config_name,
                "update_field": "port",
                "update_value": "4000",
            },
        )
        assert update_result.is_error is False

        # 4. View the updated configuration
        view_updated_result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.VIEW, "config_name": config_name}
        )
        assert view_updated_result.is_error is False
        # Should contain the updated port with comprehensive validation
        assert isinstance(view_updated_result.content[0], TextContent), (
            "Expected TextContent in view result"
        )
        updated_content = view_updated_result.content[0].text

        # Check that new port is present
        assert "4000" in updated_content, (
            f"Expected updated port '4000' to be in config content. "
            f"Content preview: {updated_content[:500]}..."
        )

        # Verify old port is replaced (basic check)
        port_4000_count = updated_content.count("4000")
        port_3000_count = updated_content.count("3000")
        assert port_4000_count > 0, "New port should be present at least once"
        # Old port might still appear in comments, so just ensure new port is prominent
        if port_3000_count > 0:
            assert port_4000_count >= port_3000_count, (
                f"New port (count: {port_4000_count}) should be at least as prominent "
                f"as old port (count: {port_3000_count})"
            )

        # 5. Remove the configuration (cleanup happens automatically)
        # This is tested separately in test_remove_configuration
