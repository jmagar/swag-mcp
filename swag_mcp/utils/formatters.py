"""Formatting utilities for SWAG MCP server."""

from typing import Any

from swag_mcp.core.constants import (
    CONFIG_TYPE_SUBDOMAIN,
    CONFIG_TYPE_SUBFOLDER,
    SAMPLE_EXTENSION,
)


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
    if result.success:
        status_icon = "✅"
        status_code = result.status_code if result.status_code is not None else "unknown"
        status_text = f"{status_code} OK"
        time_text = (
            f"({format_duration(result.response_time_ms)})" if result.response_time_ms else ""
        )

        response_info = ""
        if result.response_body:
            # Clean up response body for display
            body = result.response_body.strip()
            if body:
                response_info = f"\nResponse: {body}"

        # Handle redirects - add arrow if redirect_url is present and different from original URL
        redirect_info = ""
        if (
            hasattr(result, "redirect_url")
            and result.redirect_url
            and result.redirect_url != result.url
        ):
            redirect_info = f" -> {result.redirect_url}"

        message = (
            f"{status_icon} {result.url} - {status_text} {time_text}{redirect_info}{response_info}"
        )
        status = "successful"

    else:
        status_icon = "❌"
        if result.status_code:
            status_text = f"{result.status_code}"
            time_text = (
                f"({format_duration(result.response_time_ms)})" if result.response_time_ms else ""
            )
        else:
            status_text = "Failed"
            time_text = ""

        error_info = f" - {result.error}" if result.error else ""
        message = f"{status_icon} {result.url} - {status_text} {time_text}{error_info}"
        status = f"failed: {result.error}" if result.error else "failed"

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


def format_config_list(list_filter: str, total_count: int) -> str:
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
