"""Pydantic models for SWAG configuration management."""

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from ..core.constants import (
    VALID_CONFIG_NAME_FORMAT,
    VALID_CONFIG_NAME_PATTERN,
    VALID_CONFIG_ONLY_PATTERN,
    VALID_UPSTREAM_PATTERN,
)
from ..utils.validators import validate_domain_format


class SwagConfigRequest(BaseModel):
    """Request model for creating SWAG configurations."""

    config_name: str = Field(
        ...,
        pattern=VALID_CONFIG_NAME_FORMAT,
        description="Configuration filename (e.g., 'jellyfin.subdomain.conf')",
    )

    server_name: str = Field(..., max_length=253, description="Domain name for the service")

    upstream_app: str = Field(
        ...,
        pattern=VALID_UPSTREAM_PATTERN,
        max_length=100,
        description="Container name or IP address",
    )

    upstream_port: int = Field(..., ge=1, le=65535, description="Port number the service runs on")

    upstream_proto: Literal["http", "https"] = Field(
        default="http", description="Protocol for upstream connection"
    )

    mcp_enabled: bool = Field(default=False, description="Enable MCP/SSE support for AI services")

    auth_method: Literal["none", "ldap", "authelia", "authentik", "tinyauth"] = Field(
        default="authelia", description="Authentication method to use"
    )

    enable_quic: bool = Field(default=False, description="Enable QUIC support")

    @field_validator("server_name")
    @classmethod
    def validate_server_name(cls, v: str) -> str:
        """Validate server name format."""
        return validate_domain_format(v)

    @field_validator("config_name")
    @classmethod
    def validate_config_name(cls, v: str) -> str:
        """Validate config name format."""
        if not v or ".." in v or "/" in v or "\\" in v:
            raise ValueError("Config name contains invalid characters")
        return v


class SwagConfigResult(BaseModel):
    """Result model for SWAG configuration operations."""

    filename: str = Field(..., description="Name of the configuration file")

    content: str = Field(..., description="Configuration file content")

    backup_created: str | None = Field(default=None, description="Name of backup file if created")

    warnings: list[str] = Field(
        default_factory=list, description="List of warnings during operation"
    )


class SwagListResult(BaseModel):
    """Result model for listing SWAG configurations."""

    configs: list[str] = Field(..., description="List of configuration file names")

    total_count: int = Field(..., description="Total number of configurations found")

    config_type: str = Field(..., description="Type of configurations listed")


class SwagEditRequest(BaseModel):
    """Request model for editing SWAG configurations."""

    config_name: str = Field(
        ...,
        pattern=VALID_CONFIG_NAME_PATTERN,
        description="Name of configuration file to edit",
    )

    new_content: str | None = Field(
        default=None, description="New content for the configuration file"
    )

    # Add all create fields as optional for enhanced editing
    server_name: str | None = Field(
        default=None, max_length=253, description="Domain name for the service"
    )

    upstream_app: str | None = Field(
        default=None,
        pattern=VALID_UPSTREAM_PATTERN,
        max_length=100,
        description="Container name or IP address",
    )

    upstream_port: int | None = Field(
        default=None, ge=1, le=65535, description="Port number the service runs on"
    )

    upstream_proto: Literal["http", "https"] | None = Field(
        default=None, description="Protocol for upstream connection"
    )

    auth_method: Literal["none", "ldap", "authelia", "authentik", "tinyauth"] | None = Field(
        default=None, description="Authentication method to use"
    )

    enable_quic: bool | None = Field(default=None, description="Enable QUIC support")

    create_backup: bool = Field(
        default=True, description="Whether to create a backup before editing"
    )


class SwagRemoveRequest(BaseModel):
    """Request model for removing SWAG configurations."""

    config_name: str = Field(
        ...,
        pattern=VALID_CONFIG_ONLY_PATTERN,
        description="Name of configuration file to remove (must be .conf, not .sample)",
    )

    create_backup: bool = Field(
        default=True, description="Whether to create a backup before removing"
    )


class SwagLogsRequest(BaseModel):
    """Request model for SWAG logs."""

    log_type: Literal["nginx-access", "nginx-error", "fail2ban", "letsencrypt", "renewal"] = Field(
        default="nginx-error", description="Type of log file to read"
    )

    lines: int = Field(default=50, ge=1, le=1000, description="Number of log lines to retrieve")

    follow: bool = Field(default=False, description="Follow log output (stream mode)")


class SwagResourceList(BaseModel):
    """Model for SWAG resource listings."""

    configs: list[str] = Field(..., description="List of configuration files")

    total_count: int = Field(..., description="Total number of configurations")


