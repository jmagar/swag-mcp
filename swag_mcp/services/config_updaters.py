"""Configuration field updater module for SWAG MCP."""

import logging
import re
import tempfile
from pathlib import Path
from re import Match
from typing import TYPE_CHECKING

from swag_mcp.models.config import SwagConfigResult, SwagUpdateRequest
from swag_mcp.services.file_operations import FileOperations
from swag_mcp.services.validation import ValidationService
from swag_mcp.utils.error_codes import (
    ErrorCode,
    create_operation_error,
    create_validation_error,
)
from swag_mcp.utils.validators import validate_mcp_path

if TYPE_CHECKING:
    from swag_mcp.services.swag_manager import SwagManagerService

logger = logging.getLogger(__name__)


class MCPOperations:
    """Wrapper for MCP-related operations (adapter for incremental refactoring)."""

    def __init__(self, swag_manager: "SwagManagerService") -> None:
        """Initialize MCP operations wrapper.

        Args:
            swag_manager: SwagManagerService instance to delegate to

        """
        self.swag_manager = swag_manager

    async def add_mcp_location(
        self, config_name: str, mcp_path: str = "/mcp", create_backup: bool = True
    ) -> SwagConfigResult:
        """Add MCP location block to existing SWAG configuration.

        Delegates to SwagManagerService.add_mcp_location() method.

        Args:
            config_name: Name of configuration file
            mcp_path: Path for MCP location block (default: /mcp)
            create_backup: Whether to create backup before modification

        Returns:
            SwagConfigResult with operation results

        """
        return await self.swag_manager.add_mcp_location(
            config_name=config_name, mcp_path=mcp_path, create_backup=create_backup
        )


