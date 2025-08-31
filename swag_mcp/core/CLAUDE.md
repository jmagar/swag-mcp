# SWAG MCP Core Configuration - Claude Memory Reference

This directory contains core configuration management, application constants, and logging setup for the SWAG MCP server.

## Directory Purpose

The `core/` module provides centralized configuration management using Pydantic Settings, application-wide constants, and structured logging configuration. All environment variables use the `SWAG_MCP_*` prefix for consistency.

## Key Files

### `config.py` - SwagConfig with Pydantic Settings
Central configuration class that loads and validates all environment variables:

```python
class SwagConfig(BaseSettings):
    # Core Settings (Required)
    proxy_confs_path: Path = Field(...)
    log_directory: Path = Field(...)

    # Server Settings
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)

    # Default Configuration
    default_auth_method: str = Field(default="authelia")
    default_config_type: str = Field(default="subdomain")
    default_quic_enabled: bool = Field(default=False)

    # Performance & Logging
    log_level: str = Field(default="INFO")
    slow_operation_threshold_ms: int = Field(default=1000)

    class Config:
        env_prefix = "SWAG_MCP_"
        case_sensitive = False
```

**Key Features:**
- Automatic environment variable loading with `SWAG_MCP_*` prefix
- Path validation and normalization
- Type conversion and validation via Pydantic
- Default values with constraints (port ranges, log levels)

### `constants.py` - Application Constants
Defines validation patterns, configuration options, and default values:

```python
# Configuration Types
CONFIG_TYPES = ["subdomain", "subfolder", "mcp-subdomain", "mcp-subfolder"]

# Authentication Methods
AUTH_METHODS = ["none", "ldap", "authelia", "authentik", "tinyauth"]

# Validation Patterns
DOMAIN_PATTERN = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
SERVICE_NAME_PATTERN = r"^[a-zA-Z0-9_-]+$"

# File Extensions
NGINX_CONF_EXTENSION = ".conf"
SAMPLE_EXTENSION = ".sample"
BACKUP_EXTENSION = ".backup"

# Default Values
DEFAULT_TEMPLATE_PATH = "templates"
DEFAULT_BACKUP_RETENTION_DAYS = 30
DEFAULT_HEALTH_CHECK_TIMEOUT = 30
```

**Usage Patterns:**
- Import for validation: `from swag_mcp.core.constants import DOMAIN_PATTERN`
- Configuration validation: Check against `CONFIG_TYPES` and `AUTH_METHODS`
- File naming: Use `NGINX_CONF_EXTENSION` for consistent file handling

### `logging_config.py` - Structured Logging Setup
Configures dual logging (console + file) with optional structured JSON output:

```python
def setup_logging(config: SwagConfig) -> None:
    """Setup comprehensive logging with console and file output"""

    # Create log directory
    config.log_directory.mkdir(parents=True, exist_ok=True)

    # Configure handlers
    console_handler = logging.StreamHandler()
    file_handler = RotatingFileHandler(
        config.log_directory / "swag-mcp.log",
        maxBytes=config.log_file_max_bytes,
        backupCount=5
    )

    # Optional structured logging
    if config.enable_structured_logging:
        formatter = StructuredFormatter()
    else:
        formatter = StandardFormatter()
```

**Features:**
- Rotating file handler with size limits
- Structured JSON logging for log aggregation
- Console output with color support
- Performance timing integration
- Request/response payload logging (configurable)

## Environment Variables Reference

### Core Settings (Required)
```bash
# Path to SWAG proxy configurations directory
SWAG_MCP_PROXY_CONFS_PATH=/swag/nginx/proxy-confs

# Directory for MCP server logs
SWAG_MCP_LOG_DIRECTORY=/app/.swag-mcp/logs
```

### Server Settings
```bash
# Host interface for server binding
SWAG_MCP_HOST=0.0.0.0

# External port (internal always 8000)
SWAG_MCP_PORT=8000
```

### Default Configuration
```bash
# Default authentication method for new configs
SWAG_MCP_DEFAULT_AUTH_METHOD=authelia

# Default configuration type
SWAG_MCP_DEFAULT_CONFIG_TYPE=subdomain

# Enable QUIC support by default
SWAG_MCP_DEFAULT_QUIC_ENABLED=false
```

### Backup Settings
```bash
# Days to retain backup files
SWAG_MCP_BACKUP_RETENTION_DAYS=30
```

