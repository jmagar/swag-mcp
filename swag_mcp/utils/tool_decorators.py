"""Decorators for SWAG MCP tools."""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from fastmcp import Context
from pydantic import ValidationError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def handle_tool_errors(func: F) -> F:
    """Handle common tool errors with consistent logging.

    Handles:
    - ValidationError: Invalid request parameters
    - FileNotFoundError: Configuration files not found
    - ValueError: Business logic errors
    - Exception: Generic errors

    Args:
        func: Tool function to wrap

    Returns:
        Wrapped function with error handling

    """

    @wraps(func)
    async def wrapper(ctx: Context, *args: Any, **kwargs: Any) -> Any:
        try:
            return await func(ctx, *args, **kwargs)
        except ValidationError as e:
            error_msg = f"Invalid parameters for {func.__name__}: {str(e)}"
            logger.error(error_msg)
            # Return error instead of raising to maintain return type contract
            from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter

            formatter = TokenEfficientFormatter()
            return formatter.format_error_result(error_msg, "validation")
        except FileNotFoundError as e:
            error_msg = str(e)
            logger.error(error_msg)
            from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter

            formatter = TokenEfficientFormatter()
            return formatter.format_error_result(error_msg, "file_not_found")
        except ValueError as e:
            error_msg = str(e)
            logger.error(error_msg)
            from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter

            formatter = TokenEfficientFormatter()
            return formatter.format_error_result(error_msg, "value_error")
        except Exception as e:
            error_msg = f"Failed to execute {func.__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter

            formatter = TokenEfficientFormatter()
            return formatter.format_error_result(error_msg, "unexpected_error")

    return wrapper  # type: ignore[return-value]
