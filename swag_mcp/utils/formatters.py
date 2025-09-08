"""Formatting utilities for SWAG MCP server."""

from datetime import datetime
from typing import Any, Literal

from swag_mcp.core.constants import (
    CONFIG_TYPE_SUBDOMAIN,
    CONFIG_TYPE_SUBFOLDER,
    SAMPLE_EXTENSION,
)


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format.
    
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


def format_duration(milliseconds: float) -> str:
    """Format duration in human-readable format.

    Args:
        milliseconds: Duration in milliseconds

    Returns:
        Formatted duration string (e.g., "1.5s", "500.0ms", "1m 0.0s")

    Examples:
        format_duration(500) -> "500.0ms"
        format_duration(1500) -> "1.5s"
        format_duration(90000) -> "1m 30.0s"

    """
    if milliseconds < 1000:
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
            - success: bool
            - status_code: int | None
            - response_time_ms: int | None
            - response_body: str | None
            - url: str
            - error: str | None
            - redirect_url: str | None

    Returns:
        Tuple of (formatted_message, status_for_logging)

    """
    # Handle both dict and object formats for backward compatibility
    success = result.get("accessible") if isinstance(result, dict) else result.success
    if success:
        status_icon = "✅"
        status_code_value = (
            result.get("status_code") if isinstance(result, dict) else result.status_code
        )
        status_code = status_code_value if status_code_value is not None else "unknown"
        # Extract just the numeric status code, removing redundant text like "OK"
        if isinstance(status_code, str) and " " in status_code:
            status_text = status_code.split()[0]  # Take first part (e.g., "200" from "200 OK")
        else:
            status_text = str(status_code)
        response_time_ms = (
            result.get("response_time_ms") if isinstance(result, dict) else result.response_time_ms
        )
        time_text = f"({format_duration(response_time_ms)})" if response_time_ms else ""

        response_info = ""
        response_body = (
            result.get("response_body") if isinstance(result, dict) else result.response_body
        )
        if response_body:
            # Clean up response body for display
            body = response_body.strip()
            if body:
                response_info = f"\nResponse: {body}"

        # Handle redirects - add arrow if redirect_url is present and different from original URL
        redirect_info = ""
        redirect_url = (
            result.get("redirect_url")
            if isinstance(result, dict)
            else getattr(result, "redirect_url", None)
        )
        url = result.get("url") if isinstance(result, dict) else getattr(result, "url", "unknown")
        if redirect_url and redirect_url != url:
            redirect_info = f" -> {redirect_url}"

        message = f"{status_icon} {url} - {status_text} {time_text}{redirect_info}{response_info}"
        status = "successful"

    else:
        status_icon = "❌"
        status_code_value = (
            result.get("status_code")
            if isinstance(result, dict)
            else getattr(result, "status_code", None)
        )
        if status_code_value:
            # Extract just the numeric status code, removing redundant text like "OK"
            if isinstance(status_code_value, str) and " " in status_code_value:
                # Take first part (e.g., "404" from "404 Not Found")
                status_text = status_code_value.split()[0]
            else:
                status_text = str(status_code_value)
            response_time_ms = (
                result.get("response_time_ms")
                if isinstance(result, dict)
                else getattr(result, "response_time_ms", None)
            )
            time_text = f"({format_duration(response_time_ms)})" if response_time_ms else ""
        else:
            status_text = "Failed"
            time_text = ""

        error_value = (
            result.get("error") if isinstance(result, dict) else getattr(result, "error", None)
        )
        url_value = (
            result.get("url") if isinstance(result, dict) else getattr(result, "url", "unknown")
        )
        error_info = f" - {error_value}" if error_value else ""
        message = f"{status_icon} {url_value} - {status_text} {time_text}{error_info}"
        status = f"failed: {error_value}" if error_value else "failed"

    return message, status


def build_template_filename(config_type: str) -> str:
    """Build a template filename from config type.

    Args:
        config_type: Type of configuration

    Returns:
        Template filename with .j2 extension

    Examples:
        build_template_filename("subdomain") -> "subdomain.conf.j2"
        build_template_filename("mcp-subdomain") -> "mcp-subdomain.conf.j2"

    Raises:
        ValueError: If config_type is not one of the valid types

    """
    valid_config_types = {"subdomain", "subfolder", "mcp-subdomain", "mcp-subfolder"}

    if config_type not in valid_config_types:
        raise ValueError(
            f"Invalid config type '{config_type}'. "
            f"Must be one of: {', '.join(sorted(valid_config_types))}"
        )

    return f"{config_type}.conf.j2"


def get_possible_sample_filenames(service_name: str) -> list[str]:
    """Get all possible sample configuration filenames for a service.

    Args:
        service_name: Name of the service

    Returns:
        List of possible sample filenames

    """
    return [
        f"{service_name}.{CONFIG_TYPE_SUBDOMAIN}{SAMPLE_EXTENSION}",
        f"{service_name}.{CONFIG_TYPE_SUBFOLDER}{SAMPLE_EXTENSION}",
    ]


def format_config_list(list_filter: Literal["all", "active", "samples"], total_count: int) -> str:
    """Format configuration list message for display.

    Args:
        list_filter: The filter used for listing ('all', 'active', 'samples')
        total_count: Total number of configurations found

    Returns:
        Formatted message string for display

    Examples:
        format_config_list("all", 5) -> "Found 5 configurations (all types)"
        format_config_list("active", 3) -> "Found 3 active configurations"
        format_config_list("samples", 0) -> "No sample configurations found"

    """
    # Use dictionary lookup for cleaner conditionals
    no_results_messages = {
        "all": "No configurations found",
        "active": "No active configurations found",
        "samples": "No sample configurations found",
    }

    if total_count == 0:
        return no_results_messages.get(list_filter, f"No {list_filter} configurations found")

    # Handle singular vs plural
    config_word = "configuration" if total_count == 1 else "configurations"

    # Use dictionary lookup for found messages
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

        # Format file size using utility function
        if isinstance(size_bytes, int):
            size_str = format_file_size(size_bytes)
        else:
            size_str = "unknown size"

        # Format timestamp using utility function
        if hasattr(modified_time, "strftime"):
            time_str = format_timestamp(modified_time)
        else:
            time_str = str(modified_time)

        # Choose icon based on file type
        icon = "📝" if is_sample else "📄"

        details.append(f"  {icon} {name} ({size_str}, {time_str})")

    return "\n".join(details)
