"""Simple tests for server.py to improve coverage."""

from unittest.mock import Mock, patch

from swag_mcp.core.config import config
from swag_mcp.server import (
    _extract_service_name,
    cleanup_old_backups,
    create_mcp_server,
    detect_execution_context,
    register_resources,
    setup_templates,
)


class TestServerFunctions:
    """Test server setup functions."""

    def test_extract_service_name(self):
        """Test service name extraction from filename."""
        test_cases = [
            ("test.subdomain.conf", "test"),
            ("example-service.subfolder.conf", "example-service"),
            ("my_app.subdomain.conf.sample", "my_app"),
            ("simple.conf", "simple"),
        ]

        for filename, expected in test_cases:
            result = _extract_service_name(filename)
            assert result == expected

    def test_detect_execution_context(self):
        """Test execution context detection."""
        context = detect_execution_context()
        assert isinstance(context, str)
        assert len(context) > 0

    def test_setup_templates(self):
        """Test template setup function."""
        # Should not raise an exception
        setup_templates()

    async def test_cleanup_old_backups(self):
        """Test cleanup old backups function."""
        # Should not raise an exception for async function
        await cleanup_old_backups()

    async def test_create_mcp_server(self):
        """Test MCP server creation."""
        with patch("swag_mcp.server.FastMCP") as mock_fastmcp:
            mock_app = Mock()
            mock_fastmcp.return_value = mock_app

            result = await create_mcp_server()
            assert result == mock_app
            mock_fastmcp.assert_called_once_with("SWAG Configuration Manager")

    async def test_register_resources(self):
        """Test resource registration function."""
        mock_app = Mock()
        mock_app.add_resource = Mock()

        # Should not raise an exception
        register_resources(mock_app)

    def test_config_access(self):
        """Test that server can access configuration."""
        # Should be able to access config without errors
        assert config is not None
        assert hasattr(config, "proxy_confs_path")
        assert hasattr(config, "host")
        assert hasattr(config, "port")

    def test_extract_service_name_edge_cases(self):
        """Test service name extraction with edge cases."""
        edge_cases = [
            ("", ""),  # Empty string
            ("no-extension", "no-extension"),  # No extension
            ("multiple.dots.in.filename.conf", "multiple.dots.in.filename"),
            ("ending-with-dot.conf.", "ending-with-dot"),
        ]

        for filename, expected in edge_cases:
            result = _extract_service_name(filename)
            assert result == expected

