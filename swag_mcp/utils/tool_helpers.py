"""Helper utilities for SWAG MCP tools to reduce code duplication."""

import logging
from typing import Any

from fastmcp import Context

logger = logging.getLogger(__name__)


def validate_required_params(
    params: dict[str, tuple[Any, str]], action: str
) -> dict[str, Any] | None:
    """Validate required parameters for an action.

    Args:
        params: Dict of {param_name: (value, description)}
        action: Action name for error messages

    Returns:
        Error dict if validation fails, None if all valid

    """
    for _param_name, (value, description) in params.items():
        if not value:
            return {"success": False, "error": f"{description} is required for {action} action"}
    return None


def success_response(message: str, **kwargs: Any) -> dict[str, Any]:
    """Build a success response with common fields.

    Args:
        message: Success message
        **kwargs: Additional fields to include

    Returns:
        Success response dictionary

    """
    return {"success": True, "message": message, **kwargs}


def error_response(error: str, action: str | None = None) -> dict[str, Any]:
    """Build an error response with common fields.

    Args:
        error: Error message
        action: Optional action name

    Returns:
        Error response dictionary

    """
    response = {"success": False, "error": error}
    if action:
        response["action"] = action
    return response


def format_backup_message(base_message: str, backup_name: str | None) -> str:
    """Format message with backup information.

    Args:
        base_message: Base message text
        backup_name: Optional backup filename

    Returns:
        Formatted message with backup info if present

    """
    if backup_name:
        return f"{base_message}, backup created: {backup_name}"
    return f"{base_message} (no backup created)"


async def log_action_start(ctx: Context, action: str, details: str) -> None:
    """Log the start of an action with consistent formatting.

    Args:
        ctx: FastMCP context for logging
        action: Action being performed
        details: Action details

    """
    await ctx.info(f"{action}: {details}")


async def log_action_success(ctx: Context, message: str) -> None:
    """Log successful completion of an action.

    Args:
        ctx: FastMCP context for logging
        message: Success message

    """
    await ctx.info(message)


def build_config_response(
    config_name: str, operation: str, backup_created: str | None = None, **kwargs: Any
) -> dict[str, Any]:
    """Build a standard config operation response.

    Args:
        config_name: Configuration filename
        operation: Operation performed (e.g., "Updated", "Removed")
        backup_created: Optional backup filename
        **kwargs: Additional response fields

    Returns:
        Standard config operation response

    """
    message = format_backup_message(f"{operation} {config_name}", backup_created)

    return success_response(
        message=message, config_name=config_name, backup_created=backup_created, **kwargs
    )


def validate_config_type(config_type: str) -> dict[str, Any] | None:
    """Validate config_type parameter for list action.

    Args:
        config_type: Configuration type to validate

    Returns:
        Error dict if invalid, None if valid

    """
    if config_type not in ["all", "active", "samples"]:
        return error_response("config_type must be 'all', 'active', or 'samples'")
    return None
