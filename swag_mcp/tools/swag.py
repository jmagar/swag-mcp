"""Unified FastMCP tool for SWAG configuration management."""

import asyncio
import logging
import re
from typing import Annotated, Any, Literal, cast

from fastmcp import Context, FastMCP
from fastmcp.tools.tool import ToolResult
from pydantic import Field

from swag_mcp.core.constants import (
    VALID_UPSTREAM_PATTERN,
)
from swag_mcp.models.config import (
    SwagConfigRequest,
    SwagEditRequest,
    SwagHealthCheckRequest,
    SwagLogsRequest,
    SwagRemoveRequest,
    SwagUpdateRequest,
)
from swag_mcp.models.enums import BackupSubAction, SwagAction
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter
from swag_mcp.utils.tool_decorators import handle_tool_errors
from swag_mcp.utils.tool_helpers import (
    log_action_start,
    log_action_success,
    validate_list_filter,
    validate_required_params,
)

logger = logging.getLogger(__name__)

# Type alias for update field values
UpdateFieldType = Literal["port", "upstream", "app", "add_mcp"]

# Service will be instantiated per-invocation for stateless operation


async def _extract_server_name_from_config(
    swag_service: SwagManagerService, config_name: str
) -> str | None:
    """Extract server_name from nginx config file.

    Args:
        swag_service: Service instance for configuration operations
        config_name: Configuration file name

    Returns:
        Server name if found, None otherwise

    """
    try:
        config_content = await swag_service.read_config(config_name)

        # Extract server_name from nginx config
        match = re.search(r"server_name\s+([^;]+);", config_content)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return None


async def _run_health_check(
    swag_service: SwagManagerService, ctx: Context, server_name: str
) -> str:
    """Run health check for a domain and return formatted status.

    Args:
        swag_service: Service instance for health check operations
        ctx: FastMCP context for logging
        server_name: Domain name to check

    Returns:
        Formatted health check status

    """
    await ctx.info(f"Running health check for {server_name}...")

    try:
        health_request = SwagHealthCheckRequest(
            action=SwagAction.HEALTH_CHECK,
            domain=server_name,
            timeout=15,
            follow_redirects=True,
        )

        health_result = await swag_service.health_check(health_request)

        if health_result.success:
            status_code = health_result.status_code or "unknown"
            response_time = health_result.response_time_ms or 0
            health_status = f"✅ Health check passed: {status_code} ({response_time}ms)"
            await ctx.info(f"Health check successful for {server_name}")
        else:
            health_status = f"⚠️ Health check failed: {health_result.error or 'Unknown error'}"
            await ctx.info(f"Health check failed for {server_name}: {health_result.error}")

        return health_status

    except Exception as e:
        health_status = f"⚠️ Health check error: {str(e)}"
        await ctx.info(f"Health check encountered an error: {str(e)}")
        return health_status


async def _run_post_create_health_check(
    swag_service: SwagManagerService, ctx: Context, server_name: str, filename: str
) -> str:
    """Run health check after config creation and format results."""
    health_status = await _run_health_check(swag_service, ctx, server_name)
    return f"Created configuration: {filename}\n{health_status}"


async def _run_post_update_health_check(
    swag_service: SwagManagerService, ctx: Context, config_name: str, field: str, new_value: str
) -> str:
    """Run health check after config update and format results."""
    # Extract server name from config
    server_name = await _extract_server_name_from_config(swag_service, config_name)
    if not server_name:
        # Can't determine server name, skip health check
        return f"Updated {field} in {config_name} to {new_value}"

    health_status = await _run_health_check(swag_service, ctx, server_name)
    return f"Updated {field} in {config_name} to {new_value}\n{health_status}"


