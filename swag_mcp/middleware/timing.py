"""Timing middleware for SWAG MCP server."""

import logging

from fastmcp.server.middleware.timing import DetailedTimingMiddleware

# Configure logger for timing operations
logger = logging.getLogger("swag_mcp.middleware.timing")


def get_timing_middleware() -> DetailedTimingMiddleware:
    """Get configured timing middleware.

    Returns:
        DetailedTimingMiddleware configured for SWAG operations

    """
    # Create custom logger for timing
    timing_logger = logging.getLogger("swag_mcp.timing")

    return DetailedTimingMiddleware(logger=timing_logger)


__all__ = ["get_timing_middleware"]
