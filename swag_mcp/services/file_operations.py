"""File operations module for SWAG MCP."""

import asyncio
import errno
import logging
import os
from pathlib import Path
from typing import Any

import aiofiles

from swag_mcp.utils.error_handlers import handle_os_error
from swag_mcp.utils.validators import detect_and_handle_encoding, normalize_unicode_text

logger = logging.getLogger(__name__)


class AtomicTransaction:
    """Context manager for atomic multi-file operations with rollback support."""

    def __init__(self, file_ops: "FileOperations", transaction_id: str):
        """Initialize atomic transaction.

        Args:
            file_ops: FileOperations instance
            transaction_id: Unique identifier for this transaction

        """
        self.file_ops = file_ops
        self.transaction_id = transaction_id
        self.created_files: list[Path] = []
        self.modified_files: list[tuple[Path, str]] = []  # (file_path, original_content)
        self.deleted_files: list[tuple[Path, str]] = []  # (file_path, original_content)
        self._completed = False

    async def __aenter__(self) -> "AtomicTransaction":
        """Enter async context manager and initialize transaction."""
        async with self.file_ops._transaction_lock:
            if self.transaction_id in self.file_ops._active_transactions:
                raise ValueError(f"Transaction {self.transaction_id} is already active")
            self.file_ops._active_transactions[self.transaction_id] = {
                "created_files": self.created_files,
                "modified_files": self.modified_files,
                "deleted_files": self.deleted_files,
            }
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any
    ) -> None:
        """Exit async context manager and handle rollback if needed."""
        async with self.file_ops._transaction_lock:
            try:
                if exc_type is not None and not self._completed:
                    # Exception occurred, rollback changes
                    await self._rollback()
                    logger.info(
                        f"Rolled back transaction {self.transaction_id} due to error: {exc_val}"
                    )
                elif not self._completed:
                    # Normal completion, mark as committed
                    self._completed = True
                    logger.debug(f"Transaction {self.transaction_id} completed successfully")
            finally:
                # Clean up transaction tracking
                self.file_ops._active_transactions.pop(self.transaction_id, None)

    async def track_file_creation(self, file_path: Path) -> None:
        """Track a file that will be created in this transaction."""
        self.created_files.append(file_path)

    async def track_file_modification(self, file_path: Path) -> None:
        """Track a file that will be modified in this transaction."""
        if file_path.exists():
            try:
                # Read current content for rollback
                async with aiofiles.open(file_path, "rb") as f:
                    raw_content = await f.read()
                original_content = detect_and_handle_encoding(raw_content)
                self.modified_files.append((file_path, original_content))
            except Exception as e:
                logger.warning(
                    f"Could not backup original content for rollback of {file_path}: {e}"
                )
                # Continue without backup - not ideal but better than failing the operation

    async def track_file_deletion(self, file_path: Path) -> None:
        """Track a file that will be deleted in this transaction."""
        if file_path.exists():
            try:
                # Read current content for rollback
                async with aiofiles.open(file_path, "rb") as f:
                    raw_content = await f.read()
                original_content = detect_and_handle_encoding(raw_content)
                self.deleted_files.append((file_path, original_content))
            except Exception as e:
                logger.warning(
                    f"Could not backup content for rollback of deleted file {file_path}: {e}"
                )

    async def commit(self) -> None:
        """Explicitly commit the transaction (optional - auto-commits on successful exit)."""
        self._completed = True

    async def _rollback(self) -> None:
        """Rollback all changes made in this transaction with per-file locking for safety."""
        rollback_errors = []

        # Remove created files with per-file locking
        for file_path in reversed(self.created_files):  # Reverse order for safety
            try:
                # Acquire per-file lock for atomic rollback operation
                file_lock = await self.file_ops.get_file_lock(file_path)
                async with file_lock:
                    if file_path.exists():
                        file_path.unlink()
                        logger.debug(f"Rollback: removed created file {file_path}")
            except Exception as e:
                rollback_errors.append(f"Failed to remove created file {file_path}: {e}")

        # Restore modified files with per-file locking
        for file_path, original_content in reversed(self.modified_files):
            try:
                # Acquire per-file lock for atomic rollback operation
                file_lock = await self.file_ops.get_file_lock(file_path)
                async with file_lock:
                    # Use the file_ops' safe write with no additional lock
                    # (we already have the file lock)
                    await self.file_ops.safe_write_file(
                        file_path, original_content, f"rollback of {file_path}", use_lock=False
                    )
                    logger.debug(f"Rollback: restored modified file {file_path}")
            except Exception as e:
                rollback_errors.append(f"Failed to restore modified file {file_path}: {e}")

        # Restore deleted files with per-file locking
        for file_path, original_content in self.deleted_files:
            try:
                # Acquire per-file lock for atomic rollback operation
                file_lock = await self.file_ops.get_file_lock(file_path)
                async with file_lock:
                    # Use the file_ops' safe write with no additional lock
                    # (we already have the file lock)
                    await self.file_ops.safe_write_file(
                        file_path,
                        original_content,
                        f"rollback restore of {file_path}",
                        use_lock=False,
                    )
                    logger.debug(f"Rollback: restored deleted file {file_path}")
            except Exception as e:
                rollback_errors.append(f"Failed to restore deleted file {file_path}: {e}")

        if rollback_errors:
            # Log all rollback errors but don't raise - we're already in error handling
            logger.error(
                f"Rollback of transaction {self.transaction_id} had errors: "
                f"{'; '.join(rollback_errors)}"
            )


