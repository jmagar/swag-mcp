"""Async utilities for enhanced performance and concurrency control."""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

import aiofiles

logger = logging.getLogger(__name__)
T = TypeVar('T')


async def bounded_gather(*coros: Awaitable[T], limit: int = 10) -> list[T]:
    """Execute coroutines with concurrency limit to prevent resource exhaustion.

    Args:
        *coros: Coroutines to execute
        limit: Maximum number of concurrent operations

    Returns:
        List of results in the same order as input coroutines

    Example:
        >>> async def fetch_data(url): ...
        >>> results = await bounded_gather(
        ...     *[fetch_data(url) for url in urls],
        ...     limit=5
        ... )

    """
    if not coros:
        return []

    semaphore = asyncio.Semaphore(limit)

    async def bounded_coro(coro: Awaitable[T]) -> T:
        async with semaphore:
            return await coro

    try:
        return await asyncio.gather(*[bounded_coro(coro) for coro in coros])
    except Exception as e:
        logger.error(f"Error in bounded_gather: {e}")
        raise


class AsyncLineReader:
    """Memory-efficient async line reader for large files.

    This class provides an async iterator that reads files line by line
    without loading the entire file into memory, making it suitable for
    processing large log files or configuration files.
    """

    def __init__(self, file_path: Path, chunk_size: int = 8192):
        """Initialize async line reader.

        Args:
            file_path: Path to the file to read
            chunk_size: Size of chunks to read at once (default: 8KB)

        """
        self.file_path = file_path
        self.chunk_size = chunk_size

    async def read_lines(self, max_lines: int) -> AsyncIterator[str]:
        """Async iterator for memory-efficient line reading.

        Args:
            max_lines: Maximum number of lines to read

        Yields:
            Individual lines from the file

        Example:
            >>> reader = AsyncLineReader(Path("/var/log/nginx/error.log"))
            >>> async for line in reader.read_lines(100):
            ...     if "ERROR" in line:
            ...         print(line.strip())

        """
        if not self.file_path.exists():
            logger.warning(f"File not found: {self.file_path}")
            return

        lines_read = 0

        try:
            async with aiofiles.open(self.file_path, encoding='utf-8', errors='replace') as f:
                buffer = ""

                while lines_read < max_lines:
                    chunk = await f.read(self.chunk_size)
                    if not chunk:
                        # Handle last line if buffer has content
                        if buffer and lines_read < max_lines:
                            yield buffer + '\n'
                            lines_read += 1
                        break

                    buffer += chunk

                    while '\n' in buffer and lines_read < max_lines:
                        line, buffer = buffer.split('\n', 1)
                        yield line + '\n'
                        lines_read += 1

                    # Yield control to event loop periodically
                    await asyncio.sleep(0)

        except (OSError, UnicodeDecodeError) as e:
            logger.error(f"Error reading file {self.file_path}: {e}")
            raise


class AsyncResourceManager:
    """Context manager for handling multiple async resources.

    Provides a way to manage multiple async resources (like HTTP sessions,
    file handles, etc.) with proper cleanup even if exceptions occur.
    """

    def __init__(self) -> None:
        """Initialize async resource manager with empty resource list."""
        self._resources: list[tuple] = []
        self._entered = False

    def add_resource(self, resource: Any, cleanup_method: str = '__aexit__') -> None:
        """Add a resource to be managed.

        Args:
            resource: The async resource to manage
            cleanup_method: Name of the cleanup method (default: '__aexit__')

        """
        self._resources.append((resource, cleanup_method))

    async def __aenter__(self) -> list[Any]:
        """Enter all resources."""
        entered_resources = []

        try:
            for resource, _ in self._resources:
                if hasattr(resource, '__aenter__'):
                    entered_resource = await resource.__aenter__()
                    entered_resources.append(entered_resource)
                else:
                    entered_resources.append(resource)

            self._entered = True
            return entered_resources

        except Exception:
            # Clean up any resources that were successfully entered
            for i, resource in enumerate(entered_resources):
                try:
                    cleanup_method = self._resources[i][1]
                    if hasattr(resource, cleanup_method):
                        cleanup_func = getattr(resource, cleanup_method)
                        if asyncio.iscoroutinefunction(cleanup_func):
                            await cleanup_func(None, None, None)
                        else:
                            cleanup_func()
                except Exception as cleanup_error:
                    logger.warning(
                        f"Error cleaning up resource during failed enter: {cleanup_error}"
                    )
            raise

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit all resources in reverse order."""
        if not self._entered:
            return

        # Clean up in reverse order
        for resource, cleanup_method in reversed(self._resources):
            try:
                if hasattr(resource, cleanup_method):
                    cleanup_func = getattr(resource, cleanup_method)
                    if asyncio.iscoroutinefunction(cleanup_func):
                        await cleanup_func(exc_type, exc_val, exc_tb)
                    else:
                        cleanup_func()
            except Exception as cleanup_error:
                logger.warning(f"Error cleaning up resource: {cleanup_error}")


async def with_timeout_and_fallback(
    coro: Awaitable[T],
    timeout_seconds: float,
    fallback_value: T | None = None
) -> T | None:
    """Execute coroutine with timeout and fallback value.

    Args:
        coro: Coroutine to execute
        timeout_seconds: Timeout in seconds
        fallback_value: Value to return if timeout occurs

    Returns:
        Result of coroutine or fallback value

    Example:
        >>> result = await with_timeout_and_fallback(
        ...     slow_operation(),
        ...     timeout_seconds=5.0,
        ...     fallback_value="default"
        ... )

    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except TimeoutError:
        logger.warning(f"Operation timed out after {timeout_seconds}s, using fallback")
        return fallback_value
    except Exception as e:
        logger.error(f"Operation failed: {e}")
        raise


async def retry_with_backoff(
    coro_factory: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_multiplier: float = 2.0,
    max_delay: float = 60.0
) -> T:
    """Retry coroutine with exponential backoff.

    Args:
        coro_factory: Function that returns a coroutine to execute
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries in seconds
        backoff_multiplier: Multiplier for delay after each retry
        max_delay: Maximum delay between retries

    Returns:
        Result of successful coroutine execution

    Raises:
        Exception: The last exception if all retries fail

    Example:
        >>> async def flaky_operation():
        ...     # Some operation that might fail
        ...     pass
        >>>
        >>> result = await retry_with_backoff(
        ...     lambda: flaky_operation(),
        ...     max_retries=3
        ... )

    """
    last_exception: Exception | None = None
    delay = initial_delay

    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except Exception as e:
            last_exception = e

            if attempt == max_retries:
                logger.error(f"All {max_retries} retry attempts failed. Last error: {e}")
                break

            logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.1f}s")
            await asyncio.sleep(delay)
            delay = min(delay * backoff_multiplier, max_delay)

    if last_exception is not None:
        raise last_exception
    else:
        raise RuntimeError("Retry failed without exception")
