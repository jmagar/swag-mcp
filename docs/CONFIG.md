# Configuration Reference -- swag-mcp

Complete environment variable reference and configuration options.

## Deployment paths

| Path | Transport | Credentials source | Auth |
|------|-----------|-------------------|------|
| **Plugin (stdio)** | stdio | `userConfig` in plugin.json, interpolated via `.mcp.json` | None |
| **Plugin (mcp-remote)** | HTTP gateway | Manual `SWAG_MCP_URL` in `.mcp.json` | Bearer token |
| **Docker (HTTP)** | http | `.env` file | Bearer token |

### Plugin quickstart

Install the plugin in Claude Code. You will be prompted for:
- **SWAG Proxy Configs Path** -- local filesystem path to proxy-confs directory
- **SWAG Proxy Configs URI** -- SSH URI for remote access (key-auth only, no passwords)

One of the two is required. See [plugin/CONFIG.md](plugin/CONFIG.md) for details.

### Docker quickstart

```bash
cp .env.example .env
chmod 600 .env
# Edit .env with your paths and token
docker compose up -d
```

The configuration system uses Pydantic Settings with the `SWAG_MCP_` prefix. All variables are case-insensitive.

## Environment variables

### Core paths

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_PROXY_CONFS_PATH` | yes* | `/swag/nginx/proxy-confs` | no | Local path to SWAG proxy configurations directory |
| `SWAG_MCP_PROXY_CONFS_URI` | no | — | no | SSH URI for remote access (`[user@]host[:port]:/path`). Overrides path if set |
| `SWAG_MCP_SWAG_LOG_BASE_PATH` | no | `/swag/log` | no | Base path for SWAG log files (nginx, fail2ban, letsencrypt) |
| `SWAG_MCP_TEMPLATE_PATH` | no | `templates` | no | Path to Jinja2 template directory |
| `SWAG_MCP_LOG_DIRECTORY` | no | `/app/.swag-mcp/logs` | no | Directory for MCP server log files |

*Required when `SWAG_MCP_PROXY_CONFS_URI` is not set.

### Server settings

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_HOST` | no | `127.0.0.1` | no | Network interface to bind. Use `0.0.0.0` for Docker |
| `SWAG_MCP_BIND_ADDRESS` | no | `127.0.0.1` | no | Docker host bind address for the published MCP port |
| `SWAG_MCP_PORT` | no | `49152` | no | Docker host port mapping. Internal container port is always 8000 |
| `SWAG_MCP_TOKEN` | recommended | — | yes | Static bearer token enforced by FastMCP for direct HTTP access |
| `SWAG_MCP_NO_AUTH` | no | `false` | no | Explicitly allow startup without direct server auth |

### Default configuration

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_DEFAULT_AUTH_METHOD` | no | `authelia` | no | Default auth for new configs: none, basic, ldap, authelia, authentik, tinyauth |
| `SWAG_MCP_DEFAULT_QUIC_ENABLED` | no | `false` | no | Enable QUIC/HTTP3 by default for new configurations |

### OAuth gateway

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_OAUTH_UPSTREAM` | no | `http://mcp-oauth:8000` | no | OAuth gateway upstream (Docker container name or IP:port) |
| `SWAG_MCP_AUTH_SERVER_URL` | no | `https://mcp-auth.tootie.tv` | no | Public OAuth authorization server URL for Protected Resource Metadata |

### Backup settings

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_BACKUP_RETENTION_DAYS` | no | `30` | no | Days to retain backup files before cleanup |

### Logging

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_LOG_LEVEL` | no | `INFO` | no | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `SWAG_MCP_LOG_FILE_ENABLED` | no | `true` | no | Enable file logging in addition to console |
| `SWAG_MCP_LOG_FILE_MAX_BYTES` | no | `10485760` | no | Max log file size before rotation (10 MB default) |
| `SWAG_MCP_ENABLE_STRUCTURED_LOGGING` | no | `false` | no | Enable JSON structured logging for log aggregation |
| `SWAG_MCP_LOG_PAYLOADS` | no | `false` | no | Include request/response payloads in logs (debugging only) |
| `SWAG_MCP_LOG_PAYLOAD_MAX_LENGTH` | no | `1000` | no | Max length of logged payloads |

