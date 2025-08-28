"""Unified FastMCP tool for SWAG configuration management."""

import logging
from typing import Annotated, Any

from fastmcp import Context, FastMCP
from pydantic import Field

from ..core.config import config
from ..models.config import (
    SwagConfigRequest,
    SwagEditRequest,
    SwagHealthCheckRequest,
    SwagLogsRequest,
    SwagRemoveRequest,
)
from ..models.enums import SwagAction
from ..services.swag_manager import SwagManagerService
from ..utils.formatters import format_health_check_result
from ..utils.tool_decorators import handle_tool_errors

logger = logging.getLogger(__name__)

# Initialize the SWAG manager service
swag_service = SwagManagerService()


async def _run_post_create_health_check(ctx: Context, server_name: str, filename: str) -> str:
    """Run health check after config creation and format results.

    Args:
        ctx: FastMCP context for logging
        server_name: Domain name to check
        filename: Created config filename

    Returns:
        Formatted message with config creation and health check results

    """
    await ctx.info(f"Running health check for {server_name}...")

    try:
        health_request = SwagHealthCheckRequest(
            domain=server_name,
            timeout=15,  # Shorter timeout for create flow
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

        return f"Created configuration: {filename}\n{health_status}"

    except Exception as e:
        health_status = f"⚠️ Health check error: {str(e)}"
        await ctx.info(f"Health check encountered an error: {str(e)}")
        return f"Created configuration: {filename}\n{health_status}"


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
                pattern=r"^[\w-]*$",
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
                pattern=r"^[a-zA-Z0-9_.-]*$",
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
                pattern=r"^[a-zA-Z0-9_.-]*$",
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
        lines: Annotated[
            int, Field(default=100, ge=1, le=1000, description="Number of log lines to retrieve")
        ] = 100,
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

        """
        # Dispatch based on action using if/elif pattern (following Docker-MCP pattern)
        try:
            if action == SwagAction.LIST:
                await ctx.info(f"Listing SWAG configurations: {config_type}")

                if config_type not in ["all", "active", "samples"]:
                    return {
                        "success": False,
                        "error": "config_type must be 'all', 'active', or 'samples'",
                    }

                result = await swag_service.list_configs(config_type)
                await ctx.info(f"Found {result.total_count} configurations")

                return {
                    "success": True,
                    "total_count": result.total_count,
                    "configs": result.configs,
                    "config_type": config_type,
                }

            elif action == SwagAction.CREATE:
                # Validate required parameters
                if not service_name:
                    return {"success": False, "error": "service_name is required for create action"}
                if not server_name:
                    return {"success": False, "error": "server_name is required for create action"}
                if not upstream_app:
                    return {"success": False, "error": "upstream_app is required for create action"}
                if upstream_port == 0:
                    return {
                        "success": False,
                        "error": "upstream_port is required for create action",
                    }

                # Prepare configuration defaults
                (
                    auth_method_final,
                    enable_quic_final,
                    config_type_final,
                ) = swag_service.prepare_config_defaults(
                    auth_method, enable_quic, config_type_create
                )

                await ctx.info(f"Creating {config_type_final} configuration for {service_name}")

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
                    return {
                        "success": False,
                        "error": f"Template for {config_type_final} configuration not found",
                    }

                # Create configuration
                create_result = await swag_service.create_config(config_request)
                await ctx.info(f"Successfully created {create_result.filename}")

                # Run health check and return formatted result
                health_check_result = await _run_post_create_health_check(
                    ctx, server_name, create_result.filename
                )

                return {
                    "success": True,
                    "filename": create_result.filename,
                    "message": f"Created {create_result.filename}",
                    "health_check": health_check_result,
                }

            elif action == SwagAction.VIEW:
                if not config_name:
                    return {"success": False, "error": "config_name is required for view action"}

                await ctx.info(f"Reading configuration: {config_name}")

                try:
                    content = await swag_service.read_config(config_name)
                    await ctx.info(f"Successfully read {config_name} ({len(content)} characters)")
                    return {
                        "success": True,
                        "config_name": config_name,
                        "content": content,
                        "character_count": len(content),
                    }
                except FileNotFoundError as e:
                    return {"success": False, "error": str(e)}

            elif action == SwagAction.EDIT:
                if not config_name:
                    return {"success": False, "error": "config_name is required for edit action"}
                if not new_content:
                    return {"success": False, "error": "new_content is required for edit action"}

                await ctx.info(f"Editing configuration: {config_name}")

                edit_request = SwagEditRequest(
                    config_name=config_name,
                    new_content=new_content,
                    create_backup=create_backup,
                )

                edit_result = await swag_service.update_config(edit_request)

                message = f"Updated {config_name}"
                if edit_result.backup_created:
                    message += f", backup created: {edit_result.backup_created}"
                else:
                    message += " (no backup created)"

                await ctx.info(message)
                return {
                    "success": True,
                    "config_name": config_name,
                    "message": message,
                    "backup_created": edit_result.backup_created,
                }

            elif action == SwagAction.CONFIG:
                await ctx.info(
                    "Retrieving current default configuration from environment variables"
                )
                current_defaults = {
                    "default_auth_method": config.default_auth_method,
                    "default_quic_enabled": config.default_quic_enabled,
                    "default_config_type": config.default_config_type,
                }
                await ctx.info("Retrieved current defaults")
                return {
                    "success": True,
                    "defaults": current_defaults,
                    "message": (
                        "Current defaults retrieved. To change these values, update your .env file "
                        "and restart the server."
                    ),
                }

            elif action == SwagAction.REMOVE:
                if not config_name:
                    return {"success": False, "error": "config_name is required for remove action"}

                await ctx.info(f"Removing configuration: {config_name}")

                remove_request = SwagRemoveRequest(
                    config_name=config_name, create_backup=create_backup
                )

                remove_result = await swag_service.remove_config(remove_request)

                message = f"Removed {config_name}"
                if remove_result.backup_created:
                    message += f", backup created: {remove_result.backup_created}"
                else:
                    message += " (no backup created)"

                await ctx.info(message)
                return {
                    "success": True,
                    "config_name": config_name,
                    "message": message,
                    "backup_created": remove_result.backup_created,
                }

            elif action == SwagAction.LOGS:
                await ctx.info(f"Retrieving SWAG docker logs: {lines} lines")

                logs_request = SwagLogsRequest(lines=lines)

                logs_output = await swag_service.get_docker_logs(logs_request)
                await ctx.info(
                    f"Successfully retrieved {len(logs_output)} characters of log output"
                )

                return {
                    "success": True,
                    "lines_requested": lines,
                    "logs": logs_output,
                    "character_count": len(logs_output),
                }

            elif action == SwagAction.CLEANUP_BACKUPS:
                await ctx.info("Running backup cleanup...")

                retention_days_param = retention_days if retention_days > 0 else None
                cleaned_count = await swag_service.cleanup_old_backups(retention_days_param)

                if cleaned_count > 0:
                    message = f"Cleaned up {cleaned_count} old backup files"
                else:
                    message = "No old backup files to clean up"

                await ctx.info(message)
                return {
                    "success": True,
                    "cleaned_count": cleaned_count,
                    "message": message,
                    "retention_days": retention_days_param,
                }

            elif action == SwagAction.HEALTH_CHECK:
                if not domain:
                    return {"success": False, "error": "domain is required for health_check action"}

                await ctx.info(f"Starting health check for domain: {domain}")

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
                await ctx.info(f"Health check {status} for {domain}")

                return {
                    "success": health_result.success,
                    "domain": domain,
                    "status": status,
                    "message": message,
                    "status_code": health_result.status_code,
                    "response_time_ms": health_result.response_time_ms,
                    "error": health_result.error,
                }

        except Exception as e:
            logger.error(f"SWAG tool error - action: {action.value}, error: {str(e)}")
            return {
                "success": False,
                "error": f"Tool execution failed: {str(e)}",
                "action": action.value,
            }
