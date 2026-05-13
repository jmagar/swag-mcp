"""MCP operations module for SWAG MCP.

This module handles MCP-specific functionality for SWAG reverse proxy configurations,
including adding MCP location blocks to existing configurations.
"""

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from swag_mcp.models.config import SwagConfigResult
from swag_mcp.services.filesystem import requires_remote_nginx_validation
from swag_mcp.utils.validators import (
    validate_config_filename,
    validate_mcp_path,
)

if TYPE_CHECKING:
    from swag_mcp.services.backup_manager import BackupManager
    from swag_mcp.services.config_operations import ConfigOperations
    from swag_mcp.services.file_operations import FileOperations
    from swag_mcp.services.filesystem import FilesystemBackend
    from swag_mcp.services.template_manager import TemplateManager
    from swag_mcp.services.validation import ValidationService

logger = logging.getLogger(__name__)


class ConfigReader(Protocol):
    """Protocol for configuration readers used by MCP operations."""

    async def read_config(self, config_name: str) -> str:
        """Read a validated SWAG configuration by name."""
        ...


class MCPOperations:
    """Handles MCP-specific operations for SWAG configurations."""

    def __init__(
        self,
        config_path: Path,
        template_manager: "TemplateManager",
        validation: "ValidationService",
        file_ops: "FileOperations",
        backup_manager: "BackupManager | None" = None,
        config_ops: "ConfigOperations | None" = None,
    ) -> None:
        """Initialize MCP operations.

        Args:
            config_path: Path to the configuration directory
            template_manager: TemplateManager instance for rendering templates
            validation: ValidationService instance for validation operations
            file_ops: FileOperations instance for file operations
            backup_manager: Optional BackupManager instance for backup operations
            config_ops: Optional ConfigOperations instance to delegate read_config

        """
        self.config_path = config_path
        self.template_manager = template_manager
        self.validation = validation
        self.file_ops = file_ops
        self.backup_manager = backup_manager
        self.config_reader: ConfigReader | None = config_ops

    def attach_config_reader(self, config_reader: ConfigReader) -> None:
        """Explicitly attach the configuration reader used for MCP config reads."""
        self.config_reader = config_reader

    @property
    def fs(self) -> "FilesystemBackend":
        """Access filesystem backend through file_ops."""
        return self.file_ops.fs

    async def read_config(self, config_name: str) -> str:
        """Read configuration file content.

        Delegates to ConfigOperations if available, otherwise reads directly.

        Args:
            config_name: Name of the configuration file to read

        Returns:
            Configuration file content as string

        Raises:
            FileNotFoundError: If configuration file not found
            ValueError: If file content is not safe to read

        """
        if self.config_reader is not None:
            return await self.config_reader.read_config(config_name)

        # Fallback: read directly via file_ops
        validated_name = validate_config_filename(config_name)
        config_file = self.config_path / validated_name

        if not await self.fs.exists(str(config_file)):
            raise FileNotFoundError(f"Configuration file {validated_name} not found")

        return await self.file_ops.read_text_safe(
            str(config_file), f"configuration file {validated_name}"
        )

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

        if requires_remote_nginx_validation(self.fs):
            raise ValueError(
                "Cannot add MCP location in remote filesystem mode without "
                "authoritative remote nginx validation"
            )

        try:
            # Create backup if requested
            backup_name = None
            if create_backup and self.backup_manager:
                backup_name = await self.backup_manager.create_backup(config_name)

            # Begin atomic transaction
            async with self.file_ops.begin_transaction(f"add_mcp:{config_name}") as txn:
                # Render MCP location block from existing server-level variables.
                mcp_block = await self.render_mcp_location_block(mcp_path=mcp_path)

                # Insert MCP location block before the last closing brace
                updated_content = self.insert_location_block(content, mcp_block)

                # Write updated content (track for rollback)
                config_file = self.config_path / config_name
                await txn.track_file_modification(config_file)
                await self.file_ops.safe_write_file(
                    config_file, updated_content, f"MCP location addition for {config_name}"
                )

                # Validate nginx syntax before committing (abort on failure).
                if not await self.validation.validate_nginx_syntax(config_file):
                    raise ValueError("Generated configuration contains invalid nginx syntax")

                logger.info(f"Successfully added MCP location block to {config_name}")
                await txn.commit()
                return SwagConfigResult(
                    filename=config_name, content=updated_content, backup_created=backup_name
                )

        except (FileNotFoundError, ValueError):
            raise
        except Exception as e:
            logger.error("Failed to add MCP location to %s: %s", config_name, e)
            raise RuntimeError(f"Failed to add MCP location: {e}") from e

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

        # Check for OAuth gateway pattern: auth_request /_oauth_verify
        if (
            "auth_request /_oauth_verify" in content
            or "auth_request /{{ service_name }}/_oauth_verify" in content
        ):
            return "oauth"

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
    ) -> str:
        """Render MCP location block for insertion into existing configs.

        This implementation uses the standardized mcp-location.conf include.
        """
        # Ensure path starts with /
        if not mcp_path.startswith("/"):
            mcp_path = f"/{mcp_path}"

        # Standardized location block using modular includes
        # Note: We use the existing upstream variables from the server block
        block = f"""
    location {mcp_path} {{
        if ($origin_valid = 0) {{
            add_header Content-Type "application/json" always;
            return 403 '{{"error":"origin_not_allowed","message":"Origin failed"}}';
        }}

        auth_request /_oauth_verify;
        include /config/nginx/resolver.conf;
        include /config/nginx/proxy.conf;
        # Transport Engine (Streaming, MCP Headers, CORS)
        include /config/nginx/mcp-location.conf;

        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }}"""
        return block

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
