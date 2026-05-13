"""SWAG FastMCP Server - Main entry point."""

import asyncio
import json
import logging
import os
import secrets
import sys
from datetime import datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as metadata_version
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.resources import DirectoryResource
from fastmcp.server.auth import AccessToken, AuthProvider
from pydantic import AnyUrl
from starlette.requests import Request
from starlette.responses import JSONResponse

from swag_mcp.core.config import SwagConfig as SwagConfig  # re-export for tests
from swag_mcp.core.config import config
from swag_mcp.core.constants import (
    CONF_EXTENSION,
    CONF_PATTERN,
    CONFIG_TYPE_SUBDOMAIN,
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
    "StaticBearerTokenProvider",
    "CompositeAuthProvider",
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


class StaticBearerTokenProvider(AuthProvider):
    """FastMCP token verifier for a single operator-configured bearer token."""

    def __init__(self, token: str) -> None:
        """Initialize the provider with the expected bearer token."""
        super().__init__()
        self._token = token

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return access metadata when the bearer token matches."""
        if not secrets.compare_digest(token, self._token):
            return None

        return AccessToken(token=token, client_id="swag-mcp-token", scopes=[])


class CompositeAuthProvider(AuthProvider):
    """Auth provider that accepts tokens validated by any configured provider."""

    def __init__(self, providers: list[AuthProvider]) -> None:
        """Initialize with providers in verification order."""
        if not providers:
            raise ValueError("CompositeAuthProvider requires at least one provider")

        primary = providers[-1]
        super().__init__(
            base_url=primary.base_url,
            required_scopes=primary.required_scopes,
            resource_base_url=primary.resource_base_url,
        )
        self._providers = providers
        self._route_provider = primary

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return the first successful provider verification result."""
        for provider in self._providers:
            access_token = await provider.verify_token(token)
            if access_token is not None:
                if not access_token.scopes and self.required_scopes:
                    return AccessToken(
                        token=access_token.token,
                        client_id=access_token.client_id,
                        scopes=self.required_scopes,
                        expires_at=access_token.expires_at,
                        resource=access_token.resource,
                        claims=access_token.claims,
                    )
                return access_token
        return None

    def set_mcp_path(self, mcp_path: str | None) -> None:
        """Propagate the mounted MCP path to all child providers."""
        super().set_mcp_path(mcp_path)
        for provider in self._providers:
            provider.set_mcp_path(mcp_path)

    def get_routes(self, mcp_path: str | None = None) -> list:
        """Expose routes from the provider that owns OAuth/discovery endpoints."""
        return self._route_provider.get_routes(mcp_path)


def _derive_resource_base_url(base_url: str, mcp_path: str = "/mcp") -> str:
    """Return the public resource base URL FastMCP should combine with mcp_path."""
    normalized_base = base_url.rstrip("/")
    normalized_path = "/" + mcp_path.strip("/")
    if normalized_base.endswith(normalized_path):
        return normalized_base[: -len(normalized_path)] or normalized_base
    return normalized_base


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

    # Register streaming resources for real-time updates
    @mcp.resource("swag://configs/live")
    async def live_config_updates() -> str:
        """Return a current configuration-watch snapshot."""
        files = sorted(
            path.name
            for path in config_path.glob(CONF_PATTERN)
            if path.is_file() and not path.name.endswith(".sample") and ".backup." not in path.name
        )
        return json.dumps(
            {
                "type": "watcher_snapshot",
                "path": str(config_path),
                "timestamp": datetime.now().isoformat(),
                "files": files,
                "total_count": len(files),
                "message": "Configuration resource snapshot is readable",
            },
            indent=2,
        )

    @mcp.resource("swag://health/stream")
    async def health_status_stream() -> str:
        """Return a current health-monitor snapshot for active configurations."""
        from swag_mcp.services.swag_manager import SwagManagerService

        # Get active configurations to monitor
        swag_service = SwagManagerService()
        try:
            configs_result = await swag_service.list_configs("active")
            domains = [str(config_file) for config_file in configs_result.configs[:5]]
            return json.dumps(
                {
                    "type": "health_snapshot",
                    "timestamp": datetime.now().isoformat(),
                    "monitored_count": len(domains),
                    "domains": domains,
                    "message": "Health resource snapshot is readable",
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps(
                {
                    "type": "health_snapshot_error",
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e),
                },
                indent=2,
            )

    @mcp.resource("swag://logs/stream")
    async def log_stream() -> str:
        """Return a bounded SWAG nginx error log snapshot."""
        from swag_mcp.utils.mcp_streaming import create_log_streamer

        streamer = create_log_streamer(follow=False)
        chunks = []
        async for log_entry in streamer.stream_log_entries("nginx-error", 5):
            chunks.append(log_entry)
        return "".join(chunks)


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

    # Strip type suffix if present
    for suffix in (f".{CONFIG_TYPE_SUBDOMAIN}",):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break

    return name


async def create_mcp_server() -> FastMCP:
    """Create and configure the FastMCP server."""
    auth_provider = _build_auth_provider()

    # Create FastMCP server instance with or without authentication
    mcp = FastMCP("SWAG Configuration Manager", auth=auth_provider)

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
    logger.info("Version: %s", get_package_version())
    logger.info("Description: FastMCP server for managing SWAG reverse proxy configurations")
    logger.info("SWAG Proxy Confs Path: %s", config.proxy_confs_path)
    logger.info("Template path: %s", config.template_path)
    logger.info("MCP Transport: streamable-http on %s:%s", config.host, config.port)

    return mcp


def _build_auth_provider() -> AuthProvider | None:
    """Build the configured FastMCP auth provider."""
    providers: list[AuthProvider] = []
    fastmcp_auth = os.getenv("FASTMCP_SERVER_AUTH")
    token = os.getenv("SWAG_MCP_TOKEN")

    if token:
        providers.append(StaticBearerTokenProvider(token))
        logger.info("Static bearer token authentication enabled")

    if fastmcp_auth == "fastmcp.server.auth.providers.google.GoogleProvider":
        try:
            from fastmcp.server.auth.providers.google import (
                GoogleProvider,
            )

            # Configure GoogleProvider with environment variables
            client_id = os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID")
            client_secret = os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET")
            base_url = os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL", "http://localhost:8000")
            resource_base_url = os.getenv(
                "FASTMCP_SERVER_AUTH_RESOURCE_BASE_URL",
                _derive_resource_base_url(base_url),
            )
            scopes_str = os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_REQUIRED_SCOPES", "")
            scopes = [scope.strip() for scope in scopes_str.split(",") if scope.strip()]

            # Validate required OAuth credentials
            if not client_id or not client_secret:
                logger.error(
                    "Google OAuth requires both CLIENT_ID and CLIENT_SECRET environment variables"
                )
                logger.error(
                    "CLIENT_ID set: %s, CLIENT_SECRET set: %s",
                    bool(client_id),
                    bool(client_secret),
                )
                raise ValueError("Missing required OAuth credentials")

            redirect_path = os.getenv("FASTMCP_SERVER_AUTH_GOOGLE_REDIRECT_PATH", "/auth/callback")
            auth_provider = GoogleProvider(
                client_id=client_id,
                client_secret=client_secret,
                base_url=base_url,
                resource_base_url=resource_base_url,
                required_scopes=scopes,
                redirect_path=redirect_path,
            )
            providers.append(auth_provider)
            logger.info("✅ Google OAuth authentication enabled")
            logger.info("📍 OAuth base URL: %s", base_url)
            logger.info("📍 OAuth protected resource base URL: %s", resource_base_url)
            logger.info("🔑 OAuth client ID: %s...", client_id[:20])
            logger.info("🔒 OAuth scopes: %s", scopes)
        except ImportError:
            logger.exception("Failed to import GoogleProvider — cannot configure Google OAuth")
            raise
        except Exception:
            logger.exception("Failed to configure Google OAuth")
            raise
    elif fastmcp_auth:
        raise ValueError(f"Unsupported FASTMCP_SERVER_AUTH provider: {fastmcp_auth}")

    if not providers:
        logger.info("Google OAuth authentication disabled (FASTMCP_SERVER_AUTH not set)")
        return None

    if len(providers) == 1:
        return providers[0]

    logger.info("Combined bearer token and FastMCP OAuth authentication enabled")
    return CompositeAuthProvider(providers)


def setup_templates() -> None:
    """Set up and validate template directory."""
    # Ensure template directory exists
    template_path = Path(config.template_path)
    if not template_path.exists():
        logger.warning("Template directory %s does not exist, creating...", template_path)
        template_path.mkdir(parents=True, exist_ok=True)

    # Check if required templates exist
    required_templates = [
        build_template_filename(CONFIG_TYPE_SUBDOMAIN),
    ]

    for template_name in required_templates:
        template_file = template_path / template_name
        if not template_file.exists():
            logger.error("Template not found: %s", template_file)
        else:
            logger.debug("Template found: %s", template_file)


async def cleanup_old_backups() -> None:
    """Clean up old backup files on server startup."""
    try:
        async with SwagManagerService() as swag_service:
            cleaned_count = await swag_service.cleanup_old_backups()
        if cleaned_count > 0:
            logger.info("Startup cleanup: removed %d old backup files", cleaned_count)
        else:
            logger.debug("Startup cleanup: no old backup files to remove")
    except Exception as e:
        logger.error("Failed to cleanup old backups on startup: %s", e, exc_info=True)


def _validate_bearer_token() -> None:
    """Validate that direct streamable-http access has an auth decision."""
    token = os.getenv("SWAG_MCP_TOKEN")
    no_auth = os.getenv("SWAG_MCP_NO_AUTH", "").lower() in ("true", "1", "yes")
    fastmcp_auth = os.getenv("FASTMCP_SERVER_AUTH")

    if token and fastmcp_auth:
        logger.info("SWAG_MCP_TOKEN and FASTMCP_SERVER_AUTH configured; both auth paths enabled")
    elif token:
        logger.info("SWAG_MCP_TOKEN configured; static bearer auth will be enforced")
    elif fastmcp_auth:
        logger.info("FASTMCP_SERVER_AUTH configured; FastMCP auth provider will be enforced")
    elif no_auth:
        logger.warning(
            "SWAG_MCP_NO_AUTH=true; starting without MCP server authentication. "
            "Bind to loopback or protect access at the proxy/network layer."
        )
    else:
        logger.error(
            "Refusing to start without MCP server authentication. Set SWAG_MCP_TOKEN, "
            "configure FASTMCP_SERVER_AUTH, or explicitly set SWAG_MCP_NO_AUTH=true "
            "for loopback/proxy-isolated deployments."
        )
        sys.exit(1)


async def main() -> None:
    """Async entry point for when called from within an async context."""
    # Load environment variables from .env file if present
    load_dotenv()

    _validate_bearer_token()

    logger.info("Starting SWAG MCP Server with streamable-http transport (async mode)...")

    setup_templates()

    # Kick off cleanup in background — don't block server start
    asyncio.create_task(cleanup_old_backups())

    # Create the MCP server
    mcp_server = await create_mcp_server()

    # Use run_async() with streamable-http transport configuration
    # This is the correct method for existing event loops and Claude Desktop
    # NOTE: We bind to 0.0.0.0 inside the container; Docker's network namespace
    # provides isolation. SWAG_MCP_HOST controls the bind address but is forced
    # to 0.0.0.0 for localhost/container deployments so the service is reachable.
    _host = "0.0.0.0" if config.host in ("127.0.0.1", "localhost", None) else config.host
    await mcp_server.run_async(transport="streamable-http", host=_host, port=config.port)


def main_sync() -> None:
    """Run server in synchronous mode for direct execution."""
    load_dotenv()
    _validate_bearer_token()
    logger.info("Starting SWAG MCP Server with streamable-http transport (sync mode)...")

    setup_templates()

    async def _setup_and_run() -> None:
        # Kick off cleanup in background — don't block server start
        asyncio.create_task(cleanup_old_backups())

        # Create the MCP server
        mcp_server = await create_mcp_server()

        # Use run() with streamable-http transport configuration
        # Creates its own event loop for synchronous context
        # NOTE: bind forced to 0.0.0.0 inside container; see main() comment above.
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
        logger.debug("Detected running event loop: %s", type(loop))
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
        logger.error("Server error: %s", e)
        raise
