"""SWAG FastMCP Server - Main entry point."""

import asyncio
import logging
import sys
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.resources import DirectoryResource, FileResource
from starlette.requests import Request
from starlette.responses import Response

from swag_mcp.constants import HEALTH_CHECK_PATH
from swag_mcp.core.config import config
from swag_mcp.core.logging_config import setup_logging
from swag_mcp.middleware import setup_middleware
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.tools.swag import register_tools

# Configure dual logging (console + files)
setup_logging()

logger = logging.getLogger(__name__)


async def register_resources(mcp: FastMCP, swag_service: SwagManagerService) -> None:
    """Register all SWAG resources with the FastMCP server using Resource classes."""
    # Get the config directory path
    config_path = Path(config.proxy_confs_path)

    # Register DirectoryResource for listing active configs
    mcp.add_resource(
        DirectoryResource(
            uri="swag://",  # type: ignore[arg-type]
            name="Active SWAG Configurations",
            description=(
                "List of all active SWAG reverse proxy configurations "
                "(.conf files, excluding samples)"
            ),
            path=config_path,
            pattern="*.conf",
        )
    )

    # Register DirectoryResource for listing sample configs
    mcp.add_resource(
        DirectoryResource(
            uri="swag://samples/",  # type: ignore[arg-type]
            name="SWAG Sample Configurations",
            description=(
                "List of available SWAG sample configurations (.sample files) "
                "that can be used as templates"
            ),
            path=config_path,
            pattern="*.sample",
        )
    )

    # Register FileResource instances for each config file
    # Register active config files
    for conf_file in config_path.glob("*.conf"):
        if not conf_file.name.endswith(".sample") and ".backup." not in conf_file.name:
            service_name = _extract_service_name(conf_file.name)
            mcp.add_resource(
                FileResource(
                    uri=f"swag://{service_name}",  # type: ignore[arg-type]
                    name=f"SWAG Config: {service_name}",
                    description=f"Active SWAG configuration for {service_name} service",
                    path=conf_file,
                    mime_type="text/plain",
                )
            )

    # Register sample config files
    for sample_file in config_path.glob("*.sample"):
        service_name = _extract_service_name(sample_file.name.replace(".sample", ""))
        mcp.add_resource(
            FileResource(
                uri=f"swag://samples/{service_name}",  # type: ignore[arg-type]
                name=f"SWAG Sample: {service_name}",
                description=f"Sample SWAG configuration template for {service_name} service",
                path=sample_file,
                mime_type="text/plain",
            )
        )


def _extract_service_name(filename: str) -> str:
    """Extract service name from config filename."""
    # Remove .conf extension and any type suffixes like .subdomain or .subfolder
    name = filename.replace(".conf", "")
    if name.endswith(".subdomain"):
        return name.replace(".subdomain", "")
    elif name.endswith(".subfolder"):
        return name.replace(".subfolder", "")
    return name


async def create_mcp_server() -> FastMCP:
    """Create and configure the FastMCP server."""
    # Create FastMCP server instance - only name parameter is supported
    mcp = FastMCP("SWAG Configuration Manager")

    # Configure all middleware using the setup function
    setup_middleware(mcp)

    # Initialize SWAG manager service for resources
    swag_service = SwagManagerService()

    # Register all SWAG tools
    register_tools(mcp)

    # Register SWAG resources
    await register_resources(mcp, swag_service)

    # Add health check endpoint for Docker health checks
    @mcp.custom_route(HEALTH_CHECK_PATH, methods=["GET"])
    async def health_check(request: Request) -> Response:
        """Health check endpoint for Docker."""
        return Response(
            content='{"status": "healthy", "service": "swag-mcp"}',
            media_type="application/json",
            status_code=200,
        )

    logger.info("SWAG MCP Server initialized")
    logger.info("Version: 1.0.0")
    logger.info("Description: FastMCP server for managing SWAG reverse proxy configurations")
    logger.info(f"SWAG Proxy Confs Path: {config.proxy_confs_path}")
    logger.info(f"Template path: {config.template_path}")
    logger.info(f"MCP Transport: streamable-http on {config.host}:{config.port}")

    return mcp


def setup_templates() -> None:
    """Set up and validate template directory."""
    # Ensure template directory exists
    template_path = Path(config.template_path)
    if not template_path.exists():
        logger.warning(f"Template directory {template_path} does not exist, creating...")
        template_path.mkdir(parents=True, exist_ok=True)

    # Check if templates exist
    subdomain_template = template_path / "subdomain.conf.j2"
    subfolder_template = template_path / "subfolder.conf.j2"

    if not subdomain_template.exists():
        logger.error(f"Subdomain template not found: {subdomain_template}")
    if not subfolder_template.exists():
        logger.error(f"Subfolder template not found: {subfolder_template}")


async def cleanup_old_backups() -> None:
    """Clean up old backup files on server startup."""
    try:
        swag_service = SwagManagerService()
        cleaned_count = await swag_service.cleanup_old_backups()
        if cleaned_count > 0:
            logger.info(f"Startup cleanup: removed {cleaned_count} old backup files")
        else:
            logger.debug("Startup cleanup: no old backup files to remove")
    except Exception as e:
        logger.error(f"Failed to cleanup old backups on startup: {e}")


async def main() -> None:
    """Async entry point for when called from within an async context."""
    logger.info("Starting SWAG MCP Server with streamable-http transport (async mode)...")

    setup_templates()

    # Clean up old backup files on startup
    await cleanup_old_backups()

    # Create the MCP server
    mcp_server = await create_mcp_server()

    # Use run_async() with streamable-http transport configuration
    # This is the correct method for existing event loops and Claude Desktop
    await mcp_server.run_async(transport="streamable-http", host=config.host, port=config.port)


def is_event_loop_running() -> bool:
    """Check if an event loop is already running.

    Returns:
        bool: True if an event loop is running, False otherwise
    """
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


if __name__ == "__main__":
    try:
        if is_event_loop_running():
            # Event loop already running - provide clear error message
            logger.error("Cannot start server: Event loop already running")
            logger.error("Please use one of these methods instead:")
            logger.error("  1. python -m swag_mcp")
            logger.error("  2. fastmcp dev")
            logger.error("  3. Run directly: python swag_mcp/server.py")
            sys.exit(1)
        
        # No event loop running - safe to start
        logger.info("Starting SWAG MCP Server...")
        asyncio.run(main())
        
    except KeyboardInterrupt:
        logger.info("Server shutdown by user")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        raise
