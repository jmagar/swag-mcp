"""SWAG FastMCP Server - Main entry point."""

import asyncio
import logging
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as metadata_version
from pathlib import Path
from typing import Any, cast

from pydantic import AnyUrl

from fastmcp import FastMCP
from fastmcp.resources import DirectoryResource
from starlette.requests import Request
from starlette.responses import JSONResponse

from swag_mcp.core.config import SwagConfig as SwagConfig  # re-export for tests
from swag_mcp.core.config import config
from swag_mcp.core.constants import (
    CONF_EXTENSION,
    CONF_PATTERN,
    CONFIG_TYPE_SUBDOMAIN,
    CONFIG_TYPE_SUBFOLDER,
    HEALTH_ENDPOINT,
    HTTP_METHOD_GET,
    SERVICE_NAME,
    STATUS_HEALTHY,
    SWAG_URI_BASE,
)
from swag_mcp.core.logging_config import setup_logging
from swag_mcp.middleware import setup_middleware

# Re-exports for testing
from swag_mcp.middleware.error_handling import get_error_handling_middleware
from swag_mcp.middleware.rate_limiting import get_rate_limiting_middleware
from swag_mcp.middleware.request_logging import get_logging_middleware
from swag_mcp.middleware.timing import get_timing_middleware
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.tools.swag import register_tools
from swag_mcp.utils.formatters import build_template_filename

# Aliases for test compatibility (tests expect these specific names)
error_handling_middleware = get_error_handling_middleware
timing_middleware = get_timing_middleware
request_logging_middleware = get_logging_middleware
rate_limiting_middleware = get_rate_limiting_middleware


# Dummy function for test compatibility (does not register a tool)
def swag_dummy(*args: Any, **kwargs: Any) -> None:
    """No-op placeholder used by tests."""
    return None


# Alias for test compatibility
swag = swag_dummy


# Explicit re-exports expected by tests
__all__ = [
    "SwagConfig",
    "create_mcp_server",
    "register_resources",
    "get_package_version",
    "setup_templates",
    "cleanup_old_backups",
    "main",
    "main_sync",
    "detect_execution_context",
    "timing_middleware",
    "request_logging_middleware",
    "rate_limiting_middleware",
    "swag",
]

# Configure dual logging (console + files)
setup_logging()

logger = logging.getLogger(__name__)

# Cache version to avoid redundant calls
_cached_version: str | None = None


def get_package_version() -> str:
    """Get the package version dynamically from metadata."""
    global _cached_version
    if _cached_version is None:
        try:
            _cached_version = metadata_version("swag-mcp")
        except PackageNotFoundError:
            # Fallback for development or when package is not installed
            _cached_version = "dev"
    return _cached_version


def register_resources(mcp: FastMCP) -> None:
    """Register all SWAG resources with the FastMCP server using Resource classes."""
    # Get the config directory path
    config_path = Path(config.proxy_confs_path)

    # Register DirectoryResource for listing active configs
    mcp.add_resource(
        DirectoryResource(
            uri=AnyUrl(SWAG_URI_BASE),
            name="Active SWAG Configurations",
            description=(
                "List of all active SWAG reverse proxy configurations "
                f"({CONF_EXTENSION} files, excluding samples)"
            ),
            path=config_path,
            pattern=CONF_PATTERN,
        )
    )


def _extract_service_name(filename: str) -> str:
    """Extract service name from config filename.

    Handles:
    - *.conf and *.conf.sample files
    - Optional type suffixes: .subdomain / .subfolder
    - Trailing dot artifacts
    """
    name = filename

    # Remove any trailing dots first (handles cases like "file.conf.")
    name = name.rstrip(".")

    # Strip optional ".sample"
    if name.endswith(".sample"):
        name = name[: -len(".sample")]

    # Strip ".conf" extension
    if name.endswith(CONF_EXTENSION):
        name = name[: -len(CONF_EXTENSION)]

    # Strip type suffixes if present
    if name.endswith(f".{CONFIG_TYPE_SUBDOMAIN}"):
        name = name[: -len(f".{CONFIG_TYPE_SUBDOMAIN}")]
    elif name.endswith(f".{CONFIG_TYPE_SUBFOLDER}"):
        name = name[: -len(f".{CONFIG_TYPE_SUBFOLDER}")]

    return name


async def create_mcp_server() -> FastMCP:
    """Create and configure the FastMCP server."""
    # Create FastMCP server instance - only name parameter is supported
    mcp = FastMCP("SWAG Configuration Manager")

    # Configure all middleware using the setup function
    setup_middleware(mcp)

    # Register all SWAG tools
    register_tools(mcp)

    # Register SWAG resources
    register_resources(mcp)

    # Add health check endpoint for Docker health checks
    @mcp.custom_route(HEALTH_ENDPOINT, methods=[HTTP_METHOD_GET])
    async def health_check(request: Request) -> JSONResponse:
        """Health check endpoint for Docker."""
        version = get_package_version()
        payload = {"status": STATUS_HEALTHY, "service": SERVICE_NAME, "version": version}
        return JSONResponse(
            content=payload,
            status_code=200,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    logger.info("SWAG MCP Server initialized")
    logger.info(f"Version: {get_package_version()}")
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
        logger.error(f"Failed to cleanup old backups on startup: {e}", exc_info=True)


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
    _host = "0.0.0.0" if config.host in ("127.0.0.1", "localhost", None) else config.host
    await mcp_server.run_async(transport="streamable-http", host=_host, port=config.port)


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
        _host = "0.0.0.0" if config.host in ("127.0.0.1", "localhost", None) else config.host
        await mcp_server.run_async(transport="streamable-http", host=_host, port=config.port)

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
