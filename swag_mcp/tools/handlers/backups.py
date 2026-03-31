"""Handler for SWAG backups action."""

import asyncio
import logging
from typing import Any

from fastmcp import Context
from fastmcp.tools.tool import ToolResult

from swag_mcp.models.enums import BackupSubAction
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter
from swag_mcp.utils.tool_helpers import log_action_start, log_action_success

logger = logging.getLogger(__name__)


async def _handle_backups_action(
    ctx: Context,
    swag_service: SwagManagerService,
    formatter: TokenEfficientFormatter,
    backup_action: BackupSubAction,
    retention_days: int,
) -> ToolResult:
    """Handle BACKUPS action with cleanup progress reporting."""
    # eqf.18: backup_action is now the primary signal (not derived from retention_days)
    # retention_days is only used when backup_action=cleanup to set the retention window

    try:
        if backup_action == BackupSubAction.CLEANUP:
            retention_msg = (
                f"{retention_days} days retention" if retention_days > 0 else "default retention"
            )
            await log_action_start(ctx, "Running backup cleanup", retention_msg)
            await ctx.info("Scanning for old backup files...")

            retention_days_param = retention_days if retention_days > 0 else None
            cleaned_count = await swag_service.cleanup_old_backups(retention_days_param)

            if cleaned_count > 0:
                message = f"Cleaned up {cleaned_count} old backup files"
                await ctx.info(f"Cleanup completed: {cleaned_count} files removed")
            else:
                message = "No old backup files to clean up"
                await ctx.info("Cleanup completed: no files to remove")

            await log_action_success(ctx, message)

            # Convert service result to dict for formatter
            cleanup_data = {
                "cleaned_count": cleaned_count,
                "retention_days": retention_days_param or 30,  # Default fallback
            }

            return formatter.format_backup_result(cleanup_data, backup_action)

        else:  # LIST
            await log_action_start(ctx, "Listing backup files", "all backup files")
            await ctx.info("Scanning backup directory...")

            backup_files = await swag_service.list_backups()

            if not backup_files:
                message = "No backup files found"
            else:
                message = f"Found {len(backup_files)} backup files"

            await log_action_success(ctx, message)
            await ctx.info(f"Scan completed: {len(backup_files)} backup files found")

            # Convert service result to dict for formatter
            result_data: dict[str, Any] = {
                "backup_files": backup_files,
                "total_count": len(backup_files),
            }

            return formatter.format_backup_result(result_data, backup_action)

    except asyncio.CancelledError:
        await ctx.info("Backup operation cancelled by user")
        raise
