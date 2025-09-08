# 🛡️ SWAG MCP Server

> **Intelligent reverse proxy management for SWAG (Secure Web Application Gateway) with Model Context Protocol support**

[![Test Suite](https://github.com/jmagar/swag-mcp/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/jmagar/swag-mcp/actions/workflows/test.yml)
[![Build and Push Docker Image](https://github.com/jmagar/swag-mcp/actions/workflows/docker-publish.yml/badge.svg?branch=main)](https://github.com/jmagar/swag-mcp/actions/workflows/docker-publish.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastMCP](https://img.shields.io/badge/FastMCP-latest-green.svg)](https://github.com/fastmcp/fastmcp)
[![Docker](https://img.shields.io/badge/Docker-ghcr.io-blue.svg)](https://github.com/jmagar/swag-mcp/pkgs/container/swag-mcp)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

Transform your SWAG reverse proxy management with AI-powered automation and real-time health monitoring. The unified `swag` tool provides comprehensive functionality for managing SWAG proxy configs for your self-hosted services and MCP servers.

> **What is MCP?** Model Context Protocol enables LLMs like Claude to interact with external tools and services. This server implements MCP to allow AI assistants to manage your SWAG configurations through natural language.

---

## ✨ Key Features

### 🚀 **Core Capabilities**
- **Smart Configuration Generation** - Create SWAG proxy configs from intelligent templates, including remote MCP servers
- **Real-time Health Monitoring** - Verify your services are accessible and running
- **Automatic Backups** - Never lose a configuration with automatic backup on edit
- **MCP Protocol Support** - Generates Streamable-HTTP SWAG proxy configs

### 🔐 **Security First**
- **Authelia by Default** - All services protected automatically
- **Secure Templates** - Pre-configured security headers and best practices
- **Audit Logging** - Complete activity tracking and monitoring

### 🤖 **MCP Ready**
- **Claude Desktop Integration** - Works seamlessly with Claude AI, Claude Code, Cursor, Windsurf, Cline, Roo Code, KiloCode, Goose, etc.
- **Streaming Support** - Server-Sent Events for real-time AI responses
- **Extended Timeouts** - Optimized for remote MCP servers.

---

## 📋 Prerequisites

Before installing SWAG MCP, ensure you have:

- **Docker & Docker Compose** - Latest versions recommended (Docker Compose v2)
- **SWAG Container** - LinuxServer SWAG container already running
- **File System Access** - Read/write access to SWAG configuration directory
- **Available Port** - Port 8000 free (or specify custom port in configuration)
- **Network Access** - Ability to reach your SWAG services for health checks

---

## 🚀 Quick Install (One Line!)

```bash
curl -sSL https://raw.githubusercontent.com/jmagar/swag-mcp/main/install.sh | bash
```

This intelligent installer will:
- ✅ **Auto-discover** your SWAG proxy-confs location
- ✅ **Find an available port** automatically
- ✅ **Download and configure** automagically
- ✅ **Start the service** immediately

## 📦 Compatibility

| Component | Version | Notes |
|-----------|---------|-------|
| **SWAG** | Latest linuxserver/swag | Required base container |
| **Python** | 3.11+ | Runtime environment |
| **FastMCP** | 2.11.3+ | MCP framework |
| **Docker Compose** | v2 | Recommended over v1 |
| **Architecture** | x86_64, ARM64 | Multi-platform support |

---

## 🎯 Installation Options

### Option 1: Docker Compose (Recommended)

The one-line installer above is the fastest way. For manual Docker installation:

> **Production Tip**: The docker-compose.yaml defaults to building locally. For production, uncomment the pre-built image line and comment out the build section to use `ghcr.io/jmagar/swag-mcp:latest`

```bash
# Download files manually
curl -O https://raw.githubusercontent.com/jmagar/swag-mcp/main/docker-compose.yaml
curl -O https://raw.githubusercontent.com/jmagar/swag-mcp/main/.env.example
cp .env.example .env

# Edit .env with your paths (key variables to configure)
nano .env
# Set: SWAG_MCP_PROXY_CONFS_PATH, SWAG_MCP_LOG_DIRECTORY, SWAG_MCP_PORT

# Deploy
docker compose up -d
```

### Option 2: Development Installation

For development or customization:

```bash
# Clone the repository
git clone https://github.com/jmagar/swag-mcp.git
cd swag-mcp

# Install dependencies with UV
uv sync

# Configure
cp .env.example .env
nano .env

# Run in development mode
fastmcp dev swag_mcp/server.py
```

---

## 🔧 Configuration

### Essential Settings

Create a `.env` file with your configuration:

```bash
# Core Paths (Required)
SWAG_MCP_PROXY_CONFS_PATH=/swag/nginx/proxy-confs
SWAG_MCP_LOG_DIRECTORY=/app/.swag-mcp/logs

# Security (Defaults shown)
SWAG_MCP_DEFAULT_AUTH_METHOD=authelia    # Never expose services without auth!

# Server Settings
SWAG_MCP_HOST=0.0.0.0  # For Docker/external access
# Note: Container uses port 8000 internally (default), host port mapping configurable via SWAG_MCP_PORT
```

<details>
<summary>📊 Advanced Configuration Options</summary>

```bash
# Logging Configuration
SWAG_MCP_LOG_LEVEL=INFO                        # DEBUG, INFO, WARNING, ERROR, CRITICAL
SWAG_MCP_LOG_FILE_ENABLED=true                 # Enable file logging
SWAG_MCP_LOG_FILE_MAX_BYTES=10485760          # Max log file size (10MB)
SWAG_MCP_ENABLE_STRUCTURED_LOGGING=false      # JSON structured logging
SWAG_MCP_LOG_PAYLOADS=false                   # Log request/response payloads
SWAG_MCP_LOG_PAYLOAD_MAX_LENGTH=1000          # Max payload log length

# Performance & Reliability
SWAG_MCP_SLOW_OPERATION_THRESHOLD_MS=1000     # Slow operation warning threshold
SWAG_MCP_ENABLE_RETRY_MIDDLEWARE=true         # Enable automatic retries
SWAG_MCP_MAX_RETRIES=3                        # Maximum retry attempts

# Rate Limiting (Protection)
SWAG_MCP_RATE_LIMIT_ENABLED=false             # Enable rate limiting
SWAG_MCP_RATE_LIMIT_RPS=10.0                  # Requests per second
SWAG_MCP_RATE_LIMIT_BURST=20                  # Burst capacity

# Backup Management
SWAG_MCP_BACKUP_RETENTION_DAYS=30             # Days to keep backups

# Default Configuration Behavior
SWAG_MCP_DEFAULT_QUIC_ENABLED=false           # Default QUIC setting
```

</details>

---

## 📚 Usage Guide

SWAG MCP is controlled through natural language commands. Simply tell Claude (or any MCP-compatible AI) what you want to do:

### Creating a Basic Service

**Natural Language:**
- *"Create a SWAG reverse proxy for Jellyfin at jellyfin.example.com running on port 8096"*
- *"Set up proxy for jellyfin using jellyfin.example.com on port 8096"*

**Shorthand:**
```
swag create jellyfin jellyfin.example.com jellyfin 8096
```

### Creating a Streamable-HTTP MCP service

**Natural Language:**
- *"Create a streaming MCP proxy for claude-mcp at ai.example.com on port 8080"*
- *"Set up MCP subdomain proxy for claude-mcp-server at ai.example.com:8080 with streaming support"*

**Shorthand:**
```
swag create claude-mcp ai.example.com claude-mcp-server 8080 mcp-subdomain
```

### Health Check Verification

**Natural Language:**
- *"Check if jellyfin.example.com is accessible"*
- *"Test the health of jellyfin.example.com"*
- *"Is jellyfin.example.com working?"*

**Shorthand:**
```
swag health check jellyfin.example.com
```

---

## 🏃 Quick Start

Once installed, try these common commands with your AI assistant:

### Most Common Tasks

**Add a new service:**
- *"Create a reverse proxy for Plex at plex.mydomain.com on port 32400"*
- *"Add Sonarr proxy using sonarr.mydomain.com port 8989"*

**Check what's configured:**
- *"List all my proxy configurations"*
- *"Show me only the active proxies"*
- *"What SWAG configs do I have?"*

**Health monitoring:**
- *"Is plex.mydomain.com working?"*
- *"Check if all my services are accessible"*

**Make changes:**
- *"Update plex config to use port 32401"*
- *"Change sonarr upstream to new-sonarr container"*
- *"Add an MCP endpoint to jellyfin.subdomain.conf"*
- *"Remove the old test.subdomain.conf"*

**View logs and troubleshoot:**
- *"Show me the last 50 nginx error log lines"*
- *"Get fail2ban logs"*
- *"What's in the SWAG access logs?"*

---

## 🛠️ Available Tool

The SWAG MCP server provides a single, powerful **`swag`** tool that performs different actions. You interact with it through natural language - just tell your AI assistant what you want to do!

### How to Use the Tool

Simply describe what you want in natural language:
- *"Create a reverse proxy for [service] at [domain] on port [port]"*
- *"Check if [domain] is working"*
- *"List all proxy configurations"*
- *"Update [config] to use port [port]"*
- *"Add an MCP endpoint to [config]"*
The AI assistant will translate your request into the appropriate tool parameters.

### Available Actions

| Action | Description | Key Parameters |
|--------|-------------|----------------|
| **`list`** | List all configurations | `list_filter` (all/active/samples) |
| **`create`** | Generate new proxy configuration | `service_name`, `server_name`, `upstream_app`, `upstream_port` |
| **`view`** | Read configuration content | `config_name` |
| **`edit`** | Modify configuration safely | `config_name`, `new_content`, `create_backup` |
| **`update`** | Update specific config fields | `config_name`, `update_field` (port\|upstream\|app\|add_mcp), `update_value` |
| **`remove`** | Delete configuration | `config_name`, `create_backup` |
| **`health_check`** | Verify service accessibility | `domain`, `timeout`, `follow_redirects` |
| **`logs`** | View SWAG container logs | `log_type`, `lines` |
| **`backups`** | Manage backup files | `retention_days` |

<details>
<summary>📖 Detailed Action Documentation</summary>

#### `create` Action
Creates a new reverse proxy configuration with automatic health check verification.

**Natural Language Examples:**
- *"Create a reverse proxy for myapp at app.example.com running on myapp:8080"*
- *"Set up subdomain proxy for myapp at app.example.com with authelia authentication"*
- *"Add HTTPS proxy for secure-app at secure.example.com on port 8443"*
- *"Create MCP streaming proxy for ai-service at ai.example.com:8080"*

**Key Options:**

- **Config Type**: Automatically inferred from filename (service.subdomain.conf or service.subfolder.conf)
- **MCP Support**: Add `mcp_enabled=true` for streaming/SSE features
- **Authentication**: none, basic, ldap, authelia, authentik, tinyauth (default: authelia)
- **Protocols**: http, https (default: http)
- **QUIC Support**: Available for enhanced performance

#### `health_check` Action
Intelligently tests service availability through multiple endpoints.

**Smart Endpoint Detection:**
1. Tries `/health` endpoint first
2. Falls back to `/mcp` for AI services
3. Finally tests root `/` endpoint
4. Returns success for any valid HTTP response

**Natural Language Examples:**
- *"Check if app.example.com is accessible"*
- *"Test app.example.com with 30 second timeout"*
- *"Is my service at secure.example.com working?"*

#### `update` Action
Update specific fields in existing configurations without full rewrites.

**Supported update fields:**

- **`port`** — Update the upstream port (e.g., "8080")
- **`upstream`** — Update the upstream app name or IP address (e.g., "myapp")
- **`app`** — Update both app name and port (e.g., "myapp:8080")
- **`add_mcp`** — Add an MCP streaming-endpoint path (e.g., "/mcp")

**Natural Language Examples:**
- *"Update port for app.subdomain.conf to 8081"*
- *"Change upstream app for app.subdomain.conf to newapp"*
- *"Update app.subdomain.conf to use newapp:8081"*
- *"Modify plex config to use port 32401"*
- *"Add an MCP endpoint to jellyfin.subdomain.conf"*
- *"Add an MCP location at /ai-service to plex.subdomain.conf"*

#### `list` Action
List and filter configuration files.

**Natural Language Examples:**
- *"List all SWAG configurations"*
- *"Show only active proxy configurations"*
- *"What sample configuration files are available?"*
- *"Display all my proxy configs"*

#### `logs` Action
View SWAG container logs for debugging.

**Natural Language Examples:**
- *"Show last 100 lines of nginx error logs"*
- *"Get fail2ban logs"*
- *"Display nginx access log entries"*
- *"Show me the Let's Encrypt renewal logs"*

</details>

---

## 🏗️ Template System

The template system automatically selects the appropriate template based on the configuration filename format and the `mcp_enabled` parameter:

### Standard Templates

Perfect for traditional web applications:

- **`subdomain`** - `service.subdomain.conf` → `app.example.com` → `container:port`
- **`subfolder`** - `service.subfolder.conf` → `example.com/app` → `container:port`

### MCP Templates

Optimized for remote MCP services with streaming (enabled with `mcp_enabled=true`):

- **`mcp-subdomain`** - `service.subdomain.conf` + MCP features → Streamable-HTTP/SSE support
- **`mcp-subfolder`** - `service.subfolder.conf` + MCP features → path-based with SSE support

#### Template Selection

- Base type inferred from filename: `.subdomain.conf` or `.subfolder.conf`
- MCP features added when `mcp_enabled=true` parameter is used
- No need to specify template type separately — it's determined automatically

#### MCP Template Features

- 🚀 Zero-buffering for real-time streaming
- ⏱️ 24-hour timeouts for long AI tasks
- 🔄 Server-Sent Events (SSE) support
- 📡 WebSocket upgrade capability
- 🛡️ Authelia integration by default

---

## 🤝 Claude Desktop Integration

### Quick Setup

Add to your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "swag-mcp": {
      "command": "python",
      "args": ["-m", "swag_mcp.server"],
      "cwd": "/path/to/swag-mcp",
      "env": {
        "SWAG_MCP_PROXY_CONFS_PATH": "/your/swag/nginx/proxy-confs",
        "SWAG_MCP_LOG_DIRECTORY": "/your/swag-mcp/logs",
        "SWAG_MCP_DEFAULT_AUTH_METHOD": "authelia"
      }
    }
  }
}
```

### Or Use FastMCP CLI

```bash
# Auto-install for Claude Desktop
fastmcp install claude-desktop /path/to/swag-mcp/swag_mcp/server.py

# Generate config manually
fastmcp install mcp-json /path/to/swag-mcp/swag_mcp/server.py
```

---

## 🧪 Testing

### Running Tests

```bash
# Full test suite
uv run pytest

# With coverage report
uv run pytest --cov=swag_mcp --cov-report=term-missing

# Specific test categories
uv run pytest tests/test_swag_actions.py  # Action-specific tests
uv run pytest tests/test_validation.py    # Input validation tests
uv run pytest tests/test_error_handling.py# Error handling tests
uv run pytest tests/test_integration.py   # Integration tests
uv run pytest tests/test_performance.py   # Performance tests
uv run pytest tests/test_mocking.py       # Mock tests
```


---

## 📂 Project Structure

```
swag-mcp/
├── 📦 swag_mcp/              # Core application
│   ├── 🚀 server.py          # Entry point
│   ├── ⚙️ core/              # Configuration & constants
│   │   ├── config.py         # Main configuration class
│   │   ├── constants.py      # Application constants
│   │   └── logging_config.py # Logging setup
│   ├── 📊 models/            # Data models
│   │   ├── config.py         # Pydantic request/response models
│   │   └── enums.py          # Action enums
│   ├── 🔧 services/          # Business logic
│   │   └── swag_manager.py   # Core SWAG operations
│   ├── 🛠️ tools/             # MCP tools
│   │   └── swag.py           # Unified SWAG tool
│   ├── 🔌 middleware/        # Request processing
│   │   ├── error_handling.py # Error handling middleware
│   │   ├── rate_limiting.py  # Rate limiting
│   │   ├── request_logging.py# Request/response logging
│   │   └── timing.py         # Performance timing
│   └── 🔨 utils/             # Utility modules
│       ├── error_handlers.py # Error handling utilities
│       ├── error_messages.py # Error message constants
│       ├── formatters.py     # Output formatting
│       ├── tool_decorators.py# Tool decorators
│       ├── tool_helpers.py   # Tool helper functions
│       └── validators.py     # Input validation
├── 📝 templates/             # Jinja2 templates
│   ├── subdomain.conf.j2     # Standard subdomain proxy
│   ├── subfolder.conf.j2     # Path-based routing
│   ├── mcp-subdomain.conf.j2 # AI service with SSE support
│   └── mcp-subfolder.conf.j2 # AI service on path with SSE
├── 📚 docs/                  # Documentation
│   └── swag-test-commands.md # Comprehensive test commands (600+ examples)
├── 🧪 tests/                 # Test suite
│   ├── fixtures/             # Test fixtures
│   ├── test_error_handling.py# Error handling tests
│   ├── test_integration.py   # Integration tests
│   ├── test_mocking.py       # Mock tests
│   ├── test_performance.py   # Performance tests
│   ├── test_swag_actions.py  # Action-specific tests
│   └── test_validation.py    # Validation tests
├── 🚀 install.sh             # One-line installer script
├── 🐳 docker-compose.yaml    # Docker configuration
├── 📋 .env.example           # Configuration template
├── 🛠️ Dockerfile             # Container definition
└── 📄 pyproject.toml         # Python project configuration
```

---

## 🔐 Security Best Practices

### 🛡️ Authentication by Default
**All services are protected with Authelia authentication by default**. This prevents accidental exposure of services to the internet.

### ⚠️ Disabling Authentication (Not Recommended)
If you absolutely must disable authentication:

1. Set environment variable: `SWAG_MCP_DEFAULT_AUTH_METHOD=none`
2. Explicitly request no authentication when creating configs (not recommended)
3. **Warning**: Only do this for internal networks!

### 🤖 MCP Services Security
MCP servers are powerful and must be protected:
- Always use authentication for MCP endpoints
- Monitor access logs regularly
- Use HTTPS in production
- Implement rate limiting for public services

---

## 📊 Monitoring & Logs

### Log Locations

```bash
# Application logs (inside container)
/app/.swag-mcp/logs/swag-mcp.log

# Host log directory (mounted volume)
${SWAG_MCP_LOG_DIRECTORY}/swag-mcp.log

# Docker container logs
docker compose logs -f swag-mcp

# View logs using natural language
"Show last 100 lines of nginx error logs"
```

### Health Monitoring

```bash
# Internal health endpoint
curl http://localhost:${SWAG_MCP_PORT}/health

# Check specific service using natural language
"Check if app.example.com is accessible"

# Container health status
docker compose ps swag-mcp
```

---

## 🔧 Troubleshooting

### Common Issues & Solutions

#### Port Already in Use
**Problem**: `bind: address already in use`
**Solution**: Change `SWAG_MCP_PORT` in your `.env` file to an available port

#### Permission Denied Errors
**Problem**: Cannot access SWAG directories
**Solution**:
- Ensure Docker has access to mounted volumes
- Check directory permissions: `ls -la /path/to/swag/nginx/proxy-confs`
- Verify user/group ownership matches Docker container

#### Health Checks Failing
**Problem**: Services appear unreachable
**Solution**:
- Verify services are running: `docker ps`
- Check domain DNS resolution
- Ensure SWAG is properly configured and running
- Test direct access: `curl http://service:port`

#### Logs Not Appearing
**Problem**: Log commands return empty
**Solution**:
- Check `SWAG_MCP_LOG_DIRECTORY` permissions
- Verify log directory exists and is writable
- Ensure container has access to log volume mount

#### Configuration Not Applied
**Problem**: New configs don't take effect
**Solution**:
- Restart SWAG container: `docker restart swag`
- Check SWAG logs for configuration errors
- Verify config file syntax and permissions

#### Connection Timeouts
**Problem**: AI assistant loses connection
**Solution**:
- Check container status: `docker compose ps swag-mcp`
- Verify network connectivity: `curl http://localhost:${SWAG_MCP_PORT}/health`
- Restart the MCP server: `docker compose restart swag-mcp`

### Getting Help

If you encounter issues not covered above:
1. Check container logs: `docker compose logs swag-mcp`
2. Verify your `.env` configuration
3. Test with the health endpoint
4. Join the community discussions on GitHub

---

## 🤝 Contributing

We welcome contributions! Feel free to open issues, submit pull requests, or suggest improvements.

### Development Setup

```bash
# Clone and setup
git clone https://github.com/jmagar/swag-mcp.git
cd swag-mcp

# Install with dev dependencies
uv sync --dev

# Run pre-commit hooks
pre-commit install

# Run tests before submitting
uv run pytest
```

---

## 📝 License

MIT License - See [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

Built with:
- [FastMCP](https://github.com/fastmcp/fastmcp) - MCP server framework
- [SWAG](https://github.com/linuxserver/docker-swag) - Secure Web Application Gateway
- [Authelia](https://www.authelia.com/) - Authentication and authorization server

---

<p align="center">
  Made with ❤️ for the self-hosting community
</p>
