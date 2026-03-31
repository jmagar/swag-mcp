"""Handler for SWAG health_check action."""

import asyncio
import logging

from fastmcp import Context
from fastmcp.tools.tool import ToolResult

from swag_mcp.models.config import SwagHealthCheckRequest
from swag_mcp.models.enums import SwagAction
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter
from swag_mcp.utils.tool_helpers import (
    log_action_start,
    log_action_success,
    validate_required_params,
)

logger = logging.getLogger(__name__)


async def _handle_health_check_action(
    ctx: Context,
    swag_service: SwagManagerService,
    formatter: TokenEfficientFormatter,
    domain: str,
    timeout: int,
    follow_redirects: bool,
) -> ToolResult:
    """Handle HEALTH_CHECK action with progress reporting."""
    if error := validate_required_params({"domain": (domain, "domain")}, "health_check"):
        return formatter.format_error_result(error.get("message", "Missing domain"), "health_check")

    await log_action_start(ctx, "Starting health check", domain)

    try:
        await ctx.info(f"Testing connectivity to {domain}...")

        # Validate and create health check request
        health_request = SwagHealthCheckRequest(
            action=SwagAction.HEALTH_CHECK,
            domain=domain,
            timeout=timeout,
            follow_redirects=follow_redirects,
        )

        # Perform health check with timeout
        health_result = await asyncio.wait_for(
            swag_service.health_check(health_request),
            timeout=timeout + 10,  # Add buffer to service timeout
        )

        await log_action_success(ctx, f"Health check completed for {domain}")

        if health_result.success:
            await ctx.info(f"Health check passed: {health_result.status_code}")
        else:
            await ctx.info(f"Health check failed: {health_result.error}")

        # Convert service result to dict for formatter
        result_data = {
            "success": health_result.success,
            "domain": health_result.domain,
            "status_code": health_result.status_code,
            "response_time_ms": health_result.response_time_ms,
            "error": getattr(health_result, "error", None),
        }

        return formatter.format_health_check_result(result_data)

    except asyncio.CancelledError:
        await ctx.info("Health check cancelled by user")
        raise
    except TimeoutError:
        await ctx.info("Health check timed out")
        return formatter.format_error_result(f"Health check for {domain} timed out", "health_check")
