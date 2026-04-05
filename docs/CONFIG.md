# Configuration Reference -- swag-mcp

Complete environment variable reference and configuration options.

## Environment file

```bash
cp .env.example .env
chmod 600 .env
```

Precedence (highest to lowest):
1. `.env` file in project root
2. Container environment variables (Docker `environment:` or `-e` flags)
3. System environment variables

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
| `SWAG_MCP_PORT` | no | `8000` | no | External port mapping. Internal container port is always 8000 |
| `SWAG_MCP_TOKEN` | no | — | yes | Bearer token (informational; auth enforced externally) |
| `SWAG_MCP_NO_AUTH` | no | `false` | no | Suppress auth warning at startup |

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

## Plugin userConfig

When installed as a Claude Code plugin, these fields map to `userConfig` in `.claude-plugin/plugin.json`:

```json
{
  "userConfig": {
    "swag_mcp_url": {
      "type": "string",
      "title": "SWAG MCP Server URL",
      "description": "URL of the swag-mcp MCP server",
      "default": "https://swag.tootie.tv/mcp",
      "sensitive": false
    },
    "swag_proxy_confs_path": {
      "type": "string",
      "title": "SWAG Proxy Configs Path",
      "description": "Local filesystem path to SWAG nginx proxy-confs directory",
      "sensitive": false
    },
    "swag_proxy_confs_uri": {
      "type": "string",
      "title": "SWAG Proxy Configs URI (Remote/SSH)",
      "description": "SSH URI to remote SWAG proxy-confs. Overrides path if set.",
      "sensitive": false
    },
    "swag_mcp_token": {
      "type": "string",
      "title": "MCP Server Bearer Token",
      "description": "Bearer token for MCP auth. Generate: openssl rand -hex 32",
      "sensitive": true
    }
  }
}
```

## .env.example conventions

- Group variables by section with comment headers
- Required variables first within each group
- No actual secrets -- only placeholders
- Include inline usage instructions
- See `.env.example` in the repository root for the complete template
