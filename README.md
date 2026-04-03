# SWAG MCP Server

> **Intelligent reverse proxy and security management for SWAG via the Model Context Protocol.**

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](CHANGELOG.md)
[![Python Version](https://img.shields.io/badge/python-3.11+-green.svg)](https://www.python.org/downloads/)
[![FastMCP](https://img.shields.io/badge/FastMCP-Enabled-brightgreen.svg)](https://github.com/jlowin/fastmcp)
[![License](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

---

## ✨ Overview
SWAG MCP transforms reverse proxy management into an AI-powered automated workflow. It enables AI assistants to generate secure Nginx configurations, manage service accessibility, and perform real-time health monitoring for your homelab services.

### 🎯 Key Features
| Feature | Description |
|---------|-------------|
| **Smart Templates** | Generate secure configs for basic, MCP, and remote services |
| **Auto-Security** | Native Authelia integration and pre-configured headers |
| **Fail-Safe Edits** | Automatic config backups before every modification |
| **Health Guard** | Real-time verification of service accessibility |

---

## 🎯 Claude Code Integration
The easiest way to use this plugin is through the Claude Code marketplace:

```bash
# Add the marketplace
/plugin marketplace add jmagar/claude-homelab

# Install the plugin
/plugin install swag-mcp @jmagar-claude-homelab
```

---

## ⚙️ Configuration & Credentials
Credentials follow the standardized `homelab-core` pattern.

**Location:** `~/.swag-mcp/.env`

### Required Variables
```bash
SWAG_MCP_PROXY_CONFS_PATH="/path/to/swag/proxy-confs"
SWAG_MCP_LOG_DIRECTORY="/app/.swag-mcp/logs"
SWAG_MCP_DEFAULT_AUTH_METHOD="authelia"
SWAG_MCP_PORT=8000
```

---

## 🛠️ Available Tools & Resources

### 🔧 Primary Tool: `swag`
The `swag` tool uses action-based routing to manage your Nginx proxy ecosystem.

| Action | Parameters | Description |
|--------|------------|-------------|
| **`create`** | `service_name`, `server_name`, `upstream`, `port` | Generate new proxy configuration |
| **`list`** | `none` | List all active proxy configurations |
| **`health`** | `service_name` | Verify service reachability and HTTP status |
| **`backup`** | `service_name` | Manually trigger a configuration backup |
| **`status`** | `service_name` | Check if config is enabled/disabled |

---

## 🏗️ Architecture & Design
This server is built for reliability and security in production homelab environments:
- **Template Engine:** Intelligent generation of Nginx `.subdomain.conf` files.
- **Safety Middleware:** Automatic backups and YAML-based state tracking.
- **MCP Streaming:** Optimized for remote MCP server proxying with SSE support.

---

## 🔧 Development
### Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager

### Setup
```bash
uv sync
uv run python -m swag_mcp.main
```

### Docker Deployment
```bash
# Deploy via one-line installer
curl -sSL https://raw.githubusercontent.com/jmagar/swag-mcp/main/install.sh | bash
```

---

## 🐛 Troubleshooting
| Issue | Cause | Solution |
|-------|-------|----------|
| **Permission Denied** | File Ownership | Check `SWAG_MCP_PROXY_CONFS_PATH` perms |
| **Config Not Active** | Disable State | Run `swag enable service_name` |
| **Port Conflict** | 8000 is taken | Change `SWAG_MCP_PORT` in `.env` |

---

## 📄 License
MIT © jmagar
