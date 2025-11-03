"""MCP operations module for SWAG MCP.

This module handles MCP-specific functionality for SWAG reverse proxy configurations,
including adding MCP location blocks to existing configurations.
"""

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

import aiofiles

from swag_mcp.models.config import SwagConfigResult
from swag_mcp.utils.validators import (
    detect_and_handle_encoding,
    validate_config_filename,
    validate_file_content_safety_async,
    validate_mcp_path,
)

if TYPE_CHECKING:
    from swag_mcp.services.backup_manager import BackupManager
    from swag_mcp.services.file_operations import FileOperations
    from swag_mcp.services.template_manager import TemplateManager
    from swag_mcp.services.validation import ValidationService

logger = logging.getLogger(__name__)


class MCPOperations:
    """Handles MCP-specific operations for SWAG configurations."""

    def __init__(
        self,
        config_path: Path,
        template_manager: "TemplateManager",
        validation: "ValidationService",
        file_ops: "FileOperations",
        backup_manager: "BackupManager | None" = None,
    ) -> None:
        """Initialize MCP operations.

        Args:
            config_path: Path to the configuration directory
            template_manager: TemplateManager instance for rendering templates
            validation: ValidationService instance for validation operations
            file_ops: FileOperations instance for file operations
            backup_manager: Optional BackupManager instance for backup operations

        """
        self.config_path = config_path
        self.template_manager = template_manager
        self.validation = validation
        self.file_ops = file_ops
        self.backup_manager = backup_manager

    async def read_config(self, config_name: str) -> str:
        """Read configuration file content.

        Args:
            config_name: Name of the configuration file to read

        Returns:
            Configuration file content as string

        Raises:
            FileNotFoundError: If configuration file not found
            ValueError: If file content is not safe to read

        """
        logger.info(f"Reading configuration: {config_name}")

        # Validate config name directly (must be full filename)
        validated_name = validate_config_filename(config_name)
        config_file = self.config_path / validated_name

        # Check if file exists first
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file {validated_name} not found")

        # Security validation: ensure file is safe to read as text
        if not await validate_file_content_safety_async(config_file):
            raise ValueError(f"Configuration file {validated_name} is not safe to read as text")

        # Read file with proper encoding detection and Unicode normalization
        try:
            async with aiofiles.open(config_file, "rb") as f:
                raw_content = await f.read()

            # Detect encoding and normalize Unicode
            content = detect_and_handle_encoding(raw_content)
            logger.debug(f"Successfully read configuration {validated_name}")
            return content

        except (ValueError, UnicodeDecodeError) as e:
            raise ValueError(
                f"Configuration file has invalid text encoding or Unicode characters: "
                f"{validated_name}: {str(e)}"
            ) from e

    async def add_mcp_location(
        self, config_name: str, mcp_path: str = "/mcp", create_backup: bool = True
    ) -> SwagConfigResult:
        """Add MCP location block to existing SWAG configuration.

        Args:
            config_name: Name of the configuration file to modify
            mcp_path: URL path for the MCP endpoint (default: "/mcp")
            create_backup: Whether to create a backup before modifying (default: True)

        Returns:
            SwagConfigResult with operation details

        Raises:
            ValueError: If MCP path is invalid, location already exists, or nginx syntax invalid
            FileNotFoundError: If configuration file not found

        """
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
            from swag_mcp.utils.error_handlers import handle_os_error

            handle_os_error(e, "reading configuration file", config_name)

        # Check if MCP location already exists (match '=', '^~', or plain)
        dup_pat = re.compile(rf"^\s*location\s+(?:=\s+|\^~\s+)?{re.escape(mcp_path)}\s*\{{", re.M)
        if dup_pat.search(content):
            raise ValueError(f"MCP location {mcp_path} already exists in configuration")

        # Create backup if requested
        backup_name = None
        if create_backup and self.backup_manager:
            backup_name = await self.backup_manager.create_backup(config_name)

        try:
            # Begin atomic transaction
            async with self.file_ops.begin_transaction(f"add_mcp:{config_name}") as txn:
                # Extract current upstream values from config
                upstream_app = self.extract_upstream_value(content, "upstream_app")
                upstream_port = self.extract_upstream_value(content, "upstream_port")
                upstream_proto_raw = self.extract_upstream_value(content, "upstream_proto")
                # Validate and cast upstream_proto to Literal type
                if upstream_proto_raw not in ("http", "https"):
                    upstream_proto_raw = "http"  # Default to safe value
                upstream_proto = cast(Literal["http", "https"], upstream_proto_raw)
                auth_method = self.extract_auth_method(content)

                # Render MCP location block
                mcp_block = await self.render_mcp_location_block(
                    mcp_path=mcp_path,
                    upstream_app=upstream_app,
                    upstream_port=upstream_port,
                    upstream_proto=upstream_proto,
                    auth_method=auth_method,
                )

                # Insert MCP location block before the last closing brace
                updated_content = self.insert_location_block(content, mcp_block)

                # Write updated content (track for rollback)
                config_file = self.config_path / config_name
                await txn.track_file_modification(config_file)
                await self.file_ops.safe_write_file(
                    config_file, updated_content, f"MCP location addition for {config_name}"
                )

                # Validate nginx syntax before committing (abort on failure)
                if not await self.validation.validate_nginx_syntax(config_file):
                    raise ValueError("Generated configuration contains invalid nginx syntax")

                logger.info(f"Successfully added MCP location block to {config_name}")
                await txn.commit()
                return SwagConfigResult(
                    filename=config_name, content=updated_content, backup_created=backup_name
                )

        except Exception as e:
            logger.error(f"Failed to add MCP location to {config_name}: {str(e)}")
            raise ValueError(f"Failed to add MCP location: {str(e)}") from e

    def extract_upstream_value(self, content: str, variable_name: str) -> str:
        """Extract upstream variable value from nginx configuration content.

        Args:
            content: Nginx configuration file content
            variable_name: Name of the variable to extract (e.g., "upstream_app", "upstream_port")

        Returns:
            Value of the variable as string

        Raises:
            ValueError: If variable not found in configuration

        """
        # Pattern to match: set $upstream_app "value"; or set $upstream_port "value";
        pattern = rf'set \${variable_name}\s+"([^"]*)"'
        match = re.search(pattern, content)

        if not match:
            raise ValueError(f"Could not find {variable_name} in configuration")

        return str(match.group(1)).strip()

    def extract_auth_method(self, content: str) -> str:
        """Extract authentication method from nginx configuration content.

        Args:
            content: Nginx configuration file content

        Returns:
            Authentication method name (e.g., "authelia", "ldap", "basic", "none")

        """
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

    async def render_mcp_location_block(
        self,
        mcp_path: str,
        upstream_app: str,
        upstream_port: str,
        upstream_proto: Literal["http", "https"],
        auth_method: str,
    ) -> str:
        """Render MCP location block template with provided variables.

        Args:
            mcp_path: URL path for the MCP endpoint
            upstream_app: Upstream application name or IP
            upstream_port: Upstream port number
            upstream_proto: Protocol for upstream connection ("http" or "https")
            auth_method: Authentication method to use

        Returns:
            Rendered MCP location block as string

        Raises:
            ValueError: If template rendering fails

        """
        try:
            # Prepare template variables
            template_vars = {
                "mcp_path": mcp_path,
                "upstream_app": upstream_app,
                "upstream_port": upstream_port,
                "upstream_proto": upstream_proto,
                "auth_method": auth_method,
            }

            # Render template with validated variables using the template manager
            template_name = "mcp_location_block.j2"
            rendered = await self.template_manager.render_template(template_name, template_vars)
            return rendered

        except ValueError as e:
            # Template manager already provides detailed error messages
            raise e
        except Exception as e:
            raise ValueError(f"Failed to render MCP location block template: {str(e)}") from e

    def insert_location_block(self, content: str, location_block: str) -> str:
        """Insert location block before the closing brace of the outermost server block.

        Args:
            content: Original nginx configuration content
            location_block: Location block content to insert

        Returns:
            Updated configuration content with location block inserted

        Raises:
            ValueError: If server block structure cannot be found

        """
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
