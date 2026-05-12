"""Configuration field updater module for SWAG MCP."""

import logging
import re
import tempfile
from pathlib import Path
from re import Match
from typing import Protocol, runtime_checkable

from swag_mcp.models.config import SwagConfigResult, SwagUpdateRequest
from swag_mcp.services.file_operations import FileOperations
from swag_mcp.services.validation import ValidationService
from swag_mcp.utils.error_codes import (
    ErrorCode,
    create_operation_error,
    create_validation_error,
)
from swag_mcp.utils.validators import validate_mcp_path

logger = logging.getLogger(__name__)

SET_DIRECTIVE_PATTERN = r'set \${variable_name} ("[^"]*"|[^;]+);'


def _extract_set_value(content: str, variable_name: str) -> str | None:
    """Extract a simple nginx `set $variable "value";` value."""
    pattern = rf'set \${variable_name}\s+"?([^";]+)"?\s*;'
    match = re.search(pattern, content)
    return match.group(1).strip() if match else None


def _replace_set_value(content: str, variable_name: str, value: str | int) -> tuple[str, int]:
    """Replace a simple nginx set directive value."""
    pattern = SET_DIRECTIVE_PATTERN.format(variable_name=variable_name)
    replacement = rf'set ${variable_name} "{value}";'
    return re.subn(pattern, replacement, content)


def _validate_service_identifier(value: str, label: str) -> str:
    """Validate a service/upstream identifier used in nginx upstream settings."""
    if not re.match(r"^[A-Za-z0-9_.-]+$", value):
        raise create_validation_error(
            ErrorCode.INVALID_SERVICE_NAME,
            f"Invalid {label}: {value}",
        )
    return value


def _parse_port_value(value: str | int, label: str = "port value") -> int:
    """Parse and validate a TCP port value."""
    try:
        port_value = int(value)
        if not (1 <= port_value <= 65535):
            raise create_validation_error(
                ErrorCode.INVALID_PORT_NUMBER,
                f"Port number must be between 1-65535, got: {port_value}",
            )
    except (ValueError, TypeError) as e:
        raise create_validation_error(
            ErrorCode.INVALID_PORT_NUMBER,
            f"Invalid {label}: {value}",
            context={"original_error": str(e)},
        ) from e

    return port_value


def _replace_template_value_pair(
    content: str,
    primary_variable: str,
    inherited_variable: str,
    new_value: str | int,
) -> tuple[str, bool]:
    """Replace a primary set value and inherited MCP value when it mirrors the primary."""
    original_primary = _extract_set_value(content, primary_variable)
    original_inherited = _extract_set_value(content, inherited_variable)
    updated_content, primary_replacements = _replace_set_value(
        content, primary_variable, new_value
    )
    changes_made = primary_replacements > 0

    if primary_replacements > 0:
        logger.debug("Updated %s %s references", primary_replacements, primary_variable)

    if original_inherited and original_inherited == original_primary:
        new_content, inherited_replacements = _replace_set_value(
            updated_content, inherited_variable, new_value
        )
        if inherited_replacements > 0:
            updated_content = new_content
            logger.debug(
                "Updated %s inherited %s references",
                inherited_replacements,
                inherited_variable,
            )

    return updated_content, changes_made


def _replace_template_values(
    content: str, updates: list[tuple[str, str | int]]
) -> tuple[str, bool]:
    """Apply multiple nginx set directive replacements."""
    updated_content = content
    changes_made = False

    for variable_name, value in updates:
        new_content, count = _replace_set_value(updated_content, variable_name, value)
        if count > 0:
            updated_content = new_content
            changes_made = True

    return updated_content, changes_made


@runtime_checkable
class MCPOperationsProtocol(Protocol):
    """Protocol for MCP location block operations.

    eqf.20: Replaces the SwagManagerService wrapper to eliminate the circular import.
    ConfigFieldUpdaters now accepts any object satisfying this interface instead of
    depending on SwagManagerService directly.
    """

    async def add_mcp_location(
        self, config_name: str, mcp_path: str, create_backup: bool
    ) -> SwagConfigResult:
        """Add MCP location block to existing SWAG configuration."""
        ...


# Backward-compatible alias so swag_manager.py import still works during transition
MCPOperations = MCPOperationsProtocol


class ConfigFieldUpdaters:
    """Handles field-specific configuration updates."""

    def __init__(
        self,
        config_path: Path,
        validation: ValidationService,
        file_ops: FileOperations,
        mcp_ops: MCPOperationsProtocol,
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
        port_value = _parse_port_value(update_request.update_value)

        updated_content, changes_made = _replace_template_value_pair(
            content,
            primary_variable="upstream_port",
            inherited_variable="mcp_upstream_port",
            new_value=port_value,
        )

        if not changes_made:
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
        upstream_app = _validate_service_identifier(
            update_request.update_value, "upstream app name"
        )

        updated_content, changes_made = _replace_template_value_pair(
            content,
            primary_variable="upstream_app",
            inherited_variable="mcp_upstream_app",
            new_value=upstream_app,
        )

        if not changes_made:
            # Try simple nginx format: proxy_pass http://app:port
            pattern = r"proxy_pass\s+https?://([^/:]+)(:\d+)?([^;]*);"

            def replace_proxy_pass(match: Match[str]) -> str:
                port = match.group(2) or ""
                path = match.group(3) or ""
                protocol = "https" if "https" in match.group(0) else "http"
                return f"proxy_pass {protocol}://{upstream_app}{port}{path};"

            new_content, proxy_replacements = re.subn(pattern, replace_proxy_pass, updated_content)
            if proxy_replacements > 0:
                updated_content = new_content
                changes_made = True
                logger.debug(
                    f"Updated {proxy_replacements} proxy_pass app references to {upstream_app}"
                )

        # Update upstream comment
        upstream_comment_pattern = r"(# Upstream: https?://)[^:]+(:\d+)"
        upstream_comment_replacement = rf"\g<1>{upstream_app}\g<2>"
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

        app = _validate_service_identifier(app, "app name")
        port_value = _parse_port_value(port)

        original_upstream_app = _extract_set_value(content, "upstream_app")
        original_mcp_app = _extract_set_value(content, "mcp_upstream_app")
        original_upstream_port = _extract_set_value(content, "upstream_port")
        original_mcp_port = _extract_set_value(content, "mcp_upstream_port")

        template_updates: list[tuple[str, str | int]] = [
            ("upstream_app", app),
            ("upstream_port", port_value),
        ]
        if original_mcp_app and original_mcp_app == original_upstream_app:
            template_updates.append(("mcp_upstream_app", app))
        if original_mcp_port and original_mcp_port == original_upstream_port:
            template_updates.append(("mcp_upstream_port", port_value))

        updated_content, changes_made = _replace_template_values(content, template_updates)

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
