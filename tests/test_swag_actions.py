"""Core SWAG MCP tool action tests using in-memory FastMCP Client.

Following the principles from "Stop Vibe-Testing Your MCP Server":
- Deterministic testing using FastMCP Client
- In-memory connections for zero network overhead
- Testing actual MCP protocol interactions, not just functions
- Clear test names that indicate what breaks when they fail
"""

import pytest
from fastmcp import Client
from mcp.types import TextContent
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path


class TestSwagListAction:
    """Test the LIST action of the unified SWAG tool."""

    @pytest.mark.asyncio
    async def test_list_all_configurations_success(self, mcp_client: Client):
        """LIST action should return all configurations with correct structure."""
        result = await mcp_client.call_tool("swag", {"action": "list", "config_type": "all"})
        
        response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert "total_count" in response
        assert "configs" in response
        assert response["config_type"] == "all"

    @pytest.mark.asyncio
    async def test_list_active_configurations_only(self, mcp_client: Client):
        """LIST action should filter to active configurations only."""
        result = await mcp_client.call_tool("swag", {"action": "list", "config_type": "active"})
        
        response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert response["config_type"] == "active"

    @pytest.mark.asyncio
    async def test_list_sample_configurations_only(self, mcp_client: Client):
        """LIST action should filter to sample configurations only."""
        result = await mcp_client.call_tool("swag", {"action": "list", "config_type": "samples"})
        
        response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert response["config_type"] == "samples"

    @pytest.mark.asyncio
    async def test_list_invalid_config_type_fails(self, mcp_client: Client):
        """LIST action should reject invalid config_type parameter."""
        result = await mcp_client.call_tool("swag", {"action": "list", "config_type": "invalid"})
        
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "config_type must be" in response["error"]


class TestSwagCreateAction:
    """Test the CREATE action of the unified SWAG tool."""

    @pytest.mark.asyncio
    async def test_create_subdomain_configuration_success(self, mcp_client: Client):
        """CREATE action should successfully create subdomain configuration."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            
            # Mock successful config creation
            mock_create.return_value = MagicMock(filename="testapp.conf")
            mock_health.return_value = MagicMock(
                success=True, 
                status_code=200, 
                response_time_ms=150,
                error=None
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "testapp",
                "server_name": "test.example.com",
                "upstream_app": "testapp",
                "upstream_port": 8080,
                "config_type_create": "subdomain"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert response["filename"] == "testapp.conf"
        assert "health_check" in response

    @pytest.mark.asyncio
    async def test_create_missing_service_name_fails(self, mcp_client: Client):
        """CREATE action should fail when service_name is missing."""
        result = await mcp_client.call_tool("swag", {
            "action": "create",
            "server_name": "test.example.com",
            "upstream_app": "testapp",
            "upstream_port": 8080
        })
        
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "service_name is required" in response["error"]

    @pytest.mark.asyncio
    async def test_create_missing_server_name_fails(self, mcp_client: Client):
        """CREATE action should fail when server_name is missing."""
        result = await mcp_client.call_tool("swag", {
            "action": "create",
            "service_name": "testapp",
            "upstream_app": "testapp",
            "upstream_port": 8080
        })
        
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "server_name is required" in response["error"]

    @pytest.mark.asyncio
    async def test_create_missing_upstream_app_fails(self, mcp_client: Client):
        """CREATE action should fail when upstream_app is missing."""
        result = await mcp_client.call_tool("swag", {
            "action": "create",
            "service_name": "testapp",
            "server_name": "test.example.com",
            "upstream_port": 8080
        })
        
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "upstream_app is required" in response["error"]

    @pytest.mark.asyncio
    async def test_create_invalid_upstream_port_fails(self, mcp_client: Client):
        """CREATE action should fail when upstream_port is 0 or invalid."""
        result = await mcp_client.call_tool("swag", {
            "action": "create",
            "service_name": "testapp",
            "server_name": "test.example.com",
            "upstream_app": "testapp",
            "upstream_port": 0
        })
        
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "upstream_port is required" in response["error"]

    @pytest.mark.asyncio
    async def test_create_template_not_found_fails(self, mcp_client: Client):
        """CREATE action should fail when template doesn't exist."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=False):
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "testapp",
                "server_name": "test.example.com",
                "upstream_app": "testapp",
                "upstream_port": 8080,
                "config_type_create": "invalid_template"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "Template for" in response["error"]


