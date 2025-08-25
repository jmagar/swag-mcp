"""Behavior-focused tests for SWAG MCP tools.

These tests focus on verifying server behavior rather than implementation details,
following FastMCP testing best practices.
"""

from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError


class TestSwagToolsBehavior:
    """Behavior-focused test suite for SWAG MCP tools."""

    @pytest.mark.asyncio
    async def test_create_config_with_invalid_template_behavior(
        self, mcp_client: Client, mock_config
    ):
        """Test server behavior when template is missing - should provide clear error."""
        # Remove template files to create real error condition
        template_dir = Path(mock_config.template_path)
        subdomain_template = template_dir / "subdomain.conf.j2"

        # Backup original if it exists
        backup_content = None
        if subdomain_template.exists():
            backup_content = subdomain_template.read_text()
            subdomain_template.unlink()

        try:
            # Test behavior: server should detect missing template and provide helpful error
            with pytest.raises(ToolError) as exc_info:
                await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": "testapp",
                        "server_name": "testapp.example.com",
                        "upstream_app": "testapp",
                        "upstream_port": 3000,
                        "config_type": "subdomain",
                    },
                )

            # Verify behavior: error message should mention template issue
            error_message = str(exc_info.value)
            assert "template" in error_message.lower() or "not found" in error_message.lower()

        finally:
            # Restore template if we backed it up
            if backup_content and subdomain_template.parent.exists():
                subdomain_template.write_text(backup_content)

    @pytest.mark.asyncio
    async def test_create_config_with_readonly_directory_behavior(
        self, mcp_client: Client, mock_config
    ):
        """Test server behavior when target directory is read-only."""
        config_dir = Path(mock_config.proxy_confs_path)

        # Make directory read-only to create real error condition
        original_mode = config_dir.stat().st_mode
        try:
            config_dir.chmod(0o444)  # Read-only

            # Test behavior: server should handle permission error gracefully
            with pytest.raises(ToolError) as exc_info:
                await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": "testapp",
                        "server_name": "testapp.example.com",
                        "upstream_app": "testapp",
                        "upstream_port": 3000,
                    },
                )

            # Verify behavior: error should indicate permission issue
            error_message = str(exc_info.value)
            assert any(word in error_message.lower() for word in ["permission", "access", "denied"])

        finally:
            # Restore original permissions
            config_dir.chmod(original_mode)

    @pytest.mark.asyncio
    async def test_view_config_file_corruption_behavior(
        self, mcp_client: Client, mock_config, sample_configs
    ):
        """Test server behavior when viewing a corrupted configuration file."""
        config_path = Path(mock_config.proxy_confs_path) / "corrupted.conf"

        # Create a corrupted file (binary content)
        config_path.write_bytes(b"\x00\x01\x02\xff\xfe\xfd")

        try:
            # Test behavior: server should detect and reject binary content
            with pytest.raises(ToolError) as exc_info:
                await mcp_client.call_tool("swag_view", {"config_name": "corrupted.conf"})

            # Verify behavior: should provide clear security error message
            error_message = str(exc_info.value).lower()
            assert any(
                word in error_message for word in ["binary", "unsafe", "content", "validation"]
            )
            assert "corrupted.conf" in error_message

        finally:
            if config_path.exists():
                config_path.unlink()

    @pytest.mark.asyncio
    async def test_concurrent_config_creation_behavior(self, mcp_client: Client, mock_config):
        """Test server behavior when creating multiple configs concurrently."""
        import asyncio

        # Test behavior: concurrent operations should not interfere with each other
        async def create_config(service_name: str):
            return await mcp_client.call_tool(
                "swag_create",
                {
                    "service_name": service_name,
                    "server_name": f"{service_name}.example.com",
                    "upstream_app": service_name,
                    "upstream_port": 3000,
                },
            )

        # Run multiple concurrent create operations
        results = await asyncio.gather(
            create_config("app1"),
            create_config("app2"),
            create_config("app3"),
            return_exceptions=True,
        )

        config_dir = Path(mock_config.proxy_confs_path)

        try:
            # Verify behavior: all operations should succeed or fail gracefully
            for i, result in enumerate(results, 1):
                service_name = f"app{i}"
                if isinstance(result, Exception):
                    # If exception, should be a proper ToolError
                    assert isinstance(result, ToolError)
                else:
                    # If successful, config file should exist
                    assert not result.is_error
                    config_file = config_dir / f"{service_name}.subdomain.conf"
                    assert config_file.exists()

                    # Content should be valid
                    content = config_file.read_text()
                    assert service_name in content

        finally:
            # Cleanup
            for i in range(1, 4):
                config_file = config_dir / f"app{i}.subdomain.conf"
                if config_file.exists():
                    config_file.unlink()

    @pytest.mark.asyncio
    async def test_large_config_file_behavior(self, mcp_client: Client, mock_config):
        """Test server behavior when handling very large configuration files."""
        config_dir = Path(mock_config.proxy_confs_path)
        large_config = config_dir / "large.conf"

        # Create a large config file (1MB)
        large_content = "# Large config file\n" + "# Comment line\n" * 50000
        large_config.write_text(large_content)

        try:
            # Test behavior: server should handle large files gracefully
            result = await mcp_client.call_tool("swag_view", {"config_name": "large.conf"})

            # Verify behavior: should either succeed or fail with helpful error
            if result.is_error:
                error_message = str(result.error) if result.error else ""
                assert "size" in error_message.lower() or "memory" in error_message.lower()
            else:
                # Should return the content
                assert isinstance(result.data, str)
                assert len(result.data) > 100000  # Should be large

        finally:
            if large_config.exists():
                large_config.unlink()

    @pytest.mark.asyncio
    async def test_config_name_validation_behavior(self, mcp_client: Client):
        """Test server behavior with various invalid configuration names."""
        invalid_names = [
            "../../../etc/passwd",  # Path traversal
            "config\x00.conf",  # Null byte injection
            "config\n.conf",  # Newline injection
            "config with spaces.conf",  # Spaces
            "config|rm -rf /.conf",  # Command injection attempt
            "a" * 300 + ".conf",  # Very long name
        ]

        for invalid_name in invalid_names:
            # Test behavior: server should reject invalid names
            with pytest.raises(ToolError) as exc_info:
                await mcp_client.call_tool("swag_view", {"config_name": invalid_name})

            # Verify behavior: error should indicate validation issue
            error_message = str(exc_info.value).lower()
            assert any(
                word in error_message
                for word in [
                    "invalid",
                    "validation",
                    "not allowed",
                    "characters",
                    "patterns",
                    "filename",
                    "must end",
                ]
            ), f"Expected validation error for '{invalid_name}', got: {error_message}"

    @pytest.mark.asyncio
    async def test_workflow_consistency_behavior(
        self, mcp_client: Client, mock_config, test_helpers
    ):
        """Test complete workflow behavior: create → view → edit → remove."""
        service_name = "workflow-test"
        config_name = f"{service_name}.subdomain.conf"
        config_dir = Path(mock_config.proxy_confs_path)
        config_file = config_dir / config_name

        try:
            # Step 1: Create config
            create_result = await mcp_client.call_tool(
                "swag_create",
                {
                    "service_name": service_name,
                    "server_name": f"{service_name}.example.com",
                    "upstream_app": service_name,
                    "upstream_port": 8080,
                },
            )
            assert not create_result.is_error
            assert config_file.exists()

            # Step 2: View config - should match what we created
            view_result = await mcp_client.call_tool("swag_view", {"config_name": config_name})
            assert not view_result.is_error
            original_content = view_result.data
            assert service_name in original_content
            assert "8080" in original_content

            # Step 3: Edit config - should preserve behavior
            modified_content = original_content.replace("8080", "9090")
            edit_result = await mcp_client.call_tool(
                "swag_edit",
                {"config_name": config_name, "new_content": modified_content},
            )
            assert not edit_result.is_error

            # Verify edit behavior: content should be updated
            view_after_edit = await mcp_client.call_tool("swag_view", {"config_name": config_name})
            assert not view_after_edit.is_error
            assert "9090" in view_after_edit.data
            assert "8080" not in view_after_edit.data

            # Step 4: Remove config - should clean up completely
            remove_result = await mcp_client.call_tool("swag_remove", {"config_name": config_name})
            assert not remove_result.is_error

            # Verify removal behavior: file should be gone, backup should exist
            assert not config_file.exists()
            backup_files = list(config_dir.glob(f"{config_name}.backup.*"))
            assert len(backup_files) >= 1

        finally:
            # Cleanup any remaining files
            if config_file.exists():
                config_file.unlink()
            for backup_file in config_dir.glob(f"{config_name}.backup.*"):
                backup_file.unlink()
