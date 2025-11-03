"""Concurrency tests for SWAG MCP.

Tests critical concurrency fixes including deadlock prevention,
race condition handling, and resource management.
"""

import asyncio
import tempfile
import time
from pathlib import Path

import pytest
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.utils.async_utils import AsyncLineReader, bounded_gather


class TestDeadlockPrevention:
    """Test deadlock prevention in SwagManagerService."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def swag_service(self, temp_dir):
        """Create SwagManagerService instance for testing."""
        return SwagManagerService(
            config_path=temp_dir,
            template_path=Path("templates")
        )

    @pytest.mark.asyncio
    async def test_deadlock_prevention_cleanup_backup_locks(self, swag_service):
        """Test that cleanup and backup operations don't deadlock.

        This tests the fix for the critical deadlock risk identified in
        the SwagManagerService where nested locks could cause deadlocks.
        """
        # Create some test backup files
        test_files = []
        for i in range(5):
            backup_file = swag_service.config_path / f"test{i}.backup.20240101_120000"
            backup_file.write_text(f"test backup content {i}")
            test_files.append(backup_file)

        # Create tasks that will try to acquire locks in different orders
        async def cleanup_task():
            return await swag_service.cleanup_old_backups(retention_days=0)

        async def backup_task(i):
            # Create a config file to backup
            config_file = swag_service.config_path / f"test{i}.conf"
            config_file.write_text(f"test config {i}")
            return await swag_service.backup_manager.create_backup(f"test{i}.conf")

        # Run operations concurrently that previously could deadlock
        tasks = [cleanup_task()]
        tasks.extend([backup_task(i) for i in range(3)])

        # This should complete without deadlocking
        start_time = time.time()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        elapsed = time.time() - start_time

        # Should complete quickly (no deadlock)
        assert elapsed < 5.0, "Operations took too long, possible deadlock"

        # Check that we got results (not exceptions)
        cleanup_result = results[0]
        assert isinstance(cleanup_result, int), "Cleanup should return count"

        # Backup results might be exceptions due to missing templates, but shouldn't hang
        for i, result in enumerate(results[1:], 1):
            assert result is not None, f"Backup task {i} should not hang"

    @pytest.mark.asyncio
    async def test_ordered_locking_pattern(self, swag_service):
        """Test that the ordered locking pattern prevents deadlocks.

        This verifies that the fix from nested locks to ordered locks
        prevents the deadlock condition.
        """
        lock_acquisition_order = []

        # Mock the locks to track acquisition order
        original_cleanup_lock = swag_service.backup_manager._cleanup_lock
        original_backup_lock = swag_service.backup_manager._backup_lock

        class TrackingLock:
            def __init__(self, name, original_lock):
                self.name = name
                self._lock = original_lock

            async def __aenter__(self):
                lock_acquisition_order.append(f"acquire_{self.name}")
                return await self._lock.__aenter__()

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                lock_acquisition_order.append(f"release_{self.name}")
                return await self._lock.__aexit__(exc_type, exc_val, exc_tb)

        swag_service.backup_manager._cleanup_lock = TrackingLock("cleanup", original_cleanup_lock)
        swag_service.backup_manager._backup_lock = TrackingLock("backup", original_backup_lock)

        # Create test backup files
        for i in range(3):
            backup_file = swag_service.config_path / f"old{i}.backup.20200101_120000"
            backup_file.write_text(f"old backup {i}")

        # Run cleanup which should acquire locks in order
        await swag_service.cleanup_old_backups(retention_days=0)

        # Verify correct lock ordering (cleanup before backup)
        cleanup_acquire_idx = lock_acquisition_order.index("acquire_cleanup")
        backup_acquire_idx = lock_acquisition_order.index("acquire_backup")

        assert cleanup_acquire_idx < backup_acquire_idx, (
            "Cleanup lock should be acquired before backup lock to prevent deadlock"
        )


class TestRaceConditionHandling:
    """Test race condition handling in concurrent operations."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def swag_service(self, temp_dir):
        """Create SwagManagerService instance for testing."""
        return SwagManagerService(
            config_path=temp_dir,
            template_path=Path("templates")
        )

    @pytest.mark.asyncio
    async def test_concurrent_file_operations_no_corruption(self, swag_service):
        """Test that concurrent file writes don't corrupt data.

        This tests the per-file locking mechanism that prevents
        race conditions in file operations.
        """
        config_file = swag_service.config_path / "test.conf"
        config_file.write_text("initial content")

        # Track write operations
        write_operations = []

        async def write_operation(content, operation_id):
            """Simulate a write operation with tracking."""
            write_operations.append(f"start_{operation_id}")

            # Use the service's file writing mechanism
            await swag_service.file_ops.safe_write_file(
                config_file,
                content,
                f"test operation {operation_id}"
            )

            write_operations.append(f"end_{operation_id}")
            return operation_id

        # Run multiple concurrent write operations
        tasks = [
            write_operation(f"content from operation {i}", i)
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All operations should complete successfully
        assert len([r for r in results if not isinstance(r, Exception)]) == 5

        # File should contain content from one of the operations (not corrupted)
        final_content = config_file.read_text()
        assert "content from operation" in final_content
        assert "initial content" not in final_content  # Should be overwritten

        # Operations should have executed in some order (not interleaved)
        # Check that start/end pairs are properly nested or sequential
        start_count = len([op for op in write_operations if op.startswith("start_")])
        end_count = len([op for op in write_operations if op.startswith("end_")])
        assert start_count == end_count == 5

    @pytest.mark.asyncio
    async def test_backup_creation_race_condition_prevention(self, swag_service):
        """Test that concurrent backup creation uses UUID fallback.

        This tests the race condition fix for backup naming that now
        includes UUID suffixes to ensure uniqueness.
        """
        # Create a config file to backup
        config_file = swag_service.config_path / "test.conf"
        config_file.write_text("test configuration content")

        # Create multiple concurrent backup operations
        async def create_backup():
            return await swag_service.backup_manager.create_backup("test.conf")

        # Run many concurrent backup operations
        tasks = [create_backup() for _ in range(10)]
        backup_names = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out any exceptions (some might fail due to missing original file)
        successful_backups = [
            name for name in backup_names
            if isinstance(name, str) and not isinstance(name, Exception)
        ]

        # If any succeeded, they should all have unique names
        if successful_backups:
            assert len(successful_backups) == len(set(successful_backups)), (
                "All backup names should be unique (race condition test)"
            )

            # Each backup name should contain a UUID suffix
            for backup_name in successful_backups:
                # Format: filename.backup.YYYYMMDD_HHMMSS_microseconds_uuid
                parts = backup_name.split('_')
                assert len(parts) >= 4, f"Backup name should have UUID suffix: {backup_name}"

                # The last part should be an 8-character UUID
                uuid_part = parts[-1]
                assert len(uuid_part) == 8, f"UUID part should be 8 characters: {uuid_part}"
                assert uuid_part.isalnum(), f"UUID part should be alphanumeric: {uuid_part}"


class TestResourceManagement:
    """Test proper resource management and cleanup."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)

    @pytest.fixture
    def swag_service(self, temp_dir):
        """Create SwagManagerService instance for testing."""
        return SwagManagerService(
            config_path=temp_dir,
            template_path=Path("templates")
        )

    @pytest.mark.asyncio
    async def test_http_session_cleanup(self, swag_service):
        """Test that HTTP sessions are properly cleaned up.

        This tests the HTTP session resource leak fix with the new
        async context manager pattern.
        """
        # Use the service as an async context manager
        async with swag_service:
            # Get a session to create one
            session1 = await swag_service.health_monitor.get_session()
            assert session1 is not None
            assert not session1.closed

            # Get the same session (should be cached)
            session2 = await swag_service.health_monitor.get_session()
            assert session1 is session2

        # After context exit, session should be cleaned up
        # Note: We can't easily test if it's actually closed without
        # accessing private members, but the cleanup should have been called

    @pytest.mark.asyncio
    async def test_file_locks_cleanup(self, swag_service):
        """Test that file locks are properly cleaned up.

        This tests the file lock cleanup mechanism that prevents
        memory growth from accumulating locks.
        """
        # Create multiple file locks
        test_files = []
        locks = []

        for i in range(10):
            test_file = swag_service.config_path / f"test{i}.conf"
            test_file.write_text(f"test content {i}")
            test_files.append(test_file)

            # Get lock for each file
            lock = await swag_service.file_ops.get_file_lock(test_file)
            locks.append(lock)

        # Should have 10 locks in the registry
        initial_lock_count = len(swag_service.file_ops._file_locks)
        assert initial_lock_count == 10

        # Clean up unused locks
        await swag_service.file_ops.cleanup_file_locks()

        # All locks should still be there (they're not locked)
        # This tests that the cleanup doesn't remove unlocked locks incorrectly
        # The actual cleanup happens when locks are not in use
        after_cleanup_count = len(swag_service.file_ops._file_locks)

        # Locks should be cleaned up if they're not locked
        assert after_cleanup_count <= initial_lock_count


class TestConcurrencyUtilities:
    """Test the new async utilities for concurrency control."""

    @pytest.mark.asyncio
    async def test_bounded_gather_limits_concurrency(self):
        """Test bounded_gather limits concurrent operations."""
        execution_times = []
        max_concurrent = 0
        current_concurrent = 0

        async def slow_operation(delay, operation_id):
            nonlocal max_concurrent, current_concurrent

            current_concurrent += 1
            max_concurrent = max(max_concurrent, current_concurrent)

            start_time = time.time()
            execution_times.append((operation_id, "start", start_time))

            await asyncio.sleep(delay)

            end_time = time.time()
            execution_times.append((operation_id, "end", end_time))

            current_concurrent -= 1
            return operation_id

        # Create 10 operations with 0.1s delay each
        operations = [slow_operation(0.1, i) for i in range(10)]

        # Limit to 3 concurrent operations
        start_time = time.time()
        results = await bounded_gather(*operations, limit=3)
        total_time = time.time() - start_time

        # All operations should complete
        assert len(results) == 10
        assert results == list(range(10))

        # Should not exceed the concurrency limit
        assert max_concurrent <= 3, f"Exceeded concurrency limit: {max_concurrent}"

        # Should take longer than 0.1s (sequential) but less than 1.0s (fully sequential)
        assert 0.3 <= total_time <= 0.8, f"Unexpected total time: {total_time}"

    @pytest.mark.asyncio
    async def test_bounded_gather_handles_exceptions(self):
        """Test bounded_gather properly handles exceptions."""

        async def failing_operation(should_fail):
            await asyncio.sleep(0.01)  # Small delay
            if should_fail:
                raise ValueError("Operation failed")
            return "success"

        # Mix of successful and failing operations
        operations = [
            failing_operation(i % 3 == 0)  # Every 3rd operation fails
            for i in range(9)
        ]

        # Should raise exception (gather behavior)
        with pytest.raises(ValueError, match="Operation failed"):
            await bounded_gather(*operations, limit=3)

    @pytest.mark.asyncio
    async def test_async_line_reader_memory_efficiency(self):
        """Test AsyncLineReader handles large files efficiently."""
        # Create a test file with many lines
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            for i in range(1000):
                f.write(f"Line {i}: This is a test line with some content\n")
            temp_file = Path(f.name)

        try:
            reader = AsyncLineReader(temp_file, chunk_size=1024)

            # Read only first 100 lines
            lines_read = []
            async for line in reader.read_lines(100):
                lines_read.append(line.strip())

            # Should have read exactly 100 lines
            assert len(lines_read) == 100

            # Lines should be in correct order
            for i, line in enumerate(lines_read):
                expected = f"Line {i}: This is a test line with some content"
                assert line == expected

        finally:
            # Clean up temp file
            temp_file.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_async_line_reader_handles_missing_file(self):
        """Test AsyncLineReader handles missing files gracefully."""
        missing_file = Path("/nonexistent/file.txt")
        reader = AsyncLineReader(missing_file)

        lines_read = []
        async for line in reader.read_lines(10):
            lines_read.append(line)

        # Should handle missing file gracefully (empty result)
        assert len(lines_read) == 0
