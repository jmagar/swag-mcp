"""Decorators for SWAG MCP tools."""

import logging
from collections.abc import Awaitable
from collections.abc import Callable as _Callable
from functools import wraps
from typing import Concatenate, ParamSpec, TypeVar

from fastmcp import Context
from fastmcp.tools.tool import ToolResult
from pydantic import ValidationError

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


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
        Wrapped function with error handling

    """

    @wraps(func)
    async def wrapper(ctx: Context, *args: P.args, **kwargs: P.kwargs) -> R | ToolResult:
        try:
            return await func(ctx, *args, **kwargs)
        except ValidationError as e:
            error_msg = f"Invalid parameters for {func.__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            # Return ToolResult for error cases
            return ToolResult(content=error_msg)
        except FileNotFoundError as e:
            error_msg = str(e)
            logger.error(error_msg)
            return ToolResult(content=error_msg)
        except ValueError as e:
            error_msg = str(e)
            logger.error(error_msg)
            return ToolResult(content=error_msg)
        except Exception as e:
            error_msg = f"Failed to execute {func.__name__}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return ToolResult(content=error_msg)

    return wrapper
