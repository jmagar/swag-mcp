"""Decorators for SWAG MCP tools."""

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from pydantic import ValidationError

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")

# Lazy formatter factory to avoid duplication
_formatter_instance = None


def _get_token_formatter() -> Any:
    """Get cached TokenEfficientFormatter instance."""
    global _formatter_instance
    if _formatter_instance is None:
        from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter

        _formatter_instance = TokenEfficientFormatter()
    return _formatter_instance


def handle_tool_errors(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
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
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
        try:
            return await func(*args, **kwargs)
        except ValidationError as e:
            error_msg = f"Invalid parameters for {func.__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            # Return error instead of raising to maintain return type contract
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, "validation")
        except FileNotFoundError as e:
            error_msg = str(e)
            logger.error(error_msg)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, "file_not_found")
        except ValueError as e:
            error_msg = str(e)
            logger.error(error_msg)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, "value_error")
        except Exception as e:
            error_msg = f"Failed to execute {func.__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, "unexpected_error")

    return wrapper
