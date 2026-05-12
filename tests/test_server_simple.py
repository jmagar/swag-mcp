"""Simple tests for server.py to improve coverage."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from swag_mcp.core.config import config
from swag_mcp.server import (
    StaticBearerTokenProvider,
    _build_auth_provider,
    _extract_service_name,
    _validate_bearer_token,
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
        with patch("swag_mcp.server.SwagManagerService") as service_cls:
            service = service_cls.return_value.__aenter__.return_value
            service.cleanup_old_backups = AsyncMock(return_value=0)

            await cleanup_old_backups()

            service_cls.return_value.__aenter__.assert_awaited_once()
            service.cleanup_old_backups.assert_awaited_once()
            service_cls.return_value.__aexit__.assert_awaited_once()

    async def test_create_mcp_server(self):
        """Test MCP server creation."""
        with patch("swag_mcp.server.FastMCP") as mock_fastmcp:
            mock_app = Mock()
            mock_fastmcp.return_value = mock_app

            result = await create_mcp_server()
            assert result == mock_app
            mock_fastmcp.assert_called_once_with("SWAG Configuration Manager", auth=None)

    async def test_static_bearer_token_provider_accepts_only_configured_token(self):
        """Static bearer provider accepts only the configured secret token."""
        provider = StaticBearerTokenProvider("expected-token")

        valid_token = await provider.verify_token("expected-token")
        invalid_token = await provider.verify_token("wrong-token")

        assert valid_token is not None
        assert valid_token.token == "expected-token"
        assert invalid_token is None

    def test_build_auth_provider_uses_static_bearer_token(self, monkeypatch):
        """SWAG_MCP_TOKEN wires FastMCP auth instead of being advisory only."""
        monkeypatch.setenv("SWAG_MCP_TOKEN", "expected-token")
        monkeypatch.delenv("FASTMCP_SERVER_AUTH", raising=False)

        provider = _build_auth_provider()

        assert isinstance(provider, StaticBearerTokenProvider)

    def test_validate_bearer_token_fails_closed_without_auth(self, monkeypatch):
        """Startup refuses unauthenticated mode unless explicitly requested."""
        monkeypatch.delenv("SWAG_MCP_TOKEN", raising=False)
        monkeypatch.delenv("FASTMCP_SERVER_AUTH", raising=False)
        monkeypatch.setenv("SWAG_MCP_NO_AUTH", "false")

        with pytest.raises(SystemExit):
            _validate_bearer_token()

    def test_validate_bearer_token_allows_explicit_no_auth(self, monkeypatch):
        """Explicit no-auth mode remains available for stdio or loopback-only use."""
        monkeypatch.delenv("SWAG_MCP_TOKEN", raising=False)
        monkeypatch.delenv("FASTMCP_SERVER_AUTH", raising=False)
        monkeypatch.setenv("SWAG_MCP_NO_AUTH", "true")

        _validate_bearer_token()

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
