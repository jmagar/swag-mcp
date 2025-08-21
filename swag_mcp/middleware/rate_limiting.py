"""Rate limiting middleware for SWAG MCP server."""

import logging

from fastmcp.server.middleware.rate_limiting import (
    RateLimitingMiddleware,
    SlidingWindowRateLimitingMiddleware,
)

from ..core.config import config

# Configure logger for rate limiting
logger = logging.getLogger("swag_mcp.middleware.rate_limiting")


def get_rate_limiting_middleware() -> RateLimitingMiddleware | None:
    """Get configured rate limiting middleware if enabled.

    Returns:
        RateLimitingMiddleware if enabled, None otherwise

    """
    if not config.rate_limit_enabled:
        logger.debug("Rate limiting is disabled")
        return None

    logger.info(
        f"Rate limiting enabled: {config.rate_limit_rps} RPS, burst: {config.rate_limit_burst}"
    )

    return RateLimitingMiddleware(
        max_requests_per_second=config.rate_limit_rps, burst_capacity=config.rate_limit_burst
    )


def get_sliding_window_rate_limiting_middleware() -> SlidingWindowRateLimitingMiddleware | None:
    """Get sliding window rate limiting middleware if enabled.

    Returns:
        SlidingWindowRateLimitingMiddleware if enabled, None otherwise

    """
    if not config.rate_limit_enabled:
        logger.debug("Rate limiting is disabled")
        return None

    # Convert RPS to requests per minute for sliding window
    max_requests = int(config.rate_limit_rps * 60)

    logger.info(f"Sliding window rate limiting enabled: {max_requests} requests per minute")

    return SlidingWindowRateLimitingMiddleware(max_requests=max_requests, window_minutes=1)


__all__ = ["get_rate_limiting_middleware", "get_sliding_window_rate_limiting_middleware"]
