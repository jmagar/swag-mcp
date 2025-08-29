"""Unified FastMCP tool for SWAG configuration management."""

import logging
from typing import Annotated, Any, Literal

from fastmcp import Context, FastMCP
from pydantic import Field

from ..core.config import config
from ..core.constants import (
    VALID_NAME_PATTERN,
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
from ..models.enums import SwagAction
from ..services.swag_manager import SwagManagerService
from ..utils.formatters import format_health_check_result
from ..utils.tool_decorators import handle_tool_errors
from ..utils.tool_helpers import (
    build_config_response,
    error_response,
    format_backup_message,
    log_action_start,
    log_action_success,
    success_response,
    validate_config_type,
    validate_required_params,
)

logger = logging.getLogger(__name__)

# Initialize the SWAG manager service
swag_service = SwagManagerService()


async def _extract_server_name_from_config(config_name: str) -> str | None:
    """Extract server_name from nginx config file.

    Args:
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


async def _run_health_check(ctx: Context, server_name: str) -> str:
    """Run health check for a domain and return formatted status.

    Args:
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


async def _run_post_create_health_check(ctx: Context, server_name: str, filename: str) -> str:
    """Run health check after config creation and format results."""
    health_status = await _run_health_check(ctx, server_name)
    return f"Created configuration: {filename}\n{health_status}"


async def _run_post_update_health_check(
    ctx: Context, config_name: str, field: str, new_value: str
) -> str:
    """Run health check after config update and format results."""
    # Extract server name from config
    server_name = await _extract_server_name_from_config(config_name)
    if not server_name:
        # Can't determine server name, skip health check
        return f"Updated {field} in {config_name} to {new_value}"

    health_status = await _run_health_check(ctx, server_name)
    return f"Updated {field} in {config_name} to {new_value}\n{health_status}"


def register_tools(mcp: FastMCP) -> None:
    """Register the unified SWAG tool with the FastMCP server."""

    @mcp.tool
    @handle_tool_errors
    async def swag(
        ctx: Context,
        action: Annotated[SwagAction, Field(description="Action to perform")],
        # List parameters
        config_type: Annotated[
            str,
            Field(
                default="all",
                description="Type of configurations to list: 'all' | 'active' | 'samples'",
            ),
        ] = "all",
        # Create parameters
        service_name: Annotated[
            str,
            Field(
                default="",
                description="Service identifier used for filename",
                max_length=50,
                pattern=VALID_NAME_PATTERN.replace("+", "*"),  # Make optional for tool parameters
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
        config_type_create: Annotated[
            str,
            Field(
                default="subdomain",
                description=(
                    "Type of configuration to generate: 'subdomain' | 'subfolder' | "
                    "'mcp-subdomain' | 'mcp-subfolder'"
                ),
            ),
        ] = "subdomain",
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
        # View/Edit/Remove parameters
        config_name: Annotated[
            str,
            Field(
                default="",
                description="Configuration file name (with or without extension)",
                max_length=255,
                pattern=VALID_UPSTREAM_PATTERN.replace("+", "*"),  # Optional
            ),
        ] = "",
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
        # Cleanup parameters
        retention_days: Annotated[
            int,
            Field(
                default=0,
                ge=0,
                description="Days to retain backup files (uses config default if not specified)",
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
                description="Field to update: 'port' | 'upstream' | 'app'",
            ),
        ] = "",
        update_value: Annotated[
            str,
            Field(
                default="",
                description="New value for the field (port number, app name, or app:port)",
            ),
        ] = "",
    ) -> dict[str, Any]:
        """Unified SWAG reverse proxy configuration management tool.

        This single tool handles all SWAG operations based on the 'action' parameter.
        Different actions use different parameters.

        Actions:
        • list: List configuration files
          - Required: action
          - Optional: config_type (default: "all")

        • create: Create new reverse proxy configuration
          - Required: action, service_name, server_name, upstream_app, upstream_port
          - Optional: upstream_proto, config_type_create, auth_method, enable_quic

        • view: View configuration file contents
          - Required: action, config_name

        • edit: Edit existing configuration
          - Required: action, config_name, new_content
          - Optional: create_backup

        • update: Update specific field in existing configuration
          - Required: action, config_name, update_field, update_value
          - Optional: create_backup
          - update_field options: 'port' | 'upstream' | 'app'

        • config: View current default settings
          - Required: action

        • remove: Remove configuration file
          - Required: action, config_name
          - Optional: create_backup

        • logs: Show SWAG docker container logs
          - Required: action
          - Optional: lines

        • cleanup_backups: Clean up old backup files
          - Required: action
          - Optional: retention_days

        • health_check: Perform health check on service endpoint
          - Required: action, domain
          - Optional: timeout, follow_redirects

        Examples:
          swag(action="create", service_name="jellyfin", server_name="media.example.com",
               upstream_app="jellyfin", upstream_port=8096)
          swag(action="list", config_type="active")
          swag(action="view", config_name="plex")
          swag(action="update", config_name="crawler.subdomain.conf", update_field="port",
               update_value="8011")

        """
        # Dispatch based on action using if/elif pattern (following Docker-MCP pattern)
        try:
            if action == SwagAction.LIST:
                await log_action_start(ctx, "Listing SWAG configurations", config_type)

                if error := validate_config_type(config_type):
                    return error

                result = await swag_service.list_configs(config_type)
                await log_action_success(ctx, f"Found {result.total_count} configurations")

                return success_response(
                    f"Listed {result.total_count} {config_type} configurations",
                    total_count=result.total_count,
                    configs=result.configs,
                    config_type=config_type,
                )

            elif action == SwagAction.CREATE:
                # Validate required parameters
                if error := validate_required_params(
                    {
                        "service_name": (service_name, "service_name"),
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

                # Prepare configuration defaults
                (
                    auth_method_final,
                    enable_quic_final,
                    config_type_final,
                ) = swag_service.prepare_config_defaults(
                    auth_method, enable_quic, config_type_create
                )

                await log_action_start(
                    ctx, f"Creating {config_type_final} configuration", service_name
                )

                # Convert parameters to existing request model
                config_request = SwagConfigRequest(
                    service_name=service_name,
                    server_name=server_name,
                    upstream_app=upstream_app,
                    upstream_port=upstream_port,
                    upstream_proto=upstream_proto,  # type: ignore[arg-type]
                    config_type=config_type_final,  # type: ignore[arg-type]
                    auth_method=auth_method_final,  # type: ignore[arg-type]
                    enable_quic=enable_quic_final,
                )

                # Check if template exists
                if not await swag_service.validate_template_exists(config_type_final):
                    return error_response(
                        f"Template for {config_type_final} configuration not found"
                    )

                # Create configuration
                create_result = await swag_service.create_config(config_request)
                await log_action_success(ctx, f"Successfully created {create_result.filename}")

                # Run health check and return formatted result
                health_check_result = await _run_post_create_health_check(
                    ctx, server_name, create_result.filename
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

            elif action == SwagAction.CONFIG:
                await log_action_start(
                    ctx, "Retrieving current default configuration", "environment variables"
                )

                current_defaults = {
                    "default_auth_method": config.default_auth_method,
                    "default_quic_enabled": config.default_quic_enabled,
                    "default_config_type": config.default_config_type,
                }

                await log_action_success(ctx, "Retrieved current defaults")
                return success_response(
                    "Current defaults retrieved. To change these values, "
                    "update your .env file and restart the server.",
                    defaults=current_defaults,
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

            elif action == SwagAction.CLEANUP_BACKUPS:
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
                    update_field=update_field,  # type: ignore[arg-type]
                    update_value=update_value,
                    create_backup=create_backup,
                )

                update_result = await swag_service.update_config_field(update_request)

                # Run health check and return formatted result
                health_check_result = await _run_post_update_health_check(
                    ctx, config_name, update_field, update_value
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

        except Exception as e:
            logger.error(f"SWAG tool error - action: {action.value}, error: {str(e)}")
            return error_response(
                f"Tool execution failed: {str(e)}",
                action=action.value,
            )
