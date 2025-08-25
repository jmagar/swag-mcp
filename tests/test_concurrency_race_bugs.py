"""Concurrency and race condition bug discovery tests.

These tests focus on finding real bugs that occur when multiple operations
happen simultaneously, including file corruption, deadlocks, and resource leaks.
"""

import asyncio
import contextlib
import os
import random
import time
from pathlib import Path

import pytest
from fastmcp import Client
from swag_mcp.models.config import SwagConfigRequest
from swag_mcp.services.swag_manager import SwagManagerService


class TestConcurrencyRaceBugs:
    """Bug discovery tests for concurrency and race condition vulnerabilities."""

    @pytest.mark.asyncio
    async def test_simultaneous_config_creation_race(self, mcp_client: Client, mock_config):
        """Test race conditions when multiple clients create configs simultaneously."""
        config_dir = Path(mock_config.proxy_confs_path)

        async def create_same_config(service_name: str, delay: float = 0):
            """Create config with optional delay to create race conditions."""
            if delay:
                await asyncio.sleep(delay)
            try:
                return await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": service_name,
                        "server_name": f"{service_name}.example.com",
                        "upstream_app": service_name,
                        "upstream_port": 8080,
                    },
                )
            except Exception as e:
                return e

        # Test 1: Exact same config name from multiple clients
        results = await asyncio.gather(
            create_same_config("race-test"),
            create_same_config("race-test", 0.001),
            create_same_config("race-test", 0.002),
            return_exceptions=True,
        )

        # One should succeed, others should fail gracefully with descriptive errors
        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, Exception)]

        assert len(successes) == 1, "Exactly one config creation should succeed"
        assert len(failures) == 2, "Two should fail with proper errors"

        for failure in failures:
            error_msg = str(failure).lower()
            assert any(word in error_msg for word in ["exists", "conflict", "already"])

        # Verify file integrity - should exist and be valid
        config_file = config_dir / "race-test.subdomain.conf"
        assert config_file.exists()
        content = config_file.read_text()
        assert len(content) > 0
        assert "race-test" in content

        # Clean up
        config_file.unlink()

        # Test 2: Similar but different config names (potential filename collision)
        similar_names = ["test-123", "test_123", "test.123"]
        results = await asyncio.gather(
            *[create_same_config(name) for name in similar_names], return_exceptions=True
        )

        # All should succeed or fail gracefully with user-friendly errors
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_msg = str(result).lower()
                # Check that sensitive information isn't exposed in validation errors
                assert (
                    "pydantic" not in error_msg
                ), f"Internal pydantic details exposed for {similar_names[i]}: {error_msg}"
                assert (
                    "traceback" not in error_msg
                ), f"Internal traceback exposed for {similar_names[i]}: {error_msg}"
                # For validation errors, ensure user-friendly messaging
                if "validation error" in error_msg:
                    assert any(word in error_msg for word in ["invalid", "pattern", "character"]), (
                        f"Validation error should be user-friendly for {similar_names[i]}: "
                        f"{error_msg}"
                    )

        # Clean up any created configs
        for name in similar_names:
            for ext in [".subdomain.conf", ".subfolder.conf"]:
                config_file = config_dir / f"{name}{ext}"
                if config_file.exists():
                    config_file.unlink()

    @pytest.mark.asyncio
    async def test_concurrent_read_write_corruption(self, mcp_client: Client, mock_config):
        """Test for file corruption when reading/writing configs simultaneously."""
        config_dir = Path(mock_config.proxy_confs_path)

        # Create initial config
        await mcp_client.call_tool(
            "swag_create",
            {
                "service_name": "concurrent-test",
                "server_name": "concurrent.example.com",
                "upstream_app": "concurrent-test",
                "upstream_port": 8080,
            },
        )

        async def continuous_reader(iterations: int):
            """Continuously read config to detect corruption."""
            results = []
            for i in range(iterations):
                try:
                    result = await mcp_client.call_tool(
                        "swag_view", {"config_name": "concurrent-test.subdomain.conf"}
                    )
                    if not result.is_error:
                        content = result.data
                        # Verify content integrity
                        if len(content) == 0:
                            results.append(f"Empty content at iteration {i}")
                        elif "concurrent-test" not in content:
                            results.append(f"Missing service name at iteration {i}")
                        elif content.count("{") != content.count("}"):
                            results.append(f"Unmatched braces at iteration {i}")
                    await asyncio.sleep(0.001)  # Small delay
                except Exception as e:
                    results.append(f"Read error at iteration {i}: {str(e)}")
            return results

        async def continuous_writer(iterations: int):
            """Continuously write config to create race conditions."""
            results = []
            for i in range(iterations):
                try:
                    new_content = f"""# Modified iteration {i}
server {{
    listen 443;
    server_name concurrent.example.com;
    location / {{
        proxy_pass http://concurrent-test:808{i % 10};
    }}
}}"""
                    result = await mcp_client.call_tool(
                        "swag_edit",
                        {
                            "config_name": "concurrent-test.subdomain.conf",
                            "new_content": new_content,
                        },
                    )
                    if result.is_error:
                        results.append(f"Write error at iteration {i}: {result.error}")
                    await asyncio.sleep(0.001)  # Small delay
                except Exception as e:
                    results.append(f"Write exception at iteration {i}: {str(e)}")
            return results

        # Run concurrent readers and writers
        try:
            reader_results, writer_results = await asyncio.gather(
                continuous_reader(50), continuous_writer(25), return_exceptions=True
            )

            # Check for corruption indicators
            all_issues = []
            if isinstance(reader_results, list):
                all_issues.extend(reader_results)
            if isinstance(writer_results, list):
                all_issues.extend(writer_results)

            if all_issues:
                pytest.fail(
                    f"File corruption detected during concurrent operations: {all_issues[:5]}"
                )

        finally:
            # Clean up
            config_file = config_dir / "concurrent-test.subdomain.conf"
            if config_file.exists():
                config_file.unlink()
            # Clean up any backup files
            for backup_file in config_dir.glob("concurrent-test.subdomain.conf.backup.*"):
                backup_file.unlink()

    @pytest.mark.asyncio
    async def test_backup_creation_race_conditions(self, swag_service: SwagManagerService):
        """Test race conditions in backup file creation."""
        # Create initial config
        request = SwagConfigRequest(
            service_name="backup-race",
            server_name="backup.example.com",
            upstream_app="backup-test",
            upstream_port=8080,
        )
        await swag_service.create_config(request)

        async def create_backup_rapidly(iteration: int):
            """Create backup with rapid succession to test timestamp collision."""
            from swag_mcp.models.config import SwagEditRequest

            edit_request = SwagEditRequest(
                config_name="backup-race.subdomain.conf",
                new_content=f"# Backup test {iteration}",
                create_backup=True,
            )
            try:
                result = await swag_service.update_config(edit_request)
                return result.backup_created
            except Exception as e:
                return f"Error {iteration}: {str(e)}"

        # Create multiple backups simultaneously
        backup_results = await asyncio.gather(
            *[create_backup_rapidly(i) for i in range(10)], return_exceptions=True
        )

        # Verify all backups were created with unique names
        backup_names = [
            r for r in backup_results if isinstance(r, str) and r.startswith("backup-race")
        ]
        unique_backups = set(backup_names)

        if len(backup_names) != len(unique_backups):
            pytest.fail(
                f"Backup name collision detected: {len(backup_names)} backups, "
                f"{len(unique_backups)} unique names"
            )

        # Verify all backup files exist and have content
        for backup_name in backup_names:
            backup_file = swag_service.config_path / backup_name
            assert backup_file.exists(), f"Backup file missing: {backup_name}"
            content = backup_file.read_text()
            assert len(content) > 0, f"Empty backup file: {backup_name}"

        # Clean up
        config_file = swag_service.config_path / "backup-race.subdomain.conf"
        if config_file.exists():
            config_file.unlink()
        for backup_file in swag_service.config_path.glob("backup-race.*"):
            backup_file.unlink()

    @pytest.mark.asyncio
    async def test_async_resource_cleanup_leaks(self, swag_service: SwagManagerService):
        """Test for resource leaks in async file operations with exceptions."""
        initial_fd_count = (
            len(os.listdir("/proc/self/fd")) if os.path.exists("/proc/self/fd") else 0
        )

        async def failing_operation():
            """Perform operation that might fail and leak resources."""
            # Create config that will cause various failure modes
            failing_configs = [
                # Invalid template data that might cause partial processing
                SwagConfigRequest(
                    service_name="leak-test",
                    server_name="",  # Invalid empty server name
                    upstream_app="test",
                    upstream_port=8080,
                ),
                SwagConfigRequest(
                    service_name="",  # Invalid empty service name
                    server_name="leak.example.com",
                    upstream_app="test",
                    upstream_port=8080,
                ),
                SwagConfigRequest(
                    service_name="leak-test",
                    server_name="leak.example.com",
                    upstream_app="test",
                    upstream_port=-1,  # Invalid port
                ),
            ]

            for config in failing_configs:
                with contextlib.suppress(Exception):
                    await swag_service.create_config(config)

        # Run many failing operations to amplify any resource leaks
        tasks = [failing_operation() for _ in range(20)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Small delay to allow cleanup
        await asyncio.sleep(0.1)

        # Check for file descriptor leaks (Linux only)
        if os.path.exists("/proc/self/fd"):
            final_fd_count = len(os.listdir("/proc/self/fd"))
            fd_increase = final_fd_count - initial_fd_count

            # Allow some increase for normal operations, but flag excessive growth
            if fd_increase > 10:
                pytest.fail(f"Potential file descriptor leak: increased by {fd_increase} FDs")

    @pytest.mark.asyncio
    async def test_deadlock_prevention(self, mcp_client: Client, mock_config):
        """Test for deadlocks in concurrent file operations."""
        config_dir = Path(mock_config.proxy_confs_path)

        # Create multiple configs that will be operated on simultaneously
        config_names = [f"deadlock-test-{i}" for i in range(5)]

        for name in config_names:
            await mcp_client.call_tool(
                "swag_create",
                {
                    "service_name": name,
                    "server_name": f"{name}.example.com",
                    "upstream_app": name,
                    "upstream_port": 8080,
                },
            )

        async def mixed_operations(base_name: str, iterations: int):
            """Perform mixed read/write/backup operations that could cause deadlocks."""
            operations = []
            for i in range(iterations):
                operation_type = random.choice(["read", "edit", "remove_and_recreate"])
                config_name = f"{base_name}.subdomain.conf"

                try:
                    if operation_type == "read":
                        await mcp_client.call_tool("swag_view", {"config_name": config_name})
                        operations.append(f"read_{i}")

                    elif operation_type == "edit":
                        new_content = f"# Edit {i}\nserver {{ listen 443; }}"
                        await mcp_client.call_tool(
                            "swag_edit",
                            {
                                "config_name": config_name,
                                "new_content": new_content,
                                "create_backup": True,
                            },
                        )
                        operations.append(f"edit_{i}")

                    elif operation_type == "remove_and_recreate":
                        # Remove
                        await mcp_client.call_tool("swag_remove", {"config_name": config_name})
                        # Recreate
                        await mcp_client.call_tool(
                            "swag_create",
                            {
                                "service_name": base_name,
                                "server_name": f"{base_name}.example.com",
                                "upstream_app": base_name,
                                "upstream_port": 8080,
                            },
                        )
                        operations.append(f"remove_recreate_{i}")

                    # Small random delay to increase chance of race conditions
                    await asyncio.sleep(random.uniform(0.001, 0.01))

                except Exception as e:
                    operations.append(f"error_{i}_{str(e)[:50]}")

            return operations

        # Run operations on different configs simultaneously with timeout to detect deadlocks
        try:
            results = await asyncio.wait_for(
                asyncio.gather(
                    *[mixed_operations(name, 10) for name in config_names], return_exceptions=True
                ),
                timeout=30.0,  # Should complete well within 30 seconds
            )

            # Analyze results for excessive errors or patterns indicating deadlock
            for i, ops in enumerate(results):
                if isinstance(ops, Exception):
                    pytest.fail(f"Operation sequence failed for {config_names[i]}: {ops}")

                error_count = len([op for op in ops if op.startswith("error_")])
                if error_count > 5:  # More than half failed
                    pytest.fail(
                        f"Excessive errors for {config_names[i]}: "
                        f"{error_count}/10 operations failed"
                    )

        except TimeoutError:
            pytest.fail("Operations timed out - possible deadlock detected")

        finally:
            # Clean up - remove all test configs and backups
            for name in config_names:
                config_file = config_dir / f"{name}.subdomain.conf"
                if config_file.exists():
                    config_file.unlink()

            # Clean up backup files
            for backup_file in config_dir.glob("deadlock-test-*.backup.*"):
                backup_file.unlink()

    @pytest.mark.asyncio
    async def test_file_locking_conflicts(self, swag_service: SwagManagerService):
        """Test file locking behavior under concurrent access."""
        # This test is particularly important on Windows where file locking is more restrictive

        config_file = swag_service.config_path / "lock-test.conf"
        config_file.write_text("# Initial content")

        async def lock_and_modify(iteration: int, hold_time: float):
            """Simulate operations that might lock files."""
            try:
                # Simulate reading file (might create shared lock)
                content = await swag_service.read_config("lock-test.conf")

                # Hold operation for specified time to increase conflict chance
                await asyncio.sleep(hold_time)

                # Simulate writing (might create exclusive lock)
                from swag_mcp.models.config import SwagEditRequest

                edit_request = SwagEditRequest(
                    config_name="lock-test.conf",
                    new_content=f"# Modified by iteration {iteration}\n{content}",
                    create_backup=True,
                )
                await swag_service.update_config(edit_request)
                return f"success_{iteration}"

            except Exception as e:
                error_msg = str(e).lower()
                # Check for file locking related errors
                if any(
                    word in error_msg for word in ["lock", "busy", "access denied", "permission"]
                ):
                    return f"lock_error_{iteration}_{error_msg[:50]}"
                else:
                    return f"other_error_{iteration}_{error_msg[:50]}"

        # Run concurrent operations with different hold times to create conflicts
        results = await asyncio.gather(
            lock_and_modify(1, 0.1),
            lock_and_modify(2, 0.05),
            lock_and_modify(3, 0.15),
            lock_and_modify(4, 0.02),
            return_exceptions=True,
        )

        # Analyze locking behavior
        # lock_errors = [r for r in results if isinstance(r, str) and "lock_error" in r]
        successes = [r for r in results if isinstance(r, str) and r.startswith("success_")]
        other_errors = [r for r in results if isinstance(r, str) and "other_error" in r]
        exceptions = [r for r in results if not isinstance(r, str)]

        # At least some operations should succeed
        assert len(successes) > 0, f"No operations succeeded: {results}"

        # File locking errors are acceptable, but other errors or exceptions are concerning
        if other_errors:
            pytest.fail(f"Unexpected errors during file locking test: {other_errors}")
        if exceptions:
            pytest.fail(f"Exceptions during file locking test: {exceptions}")

        # Verify final file integrity
        final_content = config_file.read_text()
        assert len(final_content) > 0, "File was corrupted to empty content"
        assert "lock-test" in final_content or "Modified by iteration" in final_content

        # Clean up
        config_file.unlink()
        for backup_file in swag_service.config_path.glob("lock-test.conf.backup.*"):
            backup_file.unlink()

    @pytest.mark.asyncio
    async def test_cleanup_operation_race_conditions(self, swag_service: SwagManagerService):
        """Test race conditions between cleanup operations and active file operations."""
        # Create many backup files
        config_name = "cleanup-race.conf"
        config_file = swag_service.config_path / config_name
        config_file.write_text("# Test config")

        # Create old backup files that should be cleaned up
        backup_files = []
        for i in range(10):
            backup_name = (
                f"{config_name}.backup.{int(time.time()) - (40 * 24 * 60 * 60) - i}"  # 40+ days old
            )
            backup_file = swag_service.config_path / backup_name
            backup_file.write_text(f"# Old backup {i}")
            backup_files.append(backup_file)

        async def active_file_operations():
            """Perform active operations while cleanup is running."""
            operations = []
            for i in range(5):
                try:
                    # Read config
                    content = await swag_service.read_config(config_name)
                    operations.append(f"read_{i}")

                    # Create new backup
                    from swag_mcp.models.config import SwagEditRequest

                    edit_request = SwagEditRequest(
                        config_name=config_name,
                        new_content=f"# Active operation {i}\n{content}",
                        create_backup=True,
                    )
                    await swag_service.update_config(edit_request)
                    operations.append(f"edit_{i}")

                    await asyncio.sleep(0.01)  # Small delay

                except Exception as e:
                    operations.append(f"error_{i}_{str(e)[:30]}")

            return operations

        async def cleanup_operations():
            """Run cleanup while other operations are active."""
            try:
                cleaned_count = await swag_service.cleanup_old_backups(retention_days=30)
                return f"cleaned_{cleaned_count}"
            except Exception as e:
                return f"cleanup_error_{str(e)[:50]}"

        # Run cleanup and active operations simultaneously
        results = await asyncio.gather(
            active_file_operations(), cleanup_operations(), return_exceptions=True
        )

        active_results, cleanup_result = results

        # Verify no serious errors occurred
        if isinstance(active_results, Exception):
            pytest.fail(f"Active operations failed with exception: {active_results}")
        if isinstance(cleanup_result, Exception):
            pytest.fail(f"Cleanup failed with exception: {cleanup_result}")

        # Check for errors in active operations
        errors = [op for op in active_results if op.startswith("error_")]
        if len(errors) > 2:  # Allow some errors due to timing
            pytest.fail(f"Too many errors in active operations during cleanup: {errors}")

        # Verify cleanup worked
        if not cleanup_result.startswith("cleaned_"):
            pytest.fail(f"Cleanup operation failed: {cleanup_result}")

        # Verify old backup files were cleaned up
        remaining_old_backups = [bf for bf in backup_files if bf.exists()]
        if len(remaining_old_backups) > 2:  # Allow some to remain due to race conditions
            pytest.fail(
                f"Cleanup didn't remove enough old backups: {len(remaining_old_backups)} remaining"
            )

        # Clean up remaining test files
        if config_file.exists():
            config_file.unlink()
        for backup_file in swag_service.config_path.glob(f"{config_name}.backup.*"):
            backup_file.unlink()
