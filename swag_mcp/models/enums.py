"""Enum definitions for SWAG MCP server."""

from enum import Enum


class SwagAction(str, Enum):
    """Actions for SWAG configuration management."""

    LIST = "list"
    CREATE = "create"
    VIEW = "view"
    EDIT = "edit"
    CONFIG = "config"
    REMOVE = "remove"
    LOGS = "logs"
    CLEANUP_BACKUPS = "cleanup_backups"
    HEALTH_CHECK = "health_check"