"""Integration tests for end-to-end SWAG MCP workflows.

Tests complete workflows that span multiple operations to ensure
real-world usage patterns work correctly.
"""

import pytest
from fastmcp import Client
# TextContent no longer needed - using result.data instead
from unittest.mock import MagicMock, patch


class TestCreateViewEditRemoveLifecycle:
    """Test the complete lifecycle of configuration management."""

    @pytest.mark.asyncio
    async def test_full_config_lifecycle_success(self, mcp_client: Client):
        """Test complete Create → View → Edit → Remove lifecycle."""
        # Mock all the external dependencies
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.read_config') as mock_read, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.update_config') as mock_update, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.remove_config') as mock_remove:
            
            # Setup mocks
            mock_create.return_value = MagicMock(filename="lifecycle-test.conf")
            mock_health.return_value = MagicMock(success=True, status_code=200, response_time_ms=100, error=None)
            mock_read.return_value = "# Original configuration\nserver { listen 443; }"
            mock_update.return_value = MagicMock(backup_created="lifecycle-test.conf.backup.123456")
            mock_remove.return_value = MagicMock(backup_created="lifecycle-test.conf.backup.789012")
            
            # Step 1: Create configuration
            create_result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "lifecycle-test",
                "server_name": "lifecycle.example.com",
                "upstream_app": "lifecycle-app",
                "upstream_port": 8080,
                "auth_method": "authelia"
            })
            
            # Response validation handled by result.is_error check
            create_response = create_result.data
            assert not create_result.is_error
            assert create_response["success"] is True
            assert create_response["filename"] == "lifecycle-test.conf"
            
            # Step 2: View the created configuration
            view_result = await mcp_client.call_tool("swag", {
                "action": "view",
                "config_name": "lifecycle-test.conf"
            })
            
            # Response validation handled by result.is_error check
            view_response = view_result.data
            assert not view_result.is_error
            assert view_response["success"] is True
            assert view_response["config_name"] == "lifecycle-test.conf"
            assert "Original configuration" in view_response["content"]
            
            # Step 3: Edit the configuration
            new_content = "# Updated configuration\nserver { listen 443; location / { return 200; } }"
            edit_result = await mcp_client.call_tool("swag", {
                "action": "edit",
                "config_name": "lifecycle-test.conf",
                "new_content": new_content,
                "create_backup": True
            })
            
            # Response validation handled by result.is_error check
            edit_response = edit_result.data
            assert not edit_result.is_error
            assert edit_response["success"] is True
            assert edit_response["backup_created"] == "lifecycle-test.conf.backup.123456"
            
            # Step 4: Remove the configuration
            remove_result = await mcp_client.call_tool("swag", {
                "action": "remove",
                "config_name": "lifecycle-test.conf",
                "create_backup": True
            })
            
            # Response validation handled by result.is_error check
            remove_response = remove_result.data
            assert not remove_result.is_error
            assert remove_response["success"] is True
            assert remove_response["backup_created"] == "lifecycle-test.conf.backup.789012"
            
            # Verify all service methods were called with correct parameters
            mock_create.assert_called_once()
            mock_read.assert_called_once_with("lifecycle-test.conf")
            mock_update.assert_called_once()
            mock_remove.assert_called_once()

    @pytest.mark.asyncio
    async def test_lifecycle_with_health_check_failure_and_recovery(self, mcp_client: Client):
        """Test lifecycle where health check initially fails but config is still created."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            
            # Setup mocks - health check fails initially
            mock_create.return_value = MagicMock(filename="failing-health.conf")
            mock_health.return_value = MagicMock(
                success=False, 
                status_code=503, 
                response_time_ms=None, 
                error="Service unavailable"
            )
            
            # Create configuration despite health check failure
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "failing-health",
                "server_name": "failing.example.com",
                "upstream_app": "failing-app",
                "upstream_port": 8080
            })
            
            # Response validation handled by result.is_error check
            response = result.data
            assert not result.is_error
            assert response["success"] is True  # Config creation succeeds
            assert response["filename"] == "failing-health.conf"
            # Health check failure should be reported but not prevent creation
            assert "health_check" in response


class TestMultipleConfigurationWorkflow:
    """Test workflows involving multiple configurations."""

    @pytest.mark.asyncio
    async def test_create_multiple_configs_and_list_workflow(self, mcp_client: Client):
        """Test creating multiple configs and then listing them."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.list_configs') as mock_list:
            
            # Setup mocks
            mock_health.return_value = MagicMock(success=True, status_code=200, response_time_ms=100, error=None)
            mock_list.return_value = MagicMock(
                total_count=3,
                configs=[
                    {"name": "app1.conf", "type": "active"},
                    {"name": "app2.conf", "type": "active"},
                    {"name": "app3.conf", "type": "active"}
                ]
            )
            
            # Create first configuration
            mock_create.return_value = MagicMock(filename="app1.conf")
            result1 = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "app1",
                "server_name": "app1.example.com",
                "upstream_app": "app1",
                "upstream_port": 8001
            })
            
            # Response validation handled by result.is_error check
            response1 = result1.data
            assert not result1.is_error
            assert response1["success"] is True
            
            # Create second configuration
            mock_create.return_value = MagicMock(filename="app2.conf")
            result2 = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "app2",
                "server_name": "app2.example.com",
                "upstream_app": "app2",
                "upstream_port": 8002
            })
            
            # Response validation handled by result.is_error check
            response2 = result2.data
            assert not result2.is_error
            assert response2["success"] is True
            
            # Create third configuration
            mock_create.return_value = MagicMock(filename="app3.conf")
            result3 = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "app3",
                "server_name": "app3.example.com",
                "upstream_app": "app3",
                "upstream_port": 8003
            })
            
            # Response validation handled by result.is_error check
            response3 = result3.data
            assert not result3.is_error
            assert response3["success"] is True
            
            # List all configurations
            list_result = await mcp_client.call_tool("swag", {
                "action": "list",
                "config_type": "all"
            })
            
            # Response validation handled by result.is_error check
            list_response = list_result.data
            assert not list_result.is_error
            assert list_response["success"] is True
            assert list_response["total_count"] == 3
            assert len(list_response["configs"]) == 3
            
            # Verify all creates were called
            assert mock_create.call_count == 3

    @pytest.mark.asyncio
    async def test_batch_configuration_filtering_workflow(self, mcp_client: Client):
        """Test listing and filtering configurations with different types."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.list_configs') as mock_list:
            
            # Mock different list responses for different config types
            def mock_list_side_effect(config_type):
                if config_type == "active":
                    return MagicMock(
                        total_count=2,
                        configs=[
                            {"name": "app1.conf", "type": "active"},
                            {"name": "app2.conf", "type": "active"}
                        ]
                    )
                elif config_type == "samples":
                    return MagicMock(
                        total_count=1,
                        configs=[
                            {"name": "sample.conf", "type": "sample"}
                        ]
                    )
                else:  # "all"
                    return MagicMock(
                        total_count=3,
                        configs=[
                            {"name": "app1.conf", "type": "active"},
                            {"name": "app2.conf", "type": "active"},
                            {"name": "sample.conf", "type": "sample"}
                        ]
                    )
            
            mock_list.side_effect = mock_list_side_effect
            
            # List active configurations
            active_result = await mcp_client.call_tool("swag", {
                "action": "list",
                "config_type": "active"
            })
            
            # Response validation handled by result.is_error check
            active_response = active_result.data
            assert not active_result.is_error
            assert active_response["success"] is True
            assert active_response["total_count"] == 2
            
            # List sample configurations
            samples_result = await mcp_client.call_tool("swag", {
                "action": "list",
                "config_type": "samples"
            })
            
            # Response validation handled by result.is_error check
            samples_response = samples_result.data
            assert not samples_result.is_error
            assert samples_response["success"] is True
            assert samples_response["total_count"] == 1
            
            # List all configurations
            all_result = await mcp_client.call_tool("swag", {
                "action": "list",
                "config_type": "all"
            })
            
            # Response validation handled by result.is_error check
            all_response = all_result.data
            assert not all_result.is_error
            assert all_response["success"] is True
            assert all_response["total_count"] == 3


class TestHealthCheckIntegrationWorkflow:
    """Test health check integration workflows."""

    @pytest.mark.asyncio
    async def test_create_then_standalone_health_check_workflow(self, mcp_client: Client):
        """Test creating config with health check, then running standalone health check."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            
            # Setup mocks
            mock_create.return_value = MagicMock(filename="health-test.conf")
            
            # First health check (during create) returns service unavailable
            mock_health.return_value = MagicMock(
                success=False, 
                status_code=503, 
                response_time_ms=None, 
                error="Service unavailable"
            )
            
            # Create configuration
            create_result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "health-test",
                "server_name": "health.example.com",
                "upstream_app": "health-app",
                "upstream_port": 8080
            })
            
            # Response validation handled by result.is_error check
            create_response = create_result.data
            assert not create_result.is_error
            assert create_response["success"] is True
            assert "health_check" in create_response
            
            # Later, service comes online - standalone health check
            mock_health.return_value = MagicMock(
                success=True,
                status_code=200,
                response_time_ms=250,
                error=None
            )
            
            health_result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "health.example.com",
                "timeout": 30
            })
            
            # Response validation handled by result.is_error check
            health_response = health_result.data
            assert not health_result.is_error
            assert health_response["success"] is True
            assert health_response["status_code"] == 200
            assert health_response["response_time_ms"] == 250
            
            # Verify health check was called twice
            assert mock_health.call_count == 2

    @pytest.mark.asyncio
    async def test_health_check_timeout_adjustment_workflow(self, mcp_client: Client):
        """Test health check with different timeout values."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            
            def mock_health_side_effect(request):
                # Simulate different responses based on timeout
                if request.timeout <= 5:
                    return MagicMock(
                        success=False,
                        status_code=None,
                        response_time_ms=None,
                        error="Request timeout"
                    )
                else:
                    return MagicMock(
                        success=True,
                        status_code=200,
                        response_time_ms=4500,  # Takes 4.5 seconds
                        error=None
                    )
            
            mock_health.side_effect = mock_health_side_effect
            
            # First check with short timeout - should timeout
            timeout_result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "slow.example.com",
                "timeout": 5
            })
            
            # Response validation handled by result.is_error check
            timeout_response = timeout_result.data
            assert not timeout_result.is_error
            assert timeout_response["success"] is False
            assert "timeout" in timeout_response["error"].lower()
            
            # Second check with longer timeout - should succeed
            success_result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "slow.example.com",
                "timeout": 10
            })
            
            # Response validation handled by result.is_error check
            success_response = success_result.data
            assert not success_result.is_error
            assert success_response["success"] is True
            assert success_response["response_time_ms"] == 4500


class TestBackupAndCleanupWorkflow:
    """Test backup creation and cleanup workflows."""

    @pytest.mark.asyncio
    async def test_edit_with_backup_then_cleanup_workflow(self, mcp_client: Client, sample_configs):
        """Test editing with backup creation followed by cleanup."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.update_config') as mock_update, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.cleanup_old_backups') as mock_cleanup:
            
            # Setup mocks
            mock_update.return_value = MagicMock(backup_created="test.conf.backup.20241128_120000")
            mock_cleanup.return_value = 1  # 1 file cleaned
            
            # Edit configuration with backup
            edit_result = await mcp_client.call_tool("swag", {
                "action": "edit",
                "config_name": "test.conf",
                "new_content": "# Updated content with backup",
                "create_backup": True
            })
            
            # Response validation handled by result.is_error check
            edit_response = edit_result.data
            assert not edit_result.is_error
            assert edit_response["success"] is True
            assert edit_response["backup_created"] == "test.conf.backup.20241128_120000"
            
            # Clean up old backups
            cleanup_result = await mcp_client.call_tool("swag", {
                "action": "cleanup_backups",
                "retention_days": 7
            })
            
            # Response validation handled by result.is_error check
            cleanup_response = cleanup_result.data
            assert not cleanup_result.is_error
            assert cleanup_response["success"] is True
            assert cleanup_response["cleaned_count"] == 1
            assert cleanup_response["retention_days"] == 7
            
            # Verify both operations were called
            mock_update.assert_called_once()
            mock_cleanup.assert_called_once_with(7)

    @pytest.mark.asyncio
    async def test_multiple_edits_with_backup_accumulation(self, mcp_client: Client, sample_configs):
        """Test multiple edits creating multiple backups."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.update_config') as mock_update, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.cleanup_old_backups') as mock_cleanup:
            
            # Setup mocks for multiple edits
            backup_files = [
                "test.conf.backup.20241128_120000",
                "test.conf.backup.20241128_130000", 
                "test.conf.backup.20241128_140000"
            ]
            
            mock_update.side_effect = [
                MagicMock(backup_created=backup) for backup in backup_files
            ]
            
            # Perform multiple edits
            for i, content in enumerate([
                "# First update",
                "# Second update", 
                "# Third update"
            ]):
                result = await mcp_client.call_tool("swag", {
                    "action": "edit",
                    "config_name": "test.conf",
                    "new_content": content,
                    "create_backup": True
                })
                
                # Response validation handled by result.is_error check
                response = result.data
                assert not result.is_error
                assert response["success"] is True
                assert response["backup_created"] == backup_files[i]
            
            # Clean up backups - should clean 2 old ones, keep 1 recent
            mock_cleanup.return_value = 2
            cleanup_result = await mcp_client.call_tool("swag", {
                "action": "cleanup_backups",
                "retention_days": 1
            })
            
            # Response validation handled by result.is_error check
            cleanup_response = cleanup_result.data
            assert not cleanup_result.is_error
            assert cleanup_response["success"] is True
            assert cleanup_response["cleaned_count"] == 2
            
            # Verify all operations were called
            assert mock_update.call_count == 3
            mock_cleanup.assert_called_once_with(1)


class TestDockerLogsWorkflow:
    """Test Docker logs integration workflows."""

    @pytest.mark.asyncio
    async def test_logs_with_different_line_counts_workflow(self, mcp_client: Client):
        """Test retrieving logs with different line count requirements."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.get_docker_logs') as mock_logs:
            
            # Mock different log outputs based on line count
            def mock_logs_side_effect(request):
                lines = request.lines
                return "Sample log line\n" * min(lines, 50)  # Simulate max 50 lines available
            
            mock_logs.side_effect = mock_logs_side_effect
            
            # Request small number of lines
            small_result = await mcp_client.call_tool("swag", {
                "action": "logs",
                "lines": 10
            })
            
            # Response validation handled by result.is_error check
            small_response = small_result.data
            assert not small_result.is_error
            assert small_response["success"] is True
            assert small_response["lines_requested"] == 10
            assert small_response["logs"].count("Sample log line") == 10
            
            # Request large number of lines
            large_result = await mcp_client.call_tool("swag", {
                "action": "logs", 
                "lines": 100
            })
            
            # Response validation handled by result.is_error check
            large_response = large_result.data
            assert not large_result.is_error
            assert large_response["success"] is True
            assert large_response["lines_requested"] == 100
            assert large_response["logs"].count("Sample log line") == 50  # Limited by available logs
            
            # Verify logs were called with correct parameters
            assert mock_logs.call_count == 2


