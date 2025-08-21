"""SWAG MCP Middleware package."""

import logging
from typing import TYPE_CHECKING

from fastmcp import FastMCP

if TYPE_CHECKING:
    from fastmcp.server.middleware import Middleware

from .error_handling import get_error_handling_middleware, get_retry_middleware
from .rate_limiting import get_rate_limiting_middleware
from .request_logging import get_logging_middleware
from .timing import get_timing_middleware

logger = logging.getLogger(__name__)


def setup_middleware(mcp: FastMCP) -> None:
    """Set up all middleware for the SWAG MCP server in the correct order.

    Args:
        mcp: The FastMCP server instance to configure

    """
    middleware_list: list[Middleware | None] = []

    # 1. Error handling middleware (catch all errors first)
    error_middleware = get_error_handling_middleware()
    middleware_list.append(error_middleware)
    logger.info("Added error handling middleware")

    # 2. Retry middleware (if enabled)
    retry_middleware = get_retry_middleware()
    if retry_middleware:
        middleware_list.append(retry_middleware)
        logger.info("Added retry middleware")

    # 3. Rate limiting middleware (if enabled)
    rate_limit_middleware = get_rate_limiting_middleware()
    if rate_limit_middleware:
        middleware_list.append(rate_limit_middleware)
        logger.info("Added rate limiting middleware")

    # 4. Timing middleware (performance monitoring)
    timing_middleware = get_timing_middleware()
    middleware_list.append(timing_middleware)
    logger.info("Added timing middleware")

    # 5. Logging middleware (audit trail - should be last)
    logging_middleware = get_logging_middleware()
    middleware_list.append(logging_middleware)
    logger.info("Added logging middleware")

    # Add all middleware to the server
    for middleware in middleware_list:
        if middleware:
            mcp.add_middleware(middleware)

    logger.info(f"Configured {len([m for m in middleware_list if m])} middleware components")


__all__ = [
    "setup_middleware",
    "get_logging_middleware",
    "get_timing_middleware",
    "get_rate_limiting_middleware",
    "get_error_handling_middleware",
    "get_retry_middleware",
]
