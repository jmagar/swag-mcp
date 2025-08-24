"""Pydantic models for SWAG configuration management."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from ..constants import (
    AUTH_AUTHELIA,
    AUTH_AUTHENTIK,
    AUTH_LDAP,
    AUTH_NONE,
    AUTH_TINYAUTH,
    CONFIG_FILE_PATTERN,
    DEFAULT_LOG_LINES,
    DEFAULT_TIMEOUT,
    MAX_CONFIG_CONTENT_LENGTH,
    MAX_DOMAIN_LENGTH,
    MAX_LOG_LINES,
    MAX_PORT,
    MAX_SERVICE_NAME_LENGTH,
    MAX_UPSTREAM_APP_LENGTH,
    MIN_LOG_LINES,
    MIN_PORT,
    PROTO_HTTP,
    PROTO_HTTPS,
    RESPONSE_BODY_MAX_LENGTH,
    SERVICE_NAME_PATTERN,
    TEMPLATE_MCP_SUBDOMAIN,
    TEMPLATE_MCP_SUBFOLDER,
    TEMPLATE_SUBDOMAIN,
    TEMPLATE_SUBFOLDER,
    UPSTREAM_APP_PATTERN,
)
from ..validators import validate_domain, validate_service_name


class SwagConfigRequest(BaseModel):
    """Request model for creating SWAG configurations."""

    service_name: str = Field(
        ...,
        pattern=SERVICE_NAME_PATTERN,
        max_length=MAX_SERVICE_NAME_LENGTH,
        description="Service identifier used for filename",
    )

    server_name: str = Field(..., max_length=MAX_DOMAIN_LENGTH, description="Domain name for the service")

    upstream_app: str = Field(
        ...,
        pattern=UPSTREAM_APP_PATTERN,
        max_length=MAX_UPSTREAM_APP_LENGTH,
        description="Container name or IP address",
    )

    upstream_port: int = Field(..., ge=MIN_PORT, le=MAX_PORT, description="Port number the service runs on")

    upstream_proto: Literal[PROTO_HTTP, PROTO_HTTPS] = Field(
        default=PROTO_HTTP, description="Protocol for upstream connection"
    )

    config_type: Literal[TEMPLATE_SUBDOMAIN, TEMPLATE_SUBFOLDER, TEMPLATE_MCP_SUBDOMAIN, TEMPLATE_MCP_SUBFOLDER] = Field(
        default=TEMPLATE_SUBDOMAIN, description="Type of configuration to generate"
    )

    auth_method: Literal[AUTH_NONE, AUTH_LDAP, AUTH_AUTHELIA, AUTH_AUTHENTIK, AUTH_TINYAUTH] = Field(
        default=AUTH_NONE, description="Authentication method to use"
    )

    enable_quic: bool = Field(default=False, description="Enable QUIC support")

    @field_validator("server_name")
    @classmethod
    def validate_server_name(cls, v: str) -> str:
        """Validate server name format."""
        return validate_domain(v)

    @field_validator("service_name")
    @classmethod
    def validate_service_name_field(cls, v: str) -> str:
        """Validate service name."""
        return validate_service_name(v)


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
        pattern=CONFIG_FILE_PATTERN,
        description="Name of configuration file to edit",
    )

    new_content: str = Field(
        ..., min_length=1, max_length=MAX_CONFIG_CONTENT_LENGTH, description="New content for the configuration file"
    )

    create_backup: bool = Field(
        default=True, description="Whether to create a backup before editing"
    )


class SwagRemoveRequest(BaseModel):
    """Request model for removing SWAG configurations."""

    config_name: str = Field(
        ...,
        pattern=r"^[a-zA-Z0-9_.-]+\.conf$",
        description="Name of configuration file to remove (must be .conf, not .sample)",
    )

    create_backup: bool = Field(
        default=True, description="Whether to create a backup before removing"
    )


class SwagLogsRequest(BaseModel):
    """Request model for SWAG docker logs."""

    lines: int = Field(default=DEFAULT_LOG_LINES, ge=MIN_LOG_LINES, le=MAX_LOG_LINES, description="Number of log lines to retrieve")

    follow: bool = Field(default=False, description="Follow log output (stream mode)")


class SwagResourceList(BaseModel):
    """Model for SWAG resource listings."""

    configs: list[str] = Field(..., description="List of configuration files")

    total_count: int = Field(..., description="Total number of configurations")


class SwagHealthCheckRequest(BaseModel):
    """Request model for health check operations."""

    domain: str = Field(
        ...,
        max_length=MAX_DOMAIN_LENGTH,
        description="Domain to check health for (e.g., docker-mcp.tootie.tv)",
    )

    timeout: int = Field(default=DEFAULT_TIMEOUT, ge=1, le=300, description="Request timeout in seconds")

    follow_redirects: bool = Field(default=True, description="Whether to follow HTTP redirects")

    @field_validator("domain")
    @classmethod
    def validate_domain_field(cls, v: str) -> str:
        """Validate domain format."""
        return validate_domain(v)


class SwagHealthCheckResult(BaseModel):
    """Result model for health check operations."""

    domain: str = Field(..., description="Domain that was checked")

    url: str = Field(..., description="URL that was checked")

    status_code: int | None = Field(default=None, description="HTTP status code")

    response_time_ms: int | None = Field(default=None, description="Response time in milliseconds")

    response_body: str | None = Field(default=None, max_length=RESPONSE_BODY_MAX_LENGTH, description="Response body (truncated)")

    success: bool = Field(..., description="Whether the health check was successful")

    error: str | None = Field(default=None, description="Error message if check failed")
