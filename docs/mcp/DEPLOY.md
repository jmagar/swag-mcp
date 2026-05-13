# Deployment Guide

Deployment patterns for swag-mcp. Choose the method that fits your environment.

## Local development

```bash
# Install dependencies
uv sync --dev

# Start server
just dev
# or: uv run python -m swag_mcp
```

Server runs at `http://localhost:8000` for local development. Set
`SWAG_MCP_TOKEN` or `SWAG_MCP_NO_AUTH=true` before starting. Uses local
filesystem access to proxy-confs.

## Docker Compose (recommended for production)

```bash
# Copy and configure environment
cp .env.example .env
chmod 600 .env
# Edit .env with your paths and SWAG_MCP_TOKEN

# Start
just up
# or: docker compose up -d
```

Compose publishes the MCP server on `127.0.0.1:49152` by default. Change
`SWAG_MCP_PORT` for a different host port. Change `SWAG_MCP_BIND_ADDRESS` only
when the service is protected by an authenticated proxy or trusted network.

### Volume mounts

The `docker-compose.yaml` mounts:

| Host path | Container path | Mode | Purpose |
| --- | --- | --- | --- |
| `${SWAG_MCP_LOG_HOST_PATH:-/tmp/swag-mcp/logs}` | `/app/.swag-mcp/logs` | rw | Server log files |
| `${SWAG_MCP_SSH_HOST_PATH:-./.cache/swag-mcp/ssh}` | `/home/swagmcp/.ssh` | ro | App-specific SSH config, private key, and known_hosts for remote access |
| `${SWAG_MCP_PROXY_CONFS_HOST_PATH:-/mnt/appdata/swag/nginx/proxy-confs}` | `/proxy-confs` | rw | SWAG proxy configuration files |
| `${SWAG_MCP_NGINX_INCLUDES_HOST_PATH:-./config/nginx}` | `/config/nginx` | ro | MCP nginx include snippets copied into SWAG config space |
| `${SWAG_MCP_FASTMCP_DATA_HOST_PATH:-/mnt/appdata/swag-mcp/data}` | `/home/swagmcp/.local/share/fastmcp` | rw | FastMCP runtime data |

`SWAG_MCP_LOG_DIRECTORY` remains the in-container path used by the application.
Use the `*_HOST_PATH` variables above for Compose bind mounts.

### Environment injection

Compose reads a required repo-local `.env` file. Keep secrets in that file and
keep `.env` out of version control. The only tracked environment template is
`.env.example`.

### Network

The container joins an external Docker network (`DOCKER_NETWORK`, default `swag-mcp`).
`just up` runs `just check-network` first and creates the network if it is
missing. If you run Compose directly, create it before starting:

```bash
docker network create swag-mcp
```

### Resource limits

- Memory: 1024 MB
- CPU: 1 core

### Health check

```bash
curl -f http://127.0.0.1:49152/health
```

Docker's built-in healthcheck runs every 30 seconds with a 10-second timeout and 3 retries.

### Port policy

The container listens on port 8000 internally. The published host port is
configured with `SWAG_MCP_BIND_ADDRESS` and `SWAG_MCP_PORT`; defaults are
`127.0.0.1:49152`. Keep production deployments on high-numbered, documented
ports and increment sequentially for additional services. Before deployment,
run `just preflight` or manually check the selected port with `ss -tuln` or
`lsof -iTCP:<port> -sTCP:LISTEN`.

## Docker standalone

```bash
docker build -t swag-mcp .
docker run -d \
  --name swag-mcp \
  -p 127.0.0.1:49152:8000 \
  -v /mnt/appdata/swag/nginx/proxy-confs:/proxy-confs:rw \
  -v ./.cache/swag-mcp/ssh:/home/swagmcp/.ssh:ro \
  --env-file .env \
  swag-mcp
```

## Behind SWAG reverse proxy

Place swag-mcp behind SWAG itself for production access:

```nginx
server {
    listen 443 ssl;
    server_name swag-mcp.example.com;

    include /config/nginx/ssl.conf;
    include /config/nginx/authelia-server.conf;

    location / {
        include /config/nginx/authelia-location.conf;
        include /config/nginx/proxy.conf;
        include /config/nginx/resolver.conf;
        proxy_pass http://swag-mcp:8000;
    }

    location /health {
        include /config/nginx/resolver.conf;
        proxy_pass http://swag-mcp:8000;
    }
}
```

Or generate this config using swag-mcp itself:

```python
swag(action="create",
     config_name="swag-mcp.subdomain.conf",
     server_name="swag-mcp.example.com",
     upstream_app="swag-mcp",
     upstream_port=8000,
     auth_method="authelia")
```

## Updating

```bash
# Pull or select the reviewed image
docker compose pull swag-mcp

# Stop the existing service, validate network/port, start the selected image
just redeploy

# Verify
just health
```

## Image pinning

Compose uses `SWAG_MCP_IMAGE` and defaults to
`ghcr.io/jmagar/swag-mcp:1.1.4`. Production deployments can pin this to an
immutable digest for stricter provenance, for example:

```env
SWAG_MCP_IMAGE=ghcr.io/jmagar/swag-mcp:1.1.4
# or after reviewing the published digest:
SWAG_MCP_IMAGE=ghcr.io/jmagar/swag-mcp@sha256:<digest>
```

The `Dockerfile` also accepts digest-pinned build arguments for base images:

```bash
docker build \
  --build-arg PYTHON_BASE_IMAGE='python@sha256:<digest>' \
  --build-arg UV_IMAGE='ghcr.io/astral-sh/uv@sha256:<digest>' \
  -t swag-mcp .
```

Note: Digest values must be obtained from the registry; placeholder or example
digests will not work. Record the reviewed digest in deployment notes once it
has been resolved from the registry.

## Rollback and restore

Container rollback uses a previously reviewed image:

```bash
just rollback ghcr.io/jmagar/swag-mcp:1.1.4
just health
```

Configuration restore uses backups created before edit, update, and remove
operations:

1. Stop additional config-changing actions and do not run backup cleanup.
2. List backups with `swag(action="backups", backup_action="list")`.
3. Identify the backup for the affected config and timestamp.
4. View the backup file through the filesystem backend or operator shell.
5. Restore its content with `swag(action="edit", config_name="...", new_content="...", create_backup=true)`.
6. Validate nginx syntax, reload SWAG, run `swag(action="health_check", domain="...")`, and inspect `nginx-error` logs.
7. Record the image, config, backup filename, port, timestamp, and outcome in `docs/deployment-log.md`.

## Incident runbook

For production-impacting failures:

1. Freeze changes: stop create/edit/update/remove actions and pause backup cleanup.
2. Capture state: `docker compose ps`, `docker compose logs --tail=200 swag-mcp`, `swag(action="logs", log_type="nginx-error", lines=200)`, and the affected config content.
3. Classify the failure: auth, generated config, SWAG reload, upstream outage, remote SSH/filesystem, MCP server, or dependency/image rollout.
4. Roll back the container image or restore the config backup if the last change caused the incident.
5. Verify the auth path, `/health`, `health_check` endpoint results, nginx syntax, SWAG reload, and upstream container/service health.
6. Document the timeline and commands in `docs/deployment-log.md` or incident notes using `HH:MM:SS | MM/DD/YYYY EST`.
