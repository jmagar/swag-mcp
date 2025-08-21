# SWAG MCP Server

A FastMCP server for managing SWAG (Secure Web Application Gateway) reverse proxy configurations.

## Features

- **Create configurations**: Generate new SWAG proxy configs from templates
- **MCP Support**: Specialized templates for Model Context Protocol servers with streamable-HTTP transport
- **Health Check**: Verify reverse proxy configurations are working correctly
- **List configurations**: View active and sample configuration files
- **View configurations**: Read existing configuration content
- **Edit configurations**: Modify configs with automatic backup
- **Default settings**: Configure default auth methods and QUIC settings
- **Security-by-default**: Authelia authentication enabled by default to prevent accidental exposure

## Installation

1. Install dependencies with UV:
```bash
uv install
```

2. Copy environment configuration:
```bash
cp .env.example .env
```

3. Edit `.env` to match your SWAG setup.

## Usage

### Running the Server

#### For Development/Testing:
```bash
# Run with FastMCP CLI for debugging
fastmcp dev swag_mcp/server.py

# Test with FastMCP Inspector
fastmcp dev swag_mcp/server.py --with inspector
```

#### For Direct Module Execution:
```bash
python -m swag_mcp.server
```

#### For HTTP Testing:
```bash
# Run with HTTP transport for testing
fastmcp run swag_mcp/server.py --transport http
```

## Testing

This project includes comprehensive test coverage using pytest and FastMCP's in-memory testing capabilities.

### Running Tests

```bash
# Run all tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=swag_mcp --cov-report=term-missing

# Run specific test files
uv run pytest tests/test_services.py
uv run pytest tests/test_tools.py
uv run pytest tests/test_middleware.py
uv run pytest tests/test_config.py

# Run tests with verbose output
uv run pytest -v

# Run tests and stop on first failure
uv run pytest -x
```

### Test Structure

The test suite is organized as follows:

- **`tests/test_services.py`** - Tests for the core `SwagManagerService`
- **`tests/test_tools.py`** - Tests for all MCP tools using in-memory client
- **`tests/test_middleware.py`** - Tests for middleware components
- **`tests/test_config.py`** - Tests for configuration loading and validation
- **`tests/conftest.py`** - Shared fixtures and test configuration

### Test Requirements

Tests require:
- Valid SWAG proxy configurations directory (set via `SWAG_MCP_PROXY_CONFS_PATH`)
- Write permissions to the proxy configs directory for testing file operations
- The actual Jinja2 templates from the `templates/` directory

### CI/CD Testing

The project includes GitHub Actions workflows for:
- **Test Suite** (`.github/workflows/test.yml`) - Runs tests on Python 3.11 and 3.12
- **Security & Dependencies** (`.github/workflows/dependencies.yml`) - Weekly dependency updates and security scans

The CI pipeline includes:
- Code linting with Ruff
- Type checking with MyPy (non-blocking)
- Test execution with coverage reporting
- Docker build verification
- Integration tests
- Security scanning with Bandit and CodeQL

The server uses streamable-http transport for Claude Desktop integration.

### Available Tools

#### swag_list
List SWAG configuration files.
```python
swag_list(config_type="all")  # "all", "active", or "samples"
```

#### swag_create
Create new SWAG reverse proxy configuration.
```python
swag_create(
    service_name="myapp",
    server_name="myapp.example.com",
    upstream_app="myapp_container",
    upstream_port=8080,
    upstream_proto="http",
    config_type="subdomain",  # Options: "subdomain", "subfolder", "mcp-subdomain", "mcp-subfolder"
    auth_method="none",  # Will default to "authelia" for security
    enable_quic=False
)
```

**Security Note**: Since v2.0, `auth_method="none"` automatically defaults to "authelia" to prevent accidental exposure of services. Explicitly pass `auth_method="none"` twice or use environment variables to disable authentication.

#### swag_view
View configuration file contents.
```python
swag_view(config_name="jellyfin.subdomain.conf")
```

#### swag_edit
Edit existing configuration with backup.
```python
swag_edit(
    config_name="test.subdomain.conf",
    new_content="...",
    create_backup=True
)
```

#### swag_config
Configure default settings.
```python
swag_config(
    default_auth="authelia",
    enable_quic=True
)
```

