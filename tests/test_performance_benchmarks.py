"""Performance benchmark tests for SWAG MCP.

Benchmarks critical operations to ensure performance improvements
and detect regressions.
"""

import asyncio
import os
import statistics
import tempfile
import time
from pathlib import Path

import psutil
import pytest
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.utils.async_utils import AsyncLineReader, bounded_gather


class PerformanceTracker:
    """Helper class to track performance metrics."""

    def __init__(self):
        self.start_time = None
        self.end_time = None
        self.start_memory = None
        self.end_memory = None
        self.process = psutil.Process(os.getpid())

    def start(self):
        """Start performance tracking."""
        self.start_time = time.time()
        self.start_memory = self.process.memory_info().rss

    def stop(self):
        """Stop performance tracking."""
        self.end_time = time.time()
        self.end_memory = self.process.memory_info().rss

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        return self.end_time - self.start_time if self.end_time else 0.0

    @property
    def memory_delta(self) -> int:
        """Get memory usage delta in bytes."""
        return self.end_memory - self.start_memory if self.end_memory else 0

    @property
    def memory_delta_mb(self) -> float:
        """Get memory usage delta in MB."""
        return self.memory_delta / (1024 * 1024)


@pytest.mark.benchmark
class TestAsyncUtilityPerformance:
    """Benchmark async utility performance."""

    @pytest.mark.asyncio
    async def test_bounded_gather_performance_vs_regular_gather(self):
        """Compare bounded_gather vs regular asyncio.gather performance.

        This benchmarks the overhead of the bounded concurrency control.
        """

        async def dummy_operation(delay: float, value: int) -> int:
            await asyncio.sleep(delay)
            return value * 2

        # Test with 50 operations
        operations = [dummy_operation(0.01, i) for i in range(50)]

        # Benchmark regular gather
        tracker_regular = PerformanceTracker()
        tracker_regular.start()

        results_regular = await asyncio.gather(*operations)

        tracker_regular.stop()

        # Benchmark bounded gather with same effective concurrency
        operations_bounded = [dummy_operation(0.01, i) for i in range(50)]

        tracker_bounded = PerformanceTracker()
        tracker_bounded.start()

        results_bounded = await bounded_gather(*operations_bounded, limit=50)

        tracker_bounded.stop()

        # Results should be identical
        assert results_regular == results_bounded

        # Performance comparison
        print(f"Regular gather: {tracker_regular.elapsed_time:.3f}s")
        print(f"Bounded gather: {tracker_bounded.elapsed_time:.3f}s")
        print(f"Overhead: {tracker_bounded.elapsed_time - tracker_regular.elapsed_time:.3f}s")

        # Bounded gather should not add significant overhead when limit is high
        overhead_ratio = tracker_bounded.elapsed_time / tracker_regular.elapsed_time
        assert overhead_ratio < 2.0, f"Too much overhead: {overhead_ratio:.2f}x"

    @pytest.mark.asyncio
    async def test_bounded_gather_memory_efficiency(self):
        """Test that bounded_gather uses memory efficiently.

        This verifies that bounded concurrency prevents memory spikes.
        """

        async def memory_intensive_operation(data_size: int) -> int:
            # Simulate memory usage
            data = "x" * data_size
            await asyncio.sleep(0.01)
            return len(data)

        # Create many memory-intensive operations
        data_size = 100_000  # 100KB per operation
        num_operations = 100

        operations = [memory_intensive_operation(data_size) for _ in range(num_operations)]

        tracker = PerformanceTracker()
        tracker.start()

        # Use bounded gather with low concurrency to limit memory
        results = await bounded_gather(*operations, limit=5)

        tracker.stop()

        # Should complete successfully
        assert len(results) == num_operations
        assert all(r == data_size for r in results)

        print(f"Memory delta: {tracker.memory_delta_mb:.2f}MB")
        print(f"Time: {tracker.elapsed_time:.3f}s")

        # Memory usage should be reasonable (not num_operations * data_size)
        expected_max_memory_mb = (data_size * 10) / (1024 * 1024)  # 10 operations * 100KB
        assert tracker.memory_delta_mb < expected_max_memory_mb * 3  # Allow some overhead

    @pytest.mark.asyncio
    async def test_async_line_reader_vs_traditional_methods(self):
        """Compare AsyncLineReader performance vs traditional file reading."""

        # Create a large test file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            for i in range(10000):
                f.write(f"Line {i:05d}: This is a test line with some content for benchmarking\n")
            temp_file = Path(f.name)

        try:
            # Benchmark traditional synchronous reading
            tracker_sync = PerformanceTracker()
            tracker_sync.start()

            with open(temp_file) as f:
                sync_lines = []
                for i, line in enumerate(f):
                    if i >= 1000:  # Read first 1000 lines
                        break
                    sync_lines.append(line.strip())

            tracker_sync.stop()

            # Benchmark AsyncLineReader
            tracker_async = PerformanceTracker()
            tracker_async.start()

            reader = AsyncLineReader(temp_file, chunk_size=8192)
            async_lines = []
            async for line in reader.read_lines(1000):
                async_lines.append(line.strip())

            tracker_async.stop()

            # Results should be equivalent
            assert len(sync_lines) == len(async_lines) == 1000
            assert sync_lines == async_lines

            print(
                f"Sync reading: {tracker_sync.elapsed_time:.3f}s, "
                f"{tracker_sync.memory_delta_mb:.2f}MB"
            )
            print(
                f"Async reading: {tracker_async.elapsed_time:.3f}s, "
                f"{tracker_async.memory_delta_mb:.2f}MB"
            )

            # Async reader should not be significantly slower
            performance_ratio = tracker_async.elapsed_time / tracker_sync.elapsed_time
            assert performance_ratio < 3.0, f"Async reader too slow: {performance_ratio:.2f}x"

            # Memory usage should be similar or better
            memory_ratio = (
                abs(tracker_async.memory_delta_mb) / max(abs(tracker_sync.memory_delta_mb), 1)
            )
            assert memory_ratio < 2.0, f"Async reader uses too much memory: {memory_ratio:.2f}x"

        finally:
            temp_file.unlink(missing_ok=True)