### Logging Configuration
```bash
# Logging verbosity level
SWAG_MCP_LOG_LEVEL=INFO

# Enable file logging
SWAG_MCP_LOG_FILE_ENABLED=true

# Max log file size before rotation
SWAG_MCP_LOG_FILE_MAX_BYTES=10485760

# Structured JSON logging
SWAG_MCP_ENABLE_STRUCTURED_LOGGING=false

# Log request/response payloads
SWAG_MCP_LOG_PAYLOADS=false

# Max payload length in logs
SWAG_MCP_LOG_PAYLOAD_MAX_LENGTH=1000
```

### Performance Settings
```bash
# Slow operation warning threshold
SWAG_MCP_SLOW_OPERATION_THRESHOLD_MS=1000

# Enable retry middleware
SWAG_MCP_ENABLE_RETRY_MIDDLEWARE=true

# Max retries for failed operations
SWAG_MCP_MAX_RETRIES=3
```

### Rate Limiting
```bash
# Enable rate limiting
SWAG_MCP_RATE_LIMIT_ENABLED=false

# Requests per second limit
SWAG_MCP_RATE_LIMIT_RPS=10.0

# Burst capacity
SWAG_MCP_RATE_LIMIT_BURST=20
```

## Configuration Patterns

### Loading Configuration
```python
# In services and tools
from swag_mcp.core.config import SwagConfig

config = SwagConfig()  # Automatically loads from environment
service = SwagManagerService(config)
```

### Validation Integration
```python
# Using constants for validation
from swag_mcp.core.constants import CONFIG_TYPES, AUTH_METHODS

def validate_config_type(config_type: str) -> bool:
    return config_type in CONFIG_TYPES

def validate_auth_method(auth_method: str) -> bool:
    return auth_method in AUTH_METHODS
```

### Logging Setup
```python
# In server.py or __main__.py
from swag_mcp.core.logging_config import setup_logging
from swag_mcp.core.config import SwagConfig

config = SwagConfig()
setup_logging(config)  # Must call before any logging
```

## Common Development Tasks

### Adding New Environment Variable
1. Add field to `SwagConfig` class with type annotation and validation
2. Add default value in `constants.py` if applicable
3. Update `.env.example` in project root
4. Add validation tests if needed

Example:
```python
# In config.py
class SwagConfig(BaseSettings):
    # New setting with validation
    new_feature_enabled: bool = Field(default=False)
    new_timeout: int = Field(default=30, ge=1, le=300)
```

### Updating Validation Patterns
1. Modify pattern in `constants.py`
2. Update corresponding validator in `utils/validators.py`
3. Add test cases for new pattern
4. Update documentation if user-facing

### Logging Configuration Changes
1. Modify `setup_logging()` function
2. Add new environment variables to `SwagConfig` if needed
3. Test logging output format changes
4. Update structured logging schema if using JSON

## Development Commands

### Configuration Testing
```bash
# Test configuration loading
python -c "from swag_mcp.core.config import SwagConfig; print(SwagConfig())"

# Validate environment variables
uv run pytest tests/ -k "config" -v

# Test with custom env file
SWAG_MCP_LOG_LEVEL=DEBUG python -m swag_mcp
```

### Logging Testing
```bash
# Test logging output
SWAG_MCP_LOG_PAYLOADS=true fastmcp dev swag_mcp/server.py

# Test structured logging
SWAG_MCP_ENABLE_STRUCTURED_LOGGING=true python -m swag_mcp

# Test log rotation
truncate -s 20M /path/to/logs/swag-mcp.log  # Force rotation
```

## Important Notes

### Configuration Loading Order
1. Environment variables (highest priority)
2. `.env` file values
3. Default values from `SwagConfig` fields
4. Constants from `constants.py` (lowest priority)

### Path Handling
- All paths in configuration are resolved to absolute paths
- Parent directories are created automatically if needed
- Path validation ensures readability/writability

### Type Safety
- All configuration uses Pydantic for automatic type conversion
- Invalid values raise validation errors at startup
- Port numbers, timeouts have range constraints

### Security Considerations
- No sensitive defaults (auth method defaults to secure option)
- Paths are validated to prevent directory traversal
- File permissions checked before operations
- Log payload redaction for sensitive data

### Performance Impact
- Configuration loaded once at startup and cached
- No runtime configuration reloading (requires restart)
- Logging configuration affects performance (especially payload logging)
- Structured logging has overhead but enables better monitoring