#### swag_remove
Remove an existing SWAG configuration file.
```python
swag_remove(
    config_name="test.subdomain.conf",
    create_backup=True
)
```

#### swag_logs
Show SWAG docker container logs.
```python
swag_logs(
    lines=100,
    follow=False
)
```

#### swag_cleanup_backups
Clean up old backup files.
```python
swag_cleanup_backups(
    retention_days=30  # Optional, uses config default if not specified
)
```

#### swag_health_check
Verify that a SWAG reverse proxy configuration is working correctly.
```python
swag_health_check(
    domain="myapp.example.com",  # Full domain to test
    timeout=30,  # Request timeout in seconds
    follow_redirects=True  # Follow HTTP redirects
)
```

The health check intelligently tests multiple endpoints:
- First tries `/health` endpoint
- Falls back to `/mcp` for MCP services (accepts 406 as success)
- Finally tries root `/` endpoint
- Returns success if the reverse proxy responds with any HTTP status

Returns formatted results with status icons (✅/❌), response time, and status codes.

## Configuration

Environment variables (prefix: `SWAG_MCP_`):

**Core Paths:**
- `SWAG_PROXY_CONFS_PATH`: Path to SWAG proxy configurations (default: `/mnt/appdata/swag/nginx/proxy-confs`)
- `SWAG_MCP_DATA_PATH`: Path for app data, backups, and logs (default: `/mnt/appdata/swag-mcp`)

**Default Settings:**
- `SWAG_MCP_DEFAULT_AUTH_METHOD`: Default auth method (default: `authelia` - changed from `none` for security)
- `SWAG_MCP_DEFAULT_QUIC_ENABLED`: Default QUIC setting (default: `false`)
- `SWAG_MCP_DEFAULT_CONFIG_TYPE`: Default config type - `subdomain`, `subfolder`, `mcp-subdomain`, or `mcp-subfolder` (default: `subdomain`)

**Server Settings:**
- `SWAG_MCP_BACKUP_RETENTION_DAYS`: Days to retain backup files (default: `30`)
- `SWAG_MCP_HOST`: Server host (default: `0.0.0.0` for Docker)
- `SWAG_MCP_PORT`: Server port (default: `8000`)

**Logging:**
- `SWAG_MCP_LOG_LEVEL`: Logging level (default: `INFO`)
- `SWAG_MCP_LOG_FILE_ENABLED`: Enable file logging (default: `true`)
- `SWAG_MCP_LOG_FILE_MAX_BYTES`: Max log file size before rotation (default: `10485760` = 10MB)

### Middleware Configuration

The server includes optional middleware for enhanced functionality:

**Rate Limiting (Optional)**:
- `SWAG_MCP_RATE_LIMIT_ENABLED`: Enable rate limiting (default: `false`)
- `SWAG_MCP_RATE_LIMIT_RPS`: Requests per second limit (default: `10.0`)
- `SWAG_MCP_RATE_LIMIT_BURST`: Burst capacity for rate limiting (default: `20`)

**Advanced Logging (Optional)**:
- `SWAG_MCP_LOG_PAYLOADS`: Include request/response payloads in logs (default: `false`)
- `SWAG_MCP_LOG_PAYLOAD_MAX_LENGTH`: Max length of logged payloads (default: `1000`)
- `SWAG_MCP_ENABLE_STRUCTURED_LOGGING`: Enable JSON structured logging (default: `false`)

**Performance Monitoring**:
- `SWAG_MCP_SLOW_OPERATION_THRESHOLD_MS`: Threshold for slow operation warnings (default: `1000`)

**Error Handling**:
- `SWAG_MCP_ENABLE_RETRY_MIDDLEWARE`: Enable automatic retries (default: `true`)
- `SWAG_MCP_MAX_RETRIES`: Maximum retry attempts (default: `3`)

## Templates

The server uses Jinja2 templates for generating configurations:

**Standard Templates:**
- `templates/subdomain.conf.j2`: For subdomain-based configurations
- `templates/subfolder.conf.j2`: For subfolder-based configurations

**MCP Templates (Model Context Protocol):**
- `templates/mcp-subdomain.conf.j2`: For MCP servers on subdomains with streamable-HTTP transport
- `templates/mcp-subfolder.conf.j2`: For MCP servers on subfolders with streamable-HTTP transport

