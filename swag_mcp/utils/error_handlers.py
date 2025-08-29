"""Centralized error handling utilities for SWAG MCP."""

import errno
from typing import NoReturn


def handle_os_error(error: OSError, operation: str, filename: str = "") -> NoReturn:
    """Handle OSError with specific errno codes and appropriate error messages.

    Args:
        error: The OSError to handle
        operation: Description of the operation being performed
        filename: Optional filename for context

    Raises:
        OSError: With appropriate errno and descriptive message

    """
    file_context = f" for {filename}" if filename else ""

    if error.errno == errno.ENOSPC:
        raise OSError(errno.ENOSPC, f"Disk full during {operation}{file_context}") from error
    elif error.errno == errno.EDQUOT:
        raise OSError(
            errno.EDQUOT, f"Disk quota exceeded during {operation}{file_context}"
        ) from error
    elif error.errno == errno.EACCES:
        raise OSError(errno.EACCES, f"Permission denied for {operation}{file_context}") from error
    elif error.errno == errno.EROFS:
        raise OSError(
            errno.EROFS, f"Read-only filesystem prevents {operation}{file_context}"
        ) from error
    elif error.errno == errno.EIO:
        raise OSError(errno.EIO, f"I/O error during {operation}{file_context}") from error
    elif error.errno == errno.EBUSY:
        raise OSError(errno.EBUSY, f"Resource busy during {operation}{file_context}") from error
    elif error.errno == errno.EEXIST:
        raise OSError(
            errno.EEXIST, f"File already exists during {operation}{file_context}"
        ) from error
    else:
        # For unknown errno codes, preserve the original errno
        raise OSError(
            error.errno or errno.EIO, f"Failed {operation}{file_context}: {str(error)}"
        ) from error


def get_error_message(error: OSError, operation: str, filename: str = "") -> str:
    """Get a descriptive error message for an OSError without raising.

    Args:
        error: The OSError to describe
        operation: Description of the operation being performed
        filename: Optional filename for context

    Returns:
        Formatted error message string

    """
    file_context = f" for {filename}" if filename else ""

    error_messages = {
        errno.ENOSPC: f"Disk full during {operation}{file_context}",
        errno.EDQUOT: f"Disk quota exceeded during {operation}{file_context}",
        errno.EACCES: f"Permission denied for {operation}{file_context}",
        errno.EROFS: f"Read-only filesystem prevents {operation}{file_context}",
        errno.EIO: f"I/O error during {operation}{file_context}",
        errno.EBUSY: f"Resource busy during {operation}{file_context}",
        errno.EEXIST: f"File already exists during {operation}{file_context}",
    }

    return error_messages.get(
        error.errno or errno.EIO, f"Failed {operation}{file_context}: {str(error)}"
    )


# Common errno codes for disk space and permission issues
DISK_SPACE_ERRORS = {errno.ENOSPC, errno.EDQUOT}
PERMISSION_ERRORS = {errno.EACCES, errno.EROFS}
IO_ERRORS = {errno.EIO, errno.EBUSY}
