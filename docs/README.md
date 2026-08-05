# SWAG MCP

<!-- mcp-name: tv.nashost/swag-mcp -->

[![PyPI](https://img.shields.io/pypi/v/swag-mcp)](https://pypi.org/project/swag-mcp/) [![ghcr.io](https://img.shields.io/badge/ghcr.io-jmagar%2Fswag--mcp-blue?logo=docker)](https://github.com/jmagar/swag-mcp/pkgs/container/swag-mcp)

MCP server for self-hosted SWAG (Secure Web Application Gateway) reverse proxy. Exposes a unified `swag` action router and a `swag_help` companion tool for managing nginx proxy configurations.

## Overview

Two MCP tools are exposed:

| Tool | Purpose |
| --- | --- |
| `swag` | Unified action router for all SWAG proxy configuration operations |
| `swag_help` | Returns markdown documentation for all actions and parameters |

The server uses streamable-HTTP transport on port 8000 internally. Direct HTTP
access requires `SWAG_MCP_TOKEN`, a FastMCP auth provider, or explicit
`SWAG_MCP_NO_AUTH=true` for loopback/proxy-isolated deployments. Both local
filesystem and remote SSH access modes are supported.

## What this repository ships

- `swag_mcp/server.py`: FastMCP server with streamable-http transport, middleware stack, and health endpoint
- `swag_mcp/tools/swag.py`: Unified action router with 9 actions
- `swag_mcp/services/`: Service layer with 9 sub-managers (file ops, templates, validation, backups, health, resources, MCP ops, config updaters, config operations)
- `swag_mcp/middleware/`: Rate limiting, error handling, timing, request logging, retry, security error sanitization
- `templates/mcp.subdomain.conf.j2`: Jinja2 nginx config template with MCP/OAuth support
- `config/nginx/mcp-server.conf`: Server-level MCP identity/discovery/auth sidecar
- `config/nginx/mcp-location.conf`: Location-level MCP transport overrides (buffering, timeouts, SSE, CORS)
- `plugins/swag-mcp/skills/swag/SKILL.md`: Client-facing skill documentation
- `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `gemini-extension.json`: Client manifests
- `docker-compose.yaml`, `Dockerfile`, `entrypoint.sh`: Container deployment

## Tools

### `swag`

Single entry point for all SWAG operations. Select the operation with the `action` parameter.

| Action | Description |
| --- | --- |
| `list` | List proxy configurations (filter: all/active/samples, pagination support) |
| `create` | Create new proxy configuration from Jinja2 template |
| `view` | View a configuration file's contents |
| `edit` | Replace a configuration file's content (with backup) |
| `update` | Update a specific field: port, upstream, app, or add_mcp |
| `remove` | Remove a configuration file (with backup) |
| `logs` | View SWAG logs (nginx-access, nginx-error, fail2ban, letsencrypt, renewal) |
| `backups` | Manage config backups (list or cleanup with retention days) |
| `health_check` | Run HTTP health check against a proxied domain |

### `swag_help`

Returns the full action reference as Markdown. Call this to discover available actions.

```python
swag_help()
```

## Installation

### Marketplace

```bash
/plugin marketplace add jmagar/claude-homelab
/plugin install swag-mcp @jmagar-claude-homelab
```

### Local development

```bash
uv sync --dev
uv run python -m swag_mcp
```

### Docker

```bash
just up
```

Or manually:

```bash
docker compose up -d
```

## Authentication

`SWAG_MCP_TOKEN` enables built-in static bearer-token authentication for direct
HTTP MCP access. Startup fails closed unless token auth, `FASTMCP_SERVER_AUTH`,
or explicit `SWAG_MCP_NO_AUTH=true` is configured.

Keep Docker's published port bound to loopback unless a reverse proxy or trusted
network enforces access controls. See [AUTH](mcp/AUTH.md) for detailed setup.

## Configuration

Copy `.env.example` to `.env` and fill in the required values:

```bash
cp .env.example .env
chmod 600 .env
```

### Environment variables

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `SWAG_MCP_PROXY_CONFS_PATH` | yes* | `/swag/nginx/proxy-confs` | Path to SWAG proxy configurations directory |
| `SWAG_MCP_PROXY_CONFS_URI` | no | — | SSH URI to remote proxy-confs (overrides path if set) |
| `SWAG_MCP_HOST` | no | `127.0.0.1` | Network interface to bind |
| `SWAG_MCP_BIND_ADDRESS` | no | `127.0.0.1` | Docker host bind address |
| `SWAG_MCP_PORT` | no | `49152` | Docker host port mapping (container always uses 8000) |
| `SWAG_MCP_TOKEN` | recommended | — | Bearer token enforced by FastMCP |
| `SWAG_MCP_NO_AUTH` | no | `false` | Explicitly allow startup without direct server auth |

*Required when `SWAG_MCP_PROXY_CONFS_URI` is not set.

See [CONFIG](CONFIG.md) for all variables including logging, rate limiting, retry, and backup settings.

## Quick start

```python
# List all active proxy configurations
swag(action="list", list_filter="active")

# Create a new proxy config
swag(action="create", config_name="jellyfin.subdomain.conf",
     server_name="media.example.com", upstream_app="jellyfin",
     upstream_port=8096, auth_method="authelia")

# Create with split routing (main app + separate MCP server)
swag(action="create", config_name="jellyfin.subdomain.conf",
     server_name="jellyfin.example.com", upstream_app="jellyfin",
     upstream_port=8096, mcp_upstream_app="ai-gpu-server",
     mcp_upstream_port=8080)

# View a configuration
swag(action="view", config_name="jellyfin.subdomain.conf")

# Update a port
swag(action="update", config_name="jellyfin.subdomain.conf",
     update_field="port", update_value="8097")

# Add MCP endpoint to existing config
swag(action="update", config_name="plex.subdomain.conf",
     update_field="add_mcp", update_value="/mcp")

# Check health
swag(action="health_check", domain="media.example.com")

# View nginx error logs
swag(action="logs", log_type="nginx-error", lines=100)

# Clean up old backups
swag(action="backups", backup_action="cleanup", retention_days=7)
```

## Docker usage

```bash
# Build and start
just up

# View logs
just logs

# Health check
just health
# or: curl http://127.0.0.1:49152/health

# Stop
just down
```

The `/health` endpoint is unauthenticated for liveness probes.

## Dual access modes

SWAG MCP supports two modes for accessing proxy configuration files:

### Local filesystem

Set `SWAG_MCP_PROXY_CONFS_PATH` to a local directory. Used when the MCP server runs on the same machine as SWAG or has the directory mounted via Docker volume.

```bash
SWAG_MCP_PROXY_CONFS_PATH=/mnt/appdata/swag/nginx/proxy-confs
```

### Remote SSH

Set `SWAG_MCP_PROXY_CONFS_URI` to an SSH URI. Used when SWAG runs on a different machine. Requires passwordless SSH keys.

```bash
# Basic
SWAG_MCP_PROXY_CONFS_URI=swag-server:/mnt/appdata/swag/nginx/proxy-confs

# With user
SWAG_MCP_PROXY_CONFS_URI=admin@swag-server:/mnt/appdata/swag/nginx/proxy-confs

# With custom port
SWAG_MCP_PROXY_CONFS_URI=swag-server:2222:/mnt/appdata/swag/nginx/proxy-confs
```

When `SWAG_MCP_PROXY_CONFS_URI` is set, it takes precedence over `SWAG_MCP_PROXY_CONFS_PATH`. The SSH backend uses asyncssh for native async SFTP operations with automatic reconnection on connection loss.

## Related plugins

| Plugin | Category | Description |
|--------|----------|-------------|
| [homelab-core](https://github.com/jmagar/claude-homelab) | core | Core agents, commands, skills, and setup/health workflows for homelab management. |
| [overseerr-mcp](https://github.com/jmagar/overseerr-mcp) | media | Search movies and TV shows, submit requests, and monitor failed requests via Overseerr. |
| [unraid-mcp](https://github.com/jmagar/unraid-mcp) | infrastructure | Query, monitor, and manage Unraid servers. |
| [unifi-mcp](https://github.com/jmagar/unifi-mcp) | infrastructure | Monitor and manage UniFi devices and network health. |
| [synapse-mcp](https://github.com/jmagar/synapse-mcp) | infrastructure | Docker management and SSH remote operations across homelab hosts. |
| [arcane-mcp](https://github.com/jmagar/arcane-mcp) | infrastructure | Manage Docker environments, containers, images, volumes, and networks. |
| [syslog-mcp](https://github.com/jmagar/syslog-mcp) | infrastructure | Receive, index, and search syslog streams via SQLite FTS5. |
| [gotify-mcp](https://github.com/jmagar/gotify-mcp) | utilities | Send push notifications and manage Gotify messages and applications. |
| [plugin-lab](https://github.com/jmagar/plugin-lab) | dev-tools | Scaffold, review, align, and deploy homelab MCP plugins. |

## License

MIT
