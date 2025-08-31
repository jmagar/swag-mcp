"""Enum definitions for SWAG MCP server."""

from enum import Enum


class SwagAction(str, Enum):
    """Actions for SWAG configuration management."""

    LIST = "list"
    CREATE = "create"
    VIEW = "view"
    EDIT = "edit"
    UPDATE = "update"
    CONFIG = "config"
    REMOVE = "remove"
    LOGS = "logs"
    BACKUPS = "backups"
    HEALTH_CHECK = "health_check"


class BackupSubAction(str, Enum):
    """Sub-actions for backup management."""

    CLEANUP = "cleanup"
    LIST = "list"
