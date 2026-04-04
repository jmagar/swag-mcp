# SWAG MCP

MCP server for managing SWAG reverse-proxy configuration files, backups, logs, and health checks. The repo uses a single `swag` action router backed by local filesystem or SSH-accessible SWAG config storage.

## What this repository ships

- `swag_mcp/`: server, config, middleware, models, services, tools, and templates
- `config/`: local config and test assets
- `docs/`: template notes, test commands, and design records
- `.claude-plugin/`, `.codex-plugin/`, `gemini-extension.json`: client manifests
- `docker-compose.yaml`, `Dockerfile`, `entrypoint.sh`: container deployment

## MCP surface

### Main tool

| Tool | Purpose |
| --- | --- |
| `swag` | Unified action router for config, logs, backups, and health checks |

### Supported actions

| Action | Purpose |
| --- | --- |
| `list` | List config files |
| `create` | Create a new reverse-proxy config |
| `view` | View config contents |
| `edit` | Replace config contents |
| `update` | Update a specific field in an existing config |
| `remove` | Remove a config |
| `logs` | Read SWAG logs |
| `backups` | List or clean up backup files |
| `health_check` | Probe a service endpoint |

The `update` action supports field-level updates such as `port`, `upstream`, `app`, and `add_mcp`.

## Installation

### Marketplace

```bash
/plugin marketplace add jmagar/claude-homelab
/plugin install swag-mcp @jmagar-claude-homelab
```

### Local development

```bash
uv sync --all-extras --dev
uv run python -m swag_mcp
```

The repo's `Justfile` also exposes:

```bash
just dev
```

## Configuration

Create `.env` from `.env.example` and set the storage mode you use:

```bash
SWAG_MCP_PROXY_CONFS_PATH=/swag/nginx/proxy-confs
SWAG_MCP_SWAG_LOG_BASE_PATH=/swag/log
SWAG_MCP_LOG_DIRECTORY=/app/.swag-mcp/logs
SWAG_MCP_HOST=0.0.0.0
SWAG_MCP_PORT=8000
SWAG_MCP_TOKEN=...
SWAG_MCP_NO_AUTH=false
SWAG_MCP_DEFAULT_AUTH_METHOD=authelia
SWAG_MCP_DEFAULT_QUIC_ENABLED=false
SWAG_MCP_BACKUP_RETENTION_DAYS=30
SWAG_MCP_TEMPLATE_PATH=templates
```

Important notes:

- use `SWAG_MCP_PROXY_CONFS_PATH` for local filesystem mode
- use the repo's remote/SSH options if configs live on another host
- HTTP auth is token-based unless disabled intentionally
- the server runs streamable HTTP in practice through `python -m swag_mcp`

## Typical operations

```text
swag action=list
swag action=create config_name=jellyfin.subdomain.conf server_name=jellyfin.example.com upstream_app=jellyfin upstream_port=8096
swag action=view config_name=jellyfin.subdomain.conf
swag action=update config_name=jellyfin.subdomain.conf update_field=port update_value=8097
swag action=health_check domain=jellyfin.example.com
```

## Development commands

```bash
just setup
just dev
just lint
just fmt
just typecheck
just test
just up
just logs
```

## Verification

Recommended:

```bash
just lint
just typecheck
just test
```

If you need a local health check:

```bash
just health
```

## Related files

- `swag_mcp/server.py`: server bootstrap and transport startup
- `swag_mcp/tools/handlers/`: action handlers
- `docs/TEMPLATES.md`: template model and routing behavior
- `config/mcporter.json`: test harness config

## License

MIT
