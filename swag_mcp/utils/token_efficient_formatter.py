"""Token-efficient formatting functions for SWAG MCP tool responses.

This module implements the dual content strategy where every tool response includes:
1. Human-readable content: Token-efficient formatted text optimized for CLI usage
2. Structured content: Complete JSON data for programmatic access

Based on the Docker MCP token-efficient formatting system.
"""

from datetime import datetime
from typing import Any, Literal

from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from swag_mcp.models.enums import BackupSubAction


class TokenEfficientFormatter:
    """Formatter class for creating token-efficient responses with dual content."""

    @staticmethod
    def format_file_size(size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes == 0:
            return "0B"

        units = ["B", "KB", "MB", "GB"]
        unit_index = 0
        size = float(size_bytes)

        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1

        if unit_index == 0:
            return f"{int(size)}{units[unit_index]}"
        else:
            return f"{size:.1f}{units[unit_index]}"

    @staticmethod
    def format_duration(milliseconds: float) -> str:
        """Format duration in human-readable format."""
        if milliseconds < 1000:
            return f"{milliseconds:.0f}ms"
        elif milliseconds < 60000:
            return f"{milliseconds/1000:.1f}s"
        else:
            minutes = int(milliseconds // 60000)
            seconds = (milliseconds % 60000) / 1000
            return f"{minutes}m{seconds:.1f}s"

    @staticmethod
    def format_timestamp(timestamp: datetime) -> str:
        """Format timestamp for compact display."""
        return timestamp.strftime("%m-%d %H:%M")

    def format_list_result(
        self, result: dict[str, Any], list_filter: Literal["all", "active", "samples"] = "all"
    ) -> ToolResult:
        """Format configuration list with token-efficient display.

        Token Efficiency Strategy: Grouped display with status indicators and size info.
        """
        configs = result.get("configs", [])
        total_count = result.get("total_count", len(configs))

        if not configs:
            formatted_content = f"No configurations found (filter: {list_filter})"
            return ToolResult(
                content=[TextContent(type="text", text=formatted_content)],
                structured_content=result,
            )

        # Group configs by type for efficient display
        active_configs = []
        sample_configs = []

        for config in configs:
            if config.endswith(".sample"):
                sample_configs.append(config)
            else:
                active_configs.append(config)

        lines = [f"SWAG configurations ({total_count} total, filter: {list_filter})"]

        if active_configs:
            lines.append(f"\n📄 Active Configs ({len(active_configs)}):")
            for config in active_configs[:10]:  # Show first 10
                lines.append(f"  {config}")
            if len(active_configs) > 10:
                lines.append(f"  ... +{len(active_configs) - 10} more")

        if sample_configs:
            lines.append(f"\n📝 Sample Configs ({len(sample_configs)}):")
            for config in sample_configs[:5]:  # Show first 5 samples
                lines.append(f"  {config}")
            if len(sample_configs) > 5:
                lines.append(f"  ... +{len(sample_configs) - 5} more")

        formatted_content = "\n".join(lines)

        return ToolResult(
            content=[TextContent(type="text", text=formatted_content)], structured_content=result
        )

    def format_create_result(
        self, result: dict[str, Any], filename: str, health_check: str | None = None
    ) -> ToolResult:
        """Format creation result with health check status.

        Token Efficiency Strategy: Single line with status and health info.
        """
        success = result.get("success", False)

        if success:
            status = "✅"
            message = f"{status} Created {filename}"

            if health_check:
                # Extract concise health info
                if "accessible" in health_check.lower():
                    if "200" in health_check:
                        # Extract response time
                        import re

                        time_match = re.search(r"\((\d+)ms\)", health_check)
                        time_str = f" ({time_match.group(1)}ms)" if time_match else ""
                        message += f" → accessible{time_str}"
                    else:
                        message += " → accessible"
                elif "not accessible" in health_check.lower():
                    message += " → unreachable"
                else:
                    message += " → unknown status"
        else:
            status = "❌"
            error_msg = result.get("message", "Unknown error")
            message = f"{status} Failed to create {filename}: {error_msg}"

        return ToolResult(
            content=[TextContent(type="text", text=message)], structured_content=result
        )

    def format_view_result(self, result: dict[str, Any], config_name: str) -> ToolResult:
        """Format view result with content preview and metadata.

        Token Efficiency Strategy: Metadata summary with content preview.
        """
        content = result.get("content", "")
        character_count = result.get("character_count", len(content))

        lines = content.splitlines() if content else []
        line_count = len(lines)

        # Build compact header
        size_info = self.format_file_size(character_count)
        header = f"📄 {config_name} ({size_info}, {line_count} lines)"

        # Show preview of first 5 and last 5 lines for context
        preview_lines = [header, ""]

        if line_count <= 10:
            # Show all lines if 10 or fewer
            preview_lines.extend([f"  {i+1:2d}│ {line}" for i, line in enumerate(lines)])
        else:
            # Show first 5 and last 5 with separator
            preview_lines.extend([f"  {i+1:2d}│ {line}" for i, line in enumerate(lines[:5])])
            preview_lines.append(f"  ⋮ │ ... ({line_count - 10} lines omitted)")
            preview_lines.extend(
                [f"  {i+line_count-4:2d}│ {line}" for i, line in enumerate(lines[-5:])]
            )

        formatted_content = "\n".join(preview_lines)

        return ToolResult(
            content=[TextContent(type="text", text=formatted_content)], structured_content=result
        )

    def format_health_check_result(self, result: dict[str, Any]) -> ToolResult:
        """Format health check result with status and timing.

        Token Efficiency Strategy: Single line with status indicator and metrics.
        """
        success = result.get("success", False)
        domain = result.get("domain", "unknown")

        if success:
            status_code = result.get("status_code", "unknown")
            response_time = result.get("response_time_ms", 0)
            time_str = self.format_duration(response_time)

            formatted_content = f"✅ {domain} accessible (HTTP {status_code}, {time_str})"
        else:
            error_msg = result.get("error", "Unknown error")
            formatted_content = f"❌ {domain} unreachable: {error_msg}"

        return ToolResult(
            content=[TextContent(type="text", text=formatted_content)], structured_content=result
        )

    def format_update_result(
        self,
        result: dict[str, Any],
        config_name: str,
        field: str,
        new_value: str,
        health_check: str | None = None,
    ) -> ToolResult:
        """Format update result with field change summary.

        Token Efficiency Strategy: Concise change notification with health status.
        """
        success = result.get("success", False)
        backup_created = result.get("backup_created", False)

        if success:
            status = "✅"
            backup_indicator = " 💾" if backup_created else ""
            message = f"{status} Updated {field} in {config_name} → {new_value}{backup_indicator}"

            if health_check and "accessible" in health_check.lower():
                message += " (accessible)"
            elif health_check and "unreachable" in health_check.lower():
                message += " (unreachable)"
        else:
            status = "❌"
            error_msg = result.get("message", "Unknown error")
            message = f"{status} Update failed: {error_msg}"

        return ToolResult(
            content=[TextContent(type="text", text=message)], structured_content=result
        )

    def format_remove_result(self, result: dict[str, Any], config_name: str) -> ToolResult:
        """Format removal result with backup status.

        Token Efficiency Strategy: Single line confirmation with backup indicator.
        """
        success = result.get("success", False)
        backup_created = result.get("backup_created", False)

        if success:
            status = "✅"
            backup_indicator = " (backup created)" if backup_created else ""
            message = f"{status} Removed {config_name}{backup_indicator}"
        else:
            status = "❌"
            error_msg = result.get("message", "Unknown error")
            message = f"{status} Remove failed: {error_msg}"

        return ToolResult(
            content=[TextContent(type="text", text=message)], structured_content=result
        )

    def format_logs_result(
        self, result: dict[str, Any], log_type: str, lines_requested: int
    ) -> ToolResult:
        """Format logs result with summary and preview.

        Token Efficiency Strategy: Show summary with first/last lines preview.
        """
        logs = result.get("logs", "")
        character_count = result.get("character_count", len(logs))

        log_lines = logs.splitlines() if logs else []
        actual_lines = len(log_lines)

        # Build compact header
        size_info = self.format_file_size(character_count)
        header = f"📋 {log_type} logs ({actual_lines} lines, {size_info})"

        if actual_lines == 0:
            formatted_content = f"{header}\n  (no logs found)"
        elif actual_lines <= 10:
            # Show all lines if 10 or fewer
            preview_lines = [header, ""]
            preview_lines.extend([f"  {line}" for line in log_lines])
            formatted_content = "\n".join(preview_lines)
        else:
            # Show first 3 and last 3 lines with separator
            preview_lines = [header, ""]
            preview_lines.extend([f"  {line}" for line in log_lines[:3]])
            preview_lines.append(f"  ⋮ ... ({actual_lines - 6} lines omitted)")
            preview_lines.extend([f"  {line}" for line in log_lines[-3:]])
            formatted_content = "\n".join(preview_lines)

        return ToolResult(
            content=[TextContent(type="text", text=formatted_content)], structured_content=result
        )

    def format_backup_result(self, result: dict[str, Any], backup_action: str) -> ToolResult:
        """Format backup operation result.

        Token Efficiency Strategy: Summary with counts and age grouping.
        """
        if backup_action == BackupSubAction.CLEANUP:
            cleaned_count = result.get("cleaned_count", 0)
            retention_days = result.get("retention_days", "default")

            if cleaned_count > 0:
                formatted_content = (
                    f"🧹 Cleaned {cleaned_count} old backups " f"(retention: {retention_days} days)"
                )
            else:
                # Include the keyword 'cleanup' to satisfy tests and clarity
                formatted_content = (
                    f"🧹 No old backups to cleanup " f"(retention: {retention_days} days)"
                )

        elif backup_action == BackupSubAction.LIST:
            backup_files = result.get("backup_files", [])
            total_count = result.get("total_count", len(backup_files))

            if total_count == 0:
                formatted_content = "💾 No backup files found"
            else:
                # Group by recency for summary
                now = datetime.now()
                today_count = 0
                week_count = 0
                older_count = 0

                for backup_file in backup_files:
                    # Simple heuristic based on filename timestamp if available
                    if "today" in backup_file.lower() or str(now.day) in backup_file:
                        today_count += 1
                    elif "week" in backup_file.lower():
                        week_count += 1
                    else:
                        older_count += 1

                parts = [f"💾 Backups: {total_count} total"]
                if today_count > 0:
                    parts.append(f"{today_count} today")
                if week_count > 0:
                    parts.append(f"{week_count} this week")
                if older_count > 0:
                    parts.append(f"{older_count} older")

                formatted_content = " (".join(parts) + ")" if len(parts) > 1 else parts[0]

        else:
            formatted_content = f"❓ Unknown backup action: {backup_action}"

        return ToolResult(
            content=[TextContent(type="text", text=formatted_content)], structured_content=result
        )

    def format_edit_result(self, result: dict[str, Any], config_name: str) -> ToolResult:
        """Format edit result with backup status.

        Token Efficiency Strategy: Simple confirmation with backup indicator.
        """
        success = result.get("success", False)
        backup_created = result.get("backup_created", False)

        if success:
            status = "✅"
            backup_indicator = " 💾" if backup_created else ""
            message = f"{status} Edited {config_name}{backup_indicator}"
        else:
            status = "❌"
            error_msg = result.get("message", "Unknown error")
            message = f"{status} Edit failed: {error_msg}"

        return ToolResult(
            content=[TextContent(type="text", text=message)], structured_content=result
        )

    def format_error_result(
        self, error_message: str, action: str, additional_data: dict[str, Any] | None = None
    ) -> ToolResult:
        """Format error result with helpful context.

        Token Efficiency Strategy: Concise error with action context.
        """
        formatted_content = f"❌ {action.title()} failed: {error_message}"

        structured_data = {"success": False, "error": error_message, "action": action}

        if additional_data:
            structured_data.update(additional_data)

        return ToolResult(
            content=[TextContent(type="text", text=formatted_content)],
            structured_content=structured_data,
        )