class SwagHealthCheckRequest(BaseModel):
    """Request model for health check operations."""

    domain: str = Field(
        ...,
        max_length=253,
        description="Domain to check health for (e.g., docker-mcp.tootie.tv)",
    )

    timeout: int = Field(default=30, ge=1, le=300, description="Request timeout in seconds")

    follow_redirects: bool = Field(default=True, description="Whether to follow HTTP redirects")

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Validate domain format."""
        return validate_domain_format(v)


class SwagUpdateRequest(BaseModel):
    """Request model for updating specific SWAG configuration parameters."""

    config_name: str = Field(
        ...,
        pattern=VALID_CONFIG_ONLY_PATTERN,
        description="Name of configuration file to update",
    )

    update_field: Literal["port", "upstream", "app", "add_mcp"] = Field(
        ..., description="Field to update: 'port' | 'upstream' | 'app' | 'add_mcp'"
    )

    update_value: str = Field(
        ...,
        description="New value for field (port number, app name, app:port, or MCP path)",
    )

    create_backup: bool = Field(
        default=True, description="Whether to create a backup before updating"
    )

    @field_validator("update_value")
    @classmethod
    def validate_update_value_based_on_field(cls, v: str, info: Any) -> str:
        """Validate update_value based on the update_field type."""
        # Get the update_field from the model data
        if hasattr(info, "data") and "update_field" in info.data:
            update_field = info.data["update_field"]

            if update_field == "add_mcp":
                # Validate MCP path format
                if not isinstance(v, str):
                    raise ValueError("MCP path must be a string")

                if not v:
                    raise ValueError("MCP path cannot be empty")

                if not v.startswith("/"):
                    raise ValueError("MCP path must start with '/' (e.g., '/mcp', '/ai-service')")

                # Check for valid URL path characters (alphanumeric, dash, underscore, slash)
                if not re.match(r"^/[a-zA-Z0-9_/-]*$", v):
                    raise ValueError(
                        "MCP path contains invalid characters. "
                        "Only alphanumeric characters, dashes, underscores, and slashes are allowed"
                    )

                # Prevent path traversal attempts
                if ".." in v or "//" in v:
                    raise ValueError("MCP path cannot contain '..' or '//' sequences")

                # Reasonable length limit
                if len(v) > 100:
                    raise ValueError("MCP path too long (maximum 100 characters)")

            elif update_field == "port":
                # Validate port number
                try:
                    port = int(v)
                    if not (1 <= port <= 65535):
                        raise ValueError("Port number must be between 1 and 65535")
                except ValueError as e:
                    if "invalid literal" in str(e):
                        raise ValueError("Port must be a valid number") from e
                    raise

            elif update_field == "app":
                # Validate app:port format
                if ":" not in v:
                    raise ValueError("app field requires format 'app:port' (e.g., 'myapp:8080')")

                parts = v.split(":", 1)
                if len(parts) != 2:
                    raise ValueError("app field requires format 'app:port'")

                app_name, port_str = parts

                # Validate app name
                if not app_name:
                    raise ValueError("App name cannot be empty")

                if not re.match(r"^[a-zA-Z0-9_.-]+$", app_name):
                    raise ValueError(
                        "App name contains invalid characters. "
                        "Only alphanumeric characters, dots, dashes, and underscores are allowed"
                    )

                # Validate port
                try:
                    port = int(port_str)
                    if not (1 <= port <= 65535):
                        raise ValueError("Port number must be between 1 and 65535")
                except ValueError as e:
                    if "invalid literal" in str(e):
                        raise ValueError("Port must be a valid number") from e
                    raise

            elif update_field == "upstream":
                # Validate upstream app name
                if not v:
                    raise ValueError("Upstream app name cannot be empty")

                if not re.match(r"^[a-zA-Z0-9_.-]+$", v):
                    raise ValueError(
                        "Upstream app name contains invalid characters. "
                        "Only alphanumeric characters, dots, dashes, and underscores are allowed"
                    )

        return v


class SwagBackupRequest(BaseModel):
    """Request model for backup management operations."""

    backup_action: Literal["cleanup", "list"] = Field(
        ..., description="Backup action: 'cleanup' or 'list'"
    )

    retention_days: int | None = Field(
        default=None, description="Days to retain backups (only for cleanup action)"
    )


class SwagHealthCheckResult(BaseModel):
    """Result model for health check operations."""

    domain: str = Field(..., description="Domain that was checked")

    url: str = Field(..., description="URL that was checked")

    status_code: int | None = Field(default=None, description="HTTP status code")

    response_time_ms: int | None = Field(default=None, description="Response time in milliseconds")

    response_body: str | None = Field(default=None, description="Response body (truncated)")

    success: bool = Field(..., description="Whether the health check was successful")

    error: str | None = Field(default=None, description="Error message if check failed")
