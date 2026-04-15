# Security Guardrails -- swag-mcp

Safety and security patterns enforced across the swag-mcp server.

## Credential management

Storage

- All credentials in `.env` with `chmod 600` permissions
- Never commit `.env` or any file containing secrets
- Use `.env.example` as a tracked template with placeholder values only
- Generate tokens with `openssl rand -hex 32`

Ignore files

`.gitignore` and `.dockerignore` must include:

```
.env
*.secret
credentials.*
*.pem
*.key
```

Hook enforcement

Session hooks verify security invariants:

| Hook | Trigger | Purpose |
| --- | --- | --- |
The `sync-uv.sh` hook keeps the repository lockfile and persistent Python environment in sync at session start.


Credential rotation

1. Generate new token: `openssl rand -hex 32`
2. Update `.env` with the new value
3. Restart the server: `just restart`
4. Update MCP client configuration with the new token
5. Verify: `just health`

## Destructive operations

The `remove` action always creates a backup before deleting a configuration file. The `edit` action creates a backup by default (controlled by `create_backup` parameter).

Backup retention is controlled by `SWAG_MCP_BACKUP_RETENTION_DAYS` (default: 30 days). The `backups` action with `backup_action="cleanup"` removes files older than the retention period.

## Docker security

Non-root execution

The container runs as non-root (UID/GID 1000 by default):

```dockerfile
RUN groupadd -g 1000 swagmcp && \
    useradd -u 1000 -g swagmcp -m -s /bin/bash swagmcp
USER swagmcp
```

Override with `PUID` and `PGID` environment variables in `docker-compose.yaml`.

No baked environment

The Docker image does not contain credentials at build time:

- No `ENV SWAG_MCP_TOKEN=...` in Dockerfile
- No `COPY .env` in Dockerfile
- Credentials injected at runtime via `env_file` in compose

Verify with:

```bash
docker inspect swag-mcp:latest | jq '.[0].Config.Env'
```

No sensitive values should appear in the output.

Resource limits

The Docker Compose file enforces resource limits:

```yaml
deploy:
  resources:
    limits:
      memory: 1024M
      cpus: "1"
```

## Template security

Jinja2 sandboxing

The template system uses a sandboxed Jinja2 environment to prevent Server-Side Template Injection (SSTI) attacks. All template variables are validated before rendering.

Input validation

- Config names must match `^[a-zA-Z0-9_.-]+\.(conf|sample)$`
- Upstream app names must match `^[a-zA-Z0-9_.\[\]:-]+$` (supports IPv6)
- Server names validated against RFC-compliant domain patterns
- Port numbers validated as integers in range 0-65535
- Path traversal blocked via regex validation

Error message sanitization

The security error middleware sanitizes all error messages to prevent information disclosure:

- Template injection payloads removed
- File system paths stripped
- Python dunder methods filtered
- Shell injection patterns blocked
- Internal stack traces not exposed to clients

## Network security

HTTPS in production

- All proxied services should use `https://` in production
- SWAG handles TLS termination via Let's Encrypt
- HTTP is acceptable only for local development

Authentication architecture

SWAG MCP does not enforce authentication internally. Security is handled at the proxy/network layer:

- Place the MCP server behind SWAG with Authelia or OAuth
- Use Docker network isolation to restrict access
- The `/health` endpoint is unauthenticated for container liveness probes

Health endpoint

- `/health` is unauthenticated -- required for Docker health checks
- Returns only status, service name, and version
- All MCP tool calls go through the FastMCP middleware stack

## Input handling

Parameter sanitization

- All user-supplied parameters validated via Pydantic models with `Field` constraints
- `max_length` enforced on string fields (config_name: 255, server_name: 253, upstream_app: 100)
- Regex patterns enforce valid characters for upstream addresses and config names
- Unicode normalization prevents encoding-based attacks

File operations

- Atomic writes via temp file + rename pattern
- Per-file locking prevents race conditions
- Backup created before destructive operations
- Transaction rollback on failure

## Logging

- Never log credentials, tokens, or API keys -- not even at DEBUG level
- Error messages sanitized before logging
- Log rotation configured: 10 MB max, configurable via `SWAG_MCP_LOG_FILE_MAX_BYTES`
- Payload logging disabled by default (`SWAG_MCP_LOG_PAYLOADS=false`)