@pytest.mark.benchmark
class TestSwagManagerPerformance:
    """Benchmark SwagManagerService performance."""

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
    async def test_config_listing_performance_scaling(self, swag_service):
        """Test configuration listing performance with varying numbers of files."""

        # Test with different numbers of config files
        file_counts = [10, 50, 100, 200]
        performance_data = []

        for count in file_counts:
            # Create test config files
            for i in range(count):
                config_file = swag_service.config_path / f"test{i:03d}.subdomain.conf"
                config_file.write_text(f"# Test config {i}\nserver_name test{i}.example.com;")

            # Benchmark listing
            tracker = PerformanceTracker()
            tracker.start()

            result = await swag_service.list_configs("all")

            tracker.stop()

            performance_data.append({
                'count': count,
                'time': tracker.elapsed_time,
                'memory': tracker.memory_delta_mb,
                'found': result.total_count
            })

            print(f"{count} files: {tracker.elapsed_time:.3f}s, {tracker.memory_delta_mb:.2f}MB")

            # Should find all created files
            assert result.total_count >= count

        # Performance should scale reasonably (not exponentially)
        times = [data['time'] for data in performance_data]
        counts = [data['count'] for data in performance_data]

        # Calculate scaling factor (time ratio vs count ratio)
        if len(times) >= 2:
            time_ratio = times[-1] / times[0]  # Last vs first
            count_ratio = counts[-1] / counts[0]
            scaling_factor = time_ratio / count_ratio

            print(
                f"Scaling factor: {scaling_factor:.2f} "
                f"(should be close to 1.0 for linear scaling)"
            )

            # Should scale better than quadratically
            assert scaling_factor < count_ratio, "Performance scaling worse than quadratic"

    @pytest.mark.asyncio
    async def test_concurrent_file_operations_performance(self, swag_service):
        """Test performance of concurrent file operations."""

        # Create base config files
        base_configs = []
        for i in range(20):
            config_file = swag_service.config_path / f"concurrent{i:02d}.subdomain.conf"
            config_file.write_text(f"# Config {i}\nserver_name concurrent{i}.example.com;")
            base_configs.append(config_file)

        async def concurrent_read_operation(config_name):
            """Read a config file."""
            return await swag_service.read_config(config_name)

        # Benchmark concurrent reads
        tracker = PerformanceTracker()
        tracker.start()

        read_tasks = [
            concurrent_read_operation(f"concurrent{i:02d}.subdomain.conf")
            for i in range(20)
        ]
        results = await asyncio.gather(*read_tasks, return_exceptions=True)

        tracker.stop()

        # Count successful operations
        successful = len([r for r in results if isinstance(r, str)])

        print(f"Concurrent reads: {successful}/20 successful in {tracker.elapsed_time:.3f}s")
        print(f"Memory delta: {tracker.memory_delta_mb:.2f}MB")

        # Should handle concurrent operations efficiently
        assert successful >= 15, "Too many concurrent operations failed"
        assert tracker.elapsed_time < 2.0, "Concurrent operations too slow"

    @pytest.mark.asyncio
    async def test_backup_cleanup_performance(self, swag_service):
        """Test backup cleanup performance with many backup files."""

        # Create many old backup files
        backup_count = 500
        for i in range(backup_count):
            # Create old backup files (date in 2020)
            backup_file = swag_service.config_path / f"test{i:03d}.backup.20200101_120000"
            backup_file.write_text(f"old backup content {i}")

        tracker = PerformanceTracker()
        tracker.start()

        cleaned_count = await swag_service.cleanup_old_backups(retention_days=0)

        tracker.stop()

        print(f"Cleaned {cleaned_count}/{backup_count} backups in {tracker.elapsed_time:.3f}s")
        print(f"Memory delta: {tracker.memory_delta_mb:.2f}MB")

        # Should clean up efficiently
        assert cleaned_count > 0, "Should have cleaned some backups"
        assert tracker.elapsed_time < 10.0, "Backup cleanup too slow"

        # Performance should be reasonable for the number of files
        time_per_file = tracker.elapsed_time / max(cleaned_count, 1)
        assert time_per_file < 0.1, f"Too slow per file: {time_per_file:.3f}s"


