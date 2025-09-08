"""Token-efficient formatting functions for SWAG MCP tool responses.

This module implements the dual content strategy where every tool response includes:
1. Human-readable content: Token-efficient formatted text optimized for CLI usage
2. Structured content: Complete JSON data for programmatic access

Based on the Docker MCP token-efficient formatting system.
"""

import re
import unicodedata
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent

from swag_mcp.models.config import ListFilterType
from swag_mcp.models.enums import BackupSubAction
from swag_mcp.utils.formatters import format_duration, format_file_size, format_health_check_result


class TokenEfficientFormatter:
    """Formatter class for creating token-efficient responses with dual content."""

    @staticmethod
    def _nfkc(text: str) -> str:
        """Normalize Unicode text using NFKC form for consistent display.

        Args:
            text: User-provided string to normalize

        Returns:
            Unicode normalized string safe for display

        """
        return unicodedata.normalize("NFKC", text)

    def _create_tool_result(
        self, text_content: str, structured_content: Mapping[str, Any] | dict[str, Any]
    ) -> ToolResult:
        """Create ToolResult with consistent structure."""
        return ToolResult(
            content=[TextContent(type="text", text=text_content)],
            structured_content=structured_content,
        )

    def _format_success_failure(
        self,
        result: Mapping[str, Any],
        success_message: str,
        failure_template: str = "failed",
        show_backup: bool = False,
    ) -> str:
        """Format common success/failure pattern with optional backup indicator."""
        success = result.get("success", False)

        if success:
            status = "✅"
            message = f"{status} {success_message}"

            if show_backup and result.get("backup_created", False):
                message += " 💾"

            return message
        else:
            status = "❌"
            error_msg = result.get("message", "Unknown error")
            return f"{status} {failure_template}: {error_msg}"

    def format_file_size_compact(self, size_bytes: int) -> str:
        """Format file size in compact format (no spaces).

        Args:
            size_bytes: File size in bytes

        Returns:
            Formatted file size string in compact format (e.g., "1.5KB", "2.3MB")

        """
        # Use canonical formatter but remove spaces for compact display
        canonical_size = format_file_size(size_bytes)
        return canonical_size.replace(" ", "")

    def format_duration_compact(self, milliseconds: float | None) -> str:
        """Format duration in compact format (no spaces).

        Args:
            milliseconds: Duration in milliseconds, or None for unknown duration

        Returns:
            Formatted duration string in compact format

        """
        # Use canonical formatter but remove spaces for compact display
        canonical_duration = format_duration(milliseconds)
        return canonical_duration.replace(" ", "")

    @staticmethod
    def format_timestamp(timestamp: datetime) -> str:
        """Format timestamp for compact display."""
        return timestamp.strftime("%m-%d %H:%M")

    def format_list_result(
        self, result: Mapping[str, Any], list_filter: ListFilterType = "all"
    ) -> ToolResult:
        """Format configuration list with token-efficient display.

        Token Efficiency Strategy: Grouped display with status indicators and size info.

        Args:
            result: Dictionary containing:
                - configs: List[str] - list of configuration file names
                - total_count: int - total number of configurations
                - list_filter: str - filter type used
            list_filter: Type of filter applied ("all", "active", "samples")

        """
        configs: list[str] = result.get("configs", [])
        total_count = result.get("total_count", len(configs))

        if not configs:
            formatted_content = f"No configurations found (filter: {list_filter})"
            return self._create_tool_result(formatted_content, result)

        # Group configs by type for efficient display
        active_configs: list[str] = []
        sample_configs: list[str] = []

        for config in configs:
            # configs is a list of strings (file names)
            if config.endswith(".sample"):
                sample_configs.append(config)
            else:
                active_configs.append(config)

        lines = [f"SWAG configurations ({total_count} total, filter: {list_filter})"]

        if active_configs:
            lines.append(f"\n📄 Active Configs ({len(active_configs)}):")
            for config in active_configs:
                lines.append(f"  {config}")

        if sample_configs:
            lines.append(f"\n📝 Sample Configs ({len(sample_configs)}):")
            for config in sample_configs:
                lines.append(f"  {config}")

        formatted_content = "\n".join(lines)

        return self._create_tool_result(formatted_content, result)

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
        """Format view result showing the entire file with line numbers.

        Rationale: For configuration inspection, eliding lines is harmful.
        Always render the full file content so users can review every line.
        """
        content = result.get("content", "")
        character_count = result.get("character_count", len(content))

        lines = content.splitlines() if content else []
        line_count = len(lines)

        # Build compact header with safe size formatting using canonical formatter
        size_bytes = result.get("size_bytes")
        size_info = (
            self.format_file_size_compact(size_bytes)
            if isinstance(size_bytes, int) and size_bytes >= 0
            else f"{character_count} chars"
        )
        header = f"📄 {self._nfkc(config_name)} ({size_info}, {line_count} lines)"

        # Always show the full file with line numbers
        output_lines = [header, ""]
        output_lines.extend([f"  {i + 1:2d}│ {line}" for i, line in enumerate(lines)])

        formatted_content = "\n".join(output_lines)

        return self._create_tool_result(formatted_content, result)

    def format_health_check_result(self, result: Mapping[str, Any]) -> ToolResult:
        """Format health check result with status and timing.

        Token Efficiency Strategy: Single line with status indicator and metrics.
        Prefers 'success' over 'accessible' attribute for consistency.
        """
        self._nfkc(result.get("domain", "unknown"))

        # Use canonical health check formatter for consistency
        formatted_message, _ = format_health_check_result(result)
        formatted_content = formatted_message

        return self._create_tool_result(formatted_content, result)

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
        success_msg = f"Removed {config_name}"
        if result.get("backup_created", False):
            success_msg += " (backup created)"

        message = self._format_success_failure(result, success_msg, "Remove failed")
        return self._create_tool_result(message, result)

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

        # Build compact header with safe size formatting using canonical formatter
        size_info = (
            self.format_file_size_compact(character_count)
            if isinstance(character_count, int) and character_count >= 0
            else f"{character_count} chars"
        )
        header = f"📋 {self._nfkc(log_type)} logs ({actual_lines} lines, {size_info})"

        if actual_lines == 0:
            formatted_content = f"{header}\n  (no logs found)"
        else:
            # Show all lines
            preview_lines = [header, ""]
            preview_lines.extend([f"  {line}" for line in log_lines])
            formatted_content = "\n".join(preview_lines)

        return self._create_tool_result(formatted_content, result)

    def format_backup_result(
        self, result: dict[str, Any], backup_action: BackupSubAction
    ) -> ToolResult:
        """Format backup operation result.

        Token Efficiency Strategy: Summary with counts and age grouping.
        """
        if backup_action == BackupSubAction.CLEANUP:
            cleaned_count = result.get("cleaned_count", 0)
            retention_days = result.get("retention_days", "default")

            if cleaned_count > 0:
                formatted_content = (
                    f"🧹 Cleaned {cleaned_count} old backups (retention: {retention_days} days)"
                )
            else:
                # Include the keyword 'cleanup' to satisfy tests and clarity
                formatted_content = (
                    f"🧹 No old backups to cleanup (retention: {retention_days} days)"
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
                    backup_name = backup_file.get("name", "")
                    if "today" in backup_name.lower() or str(now.day) in backup_name:
                        today_count += 1
                    elif "week" in backup_name.lower():
                        week_count += 1
                    else:
                        older_count += 1

                head = f"💾 Backups: {total_count} total"
                extras: list[str] = []
                if today_count > 0:
                    extras.append(f"{today_count} today")
                if week_count > 0:
                    extras.append(f"{week_count} this week")
                if older_count > 0:
                    extras.append(f"{older_count} older")
                formatted_content = f"{head} ({', '.join(extras)})" if extras else head

        else:
            # This should not happen with proper typing, but handle gracefully
            formatted_content = f"❓ Unknown backup action: {backup_action}"  # type: ignore[unreachable]

        return self._create_tool_result(formatted_content, result)

    def format_edit_result(self, result: dict[str, Any], config_name: str) -> ToolResult:
        """Format edit result with backup status.

        Token Efficiency Strategy: Simple confirmation with backup indicator.
        """
        message = self._format_success_failure(
            result, f"Edited {config_name}", "Edit failed", show_backup=True
        )
        return self._create_tool_result(message, result)

    def format_error_result(
        self, error_message: str, action: str, additional_data: dict[str, Any] | None = None
    ) -> ToolResult:
        """Format error result with helpful context.

        Token Efficiency Strategy: Concise error with action context.
        """
        pretty_action = self._nfkc(action).replace("_", " ").replace("-", " ").strip().title()
        formatted_content = f"❌ {pretty_action} failed: {self._nfkc(error_message)}"

        structured_data = {"success": False, "error": error_message, "action": action}
        if additional_data:
            structured_data.update(additional_data)

        return self._create_tool_result(formatted_content, structured_data)
