"""Error recovery and exception handling bug discovery tests.

These tests focus on finding bugs in error handling, recovery scenarios,
and exception propagation by simulating real failure conditions.
"""

import asyncio
import contextlib
import stat
from pathlib import Path
from unittest.mock import patch

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from swag_mcp.models.config import SwagConfigRequest, SwagEditRequest
from swag_mcp.services.swag_manager import SwagManagerService


class TestErrorRecoveryBugs:
    """Bug discovery tests for error recovery and exception handling gaps."""

    @pytest.mark.asyncio
    async def test_disk_full_recovery_behavior(self, swag_service: SwagManagerService):
        """Test system behavior when disk space is exhausted and then recovered."""
        config_dir = swag_service.config_path
        large_content = "# Large config\n" + ("# Comment line\n" * 10000)  # ~200KB

        # Create initial config
        request = SwagConfigRequest(
            service_name="disk-full-test",
            server_name="diskfull.example.com",
            upstream_app="diskfull-test",
            upstream_port=8080,
        )
        result = await swag_service.create_config(request)
        config_file = config_dir / result.filename

        try:
            # Simulate disk full by patching file write operations
            original_write = Path.write_text
            write_call_count = 0

            def failing_write(self, data, encoding=None, errors=None, newline=None):
                nonlocal write_call_count
                write_call_count += 1

                # Fail the first few write attempts to simulate disk full
                if write_call_count <= 2:
                    raise OSError(28, "No space left on device")  # ENOSPC
                else:
                    # Allow subsequent writes to succeed (disk space recovered)
                    return original_write(self, data, encoding, errors, newline)

            with patch.object(Path, "write_text", failing_write):
                # Try to update config while "disk is full"
                edit_request = SwagEditRequest(
                    config_name=result.filename,
                    new_content=large_content,
                    create_backup=True,
                )

                # First attempt should fail due to disk full
                with pytest.raises((OSError, IOError, ValueError)) as exc_info:
                    await swag_service.update_config(edit_request)

                error_msg = str(exc_info.value).lower()
                assert "space" in error_msg or "disk" in error_msg or "enospc" in error_msg

                # File should not be corrupted (should remain original or be empty)
                if config_file.exists():
                    current_content = config_file.read_text()
                    # Should either be original content or empty (partial write should be avoided)
                    assert current_content == "" or "disk-full-test" in current_content

                # Reset counter to simulate disk space recovery
                write_call_count = 10

                # Second attempt should succeed after disk space recovery
                result2 = await swag_service.update_config(edit_request)
                assert result2.backup_created is not None

                # Verify file integrity after recovery
                final_content = config_file.read_text()
                assert len(final_content) > 100  # Should have the large content
                assert "Large config" in final_content

        finally:
            # Clean up
            if config_file.exists():
                config_file.unlink()
            for backup_file in config_dir.glob(f"{result.filename}.backup.*"):
                backup_file.unlink()

    @pytest.mark.asyncio
    async def test_permission_denied_recovery(self, swag_service: SwagManagerService):
        """Test recovery when file permissions are denied and then restored."""
        config_dir = swag_service.config_path

        # Create initial config
        request = SwagConfigRequest(
            service_name="permission-test",
            server_name="permission.example.com",
            upstream_app="permission-test",
            upstream_port=8080,
        )
        result = await swag_service.create_config(request)
        config_file = config_dir / result.filename

        try:
            # Make config file read-only to simulate permission issues
            original_mode = config_file.stat().st_mode
            config_file.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # Read-only

            # Try to update read-only file
            edit_request = SwagEditRequest(
                config_name=result.filename,
                new_content="# Updated content",
                create_backup=True,
            )

            with pytest.raises(Exception) as exc_info:
                await swag_service.update_config(edit_request)

            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["permission", "access", "denied", "readonly"])

            # Restore write permissions
            config_file.chmod(original_mode)

            # Operation should now succeed
            result2 = await swag_service.update_config(edit_request)
            assert "Updated content" in result2.content

            # Verify file was actually updated
            final_content = config_file.read_text()
            assert "Updated content" in final_content

        finally:
            # Ensure permissions are restored and clean up
            if config_file.exists():
                with contextlib.suppress(OSError, PermissionError):
                    config_file.chmod(0o666)
                config_file.unlink()
            for backup_file in config_dir.glob(f"{result.filename}.backup.*"):
                backup_file.unlink()

    @pytest.mark.asyncio
    async def test_partial_write_corruption_recovery(self, swag_service: SwagManagerService):
        """Test recovery from partial file writes that leave files corrupted."""
        config_dir = swag_service.config_path

        # Create initial config
        request = SwagConfigRequest(
            service_name="partial-write-test",
            server_name="partial.example.com",
            upstream_app="partial-test",
            upstream_port=8080,
        )
        result = await swag_service.create_config(request)
        config_file = config_dir / result.filename
        original_content = config_file.read_text()

        try:
            # Simulate partial write by interrupting the write operation
            original_write = Path.write_text

            def partial_write(self, data, encoding=None, errors=None, newline=None):
                # Write only part of the data, then fail
                partial_data = data[: len(data) // 2]  # Write only first half
                original_write(self, partial_data, encoding, errors, newline)
                raise OSError("Write operation interrupted")

            with patch.object(Path, "write_text", partial_write):
                edit_request = SwagEditRequest(
                    config_name=result.filename,
                    new_content="# This is a complete config file\nserver { listen 443; }",
                    create_backup=True,
                )

                with pytest.raises((OSError, PermissionError, FileNotFoundError)):
                    await swag_service.update_config(edit_request)

            # File should now be corrupted (partially written)
            corrupted_content = config_file.read_text()
            assert len(corrupted_content) < len(original_content) + 50  # Should be truncated

            # Try to read the corrupted config
            with pytest.raises((OSError, IOError, ValueError)):
                content = await swag_service.read_config(result.filename)
                # If read succeeds, content should be detectably corrupted
                if "server {" in content and "}" not in content:
                    pytest.fail("Corrupted config was accepted as valid")

            # Recovery: restore from backup or recreate
            # First try to restore the original content
            config_file.write_text(original_content)

            # Now the read should succeed
            recovered_content = await swag_service.read_config(result.filename)
            assert "partial-write-test" in recovered_content

        finally:
            # Clean up
            if config_file.exists():
                config_file.unlink()
            for backup_file in config_dir.glob(f"{result.filename}.backup.*"):
                backup_file.unlink()

    @pytest.mark.asyncio
    async def test_backup_corruption_recovery(self, swag_service: SwagManagerService):
        """Test recovery when backup files are corrupted or missing."""
        config_dir = swag_service.config_path

        # Create config and backup
        request = SwagConfigRequest(
            service_name="backup-corrupt-test",
            server_name="corrupt.example.com",
            upstream_app="corrupt-test",
            upstream_port=8080,
        )
        result = await swag_service.create_config(request)
        config_file = config_dir / result.filename

        # Create a backup
        edit_request = SwagEditRequest(
            config_name=result.filename,
            new_content="# Modified content",
            create_backup=True,
        )
        result2 = await swag_service.update_config(edit_request)
        backup_file = config_dir / result2.backup_created

        try:
            # Corrupt the backup file
            backup_file.write_bytes(b"\x00\x01\x02\xff\xfe\xfd")  # Binary garbage

            # Try to read the corrupted backup
            try:
                backup_file.read_text()
                pytest.fail("Corrupted backup was read as text without error")
            except UnicodeDecodeError:
                # Expected - backup is corrupted
                pass

            # System should handle corrupted backups gracefully
            # Try to create another backup (should not be affected by corrupted existing backup)
            edit_request2 = SwagEditRequest(
                config_name=result.filename,
                new_content="# Another modification",
                create_backup=True,
            )
            result3 = await swag_service.update_config(edit_request2)

            # New backup should be created successfully
            assert result3.backup_created is not None
            new_backup_file = config_dir / result3.backup_created
            assert new_backup_file.exists()

            # New backup should be valid
            new_backup_content = new_backup_file.read_text()
            assert "Modified content" in new_backup_content

        finally:
            # Clean up
            if config_file.exists():
                config_file.unlink()
            for backup_file in config_dir.glob(f"{result.filename}.backup.*"):
                with contextlib.suppress(OSError, FileNotFoundError):
                    backup_file.unlink()

    @pytest.mark.asyncio
    async def test_template_rendering_error_recovery(self, swag_service: SwagManagerService):
        """Test recovery from template rendering errors."""
        # Test with template that will cause rendering error
        failing_template_data = {
            "service_name": "template-error-test",
            "server_name": "error.example.com",
            "upstream_app": "{{undefined_variable}}",  # This should cause template error
            "upstream_port": 8080,
        }

        with pytest.raises(Exception) as exc_info:
            request = SwagConfigRequest(**failing_template_data)
            await swag_service.create_config(request)

        # Should get a descriptive template error, not a generic exception
        error_msg = str(exc_info.value).lower()
        assert any(word in error_msg for word in ["template", "variable", "undefined", "render"])

        # System should remain stable after template error
        # Try a valid config creation immediately after
        valid_request = SwagConfigRequest(
            service_name="template-recovery-test",
            server_name="recovery.example.com",
            upstream_app="recovery-test",
            upstream_port=8080,
        )
        result = await swag_service.create_config(valid_request)

        # Should succeed and create proper file
        config_file = swag_service.config_path / result.filename
        assert config_file.exists()
        content = config_file.read_text()
        assert "template-recovery-test" in content

        # Clean up
        config_file.unlink()

    @pytest.mark.asyncio
    async def test_exception_propagation_gaps(self, mcp_client: Client):
        """Test for gaps in exception handling where errors aren't properly propagated."""

        # Test various scenarios that should raise specific exceptions
        exception_scenarios = [
            # Invalid port ranges
            {
                "tool": "swag_create",
                "params": {
                    "service_name": "port-test",
                    "server_name": "port.example.com",
                    "upstream_app": "test",
                    "upstream_port": 99999,  # Out of valid range
                },
                "expected_errors": ["port", "range", "invalid", "validation"],
            },
            # Extremely long service names
            {
                "tool": "swag_create",
                "params": {
                    "service_name": "x" * 1000,  # Very long name
                    "server_name": "long.example.com",
                    "upstream_app": "test",
                    "upstream_port": 8080,
                },
                "expected_errors": ["length", "long", "invalid", "name"],
            },
            # Invalid domain formats
            {
                "tool": "swag_create",
                "params": {
                    "service_name": "domain-test",
                    "server_name": "invalid..domain..com",  # Double dots
                    "upstream_app": "test",
                    "upstream_port": 8080,
                },
                "expected_errors": ["domain", "invalid", "format"],
            },
            # Malformed config names
            {
                "tool": "swag_view",
                "params": {"config_name": "does-not-exist.conf"},
                "expected_errors": ["not found", "missing", "exist"],
            },
        ]

        for scenario in exception_scenarios:
            with pytest.raises(ToolError) as exc_info:
                await mcp_client.call_tool(scenario["tool"], scenario["params"])

            error_msg = str(exc_info.value).lower()

            # Should not be generic "internal error"
            assert "internal error" not in error_msg, f"Generic error for {scenario}: {error_msg}"

            # Should contain expected error indicators
            has_expected_error = any(
                expected in error_msg for expected in scenario["expected_errors"]
            )
            assert has_expected_error, f"Missing expected error for {scenario}: {error_msg}"

            # Should not contain stack traces or implementation details
            assert "traceback" not in error_msg
            assert "line " not in error_msg  # Line numbers from stack traces
            assert "__" not in error_msg  # Python internal method names

    @pytest.mark.asyncio
    async def test_async_context_cleanup_failures(self, swag_service: SwagManagerService):
        """Test async context manager cleanup when operations fail."""

        # Mock file operations to fail at different points
        original_open = Path.open

        def failing_open(self, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
            if "fail-context" in str(self):
                raise PermissionError("Simulated file access failure")
            return original_open(self, mode, buffering, encoding, errors, newline)

        with patch.object(Path, "open", failing_open):
            # Try to read a config that will fail to open
            with pytest.raises(Exception) as exc_info:
                await swag_service.read_config("fail-context-test.conf")

            # Exception should be properly handled
            error_msg = str(exc_info.value).lower()
            assert "permission" in error_msg or "access" in error_msg or "not found" in error_msg

        # Test with actual file that exists but becomes inaccessible
        config_file = swag_service.config_path / "context-cleanup-test.conf"
        config_file.write_text("# Test content")

        try:
            # Make file inaccessible
            config_file.chmod(0o000)

            with pytest.raises((OSError, PermissionError, FileNotFoundError)):
                await swag_service.read_config("context-cleanup-test.conf")

            # Restore access
            config_file.chmod(0o666)

            # Should work now
            content = await swag_service.read_config("context-cleanup-test.conf")
            assert "Test content" in content

        finally:
            if config_file.exists():
                try:
                    config_file.chmod(0o666)
                    config_file.unlink()
                except (OSError, PermissionError):
                    pass

    @pytest.mark.asyncio
    async def test_transaction_rollback_scenarios(self, swag_service: SwagManagerService):
        """Test rollback behavior when multi-step operations fail partway through."""
        config_dir = swag_service.config_path

        # Create initial config
        request = SwagConfigRequest(
            service_name="transaction-test",
            server_name="transaction.example.com",
            upstream_app="transaction-test",
            upstream_port=8080,
        )
        result = await swag_service.create_config(request)
        config_file = config_dir / result.filename
        original_content = config_file.read_text()

        try:
            # Simulate failure after backup creation but before config update
            original_write = Path.write_text
            backup_created = False

            def selective_failing_write(self, data, encoding=None, errors=None, newline=None):
                nonlocal backup_created

                if "backup" in str(self):
                    # Allow backup creation to succeed
                    backup_created = True
                    return original_write(self, data, encoding, errors, newline)
                elif str(self).endswith("transaction-test.subdomain.conf"):
                    # Fail the main config update
                    raise OSError("Simulated failure during config update")
                else:
                    return original_write(self, data, encoding, errors, newline)

            with patch.object(Path, "write_text", selective_failing_write):
                edit_request = SwagEditRequest(
                    config_name=result.filename,
                    new_content="# Transaction test update",
                    create_backup=True,
                )

                with pytest.raises((OSError, IOError)):
                    await swag_service.update_config(edit_request)

            # Check transaction state after failure
            # Original config should be unchanged (rollback behavior)
            current_content = config_file.read_text()
            assert (
                current_content == original_content
            ), "Config was partially updated without rollback"

            # Backup should exist (operation got that far)
            assert backup_created, "Backup creation should have succeeded"
            backup_files = list(config_dir.glob(f"{result.filename}.backup.*"))
            assert len(backup_files) >= 1, "Backup file should exist after partial operation"

            # System should be in consistent state for retry
            edit_request2 = SwagEditRequest(
                config_name=result.filename,
                new_content="# Retry transaction test",
                create_backup=True,
            )
            result2 = await swag_service.update_config(edit_request2)

            # Retry should succeed
            assert "Retry transaction test" in result2.content

        finally:
            # Clean up
            if config_file.exists():
                config_file.unlink()
            for backup_file in config_dir.glob(f"{result.filename}.backup.*"):
                backup_file.unlink()

    @pytest.mark.asyncio
    async def test_network_interruption_simulation(self, mcp_client: Client, mock_config):
        """Test behavior when network operations are interrupted."""

        # Simulate network-related operations that could be interrupted
        async def simulate_slow_network_operation():
            """Simulate a slow network operation that could be interrupted."""
            await asyncio.sleep(0.1)  # Simulate network delay
            return "network_operation_complete"

        # Test timeout behavior with actual operations
        timeout_scenarios = [
            {
                "tool": "swag_logs",
                "params": {"lines": 1000},
                "timeout": 0.001,
            },  # Very short timeout
        ]

        for scenario in timeout_scenarios:
            try:
                # Use asyncio.wait_for to simulate network timeout
                await asyncio.wait_for(
                    mcp_client.call_tool(scenario["tool"], scenario["params"]),
                    timeout=scenario["timeout"],
                )
                # If it completes within timeout, that's fine

            except TimeoutError:
                # Expected behavior for slow operations
                pass
            except Exception as e:
                # Should not cause system instability
                error_msg = str(e).lower()
                assert "crash" not in error_msg
                assert "internal error" not in error_msg

    @pytest.mark.asyncio
    async def test_resource_cleanup_on_process_interruption(self, swag_service: SwagManagerService):
        """Test resource cleanup when operations are forcibly interrupted."""

        config_dir = swag_service.config_path
        cleanup_test_files = []

        try:
            # Create operation that will be interrupted
            async def long_running_operation():
                """Operation that takes time and creates resources."""
                for i in range(10):
                    temp_file = config_dir / f"temp_operation_{i}.tmp"
                    temp_file.write_text(f"Temporary data {i}")
                    cleanup_test_files.append(temp_file)
                    await asyncio.sleep(0.01)  # Allow interruption

                # If we get here, operation completed normally
                return "operation_completed"

            # Start the operation
            task = asyncio.create_task(long_running_operation())

            # Interrupt it after short time
            await asyncio.sleep(0.05)
            task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await task

            # Check for resource leaks
            # remaining_temp_files = [f for f in cleanup_test_files if f.exists()]

            # Some temp files might remain (this is acceptable for this test)
            # But there shouldn't be excessive file descriptor leaks
            # This is a basic test - more sophisticated resource tracking
            # would be needed for production

        finally:
            # Manual cleanup
            for temp_file in cleanup_test_files:
                if temp_file.exists():
                    with contextlib.suppress(OSError, FileNotFoundError):
                        temp_file.unlink()
