"""External dependency mocking tests for SWAG MCP tool.

Tests isolated behavior by mocking external services like Docker, HTTP, and file system.
Ensures deterministic testing by eliminating external dependencies.
"""

import asyncio
import subprocess
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
from fastmcp import Client
# TextContent no longer needed - using result.data instead


class TestDockerMocking:
    """Test Docker command mocking scenarios."""

    @pytest.mark.asyncio
    async def test_docker_logs_successful_execution(self, mcp_client: Client):
        """Test successful Docker logs retrieval with mocked subprocess."""
        mock_log_output = """
2024-01-15 10:30:00 [INFO] SWAG container started
2024-01-15 10:30:01 [INFO] Loading SSL certificate
2024-01-15 10:30:02 [INFO] Starting nginx
2024-01-15 10:30:03 [INFO] Ready to serve requests
"""
        
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.return_value = MagicMock(
                returncode=0,
                stdout=mock_log_output.strip(),
                stderr=""
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "logs",
                "lines": 50
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            assert response["lines_requested"] == 50
            assert "SWAG container started" in response["logs"]
            assert "Ready to serve requests" in response["logs"]
            
            # Verify subprocess was called with correct parameters
            mock_subprocess.assert_called_once()
            call_args = mock_subprocess.call_args
            assert "docker" in call_args[0][0]
            assert "logs" in call_args[0][0]
            assert "--tail" in call_args[0][0]
            assert "50" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_docker_container_not_found_error(self, mcp_client: Client):
        """Test Docker container not found error handling."""
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.side_effect = subprocess.CalledProcessError(
                1, 
                ["docker", "logs", "--tail", "100", "swag"],
                stderr="Error: No such container: swag"
            )
            
            result = await mcp_client.call_tool("swag", {"action": "logs"})
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "container" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_docker_daemon_not_running_error(self, mcp_client: Client):
        """Test Docker daemon not running error handling."""
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.side_effect = subprocess.CalledProcessError(
                1,
                ["docker", "logs", "--tail", "100", "swag"],
                stderr="Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?"
            )
            
            result = await mcp_client.call_tool("swag", {"action": "logs"})
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "docker" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_docker_permission_denied_error(self, mcp_client: Client):
        """Test Docker permission denied error handling."""
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.side_effect = subprocess.CalledProcessError(
                1,
                ["docker", "logs", "--tail", "100", "swag"],
                stderr="Got permission denied while trying to connect to the Docker daemon socket"
            )
            
            result = await mcp_client.call_tool("swag", {"action": "logs"})
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "permission" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_docker_logs_empty_output(self, mcp_client: Client):
        """Test Docker logs with empty output."""
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            result = await mcp_client.call_tool("swag", {"action": "logs"})
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            assert response["logs"] == ""
            assert response["character_count"] == 0

    @pytest.mark.asyncio
    async def test_docker_logs_with_stderr_warnings(self, mcp_client: Client):
        """Test Docker logs with stderr warnings."""
        mock_stdout = "2024-01-15 10:30:00 [INFO] Container running normally"
        mock_stderr = "WARNING: Container health check failed"
        
        with patch('subprocess.run') as mock_subprocess:
            mock_subprocess.return_value = MagicMock(
                returncode=0,
                stdout=mock_stdout,
                stderr=mock_stderr
            )
            
            result = await mcp_client.call_tool("swag", {"action": "logs"})
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            # Should contain stdout logs
            assert "Container running normally" in response["logs"]


class TestHTTPMocking:
    """Test HTTP health check mocking scenarios."""

    @pytest.mark.asyncio
    async def test_http_health_check_success_200(self, mcp_client: Client):
        """Test successful HTTP health check with 200 response."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(
                success=True,
                status_code=200,
                response_time_ms=150,
                error=None
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "healthy.example.com",
                "timeout": 30
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            assert response["status_code"] == 200
            assert response["response_time_ms"] == 150
            assert response["error"] is None

    @pytest.mark.asyncio
    async def test_http_health_check_redirect_301(self, mcp_client: Client):
        """Test HTTP health check with redirect."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(
                success=True,
                status_code=301,
                response_time_ms=200,
                error=None
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "redirect.example.com",
                "follow_redirects": True
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            assert response["status_code"] == 301

    @pytest.mark.asyncio
    async def test_http_health_check_server_error_500(self, mcp_client: Client):
        """Test HTTP health check with server error."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(
                success=False,
                status_code=500,
                response_time_ms=1000,
                error="Internal server error"
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "broken.example.com"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert response["status_code"] == 500
            assert response["error"] == "Internal server error"

    @pytest.mark.asyncio
    async def test_http_health_check_connection_timeout(self, mcp_client: Client):
        """Test HTTP health check with connection timeout."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(
                success=False,
                status_code=None,
                response_time_ms=None,
                error="Connection timeout after 30 seconds"
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "timeout.example.com",
                "timeout": 30
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert response["status_code"] is None
            assert "timeout" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_http_health_check_ssl_certificate_error(self, mcp_client: Client):
        """Test HTTP health check with SSL certificate error."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(
                success=False,
                status_code=None,
                response_time_ms=None,
                error="SSL certificate verification failed: self signed certificate"
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "badssl.example.com"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "ssl" in response["error"].lower() or "certificate" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_http_health_check_dns_resolution_failure(self, mcp_client: Client):
        """Test HTTP health check with DNS resolution failure."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(
                success=False,
                status_code=None,
                response_time_ms=None,
                error="DNS resolution failed: Name or service not known"
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "nonexistent-domain.invalid"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "dns" in response["error"].lower() or "resolution" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_http_health_check_connection_refused(self, mcp_client: Client):
        """Test HTTP health check with connection refused."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(
                success=False,
                status_code=None,
                response_time_ms=None,
                error="Connection refused"
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "offline.example.com"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "connection refused" in response["error"].lower()


class TestFileSystemMocking:
    """Test file system operation mocking scenarios."""

    @pytest.mark.asyncio
    async def test_read_config_file_success(self, mcp_client: Client):
        """Test successful config file reading with mocked file system."""
        mock_content = """# Test configuration
server {
    listen 443 ssl http2;
    server_name test.example.com;
    
    location / {
        set $upstream_app testapp;
        set $upstream_port 8080;
        proxy_pass http://$upstream_app:$upstream_port;
    }
}
"""
        
        with patch('swag_mcp.services.swag_manager.SwagManagerService.read_config') as mock_read:
            mock_read.return_value = mock_content
            
            result = await mcp_client.call_tool("swag", {
                "action": "view",
                "config_name": "test.conf"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            assert response["content"] == mock_content
            assert response["character_count"] == len(mock_content)
            
            mock_read.assert_called_once_with("test.conf")

    @pytest.mark.asyncio
    async def test_read_config_file_not_found(self, mcp_client: Client):
        """Test config file not found with mocked file system."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.read_config') as mock_read:
            mock_read.side_effect = FileNotFoundError("Configuration file 'missing.conf' not found")
            
            result = await mcp_client.call_tool("swag", {
                "action": "view",
                "config_name": "missing.conf"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "not found" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_read_config_permission_denied(self, mcp_client: Client):
        """Test config file permission denied with mocked file system."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.read_config') as mock_read:
            mock_read.side_effect = PermissionError("Permission denied accessing 'restricted.conf'")
            
            result = await mcp_client.call_tool("swag", {
                "action": "view",
                "config_name": "restricted.conf"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "permission" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_write_config_disk_full(self, mcp_client: Client, sample_configs):
        """Test config file write with disk full error."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.update_config') as mock_update:
            mock_update.side_effect = OSError("No space left on device")
            
            result = await mcp_client.call_tool("swag", {
                "action": "edit",
                "config_name": "test.conf",
                "new_content": "# New content"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "space" in response["error"].lower() or "disk" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_list_configs_with_mocked_directory(self, mcp_client: Client):
        """Test listing configurations with mocked directory operations."""
        mock_config_list = MagicMock(
            total_count=3,
            configs=[
                {"name": "app1.conf", "type": "active", "size": 1024},
                {"name": "app2.conf", "type": "active", "size": 2048},
                {"name": "sample.conf.sample", "type": "sample", "size": 512}
            ]
        )
        
        with patch('swag_mcp.services.swag_manager.SwagManagerService.list_configs') as mock_list:
            mock_list.return_value = mock_config_list
            
            result = await mcp_client.call_tool("swag", {
                "action": "list",
                "config_type": "all"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            assert response["total_count"] == 3
            assert len(response["configs"]) == 3
            
            mock_list.assert_called_once_with("all")

    @pytest.mark.asyncio
    async def test_create_config_with_mocked_template_rendering(self, mcp_client: Client):
        """Test config creation with mocked template rendering."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            
            # Mock successful creation
            mock_create.return_value = MagicMock(filename="templated.conf")
            mock_health.return_value = MagicMock(success=True, status_code=200, response_time_ms=100, error=None)
            
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "templated",
                "server_name": "templated.example.com",
                "upstream_app": "templated-app",
                "upstream_port": 8080,
                "config_type_create": "subdomain"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            assert response["filename"] == "templated.conf"
            
            # Verify template creation was called
            mock_create.assert_called_once()


class TestTemplateMocking:
    """Test template system mocking scenarios."""

    @pytest.mark.asyncio
    async def test_template_not_found_error(self, mcp_client: Client):
        """Test template not found error handling."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=False):
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "missing-template",
                "server_name": "missing.example.com",
                "upstream_app": "missing-app",
                "upstream_port": 8080,
                "config_type_create": "nonexistent"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "template" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_template_rendering_syntax_error(self, mcp_client: Client):
        """Test template rendering syntax error handling."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create:
            
            from jinja2 import TemplateSyntaxError
            mock_create.side_effect = TemplateSyntaxError("Unexpected end of template")
            
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "syntax-error",
                "server_name": "syntax.example.com",
                "upstream_app": "syntax-app",
                "upstream_port": 8080
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "template" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_template_rendering_undefined_variable(self, mcp_client: Client):
        """Test template rendering with undefined variable."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create:
            
            from jinja2 import UndefinedError
            mock_create.side_effect = UndefinedError("'undefined_variable' is undefined")
            
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "undefined-var",
                "server_name": "undefined.example.com",
                "upstream_app": "undefined-app",
                "upstream_port": 8080
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "template" in response["error"].lower()


class TestBackupMocking:
    """Test backup operation mocking scenarios."""

    @pytest.mark.asyncio
    async def test_backup_creation_success(self, mcp_client: Client, sample_configs):
        """Test successful backup creation."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.update_config') as mock_update:
            mock_update.return_value = MagicMock(backup_created="test.conf.backup.20241128_120000")
            
            result = await mcp_client.call_tool("swag", {
                "action": "edit",
                "config_name": "test.conf",
                "new_content": "# Updated with backup",
                "create_backup": True
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            assert response["backup_created"] == "test.conf.backup.20241128_120000"

    @pytest.mark.asyncio
    async def test_backup_creation_failure(self, mcp_client: Client, sample_configs):
        """Test backup creation failure."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.update_config') as mock_update:
            mock_update.side_effect = OSError("Failed to create backup: Permission denied")
            
            result = await mcp_client.call_tool("swag", {
                "action": "edit",
                "config_name": "test.conf",
                "new_content": "# Updated content",
                "create_backup": True
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "backup" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_backup_cleanup_multiple_files(self, mcp_client: Client):
        """Test backup cleanup with multiple files."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.cleanup_old_backups') as mock_cleanup:
            mock_cleanup.return_value = 5  # 5 files cleaned
            
            result = await mcp_client.call_tool("swag", {
                "action": "cleanup_backups",
                "retention_days": 30
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            assert response["cleaned_count"] == 5
            assert response["retention_days"] == 30
            
            mock_cleanup.assert_called_once_with(30)

    @pytest.mark.asyncio
    async def test_backup_cleanup_no_files(self, mcp_client: Client):
        """Test backup cleanup with no files to clean."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.cleanup_old_backups') as mock_cleanup:
            mock_cleanup.return_value = 0  # No files to clean
            
            result = await mcp_client.call_tool("swag", {"action": "cleanup_backups"})
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            assert response["cleaned_count"] == 0
            assert "No old backup files" in response["message"]


class TestAsyncMocking:
    """Test async operation mocking scenarios."""

    @pytest.mark.asyncio
    async def test_async_health_check_timeout(self, mcp_client: Client):
        """Test async health check timeout simulation."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.side_effect = asyncio.TimeoutError()
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "async-timeout.example.com"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            # Should handle the timeout gracefully

    @pytest.mark.asyncio
    async def test_async_operation_cancelled(self, mcp_client: Client):
        """Test async operation cancellation handling."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.side_effect = asyncio.CancelledError()
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "cancelled.example.com"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False

    @pytest.mark.asyncio
    async def test_async_mock_with_delay_simulation(self, mcp_client: Client):
        """Test async operation with simulated delay."""
        async def slow_health_check(*args, **kwargs):
            await asyncio.sleep(0.001)  # Minimal delay for testing
            return MagicMock(
                success=True,
                status_code=200,
                response_time_ms=1000,  # Simulated slow response
                error=None
            )
        
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check', side_effect=slow_health_check):
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "slow.example.com"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            assert response["response_time_ms"] == 1000


class TestComplexMockingScenarios:
    """Test complex mocking scenarios with multiple dependencies."""

    @pytest.mark.asyncio
    async def test_create_config_with_all_dependencies_mocked(self, mcp_client: Client):
        """Test config creation with all external dependencies mocked."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health, \
             patch('subprocess.run') as mock_subprocess:
            
            # Mock all dependencies
            mock_create.return_value = MagicMock(filename="complex.conf")
            mock_health.return_value = MagicMock(success=True, status_code=200, response_time_ms=150, error=None)
            mock_subprocess.return_value = MagicMock(returncode=0, stdout="Container restarted", stderr="")
            
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "complex",
                "server_name": "complex.example.com",
                "upstream_app": "complex-app",
                "upstream_port": 8080,
                "auth_method": "authelia",
                "enable_quic": True
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            assert response["filename"] == "complex.conf"
            assert "health_check" in response
            
            # Verify all mocks were used appropriately
            mock_create.assert_called_once()
            mock_health.assert_called_once()

    @pytest.mark.asyncio
    async def test_cascade_failure_with_multiple_mocks(self, mcp_client: Client):
        """Test cascade failure scenario with multiple mocked dependencies."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=False), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            
            # Template validation fails, should short-circuit before other calls
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "cascade-fail",
                "server_name": "cascade.example.com",
                "upstream_app": "cascade-app",
                "upstream_port": 8080
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is False
            assert "template" in response["error"].lower()
            
            # Verify downstream methods were not called due to early failure
            mock_create.assert_not_called()
            mock_health.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_mock_success_with_real_logic(self, mcp_client: Client):
        """Test scenario with some mocked and some real logic."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            # Mock only health check, let other logic run normally
            mock_health.return_value = MagicMock(success=True, status_code=200, response_time_ms=100, error=None)
            
            # Test config retrieval (should use real logic)
            result = await mcp_client.call_tool("swag", {"action": "config"})
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True
            assert "defaults" in response
            
            # Health check mock should not have been called for config action
            mock_health.assert_not_called()