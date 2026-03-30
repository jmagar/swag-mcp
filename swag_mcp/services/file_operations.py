"""File operations module for SWAG MCP."""

import asyncio
import errno
import logging
from pathlib import Path
from typing import Any

from swag_mcp.services.filesystem import FilesystemBackend, LocalFilesystem
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

    @property
    def fs(self) -> FilesystemBackend:
        """Access filesystem backend via file_ops."""
        return self.file_ops.fs

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
        if await self.fs.exists(str(file_path)):
            try:
                raw_content = await self.fs.read_bytes(str(file_path))
                original_content = detect_and_handle_encoding(raw_content)
                self.modified_files.append((file_path, original_content))
            except Exception as e:
                logger.warning(
                    f"Could not backup original content for rollback of {file_path}: {e}"
                )

    async def track_file_deletion(self, file_path: Path) -> None:
        """Track a file that will be deleted in this transaction."""
        if await self.fs.exists(str(file_path)):
            try:
                raw_content = await self.fs.read_bytes(str(file_path))
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
                file_lock = await self.file_ops.get_file_lock(file_path)
                async with file_lock:
                    if await self.fs.exists(str(file_path)):
                        await self.fs.unlink(str(file_path))
                        logger.debug(f"Rollback: removed created file {file_path}")
            except Exception as e:
                rollback_errors.append(f"Failed to remove created file {file_path}: {e}")

        # Restore modified files with per-file locking
        for file_path, original_content in reversed(self.modified_files):
            try:
                file_lock = await self.file_ops.get_file_lock(file_path)
                async with file_lock:
                    await self.file_ops.safe_write_file(
                        file_path, original_content, f"rollback of {file_path}", use_lock=False
                    )
                    logger.debug(f"Rollback: restored modified file {file_path}")
            except Exception as e:
                rollback_errors.append(f"Failed to restore modified file {file_path}: {e}")

        # Restore deleted files with per-file locking
        for file_path, original_content in self.deleted_files:
            try:
                file_lock = await self.file_ops.get_file_lock(file_path)
                async with file_lock:
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
            logger.error(
                f"Rollback of transaction {self.transaction_id} had errors: "
                f"{'; '.join(rollback_errors)}"
            )


class FileOperations:
    """Handles low-level file I/O, locking, and transactions."""

    def __init__(
        self,
        config_path: Path,
        fs: FilesystemBackend | None = None,
    ) -> None:
        """Initialize file operations.

        Args:
            config_path: Path to the configuration directory
            fs: Filesystem backend (defaults to LocalFilesystem)

        """
        self.config_path = config_path
        self.fs: FilesystemBackend = fs or LocalFilesystem()
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
        file_key = str(file_path)

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

        Includes Unicode normalization. Uses the filesystem backend for atomic writes.

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
            path_str = str(file_path)
            parent_str = str(file_path.parent)

            # Check available disk space before writing (approximate check)
            try:
                space_info = await self.fs.statvfs(parent_str)
                if space_info is not None:
                    available_bytes, _ = space_info
                    content_size = len(normalized_content.encode("utf-8"))
                    required_bytes = content_size + (10 * 1024 * 1024)

                    if available_bytes < required_bytes:
                        raise OSError(
                            errno.ENOSPC,
                            f"Insufficient disk space for {operation_name}. "
                            f"Required: {required_bytes // 1024 // 1024}MB, "
                            f"Available: {available_bytes // 1024 // 1024}MB",
                        )
            except OSError as e:
                if e.errno == errno.ENOSPC:
                    raise
                logger.debug(f"Could not check disk space: {e}")

            # Write atomically via filesystem backend
            try:
                await self.fs.write_text(path_str, normalized_content)
            except OSError as e:
                handle_os_error(e, operation_name)
            except UnicodeEncodeError as e:
                raise ValueError(
                    f"Content contains invalid characters for {operation_name}: {str(e)}"
                ) from e
            except Exception as e:
                raise OSError(
                    errno.EIO, f"Unexpected error during {operation_name}: {str(e)}"
                ) from e

            logger.debug(f"Successfully completed atomic {operation_name} to {file_path}")

        # Execute write with or without file locking
        if use_lock:
            file_lock = await self.get_file_lock(file_path)
            async with file_lock:
                await _perform_write()
        else:
            await _perform_write()

    async def ensure_config_directory(self) -> None:
        """Ensure the configuration directory exists."""
        if not self._directory_checked:
            await self.fs.mkdir(str(self.config_path), parents=True)
            self._directory_checked = True

    async def read_text_safe(self, path: str, context: str = "file") -> str:
        """Read a file as text with binary detection, encoding handling, and error wrapping.

        Args:
            path: Filesystem path to read
            context: Description of the file for error messages

        Returns:
            Decoded and Unicode-normalized text content

        Raises:
            FileNotFoundError: If the file does not exist
            ValueError: If file contains binary content or invalid encoding
            OSError: For filesystem errors

        """
        raw_content = await self.fs.read_bytes(path)
        if b"\0" in raw_content[:512]:
            raise ValueError(f"{context} contains binary content or is unsafe to read")

        try:
            return detect_and_handle_encoding(raw_content)
        except OSError as e:
            handle_os_error(e, f"reading {context}")
            raise  # handle_os_error may not always raise
        except (ValueError, UnicodeDecodeError) as e:
            raise ValueError(
                f"{context} has invalid text encoding or Unicode characters: {e}"
            ) from e
        except Exception as e:
            raise OSError(
                errno.EIO,
                f"Unexpected error reading {context}: {e}",
            ) from e