class TestSwagViewAction:
    """Test the VIEW action of the unified SWAG tool."""

    @pytest.mark.asyncio
    async def test_view_existing_configuration_success(self, mcp_client: Client, sample_configs):
        """VIEW action should successfully read existing configuration file."""
        result = await mcp_client.call_tool("swag", {
            "action": "view",
            "config_name": "test.conf"
        })
        
        response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert response["config_name"] == "test.conf"
        assert "content" in response
        assert "character_count" in response

    @pytest.mark.asyncio
    async def test_view_missing_config_name_fails(self, mcp_client: Client):
        """VIEW action should fail when config_name is missing."""
        result = await mcp_client.call_tool("swag", {"action": "view"})
        
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "config_name is required" in response["error"]

    @pytest.mark.asyncio
    async def test_view_nonexistent_configuration_fails(self, mcp_client: Client):
        """VIEW action should fail when configuration file doesn't exist."""
        result = await mcp_client.call_tool("swag", {
            "action": "view",
            "config_name": "nonexistent.conf"
        })
        
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        # Should contain file not found error message


class TestSwagEditAction:
    """Test the EDIT action of the unified SWAG tool."""

    @pytest.mark.asyncio
    async def test_edit_existing_configuration_success(self, mcp_client: Client, sample_configs):
        """EDIT action should successfully update existing configuration."""
        new_content = "# Updated configuration\nserver { listen 443; }"
        
        result = await mcp_client.call_tool("swag", {
            "action": "edit",
            "config_name": "test.conf",
            "new_content": new_content,
            "create_backup": True
        })
        
        response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert response["config_name"] == "test.conf"
        assert "backup_created" in response

    @pytest.mark.asyncio
    async def test_edit_missing_config_name_fails(self, mcp_client: Client):
        """EDIT action should fail when config_name is missing."""
        result = await mcp_client.call_tool("swag", {
            "action": "edit",
            "new_content": "some content"
        })
        
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "config_name is required" in response["error"]

    @pytest.mark.asyncio
    async def test_edit_missing_new_content_fails(self, mcp_client: Client):
        """EDIT action should fail when new_content is missing."""
        result = await mcp_client.call_tool("swag", {
            "action": "edit",
            "config_name": "test.conf"
        })
        
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "new_content is required" in response["error"]


class TestSwagRemoveAction:
    """Test the REMOVE action of the unified SWAG tool."""

    @pytest.mark.asyncio
    async def test_remove_existing_configuration_success(self, mcp_client: Client, sample_configs):
        """REMOVE action should successfully delete existing configuration."""
        result = await mcp_client.call_tool("swag", {
            "action": "remove",
            "config_name": "test.conf",
            "create_backup": True
        })
        
        response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert response["config_name"] == "test.conf"
        assert "backup_created" in response

    @pytest.mark.asyncio
    async def test_remove_missing_config_name_fails(self, mcp_client: Client):
        """REMOVE action should fail when config_name is missing."""
        result = await mcp_client.call_tool("swag", {"action": "remove"})
        
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "config_name is required" in response["error"]


class TestSwagConfigAction:
    """Test the CONFIG action of the unified SWAG tool."""

    @pytest.mark.asyncio
    async def test_config_returns_current_defaults(self, mcp_client: Client):
        """CONFIG action should return current default configuration values."""
        result = await mcp_client.call_tool("swag", {"action": "config"})
        
        response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert "defaults" in response
        assert "default_auth_method" in response["defaults"]
        assert "default_quic_enabled" in response["defaults"]
        assert "default_config_type" in response["defaults"]


