"""MCP-specific caching utilities for performance optimization."""

import asyncio
import hashlib
import logging
import re
import time
from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import lru_cache, wraps
from re import Pattern
from typing import Any

logger = logging.getLogger(__name__)


class MCPCache:
    """Thread-safe cache with TTL support optimized for MCP operations.

    This cache is designed to optimize frequently accessed SWAG configuration
    data while maintaining consistency and providing automatic cleanup.
    """

    def __init__(self, default_ttl: int = 300, max_size: int = 1000):
        """Initialize MCP cache.

        Args:
            default_ttl: Default time-to-live in seconds
            max_size: Maximum number of cache entries

        """
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._cache: dict[str, dict[str, Any]] = {}
        self._timestamps: dict[str, float] = {}
        self._access_times: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], Awaitable[Any]],
        ttl: int | None = None
    ) -> Any:
        """Get cached value or compute and cache new value.

        Args:
            key: Cache key
            factory: Async function to compute value if not cached
            ttl: Time-to-live override

        Returns:
            Cached or computed value

        """
        async with self._lock:
            # Check if key exists and hasn't expired
            if key in self._cache:
                age = time.time() - self._timestamps[key]
                ttl_to_use = ttl or self.default_ttl

                if age < ttl_to_use:
                    # Update access time for LRU
                    self._access_times[key] = time.time()
                    logger.debug(f"Cache hit for key: {key}")
                    return self._cache[key]["value"]
                else:
                    # Expired, remove from cache
                    logger.debug(f"Cache expired for key: {key}")
                    await self._remove_key(key)

            # Not in cache or expired, compute new value
            logger.debug(f"Cache miss for key: {key}, computing value")
            try:
                value = await factory()
                await self._set_value(key, value, ttl)
                return value
            except Exception as e:
                logger.error(f"Error computing cache value for key {key}: {e}")
                raise

    async def _set_value(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Set cache value with TTL and LRU management."""
        # Enforce max size with LRU eviction
        if len(self._cache) >= self.max_size:
            await self._evict_lru()

        current_time = time.time()
        self._cache[key] = {"value": value, "ttl": ttl or self.default_ttl}
        self._timestamps[key] = current_time
        self._access_times[key] = current_time

    async def _remove_key(self, key: str) -> None:
        """Remove key from all cache structures."""
        self._cache.pop(key, None)
        self._timestamps.pop(key, None)
        self._access_times.pop(key, None)

    async def _evict_lru(self) -> None:
        """Evict least recently used item."""
        if not self._access_times:
            return

        lru_key = min(self._access_times.items(), key=lambda x: x[1])[0]
        logger.debug(f"Evicting LRU key: {lru_key}")
        await self._remove_key(lru_key)

    async def get(self, key: str) -> Any | None:
        """Get value from cache if exists and not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired

        """
        async with self._lock:
            if key not in self._cache:
                return None

            age = time.time() - self._timestamps[key]
            ttl = self._cache[key]["ttl"]

            if age >= ttl:
                await self._remove_key(key)
                return None

            # Update access time for LRU
            self._access_times[key] = time.time()
            return self._cache[key]["value"]

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None
    ) -> None:
        """Set cache value.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live override

        """
        async with self._lock:
            await self._set_value(key, value, ttl)

    async def invalidate(self, pattern: str | Pattern | None = None) -> int:
        """Invalidate cache entries matching pattern.

        Args:
            pattern: String pattern or regex to match keys for invalidation

        Returns:
            Number of entries invalidated

        """
        async with self._lock:
            if pattern is None:
                # Clear all entries
                count = len(self._cache)
                self._cache.clear()
                self._timestamps.clear()
                self._access_times.clear()
                logger.info(f"Cache cleared: {count} entries removed")
                return count

            # Pattern matching
            if isinstance(pattern, str):
                # Convert string pattern to regex
                regex_pattern = re.compile(pattern.replace("*", ".*"))
            else:
                regex_pattern = pattern

            keys_to_remove = [
                key for key in self._cache
                if regex_pattern.search(key)
            ]

            for key in keys_to_remove:
                await self._remove_key(key)

            logger.info(f"Cache invalidation: {len(keys_to_remove)} entries removed")
            return len(keys_to_remove)

    async def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed

        """
        async with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, timestamp in self._timestamps.items()
                if current_time - timestamp >= self._cache[key]["ttl"]
            ]

            for key in expired_keys:
                await self._remove_key(key)

            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

            return len(expired_keys)

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats

        """
        current_time = time.time()
        total_entries = len(self._cache)
        expired_entries = sum(
            1 for key, timestamp in self._timestamps.items()
            if current_time - timestamp >= self._cache[key]["ttl"]
        )

        return {
            "total_entries": total_entries,
            "active_entries": total_entries - expired_entries,
            "expired_entries": expired_entries,
            "max_size": self.max_size,
            "default_ttl": self.default_ttl,
        }


# Global cache instance for SWAG configuration data
_global_cache: MCPCache | None = None


def get_cache() -> MCPCache:
    """Get or create global cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = MCPCache(default_ttl=300, max_size=1000)
    return _global_cache


