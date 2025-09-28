"""Comprehensive error code system for SWAG MCP."""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Structured error codes for better error categorization and handling."""

    # Validation errors (E001-E099)
    INVALID_CONFIG_TYPE = "E001"
    EMPTY_CONTENT = "E002"
    FILE_NOT_FOUND = "E003"
    INVALID_UPDATE_FIELD = "E004"
    INVALID_DOMAIN_FORMAT = "E005"
    INVALID_PORT_NUMBER = "E006"
    INVALID_SERVICE_NAME = "E007"
    INVALID_MCP_PATH = "E008"
    INVALID_UPSTREAM_APP = "E009"
    INVALID_FILE_CONTENT = "E010"

    # File operations (E100-E199)
    FILE_PERMISSION_DENIED = "E100"
    FILE_READ_ERROR = "E101"
    FILE_WRITE_ERROR = "E102"
    BACKUP_CREATION_FAILED = "E103"
    CONFIG_SYNTAX_ERROR = "E104"

    # Concurrency and locking (E200-E299)
    DEADLOCK_PREVENTION = "E200"
    LOCK_TIMEOUT = "E201"
    RESOURCE_BUSY = "E202"
    RACE_CONDITION_DETECTED = "E203"

    # Network and health checks (E300-E399)
    HEALTH_CHECK_FAILED = "E300"
    CONNECTION_TIMEOUT = "E301"
    SSL_VERIFICATION_FAILED = "E302"
    HTTP_SESSION_ERROR = "E303"

    # Template and rendering (E400-E499)
    TEMPLATE_NOT_FOUND = "E400"
    TEMPLATE_SYNTAX_ERROR = "E401"
    TEMPLATE_RENDER_ERROR = "E402"
    TEMPLATE_VARIABLE_ERROR = "E403"

    # Service and system (E500-E599)
    SERVICE_UNAVAILABLE = "E500"
    CONFIGURATION_ERROR = "E501"
    INITIALIZATION_FAILED = "E502"
    CLEANUP_FAILED = "E503"


@dataclass
class SwagValidationError(ValueError):
    """Custom validation error with structured error code."""

    code: ErrorCode
    message: str
    context: dict[str, Any] | None = None

    def __str__(self) -> str:
        """Return string representation of validation error."""
        ctx = f" ({self.context})" if self.context else ""
        return f"[{self.code}] {self.message}{ctx}"


@dataclass
class SwagOperationError(Exception):
    """Custom operation error with structured error code."""

    code: ErrorCode
    message: str
    context: dict[str, Any] | None = None
    original_error: Exception | None = None

    def __str__(self) -> str:
        """Return string representation of operation error."""
        ctx = f" ({self.context})" if self.context else ""
        orig = f" [Caused by: {self.original_error}]" if self.original_error else ""
        return f"[{self.code}] {self.message}{ctx}{orig}"


def create_validation_error(
    code: ErrorCode,
    message: str,
    context: dict[str, Any] | None = None
) -> SwagValidationError:
    """Create validation errors with structured error codes."""
    return SwagValidationError(code=code, message=message, context=context)


def create_operation_error(
    code: ErrorCode,
    message: str,
    context: dict[str, Any] | None = None,
    original_error: Exception | None = None
) -> SwagOperationError:
    """Create operation errors with structured error codes."""
    return SwagOperationError(
        code=code,
        message=message,
        context=context,
        original_error=original_error
    )
