"""Backup management module for SWAG MCP."""

import asyncio
import errno
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from re import Pattern
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from swag_mcp.services.file_operations import FileOperations

from swag_mcp.services.filesystem import FilesystemBackend
from swag_mcp.utils.validators import validate_config_filename

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _BackupCleanupCandidate:
    """Backup file metadata captured during cleanup scanning."""

    filename: str
    path: str
    stat: Any


class BackupManager:
    """Handles backup creation and cleanup."""

    def __init__(
        self,
        config_path: Path,
        file_ops: "FileOperations",
        backup_retention_days: int,
    ) -> None:
        """Initialize backup manager.

        Args:
            config_path: Path to the configuration directory
            file_ops: FileOperations instance for safe file operations
            backup_retention_days: Default retention period for cleanup

        """
        self.config_path = config_path
        self.file_ops = file_ops
        self.backup_retention_days = backup_retention_days

        # Initialize asyncio locks for concurrent operation safety
        self._backup_lock = asyncio.Lock()  # Protects backup creation operations
        self._cleanup_lock = asyncio.Lock()  # Protects cleanup operations

    @property
    def fs(self) -> FilesystemBackend:
        """Access the filesystem backend."""
        return self.file_ops.fs

    async def create_backup(self, config_name: str, content: str | None = None) -> str:
        """Create timestamped backup of configuration file with proper locking.

        Args:
            config_name: Name of the configuration file to back up
            content: Pre-read content to avoid double file reads. If None, reads from disk.

        """
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
                while (
                    await self.fs.exists(str(backup_file)) and counter < 1000
                ):  # Prevent infinite loop
                    counter += 1
                    backup_name = f"{original_backup_name}.{counter}"
                    backup_file = self.config_path / backup_name

                if counter >= 1000:
                    raise OSError(
                        errno.EEXIST, "Could not generate unique backup name after 1000 attempts"
                    )

                # Use pre-read content if provided, otherwise read from disk
                if content is None:
                    content = await self.file_ops.read_text_safe(
                        str(config_file), f"configuration file {validated_name}"
                    )

                # Write backup safely with proper error handling
                # (no lock since we're already in one)
                await self.file_ops.safe_write_file(
                    backup_file, content, f"backup creation for {backup_name}", use_lock=False
                )

                return backup_name

    async def list_backups(self, offset: int = 0, limit: int | None = None) -> list[dict[str, Any]]:
        """List backup files with metadata and optional pagination."""
        from swag_mcp.core.constants import BACKUP_MARKER

        if offset < 0:
            raise ValueError("offset must be greater than or equal to 0")
        if limit is not None and limit < 1:
            raise ValueError("limit must be greater than or equal to 1")

        logger.info("Listing all backup files")
        backup_files = []
        backup_pattern = "*" + BACKUP_MARKER + "*"

        try:
            filenames = await self.fs.glob(str(self.config_path), backup_pattern)
            for filename in filenames:
                full_path = str(self.config_path / filename)
                if await self.fs.is_file(full_path):
                    stat = await self.fs.stat(full_path)

                    # Extract original config name from backup filename
                    original_config = filename.split(BACKUP_MARKER)[0]
                    # Only append .conf if it's missing both .conf and .conf.sample
                    if not original_config.endswith(".conf") and not original_config.endswith(
                        ".conf.sample"
                    ):
                        original_config += ".conf"

                    backup_files.append(
                        {
                            "name": filename,
                            "size_bytes": stat.st_size,
                            "modified_time": stat.st_mtime,
                            "original_config": original_config,
                        }
                    )
        except OSError as e:
            logger.warning(f"Error scanning backup files: {e}")
            return []

        # Sort by modification time, newest first, then name for deterministic paging.
        sorted_backups = sorted(
            backup_files,
            key=lambda x: (x["modified_time"], x["name"]),
            reverse=True,
        )
        if limit is not None:
            return sorted_backups[offset : offset + limit]
        if offset:
            return sorted_backups[offset:]
        return sorted_backups

    async def cleanup_old_backups(self, retention_days: int | None = None) -> int:
        """Clean up old backup files beyond retention period with proper concurrency control."""
        if retention_days is None:
            retention_days = self.backup_retention_days

        logger.info(f"Cleaning up backups older than {retention_days} days")

        # Use cleanup lock to prevent multiple cleanup operations
        # and coordinate with backup creation
        # Fix: Implement ordered locking to prevent deadlock
        async with self._cleanup_lock, self._backup_lock:
            cutoff_time = datetime.now().timestamp() - (retention_days * 24 * 60 * 60)
            cleaned_count = 0

            backup_candidates = await self._scan_backup_candidates()

            # Process each candidate backup file
            for candidate in backup_candidates:
                if await self._delete_backup_candidate(candidate, cutoff_time):
                    cleaned_count += 1

            logger.info(f"Cleaned up {cleaned_count} old backup files")
            return cleaned_count

    def _cleanup_backup_pattern(self) -> Pattern[str]:
        """Return the accepted backup filename pattern for cleanup deletion."""
        return re.compile(r"^.+\.backup\.\d{8}_\d{6}_\d{6}_[a-f0-9]{8}(?:\.\d+)?$")

    async def _scan_backup_candidates(self) -> list[_BackupCleanupCandidate]:
        """Scan backup files and capture metadata once for cleanup processing."""
        backup_candidates: list[_BackupCleanupCandidate] = []
        try:
            filenames = await self.fs.glob(str(self.config_path), "*.backup.*")
            for filename in filenames:
                full_path = str(self.config_path / filename)
                file_stat = await self.fs.stat(full_path)
                if file_stat.is_file:
                    backup_candidates.append(
                        _BackupCleanupCandidate(filename=filename, path=full_path, stat=file_stat)
                    )
        except OSError as e:
            logger.warning(f"Error scanning backup files: {e}")
            return []

        return backup_candidates

    async def _is_backup_being_written(self, backup_file_path: str) -> bool:
        """Return whether a process-local temporary file exists for a backup."""
        backup_path_obj = Path(backup_file_path)
        exact_temp_file = backup_path_obj.with_suffix(f"{backup_path_obj.suffix}.tmp.{os.getpid()}")
        if await self.fs.exists(str(exact_temp_file)):
            return True

        temp_pattern = f"{backup_path_obj.name}.tmp.{os.getpid()}.*"
        return bool(await self.fs.glob(str(backup_path_obj.parent), temp_pattern))

    async def _delete_backup_candidate(
        self,
        candidate: _BackupCleanupCandidate,
        cutoff_time: float,
    ) -> bool:
        """Delete one cleanup candidate when it still meets all safety checks."""
        try:
            if not await self.fs.exists(candidate.path):
                return False

            if not self._cleanup_backup_pattern().match(candidate.filename):
                logger.debug(f"Skipping file (wrong format): {candidate.filename}")
                return False

            if not candidate.stat.is_file:
                logger.debug(f"Skipping non-file: {candidate.filename}")
                return False

            if await self._is_backup_being_written(candidate.path):
                logger.debug(f"Skipping backup being written: {candidate.filename}")
                return False

            if candidate.stat.st_mtime >= cutoff_time:
                return False

            file_lock = await self.file_ops.get_file_lock(Path(candidate.path))
            if file_lock.locked():
                logger.debug(f"Skipping locked backup file: {candidate.filename}")
                return False

            try:
                async with asyncio.timeout(1.0):
                    async with file_lock:
                        current_stat = await self.fs.stat(candidate.path)
                        if (
                            await self.fs.exists(candidate.path)
                            and current_stat.is_file
                            and current_stat.st_mtime < cutoff_time
                        ):
                            logger.debug(f"Deleting old backup: {candidate.filename}")
                            await self.fs.unlink(candidate.path)
                            return True
            except TimeoutError:
                logger.debug(f"Timeout acquiring lock for cleanup of {candidate.filename}")
                return False
            except FileNotFoundError:
                logger.debug(f"Backup disappeared during cleanup: {candidate.filename}")
                return False
            except (PermissionError, OSError) as e:
                logger.warning(f"Failed to delete backup {candidate.filename}: {e}")
                return False
            except Exception as e:
                logger.warning(f"Unexpected error cleaning up backup {candidate.filename}: {e}")
                return False
        except Exception as e:
            logger.warning(f"Error processing backup file {candidate.filename}: {e}")
            return False

        return False
