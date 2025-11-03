"""Core SWAG configuration management service."""

import asyncio
import errno
import logging
import os
import re
from collections import deque
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from re import Match
from typing import Any, Literal

import aiofiles
import aiohttp
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from jinja2.sandbox import SandboxedEnvironment

from swag_mcp.core.config import config
from swag_mcp.core.constants import LIST_FILTERS
from swag_mcp.models.config import (
    ListFilterType,
    SwagConfigRequest,
    SwagConfigResult,
    SwagEditRequest,
    SwagHealthCheckRequest,
    SwagHealthCheckResult,
    SwagListResult,
    SwagLogsRequest,
    SwagRemoveRequest,
    SwagResourceList,
    SwagUpdateRequest,
)
from swag_mcp.utils.error_codes import (
    ErrorCode,
    create_operation_error,
    create_validation_error,
)
from swag_mcp.utils.error_handlers import handle_os_error
from swag_mcp.utils.formatters import (
    build_template_filename,
    get_possible_sample_filenames,
)
from swag_mcp.utils.validators import (
    detect_and_handle_encoding,
    normalize_unicode_text,
    validate_config_filename,
    validate_domain_format,
    validate_file_content_safety_async,
    validate_mcp_path,
    validate_service_name,
    validate_upstream_port,
)

logger = logging.getLogger(__name__)


