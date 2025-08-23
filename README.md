# 🛡️ SWAG MCP Server

> **Intelligent reverse proxy management for SWAG (Secure Web Application Gateway) with Model Context Protocol support**

[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastMCP](https://img.shields.io/badge/FastMCP-latest-green.svg)](https://github.com/fastmcp/fastmcp)
[![Docker](https://img.shields.io/badge/Docker-ghcr.io-blue.svg)](https://github.com/jmagar/swag-mcp/pkgs/container/swag-mcp)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

Transform your SWAG reverse proxy management with AI-powered automation and real-time health monitoring. Generates SWAG proxy configs for your self-hosted services and MCP servers.

---

## ✨ Key Features

### 🚀 **Core Capabilities**
- **Smart Configuration Generation** - Create SWAG proxy configs from intelligent templates
- **Real-time Health Monitoring** - Verify your services are accessible and running
- **Automatic Backups** - Never lose a configuration with automatic backup on edit
- **MCP Protocol Support** - Generates steamable-http SWAG proxy configs

### 🔐 **Security First**
- **Authelia by Default** - All services protected automatically
- **Secure Templates** - Pre-configured security headers and best practices
- **Audit Logging** - Complete activity tracking and monitoring

### 🤖 **MCP Ready**
- **Claude Desktop Integration** - Works seamlessly with Claude AI, Claude Code, Cursor, Windsurf, Cline, Roo Code, KiloCode, Goose, etx 
- **Streaming Support** - Server-Sent Events for real-time AI responses
- **Extended Timeouts** - Optimized for remote MCP servers.

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

---

## 🎯 Installation Options

### Option 1: Docker Compose (Recommended)

The one-line installer above is the fastest way. For manual Docker installation:

```bash
# Download files manually
curl -O https://raw.githubusercontent.com/jmagar/swag-mcp/main/docker-compose.yaml
curl -O https://raw.githubusercontent.com/jmagar/swag-mcp/main/.env.example
cp .env.example .env

# Edit .env with your paths
nano .env

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
SWAG_PROXY_CONFS_PATH=/mnt/appdata/swag/nginx/proxy-confs
SWAG_MCP_DATA_PATH=/mnt/appdata/swag-mcp

# Security (Defaults shown)
SWAG_MCP_DEFAULT_AUTH_METHOD=authelia  # Never expose services without auth!
SWAG_MCP_DEFAULT_CONFIG_TYPE=subdomain  # or subfolder, mcp-subdomain, mcp-subfolder

# Server Settings
SWAG_MCP_HOST=0.0.0.0  # For Docker/external access
SWAG_MCP_PORT=8000
```

<details>
<summary>📊 Advanced Configuration Options</summary>

```bash
# Logging
SWAG_MCP_LOG_LEVEL=INFO
SWAG_MCP_LOG_FILE_ENABLED=true
SWAG_MCP_LOG_FILE_MAX_BYTES=10485760

# Performance
SWAG_MCP_SLOW_OPERATION_THRESHOLD_MS=1000
SWAG_MCP_ENABLE_RETRY_MIDDLEWARE=true
SWAG_MCP_MAX_RETRIES=3

# Rate Limiting (Optional)
SWAG_MCP_RATE_LIMIT_ENABLED=false
SWAG_MCP_RATE_LIMIT_RPS=10.0
SWAG_MCP_RATE_LIMIT_BURST=20

# Backup Management
SWAG_MCP_BACKUP_RETENTION_DAYS=30
```

</details>

---

## 📚 Usage Guide

### Creating a Basic Service

```python
# Standard web service
swag_create(
    service_name="jellyfin",
    server_name="jellyfin.example.com",
    upstream_app="jellyfin",
    upstream_port=8096
)
```

### Creating a Streamable-HTTP MCP service

```python
# AI service with streaming support
swag_create(
    service_name="claude-mcp",
    server_name="ai.example.com",
    upstream_app="claude-mcp-server",
    upstream_port=8080,
    config_type="mcp-subdomain"  # Enables Streamable-HTTP/SSE streaming
)
```

### Health Check Verification

```python
# Verify your service is accessible
swag_health_check(
    domain="jellyfin.example.com"
)
# Returns: ✅ Health check passed: 200 (45ms)
```

---

## 🛠️ Available Tools

### Essential Tools

| Tool | Description | Example |
|------|-------------|---------|
| **`swag_create`** | Generate new proxy configuration | Create subdomain for service |
| **`swag_health_check`** | Verify service accessibility | Test if proxy is working |
| **`swag_list`** | List all configurations | View active/sample configs |
| **`swag_view`** | Read configuration content | Inspect existing config |
| **`swag_edit`** | Modify configuration safely | Update with automatic backup |

### Management Tools

| Tool | Description | Example |
|------|-------------|---------|
| **`swag_remove`** | Delete configuration | Remove with optional backup |
| **`swag_config`** | Set default preferences | Configure auth method |
| **`swag_logs`** | View container logs | Debug issues |
| **`swag_cleanup_backups`** | Manage backup files | Remove old backups |

<details>
<summary>📖 Detailed Tool Documentation</summary>

#### swag_create
Creates a new reverse proxy configuration with automatic health check verification.

**Parameters:**
- `service_name` - Identifier for your service
- `server_name` - Domain name (e.g., app.example.com)
- `upstream_app` - Container name or IP address
- `upstream_port` - Port number
- `config_type` - Template type:
  - `subdomain` - Standard subdomain proxy
  - `subfolder` - Path-based routing
  - `mcp-subdomain` - AI service with SSE
  - `mcp-subfolder` - AI service on path
- `auth_method` - Authentication (defaults to authelia)

#### swag_health_check
Intelligently tests service availability through multiple endpoints.

**Smart Endpoint Detection:**
1. Tries `/health` endpoint first
2. Falls back to `/mcp` for AI services
3. Finally tests root `/` endpoint
4. Returns success for any valid HTTP response

**Parameters:**
- `domain` - Full domain to test
- `timeout` - Max wait time (default: 30s)
- `follow_redirects` - Handle redirects (default: true)

</details>

---

## 🏗️ Template System

### Standard Templates
Perfect for traditional web applications:
- **`subdomain`** - `app.example.com` → `container:port`
- **`subfolder`** - `example.com/app` → `container:port`

### MCP Templates
Optimized for remote MCP services with streaming:
- **`mcp-subdomain`** - MCP service on subdomain with Streamable-HTTP/SSE support
- **`mcp-subfolder`** - MCP service on path with Streamable-HTTP/SSE support

**MCP Template Features:**
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
        "SWAG_PROXY_CONFS_PATH": "/your/swag/proxy-confs",
        "SWAG_MCP_DATA_PATH": "/your/swag-mcp/data"
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
uv run pytest tests/test_services.py   # Core logic
uv run pytest tests/test_tools.py      # MCP tools
uv run pytest tests/test_middleware.py # Middleware
```

---

## 📂 Project Structure

```
swag-mcp/
├── 📦 swag_mcp/              # Core application
│   ├── 🚀 server.py          # Entry point
│   ├── ⚙️ core/              # Configuration
│   ├── 📊 models/            # Data models
│   ├── 🔧 services/          # Business logic
│   ├── 🛠️ tools/             # MCP tools
│   └── 🔌 middleware/        # Request processing
├── 📝 templates/             # Jinja2 templates
│   ├── subdomain.conf.j2
│   ├── subfolder.conf.j2
│   ├── mcp-subdomain.conf.j2  # AI-optimized
│   └── mcp-subfolder.conf.j2  # AI-optimized
├── 🧪 tests/                 # Test suite
├── 🐳 docker-compose.yaml    # Docker config
└── 📋 .env.example           # Config template
```

---

## 🔐 Security Best Practices

### 🛡️ Authentication by Default
Starting with v2.0, **all services are protected with Authelia authentication by default**. This prevents accidental exposure of services to the internet.

### ⚠️ Disabling Authentication (Not Recommended)
If you absolutely must disable authentication:

1. Set environment variable: `SWAG_MCP_DEFAULT_AUTH_METHOD=none`
2. Explicitly pass: `auth_method="none"` when creating configs
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
# Application logs
${SWAG_MCP_DATA_PATH}/logs/swag-mcp.log

# Middleware logs (performance, errors)
${SWAG_MCP_DATA_PATH}/logs/swag-middleware.log

# Docker logs
docker compose logs -f swag-mcp
```

### Health Monitoring

```bash
# Internal health endpoint
curl http://localhost:8000/health

# Check specific service
swag_health_check domain="app.example.com"
```

---

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

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
