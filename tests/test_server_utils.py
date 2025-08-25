"""Tests for SWAG MCP server utility functions."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from swag_mcp.server import (
    _extract_service_name,
    cleanup_old_backups,
    detect_execution_context,
    setup_templates,
)


class TestServerUtilityFunctions:
    """Test suite for server utility functions."""

    def test_extract_service_name_basic(self):
        """Test extracting service name from basic config filename."""
        assert _extract_service_name("myapp.conf") == "myapp"
        assert _extract_service_name("webapp.conf") == "webapp"
        assert _extract_service_name("api.conf") == "api"

    def test_extract_service_name_subdomain(self):
        """Test extracting service name from subdomain config filename."""
        assert _extract_service_name("myapp.subdomain.conf") == "myapp"
        assert _extract_service_name("webapp.subdomain.conf") == "webapp"
        assert _extract_service_name("api-service.subdomain.conf") == "api-service"

    def test_extract_service_name_subfolder(self):
        """Test extracting service name from subfolder config filename."""
        assert _extract_service_name("myapp.subfolder.conf") == "myapp"
        assert _extract_service_name("webapp.subfolder.conf") == "webapp"
        assert _extract_service_name("api-service.subfolder.conf") == "api-service"

    def test_extract_service_name_edge_cases(self):
        """Test extracting service name from edge case filenames."""
        # Without .conf extension
        assert _extract_service_name("myapp") == "myapp"
        assert _extract_service_name("myapp.subdomain") == "myapp"
        assert _extract_service_name("myapp.subfolder") == "myapp"

        # Complex names
        assert _extract_service_name("my-complex-app.subdomain.conf") == "my-complex-app"
        assert (
            _extract_service_name("app_with_underscores.subfolder.conf") == "app_with_underscores"
        )

    @patch("swag_mcp.server.logger")
    def test_setup_templates_directory_exists(self, mock_logger):
        """Test setup_templates when template directory exists."""
        with tempfile.TemporaryDirectory() as temp_dir:
            template_path = Path(temp_dir)

            # Create all required template files
            (template_path / "subdomain.conf.j2").touch()
            (template_path / "subfolder.conf.j2").touch()
            (template_path / "mcp-subdomain.conf.j2").touch()
            (template_path / "mcp-subfolder.conf.j2").touch()

            with patch("swag_mcp.server.config.template_path", template_path):
                setup_templates()

            # Should not log any warnings or errors
            mock_logger.warning.assert_not_called()
            mock_logger.error.assert_not_called()

    @patch("swag_mcp.server.logger")
    def test_setup_templates_directory_missing(self, mock_logger):
        """Test setup_templates when template directory doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            template_path = Path(temp_dir) / "nonexistent"

            with patch("swag_mcp.server.config.template_path", template_path):
                setup_templates()

            # Should create directory and log warning
            assert template_path.exists()
            mock_logger.warning.assert_called()

    @patch("swag_mcp.server.logger")
    def test_setup_templates_missing_templates(self, mock_logger):
        """Test setup_templates when template files are missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            template_path = Path(temp_dir)

            # Don't create template files

            with patch("swag_mcp.server.config.template_path", template_path):
                setup_templates()

            # Should log errors for missing templates
            # (4 templates: subdomain, subfolder, mcp-subdomain, mcp-subfolder)
            assert mock_logger.error.call_count == 4
            error_calls = [call[0][0] for call in mock_logger.error.call_args_list]
            assert any("subdomain.conf.j2" in call for call in error_calls)
            assert any("subfolder.conf.j2" in call for call in error_calls)
            assert any("mcp-subdomain.conf.j2" in call for call in error_calls)
            assert any("mcp-subfolder.conf.j2" in call for call in error_calls)

    def test_detect_execution_context_no_loop(self):
        """Test detect_execution_context when no event loop is running."""
        # This test runs in a sync context (pytest doesn't run tests in async by default)
        context = detect_execution_context()
        assert context == "sync"

    @pytest.mark.asyncio
    async def test_detect_execution_context_with_loop(self):
        """Test detect_execution_context when an event loop is running."""
        # This test runs in an async context (marked with @pytest.mark.asyncio)
        context = detect_execution_context()
        assert context == "async"

    @patch("swag_mcp.server.logger")
    @pytest.mark.asyncio
    async def test_cleanup_old_backups_success(self, mock_logger):
        """Test cleanup_old_backups function executes successfully."""
        # Mock the SwagManagerService
        mock_service = MagicMock()
        mock_service.cleanup_old_backups = AsyncMock(return_value=3)

        with patch("swag_mcp.server.SwagManagerService", return_value=mock_service):
            await cleanup_old_backups()

        # Should call the service cleanup method
        mock_service.cleanup_old_backups.assert_called_once()

        # Should log the cleanup result
        mock_logger.info.assert_called_with("Startup cleanup: removed 3 old backup files")

    @patch("swag_mcp.server.logger")
    @pytest.mark.asyncio
    async def test_cleanup_old_backups_no_files(self, mock_logger):
        """Test cleanup_old_backups when no files need cleanup."""
        # Mock the SwagManagerService
        mock_service = MagicMock()
        mock_service.cleanup_old_backups = AsyncMock(return_value=0)

        with patch("swag_mcp.server.SwagManagerService", return_value=mock_service):
            await cleanup_old_backups()

        # Should call the service cleanup method
        mock_service.cleanup_old_backups.assert_called_once()

        # Should log debug message for no files
        mock_logger.debug.assert_called_with("Startup cleanup: no old backup files to remove")

    @patch("swag_mcp.server.logger")
    @pytest.mark.asyncio
    async def test_cleanup_old_backups_error_handling(self, mock_logger):
        """Test cleanup_old_backups error handling."""
        # Mock the SwagManagerService to raise an exception
        mock_service = MagicMock()
        mock_service.cleanup_old_backups = AsyncMock(side_effect=Exception("Cleanup failed"))

        with patch("swag_mcp.server.SwagManagerService", return_value=mock_service):
            await cleanup_old_backups()

        # Should call the service cleanup method
        mock_service.cleanup_old_backups.assert_called_once()

        # Should log the error
        mock_logger.error.assert_called_with(
            "Failed to cleanup old backups on startup: Cleanup failed"
        )


class TestServerIntegration:
    """Test server integration and initialization functions."""

    @pytest.mark.asyncio
    async def test_server_main_functions_importable(self):
        """Test that main server functions can be imported and are callable."""
        from swag_mcp.server import create_mcp_server, main, main_sync

        assert callable(main)
        assert callable(main_sync)
        assert callable(create_mcp_server)

    @patch("swag_mcp.server.setup_templates")
    @patch("swag_mcp.server.cleanup_old_backups")
    @patch("swag_mcp.server.create_mcp_server")
    @pytest.mark.asyncio
    async def test_main_async_execution_path(self, mock_create_server, mock_cleanup, mock_setup):
        """Test main() async execution path."""
        # Mock the server to avoid actual startup
        mock_server = AsyncMock()
        mock_create_server.return_value = mock_server
        mock_cleanup.return_value = None

        from swag_mcp.server import main

        # This should execute the main async path (lines 175-189)
        # We can't patch properties directly, so mock the config object
        with patch("swag_mcp.server.config") as mock_config:
            mock_config.host = "localhost"
            mock_config.port = 8000
            mock_config.proxy_confs_path = Path("/test/proxy-confs")
            mock_config.data_path = Path("/test/data")
            mock_config.templates_path = Path("/test/templates")
            mock_config.default_auth_method = "authelia"
            mock_config.default_config_type = "subdomain"
            mock_config.default_quic_enabled = False

            # Mock run_async to avoid actual server startup
            mock_server.run_async = AsyncMock()

            await main()

            # Verify the execution path
            mock_setup.assert_called_once()
            mock_cleanup.assert_called_once()
            mock_create_server.assert_called_once()
            mock_server.run_async.assert_called_once_with(
                transport="streamable-http", host="localhost", port=8000
            )

    @patch("swag_mcp.server.setup_templates")
    @patch("swag_mcp.server.asyncio.run")
    def test_main_sync_execution_path(self, mock_asyncio_run, mock_setup):
        """Test main_sync() execution path."""
        from swag_mcp.server import main_sync

        # This should execute the sync path (lines 194-212)
        main_sync()

        # Verify the execution path
        mock_setup.assert_called_once()
        mock_asyncio_run.assert_called_once()