class TestConfigurationDefaults:
    """Test configuration defaults integration."""

    @pytest.mark.asyncio
    async def test_config_defaults_used_in_create_workflow(self, mcp_client: Client):
        """Test that config defaults are properly integrated with create operations."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.health_check'):
            
            # Setup mock
            mock_create.return_value = MagicMock(filename="defaults-test.conf")
            
            # Get current defaults first
            config_result = await mcp_client.call_tool("swag", {"action": "config"})
            
            # Response validation handled by result.is_error check
            config_response = config_result.data
            assert not config_result.is_error
            assert config_response["success"] is True
            assert "defaults" in config_response
            
            # Create configuration without specifying optional parameters (should use defaults)
            create_result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "defaults-test",
                "server_name": "defaults.example.com",
                "upstream_app": "defaults-app",
                "upstream_port": 8080
                # Not specifying auth_method, enable_quic, config_type_create
            })
            
            # Response validation handled by result.is_error check
            create_response = create_result.data
            assert not create_result.is_error
            assert create_response["success"] is True
            assert create_response["filename"] == "defaults-test.conf"
            
            # Verify create was called (defaults handling is tested in the service layer)
            mock_create.assert_called_once()


class TestErrorRecoveryWorkflows:
    """Test error recovery in multi-step workflows."""

    @pytest.mark.asyncio
    async def test_partial_failure_recovery_workflow(self, mcp_client: Client):
        """Test recovery after partial failures in multi-step workflows."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.read_config') as mock_read:
            
            # Setup mocks - create succeeds but health check fails
            mock_create.return_value = MagicMock(filename="recovery-test.conf")
            mock_health.return_value = MagicMock(
                success=False,
                status_code=503,
                response_time_ms=None,
                error="Service unavailable"
            )
            mock_read.return_value = "# Configuration created despite health check failure"
            
            # Step 1: Create config (succeeds) with health check (fails)
            create_result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "recovery-test",
                "server_name": "recovery.example.com",
                "upstream_app": "recovery-app",
                "upstream_port": 8080
            })
            
            # Response validation handled by result.is_error check
            create_response = create_result.data
            assert not create_result.is_error
            assert create_response["success"] is True  # Create still succeeds
            assert "health_check" in create_response  # But health check failure is reported
            
            # Step 2: Verify config was created by viewing it
            view_result = await mcp_client.call_tool("swag", {
                "action": "view",
                "config_name": "recovery-test.conf"
            })
            
            # Response validation handled by result.is_error check
            view_response = view_result.data
            assert not view_result.is_error
            assert view_response["success"] is True
            assert "Configuration created despite" in view_response["content"]
            
            # Step 3: Later, try health check again (should work independently)
            mock_health.return_value = MagicMock(
                success=True,
                status_code=200,
                response_time_ms=200,
                error=None
            )
            
            health_result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "recovery.example.com"
            })
            
            # Response validation handled by result.is_error check
            health_response = health_result.data
            assert not health_result.is_error
            assert health_response["success"] is True
            assert health_response["status_code"] == 200
            
            # Verify all operations worked as expected
            mock_create.assert_called_once()
            mock_read.assert_called_once()
            assert mock_health.call_count == 2  # Once during create, once standalone