"""Comprehensive integration tests for SWAG MCP tool with real tool calls."""

from collections.abc import Callable
from typing import Any

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from mcp.types import TextContent
from swag_mcp.models.enums import SwagAction


class TestSwagToolIntegration:
    """Integration tests for the SWAG MCP tool using real tool calls."""

    # LIST Action Tests

    async def test_list_all_configurations(self, mcp_client: Client) -> None:
        """Test listing all configurations."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.LIST, "list_filter": "all"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)
        response = result.content[0].text

        # Should be a successful response
        assert "configurations" in response or "Found" in response

    async def test_list_active_configurations(self, mcp_client: Client) -> None:
        """Test listing active configurations only."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.LIST, "list_filter": "active"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)
        response = result.content[0].text
        assert "active" in response or "Found" in response

    async def test_list_sample_configurations(self, mcp_client: Client) -> None:
        """Test listing sample configurations."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.LIST, "list_filter": "samples"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)
        response = result.content[0].text
        assert "sample" in response or "Found" in response

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
        response = result.content[0].text
        assert "Created" in response or "created" in response

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
        response = result.content[0].text
        assert "Created" in response or "created" in response

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
        response = result.content[0].text
        assert "required" in response.lower() or "missing" in response.lower()

    async def test_create_invalid_port(self, mcp_client: Client, test_config_name: str) -> None:
        """Test creating config with invalid port number."""
        from fastmcp.exceptions import ToolError

        # Should raise ToolError for invalid port
        try:
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
            raise AssertionError("Expected ToolError for invalid port")
        except ToolError as e:
            assert (
                "validation" in str(e).lower() or "maximum" in str(e).lower() or "65535" in str(e)
            )

    # VIEW Action Tests

    async def test_view_sample_configuration(self, mcp_client: Client) -> None:
        """Test viewing a sample configuration (read-only, safe)."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.VIEW, "config_name": "_template.subdomain.conf.sample"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)
        response = result.content[0].text

        # Should contain nginx configuration content
        assert any(keyword in response for keyword in ["server", "location", "proxy_pass"])

    async def test_view_nonexistent_config(self, mcp_client: Client) -> None:
        """Test viewing a non-existent configuration."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.VIEW, "config_name": "nonexistent.subdomain.conf"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)
        response = result.content[0].text
        assert (
            "not found" in response.lower()
            or "does not exist" in response.lower()
            or "filename must follow format" in response.lower()
            or "binary content or is unsafe" in response.lower()
        )

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
        response = result.content[0].text
        assert "required" in response.lower() or "missing" in response.lower()

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
        response = edit_result.content[0].text
        assert "Updated" in response or "edited" in response or "backup" in response.lower()

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
        response = result.content[0].text
        assert "required" in response.lower() or "missing" in response.lower()

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
        response = update_result.content[0].text
        assert "Updated" in response and "port" in response

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
        response = update_result.content[0].text
        assert "Updated" in response and ("upstream" in response or "new-app" in response)

    async def test_update_add_mcp_location(
        self, mcp_client: Client, test_config_name: str, test_config_cleanup: Callable[[str], None]
    ) -> None:
        """Test adding an MCP location to an existing configuration."""
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

        # Add MCP location
        update_result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.UPDATE,
                "config_name": config_name,
                "update_field": "add_mcp",
                "update_value": "/mcp",
                "create_backup": True,
            },
        )

        assert update_result.is_error is False
        assert isinstance(update_result.content[0], TextContent)
        response = update_result.content[0].text
        assert "Updated" in response and ("mcp" in response or "/mcp" in response)

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
        response = result.content[0].text
        assert "validation" in response.lower() or "invalid" in response.lower()

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
        response = result.content[0].text
        assert "required" in response.lower() or "missing" in response.lower()

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
        response = remove_result.content[0].text
        assert "Removed" in response or "removed" in response

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
        response = result.content[0].text
        assert (
            "not found" in response.lower()
            or "does not exist" in response.lower()
            or "filename must follow format" in response.lower()
            or "binary content or is unsafe" in response.lower()
        )

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
        response = result.content[0].text
        assert "required" in response.lower() or "missing" in response.lower()

    # LOGS Action Tests

    async def test_get_nginx_error_logs(self, mcp_client: Client) -> None:
        """Test retrieving nginx error logs."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.LOGS, "log_type": "nginx-error", "lines": 10}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)
        response = result.content[0].text
        # Should contain log information or indicate no logs
        assert (
            "log" in response.lower()
            or "retrieved" in response.lower()
            or "no logs" in response.lower()
        )

    async def test_get_nginx_access_logs(self, mcp_client: Client) -> None:
        """Test retrieving nginx access logs."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.LOGS, "log_type": "nginx-access", "lines": 10}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)
        response = result.content[0].text
        assert (
            "log" in response.lower()
            or "retrieved" in response.lower()
            or "no logs" in response.lower()
        )

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
        from fastmcp.exceptions import ToolError

        # Should raise ToolError for invalid log type
        try:
            await mcp_client.call_tool(
                "swag", {"action": SwagAction.LOGS, "log_type": "invalid-log-type", "lines": 10}
            )
            raise AssertionError("Expected ToolError for invalid log type")
        except ToolError as e:
            assert (
                "validation" in str(e).lower()
                or "invalid" in str(e).lower()
                or "not one of" in str(e).lower()
            )

    # BACKUPS Action Tests

    async def test_list_backup_files(self, mcp_client: Client) -> None:
        """Test listing backup files."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.BACKUPS, "backup_action": "list"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)
        response = result.content[0].text
        assert "backup" in response.lower() and (
            "found" in response.lower() or "no" in response.lower()
        )

    async def test_cleanup_backups_default_retention(self, mcp_client: Client) -> None:
        """Test cleaning up backups with default retention."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.BACKUPS, "backup_action": "cleanup"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)
        response = result.content[0].text
        assert "cleanup" in response.lower() or "cleaned" in response.lower()

    async def test_cleanup_backups_custom_retention(self, mcp_client: Client) -> None:
        """Test cleaning up backups with custom retention."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.BACKUPS, "backup_action": "cleanup", "retention_days": 7}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)
        response = result.content[0].text
        assert "cleanup" in response.lower() or "cleaned" in response.lower()

    async def test_backups_invalid_action(self, mcp_client: Client) -> None:
        """Test backups with invalid action."""
        result = await mcp_client.call_tool(
            "swag", {"action": SwagAction.BACKUPS, "backup_action": "invalid"}
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)
        response = result.content[0].text
        assert "validation" in response.lower() or "invalid" in response.lower()

    async def test_backups_missing_action(self, mcp_client: Client) -> None:
        """Test backups with missing backup_action."""
        result = await mcp_client.call_tool(
            "swag",
            {
                "action": SwagAction.BACKUPS
                # Missing backup_action
            },
        )

        assert result.is_error is False
        assert isinstance(result.content[0], TextContent)
        response = result.content[0].text
        assert "required" in response.lower() or "missing" in response.lower()

    # HEALTH_CHECK Action Tests

    @pytest.mark.slow
    async def test_health_check_localhost(self, mcp_client: Client) -> None:
        """Test health check on localhost (may be slow)."""
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
        response = result.content[0].text
        # Should contain health check result
        assert any(
            keyword in response.lower()
            for keyword in ["accessible", "not accessible", "health", "check"]
        )

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
        response = result.content[0].text
        # Should indicate failure to connect
        assert (
            "not accessible" in response.lower()
            or "failed" in response.lower()
            or "error" in response.lower()
        )

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
        response = result.content[0].text
        assert "required" in response.lower() or "missing" in response.lower()

    async def test_health_check_invalid_timeout(self, mcp_client: Client) -> None:
        """Test health check with invalid timeout."""
        from fastmcp.exceptions import ToolError

        # Should raise ToolError for invalid timeout
        try:
            await mcp_client.call_tool(
                "swag",
                {
                    "action": SwagAction.HEALTH_CHECK,
                    "domain": "example.com",
                    "timeout": 999,  # Too high
                },
            )
            raise AssertionError("Expected ToolError for invalid timeout")
        except ToolError as e:
            assert (
                "validation" in str(e).lower()
                or "invalid" in str(e).lower()
                or "less than or equal to" in str(e).lower()
            )

    # Error Handling Tests

    async def test_invalid_action(self, mcp_client: Client) -> None:
        """Test with completely invalid action."""
        from fastmcp.exceptions import ToolError

        # Should raise ToolError for invalid action
        try:
            await mcp_client.call_tool("swag", {"action": "totally_invalid_action"})
            raise AssertionError("Expected ToolError for invalid action")
        except ToolError as e:
            assert (
                "validation" in str(e).lower()
                or "invalid" in str(e).lower()
                or "not one of" in str(e).lower()
            )

    async def test_empty_parameters(self, mcp_client: Client) -> None:
        """Test with minimal parameters."""
        from fastmcp.exceptions import ToolError

        # Should raise ToolError for missing action
        try:
            await mcp_client.call_tool("swag", {})
            raise AssertionError("Expected ToolError for missing action")
        except ToolError as e:
            assert (
                "required" in str(e).lower()
                or "missing" in str(e).lower()
                or "action" in str(e).lower()
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
        # Should contain the new port
        assert isinstance(view_updated_result.content[0], TextContent)
        assert "4000" in view_updated_result.content[0].text

        # 5. Remove the configuration (cleanup happens automatically)
        # This is tested separately in test_remove_configuration
