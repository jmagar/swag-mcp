"""Tests for SWAG MCP tools using in-memory client."""

from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client


class TestSwagTools:
    """Test suite for SWAG MCP tools."""

    @pytest.mark.asyncio
    async def test_swag_list_all(self, mcp_client: Client, sample_configs):
        """Test swag_list tool with 'all' config type."""
        result = await mcp_client.call_tool("swag_list", {"config_type": "all"})

        assert not result.is_error
        configs = result.data
        assert isinstance(configs, list)
        assert len(configs) >= 3  # At least our sample configs

        # Check for expected files
        assert "testapp.subdomain.conf" in configs
        assert "webapp.subfolder.conf" in configs
        assert "sampleapp.conf.sample" in configs

    @pytest.mark.asyncio
    async def test_swag_list_active(self, mcp_client: Client, sample_configs):
        """Test swag_list tool with 'active' config type."""
        result = await mcp_client.call_tool("swag_list", {"config_type": "active"})

        assert not result.is_error
        configs = result.data

        # Should include .conf files but not .sample files
        assert "testapp.subdomain.conf" in configs
        assert "webapp.subfolder.conf" in configs
        assert "sampleapp.conf.sample" not in configs

    @pytest.mark.asyncio
    async def test_swag_list_samples(self, mcp_client: Client, sample_configs):
        """Test swag_list tool with 'samples' config type."""
        result = await mcp_client.call_tool("swag_list", {"config_type": "samples"})

        assert not result.is_error
        configs = result.data

        # Should include .sample files but not active configs
        assert "sampleapp.conf.sample" in configs
        assert "testapp.subdomain.conf" not in configs
        assert "webapp.subfolder.conf" not in configs

    @pytest.mark.asyncio
    async def test_swag_view_existing_config(self, mcp_client: Client, sample_configs):
        """Test swag_view tool with existing configuration."""
        result = await mcp_client.call_tool("swag_view", {"config_name": "testapp.subdomain.conf"})

        assert not result.is_error
        content = result.data
        assert isinstance(content, str)
        assert "testapp" in content
        assert "server_name testapp.*;" in content

    @pytest.mark.asyncio
    async def test_swag_view_nonexistent_config(self, mcp_client: Client):
        """Test swag_view tool with non-existent configuration."""
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError):
            await mcp_client.call_tool("swag_view", {"config_name": "nonexistent.conf"})

    @pytest.mark.asyncio
    async def test_swag_create_subdomain(self, mcp_client: Client, mock_config, test_helpers):
        """Test swag_create tool for subdomain configuration."""
        config_file = mock_config.proxy_confs_path / "newapp.subdomain.conf"

        # Cleanup any existing file from previous runs
        if config_file.exists():
            config_file.unlink()

        try:
            result = await mcp_client.call_tool(
                "swag_create",
                {
                    "service_name": "newapp",
                    "server_name": "newapp.example.com",
                    "upstream_app": "newapp-container",
                    "upstream_port": 3000,
                    "upstream_proto": "http",
                    "auth_method": "authelia",
                    "enable_quic": False,
                    "config_type": "subdomain",
                },
            )

            assert not result.is_error
            message = result.data
            assert "Created configuration:" in message
            assert "newapp.subdomain.conf" in message

            # Verify file was created with correct content
            assert config_file.exists()

            content = config_file.read_text()
            test_helpers.assert_config_contains(
                content,
                {
                    "upstream_app": "newapp-container",
                    "upstream_port": "3000",
                    "upstream_proto": "http",
                    "server_name": "newapp.example.com",
                    "auth_method": "authelia",
                },
            )
        finally:
            # Cleanup created file
            if config_file.exists():
                config_file.unlink()

    @pytest.mark.asyncio
    async def test_swag_create_subfolder(self, mcp_client: Client, mock_config, test_helpers):
        """Test swag_create tool for subfolder configuration."""
        config_file = mock_config.proxy_confs_path / "api.subfolder.conf"

        # Cleanup any existing file from previous runs
        if config_file.exists():
            config_file.unlink()

        try:
            result = await mcp_client.call_tool(
                "swag_create",
                {
                    "service_name": "api",
                    "server_name": "example.com",
                    "upstream_app": "api-service",
                    "upstream_port": 8080,
                    "upstream_proto": "https",
                    "auth_method": "none",
                    "enable_quic": True,
                    "config_type": "subfolder",
                },
            )

            assert not result.is_error
            message = result.data
            assert "Created configuration:" in message
            assert "api.subfolder.conf" in message

            # Verify file was created
            assert config_file.exists()

            content = config_file.read_text()
            test_helpers.assert_config_contains(
                content,
                {"upstream_app": "api-service", "upstream_port": "8080", "upstream_proto": "https"},
            )
            assert "location /api" in content
        finally:
            # Cleanup created file
            if config_file.exists():
                config_file.unlink()

    @pytest.mark.asyncio
    async def test_swag_create_with_defaults(self, mcp_client: Client, mock_config, test_helpers):
        """Test swag_create tool using default values."""
        config_file = (
            mock_config.proxy_confs_path / "defaultapp.subdomain.conf"
        )  # Should default to subdomain

        # Cleanup any existing file from previous runs
        if config_file.exists():
            config_file.unlink()

        try:
            result = await mcp_client.call_tool(
                "swag_create",
                {
                    "service_name": "defaultapp",
                    "server_name": "defaultapp.example.com",
                    "upstream_app": "defaultapp",
                    "upstream_port": 8000,
                    # Not specifying auth_method, enable_quic, config_type to test defaults
                },
            )

            assert not result.is_error

            # Check file was created with defaults
            assert config_file.exists()

            content = config_file.read_text()
            # Should use default auth method from environment (authelia)
            test_helpers.assert_config_contains(content, {"auth_method": "authelia"})
        finally:
            # Cleanup created file
            if config_file.exists():
                config_file.unlink()

    @pytest.mark.asyncio
    async def test_swag_create_duplicate_file(self, mcp_client: Client, sample_configs):
        """Test swag_create tool when file already exists."""
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError):
            await mcp_client.call_tool(
                "swag_create",
                {
                    "service_name": "testapp",
                    "server_name": "testapp.example.com",
                    "upstream_app": "testapp",
                    "upstream_port": 8080,
                    "config_type": "subdomain",
                },
            )

    @pytest.mark.asyncio
    async def test_swag_edit_existing_config(
        self, mcp_client: Client, sample_configs, mock_config, test_helpers
    ):
        """Test swag_edit tool with existing configuration."""
        new_content = """# Updated configuration
server {
    listen 443 ssl;
    server_name updated.*;

    location / {
        proxy_pass http://updated-app:9000;
    }
}"""

        result = await mcp_client.call_tool(
            "swag_edit",
            {
                "config_name": "testapp.subdomain.conf",
                "new_content": new_content,
                "create_backup": True,
            },
        )

        assert not result.is_error
        message = result.data
        assert "Updated testapp.subdomain.conf" in message
        assert "backup created" in message

        # Verify content was updated
        config_file = mock_config.proxy_confs_path / "testapp.subdomain.conf"
        assert config_file.read_text() == new_content

        # Verify backup was created
        test_helpers.assert_backup_created(mock_config.proxy_confs_path, "testapp.subdomain.conf")

    @pytest.mark.asyncio
    async def test_swag_edit_without_backup(self, mcp_client: Client, sample_configs, mock_config):
        """Test swag_edit tool without creating backup."""
        new_content = "# Simple updated config"

        result = await mcp_client.call_tool(
            "swag_edit",
            {
                "config_name": "webapp.subfolder.conf",
                "new_content": new_content,
                "create_backup": False,
            },
        )

        assert not result.is_error
        message = result.data
        assert "Updated webapp.subfolder.conf" in message
        assert "no backup created" in message

        # Verify no backup was created
        backup_files = list(mock_config.proxy_confs_path.glob("webapp.subfolder.backup.*.conf"))
        assert len(backup_files) == 0

    @pytest.mark.asyncio
    async def test_swag_edit_nonexistent_config(self, mcp_client: Client, mock_config):
        """Test swag_edit tool with non-existent configuration creates the file."""
        config_file = mock_config.proxy_confs_path / "nonexistent.conf"

        try:
            result = await mcp_client.call_tool(
                "swag_edit", {"config_name": "nonexistent.conf", "new_content": "# New content"}
            )

            assert not result.is_error
            # File should be created
            assert config_file.exists()
            assert config_file.read_text() == "# New content"
        finally:
            # Cleanup created file
            if config_file.exists():
                config_file.unlink()

    @pytest.mark.asyncio
    async def test_swag_config_show_defaults(self, mcp_client: Client):
        """Test swag_config tool to show current defaults."""
        result = await mcp_client.call_tool("swag_config")

        assert not result.is_error
        message = result.data
        assert "Current defaults:" in message
        assert "default_auth_method" in message
        assert "default_quic_enabled" in message
        assert "default_config_type" in message
        assert "update your .env file" in message

    @pytest.mark.asyncio
    async def test_swag_remove_with_backup(
        self, mcp_client: Client, sample_configs, mock_config, test_helpers
    ):
        """Test swag_remove tool with backup creation."""
        result = await mcp_client.call_tool(
            "swag_remove", {"config_name": "testapp.subdomain.conf", "create_backup": True}
        )

        assert not result.is_error
        message = result.data
        assert "Removed testapp.subdomain.conf" in message
        assert "backup created" in message

        # Verify file was removed
        config_file = mock_config.proxy_confs_path / "testapp.subdomain.conf"
        assert not config_file.exists()

        # Verify backup was created
        test_helpers.assert_backup_created(mock_config.proxy_confs_path, "testapp.subdomain.conf")

    @pytest.mark.asyncio
    async def test_swag_remove_without_backup(
        self, mcp_client: Client, sample_configs, mock_config
    ):
        """Test swag_remove tool without backup creation."""
        result = await mcp_client.call_tool(
            "swag_remove", {"config_name": "webapp.subfolder.conf", "create_backup": False}
        )

        assert not result.is_error
        message = result.data
        assert "Removed webapp.subfolder.conf" in message
        assert "no backup created" in message

        # Verify file was removed and no backup created
        config_file = mock_config.proxy_confs_path / "webapp.subfolder.conf"
        assert not config_file.exists()

        backup_files = list(mock_config.proxy_confs_path.glob("webapp.subfolder.backup.*.conf"))
        assert len(backup_files) == 0

    @pytest.mark.asyncio
    async def test_swag_remove_sample_file_error(self, mcp_client: Client, sample_configs):
        """Test swag_remove tool with .sample file (should fail)."""
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError):
            await mcp_client.call_tool("swag_remove", {"config_name": "sampleapp.conf.sample"})

    @pytest.mark.asyncio
    async def test_swag_remove_nonexistent_config(self, mcp_client: Client):
        """Test swag_remove tool with non-existent configuration."""
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError):
            await mcp_client.call_tool("swag_remove", {"config_name": "nonexistent.conf"})

    @pytest.mark.asyncio
    async def test_swag_logs_default(self, mcp_client: Client):
        """Test swag_logs tool with default parameters."""
        from unittest.mock import MagicMock, patch

        # Mock subprocess.run to simulate docker logs output
        mock_result = MagicMock()
        mock_result.stdout = (
            "2025-01-15 10:00:00 SWAG initialized\n" "2025-01-15 10:00:01 Server started"
        )
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = await mcp_client.call_tool("swag_logs")

            assert not result.is_error
            message = result.data
            assert isinstance(message, str)
            assert "SWAG initialized" in message

    @pytest.mark.asyncio
    async def test_swag_logs_specific_lines(self, mcp_client: Client):
        """Test swag_logs tool with specific line count."""
        from unittest.mock import MagicMock, patch

        # Mock subprocess.run to simulate docker logs output
        mock_result = MagicMock()
        mock_result.stdout = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            result = await mcp_client.call_tool("swag_logs", {"lines": 50})

            assert not result.is_error
            message = result.data
            assert isinstance(message, str)
            assert "Line 1" in message

    @pytest.mark.asyncio
    async def test_swag_cleanup_backups(self, mcp_client: Client, mock_config):
        """Test swag_cleanup_backups tool."""
        # Create a test backup file using the correct timestamp format (YYYYMMDD_HHMMSS)
        import os
        from datetime import datetime, timedelta

        old_backup = mock_config.proxy_confs_path / "old.conf.backup.20200101_000000"
        old_backup.write_text("# Old backup")

        # Set old timestamp
        old_time = (datetime.now() - timedelta(days=35)).timestamp()
        os.utime(old_backup, (old_time, old_time))

        try:
            result = await mcp_client.call_tool("swag_cleanup_backups")

            assert not result.is_error
            message = result.data
            assert "Cleaned up 1 old backup files" in message
        finally:
            # Cleanup test backup file if it still exists
            if old_backup.exists():
                old_backup.unlink()


