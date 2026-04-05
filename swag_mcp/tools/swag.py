"""Unified FastMCP tool for SWAG configuration management."""

import logging
from typing import Annotated, Literal

from fastmcp import Context, FastMCP
from fastmcp.tools.tool import ToolResult
from pydantic import BeforeValidator, Field

from swag_mcp.core.constants import VALID_UPSTREAM_PATTERN
from swag_mcp.models.enums import BackupSubAction, SwagAction
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.tools.handlers.backups import _handle_backups_action
from swag_mcp.tools.handlers.configs import (
    _handle_create_action,
    _handle_edit_action,
    _handle_list_action,
    _handle_remove_action,
    _handle_update_action,
    _handle_view_action,
)
from swag_mcp.tools.handlers.health import _handle_health_check_action
from swag_mcp.tools.handlers.logs import _handle_logs_action
from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter
from swag_mcp.utils.tool_decorators import handle_tool_errors

logger = logging.getLogger(__name__)

# Type alias for update field values
UpdateFieldType = Literal["port", "upstream", "app", "add_mcp"]

# Pre-computed valid actions string for error messages
_VALID_ACTIONS_STR: str = ", ".join(e.value for e in SwagAction)


def _coerce_action(v: object) -> str:
    """Coerce non-string types to string before enum validation.

    Claude.ai sometimes serializes enum values as JSON primitives (true/false/null).
    """
    if v is None:
        raise ValueError(f"action is required. Must be one of: {_VALID_ACTIONS_STR}")
    if isinstance(v, bool):
        raise ValueError(
            f"action must be a string, got boolean ({v}). Must be one of: {_VALID_ACTIONS_STR}"
        )
    return str(v)


