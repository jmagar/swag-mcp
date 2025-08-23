"""FastMCP tools for SWAG configuration management."""

import logging

from fastmcp import Context, FastMCP
from pydantic import ValidationError

from ..core.config import config
from ..models.config import (
    SwagConfigRequest,
    SwagEditRequest,
    SwagHealthCheckRequest,
    SwagLogsRequest,
    SwagRemoveRequest,
)
from ..services.swag_manager import SwagManagerService

logger = logging.getLogger(__name__)

# Initialize the SWAG manager service
swag_service = SwagManagerService()


def register_tools(mcp: FastMCP) -> None:
    """Register all SWAG tools with the FastMCP server."""

    @mcp.tool
    async def swag_list(ctx: Context, config_type: str = "all") -> list[str]:
        """List SWAG configuration files.

        Args:
            ctx: FastMCP context for logging and communication
            config_type: Type of configurations to list ("all", "active", "samples")

        Returns:
            List of configuration file names

        """
        await ctx.info(f"Listing SWAG configurations: {config_type}")

        if config_type not in ["all", "active", "samples"]:
            raise ValueError("config_type must be 'all', 'active', or 'samples'")

        try:
            result = await swag_service.list_configs(config_type)
            await ctx.info(f"Found {result.total_count} configurations")
            return result.configs
        except Exception as e:
            await ctx.error(f"Failed to list configurations: {str(e)}")
            raise

    @mcp.tool
    async def swag_create(
        ctx: Context,
        service_name: str,
        server_name: str,
        upstream_app: str,
        upstream_port: int,
        upstream_proto: str = "http",
        config_type: str | None = None,
        auth_method: str = "none",
        enable_quic: bool = False,
    ) -> str:
        """Create new SWAG reverse proxy configuration.

        Args:
            ctx: FastMCP context for logging and communication
            service_name: Service identifier (used for filename)
            server_name: Domain name (e.g., "test.tootie.tv")
            upstream_app: Container name or IP address
            upstream_port: Port number the service runs on
            upstream_proto: Protocol ("http" or "https")
            config_type: Type of configuration:
                ("subdomain", "subfolder", "mcp-subdomain", or "mcp-subfolder")
            auth_method: Authentication method ("none", "ldap", "authelia", "authentik", "tinyauth")
            enable_quic: Enable QUIC support

        Returns:
            Success message with created filename

        """
        # Use defaults from environment configuration if not specified
        if auth_method == "none":
            auth_method = "authelia"  # Default to Authelia for security
        if not enable_quic:
            enable_quic = config.default_quic_enabled
        if config_type is None:
            config_type = config.default_config_type

        await ctx.info(f"Creating {config_type} configuration for {service_name}")

        try:
            # Validate and create configuration request
            config_request = SwagConfigRequest(
                service_name=service_name,
                server_name=server_name,
                upstream_app=upstream_app,
                upstream_port=upstream_port,
                upstream_proto=upstream_proto,  # type: ignore[arg-type]
                config_type=config_type,  # type: ignore[arg-type]
                auth_method=auth_method,  # type: ignore[arg-type]
                enable_quic=enable_quic,
            )

            # Check if template exists
            if not await swag_service.validate_template_exists(config_type):
                raise ValueError(f"Template for {config_type} configuration not found")

            # Create configuration
            result = await swag_service.create_config(config_request)
            await ctx.info(f"Successfully created {result.filename}")

            # Run health check to verify the configuration works
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
                    health_status = (
                        f"⚠️ Health check failed: {health_result.error or 'Unknown error'}"
                    )
                    await ctx.info(f"Health check failed for {server_name}: {health_result.error}")

                return f"Created configuration: {result.filename}\n{health_status}"

            except Exception as e:
                health_status = f"⚠️ Health check error: {str(e)}"
                await ctx.info(f"Health check encountered an error: {str(e)}")
                return f"Created configuration: {result.filename}\n{health_status}"

        except ValidationError as e:
            error_msg = f"Invalid configuration parameters: {str(e)}"
            await ctx.error(error_msg)
            raise
        except ValueError as e:
            error_msg = str(e)
            await ctx.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"Failed to create configuration: {str(e)}"
            await ctx.error(error_msg)
            raise

    @mcp.tool
    async def swag_view(ctx: Context, config_name: str) -> str:
        """View contents of an existing configuration file.

        Args:
            ctx: FastMCP context for logging and communication
            config_name: Name of configuration file to view

        Returns:
            Configuration file contents

        """
        await ctx.info(f"Reading configuration: {config_name}")

        try:
            content = await swag_service.read_config(config_name)
            await ctx.info(f"Successfully read {config_name} ({len(content)} characters)")
            return content
        except FileNotFoundError:
            error_msg = f"Configuration {config_name} not found"
            await ctx.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"Failed to read configuration: {str(e)}"
            await ctx.error(error_msg)
            raise

    @mcp.tool
    async def swag_edit(
        ctx: Context, config_name: str, new_content: str, create_backup: bool = True
    ) -> str:
        """Edit existing configuration file.

        Args:
            ctx: FastMCP context for logging and communication
            config_name: Name of configuration file to edit
            new_content: New content for the configuration file
            create_backup: Whether to create backup before editing

        Returns:
            Success message with backup information

        """
        await ctx.info(f"Editing configuration: {config_name}")

        try:
            edit_request = SwagEditRequest(
                config_name=config_name, new_content=new_content, create_backup=create_backup
            )

            result = await swag_service.update_config(edit_request)

            if result.backup_created:
                message = f"Updated {config_name}, backup created: {result.backup_created}"
                await ctx.info(message)
                return message
            else:
                message = f"Updated {config_name} (no backup created)"
                await ctx.info(message)
                return message

        except ValidationError as e:
            error_msg = f"Invalid edit request: {str(e)}"
            await ctx.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"Failed to edit configuration: {str(e)}"
            await ctx.error(error_msg)
            raise

    @mcp.tool
    async def swag_config(
        ctx: Context,
        default_auth: str | None = None,
        enable_quic: bool | None = None,
        default_config_type: str | None = None,
    ) -> str:
        """Configure default settings for new configurations.

        Args:
            ctx: FastMCP context for logging and communication
            default_auth: Default authentication method
            enable_quic: Default QUIC setting
            default_config_type: Default configuration type
                ("subdomain", "subfolder", "mcp-subdomain", "mcp-subfolder")

        Returns:
            Current defaults if no params provided, or confirmation of updated defaults

        """
        # Show current configuration from environment variables
        await ctx.info("Retrieving current default configuration from environment variables")
        current_defaults = {
            "default_auth_method": config.default_auth_method,
            "default_quic_enabled": config.default_quic_enabled,
            "default_config_type": config.default_config_type,
        }
        message = (
            f"Current defaults: {current_defaults}\n\n"
            "Note: To change these values, update your .env file and restart the server."
        )
        await ctx.info(message)
        return message

    @mcp.tool
    async def swag_remove(ctx: Context, config_name: str, create_backup: bool = True) -> str:
        """Remove an existing SWAG configuration file.

        Args:
            ctx: FastMCP context for logging and communication
            config_name: Name of configuration file to remove (must be .conf, not .sample)
            create_backup: Whether to create backup before removing

        Returns:
            Success message with backup information

        """
        await ctx.info(f"Removing configuration: {config_name}")

        try:
            remove_request = SwagRemoveRequest(config_name=config_name, create_backup=create_backup)

            result = await swag_service.remove_config(remove_request)

            if result.backup_created:
                message = f"Removed {config_name}, backup created: {result.backup_created}"
                await ctx.info(message)
                return message
            else:
                message = f"Removed {config_name} (no backup created)"
                await ctx.info(message)
                return message

        except ValidationError as e:
            error_msg = f"Invalid remove request: {str(e)}"
            await ctx.error(error_msg)
            raise
        except FileNotFoundError:
            error_msg = f"Configuration {config_name} not found"
            await ctx.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"Failed to remove configuration: {str(e)}"
            await ctx.error(error_msg)
            raise

    @mcp.tool
    async def swag_logs(ctx: Context, lines: int = 100, follow: bool = False) -> str:
        """Show SWAG docker container logs.

        Args:
            ctx: FastMCP context for logging and communication
            lines: Number of log lines to retrieve (1-1000)
            follow: Follow log output (not recommended for normal use)

        Returns:
            Docker logs output

        """
        await ctx.info(f"Retrieving SWAG docker logs: {lines} lines")

        try:
            logs_request = SwagLogsRequest(lines=lines, follow=follow)

            logs_output = await swag_service.get_docker_logs(logs_request)
            await ctx.info(f"Successfully retrieved {len(logs_output)} characters of log output")

            return logs_output

        except ValidationError as e:
            error_msg = f"Invalid logs request: {str(e)}"
            await ctx.error(error_msg)
            raise
        except FileNotFoundError as e:
            error_msg = str(e)
            await ctx.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"Failed to retrieve logs: {str(e)}"
            await ctx.error(error_msg)
            raise

    @mcp.tool
    async def swag_cleanup_backups(ctx: Context, retention_days: int | None = None) -> str:
        """Clean up old backup files.

        Args:
            ctx: FastMCP context for logging and communication
            retention_days: Days to retain backup files (uses config default if not specified)

        Returns:
            Result of the cleanup operation

        """
        await ctx.info("Running backup cleanup...")

        try:
            cleaned_count = await swag_service.cleanup_old_backups(retention_days)

            if cleaned_count > 0:
                message = f"Cleaned up {cleaned_count} old backup files"
                await ctx.info(message)
                return message
            else:
                message = "No old backup files to clean up"
                await ctx.info(message)
                return message

        except Exception as e:
            error_msg = f"Failed to cleanup backups: {str(e)}"
            await ctx.error(error_msg)
            raise

    @mcp.tool
    async def swag_health_check(
        ctx: Context, domain: str, timeout: int = 30, follow_redirects: bool = True
    ) -> str:
        """Perform health check on a SWAG-managed service endpoint.

        Args:
            ctx: FastMCP context for logging and communication
            domain: Full domain to check health for
                (e.g., "docker-mcp.tootie.tv", "swag-mcp.tootie.tv")
            timeout: Request timeout in seconds (1-300)
            follow_redirects: Whether to follow HTTP redirects

        Returns:
            Formatted health check results

        """
        await ctx.info(f"Starting health check for domain: {domain}")

        try:
            # Validate and create health check request
            health_request = SwagHealthCheckRequest(
                domain=domain, timeout=timeout, follow_redirects=follow_redirects
            )

            # Perform health check
            result = await swag_service.health_check(health_request)

            # Format the response
            if result.success:
                status_icon = "✅"
                status_text = f"{result.status_code} OK"
                time_text = f"({result.response_time_ms}ms)" if result.response_time_ms else ""

                response_info = ""
                if result.response_body:
                    # Clean up response body for display
                    body = result.response_body.strip()
                    if body:
                        response_info = f"\nResponse: {body}"

                message = f"{status_icon} {result.url} - {status_text} {time_text}{response_info}"
                await ctx.info(f"Health check successful for {domain}")

            else:
                status_icon = "❌"
                if result.status_code:
                    status_text = f"{result.status_code}"
                    time_text = f"({result.response_time_ms}ms)" if result.response_time_ms else ""
                else:
                    status_text = "Failed"
                    time_text = ""

                error_info = f" - {result.error}" if result.error else ""
                message = f"{status_icon} {result.url} - {status_text} {time_text}{error_info}"
                await ctx.info(f"Health check failed for {domain}: {result.error}")

            return message

        except ValidationError as e:
            error_msg = f"Invalid health check parameters: {str(e)}"
            await ctx.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"Failed to perform health check: {str(e)}"
            await ctx.error(error_msg)
            raise
