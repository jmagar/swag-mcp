"""SWAG FastMCP Server - Main entry point."""

import asyncio
import logging
import sys
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.resources import DirectoryResource
from starlette.requests import Request
from starlette.responses import Response

from swag_mcp.core.config import config
from swag_mcp.core.constants import (
    CONF_EXTENSION,
    CONF_PATTERN,
    CONFIG_TYPE_SUBDOMAIN,
    CONFIG_TYPE_SUBFOLDER,
    HEALTH_ENDPOINT,
    HTTP_METHOD_GET,
    MIME_TYPE_APPLICATION_JSON,
    SAMPLE_EXTENSION,
    SAMPLE_PATTERN,
    SERVICE_NAME,
    STATUS_HEALTHY,
    SWAG_URI_BASE,
    SWAG_URI_SAMPLES,
)
from swag_mcp.core.logging_config import setup_logging
from swag_mcp.middleware import setup_middleware
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.tools.swag import register_tools
from swag_mcp.utils.formatters import build_template_filename

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
            uri=SWAG_URI_BASE,  # type: ignore[arg-type]
            name="Active SWAG Configurations",
            description=(
                "List of all active SWAG reverse proxy configurations "
                f"({CONF_EXTENSION} files, excluding samples)"
            ),
            path=config_path,
            pattern=CONF_PATTERN,
        )
    )

    # Register DirectoryResource for listing sample configs
    mcp.add_resource(
        DirectoryResource(
            uri=SWAG_URI_SAMPLES,  # type: ignore[arg-type]
            name="SWAG Sample Configurations",
            description=(
                f"List of available SWAG sample configurations ({SAMPLE_EXTENSION} files) "
                "that can be used as templates"
            ),
            path=config_path,
            pattern=SAMPLE_PATTERN,
        )
    )


def _extract_service_name(filename: str) -> str:
    """Extract service name from config filename."""
    # Remove .conf extension and any type suffixes like .subdomain or .subfolder
    name = filename.replace(CONF_EXTENSION, "")
    if name.endswith(f".{CONFIG_TYPE_SUBDOMAIN}"):
        return name.replace(f".{CONFIG_TYPE_SUBDOMAIN}", "")
    elif name.endswith(f".{CONFIG_TYPE_SUBFOLDER}"):
        return name.replace(f".{CONFIG_TYPE_SUBFOLDER}", "")
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
    @mcp.custom_route(HEALTH_ENDPOINT, methods=[HTTP_METHOD_GET])
    async def health_check(request: Request) -> Response:
        """Health check endpoint for Docker."""
        return Response(
            content=f'{{"status": "{STATUS_HEALTHY}", "service": "{SERVICE_NAME}"}}',
            media_type=MIME_TYPE_APPLICATION_JSON,
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

    # Check if required templates exist
    required_templates = [
        build_template_filename(CONFIG_TYPE_SUBDOMAIN),
        build_template_filename(CONFIG_TYPE_SUBFOLDER),
        build_template_filename(f"mcp-{CONFIG_TYPE_SUBDOMAIN}"),
        build_template_filename(f"mcp-{CONFIG_TYPE_SUBFOLDER}"),
    ]

    for template_name in required_templates:
        template_file = template_path / template_name
        if not template_file.exists():
            logger.error(f"Template not found: {template_file}")
        else:
            logger.debug(f"Template found: {template_file}")


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


def main_sync() -> None:
    """Run server in synchronous mode for direct execution."""
    logger.info("Starting SWAG MCP Server with streamable-http transport (sync mode)...")

    setup_templates()

    async def _setup_and_run() -> None:
        # Clean up old backup files on startup
        await cleanup_old_backups()

        # Create the MCP server
        mcp_server = await create_mcp_server()

        # Use run() with streamable-http transport configuration
        # Creates its own event loop for synchronous context
        await mcp_server.run_async(transport="streamable-http", host=config.host, port=config.port)

    # Run with asyncio for sync context
    asyncio.run(_setup_and_run())


def detect_execution_context() -> str:
    """Detect the execution context and choose the appropriate entry point.

    Returns:
        str: 'async' if already in an event loop, 'sync' otherwise

    """
    try:
        # Try to get the running event loop
        loop = asyncio.get_running_loop()
        logger.debug(f"Detected running event loop: {type(loop)}")
        return "async"
    except RuntimeError:
        logger.debug("No running event loop detected")
        return "sync"


if __name__ == "__main__":
    try:
        context = detect_execution_context()

        if context == "async":
            # We're already in an async context (e.g., Jupyter, test runners, or uv run)
            logger.info("Detected existing async context - this may cause issues")
            logger.info("Recommended: Use 'python -m swag_mcp' or 'fastmcp dev' instead")

            # Try to run anyway using the sync entry point
            # This will fail gracefully if there's a conflict
            main_sync()
        else:
            # No async context, safe to use asyncio.run()
            logger.info("Using standard asyncio.run() execution")
            asyncio.run(main())

    except KeyboardInterrupt:
        logger.info("Server shutdown by user")
    except RuntimeError as e:
        if "Already running" in str(e):
            logger.error("Event loop conflict detected!")
            logger.error(
                "This script cannot be run from an async context that already has an event loop."
            )
            logger.error("Solutions:")
            logger.error("  1. Use 'python -m swag_mcp' instead")
            logger.error("  2. Use 'fastmcp dev' instead")
            logger.error("  3. Run this script directly with 'python swag_mcp/server.py'")
            sys.exit(1)
        else:
            raise
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        raise
