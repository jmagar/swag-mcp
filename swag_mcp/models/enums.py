"""Enum definitions for SWAG MCP server."""

from enum import StrEnum


class SwagAction(StrEnum):
    """Actions for SWAG configuration management."""

    LIST = "list"
    CREATE = "create"
    VIEW = "view"
    EDIT = "edit"
    UPDATE = "update"
    REMOVE = "remove"
    LOGS = "logs"
    BACKUPS = "backups"
    HEALTH_CHECK = "health_check"


class BackupSubAction(StrEnum):
    """Sub-actions for backup management."""

    CLEANUP = "cleanup"
    LIST = "list"
