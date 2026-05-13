"""Formatting utilities for SWAG MCP server."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit

from swag_mcp.core.constants import (
    CONFIG_TYPE_SUBDOMAIN,
    CONFIG_TYPES,
    SAMPLE_EXTENSION,
)


@dataclass(frozen=True)
class _HealthCheckDisplayData:
    """Normalized health check fields used by the rendering layer."""

    success: bool
    status_code: Any
    response_time_ms: float | None
    response_body: str | None
    url: str
    error: str | None
    redirect_url: str | None


def _get_health_result_value(result: Any, field_name: str, default: Any = None) -> Any:
    """Read a health result field from dict or object inputs."""
    if isinstance(result, dict):
        return result.get(field_name, default)
    return getattr(result, field_name, default)


def _ensure_text(value: Any, default: str = "unknown") -> str:
    """Convert text-like formatter input to a display-safe string."""
    if value is None:
        return default
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _extract_status_text(status_code: Any, fallback: str) -> str:
    """Return the display status token without redundant reason text."""
    if status_code is None:
        return fallback
    status_text = _ensure_text(status_code)
    return status_text.split()[0] if " " in status_text else status_text


def _extract_domain(url: Any) -> str:
    """Return a display domain from a health check URL value."""
    url_text = _ensure_text(url)
    domain = urlsplit(url_text).netloc or url_text
    return _ensure_text(domain)


def _normalize_health_check_result(result: Any) -> _HealthCheckDisplayData:
    """Normalize dict and object health check results before rendering."""
    success = _get_health_result_value(result, "success")
    if success is None:
        success = _get_health_result_value(result, "accessible")

    return _HealthCheckDisplayData(
        success=bool(success),
        status_code=_get_health_result_value(result, "status_code"),
        response_time_ms=_get_health_result_value(result, "response_time_ms"),
        response_body=_get_health_result_value(result, "response_body"),
        url=_ensure_text(_get_health_result_value(result, "url", "unknown")),
        error=_get_health_result_value(result, "error"),
        redirect_url=_get_health_result_value(result, "redirect_url"),
    )


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    This function provides a spaced format (e.g., "1.5 KB") compared to
    TokenEfficientFormatter's compact format (e.g., "1.5KB").

    Args:
        size_bytes: File size in bytes

    Returns:
        Formatted file size string (e.g., "1.5 KB", "2.3 MB")

    Examples:
        format_file_size(0) -> "0 B"
        format_file_size(1024) -> "1.0 KB"
        format_file_size(1536) -> "1.5 KB"
        format_file_size(2097152) -> "2.0 MB"

    """
    if size_bytes == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(size_bytes)

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"