class FileOperations:
    """Handles low-level file I/O, locking, and transactions."""

    def __init__(self, config_path: Path) -> None:
        """Initialize file operations.

        Args:
            config_path: Path to the configuration directory

        """
        self.config_path = config_path
        self._directory_checked = False

        # Initialize asyncio locks for concurrent operation safety
        self._file_write_lock = asyncio.Lock()  # Protects file write operations

        # Per-file locks for fine-grained concurrency control
        self._file_locks: dict[str, asyncio.Lock] = {}
        self._file_locks_lock = asyncio.Lock()  # Protects the file_locks dict

        # Transaction tracking for rollback capabilities
        self._active_transactions: dict[str, dict] = {}
        self._transaction_lock = asyncio.Lock()

    def begin_transaction(self, transaction_id: str | None = None) -> AtomicTransaction:
        """Begin an atomic transaction for multi-file operations.

        Args:
            transaction_id: Optional transaction identifier. Auto-generated if not provided.

        Returns:
            AtomicTransaction context manager

        """
        if transaction_id is None:
            import uuid

            transaction_id = f"tx_{uuid.uuid4().hex[:8]}"

        return AtomicTransaction(self, transaction_id)

    async def get_file_lock(self, file_path: Path) -> asyncio.Lock:
        """Get or create a per-file lock for fine-grained concurrency control.

        Args:
            file_path: Path to the file needing a lock

        Returns:
            asyncio.Lock for the specific file

        """
        file_key = str(file_path.resolve())

        async with self._file_locks_lock:
            if file_key not in self._file_locks:
                self._file_locks[file_key] = asyncio.Lock()
            return self._file_locks[file_key]

    async def cleanup_file_locks(self) -> None:
        """Clean up unused file locks to prevent memory growth."""
        async with self._file_locks_lock:
            to_remove = []
            for path, lock in self._file_locks.items():
                if not lock.locked():
                    to_remove.append(path)

            for path in to_remove:
                del self._file_locks[path]

            if to_remove:
                logger.debug(f"Cleaned up {len(to_remove)} unused file locks")

    async def safe_write_file(
        self,
        file_path: Path,
        content: str,
        operation_name: str = "file write",
        use_lock: bool = True,
    ) -> None:
        """Safely write content to file with proper error handling for disk full scenarios.

        Includes Unicode normalization.

        Args:
            file_path: Path to write the file to
            content: Content to write (will be Unicode-normalized)
            operation_name: Description of the operation for error messages
            use_lock: Whether to use file locking (default True)

        Raises:
            OSError: For disk full, permission, or other I/O errors with descriptive messages
            ValueError: For validation errors or Unicode issues

        """
        # Normalize Unicode content before writing
        try:
            normalized_content = normalize_unicode_text(content, remove_bom=True, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid Unicode content for {operation_name}: {str(e)}") from e

        async def _perform_write() -> None:
            """Perform the actual write operation."""
            # Create temporary file for atomic write
            temp_path = file_path.with_suffix(f"{file_path.suffix}.tmp.{os.getpid()}")

            try:
                # Ensure parent directory exists
                file_path.parent.mkdir(parents=True, exist_ok=True)

                # Check available disk space before writing (approximate check)
                try:
                    stat_info = os.statvfs(file_path.parent)
                    available_bytes = stat_info.f_bavail * stat_info.f_frsize
                    content_size = len(normalized_content.encode("utf-8"))

                    # Require at least 10MB buffer beyond content size
                    required_bytes = content_size + (10 * 1024 * 1024)

                    if available_bytes < required_bytes:
                        raise OSError(
                            errno.ENOSPC,
                            f"Insufficient disk space for {operation_name}. "
                            f"Required: {required_bytes // 1024 // 1024}MB, "
                            f"Available: {available_bytes // 1024 // 1024}MB",
                        )
                except (OSError, AttributeError) as e:
                    if isinstance(e, OSError) and e.errno == errno.ENOSPC:
                        raise  # Re-raise space errors
                    logger.debug(f"Could not check disk space: {e}")
                    # Continue without space check on unsupported filesystems

                # Write to temporary file first (atomic operation)
                try:
                    async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
                        bytes_written = await f.write(normalized_content)

                        # Verify all content was written
                        expected_bytes = len(normalized_content)
                        if bytes_written != expected_bytes:
                            raise OSError(
                                errno.EIO,
                                f"Partial write detected during {operation_name}. "
                                f"Expected {expected_bytes} characters, wrote {bytes_written}",
                            )

                        # Force sync to disk to catch I/O errors early
                        await f.flush()
                        await asyncio.to_thread(os.fsync, f.fileno())

                except OSError as e:
                    # Use centralized error handling for OSError
                    handle_os_error(e, operation_name)
                except UnicodeEncodeError as e:
                    raise ValueError(
                        f"Content contains invalid characters for {operation_name}: {str(e)}"
                    ) from e
                except Exception as e:
                    raise OSError(
                        errno.EIO, f"Unexpected error during {operation_name}: {str(e)}"
                    ) from e

                # Verify the temporary file was written correctly
                try:
                    temp_stat = temp_path.stat()
                    if temp_stat.st_size == 0 and normalized_content:
                        raise OSError(
                            errno.EIO,
                            f"Written file is empty after {operation_name}, possible I/O error",
                        )

                    # Read back and verify content (for critical operations)
                    async with aiofiles.open(temp_path, encoding="utf-8") as f:
                        written_content = await f.read()
                        if written_content != normalized_content:
                            raise OSError(
                                errno.EIO,
                                f"Content verification failed after {operation_name}. "
                                "File may be corrupted or partially written.",
                            )
                except OSError:
                    raise  # Re-raise OSErrors
                except Exception as e:
                    raise OSError(
                        errno.EIO, f"File verification failed after {operation_name}: {str(e)}"
                    ) from e

                # Atomic move from temporary to final location
                try:
                    temp_path.replace(file_path)
                    logger.debug(f"Successfully completed atomic {operation_name} to {file_path}")
                except OSError as e:
                    handle_os_error(e, f"final move for {operation_name}")

            except Exception:
                # Clean up temporary file on any error
                try:
                    if temp_path.exists():
                        temp_path.unlink()
                        logger.debug(f"Cleaned up temporary file after error: {temp_path}")
                except Exception as cleanup_error:
                    logger.warning(
                        f"Failed to clean up temporary file {temp_path}: {cleanup_error}"
                    )

                # Re-raise the original error
                raise

        # Execute write with or without file locking
        if use_lock:
            file_lock = await self.get_file_lock(file_path)
            async with file_lock:
                await _perform_write()
        else:
            await _perform_write()

    def ensure_config_directory(self) -> None:
        """Ensure the configuration directory exists."""
        if not self._directory_checked:
            self.config_path.mkdir(parents=True, exist_ok=True)
            self._directory_checked = True
