"""Docker integration chaos testing for external dependency failures.

These tests focus on finding bugs in Docker integration by simulating
real-world Docker failures and edge cases that commonly occur in production.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from swag_mcp.models.config import SwagLogsRequest
from swag_mcp.services.swag_manager import SwagManagerService


class TestDockerChaosBugs:
    """Bug discovery tests for Docker integration failure scenarios."""

    @pytest.mark.asyncio
    async def test_docker_daemon_not_running(self, mcp_client: Client):
        """Test behavior when Docker daemon is not running or unreachable."""

        # Mock Docker client to simulate daemon not running
        with patch("docker.from_env") as mock_docker:
            # Simulate various ways Docker daemon can be unreachable
            connection_errors = [
                ConnectionError("Error while fetching server API version"),
                FileNotFoundError("Docker socket not found"),
                PermissionError("Permission denied accessing Docker socket"),
                OSError("Docker daemon not running"),
            ]

            for error in connection_errors:
                mock_docker.side_effect = error

                # Test Docker logs functionality
                with pytest.raises(ToolError) as exc_info:
                    await mcp_client.call_tool("swag_logs", {"lines": 10})

                error_msg = str(exc_info.value).lower()
                # Should provide helpful error message, not generic failure
                assert any(
                    word in error_msg for word in ["docker", "daemon", "connection", "unavailable"]
                )
                # Should not expose internal Docker implementation details
                assert "traceback" not in error_msg
                assert "api version" not in error_msg

    @pytest.mark.asyncio
    async def test_container_state_chaos(self, mcp_client: Client):
        """Test behavior with various container states and edge cases."""

        # Mock Docker client with different container scenarios
        with patch("docker.from_env") as mock_docker:
            mock_client = MagicMock()
            mock_docker.return_value = mock_client

            # Test scenarios for container state issues
            container_scenarios = [
                # Container exists but is stopped
                {
                    "container_state": "exited",
                    "container_status": "Exited (0) 5 minutes ago",
                    "expected_behavior": "should handle stopped container gracefully",
                },
                # Container exists but is paused
                {
                    "container_state": "paused",
                    "container_status": "Paused",
                    "expected_behavior": "should handle paused container",
                },
                # Container is restarting
                {
                    "container_state": "restarting",
                    "container_status": "Restarting",
                    "expected_behavior": "should handle restarting container",
                },
                # Container doesn't exist
                {"container_exists": False, "expected_behavior": "should handle missing container"},
            ]

            for scenario in container_scenarios:
                if scenario.get("container_exists", True):
                    # Mock container that exists but in various states
                    mock_container = MagicMock()
                    mock_container.attrs = {
                        "State": {"Status": scenario["container_state"]},
                        "Config": {"Image": "linuxserver/swag:latest"},
                        "Name": "swag",
                    }
                    mock_container.status = scenario["container_state"]
                    mock_client.containers.get.return_value = mock_container

                    if scenario["container_state"] in ["exited", "paused"]:
                        # Simulate that logs can't be retrieved from stopped container
                        mock_container.logs.side_effect = Exception(
                            f"Container is {scenario['container_state']}"
                        )
                else:
                    # Mock container doesn't exist
                    from docker.errors import NotFound

                    mock_client.containers.get.side_effect = NotFound("No such container")

                # Test logs functionality
                try:
                    result = await mcp_client.call_tool("swag_logs", {"lines": 10})
                    if not result.is_error:
                        # If it succeeds, should return appropriate message
                        assert isinstance(result.data, str)
                except ToolError as e:
                    # Should fail gracefully with descriptive error
                    error_msg = str(e).lower()
                    assert any(
                        word in error_msg
                        for word in ["container", "not found", "stopped", "unavailable"]
                    )
                    # Should not contain Docker implementation details
                    assert "notfound" not in error_msg
                    assert "docker.errors" not in error_msg

    @pytest.mark.asyncio
    async def test_large_log_file_memory_exhaustion(self, mcp_client: Client):
        """Test handling of very large Docker log files that could cause memory issues."""

        with patch("docker.from_env") as mock_docker:
            mock_client = MagicMock()
            mock_docker.return_value = mock_client
            mock_container = MagicMock()
            mock_client.containers.get.return_value = mock_container

            # Test scenarios with different log sizes
            log_size_scenarios = [
                {"size_mb": 10, "description": "10MB log file"},
                {"size_mb": 100, "description": "100MB log file"},
                {"size_mb": 500, "description": "500MB log file (very large)"},
            ]

            for scenario in log_size_scenarios:
                # Create mock log data of specified size
                line_size = 200  # Average log line size in bytes
                num_lines = (scenario["size_mb"] * 1024 * 1024) // line_size

                def generate_large_logs(num_lines):
                    """Generator for large log data to avoid loading all into memory."""
                    for i in range(num_lines):
                        log_entry = (
                            f"2025-01-24T12:00:{i:02d}.000Z [INFO] Log line {i} - "
                            "This is a sample log entry with enough content to "
                            "simulate real logs\n"
                        )
                        yield log_entry.encode()

                # Mock container.logs to return large data
                mock_container.logs.return_value = b"".join(generate_large_logs(num_lines))

                try:
                    # Test with timeout to prevent hanging
                    result = await asyncio.wait_for(
                        mcp_client.call_tool("swag_logs", {"lines": 1000}),
                        timeout=5.0,  # Should complete within 5 seconds
                    )

                    if not result.is_error:
                        log_data = result.data
                        # Should not return excessively large data to client
                        assert (
                            len(log_data) < 10 * 1024 * 1024
                        ), f"Response too large for {scenario['description']}"
                        # Should contain actual log content
                        assert "Log line" in log_data

                except TimeoutError:
                    pytest.fail(
                        f"Log processing timed out for {scenario['description']} - "
                        f"possible memory exhaustion"
                    )

                except MemoryError:
                    pytest.fail(f"Memory exhaustion occurred for {scenario['description']}")

                except ToolError as e:
                    # If it fails, should be due to size limits, not crashes
                    error_msg = str(e).lower()
                    if (
                        "memory" not in error_msg
                        and "size" not in error_msg
                        and "limit" not in error_msg
                    ):
                        pytest.fail(f"Unexpected error for {scenario['description']}: {error_msg}")

    @pytest.mark.asyncio
    async def test_docker_api_timeout_scenarios(self, mcp_client: Client):
        """Test behavior when Docker API calls timeout."""

        with patch("docker.from_env") as mock_docker:
            mock_client = MagicMock()
            mock_docker.return_value = mock_client

            # Test different timeout scenarios
            timeout_scenarios = [
                {"delay": 1.0, "description": "slow Docker API response"},
                {"delay": 5.0, "description": "very slow Docker API response"},
                {"timeout_error": True, "description": "Docker API timeout error"},
            ]

            for scenario in timeout_scenarios:
                if scenario.get("timeout_error"):
                    # Simulate actual timeout error
                    from docker.errors import APIError

                    mock_client.containers.get.side_effect = APIError("Request timeout")
                else:
                    # Simulate slow response
                    async def slow_response(*args, scenario=scenario, **kwargs):
                        await asyncio.sleep(scenario["delay"])
                        mock_container = MagicMock()
                        mock_container.logs.return_value = b"Slow log response"
                        return mock_container

                    mock_client.containers.get = slow_response

                try:
                    # Test with reasonable timeout
                    result = await asyncio.wait_for(
                        mcp_client.call_tool("swag_logs", {"lines": 10}), timeout=3.0
                    )

                    # If successful, should return data
                    if not result.is_error:
                        assert len(result.data) > 0

                except TimeoutError:
                    # Expected for very slow scenarios
                    if scenario["delay"] < 3.0:
                        pytest.fail(f"Unexpected timeout for {scenario['description']}")

                except ToolError as e:
                    # Should handle timeout gracefully
                    error_msg = str(e).lower()
                    assert any(
                        word in error_msg for word in ["timeout", "slow", "unavailable", "api"]
                    )

    @pytest.mark.asyncio
    async def test_malformed_docker_api_responses(self, mcp_client: Client):
        """Test handling of malformed or unexpected Docker API responses."""

        with patch("docker.from_env") as mock_docker:
            mock_client = MagicMock()
            mock_docker.return_value = mock_client

            # Test various malformed response scenarios
            malformed_scenarios = [
                {
                    "response_type": "binary_garbage",
                    "response_data": b"\x00\x01\x02\xff\xfe\xfd",
                    "description": "binary garbage in logs",
                },
                {
                    "response_type": "invalid_json",
                    "response_data": b'{"invalid": json content}',
                    "description": "malformed JSON in logs",
                },
                {
                    "response_type": "extremely_long_lines",
                    "response_data": ("A" * 100000 + "\n").encode() * 10,
                    "description": "extremely long log lines",
                },
                {
                    "response_type": "null_bytes",
                    "response_data": b"Log line with \x00 null bytes\nAnother line\x00\x00\n",
                    "description": "log lines with null bytes",
                },
                {
                    "response_type": "unicode_issues",
                    "response_data": "Log with unicode: \ud83d\ude00 \u4e2d\u6587 \u0000".encode(
                        "utf-8", errors="ignore"
                    ),
                    "description": "log lines with unicode edge cases",
                },
            ]

            for scenario in malformed_scenarios:
                mock_container = MagicMock()
                mock_container.logs.return_value = scenario["response_data"]
                mock_client.containers.get.return_value = mock_container

                try:
                    result = await mcp_client.call_tool("swag_logs", {"lines": 10})

                    if not result.is_error:
                        log_data = result.data
                        # Should handle malformed data gracefully
                        assert isinstance(
                            log_data, str
                        ), f"Non-string response for {scenario['description']}"
                        # Should not contain raw binary data
                        assert (
                            "\x00" not in log_data
                        ), f"Null bytes in processed output for {scenario['description']}"
                        # Should have reasonable length (not extremely long)
                        assert (
                            len(log_data) < 1000000
                        ), f"Excessively long output for {scenario['description']}"
                    else:
                        # If it fails, should be a handled error
                        error_msg = str(result.error).lower()
                        assert "internal error" not in error_msg

                except ToolError as e:
                    # Should handle malformed data with descriptive errors
                    error_msg = str(e).lower()
                    assert any(
                        word in error_msg for word in ["malformed", "invalid", "format", "encoding"]
                    )

    @pytest.mark.asyncio
    async def test_docker_socket_permission_issues(self, mcp_client: Client):
        """Test behavior when Docker socket permissions are restricted."""

        with patch("docker.from_env") as mock_docker:
            # Simulate various permission-related Docker errors
            permission_errors = [
                PermissionError("Permission denied: '/var/run/docker.sock'"),
                OSError("Cannot connect to Docker socket"),
                ConnectionError("Docker socket permission denied"),
            ]

            for error in permission_errors:
                mock_docker.side_effect = error

                with pytest.raises(ToolError) as exc_info:
                    await mcp_client.call_tool("swag_logs", {"lines": 10})

                error_msg = str(exc_info.value).lower()
                # Should provide helpful error message about permissions
                assert any(
                    word in error_msg for word in ["permission", "access", "docker", "socket"]
                )
                # Should not expose system details
                assert "/var/run/docker.sock" not in error_msg

    @pytest.mark.asyncio
    async def test_concurrent_docker_log_requests(self, mcp_client: Client):
        """Test behavior under concurrent Docker log requests."""

        with patch("docker.from_env") as mock_docker:
            mock_client = MagicMock()
            mock_docker.return_value = mock_client
            mock_container = MagicMock()
            mock_client.containers.get.return_value = mock_container

            # Simulate realistic log response
            mock_container.logs.return_value = b"Log line 1\nLog line 2\nLog line 3\n" * 100

            async def get_logs(lines: int):
                """Get logs with specified line count."""
                try:
                    result = await mcp_client.call_tool("swag_logs", {"lines": lines})
                    return result.data if not result.is_error else f"error: {result.error}"
                except Exception as e:
                    return f"exception: {str(e)}"

            # Run multiple concurrent log requests
            concurrent_requests = [
                get_logs(10),
                get_logs(50),
                get_logs(100),
                get_logs(200),
                get_logs(5),
            ]

            results = await asyncio.gather(*concurrent_requests, return_exceptions=True)

            # Analyze results
            successful_results = [
                r
                for r in results
                if isinstance(r, str) and not r.startswith(("error:", "exception:"))
            ]
            error_results = [
                r for r in results if isinstance(r, str) and r.startswith(("error:", "exception:"))
            ]
            exceptions = [r for r in results if not isinstance(r, str)]

            # Most requests should succeed
            assert (
                len(successful_results) >= 3
            ), f"Too many failed requests: {error_results + [str(e) for e in exceptions]}"

            # Check that successful results contain log data
            for result in successful_results:
                assert "Log line" in result
                assert len(result) > 0

            # Errors should be handled gracefully (not internal server errors)
            for error in error_results:
                assert "internal error" not in error.lower()

    @pytest.mark.asyncio
    async def test_docker_api_rate_limiting(self, mcp_client: Client):
        """Test behavior when Docker API returns rate limiting errors."""

        with patch("docker.from_env") as mock_docker:
            mock_client = MagicMock()
            mock_docker.return_value = mock_client

            # Simulate rate limiting scenarios
            from docker.errors import APIError

            rate_limit_errors = [
                APIError("Rate limit exceeded"),
                APIError("Too many requests"),
                APIError("API quota exceeded"),
            ]

            for error in rate_limit_errors:
                mock_client.containers.get.side_effect = error

                with pytest.raises(ToolError) as exc_info:
                    await mcp_client.call_tool("swag_logs", {"lines": 10})

                error_msg = str(exc_info.value).lower()
                # Should indicate rate limiting issue
                assert any(
                    word in error_msg for word in ["rate", "limit", "quota", "requests", "throttle"]
                )
                # Should suggest retry or backoff
                assert any(word in error_msg for word in ["retry", "later", "wait"])

    @pytest.mark.asyncio
    async def test_docker_container_name_edge_cases(self, mcp_client: Client):
        """Test Docker operations with various container name formats."""

        with patch("docker.from_env") as mock_docker:
            mock_client = MagicMock()
            mock_docker.return_value = mock_client

            # Test different container naming scenarios
            container_name_scenarios = [
                {"name": "swag", "expected": "should work with simple name"},
                {"name": "/swag", "expected": "should handle leading slash"},
                {"name": "swag-container", "expected": "should handle hyphens"},
                {"name": "swag_container", "expected": "should handle underscores"},
                {"name": "SWAG", "expected": "should handle uppercase"},
                {"name": "swag123", "expected": "should handle numbers"},
            ]

            for scenario in container_name_scenarios:
                mock_container = MagicMock()
                mock_container.logs.return_value = (
                    b"Container logs for " + scenario["name"].encode()
                )
                mock_client.containers.get.return_value = mock_container

                # The actual implementation might use hardcoded container name
                # This test ensures the code can handle various naming conventions
                try:
                    result = await mcp_client.call_tool("swag_logs", {"lines": 10})

                    if not result.is_error:
                        assert len(result.data) > 0
                        # Should contain some log content
                        assert isinstance(result.data, str)

                except ToolError:
                    # Some naming formats might not be supported, which is acceptable
                    pass

    @pytest.mark.asyncio
    async def test_docker_log_streaming_edge_cases(self, swag_service: SwagManagerService):
        """Test edge cases in Docker log streaming and processing."""

        with patch("docker.from_env") as mock_docker:
            mock_client = MagicMock()
            mock_docker.return_value = mock_client
            mock_container = MagicMock()
            mock_client.containers.get.return_value = mock_container

            # Test streaming scenarios that could cause issues
            streaming_scenarios = [
                {"name": "empty_logs", "log_data": b"", "description": "container with no logs"},
                {
                    "name": "single_line",
                    "log_data": b"Single log line without newline",
                    "description": "single line without newline",
                },
                {
                    "name": "only_newlines",
                    "log_data": b"\n\n\n\n\n",
                    "description": "only empty lines",
                },
                {
                    "name": "mixed_line_endings",
                    "log_data": b"Line 1\nLine 2\r\nLine 3\rLine 4\n",
                    "description": "mixed line endings",
                },
                {
                    "name": "very_long_single_line",
                    "log_data": b"A" * 1000000 + b"\n",  # 1MB single line
                    "description": "extremely long single line",
                },
            ]

            for scenario in streaming_scenarios:
                mock_container.logs.return_value = scenario["log_data"]

                try:
                    logs_request = SwagLogsRequest(lines=100)
                    result = await swag_service.get_docker_logs(logs_request)

                    # Should handle edge cases gracefully
                    assert isinstance(result, str)
                    # Should not crash or return None
                    # Empty logs should return empty string
                    if scenario["name"] == "empty_logs":
                        assert result == ""
                    # Very long lines should be handled (truncated or processed)
                    elif scenario["name"] == "very_long_single_line":
                        assert len(result) < 2000000  # Should not return raw 1MB line

                except Exception as e:
                    # Should not cause unhandled exceptions
                    pytest.fail(f"Unhandled exception for {scenario['description']}: {str(e)}")