def register_tools(mcp: FastMCP) -> None:
    """Register the unified SWAG tool and streaming tools with the FastMCP server."""

    @mcp.tool
    @handle_tool_errors
    async def swag(
        ctx: Context,
        action: Annotated[
            SwagAction, BeforeValidator(_coerce_action), Field(description="Action to perform")
        ],
        # List parameters
        list_filter: Annotated[
            Literal["all", "active", "samples"],
            Field(
                default="all",
                description="Filter for listing configurations: 'all' | 'active' | 'samples'",
            ),
        ] = "all",
        offset: Annotated[int, Field(default=0, description="Pagination offset", ge=0)] = 0,
        limit: Annotated[
            int, Field(default=50, description="Max results to return", ge=1, le=200)
        ] = 50,
        sort_by: Annotated[str, Field(default="name", description="Field to sort by")] = "name",
        sort_order: Annotated[
            Literal["asc", "desc"], Field(default="asc", description="Sort direction")
        ] = "asc",
        query: Annotated[str, Field(default="", description="Filter query string")] = "",
        # Create parameters
        config_name: Annotated[
            str,
            Field(
                default="",
                description="Configuration filename (e.g., 'jellyfin.subdomain.conf')",
                max_length=255,
            ),
        ] = "",
        server_name: Annotated[
            str,
            Field(
                default="", description="Domain name (e.g., 'media.example.com')", max_length=253
            ),
        ] = "",
        upstream_app: Annotated[
            str,
            Field(
                default="",
                description="Container name or IP address",
                max_length=100,
                pattern=VALID_UPSTREAM_PATTERN.replace("+", "*"),  # Optional
            ),
        ] = "",
        upstream_port: Annotated[
            int, Field(default=0, ge=0, le=65535, description="Port number the service runs on")
        ] = 0,
        upstream_proto: Annotated[
            Literal["http", "https"],
            Field(default="http", description="Protocol for upstream connection: 'http' | 'https'"),
        ] = "http",
        # Remote MCP upstream parameters (optional — default to upstream_app/port/proto)
        # All configs include MCP-compatible security headers regardless of these values.
        # Set mcp_upstream_app to enable split routing: / → upstream_app, /mcp → mcp_upstream_app
        mcp_upstream_app: Annotated[
            str,
            Field(
                default="",
                description=(
                    "Container name or IP for MCP service (if different from upstream_app). "
                    "Enables split routing: / → upstream_app, /mcp → mcp_upstream_app"
                ),
                max_length=100,
                pattern=VALID_UPSTREAM_PATTERN.replace("+", "*"),  # Optional field
            ),
        ] = "",
        mcp_upstream_port: Annotated[
            int,
            Field(
                default=0,
                ge=0,
                le=65535,
                description=(
                    "Port for MCP service (if different from upstream_port). "
                    "Use 0 or omit to inherit from upstream_port."
                ),
            ),
        ] = 0,
        mcp_upstream_proto: Annotated[
            Literal["http", "https"] | None,
            Field(
                default=None,
                description=(
                    "Protocol for MCP upstream connection: 'http' | 'https'. "
                    "Omit to inherit from upstream_proto."
                ),
            ),
        ] = None,
        auth_method: Annotated[
            str,
            Field(
                default="authelia",
                description=(
                    "Authentication method: 'none' | 'basic' | 'ldap' | "
                    "'authelia' | 'authentik' | 'tinyauth'"
                ),
            ),
        ] = "authelia",
        enable_quic: Annotated[
            bool, Field(default=False, description="Enable QUIC support")
        ] = False,
        # Edit parameters
        new_content: Annotated[
            str, Field(default="", description="New content for the configuration file")
        ] = "",
        create_backup: Annotated[
            bool, Field(default=True, description="Whether to create a backup before editing")
        ] = True,
        # Logs parameters
        log_type: Annotated[
            Literal["nginx-access", "nginx-error", "fail2ban", "letsencrypt", "renewal"],
            Field(
                default="nginx-error",
                description=(
                    "Type of log to retrieve: 'nginx-access' | 'nginx-error' | 'fail2ban' | "
                    "'letsencrypt' | 'renewal'"
                ),
            ),
        ] = "nginx-error",
        lines: Annotated[
            int, Field(default=50, ge=1, le=1000, description="Number of log lines to retrieve")
        ] = 50,
        # Backup parameters
        backup_action: Annotated[
            BackupSubAction,
            Field(
                default=BackupSubAction.LIST,
                description="Backup action: 'cleanup' or 'list'",
            ),
        ] = BackupSubAction.LIST,
        retention_days: Annotated[
            int,
            Field(
                default=0,
                ge=0,
                description="Days to retain backup files (only for cleanup action)",
            ),
        ] = 0,
        # Health check parameters
        domain: Annotated[
            str,
            Field(
                default="",
                description="Full domain to check health for (e.g., 'media.example.com')",
                max_length=253,
            ),
        ] = "",
        timeout: Annotated[
            int, Field(default=30, ge=1, le=300, description="Request timeout in seconds")
        ] = 30,
        follow_redirects: Annotated[
            bool, Field(default=True, description="Whether to follow HTTP redirects")
        ] = True,
        # Update parameters
        update_field: Annotated[
            UpdateFieldType | str,
            Field(
                default="",
                description="Field to update: 'port' | 'upstream' | 'app' | 'add_mcp'",
            ),
        ] = "",
        update_value: Annotated[
            str,
            Field(
                default="",
                description="New value for field (port number, app name, app:port, or MCP path)",
            ),
        ] = "",
    ) -> ToolResult:
        """Unified SWAG reverse proxy configuration management tool.

        This single tool handles all SWAG operations based on the 'action' parameter.
        Different actions use different parameters.

        Actions:
        • list: List configuration files
          - Required: action
          - Optional: list_filter (default: "all")

        • create: Create new reverse proxy configuration
          - Required: action, config_name, server_name, upstream_app, upstream_port
          - Optional: upstream_proto, auth_method, enable_quic,
                     mcp_upstream_app, mcp_upstream_port, mcp_upstream_proto
          - Note: All configs include MCP-compatible security headers unconditionally.

        • view: View configuration file contents
          - Required: action, config_name

        • edit: Edit existing configuration
          - Required: action, config_name, new_content
          - Optional: create_backup

        • update: Update specific field in existing configuration
          - Required: action, config_name, update_field, update_value
          - Optional: create_backup
          - update_field options: 'port' | 'upstream' | 'app' | 'add_mcp'

        • remove: Remove configuration file
          - Required: action, config_name
          - Optional: create_backup

        • logs: Show SWAG logs
          - Required: action
          - Optional: lines

        • backups: Manage backup files
          - Required: action, backup_action
          - Optional: retention_days (only for cleanup action)
          - backup_action options: 'cleanup' | 'list'

        • health_check: Perform health check on service endpoint
          - Required: action, domain
          - Optional: timeout, follow_redirects

        Examples:
          "Create jellyfin.subdomain.conf for media.example.com using jellyfin:8096"
          "List all active proxy configurations"
          "Show the plex.subdomain.conf configuration"
          "Update port for crawler.subdomain.conf to 8011"
          "Add MCP endpoint to jellyfin.subdomain.conf"
          "Add MCP location at /ai-service to plex.subdomain.conf"
          "Clean up backup files older than 7 days"
          "List all backup files"

        Split-routing example (main app on one server, MCP/AI service on a GPU server):
          action=create, config_name=jellyfin.subdomain.conf,
          server_name=jellyfin.example.com, upstream_app=jellyfin, upstream_port=8096,
          mcp_upstream_app=ai-gpu-server, mcp_upstream_port=8080
          → Routes: / → jellyfin:8096, /mcp → ai-gpu-server:8080

        """
        swag_service = SwagManagerService()
        formatter = TokenEfficientFormatter()

        try:
            match action:
                case SwagAction.LIST:
                    return await _handle_list_action(
                        ctx,
                        swag_service,
                        formatter,
                        list_filter,
                        offset,
                        limit,
                        sort_by,
                        sort_order,
                        query,
                    )
                case SwagAction.CREATE:
                    # eqf.10: Emit note when mcp_upstream_port inherits from upstream_port
                    effective_mcp_port = mcp_upstream_port or None
                    if not mcp_upstream_port and mcp_upstream_app:
                        await ctx.info(
                            f"mcp_upstream_port not set — inheriting upstream_port: {upstream_port}"
                        )
                    return await _handle_create_action(
                        ctx,
                        swag_service,
                        formatter,
                        config_name,
                        server_name,
                        upstream_app,
                        upstream_port,
                        upstream_proto,
                        auth_method,
                        enable_quic,
                        mcp_upstream_app or None,
                        effective_mcp_port,
                        mcp_upstream_proto or None,  # eqf.9: coerce → model-validator inherits
                    )
                case SwagAction.VIEW:
                    return await _handle_view_action(ctx, swag_service, formatter, config_name)
                case SwagAction.EDIT:
                    return await _handle_edit_action(
                        ctx, swag_service, formatter, config_name, new_content, create_backup
                    )
                case SwagAction.REMOVE:
                    return await _handle_remove_action(
                        ctx, swag_service, formatter, config_name, create_backup
                    )
                case SwagAction.LOGS:
                    return await _handle_logs_action(ctx, swag_service, formatter, log_type, lines)
                case SwagAction.BACKUPS:
                    return await _handle_backups_action(
                        ctx, swag_service, formatter, backup_action, retention_days
                    )
                case SwagAction.HEALTH_CHECK:
                    return await _handle_health_check_action(
                        ctx, swag_service, formatter, domain, timeout, follow_redirects
                    )
                case SwagAction.UPDATE:
                    return await _handle_update_action(
                        ctx,
                        swag_service,
                        formatter,
                        config_name,
                        update_field,
                        update_value,
                        create_backup,
                    )
                case _:
                    raise ValueError(f"Unhandled action: {action}")

        except Exception as e:
            logger.error(f"SWAG tool error - action: {action.value}, error: {str(e)}")
            return formatter.format_error_result(f"Tool execution failed: {str(e)}", action.value)

    @mcp.tool
    async def swag_help() -> str:
        """Return help for the SWAG MCP server — lists all available actions and subactions."""
        return """# SWAG MCP Server

Manage SWAG (Secure Web Application Gateway) reverse proxy configurations.

## Tool: `swag`

Routes all SWAG management actions via `action` parameter.

## Available Actions

| Action | Description |
|--------|-------------|
| `list` | List proxy configurations (filter: all/active/samples) |
| `create` | Create a new proxy configuration |
| `view` | View a configuration file's contents |
| `edit` | Edit a configuration file |
| `update` | Update a field in a configuration (port, upstream, app, add_mcp) |
| `remove` | Remove a configuration file |
| `logs` | View SWAG logs (type: access/error/fail2ban) |
| `backups` | Manage config backups (subaction: list/cleanup) |
| `health_check` | Run HTTP health check on a domain |

## Examples

```json
{"action": "list", "list_filter": "active"}
{"action": "create", "config_name": "app.subdomain.conf", "server_name": "app.example.com",
 "upstream_app": "myapp", "upstream_port": 3000}
{"action": "view", "config_name": "app.subdomain.conf"}
{"action": "edit", "config_name": "app.subdomain.conf", "new_content": "..."}
{"action": "update", "config_name": "app.subdomain.conf", "update_field": "port",
 "update_value": "8080"}
{"action": "remove", "config_name": "app.subdomain.conf"}
{"action": "logs", "log_type": "nginx-access", "lines": 50}
{"action": "backups", "backup_action": "list"}
{"action": "health_check", "domain": "app.example.com"}
```
"""
