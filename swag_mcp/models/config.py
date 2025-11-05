"""Pydantic models for SWAG configuration management."""

import re
import typing
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from swag_mcp.core.constants import (
    AUTH_METHODS,
    LIST_FILTERS,
    VALID_CONFIG_NAME_FORMAT,
    VALID_CONFIG_NAME_PATTERN,
    VALID_CONFIG_ONLY_PATTERN,
    VALID_UPSTREAM_PATTERN,
)
from swag_mcp.models.enums import BackupSubAction, SwagAction
from swag_mcp.utils.validators import validate_domain_format, validate_mcp_path

# Type alias for authentication methods - validated at runtime against AUTH_METHODS
AuthMethodType = str

# Runtime validation removed - AuthMethodType is now a flexible string alias
# AUTH_METHODS from constants.py is the single source of truth

# Type alias for list filter options (synced with LIST_FILTERS in constants.py)
ListFilterType = Literal["all", "active", "samples"]

# Runtime validation to ensure ListFilterType stays in sync with LIST_FILTERS
if set(LIST_FILTERS) != set(typing.get_args(ListFilterType)):
    raise ValueError(
        f"ListFilterType {typing.get_args(ListFilterType)} is out of sync with "
        f"LIST_FILTERS {LIST_FILTERS}. Please update both to match."
    )

# Default list filter value
DEFAULT_LIST_FILTER = "all"

# Compiled regex patterns for efficient validation (source of truth in constants)
_UPSTREAM_PATTERN = re.compile(VALID_UPSTREAM_PATTERN)

# Module-level unicode normalization import (used by all validators)
_ud = unicodedata


def _validate_port_number(port_str: str) -> None:
    """Validate port number string and raise ValueError if invalid."""
    try:
        port = int(port_str)
    except ValueError as err:
        raise ValueError("Port must be a valid number") from err

    if not (1 <= port <= 65535):
        raise ValueError("Port number must be between 1 and 65535")


class SwagBaseRequest(BaseModel):
    """Base request model with common action field."""

    model_config = {"extra": "forbid"}
    action: SwagAction = Field(description="The action to perform")


class SwagListRequest(SwagBaseRequest):
    """Request model for listing SWAG configurations."""

    config_type: str = Field(
        default=DEFAULT_LIST_FILTER,
        description="Filter for configs: 'all' | 'active' | 'samples'",
    )

    @field_validator("config_type", mode="before")
    @classmethod
    def _validate_config_type(cls, v: str) -> str:
        v_norm = _ud.normalize("NFKC", v).strip().lower()
        if v_norm not in LIST_FILTERS:
            valid = ", ".join(sorted(LIST_FILTERS))
            # Normalize field name and value in error message
            raise ValueError(
                f"Invalid config_type '{_ud.normalize('NFKC', v_norm)}'. Valid values: {valid}"
            )
        return v_norm


