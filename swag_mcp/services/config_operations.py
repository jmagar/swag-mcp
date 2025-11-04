"""Configuration CRUD operations service.

This module provides core configuration file operations including create, read,
update, and delete (CRUD) functionality with automatic nginx syntax validation.
"""

import logging
import re
import tempfile
from pathlib import Path

import aiofiles

from swag_mcp.core.constants import LIST_FILTERS
from swag_mcp.models.config import (
    ListFilterType,
    SwagConfigRequest,
    SwagConfigResult,
    SwagEditRequest,
    SwagListResult,
    SwagRemoveRequest,
    SwagUpdateRequest,
)
from swag_mcp.services.backup_manager import BackupManager
from swag_mcp.services.config_updaters import ConfigFieldUpdaters
from swag_mcp.services.file_operations import FileOperations
from swag_mcp.services.template_manager import TemplateManager
from swag_mcp.services.validation import ValidationService
from swag_mcp.utils.error_handlers import handle_os_error
from swag_mcp.utils.formatters import build_template_filename
from swag_mcp.utils.validators import (
    detect_and_handle_encoding,
    validate_config_filename,
    validate_domain_format,
    validate_file_content_safety_async,
    validate_service_name,
    validate_upstream_port,
)

logger = logging.getLogger(__name__)