def format_timestamp(timestamp: datetime) -> str:
    """Format timestamp for user display.

    Args:
        timestamp: Datetime object to format

    Returns:
        Formatted timestamp string in YYYY-MM-DD HH:MM:SS format

    Examples:
        format_timestamp(datetime(2025, 1, 15, 14, 30, 0)) -> "2025-01-15 14:30:00"

    """
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def format_duration(milliseconds: float | None) -> str:
    """Format duration in human-readable format.

    Args:
        milliseconds: Duration in milliseconds, or None for unknown duration

    Returns:
        Formatted duration string (e.g., "1.5s", "500.0ms", "1m 0.0s")

    Examples:
        format_duration(500) -> "500.0ms"
        format_duration(1500) -> "1.5s"
        format_duration(90000) -> "1m 30.0s"
        format_duration(None) -> "unknown"
        format_duration(0) -> "0.0ms"

    """
    # Handle None values explicitly as per CodeRabbit suggestion
    if milliseconds is None:
        return "unknown"

    # Handle zero or negative values with explicit zero formatting
    if milliseconds <= 0:
        return "0.0ms"
    elif milliseconds < 1000:
        return f"{milliseconds:.1f}ms"
    elif milliseconds < 60000:
        seconds = milliseconds / 1000
        return f"{seconds:.1f}s"
    else:
        minutes = int(milliseconds // 60000)
        seconds = (milliseconds % 60000) / 1000
        return f"{minutes}m {seconds:.1f}s"


def format_health_check_result(result: Any) -> tuple[str, str]:
    """Format health check result for display.

    Args:
        result: Health check result object with attributes:
            - success: bool (preferred) or accessible: bool (fallback)
            - status_code: int | None
            - response_time_ms: int | None
            - response_body: str | None
            - url: str
            - error: str | None
            - redirect_url: str | None

    Returns:
        Tuple of (formatted_message, status_for_logging)

    """
    normalized = _normalize_health_check_result(result)
    domain = _extract_domain(normalized.url)

    if normalized.success:
        status_icon = "✅"
        status_text = _extract_status_text(normalized.status_code, "unknown")
        time_text = (
            f"({format_duration(normalized.response_time_ms)})"
            if normalized.response_time_ms is not None
            else ""
        )

        response_info = ""
        if normalized.response_body:
            # Clean up response body for display
            body = normalized.response_body.strip()
            if body:
                response_info = f"\nResponse: {body}"

        # Handle redirects - add arrow if redirect_url is present and different from original URL
        redirect_info = ""
        if normalized.redirect_url and normalized.redirect_url != normalized.url:
            redirect_info = f" -> {normalized.redirect_url}"

        message = (
            f"{status_icon} {domain} - {status_text} {time_text}{redirect_info}{response_info}"
        )
        # Check if the status code indicates success (2xx or 3xx)
        if normalized.status_code and isinstance(normalized.status_code, int):
            # 2xx and 3xx are considered successful
            status = "successful" if 200 <= normalized.status_code < 400 else "failed"
        else:
            # If accessible but no status code, assume success
            status = "successful"

    else:
        status_icon = "❌"
        if normalized.status_code:
            status_text = _extract_status_text(normalized.status_code, "Failed")
            time_text = (
                f"({format_duration(normalized.response_time_ms)})"
                if normalized.response_time_ms is not None
                else ""
            )
        else:
            status_text = "Failed"
            time_text = ""

        error_info = f" - {normalized.error}" if normalized.error else ""
        message = f"{status_icon} {domain} - {status_text} {time_text}{error_info}"
        status = f"failed: {normalized.error}" if normalized.error else "failed"

    return message, status


def build_template_filename(config_type: str) -> str:
    """Build a template filename from config type.

    Args:
        config_type: Base config type ("subdomain")

    Returns:
        Template filename: "mcp.subdomain.conf.j2"

    Raises:
        ValueError: If config_type is not valid

    """
    if config_type not in CONFIG_TYPES:
        raise ValueError(
            f"Invalid config type '{config_type}'. Must be one of: {', '.join(CONFIG_TYPES)}"
        )

    return f"mcp.{config_type}.conf.j2"


def get_possible_sample_filenames(service_name: str) -> list[str]:
    """Get all possible sample configuration filenames for a service.

    Args:
        service_name: Name of the service

    Returns:
        List of possible sample filenames

    """
    return [
        f"{service_name}.{CONFIG_TYPE_SUBDOMAIN}.conf{SAMPLE_EXTENSION}",
    ]


def format_config_list(list_filter: Literal["all", "active", "samples"], total_count: int) -> str:
    """Format configuration list message for display with consistent header format.

    Args:
        list_filter: The filter used for listing ('all', 'active', 'samples')
        total_count: Total number of configurations found

    Returns:
        Formatted message string for display following guideline specifications

    Examples:
        format_config_list("all", 5) -> "Found 5 configurations (all types)"
        format_config_list("active", 3) -> "Found 3 active configurations"
        format_config_list("samples", 0) -> "No sample configurations found"

    """
    # Standardized no-results messages aligned with guidelines
    no_results_messages = {
        "all": "No configurations found",
        "active": "No active configurations found",
        "samples": "No sample configurations found",
    }

    if total_count == 0:
        return no_results_messages.get(list_filter, f"No {list_filter} configurations found")

    # Handle singular vs plural with consistent formatting
    config_word = "configuration" if total_count == 1 else "configurations"

    # Standardized found messages aligned with header specifications
    found_messages = {
        "all": f"Found {total_count} {config_word} (all types)",
        "active": f"Found {total_count} active {config_word}",
        "samples": f"Found {total_count} sample {config_word}",
    }

    return found_messages.get(list_filter, f"Found {total_count} {list_filter} {config_word}")


def format_config_list_details(
    configs: list[dict], list_filter: Literal["all", "active", "samples"], total_count: int
) -> str:
    """Format configuration list with detailed file information for display.

    Args:
        configs: List of configuration dictionaries with file details
        list_filter: The filter used for listing ('all', 'active', 'samples')
        total_count: Total number of configurations found

    Returns:
        Formatted message string with detailed file information

    Examples:
        format_config_list_details([...], "all", 5) ->
        "Found 5 configurations (all types):
        📄 jellyfin.subdomain.conf (1.2 KB, 2025-01-15 14:30:00)
        📝 plex.sample (0.8 KB, 2025-01-15 13:45:00)"

    """
    # Get base message from existing function
    base_message = format_config_list(list_filter, total_count)

    if not configs or total_count == 0:
        return base_message

    # Add detailed file list
    details = [base_message + ":"]

    for config in configs:
        name = config.get("name", "unknown")
        size_bytes = config.get("size_bytes", 0)
        modified_time = config.get("modified_time", "unknown")
        is_sample = config.get("is_sample", False)

        # Format file size using shared TokenEfficientFormatter helper
        # Use ternary for simpler code structure
        size_str = format_file_size(size_bytes) if isinstance(size_bytes, int) else "unknown size"

        # Format timestamp using existing utility function
        # (keeps full format "YYYY-MM-DD HH:MM:SS" vs compact "MM-DD HH:MM")
        if hasattr(modified_time, "strftime"):
            time_str = format_timestamp(modified_time)
        else:
            time_str = str(modified_time)

        # Choose icon based on file type
        icon = "📝" if is_sample else "📄"

        details.append(f"  {icon} {name} ({size_str}, {time_str})")

    return "\n".join(details)
