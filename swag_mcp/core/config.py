"""Configuration management for SWAG MCP server."""

from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from ..constants import (
    DEFAULT_AUTH_METHOD,
    DEFAULT_BACKUP_RETENTION_DAYS,
    DEFAULT_CONFIG_TYPE,
    DEFAULT_HOST,
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOG_MAX_BYTES,
    DEFAULT_LOG_LINES,
    DEFAULT_MAX_RETRIES,
    DEFAULT_PAYLOAD_MAX_LENGTH,
    DEFAULT_PORT,
    DEFAULT_QUIC_ENABLED,
    DEFAULT_RATE_LIMIT_BURST,
    DEFAULT_RATE_LIMIT_RPS,
    ENV_PREFIX,
    SLOW_OPERATION_THRESHOLD_MS,
)
from ..validators import create_empty_string_validator


class SwagConfig(BaseSettings):
    """SWAG MCP server configuration."""

    # Core paths
    proxy_confs_path: Path = Field(
        default=Path("/proxy-confs"),
        description="Path to SWAG proxy configurations directory",
    )

    template_path: Path = Field(
        default=Path("templates"), description="Path to Jinja2 templates directory"
    )

    # Default settings
    default_auth_method: str = Field(
        default=DEFAULT_AUTH_METHOD, description="Default authentication method for new configurations"
    )

    default_quic_enabled: bool = Field(
        default=DEFAULT_QUIC_ENABLED, description="Default QUIC setting for new configurations"
    )

    default_config_type: str = Field(
        default=DEFAULT_CONFIG_TYPE, description="Default configuration type (subdomain or subfolder)"
    )

    # Backup settings
    backup_retention_days: int = Field(
        default=DEFAULT_BACKUP_RETENTION_DAYS, description="Number of days to retain backup files"
    )

    # Server settings for MCP transport
    host: str = Field(
        default=DEFAULT_HOST, description="MCP server host for streamable-http transport"
    )

    @property
    def port(self) -> int:
        """Fixed internal port for Docker container."""
        return DEFAULT_PORT

    # Logging settings
    log_level: str = Field(default=DEFAULT_LOG_LEVEL, description="Logging level")

    log_file_enabled: bool = Field(
        default=True, description="Enable file logging in addition to console"
    )

    log_file_max_bytes: int = Field(
        default=DEFAULT_LOG_MAX_BYTES, description="Maximum size of log files before rotation (10MB default)"
    )

    log_directory: Path = Field(
        default=Path("/app/.swag-mcp/logs"), description="Directory for log files"
    )

    # Middleware settings
    rate_limit_enabled: bool = Field(default=False, description="Enable rate limiting middleware")

    rate_limit_rps: float = Field(default=DEFAULT_RATE_LIMIT_RPS, description="Rate limit: requests per second")

    rate_limit_burst: int = Field(default=DEFAULT_RATE_LIMIT_BURST, description="Rate limit: burst capacity")

    log_payloads: bool = Field(
        default=False, description="Include request/response payloads in logs"
    )

    log_payload_max_length: int = Field(
        default=DEFAULT_PAYLOAD_MAX_LENGTH, description="Maximum length of logged payloads"
    )

    slow_operation_threshold_ms: int = Field(
        default=SLOW_OPERATION_THRESHOLD_MS, description="Threshold for slow operation warnings (milliseconds)"
    )

    enable_structured_logging: bool = Field(
        default=False, description="Enable JSON structured logging"
    )

    enable_retry_middleware: bool = Field(
        default=True, description="Enable automatic retry middleware"
    )

    max_retries: int = Field(
        default=DEFAULT_MAX_RETRIES, description="Maximum number of retries for failed operations"
    )

    # Consolidated validators using factory function
    _validate_auth_method = field_validator("default_auth_method", mode="before")(
        create_empty_string_validator("auth_method", DEFAULT_AUTH_METHOD)
    )
    
    _validate_config_type = field_validator("default_config_type", mode="before")(
        create_empty_string_validator("config_type", DEFAULT_CONFIG_TYPE)
    )
    
    _validate_host = field_validator("host", mode="before")(
        create_empty_string_validator("host", DEFAULT_HOST)
    )
    
    _validate_log_level = field_validator("log_level", mode="before")(
        create_empty_string_validator("log_level", DEFAULT_LOG_LEVEL)
    )

    model_config = {
        "env_file": ".env",
        "env_prefix": ENV_PREFIX,
        "case_sensitive": False,
        "extra": "ignore",  # Ignore extra environment variables
    }


# Global configuration instance
config = SwagConfig()
