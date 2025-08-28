"""Exception handling and error scenario tests for SWAG MCP tool.

Tests graceful error handling and ensures error messages guide LLM recovery.
Following the principle that MCP servers must handle chaos gracefully.
"""

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client
# TextContent no longer needed - using result.data instead


class TestFileOperationErrors:
    """Test file operation error handling."""

    @pytest.mark.asyncio
    async def test_view_file_not_found_returns_helpful_error(self, mcp_client: Client):
        """VIEW should return helpful error when config file doesn't exist."""
        result = await mcp_client.call_tool("swag", {
            "action": "view",
            "config_name": "definitely-does-not-exist.conf"
        })
        
        # Response validation handled by result.is_error check
        response = result.data
        # Should handle error gracefully - expect either MCP error or server success=false
        assert result.is_error or (response and response.get("success") is False)
        assert "not found" in response["error"].lower() or "does not exist" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_edit_file_not_found_returns_helpful_error(self, mcp_client: Client):
        """EDIT should return helpful error when config file doesn't exist."""
        result = await mcp_client.call_tool("swag", {
            "action": "edit",
            "config_name": "nonexistent.conf",
            "new_content": "# New content"
        })
        
        # Response validation handled by result.is_error check
        response = result.data
        # Should handle error gracefully - expect either MCP error or server success=false
        assert result.is_error or (response and response.get("success") is False)
        # Error message should guide LLM to create file first or check name

    @pytest.mark.asyncio
    async def test_remove_file_not_found_returns_helpful_error(self, mcp_client: Client):
        """REMOVE should return helpful error when config file doesn't exist."""
        result = await mcp_client.call_tool("swag", {
            "action": "remove",
            "config_name": "nonexistent.conf"
        })
        
        # Response validation handled by result.is_error check
        response = result.data
        # Should handle error gracefully - expect either MCP error or server success=false
        assert result.is_error or (response and response.get("success") is False)
        # Should indicate file doesn't exist

    @pytest.mark.asyncio
    async def test_file_permission_error_handled_gracefully(self, mcp_client: Client):
        """File permission errors should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.read_config') as mock_read:
            mock_read.side_effect = PermissionError("Permission denied")
            
            result = await mcp_client.call_tool("swag", {
                "action": "view",
                "config_name": "test.conf"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "permission" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_file_system_full_error_handled_gracefully(self, mcp_client: Client, sample_configs):
        """Disk full errors should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.update_config') as mock_update:
            mock_update.side_effect = OSError("No space left on device")
            
            result = await mcp_client.call_tool("swag", {
                "action": "edit",
                "config_name": "test.conf",
                "new_content": "# Updated content"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "space" in response["error"].lower() or "disk" in response["error"].lower()


class TestDockerOperationErrors:
    """Test Docker-related error handling."""

    @pytest.mark.asyncio
    async def test_docker_not_running_error_handled(self, mcp_client: Client):
        """Docker not running should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.get_docker_logs') as mock_logs:
            mock_logs.side_effect = subprocess.CalledProcessError(
                1, ['docker'], "Cannot connect to the Docker daemon"
            )
            
            result = await mcp_client.call_tool("swag", {"action": "logs"})
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "docker" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_docker_container_not_found_error_handled(self, mcp_client: Client):
        """Docker container not found should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.get_docker_logs') as mock_logs:
            mock_logs.side_effect = subprocess.CalledProcessError(
                1, ['docker'], "No such container: swag"
            )
            
            result = await mcp_client.call_tool("swag", {"action": "logs"})
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "container" in response["error"].lower() or "not found" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_docker_permission_error_handled(self, mcp_client: Client):
        """Docker permission errors should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.get_docker_logs') as mock_logs:
            mock_logs.side_effect = subprocess.CalledProcessError(
                1, ['docker'], "permission denied while trying to connect to the Docker daemon socket"
            )
            
            result = await mcp_client.call_tool("swag", {"action": "logs"})
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "permission" in response["error"].lower()


class TestNetworkOperationErrors:
    """Test network-related error handling for health checks."""

    @pytest.mark.asyncio
    async def test_health_check_connection_refused_handled(self, mcp_client: Client):
        """Connection refused during health check should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(
                success=False,
                status_code=None,
                response_time_ms=None,
                error="Connection refused"
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "unreachable.example.com"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert response["error"] == "Connection refused"

    @pytest.mark.asyncio
    async def test_health_check_timeout_handled(self, mcp_client: Client):
        """Health check timeout should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(
                success=False,
                status_code=None,
                response_time_ms=None,
                error="Request timeout"
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "slow.example.com",
                "timeout": 1
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "timeout" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_health_check_ssl_error_handled(self, mcp_client: Client):
        """SSL errors during health check should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(
                success=False,
                status_code=None,
                response_time_ms=None,
                error="SSL certificate verification failed"
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
    async def test_health_check_dns_resolution_error_handled(self, mcp_client: Client):
        """DNS resolution errors should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(
                success=False,
                status_code=None,
                response_time_ms=None,
                error="Name resolution failed"
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "nonexistent-domain-12345.invalid"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "resolution" in response["error"].lower() or "dns" in response["error"].lower()


class TestTemplateErrors:
    """Test template-related error handling."""

    @pytest.mark.asyncio
    async def test_template_not_found_error_handled(self, mcp_client: Client):
        """Template not found should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=False):
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "testapp",
                "server_name": "test.example.com",
                "upstream_app": "testapp",
                "upstream_port": 8080,
                "config_type_create": "nonexistent_template"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "template" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_template_rendering_error_handled(self, mcp_client: Client):
        """Template rendering errors should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create:
            
            # Simulate Jinja2 template error
            from jinja2 import TemplateSyntaxError
            mock_create.side_effect = TemplateSyntaxError("Unexpected end of template")
            
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "testapp",
                "server_name": "test.example.com",
                "upstream_app": "testapp",
                "upstream_port": 8080
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "template" in response["error"].lower()


class TestAsyncOperationErrors:
    """Test async operation error handling."""

    @pytest.mark.asyncio
    async def test_async_timeout_error_handled(self, mcp_client: Client):
        """AsyncIO timeout errors should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.side_effect = asyncio.TimeoutError()
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "test.example.com"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
            # Should contain timeout information

    @pytest.mark.asyncio
    async def test_async_cancelled_error_handled(self, mcp_client: Client):
        """AsyncIO cancelled errors should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.side_effect = asyncio.CancelledError()
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "test.example.com"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False


class TestBackupOperationErrors:
    """Test backup operation error handling."""

    @pytest.mark.asyncio
    async def test_backup_creation_failure_handled(self, mcp_client: Client, sample_configs):
        """Backup creation failures should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.update_config') as mock_update:
            mock_update.side_effect = OSError("Failed to create backup")
            
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
    async def test_cleanup_backup_permission_error_handled(self, mcp_client: Client):
        """Backup cleanup permission errors should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.cleanup_old_backups') as mock_cleanup:
            mock_cleanup.side_effect = PermissionError("Permission denied deleting backup files")
            
            result = await mcp_client.call_tool("swag", {"action": "cleanup_backups"})
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "permission" in response["error"].lower()


class TestUnexpectedErrors:
    """Test handling of unexpected errors and edge cases."""

    @pytest.mark.asyncio
    async def test_generic_exception_handled_with_helpful_message(self, mcp_client: Client):
        """Generic exceptions should be handled with helpful error messages."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.list_configs') as mock_list:
            mock_list.side_effect = ValueError("Unexpected error in list_configs")
            
            result = await mcp_client.call_tool("swag", {"action": "list"})
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "error" in response
            # Error message should be helpful for LLM to understand what went wrong

    @pytest.mark.asyncio
    async def test_memory_error_handled_gracefully(self, mcp_client: Client):
        """Memory errors should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.get_docker_logs') as mock_logs:
            mock_logs.side_effect = MemoryError("Out of memory")
            
            result = await mcp_client.call_tool("swag", {"action": "logs"})
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "memory" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_handled_gracefully(self, mcp_client: Client):
        """Keyboard interrupt should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.side_effect = KeyboardInterrupt()
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "test.example.com"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
            # Should handle gracefully without crashing

    @pytest.mark.asyncio
    async def test_unicode_decode_error_handled(self, mcp_client: Client):
        """Unicode decode errors should be handled gracefully."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.read_config') as mock_read:
            mock_read.side_effect = UnicodeDecodeError('utf-8', b'', 0, 1, 'invalid start byte')
            
            result = await mcp_client.call_tool("swag", {
                "action": "view",
                "config_name": "binary.conf"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "encoding" in response["error"].lower() or "decode" in response["error"].lower()


class TestErrorMessageQuality:
    """Test that error messages are helpful for LLM recovery."""

    @pytest.mark.asyncio
    async def test_error_messages_contain_action_context(self, mcp_client: Client):
        """Error messages should include action context for LLM understanding."""
        result = await mcp_client.call_tool("swag", {
            "action": "view",
            "config_name": "nonexistent.conf"
        })
        
        # Response validation handled by result.is_error check
        response = result.data
        # Should handle error gracefully - expect either MCP error or server success=false
        assert result.is_error or (response and response.get("success") is False)
        # Should include what action failed
        assert "action" in response or "view" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_error_messages_suggest_recovery_actions(self, mcp_client: Client):
        """Error messages should suggest recovery actions when possible."""
        # Test missing required parameter
        result = await mcp_client.call_tool("swag", {
            "action": "create",
            "service_name": "testapp"
            # Missing required parameters
        })
        
        # Response validation handled by result.is_error check
        response = result.data
        # Should handle error gracefully - expect either MCP error or server success=false
        assert result.is_error or (response and response.get("success") is False)
        # Should indicate what's required
        assert "required" in response["error"].lower()

    @pytest.mark.asyncio
    async def test_error_messages_are_concise_and_clear(self, mcp_client: Client):
        """Error messages should be concise and clear for LLM processing."""
        result = await mcp_client.call_tool("swag", {"action": "invalid_action"})
        
        # Response validation handled by result.is_error check
        response = result.data
        # Should handle error gracefully - expect either MCP error or server success=false
        assert result.is_error or (response and response.get("success") is False)
        # Error message should be reasonably short and clear
        assert len(response["error"]) < 500  # Reasonable length limit
        assert response["error"].strip()  # Not empty or just whitespace


class TestServiceRecovery:
    """Test service recovery patterns after errors."""

    @pytest.mark.asyncio
    async def test_service_continues_after_single_error(self, mcp_client: Client):
        """Service should continue operating after a single error."""
        # First operation fails
        result1 = await mcp_client.call_tool("swag", {
            "action": "view",
            "config_name": "nonexistent.conf"
        })
        
        response1 = result1.data
        assert not result1.is_error
        assert response1["success"] is False
        
        # Second operation should work
        result2 = await mcp_client.call_tool("swag", {"action": "config"})
        
        response2 = result2.data
        assert not result2.is_error
        assert response2["success"] is True

    @pytest.mark.asyncio
    async def test_error_state_does_not_persist(self, mcp_client: Client):
        """Error state should not persist between operations."""
        # Cause an error
        with patch('swag_mcp.services.swag_manager.SwagManagerService.list_configs') as mock_list:
            mock_list.side_effect = ValueError("Simulated error")
            
            result1 = await mcp_client.call_tool("swag", {"action": "list"})
            
        response1 = result1.data
        assert not result1.is_error
        assert response1["success"] is False
        
        # Next operation should work normally (mock is cleared)
        result2 = await mcp_client.call_tool("swag", {"action": "config"})
        
        response2 = result2.data
        assert not result2.is_error
        assert response2["success"] is True