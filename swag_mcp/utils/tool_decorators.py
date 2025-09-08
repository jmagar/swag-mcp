"""Decorators for SWAG MCP tools."""

import logging
from collections.abc import Awaitable
from collections.abc import Callable as _Callable
from functools import wraps
from typing import TYPE_CHECKING, Concatenate, ParamSpec, TypeVar

from fastmcp import Context
from fastmcp.tools.tool import ToolResult
from pydantic import ValidationError

if TYPE_CHECKING:
    from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")

# Module-level variable to cache the formatter instance
_cached_formatter: "TokenEfficientFormatter | None" = None


def _get_token_formatter() -> "TokenEfficientFormatter":
    """Lazy factory function that imports and caches TokenEfficientFormatter on first call.

    This avoids repeated import and instantiation in exception handlers.

    Returns:
        Cached TokenEfficientFormatter instance

    """
    global _cached_formatter
    if _cached_formatter is None:
        from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter

        _cached_formatter = TokenEfficientFormatter()
    return _cached_formatter


def handle_tool_errors(
    func: _Callable[Concatenate[Context, P], Awaitable[R]],
) -> _Callable[Concatenate[Context, P], Awaitable[R | ToolResult]]:
    """Handle common tool errors with consistent logging.

    Handles:
    - ValidationError: Invalid request parameters
    - FileNotFoundError: Configuration files not found
    - ValueError: Business logic errors
    - Exception: Generic errors

    Args:
        func: Tool function to wrap

    Returns:
        Wrapped async function that returns `R` on success or `ToolResult` on failure.

    """

    @wraps(func)
    async def wrapper(ctx: Context, *args: P.args, **kwargs: P.kwargs) -> R | ToolResult:
        try:
            return await func(ctx, *args, **kwargs)
        except ValidationError as e:
            error_msg = f"Invalid parameters for {func.__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            # Use cached formatter for consistent error formatting
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, func.__name__)
        except FileNotFoundError as e:
            error_msg = str(e)
            logger.error(error_msg, exc_info=True)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, func.__name__)
        except ValueError as e:
            error_msg = str(e)
            logger.error(error_msg, exc_info=True)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, func.__name__)
        except Exception as e:
            error_msg = f"Failed to execute {func.__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, func.__name__)

    return wrapper
