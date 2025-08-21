"""Error handling middleware for SWAG MCP server."""

import logging
from typing import Any

from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware, RetryMiddleware

from ..core.config import config

# Configure logger for error handling
logger = logging.getLogger("swag_mcp.middleware.error_handling")


def swag_error_callback(error: Exception, context: Any) -> None:
    """Handle errors in SWAG-specific way.

    Args:
        error: The exception that occurred
        context: The middleware context

    """
    logger.error(
        f"SWAG MCP Error in {getattr(context, 'method', 'unknown')}: "
        f"{type(error).__name__}: {error}"
    )


def get_error_handling_middleware() -> ErrorHandlingMiddleware:
    """Get configured error handling middleware.

    Returns:
        ErrorHandlingMiddleware configured for SWAG operations

    """
    return ErrorHandlingMiddleware(
        include_traceback=True, transform_errors=True, error_callback=swag_error_callback
    )


def get_retry_middleware() -> RetryMiddleware | None:
    """Get retry middleware if enabled.

    Returns:
        RetryMiddleware if enabled, None otherwise

    """
    if not config.enable_retry_middleware:
        logger.debug("Retry middleware is disabled")
        return None

    logger.info(f"Retry middleware enabled with max {config.max_retries} retries")

    # Define which exceptions should trigger retries
    retry_exceptions = (
        ConnectionError,
        TimeoutError,
        OSError,  # File system errors
    )

    return RetryMiddleware(max_retries=config.max_retries, retry_exceptions=retry_exceptions)


__all__ = ["get_error_handling_middleware", "get_retry_middleware", "swag_error_callback"]