class TestSwagLogsAction:
    """Test the LOGS action of the unified SWAG tool."""

    @pytest.mark.asyncio
    async def test_logs_retrieves_docker_logs(self, mcp_client: Client):
        """LOGS action should retrieve Docker container logs."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.get_docker_logs') as mock_logs:
            mock_logs.return_value = "Sample log output\nAnother log line"
            
            result = await mcp_client.call_tool("swag", {
                "action": "logs",
                "lines": 50
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert response["lines_requested"] == 50
        assert "logs" in response
        assert "character_count" in response

    @pytest.mark.asyncio
    async def test_logs_default_line_count(self, mcp_client: Client):
        """LOGS action should use default line count when not specified."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.get_docker_logs') as mock_logs:
            mock_logs.return_value = "Sample log output"
            
            result = await mcp_client.call_tool("swag", {"action": "logs"})
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert response["lines_requested"] == 100  # Default value


class TestSwagCleanupBackupsAction:
    """Test the CLEANUP_BACKUPS action of the unified SWAG tool."""

    @pytest.mark.asyncio
    async def test_cleanup_backups_removes_old_files(self, mcp_client: Client):
        """CLEANUP_BACKUPS action should remove old backup files."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.cleanup_old_backups') as mock_cleanup:
            mock_cleanup.return_value = 3  # 3 files cleaned
            
            result = await mcp_client.call_tool("swag", {
                "action": "cleanup_backups",
                "retention_days": 7
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert response["cleaned_count"] == 3
        assert response["retention_days"] == 7

    @pytest.mark.asyncio
    async def test_cleanup_backups_no_files_to_clean(self, mcp_client: Client):
        """CLEANUP_BACKUPS action should handle case with no files to clean."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.cleanup_old_backups') as mock_cleanup:
            mock_cleanup.return_value = 0  # No files cleaned
            
            result = await mcp_client.call_tool("swag", {"action": "cleanup_backups"})
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert response["cleaned_count"] == 0
        assert "No old backup files" in response["message"]


class TestSwagHealthCheckAction:
    """Test the HEALTH_CHECK action of the unified SWAG tool."""

    @pytest.mark.asyncio
    async def test_health_check_successful_response(self, mcp_client: Client):
        """HEALTH_CHECK action should handle successful HTTP response."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(
                success=True,
                status_code=200,
                response_time_ms=250,
                error=None
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "test.example.com",
                "timeout": 30,
                "follow_redirects": True
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert response["domain"] == "test.example.com"
        assert response["status_code"] == 200
        assert response["response_time_ms"] == 250
        assert response["error"] is None

    @pytest.mark.asyncio
    async def test_health_check_failed_response(self, mcp_client: Client):
        """HEALTH_CHECK action should handle failed HTTP response."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(
                success=False,
                status_code=500,
                response_time_ms=None,
                error="Connection refused"
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "test.example.com"
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert response["domain"] == "test.example.com"
        assert response["status_code"] == 500
        assert response["error"] == "Connection refused"

    @pytest.mark.asyncio
    async def test_health_check_missing_domain_fails(self, mcp_client: Client):
        """HEALTH_CHECK action should fail when domain is missing."""
        result = await mcp_client.call_tool("swag", {"action": "health_check"})
        
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "domain is required" in response["error"]


class TestSwagInvalidActions:
    """Test handling of invalid actions and general error cases."""

    @pytest.mark.asyncio
    async def test_invalid_action_fails_gracefully(self, mcp_client: Client):
        """SWAG tool should handle invalid action parameter gracefully."""
        result = await mcp_client.call_tool("swag", {"action": "invalid_action"})
        
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        assert "Unknown action" in response["error"]
        assert "valid_actions" in response

    @pytest.mark.asyncio 
    async def test_missing_action_parameter_fails(self, mcp_client: Client):
        """SWAG tool should fail when action parameter is missing."""
        # This should be handled by the MCP framework parameter validation
        # The test verifies the tool requires the action parameter
        with pytest.raises(Exception):  # MCP framework should raise validation error
            await mcp_client.call_tool("swag", {})