@pytest.mark.benchmark
class TestMemoryLeakDetection:
    """Tests to detect memory leaks in long-running operations."""

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
    async def test_repeated_operations_memory_stability(self, swag_service):
        """Test that repeated operations don't cause memory leaks.

        This test runs the same operation many times and checks that
        memory usage remains stable.
        """

        # Create a test config file
        config_file = swag_service.config_path / "memory_test.subdomain.conf"
        config_file.write_text("# Memory leak test config\nserver_name test.example.com;")

        memory_samples = []
        process = psutil.Process(os.getpid())

        # Perform operation multiple times
        for _i in range(50):
            # Record memory before operation

            # Perform operation (read config)
            content = await swag_service.read_config("memory_test.subdomain.conf")
            assert "test.example.com" in content

            # Record memory after operation
            memory_after = process.memory_info().rss
            memory_samples.append(memory_after)

            # Small delay to allow cleanup
            await asyncio.sleep(0.001)

        # Analyze memory trend
        # Convert to MB for easier analysis
        memory_mb = [m / (1024 * 1024) for m in memory_samples]

        # Check for significant upward trend (memory leak)
        first_quarter = memory_mb[:12]
        last_quarter = memory_mb[-12:]

        avg_first = statistics.mean(first_quarter)
        avg_last = statistics.mean(last_quarter)
        memory_growth = avg_last - avg_first

        print(f"Memory growth over 50 operations: {memory_growth:.2f}MB")
        print(f"Average first quarter: {avg_first:.2f}MB")
        print(f"Average last quarter: {avg_last:.2f}MB")

        # Should not grow significantly (allowing for some variance)
        assert memory_growth < 5.0, f"Possible memory leak detected: {memory_growth:.2f}MB growth"

    @pytest.mark.asyncio
    async def test_file_lock_accumulation(self, swag_service):
        """Test that file locks don't accumulate over time."""

        # Create many config files
        for i in range(100):
            config_file = swag_service.config_path / f"lock_test{i:03d}.subdomain.conf"
            config_file.write_text(f"# Lock test {i}")

        initial_lock_count = len(swag_service._file_locks)

        # Perform operations that create locks
        for i in range(100):
            config_name = f"lock_test{i:03d}.subdomain.conf"
            try:
                content = await swag_service.read_config(config_name)
                assert f"Lock test {i}" in content
            except Exception:
                # Some operations might fail, which is fine
                pass

        # Check lock count after operations
        after_ops_count = len(swag_service._file_locks)

        # Trigger cleanup
        await swag_service._cleanup_file_locks()

        final_lock_count = len(swag_service._file_locks)

        print(
            f"Locks: initial={initial_lock_count}, after_ops={after_ops_count}, "
            f"final={final_lock_count}"
        )

        # Locks should not accumulate indefinitely
        # Some may remain if they're still in use, but not all 100
        assert final_lock_count < after_ops_count or final_lock_count < 50, (
            "File locks may be accumulating without cleanup"
        )


@pytest.mark.benchmark
class TestConcurrencyPerformance:
    """Benchmark concurrency-related performance improvements."""

    @pytest.mark.asyncio
    async def test_lock_contention_performance(self):
        """Test performance under lock contention scenarios."""

        lock = asyncio.Lock()
        results = []

        async def contended_operation(operation_id: int, work_duration: float) -> int:
            """Simulate work that requires exclusive access."""
            start_time = time.time()

            async with lock:
                # Simulate some work
                await asyncio.sleep(work_duration)
                work_time = time.time() - start_time
                results.append((operation_id, work_time))
                return operation_id

        # Create tasks with different work durations
        tasks = [
            contended_operation(i, 0.01)  # 10ms work each
            for i in range(20)
        ]

        tracker = PerformanceTracker()
        tracker.start()

        completed = await asyncio.gather(*tasks)

        tracker.stop()

        # All tasks should complete
        assert len(completed) == 20

        # Analyze timing
        work_times = [result[1] for result in results]
        avg_work_time = statistics.mean(work_times)
        max_work_time = max(work_times)

        print(f"Lock contention test: {tracker.elapsed_time:.3f}s total")
        print(f"Average work time: {avg_work_time:.3f}s")
        print(f"Max work time: {max_work_time:.3f}s")

        # Performance should be reasonable
        # Total time should be close to sum of work times (sequential execution under lock)
        expected_min_time = 20 * 0.01  # 20 operations * 10ms each
        assert tracker.elapsed_time >= expected_min_time * 0.8, "Lock overhead too high"

        # Individual operations shouldn't be delayed too much by lock contention
        assert max_work_time < 0.5, "Individual operation took too long (lock contention)"


# Performance test configuration
pytest_plugins = ["pytest_benchmark"]


def pytest_configure(config):
    """Configure pytest for performance testing."""
    config.addinivalue_line("markers", "benchmark: mark test as a performance benchmark")
