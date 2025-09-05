"""Configuration management for SWAG MCP server."""

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from ..utils.validators import validate_empty_string
from .constants import (
    DEFAULT_AUTH_METHOD,
    DEFAULT_HOST,
    DEFAULT_LOG_LEVEL,
)


def create_empty_string_validator(default_value: str) -> Any:
    """Create a validator that converts empty strings to a default value.

    Args:
        default_value: The default value to use when the input is empty

    Returns:
        A validator function that can be used with @field_validator

    """

    def validator(cls: type, v: Any) -> str:
        return validate_empty_string(v, default_value)

    return classmethod(validator)


class SwagConfig(BaseSettings):
    """SWAG MCP server configuration."""

    # Core paths
    proxy_confs_path: Path = Field(
        default=Path("/swag/nginx/proxy-confs"),
        description="Path to SWAG proxy configurations directory",
    )

    template_path: Path = Field(
        default=Path("templates"), description="Path to Jinja2 templates directory"
    )

    # Default settings
    default_auth_method: str = Field(
        default="authelia", description="Default authentication method for new configurations"
    )

    default_quic_enabled: bool = Field(
        default=False, description="Default QUIC setting for new configurations"
    )

    # Backup settings
    backup_retention_days: int = Field(
        default=30, description="Number of days to retain backup files"
    )

    # Server settings for MCP transport
    host: str = Field(
        default="127.0.0.1", description="MCP server host for streamable-http transport"
    )

    @property
    def port(self) -> int:
        """Fixed internal port for Docker container."""
        return 8000

    # Logging settings
    log_level: str = Field(default="INFO", description="Logging level")

    log_file_enabled: bool = Field(
        default=True, description="Enable file logging in addition to console"
    )

    log_file_max_bytes: int = Field(
        default=10485760, description="Maximum size of log files before rotation (10MB default)"
    )

    log_directory: Path = Field(
        default=Path("/app/.swag-mcp/logs"), description="Directory for log files"
    )

    # Middleware settings
    rate_limit_enabled: bool = Field(default=False, description="Enable rate limiting middleware")

    rate_limit_rps: float = Field(default=10.0, description="Rate limit: requests per second")

    rate_limit_burst: int = Field(default=20, description="Rate limit: burst capacity")

    log_payloads: bool = Field(
        default=False, description="Include request/response payloads in logs"
    )

    log_payload_max_length: int = Field(
        default=1000, description="Maximum length of logged payloads"
    )

    slow_operation_threshold_ms: int = Field(
        default=1000, description="Threshold for slow operation warnings (milliseconds)"
    )

    enable_structured_logging: bool = Field(
        default=False, description="Enable JSON structured logging"
    )

    enable_retry_middleware: bool = Field(
        default=True, description="Enable automatic retry middleware"
    )

    max_retries: int = Field(
        default=3, description="Maximum number of retries for failed operations"
    )

    # Validators to handle empty string values
    handle_empty_auth_method = field_validator("default_auth_method", mode="before")(
        create_empty_string_validator(DEFAULT_AUTH_METHOD)
    )
    handle_empty_host = field_validator("host", mode="before")(
        create_empty_string_validator(DEFAULT_HOST)
    )
    handle_empty_log_level = field_validator("log_level", mode="before")(
        create_empty_string_validator(DEFAULT_LOG_LEVEL)
    )

    model_config = {
        "env_file": ".env",
        "env_prefix": "SWAG_MCP_",
        "case_sensitive": False,
        "extra": "ignore",  # Ignore extra environment variables
    }


# Global configuration instance
config = SwagConfig()