class SwagManagerService:
    """Service for managing SWAG proxy configurations."""

    def __init__(
        self,
        config_path: Path | None = None,
        template_path: Path | None = None,
    ) -> None:
        """Initialize the SWAG manager service."""
        self.config_path: Path = (
            Path(config_path) if config_path is not None else Path(config.proxy_confs_path)
        )
        self.template_path: Path = (
            Path(template_path) if template_path is not None else Path(config.template_path)
        )
        self._directory_checked: bool = False

        # Initialize secure Jinja2 environment with sandboxing
        self.template_env: Environment = self._create_secure_template_environment()

        # Testable hooks for template rendering
        self._pre_render_hook: Callable[[str, dict], None] | None = (
            None  # Called before template rendering
        )
        self._post_render_hook: Callable[[str, dict, str], None] | None = (
            None  # Called after template rendering
        )
        self._template_vars_hook: Callable[[dict], dict] | None = (
            None  # Called to modify template variables
        )

        # Initialize asyncio locks for concurrent operation safety
        self._backup_lock = asyncio.Lock()  # Protects backup creation operations
        self._file_write_lock = asyncio.Lock()  # Protects file write operations
        self._cleanup_lock = asyncio.Lock()  # Protects cleanup operations

        # Per-file locks for fine-grained concurrency control
        self._file_locks: dict[str, asyncio.Lock] = {}
        self._file_locks_lock = asyncio.Lock()  # Protects the file_locks dict

        # Transaction tracking for rollback capabilities
        self._active_transactions: dict[str, dict] = {}
        self._transaction_lock = asyncio.Lock()

        # HTTP session for health checks with connection pooling
        self._http_session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()

        logger.info(f"Initialized SWAG manager with proxy configs path: {self.config_path}")

    def set_template_hooks(
        self,
        pre_render_hook: Callable[[str, dict], None] | None = None,
        post_render_hook: Callable[[str, dict, str], None] | None = None,
        template_vars_hook: Callable[[dict], dict] | None = None,
    ) -> None:
        """Set testable hooks for template rendering.

        Args:
            pre_render_hook: Called before template rendering with (template_name, variables)
            post_render_hook: Called after template rendering with (template_name, variables,
                rendered_content)
            template_vars_hook: Called to modify template variables, should return modified dict

        """
        self._pre_render_hook = pre_render_hook
        self._post_render_hook = post_render_hook
        self._template_vars_hook = template_vars_hook

    def clear_template_hooks(self) -> None:
        """Clear all template rendering hooks (useful for test cleanup)."""
        self._pre_render_hook = None
        self._post_render_hook = None
        self._template_vars_hook = None

    async def __aenter__(self) -> "SwagManagerService":
        """Async context manager entry - initialize resources."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit - cleanup resources."""
        await self._close_session()
        await self._cleanup_file_locks()

    def _get_template_path(self) -> Path:
        """Return the root path for Jinja templates (testable hook)."""
        return self.template_path

    def _validate_template_variables(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Validate and sanitize template variables before rendering.

        Args:
            variables: Template variables to validate

        Returns:
            Sanitized variables dictionary

        """
        # Apply template_vars_hook if set (for testing)
        if self._template_vars_hook:
            variables = self._template_vars_hook(variables)

        # Basic validation - ensure all values are safe for template rendering
        safe_vars: dict[str, Any] = {}
        for key, value in variables.items():
            # Convert Path objects to strings for template compatibility
            if isinstance(value, Path):
                safe_vars[key] = str(value)
            # Ensure string values are safe
            elif isinstance(value, str | int | bool | float):
                safe_vars[key] = value
            # Skip None values
            elif value is None:
                continue
            else:
                # Convert other types to string representation
                safe_vars[key] = str(value)

        return safe_vars

    async def _render_template(self, template_name: str, variables: dict[str, Any]) -> str:
        """Render a template with validated variables (testable hook).

        Args:
            template_name: Name of the template file to render
            variables: Variables to pass to the template

        Returns:
            Rendered template content

        Raises:
            ValueError: If template not found or rendering fails

        """
        # Validate/sanitize variables before rendering
        safe_vars = self._validate_template_variables(variables)

        # Call pre-render hook if set (for testing)
        if self._pre_render_hook:
            self._pre_render_hook(template_name, safe_vars)

        try:
            template = self.template_env.get_template(template_name)
            content = template.render(**safe_vars)

            # Call post-render hook if set (for testing)
            if self._post_render_hook:
                self._post_render_hook(template_name, safe_vars, content)

            return content
        except TemplateNotFound as e:
            raise ValueError(f"Template {template_name} not found") from e
        except Exception as e:
            raise ValueError(f"Failed to render template: {str(e)}") from e

    async def _get_file_lock(self, file_path: Path) -> asyncio.Lock:
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

    async def _cleanup_file_locks(self) -> None:
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

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session with connection pooling.

        Returns:
            aiohttp.ClientSession configured with connection pooling and SSL context

        """
        async with self._session_lock:
            if self._http_session is None or self._http_session.closed:
                # Create SSL context for health checks
                import ssl

                from ..core.config import config

                ssl_context = ssl.create_default_context()

                # Only disable SSL verification if explicitly configured
                if config.health_check_insecure:
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE

                # Create connector with connection pooling
                connector = aiohttp.TCPConnector(
                    ssl=ssl_context,
                    limit=10,  # Connection pool size
                    limit_per_host=5,  # Max connections per host
                    ttl_dns_cache=300,  # DNS cache TTL in seconds
                    use_dns_cache=True,
                    enable_cleanup_closed=True,
                )

                # Create session with timeout and connector
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                self._http_session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                )

            return self._http_session

    async def _close_session(self) -> None:
        """Close HTTP session and cleanup resources."""
        async with self._session_lock:
            if self._http_session and not self._http_session.closed:
                await self._http_session.close()
                self._http_session = None

    async def _validate_nginx_syntax(self, config_path: Path) -> bool:
        """Validate nginx configuration syntax using subprocess.

        Args:
            config_path: Path to the nginx configuration file to validate

        Returns:
            bool: True if syntax is valid, False otherwise

        """
        import shutil
        import subprocess

        try:
            # Check if nginx is available
            nginx_cmd = shutil.which("nginx")
            if not nginx_cmd:
                logger.warning("nginx command not found, skipping syntax validation")
                return True  # Assume valid if nginx not available

            # Run nginx syntax test
            result = await asyncio.create_subprocess_exec(
                nginx_cmd,
                "-t",
                "-c",
                str(config_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            stdout, stderr = await result.communicate()

            # nginx -t returns 0 for valid config, non-zero for invalid
            if result.returncode == 0:
                logger.debug(f"nginx syntax validation passed for {config_path}")
                return True
            else:
                logger.error(
                    f"nginx syntax validation failed for {config_path}: "
                    f"{stderr.decode('utf-8', errors='ignore')}"
                )
                return False

        except Exception as e:
            logger.error(f"Error validating nginx syntax for {config_path}: {e}")
            # Return True to not block operations if validation fails
            return True

    class AtomicTransaction:
        """Context manager for atomic multi-file operations with rollback support."""

        def __init__(self, manager: "SwagManagerService", transaction_id: str):
            """Initialize atomic transaction.

            Args:
                manager: SwagManagerService instance
                transaction_id: Unique identifier for this transaction

            """
            self.manager = manager
            self.transaction_id = transaction_id
            self.created_files: list[Path] = []
            self.modified_files: list[tuple[Path, str]] = []  # (file_path, original_content)
            self.deleted_files: list[tuple[Path, str]] = []  # (file_path, original_content)
            self._completed = False

        async def __aenter__(self) -> "SwagManagerService.AtomicTransaction":
            """Enter async context manager and initialize transaction."""
            async with self.manager._transaction_lock:
                if self.transaction_id in self.manager._active_transactions:
                    raise ValueError(f"Transaction {self.transaction_id} is already active")
                self.manager._active_transactions[self.transaction_id] = {
                    "created_files": self.created_files,
                    "modified_files": self.modified_files,
                    "deleted_files": self.deleted_files,
                }
            return self

        async def __aexit__(
            self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: Any
        ) -> None:
            """Exit async context manager and handle rollback if needed."""
            async with self.manager._transaction_lock:
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
                    self.manager._active_transactions.pop(self.transaction_id, None)

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
                    file_lock = await self.manager._get_file_lock(file_path)
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
                    file_lock = await self.manager._get_file_lock(file_path)
                    async with file_lock:
                        # Use the manager's safe write with no additional lock
                        # (we already have the file lock)
                        await self.manager._safe_write_file(
                            file_path, original_content, f"rollback of {file_path}", use_lock=False
                        )
                        logger.debug(f"Rollback: restored modified file {file_path}")
                except Exception as e:
                    rollback_errors.append(f"Failed to restore modified file {file_path}: {e}")

            # Restore deleted files with per-file locking
            for file_path, original_content in self.deleted_files:
                try:
                    # Acquire per-file lock for atomic rollback operation
                    file_lock = await self.manager._get_file_lock(file_path)
                    async with file_lock:
                        # Use the manager's safe write with no additional lock
                        # (we already have the file lock)
                        await self.manager._safe_write_file(
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
    def begin_transaction(self, transaction_id: str | None = None) -> AtomicTransaction:
        """Begin an atomic transaction for multi-file operations.

        Args:
            transaction_id: Optional transaction identifier. Auto-generated if not provided.

        Returns:
            AtomicTransaction context manager

        """
        if transaction_id is None:
            import uuid

            transaction_id = f"txn_{uuid.uuid4().hex[:8]}"
        return self.AtomicTransaction(self, transaction_id)

    def _create_secure_template_environment(self) -> SandboxedEnvironment:
        """Create a secure sandboxed Jinja2 environment to prevent SSTI attacks.

        Returns:
            SandboxedEnvironment configured with security restrictions

        """
        # Create sandboxed environment to prevent dangerous operations
        env = SandboxedEnvironment(
            loader=FileSystemLoader(str(self.template_path)),
            autoescape=True,  # Enable autoescape for security
            undefined=StrictUndefined,  # Fail on undefined variables
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Remove dangerous globals and built-ins to prevent code execution
        # Minimal set of globals required for NGINX config templates
        env.globals = {
            # Only essential type conversion functions for template rendering
            "str": str,
            "int": int,
            "bool": bool,
        }

        # Customize sandbox to block additional dangerous operations
        def is_safe_attribute(obj: Any, attr: str, value: Any) -> bool:
            """Check if attribute access is safe."""
            # Block access to private/dunder methods
            if attr.startswith("_"):
                return False

            # Block access to dangerous attributes
            dangerous_attrs = [
                "import",
                "eval",
                "exec",
                "compile",
                "open",
                "file",
                "input",
                "raw_input",
                "reload",
                "help",
                "copyright",
                "credits",
                "license",
                "quit",
                "exit",
                "globals",
                "locals",
                "vars",
                "dir",
                "hasattr",
                "getattr",
                "setattr",
                "delattr",
                "isinstance",
                "issubclass",
                "callable",
                "classmethod",
                "staticmethod",
                "property",
                "super",
                "type",
                "__import__",
                "__builtins__",
                "__dict__",
                "__class__",
                "__bases__",
                "__name__",
                "__module__",
                "func_globals",
                "f_globals",
                "gi_frame",
                "gi_code",
                "cr_frame",
                "cr_code",
            ]

            if attr.lower() in dangerous_attrs:
                return False

            # Block access to subprocess-related attributes
            if "subprocess" in str(type(obj)).lower() or "popen" in attr.lower():
                return False

            # Block access to file system operations - return True if safe, False if blocked
            fs_access = any(
                fs_attr in attr.lower() for fs_attr in ["file", "open", "read", "write"]
            )
            safe_type = isinstance(obj, str | int | float | bool | list | dict | tuple)
            return not (fs_access and not safe_type)

        # Override the sandboxed environment's security checks
        # Note: is_safe_attribute signature doesn't perfectly match Jinja2 expectations
        # but this works for our security model
        env.is_safe_attribute = is_safe_attribute  # type: ignore[method-assign]

        # Disable dangerous template features
        env.filters.clear()  # Remove potentially dangerous filters
        env.tests.clear()  # Remove potentially dangerous tests

        # Add back only safe filters
        safe_filters = {
            "upper": str.upper,
            "lower": str.lower,
            "title": str.title,
            "capitalize": str.capitalize,
            "strip": str.strip,
            "replace": lambda s, old, new: str(s).replace(old, new),
            "length": len,
            "default": lambda val, default_val: val if val else default_val,
        }
        env.filters.update(safe_filters)

        logger.debug("Created secure sandboxed template environment")
        return env

    def _validate_config_content(self, content: str, config_name: str) -> str:
        """Validate configuration file content for security.

        Args:
            content: Configuration file content to validate
            config_name: Name of the configuration file

        Returns:
            Validated content if safe

        Raises:
            ValueError: If content contains dangerous patterns

        """
        if not content or not content.strip():
            raise ValueError("Configuration content cannot be empty")

        # Patterns that should never appear in configuration files
        dangerous_patterns = [
            # Template injection attempts (users shouldn't put raw Jinja2 in configs)
            r"\{\{.*?\}\}",  # Jinja2 expressions in user content
            r"\{%.*?%\}",  # Jinja2 statements in user content
            r"\{#.*?#\}",  # Jinja2 comments in user content
            # Server-side includes and imports
            r'include\s+["\'][^"\']*["\'];?\s*#[^}]*\}\}',  # Template includes
            r'import\s+["\'][^"\']*["\'];?\s*#[^}]*\}\}',  # Template imports
            # Script injection attempts
            r"<script.*?>",  # Script tags
            r"javascript:",  # JavaScript URLs
            r"data:.*base64",  # Data URLs with base64
            r"vbscript:",  # VBScript URLs
            # Shell command injection attempts (more specific to avoid nginx syntax)
            r";\s*(ls|cat|rm|cp|mv|mkdir|grep|sed|awk|curl|wget|nc|ncat|bash|sh|python|perl|ruby|php)[^a-zA-Z0-9_]",
            # Common shell commands after semicolon
            r"\$\([^)]*\)",  # Command substitution
            r"`[^`]*`",  # Backtick command execution
            # File system access attempts
            r"\.\./",  # Path traversal attempts
            r"\.\.\\",  # Windows path traversal
            r"/etc/",  # Direct /etc access
            r"/var/",  # Direct /var access
            r"/tmp/",  # Direct /tmp access
            r"/home/",  # Direct /home access
            r"/root/",  # Direct /root access
            r"file://",  # File:// URLs
            # Process/system access attempts
            r"proc/",  # /proc filesystem access
            r"dev/",  # /dev filesystem access
        ]

        # Check for dangerous patterns
        for pattern in dangerous_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                logger.warning(
                    f"Blocked dangerous content in configuration '{config_name}': "
                    f"matched pattern {pattern}"
                )
                raise ValueError("Configuration content contains potentially dangerous patterns")

        # Additional validation for NGINX configuration files
        if config_name.endswith(".conf"):
            # Ensure reasonable length (prevent DoS through large configs)
            if len(content) > 10000000:  # 10MB limit
                raise ValueError("Configuration content is too large")

            # Basic NGINX syntax validation - ensure it has server blocks if it's a config
            if "server" not in content and len(content.strip()) > 50:
                # Only warn for now, don't block (might be valid edge case)
                logger.info(
                    f"Configuration '{config_name}' doesn't appear to contain server blocks"
                )

        # Normalize Unicode and remove BOM for consistent processing
        try:
            normalized_content = normalize_unicode_text(content, remove_bom=True, strict=False)
        except ValueError as e:
            raise ValueError(
                f"Invalid Unicode content in configuration '{config_name}': {str(e)}"
            ) from e

        logger.debug(
            f"Validated configuration content for '{config_name}' "
            f"({len(normalized_content)} characters)"
        )
        return normalized_content

    async def _safe_write_file(
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
            file_lock = await self._get_file_lock(file_path)
            async with file_lock:
                await _perform_write()
        else:
            await _perform_write()

    def _ensure_config_directory(self) -> None:
        """Ensure the configuration directory exists."""
        if not self._directory_checked:
            self.config_path.mkdir(parents=True, exist_ok=True)
            self._directory_checked = True

    async def list_configs(self, list_filter: ListFilterType = "all") -> SwagListResult:
        """List configuration files based on type."""
        # Validate filter parameter
        if list_filter not in LIST_FILTERS:
            valid_options = ", ".join(sorted(LIST_FILTERS))
            raise ValueError(
                f"Invalid list filter '{list_filter}'. Must be one of: {valid_options}"
            )

        logger.info(f"Listing configurations of type: {list_filter}")
        self._ensure_config_directory()

        configs = []

        if list_filter in ["all", "active"]:
            # List active configurations (.conf files, not .sample)
            active_configs = [
                f.name for f in self.config_path.glob("*.conf") if not f.name.endswith(".sample")
            ]
            configs.extend(active_configs)

        if list_filter in ["all", "samples"]:
            # List sample configurations (.sample files)
            sample_configs = [f.name for f in self.config_path.glob("*.sample")]
            configs.extend(sample_configs)

        # Remove duplicates and sort
        configs = sorted(set(configs))

        logger.info(f"Found {len(configs)} configurations")

        return SwagListResult(configs=configs, total_count=len(configs), list_filter=list_filter)

    async def read_config(self, config_name: str) -> str:
        """Read configuration file content."""
        logger.info(f"Reading configuration: {config_name}")
        self._ensure_config_directory()

        # Validate config name directly (must be full filename)
        validated_name = validate_config_filename(config_name)

        config_file = self.config_path / validated_name

        # Check if file exists first
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file {validated_name} not found")

        # Security validation: ensure file is safe to read as text
        if not await validate_file_content_safety_async(config_file):
            raise ValueError(
                f"Configuration file {validated_name} contains binary content or is unsafe to read"
            )

        try:
            # Read file with proper encoding detection and Unicode normalization
            async with aiofiles.open(config_file, "rb") as f:
                raw_content = await f.read()

            # Detect encoding and normalize Unicode
            content = detect_and_handle_encoding(raw_content)

        except OSError as e:
            handle_os_error(e, "reading configuration file", validated_name)
        except (ValueError, UnicodeDecodeError) as e:
            raise ValueError(
                f"Configuration file has invalid text encoding or Unicode characters: "
                f"{validated_name}: {str(e)}"
            ) from e
        except Exception as e:
            raise OSError(
                errno.EIO,
                f"Unexpected error reading configuration file: {validated_name}: {str(e)}",
            ) from e

        logger.info(f"Successfully read {len(content)} characters from {validated_name}")
        return content

    async def create_config(self, request: SwagConfigRequest) -> SwagConfigResult:
        """Create new configuration from template."""
        # Extract service_name and base_type from config_name
        config_name = request.config_name  # e.g., "jellyfin.subdomain.conf"
        parts = config_name.rsplit(".", 2)  # ['jellyfin', 'subdomain', 'conf']
        if len(parts) != 3 or parts[2] != "conf":
            raise ValueError(
                f"Invalid config_name format. Must be 'service.type.conf' (got: {config_name})"
            )

        service_name = parts[0]
        base_type = parts[1]  # 'subdomain' or 'subfolder'

        if base_type not in ["subdomain", "subfolder"]:
            raise ValueError(f"Invalid base type '{base_type}'. Must be 'subdomain' or 'subfolder'")

        # Use SWAG-compliant MCP templates (consolidated in commit 64547f5)
        # All templates now support MCP/SSE streaming with include /config/nginx/mcp.conf
        template_type = f"swag-compliant-mcp-{base_type}"

        logger.info(f"Creating {template_type} configuration for {service_name} ({config_name})")
        self._ensure_config_directory()

        # Security validation: validate all input parameters
        validated_service_name = validate_service_name(service_name)
        validated_server_name = validate_domain_format(request.server_name)
        validated_port = validate_upstream_port(request.upstream_port)
        # Validate upstream_app with regex pattern
        if not re.match(r'^[A-Za-z0-9_.-]+$', request.upstream_app):
            raise ValueError(f"Invalid upstream app name: {request.upstream_app}")

        # Determine template and filename
        template_name = build_template_filename(template_type)
        filename = config_name  # Use the provided config_name directly

        # Perform configuration creation with proper locking to prevent race conditions
        config_file = self.config_path / filename
        file_lock = await self._get_file_lock(config_file)
        async with file_lock:
            # Check if configuration already exists
            if config_file.exists():
                raise ValueError(f"Configuration {filename} already exists")

            try:
                # Prepare template variables
                template_vars = {
                    "service_name": validated_service_name,
                    "server_name": validated_server_name,
                    "upstream_app": request.upstream_app,
                    "upstream_port": validated_port,
                    "upstream_proto": request.upstream_proto,
                    "auth_method": request.auth_method,
                    "enable_quic": request.enable_quic,
                }

                # Render template with validated variables
                content = await self._render_template(template_name, template_vars)
            except ValueError as e:
                # _render_template already handles TemplateNotFound and other exceptions
                raise e

            # Write configuration safely with proper error handling (no additional lock needed)
            await self._safe_write_file(
                config_file, content, f"configuration creation for {filename}", use_lock=False
            )

        logger.info(f"Successfully created configuration: {filename}")

        return SwagConfigResult(filename=filename, content=content)

    async def update_config(self, edit_request: SwagEditRequest) -> SwagConfigResult:
        """Update configuration with optional backup."""
        logger.info(f"Updating configuration: {edit_request.config_name}")

        # Validate config name directly (must be full filename)
        validated_name = validate_config_filename(edit_request.config_name)

        # Security validation: validate configuration content for dangerous patterns
        validated_content = self._validate_config_content(
            edit_request.new_content or "", validated_name
        )

        config_file = self.config_path / validated_name
        backup_name = None

        # Create backup if requested and file exists
        if edit_request.create_backup and config_file.exists():
            backup_name = await self._create_backup(validated_name)
            logger.info(f"Created backup: {backup_name}")

        # Write validated content safely with proper error handling
        await self._safe_write_file(
            config_file, validated_content, f"configuration update for {validated_name}"
        )

        logger.info(f"Successfully updated configuration: {validated_name}")

        return SwagConfigResult(
            filename=validated_name,
            content=validated_content,
            backup_created=backup_name,
        )

    async def update_config_field(self, update_request: SwagUpdateRequest) -> SwagConfigResult:
        """Update specific field in existing configuration using targeted updaters."""
        logger.info(f"Updating {update_request.update_field} in {update_request.config_name}")

        # Read existing config
        content = await self.read_config(update_request.config_name)

        # Create backup if requested
        backup_name = None
        if update_request.create_backup:
            backup_name = await self._create_backup(update_request.config_name)

        # Dispatch to specific updater methods
        updaters = {
            "port": self._update_port_field,
            "upstream": self._update_upstream_field,
            "app": self._update_app_field,
            "add_mcp": self._update_mcp_field
        }

        updater = updaters.get(update_request.update_field)
        if not updater:
            raise create_validation_error(
                code=ErrorCode.INVALID_UPDATE_FIELD,
                message=f"Unsupported update field: {update_request.update_field}",
                context={"valid_fields": list(updaters.keys())}
            )

        return await updater(update_request, content, backup_name)

    async def _update_port_field(
        self,
        update_request: SwagUpdateRequest,
        content: str,
        backup_name: str | None
    ) -> SwagConfigResult:
        """Update port field in configuration."""
        # Validate port value
        try:
            port_value = int(update_request.update_value)
            if not (1 <= port_value <= 65535):
                raise create_validation_error(
                    ErrorCode.INVALID_PORT_NUMBER,
                    f"Port number must be between 1-65535, got: {port_value}"
                )
        except (ValueError, TypeError) as e:
            raise create_validation_error(
                ErrorCode.INVALID_PORT_NUMBER,
                f"Invalid port value: {update_request.update_value}",
                context={"original_error": str(e)}
            ) from e

        updated_content = content
        changes_made = False

        # Try template format first: set $upstream_port
        pattern = r'set \$upstream_port ("[^"]*"|[^;]+);'
        replacement = rf"set \$upstream_port \"{port_value}\";"
        new_content, port_replacements = re.subn(pattern, replacement, updated_content)

        if port_replacements > 0:
            updated_content = new_content
            changes_made = True
            logger.debug(f"Updated {port_replacements} template port references to {port_value}")
        else:
            # Try simple nginx format: proxy_pass http://app:port
            pattern = r'proxy_pass\s+https?://([^/:]+):(\d+)([^;]*);'

            def replace_proxy_port(match: Match[str]) -> str:
                app = match.group(1)
                path = match.group(3) or ''
                protocol = 'https' if 'https' in match.group(0) else 'http'
                return f'proxy_pass {protocol}://{app}:{port_value}{path};'

            new_content, proxy_replacements = re.subn(pattern, replace_proxy_port, updated_content)
            if proxy_replacements > 0:
                updated_content = new_content
                changes_made = True
                logger.debug(
                f"Updated {proxy_replacements} proxy_pass port references to {port_value}"
            )

        # Update upstream comment
        upstream_comment_pattern = r"(# Upstream: https?://[^:]+:)\d+"
        upstream_comment_replacement = rf"\g<1>{port_value}"
        new_content, comment_replacements = re.subn(
            upstream_comment_pattern, upstream_comment_replacement, updated_content
        )
        if comment_replacements > 0:
            updated_content = new_content

        return await self._finalize_config_update(
            update_request, updated_content, backup_name, changes_made
        )

    async def _update_upstream_field(
        self,
        update_request: SwagUpdateRequest,
        content: str,
        backup_name: str | None
    ) -> SwagConfigResult:
        """Update upstream app field in configuration."""
        # Validate upstream app name
        if not re.match(r'^[A-Za-z0-9_.-]+$', update_request.update_value):
            raise create_validation_error(
                ErrorCode.INVALID_SERVICE_NAME,
                f"Invalid upstream app name: {update_request.update_value}"
            )

        updated_content = content
        changes_made = False

        # Try template format first: set $upstream_app
        pattern = r'set \$upstream_app ("[^"]*"|[^;]+);'
        replacement = rf"set \$upstream_app \"{update_request.update_value}\";"
        new_content, app_replacements = re.subn(pattern, replacement, updated_content)

        if app_replacements > 0:
            updated_content = new_content
            changes_made = True
            logger.debug(
                f"Updated {app_replacements} template app references to "
                f"{update_request.update_value}"
            )
        else:
            # Try simple nginx format: proxy_pass http://app:port
            pattern = r'proxy_pass\s+https?://([^/:]+)(:\d+)?([^;]*);'

            def replace_proxy_pass(match: Match[str]) -> str:
                port = match.group(2) or ''
                path = match.group(3) or ''
                protocol = 'https' if 'https' in match.group(0) else 'http'
                return f'proxy_pass {protocol}://{update_request.update_value}{port}{path};'

            new_content, proxy_replacements = re.subn(pattern, replace_proxy_pass, updated_content)
            if proxy_replacements > 0:
                updated_content = new_content
                changes_made = True
                logger.debug(
                    f"Updated {proxy_replacements} proxy_pass app references to "
                    f"{update_request.update_value}"
                )

        # Update upstream comment
        upstream_comment_pattern = r"(# Upstream: https?://)[^:]+(:\d+)"
        upstream_comment_replacement = rf"\g<1>{update_request.update_value}\g<2>"
        new_content, comment_replacements = re.subn(
            upstream_comment_pattern, upstream_comment_replacement, updated_content
        )
        if comment_replacements > 0:
            updated_content = new_content

        return await self._finalize_config_update(
            update_request, updated_content, backup_name, changes_made
        )

    async def _update_app_field(
        self,
        update_request: SwagUpdateRequest,
        content: str,
        backup_name: str | None
    ) -> SwagConfigResult:
        """Update both app and port field in configuration."""
        # Update both app and port (format: "app:port")
        if ":" not in update_request.update_value:
            raise create_validation_error(
                ErrorCode.INVALID_UPDATE_FIELD,
                "app field requires format 'app:port'"
            )

        app, port = update_request.update_value.split(":", 1)

        # Validate app name
        if not re.match(r'^[A-Za-z0-9_.-]+$', app):
            raise create_validation_error(
                ErrorCode.INVALID_SERVICE_NAME,
                f"Invalid app name: {app}"
            )

        # Validate port
        try:
            port_value = int(port)
            if not (1 <= port_value <= 65535):
                raise create_validation_error(
                    ErrorCode.INVALID_PORT_NUMBER,
                    f"Port number must be between 1-65535, got: {port_value}"
                )
        except (ValueError, TypeError) as e:
            raise create_validation_error(
                ErrorCode.INVALID_PORT_NUMBER,
                f"Invalid port value: {port}",
                context={"original_error": str(e)}
            ) from e

        updated_content = content
        changes_made = False

        # Try template format first
        app_pattern = r'set \$upstream_app ("[^"]*"|[^;]+);'
        app_replacement = rf"set \$upstream_app \"{app}\";"
        new_content, app_replacements = re.subn(app_pattern, app_replacement, updated_content)

        if app_replacements > 0:
            updated_content = new_content
            changes_made = True

        port_pattern = r'set \$upstream_port ("[^"]*"|[^;]+);'
        port_replacement = rf"set \$upstream_port \"{port_value}\";"
        new_content, port_replacements = re.subn(port_pattern, port_replacement, updated_content)

        if port_replacements > 0:
            updated_content = new_content
            changes_made = True

        # If template format didn't work, try simple nginx format
        if not changes_made:
            pattern = r'proxy_pass\s+https?://([^/:]+)(:\d+)?([^;]*);'

            def replace_proxy_app_port(match: Match[str]) -> str:
                path = match.group(3) or ''
                protocol = 'https' if 'https' in match.group(0) else 'http'
                return f'proxy_pass {protocol}://{app}:{port_value}{path};'

            new_content, proxy_replacements = re.subn(
                pattern, replace_proxy_app_port, updated_content
            )
            if proxy_replacements > 0:
                updated_content = new_content
                changes_made = True

        # Update upstream comment
        upstream_comment_pattern = r"# Upstream: https?://[^:]+(:\d+)"
        upstream_comment_replacement = f"# Upstream: http://{app}:{port_value}"
        new_content, comment_replacements = re.subn(
            upstream_comment_pattern, upstream_comment_replacement, updated_content
        )
        if comment_replacements > 0:
            updated_content = new_content

        return await self._finalize_config_update(
            update_request, updated_content, backup_name, changes_made
        )

    async def _update_mcp_field(
        self,
        update_request: SwagUpdateRequest,
        content: str,
        backup_name: str | None
    ) -> SwagConfigResult:
        """Add MCP location block to configuration."""
        # Add MCP location block - delegate to the dedicated method
        mcp_path = update_request.update_value if update_request.update_value else "/mcp"

        # Validate the computed MCP path
        try:
            validated_mcp_path = validate_mcp_path(mcp_path)
        except ValueError as e:
            raise create_validation_error(
                ErrorCode.INVALID_MCP_PATH,
                f"Invalid MCP path: {str(e)}"
            ) from e

        # Call the add_mcp_location method with validated path
        return await self.add_mcp_location(
            config_name=update_request.config_name,
            mcp_path=validated_mcp_path,
            create_backup=update_request.create_backup,
        )

    async def _finalize_config_update(
        self,
        update_request: SwagUpdateRequest,
        updated_content: str,
        backup_name: str | None,
        changes_made: bool
    ) -> SwagConfigResult:
        """Finalize configuration update with validation and file writing."""
        # Validate that changes were actually made
        if not changes_made:
            field = update_request.update_field
            config_name = update_request.config_name

            format_map = {
                "upstream": (
                    "'set $upstream_app' variables or 'proxy_pass' directives"
                ),
                "port": (
                    "'set $upstream_port' variables or 'proxy_pass' directives with ports"
                ),
                "app": (
                    "'set $upstream_app' and 'set $upstream_port' variables or "
                    "'proxy_pass' directives"
                )
            }

            expected_format = format_map.get(field, "template format")

            raise create_operation_error(
                ErrorCode.FILE_WRITE_ERROR,
                f"No changes made to {config_name}. The configuration file doesn't "
                f"contain the expected format for '{field}' updates",
                context={
                    "expected_format": expected_format,
                    "supports": "both template-generated and standard nginx configurations"
                }
            )

        # Write updated content to a temporary file for validation
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as temp_file:
            temp_file.write(updated_content)
            temp_path = Path(temp_file.name)

        try:
            # Validate nginx syntax before committing changes
            if not await self._validate_nginx_syntax(temp_path):
                raise create_operation_error(
                    ErrorCode.CONFIG_SYNTAX_ERROR,
                    "Updated configuration contains invalid nginx syntax"
                )

            # Write updated content
            config_file = self.config_path / update_request.config_name
            await self._safe_write_file(
                config_file, updated_content, f"field update for {update_request.config_name}"
            )

            logger.info(
                f"Successfully updated {update_request.update_field} in "
                f"{update_request.config_name}"
            )

            return SwagConfigResult(
                filename=update_request.config_name,
                content=updated_content,
                backup_created=backup_name,
            )

        finally:
            # Clean up temp file
            if temp_path.exists():
                temp_path.unlink()

    async def _create_backup(self, config_name: str) -> str:
        """Create timestamped backup of configuration file with proper locking."""
        # Security validation: ensure config name is safe (should already be validated by caller)
        validated_name = validate_config_filename(config_name)

        config_file = self.config_path / validated_name

        # Use both global backup lock and per-file lock for safety
        async with self._backup_lock:
            file_lock = await self._get_file_lock(config_file)
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
                await self._safe_write_file(
                    backup_file, content, f"backup creation for {backup_name}", use_lock=False
                )

                return backup_name

    async def validate_template_exists(self, config_type: str) -> bool:
        """Validate that the required template exists."""
        try:
            template_name = build_template_filename(config_type)
        except ValueError:
            # Invalid config_type, template doesn't exist
            return False

        try:
            self.template_env.get_template(template_name)
            return True
        except TemplateNotFound:
            return False

    async def validate_all_templates(self) -> dict[str, bool]:
        """Validate that all required templates exist.

        Returns:
            Dictionary mapping template names to their existence status

        """
        from swag_mcp.core.constants import ALL_CONFIG_TYPES

        results = {}
        for config_type in ALL_CONFIG_TYPES:
            template_name = build_template_filename(config_type)
            # Check template existence directly to avoid duplicate template_name assignment
            try:
                self.template_env.get_template(template_name)
                exists = True
            except TemplateNotFound:
                exists = False

            results[config_type] = exists

            if exists:
                logger.debug(f"Template validation passed: {template_name}")
            else:
                logger.warning(f"Template validation failed: {template_name}")

        return results

    async def remove_config(self, remove_request: SwagRemoveRequest) -> SwagConfigResult:
        """Remove configuration with optional backup."""
        logger.info(f"Removing configuration: {remove_request.config_name}")

        # Validate config name directly (must be full filename)
        validated_name = validate_config_filename(remove_request.config_name)

        config_file = self.config_path / validated_name

        # Security validation: ensure file is safe to read as text
        if not await validate_file_content_safety_async(config_file):
            raise ValueError(
                f"Configuration file {validated_name} contains binary content or is unsafe to read"
            )

        # Read content for backup and response with error handling and Unicode normalization
        try:
            # Read file with proper encoding detection and Unicode normalization
            async with aiofiles.open(config_file, "rb") as f:
                raw_content = await f.read()

            # Detect encoding and normalize Unicode
            content = detect_and_handle_encoding(raw_content)

        except OSError as e:
            handle_os_error(e, "reading configuration file for removal", validated_name)
        except (ValueError, UnicodeDecodeError) as e:
            raise ValueError(
                f"Configuration file has invalid text encoding or Unicode characters "
                f"for removal: {validated_name}: {str(e)}"
            ) from e
        except Exception as e:
            raise OSError(
                errno.EIO,
                (
                    f"Unexpected error reading configuration file for removal: "
                    f"{validated_name}: {str(e)}"
                ),
            ) from e

        backup_name = None

        # Create backup if requested
        if remove_request.create_backup:
            backup_name = await self._create_backup(validated_name)
            logger.info(f"Created backup: {backup_name}")

        # Remove the configuration file with proper error handling
        try:
            config_file.unlink()
        except OSError as e:
            handle_os_error(e, "removing configuration file", validated_name)
        except Exception as e:
            raise OSError(
                errno.EIO,
                f"Unexpected error removing configuration file: {validated_name}: {str(e)}",
            ) from e

        logger.info(f"Successfully removed configuration: {validated_name}")

        return SwagConfigResult(
            filename=validated_name, content=content, backup_created=backup_name
        )

    async def get_swag_logs(self, logs_request: SwagLogsRequest) -> str:
        """Get SWAG logs by reading log files directly from mounted volume.

        Uses memory-efficient streaming to handle large log files.
        """
        logger.info(f"Getting SWAG logs: {logs_request.log_type}, {logs_request.lines} lines")

        # Map log types to file paths (using /swag mount point)
        log_paths = {
            "nginx-access": Path("/swag/log/nginx/access.log"),
            "nginx-error": Path("/swag/log/nginx/error.log"),
            "fail2ban": Path("/swag/log/fail2ban/fail2ban.log"),
            "letsencrypt": Path("/swag/log/letsencrypt/letsencrypt.log"),
            "renewal": Path("/swag/log/letsencrypt/renewal.log"),
        }

        log_file_path = log_paths.get(logs_request.log_type)

        if not log_file_path:
            raise ValueError(f"Invalid log type: {logs_request.log_type}")

        try:
            if not log_file_path.exists():
                # Return helpful message if file doesn't exist
                return (
                    f"Log file not found: {log_file_path}\n"
                    "The log file may not exist yet or SWAG may not be running."
                )

            # Memory-efficient streaming approach using deque
            # Read file in chunks and maintain only the requested number of lines in memory
            max_lines = logs_request.lines

            # Use deque with maxlen to automatically maintain only the last N lines
            line_buffer: deque[str] = deque(maxlen=max_lines)

            # Read file in streaming fashion
            async with aiofiles.open(log_file_path, encoding="utf-8", errors="ignore") as f:
                # For large files, we need to be memory-efficient
                # Read the file line by line to avoid loading everything into memory
                async for line in f:
                    line_buffer.append(line)

                    # Optional: If file is extremely large, we could add periodic yielding
                    # This prevents blocking the event loop for too long
                    # Every 1000 lines, yield control back to the event loop
                    if len(line_buffer) == max_lines and len(line_buffer) % 1000 == 0:
                        await asyncio.sleep(0)  # Yield control

            if not line_buffer:
                return f"No log entries found in {logs_request.log_type} log."

            # Convert deque to string efficiently
            result = "".join(line_buffer)
            logger.info(
                f"Successfully retrieved {len(line_buffer)} lines from {logs_request.log_type} "
                f"(memory-efficient streaming)"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to read SWAG log file: {str(e)}")
            raise FileNotFoundError(
                f"Unable to read SWAG {logs_request.log_type} logs: {str(e)}\n"
                f"Please check that SWAG is running and log files are accessible"
            ) from e

    async def get_resource_configs(self) -> SwagResourceList:
        """Get list of active configuration files for resources."""
        logger.info("Getting active configuration files for resources")

        # Get active configurations (excluding samples and backups)
        active_configs = [
            f.name
            for f in self.config_path.glob("*.conf")
            if not f.name.endswith(".sample") and ".backup." not in f.name
        ]

        # Sort the list
        active_configs = sorted(active_configs)

        logger.info(f"Found {len(active_configs)} active configurations")

        return SwagResourceList(configs=active_configs, total_count=len(active_configs))

    async def get_sample_configs(self) -> SwagResourceList:
        """Get list of sample configuration files for resources."""
        logger.info("Getting sample configuration files for resources")

        # Get sample configurations
        sample_configs = [f.name for f in self.config_path.glob("*.sample")]

        # Sort the list
        sample_configs = sorted(sample_configs)

        logger.info(f"Found {len(sample_configs)} sample configurations")

        return SwagResourceList(configs=sample_configs, total_count=len(sample_configs))

    async def get_service_samples(self, service_name: str) -> SwagResourceList:
        """Get sample configurations for a specific service."""
        logger.info(f"Getting sample configurations for service: {service_name}")

        # Look for both subdomain and subfolder samples for the service
        patterns = get_possible_sample_filenames(service_name)

        found_configs = []
        for pattern in patterns:
            config_file = self.config_path / pattern
            if config_file.exists():
                found_configs.append(pattern)

        logger.info(f"Found {len(found_configs)} sample configurations for {service_name}")

        return SwagResourceList(configs=sorted(found_configs), total_count=len(found_configs))

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
                    if not original_config.endswith(".conf"):
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
                    temp_file = backup_file.with_suffix(
                        f"{backup_file.suffix}.tmp.{os.getpid()}"
                    )
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
                    file_lock = await self._get_file_lock(backup_file)
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
                        logger.debug(
                            f"Timeout acquiring lock for cleanup of {backup_file.name}"
                        )
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

    async def health_check(self, request: SwagHealthCheckRequest) -> SwagHealthCheckResult:
        """Perform health check on a service endpoint."""
        import time

        logger.info(f"Performing health check for domain: {request.domain}")

        # Try multiple endpoints to test if the reverse proxy is working
        endpoints_to_try = ["/health", "/mcp", "/"]
        urls_to_try = [f"https://{request.domain}{endpoint}" for endpoint in endpoints_to_try]

        for url in urls_to_try:
            logger.debug(f"Trying health check URL: {url}")

            try:
                # Configure SSL context for self-signed certificates

                # Get pooled HTTP session
                session = await self._get_session()

                # Record start time
                start_time = time.time()

                # Use custom timeout for this request
                timeout = aiohttp.ClientTimeout(total=request.timeout)

                async with session.get(
                    url, allow_redirects=request.follow_redirects, timeout=timeout
                ) as response:
                    # Calculate response time
                    response_time_ms = int((time.time() - start_time) * 1000)

                    # Read response body (limited to 1000 chars)
                    response_text = await response.text()
                    response_body = response_text[:1000]
                    if len(response_text) > 1000:
                        response_body += "... (truncated)"

                    # Determine success based on endpoint and status code
                    endpoint = url.split(request.domain)[1] if request.domain in url else "unknown"

                    if 200 <= response.status < 300:
                        # 2xx is always successful
                        success = True
                    elif response.status == 406 and endpoint == "/mcp":
                        # 406 for /mcp means endpoint exists (MCP requires POST)
                        success = True
                    elif response.status == 404 and endpoint in ["/health", "/"]:
                        # 404 for /health or / means try next endpoint
                        success = False
                    else:
                        # Any other HTTP response means proxy is working
                        success = True

                    logger.info(
                        f"Health check for {request.domain} - "
                        f"URL: {url}, Status: {response.status}, "
                        f"Time: {response_time_ms}ms, Success: {success}"
                    )

                    if success:
                        # Return successful result immediately
                        return SwagHealthCheckResult(
                            domain=request.domain,
                            url=url,
                            status_code=response.status,
                            response_time_ms=response_time_ms,
                            response_body=response_body,
                            success=True,
                            error=None,
                        )
                    else:
                        # Log the failure and continue to next endpoint
                        logger.debug(
                            f"Endpoint {endpoint} failed with {response.status}, "
                            "trying next endpoint"
                        )
                        continue

            except TimeoutError:
                error_msg = f"Timeout after {request.timeout} seconds"
                logger.warning(f"Health check timeout for {url}: {error_msg}")
                # Continue to try next URL
                continue

            except aiohttp.ClientConnectorError as e:
                error_msg = f"Connection failed: {str(e)}"
                logger.warning(f"Health check connection error for {url}: {error_msg}")
                # Continue to try next URL
                continue

            except aiohttp.ClientResponseError as e:
                error_msg = f"HTTP error: {e.status} {e.message}"
                logger.warning(f"Health check HTTP error for {url}: {error_msg}")
                # Continue to try next URL for HTTP errors
                continue

            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                logger.warning(f"Health check unexpected error for {url}: {error_msg}")
                # Continue to try next URL
                continue

        # If we get here, all URLs failed
        error_msg = f"All health check URLs failed for domain {request.domain}"
        logger.error(error_msg)

        return SwagHealthCheckResult(
            domain=request.domain,
            url=urls_to_try[0],  # Report the first URL attempted
            status_code=None,
            response_time_ms=None,
            response_body=None,
            success=False,
            error=error_msg,
        )

    async def add_mcp_location(
        self, config_name: str, mcp_path: str = "/mcp", create_backup: bool = True
    ) -> SwagConfigResult:
        """Add MCP location block to existing SWAG configuration."""
        logger.info(f"Adding MCP location block to {config_name} at path {mcp_path}")

        # Validate MCP path format using the existing validator
        try:
            mcp_path = validate_mcp_path(mcp_path)
        except ValueError as e:
            from swag_mcp.services.errors import ValidationError

            raise ValidationError(f"Invalid MCP path: {str(e)}") from e

        # Read existing config
        try:
            content = await self.read_config(config_name)
        except FileNotFoundError:
            # Re-raise FileNotFoundError unchanged
            raise
        except OSError as e:
            handle_os_error(e, "reading configuration file", config_name)

        # Check if MCP location already exists (match '=', '^~', or plain)
        dup_pat = re.compile(rf"^\s*location\s+(?:=\s+|\^~\s+)?{re.escape(mcp_path)}\s*\{{", re.M)
        if dup_pat.search(content):
            raise ValueError(f"MCP location {mcp_path} already exists in configuration")

        # Create backup if requested
        backup_name = None
        if create_backup:
            backup_name = await self._create_backup(config_name)

        try:
            # Begin atomic transaction
            async with self.begin_transaction(f"add_mcp:{config_name}") as txn:
                # Extract current upstream values from config
                upstream_app = self._extract_upstream_value(content, "upstream_app")
                upstream_port = self._extract_upstream_value(content, "upstream_port")
                upstream_proto_raw = self._extract_upstream_value(content, "upstream_proto")
                # Validate and cast upstream_proto to Literal type
                from typing import cast

                if upstream_proto_raw not in ("http", "https"):
                    upstream_proto_raw = "http"  # Default to safe value
                upstream_proto = cast("Literal['http', 'https']", upstream_proto_raw)
                auth_method = self._extract_auth_method(content)

                # Render MCP location block
                mcp_block = await self._render_mcp_location_block(
                    mcp_path=mcp_path,
                    upstream_app=upstream_app,
                    upstream_port=upstream_port,
                    upstream_proto=upstream_proto,
                    auth_method=auth_method,
                )

                # Insert MCP location block before the last closing brace
                updated_content = self._insert_location_block(content, mcp_block)

                # Write updated content (track for rollback)
                config_file = self.config_path / config_name
                await txn.track_file_modification(config_file)
                await self._safe_write_file(
                    config_file, updated_content, f"MCP location addition for {config_name}"
                )

                # Validate nginx syntax before committing (abort on failure)
                if not await self._validate_nginx_syntax(config_file):
                    raise ValueError("Generated configuration contains invalid nginx syntax")

                logger.info(f"Successfully added MCP location block to {config_name}")
                await txn.commit()
                return SwagConfigResult(
                    filename=config_name, content=updated_content, backup_created=backup_name
                )

        except Exception as e:
            logger.error(f"Failed to add MCP location to {config_name}: {str(e)}")
            raise ValueError(f"Failed to add MCP location: {str(e)}") from e

    def _extract_upstream_value(self, content: str, variable_name: str) -> str:
        """Extract upstream variable value from nginx configuration content."""
        # Pattern to match: set $upstream_app "value"; or set $upstream_port "value";
        pattern = rf'set \${variable_name}\s+"([^"]*)"'
        match = re.search(pattern, content)

        if not match:
            raise ValueError(f"Could not find {variable_name} in configuration")

        return str(match.group(1)).strip()

    def _extract_auth_method(self, content: str) -> str:
        """Extract authentication method from nginx configuration content."""
        # Look for auth method includes like: include /config/nginx/authelia-server.conf;
        pattern = r"include\s+/config/nginx/(\w+)-(?:server|location)\.conf;"
        matches = re.findall(pattern, content)

        # Also check for simple auth method includes like: include /config/nginx/ldap.conf;
        if not matches:
            simple_pattern = r"include\s+/config/nginx/(\w+)\.conf;"
            matches = re.findall(simple_pattern, content)

        # Also check for basic auth
        if "auth_basic" in content and "auth_basic_user_file" in content:
            return "basic"

        if not matches:
            return "none"

        # Return the first auth method found
        auth_method = matches[0]

        # Validate it's a known auth method
        valid_auth_methods = ["authelia", "authentik", "ldap", "tinyauth", "basic"]
        if auth_method not in valid_auth_methods:
            return "none"

        return str(auth_method)

    async def _render_mcp_location_block(
        self,
        mcp_path: str,
        upstream_app: str,
        upstream_port: str,
        upstream_proto: Literal["http", "https"],
        auth_method: str,
    ) -> str:
        """Render MCP location block template with provided variables."""
        try:
            # Prepare template variables
            template_vars = {
                "mcp_path": mcp_path,
                "upstream_app": upstream_app,
                "upstream_port": upstream_port,
                "upstream_proto": upstream_proto,
                "auth_method": auth_method,
            }

            # Render template with validated variables using the new hook
            template_name = "mcp_location_block.j2"
            rendered = await self._render_template(template_name, template_vars)
            return rendered

        except ValueError as e:
            # _render_template already provides detailed error messages
            raise e
        except Exception as e:
            raise ValueError(f"Failed to render MCP location block template: {str(e)}") from e

    def _insert_location_block(self, content: str, location_block: str) -> str:
        """Insert location block before the closing brace of the outermost server block."""
        lines = content.splitlines()
        server_start = -1
        # Find the start of the server block
        for i, line in enumerate(lines):
            if re.match(r"^\s*server\s*\{", line):
                server_start = i
                break
        if server_start == -1:
            raise ValueError("Could not find start of server block")
        # Track brace nesting from the server block start
        brace_count = 0
        insert_index = -1
        for i in range(server_start, len(lines)):
            # Count braces in the line
            brace_count += lines[i].count("{")
            brace_count -= lines[i].count("}")
            # When brace_count returns to zero, we've found the server block's closing brace
            if brace_count == 0:
                insert_index = i
                break
        if insert_index == -1:
            raise ValueError("Could not find server block closing brace")
        # Insert the location block before the closing brace
        lines.insert(insert_index, "")  # Add empty line for spacing
        lines.insert(insert_index + 1, location_block)
        return "\n".join(lines)
