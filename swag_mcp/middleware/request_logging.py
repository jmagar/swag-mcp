"""Logging middleware for SWAG MCP server."""

import logging

from fastmcp.server.middleware.logging import LoggingMiddleware, StructuredLoggingMiddleware

from ..core.config import config

# Configure logger for SWAG operations
logger = logging.getLogger("swag_mcp.middleware.logging")


def get_logging_middleware() -> LoggingMiddleware | StructuredLoggingMiddleware:
    """Get configured logging middleware based on configuration.

    Returns:
        Either LoggingMiddleware or StructuredLoggingMiddleware based on config

    """
    # Create custom logger for middleware
    middleware_logger = logging.getLogger("swag_mcp.middleware")

    if config.enable_structured_logging:
        return StructuredLoggingMiddleware(
            logger=middleware_logger,
            include_payloads=config.log_payloads,
        )
    else:
        return LoggingMiddleware(
            logger=middleware_logger,
            include_payloads=config.log_payloads,
            max_payload_length=config.log_payload_max_length,
        )


__all__ = ["get_logging_middleware"]
