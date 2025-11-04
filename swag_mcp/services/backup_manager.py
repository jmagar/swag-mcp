"""Backup management module for SWAG MCP."""

import asyncio
import errno
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles

from swag_mcp.core.config import config
from swag_mcp.utils.error_handlers import handle_os_error
from swag_mcp.utils.validators import detect_and_handle_encoding, validate_config_filename

logger = logging.getLogger(__name__)


class BackupManager:
    """Handles backup creation and cleanup."""

    def __init__(self, config_path: Path, file_ops: Any) -> None:
        """Initialize backup manager.

        Args:
            config_path: Path to the configuration directory
            file_ops: FileOperations instance for safe file operations

        """
        self.config_path = config_path
        self.file_ops = file_ops

        # Initialize asyncio locks for concurrent operation safety
        self._backup_lock = asyncio.Lock()  # Protects backup creation operations
        self._cleanup_lock = asyncio.Lock()  # Protects cleanup operations

    async def create_backup(self, config_name: str) -> str:
        """Create timestamped backup of configuration file with proper locking."""
        # Security validation: ensure config name is safe (should already be validated by caller)
        validated_name = validate_config_filename(config_name)

        config_file = self.config_path / validated_name

        # Use both global backup lock and per-file lock for safety
        async with self._backup_lock:
            file_lock = await self.file_ops.get_file_lock(config_file)
            async with file_lock:
                # Generate timestamp inside the lock to ensure uniqueness
                timestamp = datetime.now().strftime(
                    "%Y%m%d_%H%M%S_%f"
                )  # Include microseconds for uniqueness

                # Add UUID fallback for atomic backup creation to prevent race conditions
                import uuid

                uuid_suffix = uuid.uuid4().hex[:8]
                backup_name = f"{validated_name}.backup.{timestamp}_{uuid_suffix}"
                backup_file = self.config_path / backup_name

                # Double-check that backup doesn't already exist (extra safety)
                counter = 0
                original_backup_name = backup_name
                while backup_file.exists() and counter < 1000:  # Prevent infinite loop
                    counter += 1
                    backup_name = f"{original_backup_name}.{counter}"
                    backup_file = self.config_path / backup_name

                if counter >= 1000:
                    raise OSError(
                        errno.EEXIST, "Could not generate unique backup name after 1000 attempts"
                    )

                # Read original content with error handling and Unicode normalization
                try:
                    # Read file with proper encoding detection and Unicode normalization
                    async with aiofiles.open(config_file, "rb") as src:
                        raw_content = await src.read()

                    # Detect encoding and normalize Unicode
                    content = detect_and_handle_encoding(raw_content)

                except OSError as e:
                    handle_os_error(e, "reading configuration file for backup", validated_name)
                except (ValueError, UnicodeDecodeError) as e:
                    raise ValueError(
                        f"Configuration file has invalid text encoding or Unicode characters "
                        f"for backup: {validated_name}: {str(e)}"
                    ) from e
                except Exception as e:
                    raise OSError(
                        errno.EIO,
                        (
                            f"Unexpected error reading configuration file for backup: "
                            f"{validated_name}: {str(e)}"
                        ),
                    ) from e

                # Write backup safely with proper error handling
                # (no lock since we're already in one)
                await self.file_ops.safe_write_file(
                    backup_file, content, f"backup creation for {backup_name}", use_lock=False
                )

                return backup_name

    async def list_backups(self) -> list[dict[str, Any]]:
        """List all backup files with metadata."""
        from swag_mcp.core.constants import BACKUP_MARKER

        logger.info("Listing all backup files")
        backup_files = []
        backup_pattern = "*" + BACKUP_MARKER + "*"

        try:
            for backup_path in self.config_path.glob(backup_pattern):
                if backup_path.is_file():
                    stat = backup_path.stat()

                    # Extract original config name from backup filename
                    original_config = backup_path.name.split(BACKUP_MARKER)[0]
                    # Only append .conf if it's missing both .conf and .conf.sample
                    if (
                        not original_config.endswith(".conf")
                        and not original_config.endswith(".conf.sample")
                    ):
                        original_config += ".conf"

                    backup_files.append(
                        {
                            "name": backup_path.name,
                            "size_bytes": stat.st_size,
                            "modified_time": stat.st_mtime,
                            "original_config": original_config,
                        }
                    )
        except OSError as e:
            logger.warning(f"Error scanning backup files: {e}")
            return []

        # Sort by modification time, newest first
        return sorted(backup_files, key=lambda x: x["modified_time"], reverse=True)

    async def cleanup_old_backups(self, retention_days: int | None = None) -> int:
        """Clean up old backup files beyond retention period with proper concurrency control."""
        if retention_days is None:
            retention_days = config.backup_retention_days

        logger.info(f"Cleaning up backups older than {retention_days} days")

        # Use cleanup lock to prevent multiple cleanup operations
        # and coordinate with backup creation
        # Fix: Implement ordered locking to prevent deadlock
        async with self._cleanup_lock, self._backup_lock:
            cutoff_time = datetime.now().timestamp() - (retention_days * 24 * 60 * 60)
            cleaned_count = 0

            # Enhanced pattern: filename.backup.YYYYMMDD_HHMMSS_microseconds_uuid
            # This matches our improved backup naming scheme
            backup_pattern = re.compile(r"^.+\.backup\.\d{8}_\d{6}_\d{6}_[a-f0-9]{8}$")

            # Get list of backup files first (snapshot in time to avoid race conditions)
            backup_candidates = []
            try:
                for backup_file in self.config_path.glob("*.backup.*"):
                    if backup_file.is_file():
                        backup_candidates.append(backup_file)
            except OSError as e:
                logger.warning(f"Error scanning backup files: {e}")
                return 0

            # Process each candidate backup file
            for backup_file in backup_candidates:
                try:
                    # Double-check file still exists (another process might have cleaned it)
                    if not backup_file.exists():
                        continue

                    # Additional safety checks:
                    # 1. Must match our exact timestamp format
                    # 2. Must be a regular file (not directory)
                    # 3. Must be older than retention period
                    # 4. Must not be currently being written (check for temp files)

                    if not backup_pattern.match(backup_file.name):
                        logger.debug(f"Skipping file (wrong format): {backup_file.name}")
                        continue

                    if not backup_file.is_file():
                        logger.debug(f"Skipping non-file: {backup_file.name}")
                        continue

                    # Check if file is currently being written (has corresponding temp file)
                    temp_file = backup_file.with_suffix(f"{backup_file.suffix}.tmp.{os.getpid()}")
                    if temp_file.exists():
                        logger.debug(f"Skipping backup being written: {backup_file.name}")
                        continue

                    # Check modification time
                    try:
                        file_stat = backup_file.stat()
                        if file_stat.st_mtime >= cutoff_time:
                            continue  # File is not old enough to delete
                    except OSError as e:
                        logger.debug(f"Could not get stats for {backup_file.name}: {e}")
                        continue

                    # Check if file is currently locked by getting its lock (non-blocking)
                    file_lock = await self.file_ops.get_file_lock(backup_file)
                    if file_lock.locked():
                        logger.debug(f"Skipping locked backup file: {backup_file.name}")
                        continue

                    # Attempt to acquire lock briefly for deletion
                    try:
                        # Use asyncio.wait_for to timeout if lock can't be acquired
                        # quickly
                        async with asyncio.timeout(1.0):  # 1 second timeout
                            async with file_lock:
                                # Double-check file still exists and meets criteria
                                if (
                                    backup_file.exists()
                                    and backup_file.is_file()
                                    and backup_file.stat().st_mtime < cutoff_time
                                ):
                                    logger.debug(f"Deleting old backup: {backup_file.name}")
                                    backup_file.unlink()
                                    cleaned_count += 1

                    except TimeoutError:
                        logger.debug(f"Timeout acquiring lock for cleanup of {backup_file.name}")
                        continue
                    except (PermissionError, OSError) as e:
                        logger.warning(f"Failed to delete backup {backup_file.name}: {e}")
                        continue
                    except Exception as e:
                        logger.warning(
                            f"Unexpected error cleaning up backup {backup_file.name}: {e}"
                        )
                        continue

                except Exception as e:
                    logger.warning(f"Error processing backup file {backup_file}: {e}")
                    continue

            logger.info(f"Cleaned up {cleaned_count} old backup files")
            return cleaned_count
