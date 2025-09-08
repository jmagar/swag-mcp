"""Decorators for SWAG MCP tools."""

import logging
from collections.abc import Awaitable
from collections.abc import Callable as _Callable
from functools import wraps
from typing import TYPE_CHECKING, Concatenate, ParamSpec, TypeVar, cast

from fastmcp import Context
from fastmcp.tools.tool import ToolResult
from pydantic import ValidationError

from swag_mcp.utils.error_handlers import handle_os_error

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
    Includes graceful fallback if formatter import fails.

    Returns:
        Cached TokenEfficientFormatter instance, or None if import fails

    """
    global _cached_formatter
    if _cached_formatter is None:
        try:
            from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter
            _cached_formatter = TokenEfficientFormatter()
        except ImportError as e:
            logger.error(f"Failed to import TokenEfficientFormatter: {e}")
            # Create a minimal fallback formatter
            _cached_formatter = _create_fallback_formatter()
    return _cached_formatter


def _create_fallback_formatter() -> "TokenEfficientFormatter":
    """Create a minimal fallback formatter when import fails.

    Returns:
        A minimal formatter-like object with basic error formatting capability

    """
    class FallbackFormatter:
        def format_error_result(self, error_message: str, action: str) -> ToolResult:
            """Format error result without dependencies."""
            from fastmcp.tools.tool import ToolResult
            from mcp.types import TextContent

            formatted_content = f"❌ {action.replace('_', ' ').title()} failed: {error_message}"
            structured_data = {"success": False, "error": error_message, "action": action}

            return ToolResult(
                content=[TextContent(type="text", text=formatted_content)],
                structured_content=structured_data,
            )

    return cast("TokenEfficientFormatter", FallbackFormatter())


def handle_tool_errors(
    func: _Callable[Concatenate[Context, P], Awaitable[R]],
) -> _Callable[Concatenate[Context, P], Awaitable[R | ToolResult]]:
    """Handle common tool errors with comprehensive error handling and user-friendly messages.

    Handles:
    - ValidationError: Invalid request parameters with field-specific details
    - FileNotFoundError: Configuration files not found with helpful suggestions
    - PermissionError: File system permission issues with actionable advice
    - OSError: System-level errors with user-friendly explanations
    - TimeoutError: Network/operation timeouts with recovery suggestions
    - ValueError: Business logic errors with context
    - ImportError: Module import failures with graceful degradation
    - Exception: Generic errors with safe fallback

    All exceptions are logged with full stack traces (exc_info=True) for debugging.
    Error messages are formatted to be user-friendly while preserving technical details in logs.

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
            # Format validation errors with field-specific details
            error_details = []
            for err in e.errors():
                field = ".".join(str(loc) for loc in err["loc"])
                error_details.append(f"{field}: {err['msg']}")
            error_msg = f"Parameter validation failed: {'; '.join(error_details)}"
            logger.error(f"Validation error in {func.__name__}: {error_msg}", exc_info=True)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, func.__name__)

        except FileNotFoundError as e:
            # Provide helpful context for missing files
            filename = getattr(e, 'filename', 'unknown file')
            error_msg = f"File not found: {filename}. Check the path and ensure the file exists."
            logger.error(f"File not found in {func.__name__}: {filename}", exc_info=True)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, func.__name__)

        except PermissionError as e:
            # Provide actionable advice for permission errors
            filename = getattr(e, 'filename', 'file')
            error_msg = (
                f"Permission denied accessing '{filename}'. "
                f"Check file permissions and Docker volume mounts."
            )
            logger.error(f"Permission error in {func.__name__}: {filename}", exc_info=True)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, func.__name__)

        except OSError as e:
            # Use specialized OS error handling for user-friendly messages
            try:
                handle_os_error(e, f"tool operation {func.__name__}")
            except OSError as handled_error:
                error_msg = str(handled_error)
                logger.error(f"OS error in {func.__name__}: {error_msg}", exc_info=True)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, func.__name__)

        except TimeoutError as e:
            # Provide recovery suggestions for timeouts
            error_msg = (
                f"Operation timed out: {str(e)}. "
                f"Try increasing timeout or check network connectivity."
            )
            logger.error(f"Timeout error in {func.__name__}: {error_msg}", exc_info=True)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, func.__name__)

        except ValueError as e:
            # Business logic errors with context preservation
            error_msg = str(e)
            logger.error(f"Value error in {func.__name__}: {error_msg}", exc_info=True)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, func.__name__)

        except ImportError as e:
            # Handle module import failures gracefully
            error_msg = f"Module import failed: {str(e)}. Check dependencies and installation."
            logger.error(f"Import error in {func.__name__}: {error_msg}", exc_info=True)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, func.__name__)

        except Exception as e:
            # Catch-all with safe error messages
            error_msg = f"Unexpected error: {str(e)}. Check server logs for details."
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            formatter = _get_token_formatter()
            return formatter.format_error_result(error_msg, func.__name__)

    return wrapper


# Alias for backward compatibility
with_error_handling = handle_tool_errors