class ConfigOperations:
    """Service for SWAG configuration CRUD operations.

    Provides core configuration file management including:
    - Listing configurations with filtering
    - Reading configuration content
    - Creating configurations from templates with nginx validation
    - Updating entire configuration content with nginx validation
    - Updating specific configuration fields
    - Removing configurations with optional backup

    All write operations include automatic nginx syntax validation to prevent
    invalid configurations from being written.
    """

    def __init__(
        self,
        config_path: Path,
        template_manager: TemplateManager,
        validation: ValidationService,
        backup_manager: BackupManager,
        file_ops: FileOperations,
        updaters: ConfigFieldUpdaters,
    ):
        """Initialize configuration operations service.

        Args:
            config_path: Path to SWAG proxy configurations directory
            template_manager: Template rendering service
            validation: Validation service for nginx syntax checking
            backup_manager: Backup creation and management service
            file_ops: File operation utilities
            updaters: Configuration field update handlers
        """
        self.config_path = config_path
        self.template_manager = template_manager
        self.validation = validation
        self.backup_manager = backup_manager
        self.file_ops = file_ops
        self.updaters = updaters
        self._directory_checked = False

        logger.info(f"Initialized ConfigOperations with path: {config_path}")

    def _ensure_config_directory(self) -> None:
        """Ensure the configuration directory exists."""
        if not self._directory_checked:
            self.config_path.mkdir(parents=True, exist_ok=True)
            self._directory_checked = True

    async def list_configs(self, list_filter: ListFilterType = "all") -> SwagListResult:
        """List configuration files based on filter type.

        Args:
            list_filter: Filter type - "all", "active", or "samples"

        Returns:
            SwagListResult containing list of configs and total count

        Raises:
            ValueError: If list_filter is invalid
        """
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
        """Read configuration file content.

        Args:
            config_name: Name of configuration file to read

        Returns:
            Configuration file content as string

        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If file contains binary content or invalid encoding
            OSError: For file system errors
        """
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
            import errno

            raise OSError(
                errno.EIO,
                f"Unexpected error reading configuration file: {validated_name}: {str(e)}",
            ) from e

        logger.info(f"Successfully read {len(content)} characters from {validated_name}")
        return content

    async def create_config(self, request: SwagConfigRequest) -> SwagConfigResult:
        """Create new configuration from template with nginx validation.

        This method creates a new SWAG configuration file from a template and
        automatically validates the nginx syntax before writing the file.

        Args:
            request: Configuration creation request with all required parameters

        Returns:
            SwagConfigResult with filename and content

        Raises:
            ValueError: If template rendering or validation fails
            OSError: For file system errors
        """
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
        if not re.match(r"^[A-Za-z0-9_.-]+$", request.upstream_app):
            raise ValueError(f"Invalid upstream app name: {request.upstream_app}")

        # Determine template and filename
        template_name = build_template_filename(template_type)
        filename = config_name  # Use the provided config_name directly

        # Perform configuration creation with proper locking to prevent race conditions
        config_file = self.config_path / filename
        file_lock = await self.file_ops.get_file_lock(config_file)
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
                content = await self.template_manager.render_template(template_name, template_vars)
            except ValueError as e:
                # Template rendering already handles TemplateNotFound and other exceptions
                raise e

            # CRITICAL SAFETY FEATURE: Validate nginx syntax before writing
            # Write to temporary file first for validation
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".conf", delete=False
            ) as temp_file:
                temp_file.write(content)
                temp_path = Path(temp_file.name)

            try:
                if not await self.validation.validate_nginx_syntax(temp_path):
                    raise ValueError("Generated configuration contains invalid nginx syntax")
            finally:
                temp_path.unlink(missing_ok=True)

            # Write configuration safely with proper error handling (no additional lock needed)
            await self.file_ops.safe_write_file(
                config_file, content, f"configuration creation for {filename}", use_lock=False
            )

        logger.info(f"Successfully created configuration: {filename}")

        return SwagConfigResult(filename=filename, content=content)

    async def update_config(self, edit_request: SwagEditRequest) -> SwagConfigResult:
        """Update configuration with optional backup and nginx validation.

        This method updates an entire configuration file and automatically validates
        the nginx syntax before writing the changes.

        Args:
            edit_request: Configuration edit request with new content

        Returns:
            SwagConfigResult with updated content and backup info

        Raises:
            ValueError: If validation fails or content is invalid
            OSError: For file system errors
        """
        logger.info(f"Updating configuration: {edit_request.config_name}")

        # Validate config name directly (must be full filename)
        validated_name = validate_config_filename(edit_request.config_name)

        # Security validation: validate configuration content for dangerous patterns
        validated_content = self.validation.validate_config_content(
            edit_request.new_content or "", validated_name
        )

        config_file = self.config_path / validated_name
        backup_name = None

        # Create backup if requested and file exists
        if edit_request.create_backup and config_file.exists():
            backup_name = await self.backup_manager.create_backup(validated_name)
            logger.info(f"Created backup: {backup_name}")

        # CRITICAL SAFETY FEATURE: Validate nginx syntax before writing
        # Write to temporary file first for validation
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as temp_file:
            temp_file.write(validated_content)
            temp_path = Path(temp_file.name)

        try:
            if not await self.validation.validate_nginx_syntax(temp_path):
                raise ValueError("Updated configuration contains invalid nginx syntax")
        finally:
            temp_path.unlink(missing_ok=True)

        # Write validated content safely with proper error handling
        await self.file_ops.safe_write_file(
            config_file, validated_content, f"configuration update for {validated_name}"
        )

        logger.info(f"Successfully updated configuration: {validated_name}")

        return SwagConfigResult(
            filename=validated_name,
            content=validated_content,
            backup_created=backup_name,
        )

    async def update_config_field(self, update_request: SwagUpdateRequest) -> SwagConfigResult:
        """Update specific field in existing configuration using targeted updaters.

        This method delegates to specific field update handlers based on the
        update_field value. All field updates include nginx validation.

        Args:
            update_request: Configuration update request with field and value

        Returns:
            SwagConfigResult with updated content and backup info

        Raises:
            ValueError: If update field is unsupported or validation fails
            FileNotFoundError: If configuration file doesn't exist
        """
        logger.info(f"Updating {update_request.update_field} in {update_request.config_name}")

        # Read existing config
        content = await self.read_config(update_request.config_name)

        # Create backup if requested
        backup_name = None
        if update_request.create_backup:
            backup_name = await self.backup_manager.create_backup(update_request.config_name)

        # Delegate to ConfigFieldUpdaters service
        return await self.updaters.update_field(
            update_request=update_request,
            current_content=content,
            backup_name=backup_name,
            config_path=self.config_path,
        )

    async def remove_config(self, remove_request: SwagRemoveRequest) -> SwagConfigResult:
        """Remove configuration with optional backup.

        Args:
            remove_request: Configuration removal request

        Returns:
            SwagConfigResult with removed content and backup info

        Raises:
            FileNotFoundError: If configuration file doesn't exist
            ValueError: If file is unsafe to read
            OSError: For file system errors
        """
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
            import errno

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
            backup_name = await self.backup_manager.create_backup(validated_name)
            logger.info(f"Created backup: {backup_name}")

        # Remove the configuration file with proper error handling
        try:
            config_file.unlink()
        except OSError as e:
            handle_os_error(e, "removing configuration file", validated_name)
        except Exception as e:
            import errno

            raise OSError(
                errno.EIO,
                f"Unexpected error removing configuration file: {validated_name}: {str(e)}",
            ) from e

        logger.info(f"Successfully removed configuration: {validated_name}")

        return SwagConfigResult(
            filename=validated_name, content=content, backup_created=backup_name
        )
