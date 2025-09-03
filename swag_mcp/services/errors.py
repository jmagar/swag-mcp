"""Service-level exception definitions for SWAG MCP."""


class SwagServiceError(Exception):
    """Base exception for service-level errors."""

    pass


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