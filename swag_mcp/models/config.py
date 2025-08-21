"""Pydantic models for SWAG configuration management."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class SwagConfigRequest(BaseModel):
    """Request model for creating SWAG configurations."""

    service_name: str = Field(
        ...,
        pattern=r"^[a-zA-Z0-9_-]+$",
        max_length=50,
        description="Service identifier used for filename",
    )

    server_name: str = Field(..., max_length=253, description="Domain name for the service")

    upstream_app: str = Field(
        ...,
        pattern=r"^[a-zA-Z0-9_.-]+$",
        max_length=100,
        description="Container name or IP address",
    )

    upstream_port: int = Field(..., ge=1, le=65535, description="Port number the service runs on")

    upstream_proto: Literal["http", "https"] = Field(
        default="http", description="Protocol for upstream connection"
    )

    config_type: Literal["subdomain", "subfolder", "mcp-subdomain", "mcp-subfolder"] = Field(
        default="subdomain", description="Type of configuration to generate"
    )

    auth_method: Literal["none", "ldap", "authelia", "authentik", "tinyauth"] = Field(
        default="none", description="Authentication method to use"
    )

    enable_quic: bool = Field(default=False, description="Enable QUIC support")

    @field_validator("server_name")
    @classmethod
    def validate_server_name(cls, v: str) -> str:
        """Validate server name format."""
        if not v or ".." in v or v.startswith(".") or v.endswith("."):
            raise ValueError("Invalid server name format")

        # Basic domain validation
        domain_pattern = (
            r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
            + r"(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
        )
        if not re.match(domain_pattern, v):
            raise ValueError("Invalid hostname format")

        return v.lower()

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v: str) -> str:
        """Validate service name."""
        if not v or v.startswith("-") or v.endswith("-"):
            raise ValueError("Service name cannot start or end with hyphen")
        return v.lower()


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
        pattern=r"^[a-zA-Z0-9_.-]+\.(conf|sample)$",
        description="Name of configuration file to edit",
    )

    new_content: str = Field(
        ..., min_length=1, description="New content for the configuration file"
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

    lines: int = Field(default=100, ge=1, le=1000, description="Number of log lines to retrieve")

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
        if not v or ".." in v or v.startswith(".") or v.endswith("."):
            raise ValueError("Invalid domain format")

        # Basic domain validation
        domain_pattern = (
            r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
            + r"(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
        )
        import re

        if not re.match(domain_pattern, v):
            raise ValueError("Invalid domain format")

        return v.lower()


class SwagHealthCheckResult(BaseModel):
    """Result model for health check operations."""

    domain: str = Field(..., description="Domain that was checked")

    url: str = Field(..., description="URL that was checked")

    status_code: int | None = Field(default=None, description="HTTP status code")

    response_time_ms: int | None = Field(default=None, description="Response time in milliseconds")

    response_body: str | None = Field(default=None, description="Response body (truncated)")

    success: bool = Field(..., description="Whether the health check was successful")

    error: str | None = Field(default=None, description="Error message if check failed")
