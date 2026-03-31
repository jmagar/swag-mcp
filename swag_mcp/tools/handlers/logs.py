"""Handler for SWAG logs action."""

import asyncio
import logging
from typing import cast

from fastmcp import Context
from fastmcp.tools.tool import ToolResult

from swag_mcp.models.config import SwagLogsRequest
from swag_mcp.models.enums import SwagAction
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter
from swag_mcp.utils.tool_helpers import log_action_start, log_action_success

logger = logging.getLogger(__name__)


async def _handle_logs_action(
    ctx: Context,
    swag_service: SwagManagerService,
    formatter: TokenEfficientFormatter,
    log_type: str,
    lines: int,
) -> ToolResult:
    """Handle LOGS action with streaming capability for large log files."""
    await log_action_start(ctx, f"Retrieving SWAG {log_type} logs", f"{lines} lines")

    try:
        await ctx.info("Accessing SWAG container logs...")

        logs_request = SwagLogsRequest(
            action=SwagAction.LOGS,
            log_type=cast(
                "Literal['nginx-access', 'nginx-error', 'fail2ban', 'letsencrypt', 'renewal']",
                log_type,
            ),
            lines=lines,
        )

        # Use timeout for log operations
        logs_output = await asyncio.wait_for(
            swag_service.get_swag_logs(logs_request),
            timeout=60,  # 1 minute timeout for log retrieval
        )

        await log_action_success(
            ctx,
            f"Retrieved {len(logs_output)} characters of {log_type} log output",
        )
        await ctx.info("Log retrieval completed")

        # Convert service result to dict for formatter
        result_data = {
            "logs": logs_output,
            "character_count": len(logs_output),
        }

        return formatter.format_logs_result(result_data, log_type, lines)

    except asyncio.CancelledError:
        await ctx.info("Log retrieval cancelled by user")
        raise
    except TimeoutError:
        await ctx.info("Log retrieval timed out")
        return formatter.format_error_result("Log retrieval operation timed out", "logs")
