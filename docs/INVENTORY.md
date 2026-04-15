# Component Inventory -- swag-mcp

Complete listing of all plugin components.

## MCP tools

| Tool | Action | Description | Destructive |
| --- | --- | --- | --- |
| `swag` | `list` | List proxy configurations (filter, paginate, sort, search) | no |
| `swag` | `create` | Create new proxy configuration from Jinja2 template | no |
| `swag` | `view` | View configuration file contents | no |
| `swag` | `edit` | Replace configuration content (creates backup) | yes |
| `swag` | `update` | Update specific field: port, upstream, app, add_mcp | yes |
| `swag` | `remove` | Remove configuration file (creates backup) | yes |
| `swag` | `logs` | View SWAG logs (5 log types) | no |
| `swag` | `backups` | List or cleanup backup files | no* |
| `swag` | `health_check` | HTTP health check against a proxied domain | no |
| `swag_help` | -- | Return action reference as Markdown | no |

*`backups` with `backup_action="cleanup"` deletes old files.

## MCP resources

| URI | Description | MIME type |
| --- | --- | --- |
| `swag://` | Active SWAG configurations (DirectoryResource) | application/json |
| `swag://configs/live` | Real-time configuration change stream | application/json |
| `swag://health/stream` | Real-time health status updates for monitored services | text/plain |
| `swag://logs/stream` | Real-time SWAG nginx error log stream | text/plain |

## Environment variables

| Variable | Required | Default | Sensitive |
| --- | --- | --- | --- |
| `SWAG_MCP_PROXY_CONFS_PATH` | yes* | `/swag/nginx/proxy-confs` | no |
| `SWAG_MCP_PROXY_CONFS_URI` | no | — | no |
| `SWAG_MCP_SWAG_LOG_BASE_PATH` | no | `/swag/log` | no |
| `SWAG_MCP_TEMPLATE_PATH` | no | `templates` | no |
| `SWAG_MCP_LOG_DIRECTORY` | no | `/app/.swag-mcp/logs` | no |
| `SWAG_MCP_HOST` | no | `127.0.0.1` | no |
| `SWAG_MCP_PORT` | no | `8000` | no |
| `SWAG_MCP_TOKEN` | no | — | yes |
| `SWAG_MCP_NO_AUTH` | no | `false` | no |
| `SWAG_MCP_DEFAULT_AUTH_METHOD` | no | `authelia` | no |
| `SWAG_MCP_DEFAULT_QUIC_ENABLED` | no | `false` | no |
| `SWAG_MCP_OAUTH_UPSTREAM` | no | `http://mcp-oauth:8000` | no |
| `SWAG_MCP_AUTH_SERVER_URL` | no | `https://mcp-auth.tootie.tv` | no |
| `SWAG_MCP_BACKUP_RETENTION_DAYS` | no | `30` | no |
| `SWAG_MCP_LOG_LEVEL` | no | `INFO` | no |
| `SWAG_MCP_LOG_FILE_ENABLED` | no | `true` | no |
| `SWAG_MCP_LOG_FILE_MAX_BYTES` | no | `10485760` | no |
| `SWAG_MCP_ENABLE_STRUCTURED_LOGGING` | no | `false` | no |
| `SWAG_MCP_LOG_PAYLOADS` | no | `false` | no |
| `SWAG_MCP_LOG_PAYLOAD_MAX_LENGTH` | no | `1000` | no |
| `SWAG_MCP_RATE_LIMIT_ENABLED` | no | `false` | no |
| `SWAG_MCP_RATE_LIMIT_RPS` | no | `10.0` | no |
| `SWAG_MCP_RATE_LIMIT_BURST` | no | `20` | no |
| `SWAG_MCP_SLOW_OPERATION_THRESHOLD_MS` | no | `1000` | no |
| `SWAG_MCP_ENABLE_RETRY_MIDDLEWARE` | no | `true` | no |
| `SWAG_MCP_MAX_RETRIES` | no | `3` | no |
| `SWAG_MCP_HEALTH_CHECK_INSECURE` | no | `false` | no |
| `PUID` | no | `1000` | no |
| `PGID` | no | `1000` | no |
| `DOCKER_NETWORK` | no | `swag-mcp` | no |

## Plugin surfaces

| Surface | Present | Path |
| --- | --- | --- |
| Skills | yes | `skills/swag/SKILL.md` |
| Agents | no | — |
| Commands | no | — |
| Hooks | yes | `hooks/hooks.json` |
| Channels | no | — |
| Output styles | no | — |
| Schedules | no | — |

## Docker

| Component | Value |
| --- | --- |
| Image | `ghcr.io/jmagar/swag-mcp:latest` |
| Internal port | `8000` |
| Health endpoint | `GET /health` (unauthenticated) |
| Compose file | `docker-compose.yaml` |
| Entrypoint | `python -m swag_mcp` |
| User | `1000:1000` (swagmcp) |
| Memory limit | `1024M` |
| CPU limit | `1` |

## CI/CD workflows

| Workflow | Trigger | Purpose |
| --- | --- | --- |
| `test.yml` | push, PR | Lint (ruff), typecheck (ty), test (pytest) |
| `docker-publish.yml` | tag push | Build and publish Docker image to GHCR |
| `publish-pypi.yml` | tag push | Build and publish to PyPI |
| `dependencies.yml` | scheduled | Dependency updates |

## Scripts

| Script | Purpose |
| --- | --- |
| `bin/smoke-test.sh` | Smoke test against running server |
| `scripts/lint-plugin.sh` | Verify plugin manifest contract |
The `sync-uv.sh` hook keeps the repository lockfile and persistent Python environment in sync at session start.
| `bin/` | Set `.env` to chmod 600 |



## Dependencies

Runtime

| Package | Version | Purpose |
| --- | --- | --- |
| `fastmcp` | >=2.11.3 | MCP server framework |
| `pydantic` | >=2.11.7 | Data validation and settings |
| `pydantic-settings` | >=2.7.0 | Environment-based configuration |
| `jinja2` | >=3.1.6 | Template rendering for nginx configs |
| `aiofiles` | >=24.1.0 | Async file I/O |
| `aiohttp` | >=3.9.0 | Async HTTP client for health checks |
| `pyyaml` | >=6.0.0 | YAML parsing |
| `regex` | >=2024.5.15 | Advanced regex for validation |
| `docker` | >=7.1.0 | Docker API client for log access |
| `asyncssh` | >=2.14.0 | SSH/SFTP for remote filesystem access |

Development

| Package | Version | Purpose |
| --- | --- | --- |
| `pytest` | >=7.0.0 | Test framework |
| `pytest-asyncio` | >=0.21.0 | Async test support |
| `pytest-cov` | >=4.0.0 | Coverage reporting |
| `ruff` | >=0.8.0 | Linter and formatter |
| `ty` | >=0.0.24 | Type checker |
| `lefthook` | latest | Git hook management |
| `bandit` | >=1.7.0 | Security linting |
| `pip-audit` | >=2.0.0 | Dependency vulnerability scanning |
| `hypothesis` | >=6.0.0 | Property-based testing |
| `pytest-benchmark` | >=4.0.0 | Performance testing |
| `psutil` | >=5.9.0 | System monitoring for benchmarks |
