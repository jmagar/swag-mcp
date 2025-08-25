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
            await ctx.error(error_msg)
            raise
        except FileNotFoundError as e:
            error_msg = str(e)
            await ctx.error(error_msg)
            raise
        except ValueError as e:
            error_msg = str(e)
            await ctx.error(error_msg)
            raise
        except Exception as e:
            error_msg = f"Failed to execute {func.__name__}: {str(e)}"
            await ctx.error(error_msg)
            raise

    return wrapper  # type: ignore[return-value]
