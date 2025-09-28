"""MCP streaming utilities for large responses and real-time data."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Any

from swag_mcp.core.config import config
from swag_mcp.utils.async_utils import AsyncLineReader

logger = logging.getLogger(__name__)


class StreamingResponse:
    """Base class for streaming responses with chunking support."""

    def __init__(self, chunk_size: int = 8192):
        """Initialize streaming response with specified chunk size."""
        self.chunk_size = chunk_size

    async def stream_text(self, text: str) -> AsyncIterator[str]:
        """Stream text content in chunks.

        Args:
            text: Text content to stream

        Yields:
            Text chunks

        """
        for i in range(0, len(text), self.chunk_size):
            chunk = text[i:i + self.chunk_size]
            yield chunk
            # Small delay to prevent overwhelming the client
            await asyncio.sleep(0.001)


class ConfigurationStreamer(StreamingResponse):
    """Streamer for large configuration files."""

    async def stream_config_content(self, config_name: str) -> AsyncIterator[str]:
        """Stream configuration file content.

        Args:
            config_name: Configuration file name

        Yields:
            Configuration content chunks

        """
        config_path = Path(config.proxy_confs_path) / config_name

        if not config_path.exists():
            yield f"Configuration file '{config_name}' not found"
            return

        try:
            reader = AsyncLineReader(config_path, chunk_size=self.chunk_size)

            # Stream file header
            yield f"# Configuration: {config_name}\n"
            yield f"# File size: {config_path.stat().st_size} bytes\n"
            yield f"# Last modified: {datetime.fromtimestamp(config_path.stat().st_mtime)}\n"
            yield "# Content:\n\n"

            # Stream file content line by line
            async for line in reader.read_lines(max_lines=10000):
                if line:
                    yield line

        except Exception as e:
            logger.error(f"Error streaming config {config_name}: {e}")
            yield f"\nError reading configuration: {str(e)}"

    async def stream_multiple_configs(
        self, config_names: list[str]
    ) -> AsyncIterator[str]:
        """Stream multiple configuration files with separators.

        Args:
            config_names: List of configuration file names

        Yields:
            Combined configuration content with separators

        """
        for i, config_name in enumerate(config_names):
            if i > 0:
                yield f"\n{'=' * 80}\n"

            yield f"Configuration {i + 1}/{len(config_names)}: {config_name}\n"
            yield f"{'=' * 80}\n\n"

            async for chunk in self.stream_config_content(config_name):
                yield chunk


class LogStreamer(StreamingResponse):
    """Streamer for log files with real-time capability."""

    def __init__(self, chunk_size: int = 8192, follow: bool = False):
        """Initialize log streamer with chunk size and follow mode."""
        super().__init__(chunk_size)
        self.follow = follow

    async def stream_log_entries(
        self, log_type: str, lines: int, tail: bool = True
    ) -> AsyncIterator[str]:
        """Stream log entries with optional tail functionality.

        Args:
            log_type: Type of log to stream
            lines: Number of lines to retrieve
            tail: If True, stream from the end of file

        Yields:
            Log entry strings

        """
        try:
            # For now, simulate log streaming as the actual implementation
            # would depend on Docker container access
            yield f"# SWAG {log_type} Log Stream\n"
            yield f"# Requested lines: {lines}\n"
            yield f"# Timestamp: {datetime.now().isoformat()}\n\n"

            # Placeholder for actual log streaming implementation
            for i in range(min(lines, 100)):  # Limit for demo
                timestamp = datetime.now().isoformat()
                yield f"[{timestamp}] Sample {log_type} log entry {i + 1}\n"

                if self.follow:
                    await asyncio.sleep(0.1)  # Simulate real-time

        except Exception as e:
            logger.error(f"Error streaming {log_type} logs: {e}")
            yield f"Error streaming logs: {str(e)}\n"

    async def stream_live_logs(
        self, log_type: str, duration: int = 60
    ) -> AsyncIterator[str]:
        """Stream live logs for a specified duration.

        Args:
            log_type: Type of log to stream
            duration: Duration in seconds to stream

        Yields:
            Live log entries

        """
        start_time = asyncio.get_event_loop().time()
        end_time = start_time + duration

        yield f"# Live {log_type} log stream starting\n"
        yield f"# Duration: {duration} seconds\n\n"

        while asyncio.get_event_loop().time() < end_time:
            timestamp = datetime.now().isoformat()
            yield f"[{timestamp}] Live {log_type} entry\n"
            await asyncio.sleep(1)

        yield "\n# Live stream ended\n"


class HealthMonitorStreamer(StreamingResponse):
    """Streamer for real-time health monitoring data."""

    async def stream_health_updates(
        self, domains: list[str], interval: int = 30
    ) -> AsyncIterator[str]:
        """Stream health check updates for multiple domains.

        Args:
            domains: List of domains to monitor
            interval: Check interval in seconds

        Yields:
            Health status updates in JSON format

        """
        yield "# Health Monitor Stream\n"
        yield f"# Domains: {', '.join(domains)}\n"
        yield f"# Check interval: {interval}s\n\n"

        check_count = 0
        while True:  # Continuous monitoring
            check_count += 1
            timestamp = datetime.now().isoformat()

            yield f"## Health Check #{check_count} - {timestamp}\n"

            for domain in domains:
                # Simulate health check (replace with actual implementation)
                status = {
                    "domain": domain,
                    "timestamp": timestamp,
                    "status": "healthy",  # Placeholder
                    "response_time_ms": 150,  # Placeholder
                    "status_code": 200,  # Placeholder
                }

                yield f"{json.dumps(status, indent=2)}\n"

            yield f"\n{'=' * 60}\n"
            await asyncio.sleep(interval)


class ConfigurationWatcher:
    """Watch configuration directory for changes and stream updates."""

    def __init__(self, config_path: Path):
        """Initialize configuration watcher with target path."""
        self.config_path = Path(config_path)
        self._watchers: dict[str, Any] = {}

    async def watch_config_changes(self) -> AsyncIterator[dict[str, Any]]:
        """Watch for configuration file changes.

        Yields:
            Change events with details

        """
        # This would implement file system watching in a real scenario
        # For now, provide a simulation

        yield {
            "type": "watcher_started",
            "path": str(self.config_path),
            "timestamp": datetime.now().isoformat(),
            "message": "Configuration watcher started"
        }

        # Simulate periodic checks
        datetime.now()
        while True:
            await asyncio.sleep(10)  # Check every 10 seconds

            current_time = datetime.now()

            # Simulate finding changes
            if current_time.second % 30 == 0:  # Every 30 seconds simulate a change
                yield {
                    "type": "modified",
                    "config_name": "example.subdomain.conf",
                    "timestamp": current_time.isoformat(),
                    "details": {
                        "size_change": "+150 bytes",
                        "last_modified": current_time.isoformat()
                    }
                }



class BackupStreamer(StreamingResponse):
    """Streamer for backup operations with progress tracking."""

    async def stream_backup_progress(
        self, operation: str, files: list[str]
    ) -> AsyncIterator[str]:
        """Stream backup operation progress.

        Args:
            operation: Type of backup operation
            files: List of files being processed

        Yields:
            Progress updates

        """
        total_files = len(files)
        yield f"# Backup {operation} Progress\n"
        yield f"# Total files: {total_files}\n\n"

        for i, file_name in enumerate(files):
            progress = (i + 1) / total_files * 100

            yield f"Processing {file_name}... "
            await asyncio.sleep(0.1)  # Simulate processing time

            yield f"✓ Complete ({progress:.1f}%)\n"

            if i % 5 == 0 and i > 0:  # Progress summary every 5 files
                yield f"\n## Progress Summary: {i + 1}/{total_files} files processed\n\n"

        yield f"\n# {operation} completed successfully!\n"


# Factory functions for easy streamer creation

def create_config_streamer(chunk_size: int = 8192) -> ConfigurationStreamer:
    """Create a configuration streamer instance.

    Args:
        chunk_size: Size of chunks for streaming

    Returns:
        ConfigurationStreamer instance

    """
    return ConfigurationStreamer(chunk_size)


def create_log_streamer(
    chunk_size: int = 8192, follow: bool = False
) -> LogStreamer:
    """Create a log streamer instance.

    Args:
        chunk_size: Size of chunks for streaming
        follow: Enable real-time log following

    Returns:
        LogStreamer instance

    """
    return LogStreamer(chunk_size, follow)


def create_health_streamer(chunk_size: int = 8192) -> HealthMonitorStreamer:
    """Create a health monitor streamer instance.

    Args:
        chunk_size: Size of chunks for streaming

    Returns:
        HealthMonitorStreamer instance

    """
    return HealthMonitorStreamer(chunk_size)


def create_backup_streamer(chunk_size: int = 8192) -> BackupStreamer:
    """Create a backup streamer instance.

    Args:
        chunk_size: Size of chunks for streaming

    Returns:
        BackupStreamer instance

    """
    return BackupStreamer(chunk_size)


# Streaming response helper functions

async def stream_large_response(
    content: str, chunk_size: int = 8192
) -> AsyncIterator[str]:
    """Stream large text content in chunks.

    Args:
        content: Text content to stream
        chunk_size: Size of each chunk

    Yields:
        Content chunks

    """
    streamer = StreamingResponse(chunk_size)
    async for chunk in streamer.stream_text(content):
        yield chunk


async def stream_json_array(
    items: list[Any], chunk_size: int = 10
) -> AsyncIterator[str]:
    """Stream JSON array items in chunks.

    Args:
        items: List of items to stream
        chunk_size: Number of items per chunk

    Yields:
        JSON chunks

    """
    yield "[\n"

    for i in range(0, len(items), chunk_size):
        chunk = items[i:i + chunk_size]

        for j, item in enumerate(chunk):
            if i + j > 0:  # Not the first item overall
                yield ",\n"

            yield json.dumps(item, indent=2)

            # Small delay for large chunks
            if j % 5 == 4:
                await asyncio.sleep(0.001)

    yield "\n]"