### Rate limiting

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_RATE_LIMIT_ENABLED` | no | `false` | no | Enable rate limiting middleware |
| `SWAG_MCP_RATE_LIMIT_RPS` | no | `10.0` | no | Requests per second limit |
| `SWAG_MCP_RATE_LIMIT_BURST` | no | `20` | no | Burst capacity above RPS limit |

### Performance

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_SLOW_OPERATION_THRESHOLD_MS` | no | `1000` | no | Threshold for slow operation warnings (ms) |
| `SWAG_MCP_ENABLE_RETRY_MIDDLEWARE` | no | `true` | no | Enable automatic retry for failed operations |
| `SWAG_MCP_MAX_RETRIES` | no | `3` | no | Max retries for failed operations |

### Health check

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_HEALTH_CHECK_INSECURE` | no | `false` | no | Disable SSL verification for health checks (development only) |

### Docker / container

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `PUID` | no | `1000` | no | UID for container process |
| `PGID` | no | `1000` | no | GID for container process |
| `DOCKER_NETWORK` | no | `swag-mcp` | no | External Docker network name |
| `SWAG_MCP_IMAGE` | no | `ghcr.io/jmagar/swag-mcp:latest` | no | Compose image reference. Pin to a release tag or digest in production |
| `SWAG_MCP_PULL_POLICY` | no | `missing` | no | Compose image pull policy |
| `SWAG_MCP_LOG_HOST_PATH` | no | `/tmp/swag-mcp/logs` | no | Host bind path for MCP server logs |
| `SWAG_MCP_PROXY_CONFS_HOST_PATH` | no | `/mnt/appdata/swag/nginx/proxy-confs` | no | Host bind path for SWAG proxy configs |
| `SWAG_MCP_NGINX_INCLUDES_HOST_PATH` | no | `./config/nginx` | no | Host bind path for nginx include snippets |
| `SWAG_MCP_FASTMCP_DATA_HOST_PATH` | no | `/mnt/appdata/swag-mcp/data` | no | Host bind path for FastMCP runtime data |
| `SWAG_MCP_SSH_HOST_PATH` | no | `./.cache/swag-mcp/ssh` | yes | Host bind path containing only the SSH key/config known_hosts needed by this service |

## Dependency and image policy

Runtime and dev dependencies in `pyproject.toml` use reviewed lower bounds plus
upper bounds for direct dependencies. `uv.lock` pins transitive versions for
reproducible installs. Scheduled dependency automation updates one direct
dependency per pull request instead of broad lockfile upgrades.

Docker base images can be digest-pinned at build time with `PYTHON_BASE_IMAGE`
and `UV_IMAGE` build args. Production Compose deployments should pin
`SWAG_MCP_IMAGE` to a reviewed release tag or digest.

## Plugin userConfig

When installed as a Claude Code plugin, these fields are declared in `.claude-plugin/plugin.json` and interpolated into `.mcp.json` via `${userConfig.*}`:

```json
{
  "userConfig": {
    "swag_proxy_confs_path": {
      "type": "string",
      "title": "SWAG Proxy Configs Path",
      "description": "Local filesystem path to SWAG nginx proxy-confs directory",
      "sensitive": false
    },
    "swag_proxy_confs_uri": {
      "type": "string",
      "title": "SWAG Proxy Configs URI (Remote/SSH)",
      "description": "SSH URI to remote SWAG proxy-confs. Only SSH-key auth supported.",
      "sensitive": true
    }
  }
}
```

HTTP-only fields (`swag_mcp_url`, `swag_mcp_token`) are not needed for plugin (stdio) deployment. For remote gateway access, use the `swag-mcp-remote` entry in `.mcp.json`.

## .env.example conventions

- Group variables by section with comment headers
- Required variables first within each group
- No actual secrets -- only placeholders
- Include inline usage instructions
- See `.env.example` in the repository root for the complete template