def register_tools(mcp: FastMCP) -> None:
    """Register the unified SWAG tool and streaming tools with the FastMCP server."""

    @mcp.tool
    @handle_tool_errors
    async def swag(
        ctx: Context,
        action: Annotated[SwagAction, Field(description="Action to perform")],
        # List parameters
        list_filter: Annotated[
            Literal["all", "active", "samples"],
            Field(
                default="all",
                description="Filter for listing configurations: 'all' | 'active' | 'samples'",
            ),
        ] = "all",
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
        mcp_enabled: Annotated[
            bool,
            Field(default=False, description="Enable MCP/SSE support for AI services"),
        ] = False,
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
          - Optional: upstream_proto, mcp_enabled, auth_method, enable_quic

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

        """
        # Create service instance per-invocation for stateless operation
        swag_service = SwagManagerService()

        # Create formatter for token-efficient dual content responses
        formatter = TokenEfficientFormatter()

        # Dispatch based on action using pattern matching for better maintainability
        try:
            match action:
                case SwagAction.LIST:
                    return await _handle_list_action(
                        ctx, swag_service, formatter, list_filter
                    )
                case SwagAction.CREATE:
                    return await _handle_create_action(
                        ctx, swag_service, formatter, config_name, server_name,
                        upstream_app, upstream_port, upstream_proto, auth_method,
                        enable_quic, mcp_enabled
                    )
                case SwagAction.VIEW:
                    return await _handle_view_action(
                        ctx, swag_service, formatter, config_name
                    )
                case SwagAction.EDIT:
                    return await _handle_edit_action(
                        ctx, swag_service, formatter, config_name, new_content,
                        create_backup
                    )
                case SwagAction.REMOVE:
                    return await _handle_remove_action(
                        ctx, swag_service, formatter, config_name, create_backup
                    )
                case SwagAction.LOGS:
                    return await _handle_logs_action(
                        ctx, swag_service, formatter, log_type, lines
                    )
                case SwagAction.BACKUPS:
                    return await _handle_backups_action(
                        ctx, swag_service, formatter, retention_days
                    )
                case SwagAction.HEALTH_CHECK:
                    return await _handle_health_check_action(
                        ctx, swag_service, formatter, domain, timeout, follow_redirects
                    )
                case SwagAction.UPDATE:
                    return await _handle_update_action(
                        ctx, swag_service, formatter, config_name, update_field,
                        update_value, create_backup
                    )
                case _:
                    raise ValueError(f"Unhandled action: {action}")

        except Exception as e:
            logger.error(f"SWAG tool error - action: {action.value}, error: {str(e)}")
            return formatter.format_error_result(f"Tool execution failed: {str(e)}", action.value)


async def _handle_list_action(
    ctx: Context, swag_service: Any, formatter: Any, list_filter: str
) -> ToolResult:
    """Handle LIST action."""
    await log_action_start(ctx, "Listing SWAG configurations", list_filter)

    if error := validate_list_filter(cast("Literal['all', 'active', 'samples']", list_filter)):
        return cast("ToolResult", formatter.format_error_result(
            error.get("message", "Invalid list filter"), "list"
        ))

    result = await swag_service.list_configs(list_filter)

    # Convert service result to dict for formatter
    result_data = {
        "configs": result.configs,
        "total_count": result.total_count,
        "list_filter": result.list_filter,
    }

    await log_action_success(ctx, f"Listed {result.total_count} configurations")
    return cast("ToolResult", formatter.format_list_result(result_data, list_filter))


async def _handle_create_action(
    ctx: Context, swag_service: SwagManagerService, formatter: TokenEfficientFormatter,
    config_name: str, server_name: str, upstream_app: str, upstream_port: int,
    upstream_proto: str, auth_method: str, enable_quic: bool, mcp_enabled: bool
) -> ToolResult:
    """Handle CREATE action with comprehensive progress reporting."""
    # Validate required parameters
    if error := validate_required_params(
        {
            "config_name": (config_name, "config_name"),
            "server_name": (server_name, "server_name"),
            "upstream_app": (upstream_app, "upstream_app"),
            "upstream_port": (
                upstream_port if upstream_port != 0 else None,
                "upstream_port",
            ),
        },
        "create",
    ):
        return formatter.format_error_result(
            error.get("message", "Missing required parameters"), "create"
        )

    await log_action_start(ctx, "Creating configuration", config_name)

    try:
        # Progress reporting for create operation
        await ctx.info("Validating configuration parameters...")

        # Build the configuration request
        config_request = SwagConfigRequest(
            action=SwagAction.CREATE,
            config_name=config_name,
            server_name=server_name,
            upstream_app=upstream_app,
            upstream_port=upstream_port,
            upstream_proto=cast("Literal['http', 'https']", upstream_proto),
            auth_method=auth_method,
            enable_quic=enable_quic,
            mcp_enabled=mcp_enabled,
        )

        await ctx.info("Creating proxy configuration...")
        result = await asyncio.wait_for(
            swag_service.create_config(config_request),
            timeout=180  # 3 minute timeout for creation
        )

        await ctx.info("Running health verification...")
        # Run post-create health check
        health_check_result = await _run_post_create_health_check(
            swag_service, ctx, server_name, result.filename
        )

        await log_action_success(ctx, f"Created configuration {config_name}")
        await ctx.info("Configuration created successfully")

        # Convert to dict for formatter with health check result
        result_data = {
            "success": True,
            "filename": result.filename,
            "content": result.content,
            "backup_created": result.backup_created,
            "health_check": health_check_result,
        }

        return formatter.format_create_result(result_data, config_name)

    except asyncio.CancelledError:
        await ctx.info("Configuration creation cancelled by user")
        raise
    except TimeoutError:
        await ctx.info("Configuration creation timed out")
        return formatter.format_error_result(
            "Create operation timed out", "create"
        )


async def _handle_view_action(
    ctx: Context, swag_service: Any, formatter: Any, config_name: str
) -> ToolResult:
    """Handle VIEW action."""
    await log_action_start(ctx, "Viewing configuration", config_name)

    if error := validate_required_params(
        {"config_name": (config_name, "config_name")}, "view"
    ):
        return cast("ToolResult", formatter.format_error_result(
            error.get("message", "Missing config name"), "view"
        ))

    try:
        content = await swag_service.read_config(config_name)
        await log_action_success(ctx, f"Read configuration {config_name}")

        result_data = {"filename": config_name, "content": content}
        return cast("ToolResult", formatter.format_view_result(result_data, config_name))
    except FileNotFoundError:
        return cast("ToolResult", formatter.format_error_result(
            f"Configuration '{config_name}' not found", "view"
        ))


async def _handle_edit_action(
    ctx: Context, swag_service: SwagManagerService, formatter: TokenEfficientFormatter,
    config_name: str, new_content: str, create_backup: bool
) -> ToolResult:
    """Handle EDIT action with progress reporting and cancellation support."""
    await log_action_start(ctx, "Editing configuration", config_name)

    if error := validate_required_params(
        {
            "config_name": (config_name, "config_name"),
            "new_content": (new_content, "new_content"),
        },
        "edit",
    ):
        return formatter.format_error_result(
            error.get("message", "Missing required parameters"), "edit"
        )

    try:
        # Progress reporting for long operations
        await ctx.info("Validating configuration content...")

        edit_request = SwagEditRequest(
            action=SwagAction.EDIT,
            config_name=config_name,
            new_content=new_content,
            create_backup=create_backup,
        )

        # Use asyncio.wait_for for cancellation support
        await ctx.info("Applying configuration changes...")
        edit_result = await asyncio.wait_for(
            swag_service.update_config(edit_request),
            timeout=300  # 5 minute timeout for large configs
        )

        await log_action_success(ctx, f"Successfully edited {config_name}")
        await ctx.info("Configuration edit completed successfully")

        # Convert service result to dict for formatter
        result_data = {
            "success": True,
            "backup_created": edit_result.backup_created,
        }

        return formatter.format_edit_result(result_data, config_name)

    except asyncio.CancelledError:
        await ctx.info("Configuration edit cancelled by user")
        raise
    except TimeoutError:
        await ctx.info("Configuration edit timed out")
        return formatter.format_error_result(
            "Edit operation timed out", "edit"
        )


async def _handle_remove_action(
    ctx: Context, swag_service: SwagManagerService, formatter: TokenEfficientFormatter,
    config_name: str, create_backup: bool
) -> ToolResult:
    """Handle REMOVE action with progress reporting."""
    await log_action_start(ctx, "Removing configuration", config_name)

    if error := validate_required_params(
        {"config_name": (config_name, "config_name")}, "remove"
    ):
        return formatter.format_error_result(
            error.get("message", "Missing config_name"), "remove"
        )

    try:
        await ctx.info("Preparing to remove configuration...")

        remove_request = SwagRemoveRequest(
            action=SwagAction.REMOVE,
            config_name=config_name,
            create_backup=create_backup
        )

        await ctx.info("Removing configuration file...")
        remove_result = await swag_service.remove_config(remove_request)

        await log_action_success(ctx, f"Successfully removed {config_name}")
        await ctx.info("Configuration removal completed")

        # Convert service result to dict for formatter
        result_data = {
            "success": True,
            "backup_created": remove_result.backup_created,
        }

        return formatter.format_remove_result(result_data, config_name)

    except asyncio.CancelledError:
        await ctx.info("Configuration removal cancelled by user")
        raise


async def _handle_logs_action(
    ctx: Context, swag_service: SwagManagerService, formatter: TokenEfficientFormatter,
    log_type: str, lines: int
) -> ToolResult:
    """Handle LOGS action with streaming capability for large log files."""
    await log_action_start(ctx, f"Retrieving SWAG {log_type} logs", f"{lines} lines")

    try:
        await ctx.info("Accessing SWAG container logs...")

        logs_request = SwagLogsRequest(
            action=SwagAction.LOGS,
            log_type=cast(
                "Literal['nginx-access', 'nginx-error', 'fail2ban', 'letsencrypt', 'renewal']",
                log_type
            ),
            lines=lines
        )

        # Use timeout for log operations
        logs_output = await asyncio.wait_for(
            swag_service.get_swag_logs(logs_request),
            timeout=60  # 1 minute timeout for log retrieval
        )

        await log_action_success(
            ctx,
            f"Retrieved {len(logs_output)} characters of {log_type} log output",
        )
        await ctx.info("Log retrieval completed")

        # Convert service result to dict for formatter
        result_data = {
            "logs": logs_output,
            "character_count": len(logs_output),
        }

        return formatter.format_logs_result(result_data, log_type, lines)

    except asyncio.CancelledError:
        await ctx.info("Log retrieval cancelled by user")
        raise
    except TimeoutError:
        await ctx.info("Log retrieval timed out")
        return formatter.format_error_result(
            "Log retrieval operation timed out", "logs"
        )


async def _handle_backups_action(
    ctx: Context, swag_service: SwagManagerService, formatter: TokenEfficientFormatter,
    retention_days: int
) -> ToolResult:
    """Handle BACKUPS action with cleanup progress reporting."""
    backup_action = BackupSubAction.CLEANUP if retention_days > 0 else BackupSubAction.LIST

    try:
        if backup_action == BackupSubAction.CLEANUP:
            retention_msg = (
                f"{retention_days} days retention"
                if retention_days > 0
                else "default retention"
            )
            await log_action_start(ctx, "Running backup cleanup", retention_msg)
            await ctx.info("Scanning for old backup files...")

            retention_days_param = retention_days if retention_days > 0 else None
            cleaned_count = await swag_service.cleanup_old_backups(retention_days_param)

            if cleaned_count > 0:
                message = f"Cleaned up {cleaned_count} old backup files"
                await ctx.info(f"Cleanup completed: {cleaned_count} files removed")
            else:
                message = "No old backup files to clean up"
                await ctx.info("Cleanup completed: no files to remove")

            await log_action_success(ctx, message)

            # Convert service result to dict for formatter
            cleanup_data = {
                "cleaned_count": cleaned_count,
                "retention_days": retention_days_param or 30,  # Default fallback
            }

            return formatter.format_backup_result(cleanup_data, backup_action)

        else:  # LIST
            await log_action_start(ctx, "Listing backup files", "all backup files")
            await ctx.info("Scanning backup directory...")

            backup_files = await swag_service.list_backups()

            if not backup_files:
                message = "No backup files found"
            else:
                message = f"Found {len(backup_files)} backup files"

            await log_action_success(ctx, message)
            await ctx.info(f"Scan completed: {len(backup_files)} backup files found")

            # Convert service result to dict for formatter
            result_data: dict[str, Any] = {
                "backup_files": backup_files,
                "total_count": len(backup_files),
            }

            return formatter.format_backup_result(result_data, backup_action)

    except asyncio.CancelledError:
        await ctx.info("Backup operation cancelled by user")
        raise


async def _handle_health_check_action(
    ctx: Context, swag_service: SwagManagerService, formatter: TokenEfficientFormatter,
    domain: str, timeout: int, follow_redirects: bool
) -> ToolResult:
    """Handle HEALTH_CHECK action with progress reporting."""
    if error := validate_required_params(
        {"domain": (domain, "domain")}, "health_check"
    ):
        return formatter.format_error_result(
            error.get("message", "Missing domain"), "health_check"
        )

    await log_action_start(ctx, "Starting health check", domain)

    try:
        await ctx.info(f"Testing connectivity to {domain}...")

        # Validate and create health check request
        health_request = SwagHealthCheckRequest(
            action=SwagAction.HEALTH_CHECK,
            domain=domain,
            timeout=timeout,
            follow_redirects=follow_redirects,
        )

        # Perform health check with timeout
        health_result = await asyncio.wait_for(
            swag_service.health_check(health_request),
            timeout=timeout + 10  # Add buffer to service timeout
        )

        await log_action_success(ctx, f"Health check completed for {domain}")

        if health_result.success:
            await ctx.info(f"Health check passed: {health_result.status_code}")
        else:
            await ctx.info(f"Health check failed: {health_result.error}")

        # Convert service result to dict for formatter
        result_data = {
            "success": health_result.success,
            "domain": health_result.domain,
            "status_code": health_result.status_code,
            "response_time_ms": health_result.response_time_ms,
            "error": getattr(health_result, "error", None),
        }

        return formatter.format_health_check_result(result_data)

    except asyncio.CancelledError:
        await ctx.info("Health check cancelled by user")
        raise
    except TimeoutError:
        await ctx.info("Health check timed out")
        return formatter.format_error_result(
            f"Health check for {domain} timed out", "health_check"
        )


async def _handle_update_action(
    ctx: Context, swag_service: SwagManagerService, formatter: TokenEfficientFormatter,
    config_name: str, update_field: str, update_value: str, create_backup: bool
) -> ToolResult:
    """Handle UPDATE action with progress reporting and health check."""
    if error := validate_required_params(
        {
            "config_name": (config_name, "config_name"),
            "update_field": (update_field, "update_field"),
            "update_value": (update_value, "update_value"),
        },
        "update",
    ):
        return formatter.format_error_result(
            error.get("message", "Missing required parameters"), "update"
        )

    await log_action_start(
        ctx, f"Updating {update_field}", f"{config_name} to {update_value}"
    )

    try:
        # Validate update_field is a valid value
        valid_update_fields: set[UpdateFieldType] = {"port", "upstream", "app", "add_mcp"}
        if update_field not in valid_update_fields:
            return formatter.format_error_result(
                f"Invalid update_field: '{update_field}'. "
                f"Must be one of: {', '.join(valid_update_fields)}",
                "update",
            )

        # Now we know update_field is a valid UpdateFieldType
        validated_update_field: UpdateFieldType = cast("UpdateFieldType", update_field)

        await ctx.info(f"Preparing to update {update_field} field...")

        update_request = SwagUpdateRequest(
            action=SwagAction.UPDATE,
            config_name=config_name,
            update_field=validated_update_field,
            update_value=update_value,
            create_backup=create_backup,
        )

        await ctx.info(f"Applying {update_field} update...")
        update_result = await asyncio.wait_for(
            swag_service.update_config_field(update_request),
            timeout=120  # 2 minute timeout for updates
        )

        await ctx.info("Running post-update health check...")
        # Run health check and return formatted result
        health_check_result = await _run_post_update_health_check(
            swag_service, ctx, config_name, update_field, update_value
        )

        await log_action_success(ctx, f"Updated {update_field} in {config_name}")
        await ctx.info("Update completed successfully")

        # Convert service result to dict for formatter
        result_data = {
            "success": True,
            "backup_created": update_result.backup_created,
        }

        return formatter.format_update_result(
            result_data, config_name, update_field, update_value, health_check_result
        )

    except asyncio.CancelledError:
        await ctx.info("Configuration update cancelled by user")
        raise
    except TimeoutError:
        await ctx.info("Configuration update timed out")
        return formatter.format_error_result(
            "Update operation timed out", "update"
        )

