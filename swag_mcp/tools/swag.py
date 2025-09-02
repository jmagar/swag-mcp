"""Unified FastMCP tool for SWAG configuration management."""

import logging
from typing import Annotated, Any, Literal, assert_never, cast

from fastmcp import Context, FastMCP
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
from swag_mcp.utils.formatters import format_health_check_result
from swag_mcp.utils.tool_decorators import handle_tool_errors
from swag_mcp.utils.tool_helpers import (
    build_config_response,
    error_response,
    format_backup_message,
    log_action_start,
    log_action_success,
    success_response,
    validate_list_filter,
    validate_required_params,
)

from ..core.constants import (
    VALID_UPSTREAM_PATTERN,
)
from ..models.config import (
    SwagConfigRequest,
    SwagEditRequest,
    SwagHealthCheckRequest,
    SwagLogsRequest,
    SwagRemoveRequest,
    SwagUpdateRequest,
)
from ..models.enums import BackupSubAction, SwagAction
from ..services.swag_manager import SwagManagerService
from ..utils.formatters import format_config_list, format_health_check_result
from ..utils.tool_decorators import handle_tool_errors
from ..utils.tool_helpers import (
    build_config_response,
    error_response,
    format_backup_message,
    log_action_start,
    log_action_success,
    success_response,
)

