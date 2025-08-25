"""Error handling middleware for SWAG MCP server."""

import logging
import re
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from fastmcp.server.middleware import Middleware
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware, RetryMiddleware

from ..core.config import config

# Configure logger for error handling
logger = logging.getLogger("swag_mcp.middleware.error_handling")


def sanitize_error_message(error_message: str) -> str:
    """Sanitize error messages to prevent information disclosure.

    This function removes potentially sensitive information from error messages
    including template injection payloads, file paths, and internal details
    that could be exploited by attackers.

    Args:
        error_message: Raw error message that may contain sensitive information

    Returns:
        Sanitized error message safe to return to clients

    """
    # If message is empty, return generic error
    if not error_message or not error_message.strip():
        return "Invalid request parameters"

    # Sensitive patterns to remove from error messages
    sensitive_patterns = [
        # Template injection patterns
        r"\{\{.*?\}\}",  # Jinja2/Django template expressions
        r"\{%.*?%\}",  # Jinja2 template statements
        r"\$\{.*?\}",  # Various template engines (like FreeMarker)
        # File system paths (Unix and Windows)
        r"[/\\](?:etc|usr|var|opt|tmp|home|root)[/\\][^\s]*",  # Unix system paths
        r"[/\\](?:etc|passwd|shadow|hosts|fstab)[^\s]*",  # Sensitive Unix files
        r"C:[/\\][^\s]*",  # Windows paths
        r"[a-zA-Z]:[/\\][^\s]*",  # Windows drive paths
        # Dangerous function calls and imports
        r"__[a-zA-Z_]+__",  # Python dunder methods
        r"eval\s*\(",  # eval function calls
        r"exec\s*\(",  # exec function calls
        r"import\s+\w+",  # import statements
        r"from\s+\w+\s+import",  # from ... import statements
        # System commands and shell injection patterns
        r";\s*[a-zA-Z_/][^\s;]*",  # Command separators
        r"\|[^\s|]*",  # Pipe operations
        r"&[^\s&]*",  # Background processes
        r"`[^`]*`",  # Command substitution (backticks)
        r"\$\([^)]*\)",  # Command substitution $()
        # Network and URL patterns that might leak internal info
        r"https?://[^\s]+",  # URLs
        r"ftp://[^\s]+",  # FTP URLs
        r"localhost:[0-9]+",  # localhost with ports
        r"127\.0\.0\.1:[0-9]+",  # localhost IP with ports
        r"192\.168\.[0-9]+\.[0-9]+",  # Private IP ranges
        r"10\.[0-9]+\.[0-9]+\.[0-9]+",  # Private IP ranges
        # Database connection strings and credentials
        r"password[=:][^\s]+",  # Password parameters
        r"pwd[=:][^\s]+",  # Password abbreviations
        r"secret[=:][^\s]+",  # Secret parameters
        r"token[=:][^\s]+",  # Token parameters
        r"key[=:][^\s]+",  # Key parameters
        r"mysql://[^\s]+",  # MySQL connection strings
        r"postgres://[^\s]+",  # PostgreSQL connection strings
    ]

    # Start with the original message
    sanitized = error_message

    # Remove sensitive patterns
    for pattern in sensitive_patterns:
        sanitized = re.sub(pattern, "[REDACTED]", sanitized, flags=re.IGNORECASE)

    # Clean up multiple consecutive redactions
    sanitized = re.sub(r"\[REDACTED\](\s*\[REDACTED\])+", "[REDACTED]", sanitized)

    # Remove excessive whitespace
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    # If the message was completely sanitized or too short, return generic error
    if (
        not sanitized
        or sanitized == "[REDACTED]"
        or len(sanitized.replace("[REDACTED]", "").strip()) < 10
    ):
        return "Invalid request parameters"

    # Ensure message doesn't exceed reasonable length
    if len(sanitized) > 500:
        sanitized = sanitized[:497] + "..."

    return sanitized