The MCP templates include special optimizations for real-time streaming:
- Disabled buffering and caching for Server-Sent Events
- Extended timeouts (24h) for persistent connections
- MCP-specific headers (Mcp-Session-Id)
- Dedicated health check endpoints

## Security Best Practices

### Authentication by Default
Starting with v2.0, the SWAG MCP server defaults to Authelia authentication for all new configurations. This prevents accidental exposure of powerful services like MCP servers to the public internet.

To explicitly disable authentication (not recommended for production):
1. Set `SWAG_MCP_DEFAULT_AUTH_METHOD=none` in your `.env` file
2. Pass `auth_method="none"` explicitly when creating configurations

### MCP Services
Model Context Protocol servers provide powerful AI capabilities and should always be protected with authentication. The MCP templates include:
- Authelia integration by default
- Separate health endpoints that bypass auth for monitoring
- Long timeout settings appropriate for AI workloads

## Claude Desktop Integration

Add to your Claude Desktop MCP configuration:

```json
{
  "mcpServers": {
    "swag-mcp": {
      "command": "python",
      "args": ["-m", "swag_mcp.server"],
      "cwd": "/path/to/your/swag-mcp",
      "env": {
        "SWAG_PROXY_CONFS_PATH": "/path/to/swag/nginx/proxy-confs",
        "SWAG_MCP_DATA_PATH": "/path/to/swag-mcp/data"
      }
    }
  }
}
```

Or install directly with FastMCP CLI:
```bash
# Install for Claude Desktop (update paths as needed)
fastmcp install claude-desktop /path/to/swag-mcp/swag_mcp/server.py

# Generate MCP JSON config
fastmcp install mcp-json /path/to/swag-mcp/swag_mcp/server.py > swag-mcp-config.json
```

## Development

### Testing

Test files are not currently implemented. To add tests:

```bash
# Install development dependencies
uv sync --dev

# Run tests (when implemented)
uv run pytest
```

The project structure:
```
swag-mcp/
├── swag_mcp/                    # Main package
│   ├── server.py                # Main server entry point
│   ├── __main__.py              # Module entry point
│   ├── core/
│   │   └── config.py            # Configuration management
│   ├── models/
│   │   └── config.py            # Pydantic data models
│   ├── services/
│   │   └── swag_manager.py      # Core business logic
│   ├── tools/
│   │   └── swag.py              # FastMCP tools
│   └── middleware/              # Middleware components
│       ├── __init__.py          # Middleware setup
│       ├── error_handling.py    # Error handling & retry
│       ├── request_logging.py   # Logging middleware
│       ├── rate_limiting.py     # Rate limiting
│       └── timing.py            # Performance timing
├── templates/                   # Jinja2 templates
│   ├── subdomain.conf.j2       # Standard subdomain proxy
│   ├── subfolder.conf.j2       # Standard subfolder proxy
│   ├── mcp-subdomain.conf.j2   # MCP subdomain with streaming
│   └── mcp-subfolder.conf.j2   # MCP subfolder with streaming
├── docker-compose.yaml          # Docker setup
├── Dockerfile                   # Docker image configuration
└── pyproject.toml              # Project configuration
```

## Docker Deployment

The project includes Docker support for containerized deployment.

### Available Commands

```bash
# Build the Docker image
docker compose build

# Run the service
docker compose up -d

# View logs
docker compose logs -f swag-mcp

# Restart the service
docker compose restart swag-mcp

# Stop all services
docker compose down

# Clean up (remove containers and volumes)
docker compose down -v

# Health check
curl -f http://localhost:8000/health

# Access container shell
docker compose exec swag-mcp /bin/bash
```

### Configuration

- `docker-compose.yaml`: Main Docker Compose configuration
- `Dockerfile`: Multi-stage build configuration
- Environment variables can be customized via `.env` file

The Docker setup includes health checks available at `http://localhost:8000/health` internally, or externally at `http://localhost:${SWAG_MCP_PORT}/health` (port configured via .env file).

### File Logging

The server supports dual logging output:

- **Console logs**: All application output for Docker logs and development
- **File logs**: Separate rotating log files in the data directory:
  - `swag-mcp.log`: Main application logs
  - `swag-middleware.log`: Middleware-specific logs (timing, rate limiting, etc.)

Log files are stored in `${SWAG_MCP_DATA_PATH}/logs/` and rotate when they reach the configured size limit (default 10MB), clearing old content instead of keeping backup files.