logger = logging.getLogger(__name__)

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
        import re

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
            domain=server_name,
            timeout=15,
            follow_redirects=True,
        )

        health_result = await swag_service.health_check(health_request)

        if health_result.success:
            health_status = (
                f"✅ Health check passed: {health_result.status_code} "
                f"({health_result.response_time_ms}ms)"
            )
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
    """Register the unified SWAG tool with the FastMCP server."""

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
            str,
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
                    "Authentication method: 'none' | 'ldap' | 'authelia' | 'authentik' | 'tinyauth'"
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
            str,
            Field(
                default="",
                description="Backup action: 'cleanup' or 'list'",
            ),
        ] = "",
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
            str,
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
    ) -> dict[str, Any]:
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

        # Dispatch based on action using if/elif pattern (following Docker-MCP pattern)
        try:
            if action == SwagAction.LIST:
                await log_action_start(ctx, "Listing SWAG configurations", list_filter)

                if error := validate_list_filter(list_filter):
                    return error

                result = await swag_service.list_configs(list_filter)

                # Use standardized formatter for consistency
                formatted_message = format_config_list(list_filter, result.total_count)
                await log_action_success(ctx, formatted_message)

                return success_response(
                    formatted_message,
                    total_count=result.total_count,
                    configs=result.configs,
                    list_filter=list_filter,
                )

            elif action == SwagAction.CREATE:
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
                    return error

                # Use parameters directly (no need for defaults preparation)
                auth_method_final = auth_method if auth_method != "none" else "authelia"
                enable_quic_final = enable_quic

                await log_action_start(ctx, "Creating configuration", config_name)

                # Convert parameters to new request model
                config_request = SwagConfigRequest(
                    config_name=config_name,
                    server_name=server_name,
                    upstream_app=upstream_app,
                    upstream_port=upstream_port,
                    upstream_proto=upstream_proto,  # type: ignore[arg-type]
                    mcp_enabled=mcp_enabled,
                    auth_method=auth_method_final,  # type: ignore[arg-type]
                    enable_quic=enable_quic_final,
                )

                # Create configuration
                create_result = await swag_service.create_config(config_request)
                await log_action_success(ctx, f"Successfully created {create_result.filename}")

                # Run health check and return formatted result
                health_check_result = await _run_post_create_health_check(
                    swag_service, ctx, server_name, create_result.filename
                )

                return success_response(
                    f"Created {create_result.filename}",
                    filename=create_result.filename,
                    health_check=health_check_result,
                )

            elif action == SwagAction.VIEW:
                if error := validate_required_params(
                    {
                        "config_name": (config_name, "config_name"),
                    },
                    "view",
                ):
                    return error

                await log_action_start(ctx, "Reading configuration", config_name)

                try:
                    content = await swag_service.read_config(config_name)
                    await log_action_success(
                        ctx, f"Successfully read {config_name} ({len(content)} characters)"
                    )
                    return success_response(
                        f"Read {config_name}",
                        config_name=config_name,
                        content=content,
                        character_count=len(content),
                    )
                except FileNotFoundError as e:
                    return error_response(str(e))

            elif action == SwagAction.EDIT:
                if error := validate_required_params(
                    {
                        "config_name": (config_name, "config_name"),
                        "new_content": (new_content, "new_content"),
                    },
                    "edit",
                ):
                    return error

                await log_action_start(ctx, "Editing configuration", config_name)

                edit_request = SwagEditRequest(
                    config_name=config_name,
                    new_content=new_content,
                    create_backup=create_backup,
                )

                edit_result = await swag_service.update_config(edit_request)

                return build_config_response(
                    config_name=config_name,
                    operation="Updated",
                    backup_created=edit_result.backup_created,
                )

            elif action == SwagAction.REMOVE:
                if error := validate_required_params(
                    {
                        "config_name": (config_name, "config_name"),
                    },
                    "remove",
                ):
                    return error

                await log_action_start(ctx, "Removing configuration", config_name)

                remove_request = SwagRemoveRequest(
                    config_name=config_name, create_backup=create_backup
                )

                remove_result = await swag_service.remove_config(remove_request)

                return build_config_response(
                    config_name=config_name,
                    operation="Removed",
                    backup_created=remove_result.backup_created,
                )

            elif action == SwagAction.LOGS:
                await log_action_start(ctx, f"Retrieving SWAG {log_type} logs", f"{lines} lines")

                logs_request = SwagLogsRequest(log_type=log_type, lines=lines)

                logs_output = await swag_service.get_swag_logs(logs_request)
                await log_action_success(
                    ctx,
                    f"Retrieved {len(logs_output)} characters of {log_type} log output",
                )

                return success_response(
                    f"Retrieved {lines} lines of {log_type} logs",
                    log_type=log_type,
                    lines_requested=lines,
                    logs=logs_output,
                    character_count=len(logs_output),
                )

            elif action == SwagAction.BACKUPS:
                if error := validate_required_params(
                    {
                        "backup_action": (backup_action, "backup_action"),
                    },
                    "backups",
                ):
                    return error

                # Validate backup_action
                if backup_action not in ["cleanup", "list"]:
                    return error_response(
                        "Invalid backup_action. Must be 'cleanup' or 'list'",
                        "validation_error",
                    )

                # Dispatch to appropriate sub-action
                if backup_action == BackupSubAction.CLEANUP:
                    retention_msg = (
                        f"{retention_days} days retention"
                        if retention_days > 0
                        else "default retention"
                    )
                    await log_action_start(ctx, "Running backup cleanup", retention_msg)

                    retention_days_param = retention_days if retention_days > 0 else None
                    cleaned_count = await swag_service.cleanup_old_backups(retention_days_param)

                    if cleaned_count > 0:
                        message = f"Cleaned up {cleaned_count} old backup files"
                    else:
                        message = "No old backup files to clean up"

                    await log_action_success(ctx, message)
                    return success_response(
                        message,
                        cleaned_count=cleaned_count,
                        retention_days=retention_days_param,
                    )

                elif backup_action == BackupSubAction.LIST:
                    await log_action_start(ctx, "Listing backup files", "all backup files")

                    backup_files = await swag_service.list_backups()

                    if not backup_files:
                        message = "No backup files found"
                    else:
                        message = f"Found {len(backup_files)} backup files"

                    await log_action_success(ctx, message)
                    return success_response(
                        message,
                        backup_files=backup_files,
                        total_count=len(backup_files),
                    )

            elif action == SwagAction.HEALTH_CHECK:
                if error := validate_required_params(
                    {
                        "domain": (domain, "domain"),
                    },
                    "health_check",
                ):
                    return error

                await log_action_start(ctx, "Starting health check", domain)

                # Validate and create health check request
                health_request = SwagHealthCheckRequest(
                    domain=domain,
                    timeout=timeout,
                    follow_redirects=follow_redirects,
                )

                # Perform health check
                health_result = await swag_service.health_check(health_request)

                # Format the response using helper function
                message, status = format_health_check_result(health_result)
                await log_action_success(ctx, f"Health check {status} for {domain}")

                # Use success/error response based on health check result
                if health_result.success:
                    return success_response(
                        message,
                        domain=domain,
                        status=status,
                        status_code=health_result.status_code,
                        response_time_ms=health_result.response_time_ms,
                    )
                else:
                    return error_response(health_result.error or "Health check failed")

            elif action == SwagAction.UPDATE:
                if error := validate_required_params(
                    {
                        "config_name": (config_name, "config_name"),
                        "update_field": (update_field, "update_field"),
                        "update_value": (update_value, "update_value"),
                    },
                    "update",
                ):
                    return error

                await log_action_start(
                    ctx, f"Updating {update_field}", f"{config_name} to {update_value}"
                )

                update_request = SwagUpdateRequest(
                    config_name=config_name,
                    update_field=cast(Literal["port", "upstream", "app", "add_mcp"], update_field),
                    update_value=update_value,
                    create_backup=create_backup,
                )

                update_result = await swag_service.update_config_field(update_request)

                # Run health check and return formatted result
                health_check_result = await _run_post_update_health_check(
                    swag_service, ctx, config_name, update_field, update_value
                )

                base_message = format_backup_message(
                    f"Updated {update_field} in {config_name}", update_result.backup_created
                )

                await log_action_success(ctx, base_message)
                return success_response(
                    base_message,
                    config_name=config_name,
                    field=update_field,
                    new_value=update_value,
                    backup_created=update_result.backup_created,
                    health_check=health_check_result,
                )

            else:
                # This should never be reached since all SwagAction enum values are handled above
                assert_never(action)

        except Exception as e:
            logger.error(f"SWAG tool error - action: {action.value}, error: {str(e)}")
            return error_response(
                f"Tool execution failed: {str(e)}",
                action=action.value,
            )