def create_user_friendly_error(error: Exception) -> str:
    """Create user-friendly error message from exception.

    Args:
        error: Exception to convert to user-friendly message

    Returns:
        User-friendly error message

    """
    error_type = type(error).__name__
    error_str = str(error)

    # Handle specific validation error types with user-friendly messages
    if "ValidationError" in error_type:
        if "string_pattern_mismatch" in error_str:
            if "service_name" in error_str.lower():
                return "Invalid service name. Please use only letters, numbers, hyphens, and underscores."
            elif "upstream_app" in error_str.lower():
                return "Invalid upstream app name. Please use only letters, numbers, hyphens, underscores, and dots."
            else:
                return "Invalid characters in input. Please use only letters, numbers, hyphens, and underscores."
        elif "string_too_long" in error_str:
            if "service_name" in error_str.lower():
                return "Service name is too long. Please use 50 characters or less."
            else:
                return "Input value is too long. Please use a shorter value."
        elif "less_than_equal" in error_str or "greater_than_equal" in error_str:
            if "port" in error_str.lower():
                return "Port number must be between 1 and 65535."
            else:
                return "Numeric value is out of valid range."
        elif "value_error" in error_str:
            if "domain" in error_str.lower():
                return "Invalid domain format. Please check the domain name and try again."
            return "Invalid input format."
        else:
            return "Invalid request parameters. Please check your input and try again."

    elif "FileNotFoundError" in error_type:
        return "Requested file or resource not found."

    elif "PermissionError" in error_type:
        return "Access denied. Please check permissions."

    elif "TimeoutError" in error_type or "timeout" in error_str.lower():
        return "Operation timed out. Please try again later."

    elif "ConnectionError" in error_type or "connection" in error_str.lower():
        return "Connection error. Please check network connectivity."

    # Handle ToolError specifically (FastMCP wraps many errors in ToolError)
    if "ToolError" in error_type and "Error calling tool" in error_str:
        # Extract the inner error message after "Error calling tool 'tool_name': "
        import re

        match = re.search(r"Error calling tool '[^']+': (.+)", error_str)
        if match:
            inner_error = match.group(1)
            return create_user_friendly_error(Exception(inner_error))

    # For any other errors, sanitize the message
    return sanitize_error_message(error_str)


class SecurityErrorMiddleware(Middleware):
    """Security-focused error handling middleware that sanitizes error messages."""

    async def on_request(self, context: Context, call_next):
        """Handle request with security-focused error sanitization."""
        try:
            return await call_next(context)
        except Exception as error:
            # Log the full error internally for debugging
            logger.error(f"SecurityErrorMiddleware caught error: {type(error).__name__}: {error}")

            # Create sanitized user-friendly error
            sanitized_message = create_user_friendly_error(error)

            # Raise a new ToolError with sanitized message for the client
            # but preserve the original error type for internal handling
            if isinstance(error, ToolError):
                # If it's already a ToolError, update its message
                raise ToolError(sanitized_message) from error
            else:
                # Wrap other exceptions in ToolError with sanitized message
                raise ToolError(sanitized_message) from error


def swag_error_callback(error: Exception, context: Any) -> None:
    """Handle errors in SWAG-specific way.

    Args:
        error: The exception that occurred
        context: The middleware context

    """
    # Log the full error internally (with sensitive info for debugging)
    logger.error(
        f"SWAG MCP Error in {getattr(context, 'method', 'unknown')}: "
        f"{type(error).__name__}: {error}"
    )

    # Store sanitized version for client response
    if hasattr(context, "response"):
        sanitized_message = create_user_friendly_error(error)
        # Override the error message that will be sent to the client
        if hasattr(error, "__dict__"):
            error.__dict__["client_message"] = sanitized_message


def get_security_error_middleware() -> SecurityErrorMiddleware:
    """Get security-focused error handling middleware.

    Returns:
        SecurityErrorMiddleware for sanitizing error messages

    """
    return SecurityErrorMiddleware()


def get_error_handling_middleware() -> ErrorHandlingMiddleware:
    """Get configured error handling middleware.

    Returns:
        ErrorHandlingMiddleware configured for SWAG operations

    """
    return ErrorHandlingMiddleware(
        include_traceback=False, transform_errors=True, error_callback=swag_error_callback
    )


def get_retry_middleware() -> RetryMiddleware | None:
    """Get retry middleware if enabled.

    Returns:
        RetryMiddleware if enabled, None otherwise

    """
    if not config.enable_retry_middleware:
        logger.debug("Retry middleware is disabled")
        return None

    logger.info(f"Retry middleware enabled with max {config.max_retries} retries")

    # Define which exceptions should trigger retries
    retry_exceptions = (
        ConnectionError,
        TimeoutError,
        OSError,  # File system errors
    )

    return RetryMiddleware(max_retries=config.max_retries, retry_exceptions=retry_exceptions)


__all__ = [
    "get_error_handling_middleware",
    "get_retry_middleware",
    "get_security_error_middleware",
    "swag_error_callback",
    "SecurityErrorMiddleware",
    "sanitize_error_message",
    "create_user_friendly_error",
]
