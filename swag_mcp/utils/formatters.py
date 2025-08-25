"""Formatting utilities for SWAG MCP server."""

from typing import Any


def format_health_check_result(result: Any) -> tuple[str, str]:
    """Format health check result for display.

    Args:
        result: Health check result object with attributes:
            - success: bool
            - status_code: int | None
            - response_time_ms: int | None
            - response_body: str | None
            - url: str
            - error: str | None

    Returns:
        Tuple of (formatted_message, status_for_logging)

    """
    if result.success:
        status_icon = "✅"
        status_text = f"{result.status_code} OK"
        time_text = f"({result.response_time_ms}ms)" if result.response_time_ms else ""

        response_info = ""
        if result.response_body:
            # Clean up response body for display
            body = result.response_body.strip()
            if body:
                response_info = f"\nResponse: {body}"

        message = f"{status_icon} {result.url} - {status_text} {time_text}{response_info}"
        status = "successful"

    else:
        status_icon = "❌"
        if result.status_code:
            status_text = f"{result.status_code}"
            time_text = f"({result.response_time_ms}ms)" if result.response_time_ms else ""
        else:
            status_text = "Failed"
            time_text = ""

        error_info = f" - {result.error}" if result.error else ""
        message = f"{status_icon} {result.url} - {status_text} {time_text}{error_info}"
        status = f"failed: {result.error}" if result.error else "failed"

    return message, status
