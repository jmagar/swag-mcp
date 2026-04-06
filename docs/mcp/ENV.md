# Environment Variable Reference

Comprehensive reference for all environment variables read by swag-mcp. All variables use the `SWAG_MCP_` prefix and are case-insensitive.

## Deployment paths

swag-mcp supports two deployment models:

| Path | Transport | Credentials | Auth |
|------|-----------|-------------|------|
| **Plugin (stdio)** | stdio | `${userConfig.*}` in `.mcp.json` | None (stdio) |
| **Plugin (mcp-remote)** | HTTP gateway | Manual config in `.mcp.json` | Bearer token |
| **Docker (HTTP)** | http | `.env` file | Bearer token |

For plugin deployment, see [Plugin CONFIG](../plugin/CONFIG.md).

## Upstream service

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_PROXY_CONFS_PATH` | yes* | `/swag/nginx/proxy-confs` | no | Local path to SWAG proxy-confs directory |
| `SWAG_MCP_PROXY_CONFS_URI` | no | — | no | SSH URI for remote access. Format: `[user@]host[:port]:/path` |
| `SWAG_MCP_SWAG_LOG_BASE_PATH` | no | `/swag/log` | no | Base path for SWAG logs (nginx, fail2ban, letsencrypt) |

*Required when `SWAG_MCP_PROXY_CONFS_URI` is not set.

When `SWAG_MCP_PROXY_CONFS_URI` is set, it takes precedence over `SWAG_MCP_PROXY_CONFS_PATH`. The URI is parsed to determine whether to use local filesystem or SSH/SFTP backend.

### SSH URI examples

```bash
# Remote host, default port 22, current user
SWAG_MCP_PROXY_CONFS_URI=swag-server:/mnt/appdata/swag/nginx/proxy-confs

# Remote host with explicit user
SWAG_MCP_PROXY_CONFS_URI=admin@swag-server:/mnt/appdata/swag/nginx/proxy-confs

# Remote host with custom SSH port
SWAG_MCP_PROXY_CONFS_URI=swag-server:2222:/mnt/appdata/swag/nginx/proxy-confs

# Full specification
SWAG_MCP_PROXY_CONFS_URI=admin@swag-server:2222:/mnt/appdata/swag/nginx/proxy-confs
```

## MCP server

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_HOST` | no | `127.0.0.1` | no | Bind interface. Docker overrides to `0.0.0.0` |
| `SWAG_MCP_PORT` | no | `8000` | no | External port. Internal container port is fixed at 8000 |
| `SWAG_MCP_TOKEN` | no | — | yes | Bearer token (logged, not enforced) |
| `SWAG_MCP_NO_AUTH` | no | `false` | no | Suppress "no token" startup warning |
| `SWAG_MCP_TEMPLATE_PATH` | no | `templates` | no | Jinja2 template directory |
| `SWAG_MCP_LOG_DIRECTORY` | no | `/app/.swag-mcp/logs` | no | Server log file directory |

## Defaults

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_DEFAULT_AUTH_METHOD` | no | `authelia` | no | Default auth for new configs |
| `SWAG_MCP_DEFAULT_QUIC_ENABLED` | no | `false` | no | Default QUIC/HTTP3 setting |
| `SWAG_MCP_OAUTH_UPSTREAM` | no | `http://mcp-oauth:8000` | no | OAuth gateway upstream address |
| `SWAG_MCP_AUTH_SERVER_URL` | no | `https://mcp-auth.tootie.tv` | no | Public OAuth authorization server URL |
| `SWAG_MCP_BACKUP_RETENTION_DAYS` | no | `30` | no | Backup retention period in days |

## Logging

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_LOG_LEVEL` | no | `INFO` | no | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `SWAG_MCP_LOG_FILE_ENABLED` | no | `true` | no | Enable file logging |
| `SWAG_MCP_LOG_FILE_MAX_BYTES` | no | `10485760` | no | Max log file size (10 MB) |
| `SWAG_MCP_ENABLE_STRUCTURED_LOGGING` | no | `false` | no | JSON structured logging |
| `SWAG_MCP_LOG_PAYLOADS` | no | `false` | no | Log request/response payloads |
| `SWAG_MCP_LOG_PAYLOAD_MAX_LENGTH` | no | `1000` | no | Truncation limit for payloads |

## Middleware

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_RATE_LIMIT_ENABLED` | no | `false` | no | Enable rate limiting |
| `SWAG_MCP_RATE_LIMIT_RPS` | no | `10.0` | no | Requests per second |
| `SWAG_MCP_RATE_LIMIT_BURST` | no | `20` | no | Burst capacity |
| `SWAG_MCP_SLOW_OPERATION_THRESHOLD_MS` | no | `1000` | no | Slow operation warning threshold |
| `SWAG_MCP_ENABLE_RETRY_MIDDLEWARE` | no | `true` | no | Auto-retry failed operations |
| `SWAG_MCP_MAX_RETRIES` | no | `3` | no | Max retry attempts |

## Health check

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `SWAG_MCP_HEALTH_CHECK_INSECURE` | no | `false` | no | Disable SSL verification (dev only) |

## Docker

| Variable | Required | Default | Sensitive | Description |
| --- | --- | --- | --- | --- |
| `PUID` | no | `1000` | no | Container user UID |
| `PGID` | no | `1000` | no | Container group GID |
| `DOCKER_NETWORK` | no | `swag-mcp` | no | External Docker network |