class SwagConfigRequest(SwagBaseRequest):
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

    # MCP-specific upstream configuration (optional - defaults to main upstream)
    mcp_upstream_app: str | None = Field(
        default=None,
        pattern=VALID_UPSTREAM_PATTERN,
        max_length=100,
        description=(
            "Container name or IP for MCP service "
            "(defaults to upstream_app if not specified)"
        ),
    )

    mcp_upstream_port: int | None = Field(
        default=None,
        ge=1,
        le=65535,
        description="Port for MCP service (defaults to upstream_port if not specified)",
    )

    mcp_upstream_proto: Literal["http", "https"] | None = Field(
        default=None,
        description="Protocol for MCP service (defaults to upstream_proto if not specified)",
    )

    auth_method: AuthMethodType = Field(
        default="authelia", description="Authentication method to use"
    )

    enable_quic: bool = Field(default=False, description="Enable QUIC support")

    @field_validator("server_name", mode="before")
    @classmethod
    def validate_server_name(cls, v: str) -> str:
        """Validate server name format."""
        v = _ud.normalize("NFKC", v).strip().lower()
        return validate_domain_format(v)

    @field_validator("config_name", mode="before")
    @classmethod
    def validate_config_name(cls, v: str) -> str:
        """Validate config name format."""
        v = _ud.normalize("NFKC", v).strip()
        if not v or ".." in v or "/" in v or "\\" in v:
            raise ValueError(
                f"Config name '{_ud.normalize('NFKC', v[:50])}...' contains invalid characters"
            )
        if v.startswith("-") or v.endswith("-"):
            raise ValueError(
                f"Config name '{_ud.normalize('NFKC', v[:50])}...' cannot start or end with '-'"
            )
        return v

    @field_validator("upstream_app", mode="before")
    @classmethod
    def validate_upstream_app(cls, v: str) -> str:
        """Validate upstream app name format."""
        v = _ud.normalize("NFKC", v).strip()
        if not v:
            raise ValueError("Upstream app name cannot be empty")
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError(
                f"Upstream app name '{_ud.normalize('NFKC', v[:50])}...' "
                f"contains invalid characters"
            )
        return v

    @field_validator("mcp_upstream_app", mode="before")
    @classmethod
    def validate_mcp_upstream_app(cls, v: str | None) -> str | None:
        """Validate MCP upstream app name format."""
        if v is None:
            return v
        v = _ud.normalize("NFKC", v).strip()
        if not v:
            raise ValueError("MCP upstream app name cannot be empty")
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError(
                f"MCP upstream app name '{_ud.normalize('NFKC', v[:50])}...' "
                f"contains invalid characters"
            )
        return v

    @field_validator("auth_method")
    @classmethod
    def validate_auth_method(cls, v: str) -> str:
        """Validate auth method against available methods from constants."""
        if v not in AUTH_METHODS:
            valid_methods = ", ".join(sorted(AUTH_METHODS))
            raise ValueError(
                f"Invalid auth_method '{_ud.normalize('NFKC', v)}'. Valid methods: {valid_methods}"
            )
        return v

    @model_validator(mode="after")
    def set_mcp_upstream_defaults(self) -> "SwagConfigRequest":
        """Set MCP upstream defaults to main upstream if not specified.

        This ensures backward compatibility - if MCP fields are not provided,
        they automatically use the same upstream as the main service.

        Note: Defaults are set regardless of mcp_enabled because the templates
        always render these variables. If left as None, Jinja2 would render
        "None" as a string, breaking nginx configuration.
        """
        if self.mcp_upstream_app is None:
            self.mcp_upstream_app = self.upstream_app
        if self.mcp_upstream_port is None:
            self.mcp_upstream_port = self.upstream_port
        if self.mcp_upstream_proto is None:
            self.mcp_upstream_proto = self.upstream_proto
        return self


# Alias for backward/semantic compatibility with tooling/tests
class SwagCreateRequest(SwagConfigRequest):
    """Alias for SwagConfigRequest for backward compatibility."""

    pass


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

    list_filter: ListFilterType = Field(..., description="Type of configurations listed")


class SwagEditRequest(SwagBaseRequest):
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

    # MCP-specific upstream configuration (optional)
    mcp_upstream_app: str | None = Field(
        default=None,
        pattern=VALID_UPSTREAM_PATTERN,
        max_length=100,
        description="Container name or IP for MCP service",
    )

    mcp_upstream_port: int | None = Field(
        default=None,
        ge=1,
        le=65535,
        description="Port for MCP service",
    )

    mcp_upstream_proto: Literal["http", "https"] | None = Field(
        default=None,
        description="Protocol for MCP service",
    )

    auth_method: AuthMethodType | None = Field(
        default=None, description="Authentication method to use"
    )

    enable_quic: bool | None = Field(default=None, description="Enable QUIC support")

    create_backup: bool = Field(
        default=True, description="Whether to create a backup before editing"
    )

    @model_validator(mode="after")
    def _ensure_changes_present(self) -> "SwagEditRequest":
        if self.new_content is None and all(
            getattr(self, f) is None
            for f in (
                "server_name",
                "upstream_app",
                "upstream_port",
                "upstream_proto",
                "mcp_upstream_app",
                "mcp_upstream_port",
                "mcp_upstream_proto",
                "auth_method",
                "enable_quic",
            )
        ):
            raise ValueError(
                "At least one of new_content/server_name/upstream_app/"
                "upstream_port/upstream_proto/mcp_upstream_app/mcp_upstream_port/"
                "mcp_upstream_proto/auth_method/enable_quic must be provided"
            )
        return self

    @field_validator("server_name", mode="before")
    @classmethod
    def validate_edit_server_name(cls, v: str | None) -> str | None:
        """Validate server name format for edit requests."""
        if v is None:
            return v
        v = _ud.normalize("NFKC", v).strip().lower()
        return validate_domain_format(v)

    @field_validator("upstream_app", mode="before")
    @classmethod
    def validate_edit_upstream_app(cls, v: str | None) -> str | None:
        """Validate upstream app name format for edit requests."""
        if v is None:
            return v
        v = _ud.normalize("NFKC", v).strip()
        if not v:
            raise ValueError("Upstream app name cannot be empty")
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Upstream app name contains invalid characters")
        return v

    @field_validator("mcp_upstream_app", mode="before")
    @classmethod
    def validate_edit_mcp_upstream_app(cls, v: str | None) -> str | None:
        """Validate MCP upstream app name format for edit requests."""
        if v is None:
            return v
        v = _ud.normalize("NFKC", v).strip()
        if not v:
            raise ValueError("MCP upstream app name cannot be empty")
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("MCP upstream app name contains invalid characters")
        return v


