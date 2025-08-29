"""Core SWAG configuration management service."""

import asyncio
import errno
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import aiofiles
from jinja2 import FileSystemLoader, TemplateNotFound
from jinja2.sandbox import SandboxedEnvironment

from ..core.config import config
from ..models.config import (
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
from ..utils.error_handlers import handle_os_error
from ..utils.formatters import (
    build_config_filename,
    build_template_filename,
    get_possible_config_filenames,
    get_possible_sample_filenames,
)
from ..utils.validators import (
    detect_and_handle_encoding,
    normalize_unicode_text,
    validate_config_filename,
    validate_domain_format,
    validate_file_content_safety,
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
        self.config_path = config_path or config.proxy_confs_path
        self.template_path = template_path or config.template_path
        self._directory_checked = False

        # Initialize secure Jinja2 environment with sandboxing
        self.template_env = self._create_secure_template_environment()

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

        logger.info(f"Initialized SWAG manager with proxy configs path: {self.config_path}")

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
            """Rollback all changes made in this transaction."""
            rollback_errors = []

            # Remove created files
            for file_path in reversed(self.created_files):  # Reverse order for safety
                try:
                    if file_path.exists():
                        file_path.unlink()
                        logger.debug(f"Rollback: removed created file {file_path}")
                except Exception as e:
                    rollback_errors.append(f"Failed to remove created file {file_path}: {e}")

            # Restore modified files
            for file_path, original_content in reversed(self.modified_files):
                try:
                    # Use the manager's safe write with no lock (we're in transaction context)
                    await self.manager._safe_write_file(
                        file_path, original_content, f"rollback of {file_path}", use_lock=False
                    )
                    logger.debug(f"Rollback: restored modified file {file_path}")
                except Exception as e:
                    rollback_errors.append(f"Failed to restore modified file {file_path}: {e}")

            # Restore deleted files
            for file_path, original_content in self.deleted_files:
                try:
                    # Use the manager's safe write with no lock
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
            autoescape=False,  # NGINX configs don't need HTML escaping
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Remove dangerous globals and built-ins to prevent code execution
        env.globals = {
            # Only allow safe built-in functions
            "range": range,
            "len": len,
            "str": str,
            "int": int,
            "bool": bool,
            "list": list,
            "dict": dict,
            "zip": zip,
            # Math functions that are safe
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
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

    def _validate_template_variables(self, template_vars: dict) -> dict:
        """Validate and sanitize template variables to prevent injection attacks.

        Args:
            template_vars: Dictionary of variables to pass to template

        Returns:
            Sanitized dictionary safe for template rendering

        Raises:
            ValueError: If any template variable contains dangerous content

        """
        sanitized_vars = {}

        # Patterns that should never appear in template variables
        dangerous_patterns = [
            # Template injection patterns
            r"\{\{.*?\}\}",  # Jinja2 expressions
            r"\{%.*?%\}",  # Jinja2 statements
            r"\{#.*?#\}",  # Jinja2 comments
            r"\$\{.*?\}",  # Other template syntax
            # Python code execution patterns
            r"__[a-zA-Z_]+__",  # Dunder methods
            r"eval\s*\(",  # eval calls
            r"exec\s*\(",  # exec calls
            r"import\s+\w+",  # import statements
            r"from\s+\w+\s+import",  # from...import
            r"subprocess",  # subprocess module
            r"os\.system",  # os.system calls
            # File system access patterns
            r"open\s*\(",  # file open calls
            r"file\s*\(",  # file constructor
            r"\.read\s*\(",  # read methods
            r"\.write\s*\(",  # write methods
            # Network/URL patterns that might be dangerous
            r"file://",  # file:// URLs
            r"ftp://",  # FTP URLs (might be used for exfiltration)
            # Script injection patterns
            r"<script.*?>",  # Script tags
            r"javascript:",  # JavaScript URLs
            r"data:.*base64",  # Data URLs with base64
            # Shell command patterns
            r"[;&|`$]",  # Shell metacharacters
        ]

        for key, value in template_vars.items():
            # Ensure key is safe (only allow alphanumeric and underscores)
            if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", key):
                raise ValueError(f"Invalid template variable name: {key}")

            # Convert value to string for pattern checking
            str_value = str(value)

            # Check for dangerous patterns
            for pattern in dangerous_patterns:
                if re.search(pattern, str_value, re.IGNORECASE):
                    logger.warning(
                        f"Blocked dangerous content in template variable '{key}': {pattern}"
                    )
                    raise ValueError(
                        f"Template variable '{key}' contains potentially dangerous content"
                    )

            # Additional validation for specific variable types
            if key in ["service_name", "server_name", "upstream_app"]:
                # Ensure these don't contain path traversal
                if ".." in str_value or "/" in str_value or "\\" in str_value:
                    raise ValueError(f"Template variable '{key}' contains invalid path characters")

                # Ensure reasonable length
                if len(str_value) > 1000:
                    raise ValueError(f"Template variable '{key}' is too long")

            # Store sanitized value
            sanitized_vars[key] = value

        logger.debug(f"Validated {len(sanitized_vars)} template variables")
        return sanitized_vars

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

        logger.debug(
            f"Validated configuration content for '{config_name}' ({len(content)} characters)"
        )
        return content

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
            normalized_content = normalize_unicode_text(content, remove_bom=True)
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
                        os.fsync(f.fileno())

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

    def prepare_config_defaults(
        self, auth_method: str, enable_quic: bool, config_type: str | None
    ) -> tuple[str, bool, str]:
        """Prepare configuration defaults from parameters and config.

        Args:
            auth_method: Authentication method parameter
            enable_quic: QUIC enable parameter
            config_type: Configuration type parameter

        Returns:
            Tuple of (auth_method, enable_quic, config_type) with defaults applied

        """
        # Use defaults from environment configuration if not specified
        if auth_method == "none":
            auth_method = "authelia"  # Default to Authelia for security
        if not enable_quic:
            enable_quic = config.default_quic_enabled
        if config_type is None:
            config_type = config.default_config_type

        return auth_method, enable_quic, config_type

    def _resolve_config_filename(self, config_name: str, allow_create: bool = False) -> str:
        """Resolve config name to actual filename by auto-detecting extension.

        Args:
            config_name: Either a full filename with extension or just a service name
            allow_create: If True, return best filename even if file doesn't exist

        Returns:
            The resolved filename (existing or best match for creation)

        Raises:
            FileNotFoundError: If no matching configuration file is found and allow_create is False

        """
        # If already has extension, use as-is
        if config_name.endswith((".conf", ".sample")):
            config_file = self.config_path / config_name
            if config_file.exists() or allow_create:
                return config_name
            else:
                raise FileNotFoundError(f"Configuration {config_name} not found")

        # Try different extensions in order of preference
        candidates = get_possible_config_filenames(config_name, config.default_config_type)
        candidates.extend(
            [
                build_config_filename(config_name, "mcp-subdomain"),
                build_config_filename(config_name, "mcp-subfolder"),
                f"{config_name}.conf",  # fallback
            ]
        )

        # Remove duplicates while preserving order
        seen = set()
        unique_candidates = []
        for candidate in candidates:
            if candidate not in seen:
                seen.add(candidate)
                unique_candidates.append(candidate)

        # Find first existing file
        for candidate in unique_candidates:
            config_file = self.config_path / candidate
            if config_file.exists():
                logger.info(f"Resolved '{config_name}' to '{candidate}'")
                return candidate

        # If allow_create is True, return the best candidate for creation
        if allow_create and unique_candidates:
            best_candidate = unique_candidates[0]  # Use default config type
            logger.info(f"Resolved '{config_name}' to '{best_candidate}' (for creation)")
            return best_candidate

        # No file found, provide helpful error message
        available_files = [f.name for f in self.config_path.glob("*.conf")]
        available_files.extend([f.name for f in self.config_path.glob("*.sample")])
        available_files.sort()

        error_msg = (
            f"No configuration file found for '{config_name}'. "
            f"Tried: {', '.join(unique_candidates)}"
        )
        if available_files:
            error_msg += f". Available files: {', '.join(available_files)}"

        raise FileNotFoundError(error_msg)

    async def list_configs(self, config_type: str = "all") -> SwagListResult:
        """List configuration files based on type."""
        logger.info(f"Listing configurations of type: {config_type}")
        self._ensure_config_directory()

        configs = []

        if config_type in ["all", "active"]:
            # List active configurations (.conf files, not .sample)
            active_configs = [
                f.name for f in self.config_path.glob("*.conf") if not f.name.endswith(".sample")
            ]
            configs.extend(active_configs)

        if config_type in ["all", "samples"]:
            # List sample configurations (.sample files)
            sample_configs = [f.name for f in self.config_path.glob("*.sample")]
            configs.extend(sample_configs)

        # Remove duplicates and sort
        configs = sorted(set(configs))

        logger.info(f"Found {len(configs)} configurations")

        return SwagListResult(configs=configs, total_count=len(configs), config_type=config_type)

    async def read_config(self, config_name: str) -> str:
        """Read configuration file content."""
        logger.info(f"Reading configuration: {config_name}")
        self._ensure_config_directory()

        # Resolve config name to actual filename and validate it
        resolved_name = self._resolve_config_filename(config_name)
        validated_name = validate_config_filename(resolved_name)

        config_file = self.config_path / validated_name

        # Security validation: ensure file is safe to read as text
        if not validate_file_content_safety(config_file):
            raise ValueError(
                f"Configuration file {validated_name} contains binary content "
                "or is unsafe to read"
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
        logger.info(f"Creating {request.config_type} configuration for {request.service_name}")
        self._ensure_config_directory()

        # Security validation: validate all input parameters
        validated_service_name = validate_service_name(request.service_name)
        validated_server_name = validate_domain_format(request.server_name)
        validated_port = validate_upstream_port(request.upstream_port)

        # Determine template and filename
        template_name = build_template_filename(request.config_type)
        if request.config_type == "mcp-subdomain":
            filename = build_config_filename(validated_service_name, "subdomain")
        elif request.config_type == "mcp-subfolder":
            filename = build_config_filename(validated_service_name, "subfolder")
        else:
            filename = build_config_filename(validated_service_name, request.config_type)

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

                # Validate all template variables for security
                safe_template_vars = self._validate_template_variables(template_vars)

                # Render template with validated variables
                template = self.template_env.get_template(template_name)
                content = template.render(**safe_template_vars)
            except TemplateNotFound as e:
                raise ValueError(f"Template {template_name} not found") from e
            except Exception as e:
                raise ValueError(f"Failed to render template: {str(e)}") from e

            # Write configuration safely with proper error handling (no additional lock needed)
            await self._safe_write_file(
                config_file, content, f"configuration creation for {filename}", use_lock=False
            )

        logger.info(f"Successfully created configuration: {filename}")

        return SwagConfigResult(filename=filename, content=content)

    async def update_config(self, edit_request: SwagEditRequest) -> SwagConfigResult:
        """Update configuration with optional backup."""
        logger.info(f"Updating configuration: {edit_request.config_name}")

        # Resolve config name to actual filename and validate it (allow creation for edit)
        resolved_name = self._resolve_config_filename(edit_request.config_name, allow_create=True)
        validated_name = validate_config_filename(resolved_name)

        # Security validation: validate configuration content for dangerous patterns
        validated_content = self._validate_config_content(edit_request.new_content, validated_name)

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
        """Update specific field in existing configuration using regex replacement."""
        import re

        logger.info(f"Updating {update_request.update_field} in {update_request.config_name}")

        # Read existing config
        content = await self.read_config(update_request.config_name)

        # Create backup if requested
        backup_name = None
        if update_request.create_backup:
            backup_name = await self._create_backup(update_request.config_name)

        # Apply targeted replacements based on field type
        if update_request.update_field == "port":
            # Update both upstream_port locations
            pattern = r"set \$upstream_port \d+;"
            replacement = f"set $upstream_port {update_request.update_value};"
            updated_content = re.sub(pattern, replacement, content)

        elif update_request.update_field == "upstream":
            # Update upstream_app
            pattern = r"set \$upstream_app [^;]+;"
            replacement = f"set $upstream_app {update_request.update_value};"
            updated_content = re.sub(pattern, replacement, content)

        elif update_request.update_field == "app":
            # Update both app and port (format: "app:port")
            if ":" not in update_request.update_value:
                raise ValueError("app field requires format 'app:port'")
            app, port = update_request.update_value.split(":", 1)

            # Update app
            pattern = r"set \$upstream_app [^;]+;"
            replacement = f"set $upstream_app {app};"
            updated_content = re.sub(pattern, replacement, content)

            # Update port
            pattern = r"set \$upstream_port \d+;"
            replacement = f"set $upstream_port {port};"
            updated_content = re.sub(pattern, replacement, updated_content)
        else:
            raise ValueError(f"Unsupported update field: {update_request.update_field}")

        # Write updated content
        config_file = self.config_path / update_request.config_name
        await self._safe_write_file(
            config_file, updated_content, f"field update for {update_request.config_name}"
        )

        logger.info(
            f"Successfully updated {update_request.update_field} in {update_request.config_name}"
        )

        return SwagConfigResult(
            filename=update_request.config_name,
            content=updated_content,
            backup_created=backup_name,
        )

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
                backup_name = f"{validated_name}.backup.{timestamp}"
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
        template_name = build_template_filename(config_type)
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
        from ..core.constants import ALL_CONFIG_TYPES

        results = {}
        for config_type in ALL_CONFIG_TYPES:
            template_name = build_template_filename(config_type)
            try:
                self.template_env.get_template(template_name)
                results[template_name] = True
                logger.debug(f"Template validation passed: {template_name}")
            except TemplateNotFound:
                results[template_name] = False
                logger.warning(f"Template validation failed: {template_name}")

        return results

    async def remove_config(self, remove_request: SwagRemoveRequest) -> SwagConfigResult:
        """Remove configuration with optional backup."""
        logger.info(f"Removing configuration: {remove_request.config_name}")

        # Resolve config name to actual filename and validate it
        resolved_name = self._resolve_config_filename(remove_request.config_name)
        validated_name = validate_config_filename(resolved_name)

        config_file = self.config_path / validated_name

        # Security validation: ensure file is safe to read as text
        if not validate_file_content_safety(config_file):
            raise ValueError(
                f"Configuration file {validated_name} contains binary content "
                "or is unsafe to read"
            )

        # Read content for backup and response with error handling and Unicode normalization
        try:
            # Read file with proper encoding detection and Unicode normalization
            async with aiofiles.open(config_file, "rb") as f:
                raw_content = await f.read()

            # Detect encoding and normalize Unicode
            content = detect_and_handle_encoding(raw_content)

        except OSError as e:
            if e.errno == errno.EACCES:
                raise OSError(
                    errno.EACCES,
                    f"Permission denied reading configuration file for removal: {validated_name}",
                ) from e
            elif e.errno == errno.EIO:
                raise OSError(
                    errno.EIO,
                    (
                        f"I/O error reading configuration file for removal: {validated_name}. "
                        "This may indicate disk corruption."
                    ),
                ) from e
            else:
                raise OSError(
                    e.errno or errno.EIO,
                    (
                        f"Error reading configuration file for removal: {validated_name}: "
                        f"{str(e)}"
                    ),
                ) from e
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
        """Get SWAG logs by reading log files directly from mounted volume."""
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

            # Read last N lines from the file efficiently
            async with aiofiles.open(log_file_path, encoding="utf-8", errors="ignore") as f:
                lines = await f.readlines()
                # Get last N lines
                result_lines = (
                    lines[-logs_request.lines :] if len(lines) > logs_request.lines else lines
                )

            if not result_lines:
                return f"No log entries found in {logs_request.log_type} log."

            result = "".join(result_lines)
            logger.info(
                f"Successfully retrieved {len(result_lines)} lines from {logs_request.log_type}"
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

    async def cleanup_old_backups(self, retention_days: int | None = None) -> int:
        """Clean up old backup files beyond retention period with proper concurrency control."""
        import re

        if retention_days is None:
            retention_days = config.backup_retention_days

        logger.info(f"Cleaning up backups older than {retention_days} days")

        # Use cleanup lock to prevent multiple cleanup operations
        # and coordinate with backup creation
        async with self._cleanup_lock, self._backup_lock:
            cutoff_time = datetime.now().timestamp() - (retention_days * 24 * 60 * 60)
            cleaned_count = 0

            # Enhanced pattern: filename.backup.YYYYMMDD_HHMMSS[_microseconds][.counter]
            # This matches our improved backup naming scheme
            backup_pattern = re.compile(r"^.+\.backup\.\d{8}_\d{6}(_\d{6})?(\.\d+)?$")

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
                    file_lock = await self._get_file_lock(backup_file)
                    if file_lock.locked():
                        logger.debug(f"Skipping locked backup file: {backup_file.name}")
                        continue

                    # Attempt to acquire lock briefly for deletion
                    try:
                        # Use asyncio.wait_for to timeout if lock can't be acquired quickly
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
                import ssl

                import aiohttp

                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                # Create connector with SSL context
                connector = aiohttp.TCPConnector(ssl=ssl_context)

                # Record start time
                start_time = time.time()

                async with (
                    aiohttp.ClientSession(
                        connector=connector, timeout=aiohttp.ClientTimeout(total=request.timeout)
                    ) as session,
                    session.get(url, allow_redirects=request.follow_redirects) as response,
                ):
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
