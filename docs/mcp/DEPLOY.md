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

Server runs at `http://localhost:8000`. Uses local filesystem access to proxy-confs.

## Docker Compose (recommended for production)

```bash
# Copy and configure environment
cp .env.example .env
chmod 600 .env
# Edit .env with your settings

# Start
just up
# or: docker compose up -d
```

### Volume mounts

The `docker-compose.yaml` mounts:

| Host path | Container path | Mode | Purpose |
| --- | --- | --- | --- |
| `${SWAG_MCP_LOG_DIRECTORY}` | `/app/.swag-mcp/logs` | rw | Server log files |
| `~/.ssh` | `/home/swagmcp/.ssh` | ro | SSH keys for remote access |

### Environment injection

Environment variables loaded from `~/.claude-homelab/.env` (optional, via `env_file`).

### Network

The container joins an external Docker network (`DOCKER_NETWORK`, default `swag-mcp`). Create it before starting:

```bash
docker network create swag-mcp
```

### Resource limits

- Memory: 1024 MB
- CPU: 1 core

### Health check

```bash
curl -f http://localhost:8000/health
```

Docker's built-in healthcheck runs every 30 seconds with a 10-second timeout and 3 retries.

## Docker standalone

```bash
docker build -t swag-mcp .
docker run -d \
  --name swag-mcp \
  -p 8000:8000 \
  -v /mnt/appdata/swag/nginx/proxy-confs:/proxy-confs:rw \
  -v ~/.ssh:/home/swagmcp/.ssh:ro \
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
# Pull latest
git pull

# Rebuild and restart
just build && just restart

# Verify
just health
```
