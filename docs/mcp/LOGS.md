# Logging and Error Handling

Logging and error handling patterns for swag-mcp.

## Log configuration

Logging is configured at startup via `swag_mcp/core/logging_config.py` using dual output (console + optional file).

### Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `SWAG_MCP_LOG_LEVEL` | `INFO` | Minimum log level |
| `SWAG_MCP_LOG_FILE_ENABLED` | `true` | Write logs to file |
| `SWAG_MCP_LOG_FILE_MAX_BYTES` | `10485760` | Max file size before rotation (10 MB) |
| `SWAG_MCP_LOG_DIRECTORY` | `/app/.swag-mcp/logs` | Log file directory |
| `SWAG_MCP_ENABLE_STRUCTURED_LOGGING` | `false` | JSON structured logging |
| `SWAG_MCP_LOG_PAYLOADS` | `false` | Include payloads in logs |
| `SWAG_MCP_LOG_PAYLOAD_MAX_LENGTH` | `1000` | Truncation limit for payloads |

### Structured logging

Enable JSON structured logging for log aggregation pipelines:

```bash
SWAG_MCP_ENABLE_STRUCTURED_LOGGING=true
```

Structured logs include:
- Timestamp
- Log level
- Logger name
- Message
- Request context (when available)

## Error handling middleware

The middleware stack processes errors in order:

1. **Security error middleware** -- sanitizes error messages to prevent information disclosure
2. **MCP error enhancement** -- adds MCP-specific error context
3. **Error handling middleware** -- catches unhandled exceptions
4. **Retry middleware** -- retries transient failures (if enabled)

### Error sanitization

The `sanitize_error_message()` function strips:
- Jinja2 template expressions (`{{ }}`, `{% %}`)
- File system paths
- Python dunder methods
- Shell injection patterns
- Command substitution syntax

### Error codes

Structured error codes in `swag_mcp/utils/error_codes.py`:

| Error | Description |
| --- | --- |
| `SwagValidationError` | Input validation failure |
| `SwagOperationError` | Service operation failure |

### Retry behavior

When `SWAG_MCP_ENABLE_RETRY_MIDDLEWARE=true`:
- Failed operations retry up to `SWAG_MCP_MAX_RETRIES` times (default: 3)
- Uses the FastMCP `RetryMiddleware`
- Transient failures (timeouts, connection errors) are retried

## Slow operation warnings

Operations exceeding `SWAG_MCP_SLOW_OPERATION_THRESHOLD_MS` (default: 1000ms) are logged as warnings by the timing middleware:

```
WARNING  swag_mcp.middleware.timing: Slow operation: create took 2345ms
```

## Operational signals

swag-mcp does not ship an external alerting stack. Operators should monitor logs, Docker health state, and SWAG/nginx logs for these incident signals:

| Signal | Likely impact | First check |
| --- | --- | --- |
| Repeated `Tool execution failed due to an unexpected error` | MCP tool calls failing | Server logs around the request ID/action |
| `Create operation timed out`, `Edit operation timed out`, or `Update operation timed out` | File/validation/backend operation stuck or too slow | Filesystem/SSH availability and nginx validation |
| `Log retrieval operation timed out` | SWAG logs inaccessible or backend command slow | Log volume mounts, SSH command execution, SWAG container state |
| Slow operation warnings above the configured threshold | Degraded backend or upstream latency | Timing middleware logs and recent filesystem/backend changes |
| Docker health check unhealthy | MCP process or `/health` endpoint unavailable | `docker compose ps` and `docker compose logs --tail=200 swag-mcp` |
| Health-check action failures for known-good domains | Proxy, auth, DNS, TLS, or upstream outage | `endpoint_results`, nginx error logs, upstream container health |
| Backup cleanup removes unexpectedly high counts | Retention misconfiguration or backup naming issue | Backup list output and `SWAG_MCP_BACKUP_RETENTION_DAYS` |

Treat `/health` as a liveness signal only. It does not confirm proxy config write access, nginx syntax validation, SWAG reload status, remote SSH reachability, or generated route correctness.

## SWAG log access

The `logs` action reads SWAG container log files at paths defined in `DOCKER_LOG_PATHS`:

| Log type | Container path |
| --- | --- |
| `nginx-access` | `/var/log/nginx/access.log` |
| `nginx-error` | `/var/log/nginx/error.log` |
| `fail2ban` | `/var/log/fail2ban/fail2ban.log` |
| `letsencrypt` | `/var/log/letsencrypt/letsencrypt.log` |
| `renewal` | `/var/log/letsencrypt/renewal.log` |

Log retrieval uses efficient tail-based reading (subprocess `tail` for local, SSH `tail` command for remote).
