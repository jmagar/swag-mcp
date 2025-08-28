"""Performance validation tests for SWAG MCP tool.

Ensures that tests run in milliseconds as emphasized in "Stop Vibe-Testing Your MCP Server"
and validates that the MCP server responds quickly to tool calls.
"""

import time
import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client
# TextContent no longer needed - using result.data instead


class TestResponseTimePerformance:
    """Test that all tool responses complete within performance thresholds."""

    @pytest.mark.asyncio
    async def test_list_action_completes_under_100ms(self, mcp_client: Client):
        """LIST action should complete in under 100ms."""
        start_time = time.perf_counter()
        
        result = await mcp_client.call_tool("swag", {"action": "list", "config_type": "all"})
        
        end_time = time.perf_counter()
        execution_time_ms = (end_time - start_time) * 1000
        
        # Response validation handled by result.is_error check
        response = result.data
        assert not result.is_error
        assert response["success"] is True
        
        # Critical performance requirement from blog post
        assert execution_time_ms < 100, f"LIST action took {execution_time_ms:.2f}ms, should be <100ms"

    @pytest.mark.asyncio
    async def test_config_action_completes_under_50ms(self, mcp_client: Client):
        """CONFIG action should complete in under 50ms (fastest action)."""
        start_time = time.perf_counter()
        
        result = await mcp_client.call_tool("swag", {"action": "config"})
        
        end_time = time.perf_counter()
        execution_time_ms = (end_time - start_time) * 1000
        
        # Response validation handled by result.is_error check
        response = result.data
        assert not result.is_error
        assert response["success"] is True
        
        # Should be very fast since it just reads config
        assert execution_time_ms < 50, f"CONFIG action took {execution_time_ms:.2f}ms, should be <50ms"

    @pytest.mark.asyncio
    async def test_view_action_completes_under_100ms(self, mcp_client: Client, sample_configs):
        """VIEW action should complete in under 100ms."""
        start_time = time.perf_counter()
        
        result = await mcp_client.call_tool("swag", {
            "action": "view",
            "config_name": "test.conf"
        })
        
        end_time = time.perf_counter()
        execution_time_ms = (end_time - start_time) * 1000
        
        # Response validation handled by result.is_error check
        response = result.data
        assert not result.is_error
        assert response["success"] is True
        
        assert execution_time_ms < 100, f"VIEW action took {execution_time_ms:.2f}ms, should be <100ms"

    @pytest.mark.asyncio
    async def test_create_action_completes_under_200ms(self, mcp_client: Client):
        """CREATE action should complete in under 200ms (more complex operation)."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            
            # Setup mocks for fast execution
            mock_create.return_value = MagicMock(filename="perf-test.conf")
            mock_health.return_value = MagicMock(success=True, status_code=200, response_time_ms=50, error=None)
            
            start_time = time.perf_counter()
            
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "perf-test",
                "server_name": "perf.example.com",
                "upstream_app": "perf-app",
                "upstream_port": 8080
            })
            
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
            
            # More complex operation, allow more time but still fast
        assert execution_time_ms < 200, f"CREATE action took {execution_time_ms:.2f}ms, should be <200ms"

    @pytest.mark.asyncio
    async def test_edit_action_completes_under_150ms(self, mcp_client: Client, sample_configs):
        """EDIT action should complete in under 150ms."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.update_config') as mock_update:
            mock_update.return_value = MagicMock(backup_created="test.conf.backup.123")
            
            start_time = time.perf_counter()
            
            result = await mcp_client.call_tool("swag", {
                "action": "edit",
                "config_name": "test.conf",
                "new_content": "# Performance test content",
                "create_backup": True
            })
            
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
            
        assert execution_time_ms < 150, f"EDIT action took {execution_time_ms:.2f}ms, should be <150ms"

    @pytest.mark.asyncio
    async def test_remove_action_completes_under_150ms(self, mcp_client: Client, sample_configs):
        """REMOVE action should complete in under 150ms."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.remove_config') as mock_remove:
            mock_remove.return_value = MagicMock(backup_created="test.conf.backup.456")
            
            start_time = time.perf_counter()
            
            result = await mcp_client.call_tool("swag", {
                "action": "remove",
                "config_name": "test.conf",
                "create_backup": True
            })
            
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
            
        assert execution_time_ms < 150, f"REMOVE action took {execution_time_ms:.2f}ms, should be <150ms"

    @pytest.mark.asyncio
    async def test_logs_action_completes_under_100ms(self, mcp_client: Client):
        """LOGS action should complete in under 100ms with mocked subprocess."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.get_docker_logs') as mock_logs:
            mock_logs.return_value = "Fast log output\nAnother line"
            
            start_time = time.perf_counter()
            
            result = await mcp_client.call_tool("swag", {"action": "logs", "lines": 10})
            
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
            
        assert execution_time_ms < 100, f"LOGS action took {execution_time_ms:.2f}ms, should be <100ms"

    @pytest.mark.asyncio
    async def test_health_check_action_completes_under_100ms(self, mcp_client: Client):
        """HEALTH_CHECK action should complete in under 100ms with mocked HTTP."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            mock_health.return_value = MagicMock(success=True, status_code=200, response_time_ms=50, error=None)
            
            start_time = time.perf_counter()
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "fast.example.com"
            })
            
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
            
        assert execution_time_ms < 100, f"HEALTH_CHECK action took {execution_time_ms:.2f}ms, should be <100ms"

    @pytest.mark.asyncio
    async def test_cleanup_backups_action_completes_under_100ms(self, mcp_client: Client):
        """CLEANUP_BACKUPS action should complete in under 100ms."""
        with patch('swag_mcp.services.swag_manager.SwagManagerService.cleanup_old_backups') as mock_cleanup:
            mock_cleanup.return_value = 2  # Fast cleanup simulation
            
            start_time = time.perf_counter()
            
            result = await mcp_client.call_tool("swag", {"action": "cleanup_backups"})
            
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
            
        assert execution_time_ms < 100, f"CLEANUP_BACKUPS action took {execution_time_ms:.2f}ms, should be <100ms"


class TestBatchOperationPerformance:
    """Test performance of batch operations and repeated calls."""

    @pytest.mark.asyncio
    async def test_multiple_config_list_calls_scale_linearly(self, mcp_client: Client):
        """Multiple LIST calls should scale linearly, not exponentially."""
        execution_times = []
        
        for i in range(5):
            start_time = time.perf_counter()
            
            result = await mcp_client.call_tool("swag", {"action": "config"})
            
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000
            execution_times.append(execution_time_ms)
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
        
        # Performance should not degrade significantly
        first_call_time = execution_times[0]
        last_call_time = execution_times[-1]
        
        # Last call should not be more than 3x slower than first call
        assert last_call_time < first_call_time * 3, f"Performance degraded: first={first_call_time:.2f}ms, last={last_call_time:.2f}ms"

    @pytest.mark.asyncio
    async def test_concurrent_tool_calls_perform_well(self, mcp_client: Client):
        """Concurrent tool calls should not significantly impact performance."""
        async def single_config_call():
            start_time = time.perf_counter()
            result = await mcp_client.call_tool("swag", {"action": "config"})
            end_time = time.perf_counter()
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
            
            return (end_time - start_time) * 1000
        
        # Run 3 concurrent calls
        start_time = time.perf_counter()
        
        execution_times = await asyncio.gather(
            single_config_call(),
            single_config_call(),
            single_config_call()
        )
        
        total_time = (time.perf_counter() - start_time) * 1000
        
        # All individual calls should be fast
        for exec_time in execution_times:
        assert exec_time < 100, f"Individual call took {exec_time:.2f}ms, should be <100ms"
        
        # Total time should be less than sum of individual times (showing concurrency benefit)
        individual_sum = sum(execution_times)
        assert total_time < individual_sum * 0.8, f"Concurrency not working: total={total_time:.2f}ms, sum={individual_sum:.2f}ms"

    @pytest.mark.asyncio
    async def test_rapid_fire_calls_maintain_performance(self, mcp_client: Client):
        """Rapid consecutive calls should maintain performance."""
        execution_times = []
        
        for i in range(10):
            start_time = time.perf_counter()
            
            result = await mcp_client.call_tool("swag", {"action": "config"})
            
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000
            execution_times.append(execution_time_ms)
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
        
        # All calls should be under threshold
        for i, exec_time in enumerate(execution_times):
        assert exec_time < 100, f"Call {i+1} took {exec_time:.2f}ms, should be <100ms"
        
        # Average should be reasonable
        avg_time = sum(execution_times) / len(execution_times)
        assert avg_time < 50, f"Average execution time {avg_time:.2f}ms too high"


class TestMemoryPerformance:
    """Test memory usage and potential leaks."""

    @pytest.mark.asyncio
    async def test_repeated_calls_do_not_leak_memory(self, mcp_client: Client):
        """Repeated tool calls should not cause memory leaks."""
        import gc
        import sys
        
        # Force garbage collection before test
        gc.collect()
        initial_objects = len(gc.get_objects())
        
        # Make multiple calls
        for i in range(20):
            result = await mcp_client.call_tool("swag", {"action": "config"})
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
        
        # Force garbage collection after test
        gc.collect()
        final_objects = len(gc.get_objects())
        
        # Object count should not grow significantly
        object_growth = final_objects - initial_objects
        # Allow for some growth but not excessive (threshold may need adjustment)
        assert object_growth < 1000, f"Potential memory leak: {object_growth} new objects created"

    @pytest.mark.asyncio
    async def test_large_response_handling_performance(self, mcp_client: Client):
        """Large responses should still be handled performantly."""
        large_config_content = "# Large configuration file\n" + "server { listen 443; }\n" * 100
        
        with patch('swag_mcp.services.swag_manager.SwagManagerService.read_config') as mock_read:
            mock_read.return_value = large_config_content
            
            start_time = time.perf_counter()
            
            result = await mcp_client.call_tool("swag", {
                "action": "view",
                "config_name": "large.conf"
            })
            
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert len(response["content"]) > 5000  # Verify large content
            
            # Should still be reasonably fast even with large content
        assert execution_time_ms < 150, f"Large response took {execution_time_ms:.2f}ms, should be <150ms"


class TestErrorPerformance:
    """Test that error cases also perform well."""

    @pytest.mark.asyncio
    async def test_validation_errors_are_fast(self, mcp_client: Client):
        """Input validation errors should be very fast."""
        start_time = time.perf_counter()
        
        result = await mcp_client.call_tool("swag", {
            "action": "create",
            "service_name": "test"
            # Missing required parameters - should fail validation quickly
        })
        
        end_time = time.perf_counter()
        execution_time_ms = (end_time - start_time) * 1000
        
        # Response validation handled by result.is_error check
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        
        # Validation errors should be extremely fast
        assert execution_time_ms < 50, f"Validation error took {execution_time_ms:.2f}ms, should be <50ms"

    @pytest.mark.asyncio
    async def test_file_not_found_errors_are_fast(self, mcp_client: Client):
        """File not found errors should be fast."""
        start_time = time.perf_counter()
        
        result = await mcp_client.call_tool("swag", {
            "action": "view",
            "config_name": "definitely-not-found.conf"
        })
        
        end_time = time.perf_counter()
        execution_time_ms = (end_time - start_time) * 1000
        
        # Response validation handled by result.is_error check
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        
        # File not found should be handled quickly
        assert execution_time_ms < 100, f"File not found error took {execution_time_ms:.2f}ms, should be <100ms"

    @pytest.mark.asyncio
    async def test_invalid_action_errors_are_fast(self, mcp_client: Client):
        """Invalid action errors should be very fast."""
        start_time = time.perf_counter()
        
        result = await mcp_client.call_tool("swag", {"action": "invalid_action"})
        
        end_time = time.perf_counter()
        execution_time_ms = (end_time - start_time) * 1000
        
        # Response validation handled by result.is_error check
        response = result.data
        assert not result.is_error
        assert response["success"] is False
        
        # Invalid action should be caught very quickly
        assert execution_time_ms < 25, f"Invalid action error took {execution_time_ms:.2f}ms, should be <25ms"


class TestMCPProtocolPerformance:
    """Test MCP protocol-level performance."""

    @pytest.mark.asyncio
    async def test_tool_call_overhead_is_minimal(self, mcp_client: Client):
        """MCP tool call overhead should be minimal."""
        # Test multiple simple calls to measure protocol overhead
        times = []
        
        for _ in range(5):
            start_time = time.perf_counter()
            
            result = await mcp_client.call_tool("swag", {"action": "config"})
            
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000
            times.append(execution_time_ms)
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
        
        # All calls should be consistently fast
        max_time = max(times)
        min_time = min(times)
        avg_time = sum(times) / len(times)
        
        assert max_time < 100, f"Slowest call took {max_time:.2f}ms, should be <100ms"
        assert avg_time < 50, f"Average time {avg_time:.2f}ms too high"
        
        # Variance should be low (consistent performance)
        variance = max_time - min_time
        assert variance < 50, f"High variance in performance: {variance:.2f}ms"

    @pytest.mark.asyncio
    async def test_in_memory_connection_performance_benefit(self, mcp_client: Client):
        """In-memory connection should provide performance benefit over network."""
        # This test validates that we're getting the expected performance
        # from in-memory connections mentioned in the blog post
        
        very_fast_times = []
        
        for _ in range(10):
            start_time = time.perf_counter()
            
            result = await mcp_client.call_tool("swag", {"action": "config"})
            
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000
            very_fast_times.append(execution_time_ms)
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
        
        # All calls should be very fast due to in-memory connection
        for i, exec_time in enumerate(very_fast_times):
        assert exec_time < 50, f"In-memory call {i+1} took {exec_time:.2f}ms, should be <50ms for in-memory"
        
        # Average should be extremely fast
        avg_time = sum(very_fast_times) / len(very_fast_times)
        assert avg_time < 25, f"Average in-memory time {avg_time:.2f}ms should be <25ms"


class TestPerformanceRegression:
    """Test for performance regressions."""

    @pytest.mark.asyncio
    async def test_performance_baseline_maintained(self, mcp_client: Client):
        """Ensure performance baseline is maintained."""
        # This test serves as a regression detector
        # If this test starts failing, performance has regressed
        
        baseline_operations = [
            {"action": "config"},
            {"action": "list", "config_type": "all"},
            {"action": "list", "config_type": "active"},
            {"action": "list", "config_type": "samples"}
        ]
        
        for operation in baseline_operations:
            start_time = time.perf_counter()
            
            result = await mcp_client.call_tool("swag", operation)
            
            end_time = time.perf_counter()
            execution_time_ms = (end_time - start_time) * 1000
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
            
            # All baseline operations should be very fast
            action_name = operation.get("action", "unknown")
        assert execution_time_ms < 75, f"Performance regression in {action_name}: {execution_time_ms:.2f}ms, should be <75ms"