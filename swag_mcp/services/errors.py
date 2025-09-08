"""Service-level exception definitions for SWAG MCP."""

from collections.abc import Mapping
from typing import Any, Self


class SwagServiceError(Exception):
    """Base exception for service-level errors with context and cause support."""

    def __init__(
        self,
        message: str,
        *,
        context: Mapping[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        """Initialize SwagServiceError with optional context and cause.

        Args:
            message: Human-readable error message
            context: Additional context information for debugging
            cause: Original exception that caused this error

        """
        super().__init__(message)
        self.message = message
        self.context: dict[str, Any] = dict(context or {})
        self.cause = cause

        # Set proper Python exception chaining
        if cause is not None:
            self.__cause__ = cause

    def __str__(self) -> str:
        """Return formatted error message with context if available."""
        result = self.message
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            result = f"{result} (context: {context_str})"
        return result

    def with_context(self, **kwargs: Any) -> Self:
        """Return new error instance with additional context."""
        new_context = {**self.context, **kwargs}
        return self.__class__(self.message, context=new_context, cause=self.cause)


class ValidationError(SwagServiceError):
    """Configuration validation failed."""

    pass


class ConfigurationNotFoundError(SwagServiceError):
    """Configuration file not found."""

    pass


class TemplateRenderError(SwagServiceError):
    """Template rendering failed."""

    pass


class FileOperationError(SwagServiceError):
    """File operation failed."""

    pass