class TestSwagToolsValidation:
    """Test validation and error handling for SWAG tools."""

    @pytest.mark.asyncio
    async def test_invalid_config_type(self, mcp_client: Client):
        """Test tools with invalid config_type parameter."""
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError):
            await mcp_client.call_tool("swag_list", {"config_type": "invalid"})

    @pytest.mark.asyncio
    async def test_invalid_auth_method(self, mcp_client: Client):
        """Test swag_create with invalid auth_method."""
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError):
            await mcp_client.call_tool(
                "swag_create",
                {
                    "service_name": "test",
                    "server_name": "test.com",
                    "upstream_app": "test",
                    "upstream_port": 8080,
                    "auth_method": "invalid_auth",
                },
            )

    @pytest.mark.asyncio
    async def test_invalid_port_number(self, mcp_client: Client):
        """Test swag_create with invalid port number."""
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError):
            await mcp_client.call_tool(
                "swag_create",
                {
                    "service_name": "test",
                    "server_name": "test.com",
                    "upstream_app": "test",
                    "upstream_port": 99999,  # Invalid port
                },
            )

    @pytest.mark.asyncio
    async def test_invalid_service_name(self, mcp_client: Client):
        """Test swag_create with invalid service name."""
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError):
            await mcp_client.call_tool(
                "swag_create",
                {
                    "service_name": "invalid/name",
                    "server_name": "test.com",
                    "upstream_app": "test",
                    "upstream_port": 8080,
                },
            )

    @pytest.mark.asyncio
    async def test_empty_config_content(self, mcp_client: Client, sample_configs):
        """Test swag_edit with empty content."""
        from fastmcp.exceptions import ToolError

        with pytest.raises(ToolError):
            await mcp_client.call_tool(
                "swag_edit", {"config_name": "testapp.subdomain.conf", "new_content": ""}
            )

    @pytest.mark.asyncio
    async def test_invalid_config_name_pattern(self, mcp_client: Client):
        """Test tools with invalid configuration file names."""
        from fastmcp.exceptions import ToolError

        invalid_names = ["../../../etc/passwd", "config.txt", "test.conf.backup", "test..conf"]

        for invalid_name in invalid_names:
            with pytest.raises(ToolError):
                await mcp_client.call_tool("swag_view", {"config_name": invalid_name})