def cache_key_for_list(filter_type: str, timestamp: int | None = None) -> str:
    """Generate cache key for list operations.

    Args:
        filter_type: Type of filter used
        timestamp: Optional timestamp for cache busting

    Returns:
        Cache key string

    """
    if timestamp is None:
        # Use current minute as timestamp to provide reasonable caching
        timestamp = int(time.time() // 60) * 60
    return f"list:{filter_type}:{timestamp}"


def cache_key_for_config(config_name: str, operation: str = "view") -> str:
    """Generate cache key for configuration operations.

    Args:
        config_name: Configuration file name
        operation: Operation type

    Returns:
        Cache key string

    """
    return f"config:{operation}:{config_name}"


def cached_result(
    ttl: int = 300, key_func: Callable | None = None
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Cache async function results with configurable TTL.

    Args:
        ttl: Time-to-live in seconds
        key_func: Function to generate cache key from args

    Returns:
        Decorated function

    """
    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache = get_cache()

            # Generate cache key
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                # Default key generation
                key_parts = [func.__name__]
                key_parts.extend(str(arg) for arg in args[:3])  # Limit to first 3 args
                key = ":".join(key_parts)

                # Add hash of kwargs if present
                if kwargs:
                    kwargs_str = str(sorted(kwargs.items()))
                    kwargs_hash = hashlib.md5(kwargs_str.encode()).hexdigest()[:8]
                    key = f"{key}:{kwargs_hash}"

            # Try to get from cache or compute
            async def compute() -> Any:
                return await func(*args, **kwargs)

            return await cache.get_or_set(key, compute, ttl)

        return wrapper
    return decorator


# LRU cache for frequently accessed static data
@lru_cache(maxsize=128)
def get_cached_template_data(template_name: str, checksum: str) -> dict[str, Any]:
    """Cache template data with checksum validation.

    Args:
        template_name: Name of template
        checksum: File checksum for cache invalidation

    Returns:
        Template metadata

    """
    return {
        "template_name": template_name,
        "checksum": checksum,
        "cached_at": datetime.now().isoformat(),
    }


async def invalidate_config_cache(config_name: str) -> None:
    """Invalidate all cache entries for a specific configuration.

    Args:
        config_name: Configuration file name

    """
    cache = get_cache()
    pattern = f"config:*:{config_name}"
    invalidated = await cache.invalidate(pattern)
    logger.debug(f"Invalidated {invalidated} cache entries for {config_name}")


async def invalidate_list_cache() -> None:
    """Invalidate all list operation cache entries."""
    cache = get_cache()
    invalidated = await cache.invalidate("list:*")
    logger.debug(f"Invalidated {invalidated} list cache entries")


# Automatic cleanup task
class CacheCleanupTask:
    """Background task for automatic cache cleanup."""

    def __init__(self, interval: int = 300):  # 5 minutes
        """Initialize cache cleanup task with specified interval."""
        self.interval = interval
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        """Start the cleanup task."""
        if self._task is not None:
            return

        self._task = asyncio.create_task(self._cleanup_loop())
        logger.info("Started cache cleanup task")

    async def stop(self) -> None:
        """Stop the cleanup task."""
        if self._task is None:
            return

        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except TimeoutError:
            self._task.cancel()

        self._task = None
        logger.info("Stopped cache cleanup task")

    async def _cleanup_loop(self) -> None:
        """Execute main cache cleanup loop."""
        cache = get_cache()

        while not self._stop_event.is_set():
            try:
                expired_count = await cache.cleanup_expired()
                if expired_count > 0:
                    stats = cache.get_stats()
                    logger.debug(f"Cache cleanup: {expired_count} expired, "
                               f"{stats['active_entries']} active entries")

                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.interval
                )
            except TimeoutError:
                continue  # Normal timeout, continue cleanup loop
            except Exception as e:
                logger.error(f"Error in cache cleanup task: {e}")
                await asyncio.sleep(60)  # Wait before retrying


# Global cleanup task instance
_cleanup_task: CacheCleanupTask | None = None


async def start_cache_cleanup() -> None:
    """Start automatic cache cleanup."""
    global _cleanup_task
    if _cleanup_task is None:
        _cleanup_task = CacheCleanupTask()
    await _cleanup_task.start()


async def stop_cache_cleanup() -> None:
    """Stop automatic cache cleanup."""
    global _cleanup_task
    if _cleanup_task is not None:
        await _cleanup_task.stop()