class ConfigFieldUpdaters:
    """Handles field-specific configuration updates."""

    def __init__(
        self,
        config_path: Path,
        validation: ValidationService,
        file_ops: FileOperations,
        mcp_ops: MCPOperations,
    ) -> None:
        """Initialize configuration field updaters.

        Args:
            config_path: Path to SWAG proxy configurations directory
            validation: ValidationService instance for nginx syntax validation
            file_ops: FileOperations instance for safe file I/O
            mcp_ops: MCPOperations instance for MCP-related operations

        """
        self.config_path = config_path
        self.validation = validation
        self.file_ops = file_ops
        self.mcp_ops = mcp_ops

    async def update_field(
        self,
        update_request: SwagUpdateRequest,
        current_content: str,
        backup_name: str | None,
        config_path: Path,
    ) -> SwagConfigResult:
        """Dispatch to appropriate field updater based on update_field value.

        Args:
            update_request: Update request with field and value
            current_content: Current configuration content
            backup_name: Backup filename if backup was created
            config_path: Path to configuration directory (unused, kept for signature)

        Returns:
            SwagConfigResult from the appropriate field updater

        Raises:
            ValueError: If update_field is not supported

        """
        # Dispatch to specific updater methods
        updaters = {
            "port": self.update_port_field,
            "upstream": self.update_upstream_field,
            "app": self.update_app_field,
            "add_mcp": self.update_mcp_field,
        }

        updater = updaters.get(update_request.update_field)
        if not updater:
            raise ValueError(
                f"Unsupported update field: {update_request.update_field}. "
                f"Supported fields: {', '.join(updaters.keys())}"
            )

        return await updater(update_request, current_content, backup_name)

    async def update_port_field(
        self, update_request: SwagUpdateRequest, content: str, backup_name: str | None
    ) -> SwagConfigResult:
        """Update port field in configuration.

        Args:
            update_request: Update request with port value
            content: Current configuration content
            backup_name: Backup filename if backup was created

        Returns:
            SwagConfigResult with updated configuration

        Raises:
            ValidationError: If port value is invalid

        """
        # Validate port value
        try:
            port_value = int(update_request.update_value)
            if not (1 <= port_value <= 65535):
                raise create_validation_error(
                    ErrorCode.INVALID_PORT_NUMBER,
                    f"Port number must be between 1-65535, got: {port_value}",
                )
        except (ValueError, TypeError) as e:
            raise create_validation_error(
                ErrorCode.INVALID_PORT_NUMBER,
                f"Invalid port value: {update_request.update_value}",
                context={"original_error": str(e)},
            ) from e

        updated_content = content
        changes_made = False

        # Try template format first: set $upstream_port
        pattern = r'set \$upstream_port ("[^"]*"|[^;]+);'
        replacement = rf'set $upstream_port "{port_value}";'
        new_content, port_replacements = re.subn(pattern, replacement, updated_content)

        if port_replacements > 0:
            updated_content = new_content
            changes_made = True
            logger.debug(f"Updated {port_replacements} template port references to {port_value}")
        else:
            # Try simple nginx format: proxy_pass http://app:port
            pattern = r"proxy_pass\s+https?://([^/:]+):(\d+)([^;]*);"

            def replace_proxy_port(match: Match[str]) -> str:
                app = match.group(1)
                path = match.group(3) or ""
                protocol = "https" if "https" in match.group(0) else "http"
                return f"proxy_pass {protocol}://{app}:{port_value}{path};"

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

        return await self.finalize_config_update(
            update_request, updated_content, backup_name, changes_made
        )

    async def update_upstream_field(
        self, update_request: SwagUpdateRequest, content: str, backup_name: str | None
    ) -> SwagConfigResult:
        """Update upstream app field in configuration.

        Args:
            update_request: Update request with upstream app name
            content: Current configuration content
            backup_name: Backup filename if backup was created

        Returns:
            SwagConfigResult with updated configuration

        Raises:
            ValidationError: If upstream app name is invalid

        """
        # Validate upstream app name
        if not re.match(r"^[A-Za-z0-9_.-]+$", update_request.update_value):
            raise create_validation_error(
                ErrorCode.INVALID_SERVICE_NAME,
                f"Invalid upstream app name: {update_request.update_value}",
            )

        updated_content = content
        changes_made = False

        # Try template format first: set $upstream_app
        pattern = r'set \$upstream_app ("[^"]*"|[^;]+);'
        replacement = rf'set $upstream_app "{update_request.update_value}";'
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
            pattern = r"proxy_pass\s+https?://([^/:]+)(:\d+)?([^;]*);"

            def replace_proxy_pass(match: Match[str]) -> str:
                port = match.group(2) or ""
                path = match.group(3) or ""
                protocol = "https" if "https" in match.group(0) else "http"
                return f"proxy_pass {protocol}://{update_request.update_value}{port}{path};"

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

        return await self.finalize_config_update(
            update_request, updated_content, backup_name, changes_made
        )

    async def update_app_field(
        self, update_request: SwagUpdateRequest, content: str, backup_name: str | None
    ) -> SwagConfigResult:
        """Update both app and port field in configuration.

        Args:
            update_request: Update request with app:port value
            content: Current configuration content
            backup_name: Backup filename if backup was created

        Returns:
            SwagConfigResult with updated configuration

        Raises:
            ValidationError: If app or port values are invalid

        """
        # Update both app and port (format: "app:port")
        if ":" not in update_request.update_value:
            raise create_validation_error(
                ErrorCode.INVALID_UPDATE_FIELD, "app field requires format 'app:port'"
            )

        app, port = update_request.update_value.split(":", 1)

        # Validate app name
        if not re.match(r"^[A-Za-z0-9_.-]+$", app):
            raise create_validation_error(
                ErrorCode.INVALID_SERVICE_NAME, f"Invalid app name: {app}"
            )

        # Validate port
        try:
            port_value = int(port)
            if not (1 <= port_value <= 65535):
                raise create_validation_error(
                    ErrorCode.INVALID_PORT_NUMBER,
                    f"Port number must be between 1-65535, got: {port_value}",
                )
        except (ValueError, TypeError) as e:
            raise create_validation_error(
                ErrorCode.INVALID_PORT_NUMBER,
                f"Invalid port value: {port}",
                context={"original_error": str(e)},
            ) from e

        updated_content = content
        changes_made = False

        # Try template format first
        app_pattern = r'set \$upstream_app ("[^"]*"|[^;]+);'
        app_replacement = rf'set $upstream_app "{app}";'
        new_content, app_replacements = re.subn(app_pattern, app_replacement, updated_content)

        if app_replacements > 0:
            updated_content = new_content
            changes_made = True

        port_pattern = r'set \$upstream_port ("[^"]*"|[^;]+);'
        port_replacement = rf'set $upstream_port "{port_value}";'
        new_content, port_replacements = re.subn(port_pattern, port_replacement, updated_content)

        if port_replacements > 0:
            updated_content = new_content
            changes_made = True

        # If template format didn't work, try simple nginx format
        if not changes_made:
            pattern = r"proxy_pass\s+https?://([^/:]+)(:\d+)?([^;]*);"

            def replace_proxy_app_port(match: Match[str]) -> str:
                path = match.group(3) or ""
                protocol = "https" if "https" in match.group(0) else "http"
                return f"proxy_pass {protocol}://{app}:{port_value}{path};"

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

        return await self.finalize_config_update(
            update_request, updated_content, backup_name, changes_made
        )

    async def update_mcp_field(
        self, update_request: SwagUpdateRequest, content: str, backup_name: str | None
    ) -> SwagConfigResult:
        """Add MCP location block to configuration.

        Args:
            update_request: Update request with MCP path value
            content: Current configuration content (unused, kept for signature consistency)
            backup_name: Backup filename (unused, kept for signature consistency)

        Returns:
            SwagConfigResult with updated configuration

        Raises:
            ValidationError: If MCP path is invalid

        """
        # Add MCP location block - delegate to the dedicated method
        mcp_path = update_request.update_value if update_request.update_value else "/mcp"

        # Validate the computed MCP path
        try:
            validated_mcp_path = validate_mcp_path(mcp_path)
        except ValueError as e:
            raise create_validation_error(
                ErrorCode.INVALID_MCP_PATH, f"Invalid MCP path: {str(e)}"
            ) from e

        # Call the add_mcp_location method with validated path
        return await self.mcp_ops.add_mcp_location(
            config_name=update_request.config_name,
            mcp_path=validated_mcp_path,
            create_backup=update_request.create_backup,
        )

    async def finalize_config_update(
        self,
        update_request: SwagUpdateRequest,
        updated_content: str,
        backup_name: str | None,
        changes_made: bool,
    ) -> SwagConfigResult:
        """Finalize configuration update with validation and file writing.

        Args:
            update_request: Original update request
            updated_content: Updated configuration content
            backup_name: Backup filename if backup was created
            changes_made: Whether any changes were actually made

        Returns:
            SwagConfigResult with operation results

        Raises:
            OperationError: If no changes were made or validation fails

        """
        # Validate that changes were actually made
        if not changes_made:
            field = update_request.update_field
            config_name = update_request.config_name

            format_map = {
                "upstream": "'set $upstream_app' variables or 'proxy_pass' directives",
                "port": "'set $upstream_port' variables or 'proxy_pass' directives with ports",
                "app": (
                    "'set $upstream_app' and 'set $upstream_port' variables or "
                    "'proxy_pass' directives"
                ),
            }

            expected_format = format_map.get(field, "template format")

            raise create_operation_error(
                ErrorCode.FILE_WRITE_ERROR,
                f"No changes made to {config_name}. The configuration file doesn't "
                f"contain the expected format for '{field}' updates",
                context={
                    "expected_format": expected_format,
                    "supports": "both template-generated and standard nginx configurations",
                },
            )

        # Write updated content to a temporary file for validation
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as temp_file:
            temp_file.write(updated_content)
            temp_path = Path(temp_file.name)

        try:
            # Validate nginx syntax before committing changes
            if not await self.validation.validate_nginx_syntax(temp_path):
                raise create_operation_error(
                    ErrorCode.CONFIG_SYNTAX_ERROR,
                    "Updated configuration contains invalid nginx syntax",
                )

            # Write updated content
            config_file = self.config_path / update_request.config_name
            await self.file_ops.safe_write_file(
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
            try:
                temp_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file {temp_path}: {e}")