class TestSwagToolsErrorHandling:
    """Test error handling in SWAG MCP tools."""

    @pytest.mark.asyncio
    async def test_swag_list_error_handling(self, mcp_client: Client):
        """Test swag_list tool error handling (lines 49-51)."""
        from fastmcp.exceptions import ToolError

        # Patch the global swag_service instance
        with patch("swag_mcp.tools.swag.swag_service") as mock_service:
            mock_service.list_configs = AsyncMock(side_effect=Exception("List error"))

            with pytest.raises(ToolError, match="List error"):
                await mcp_client.call_tool("swag_list", {"config_type": "all"})

    @pytest.mark.asyncio
    async def test_swag_create_error_handling(self, mcp_client: Client):
        """Test swag_create tool error handling (lines 123-126)."""
        from fastmcp.exceptions import ToolError

        # Patch the global swag_service instance
        with patch("swag_mcp.tools.swag.swag_service") as mock_service:
            # Mock validate_template_exists to succeed so we reach create_config
            mock_service.validate_template_exists = AsyncMock(return_value=True)
            mock_service.create_config = AsyncMock(side_effect=Exception("Create error"))

            with pytest.raises(ToolError, match="Create error"):
                await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": "errorapp",
                        "server_name": "errorapp.example.com",
                        "upstream_app": "errorapp",
                        "upstream_port": 3000,
                    },
                )

    @pytest.mark.asyncio
    async def test_swag_view_error_handling(self, mcp_client: Client):
        """Test swag_view tool error handling (lines 150-153)."""
        from fastmcp.exceptions import ToolError

        # Patch the global swag_service instance
        with patch("swag_mcp.tools.swag.swag_service") as mock_service:
            mock_service.read_config = AsyncMock(side_effect=Exception("Read error"))

            with pytest.raises(ToolError, match="Read error"):
                await mcp_client.call_tool("swag_view", {"config_name": "test.conf"})

    @pytest.mark.asyncio
    async def test_swag_edit_error_handling(self, mcp_client: Client):
        """Test swag_edit tool error handling (lines 193-196)."""
        from fastmcp.exceptions import ToolError

        # Patch the global swag_service instance
        with patch("swag_mcp.tools.swag.swag_service") as mock_service:
            mock_service.update_config = AsyncMock(side_effect=Exception("Edit error"))

            with pytest.raises(ToolError, match="Edit error"):
                await mcp_client.call_tool(
                    "swag_edit", {"config_name": "test.conf", "new_content": "# New content"}
                )

    @pytest.mark.asyncio
    async def test_swag_remove_error_handling(self, mcp_client: Client):
        """Test swag_remove tool error handling (lines 265-268)."""
        from fastmcp.exceptions import ToolError

        # Patch the global swag_service instance
        with patch("swag_mcp.tools.swag.swag_service") as mock_service:
            mock_service.remove_config = AsyncMock(side_effect=Exception("Remove error"))

            with pytest.raises(ToolError, match="Remove error"):
                await mcp_client.call_tool("swag_remove", {"config_name": "test.conf"})

    @pytest.mark.asyncio
    async def test_swag_logs_error_handling(self, mcp_client: Client):
        """Test swag_logs tool error handling (lines 293-304)."""
        from fastmcp.exceptions import ToolError

        # Patch the global swag_service instance
        with patch("swag_mcp.tools.swag.swag_service") as mock_service:
            mock_service.get_docker_logs = AsyncMock(side_effect=Exception("Logs error"))

            with pytest.raises(ToolError, match="Logs error"):
                await mcp_client.call_tool("swag_logs", {})

    @pytest.mark.asyncio
    async def test_swag_config_error_handling(self, mcp_client: Client):
        """Test swag_config tool error handling (lines 328-335)."""
        from unittest.mock import PropertyMock

        from fastmcp.exceptions import ToolError

        # Patch the config object to raise an error when accessing attributes
        with patch("swag_mcp.tools.swag.config") as mock_config:
            # Use PropertyMock to raise an exception when the property is accessed
            type(mock_config).default_auth_method = PropertyMock(
                side_effect=Exception("Config error")
            )

            with pytest.raises(ToolError, match="Config error"):
                await mcp_client.call_tool("swag_config", {})