class SwagRemoveRequest(SwagBaseRequest):
    """Request model for removing SWAG configurations."""

    config_name: str = Field(
        ...,
        pattern=VALID_CONFIG_ONLY_PATTERN,
        description="Name of configuration file to remove (must be .conf, not .sample)",
    )

    create_backup: bool = Field(
        default=True, description="Whether to create a backup before removing"
    )


class SwagLogsRequest(SwagBaseRequest):
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


class SwagHealthCheckRequest(SwagBaseRequest):
    """Request model for health check operations."""

    domain: str = Field(
        ...,
        max_length=253,
        description="Domain to check health for (e.g., docker-mcp.tootie.tv)",
    )

    timeout: int = Field(default=30, ge=1, le=300, description="Request timeout in seconds")

    follow_redirects: bool = Field(default=True, description="Whether to follow HTTP redirects")

    @field_validator("domain", mode="before")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Validate domain format."""
        v = _ud.normalize("NFKC", v).strip().lower()
        return validate_domain_format(v)


class SwagUpdateRequest(SwagBaseRequest):
    """Request model for updating specific SWAG configuration parameters."""

    config_name: str = Field(
        ...,
        pattern=VALID_CONFIG_ONLY_PATTERN,
        max_length=255,
        description="Name of configuration file to update",
    )

    update_field: Literal["port", "upstream", "app", "add_mcp"] = Field(
        ..., description="Field to update: 'port' | 'upstream' | 'app' | 'add_mcp'"
    )

    update_value: str = Field(
        ...,
        min_length=1,
        description="New value for field (port number, app name, app:port, or MCP path)",
    )

    create_backup: bool = Field(
        default=True, description="Whether to create a backup before updating"
    )

    @model_validator(mode="after")
    def validate_update_value_based_on_field(self) -> "SwagUpdateRequest":
        """Validate update_value based on the update_field type."""
        update_field = self.update_field
        update_value = self.update_value.strip()  # Strip whitespace consistently

        # Persist the normalized value
        self.update_value = update_value

        if update_field == "add_mcp":
            # Use centralized MCP path validation and persist normalized value
            try:
                normalized = validate_mcp_path(update_value)
                self.update_value = normalized
            except ValueError:
                raise

        elif update_field == "port":
            # Use improved port validation without brittle exception inspection
            _validate_port_number(update_value)

        elif update_field == "app":
            # Validate app:port format with whitespace stripping and shared validation
            if ":" not in update_value:
                raise ValueError("app field requires format 'app:port' (e.g., 'myapp:8080')")

            parts = update_value.split(":", 1)
            if len(parts) != 2:
                raise ValueError("app field requires format 'app:port'")

            app_name, port_str = parts[0].strip(), parts[1].strip()

            # Validate app name
            if not app_name:
                raise ValueError("App name cannot be empty")

            if not _UPSTREAM_PATTERN.match(app_name):
                raise ValueError(
                    "App name contains invalid characters. "
                    "Only alphanumeric characters, dots, dashes, and underscores are allowed"
                )

            # Reuse port validation
            _validate_port_number(port_str)

        elif update_field == "upstream":
            # Validate upstream app name with whitespace handling and shared pattern
            if not update_value:
                raise ValueError("Upstream app name cannot be empty")

            if not _UPSTREAM_PATTERN.match(update_value):
                raise ValueError(
                    "App name contains invalid characters. "
                    "Only alphanumeric characters, dots, dashes, and underscores are allowed"
                )

        return self


class SwagBackupRequest(SwagBaseRequest):
    """Request model for backup management operations."""

    backup_action: BackupSubAction = Field(..., description="Backup action: 'cleanup' or 'list'")

    retention_days: int | None = Field(
        default=None, description="Days to retain backups (only for cleanup action)"
    )

    @model_validator(mode="after")
    def _validate_cleanup_requires_retention(self) -> "SwagBackupRequest":
        if self.backup_action == BackupSubAction.CLEANUP and (
            self.retention_days is None or self.retention_days < 0
        ):
            raise ValueError("retention_days must be provided and >= 0 for cleanup action")
        return self


class SwagHealthCheckResult(BaseModel):
    """Result model for health check operations."""

    domain: str = Field(..., description="Domain that was checked")

    url: str = Field(..., description="URL that was checked")

    status_code: int | None = Field(default=None, description="HTTP status code")

    response_time_ms: int | None = Field(default=None, description="Response time in milliseconds")

    response_body: str | None = Field(default=None, description="Response body (truncated)")

    success: bool = Field(..., description="Whether the health check was successful")

    error: str | None = Field(default=None, description="Error message if check failed")
