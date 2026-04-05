# Setup Guide -- swag-mcp

Step-by-step instructions to get swag-mcp running locally, in Docker, or as a Claude Code plugin.

## Prerequisites

| Dependency | Version | Purpose |
| --- | --- | --- |
| Python | 3.11+ | Runtime |
| uv | latest | Package manager |
| Docker | 24+ | Container deployment |
| Docker Compose | v2+ | Orchestration |
| just | latest | Task runner |
| openssl | any | Token generation |
| SSH keys | — | Required for remote SWAG access mode |

## 1. Clone the repository

```bash
git clone https://github.com/jmagar/swag-mcp.git
cd swag-mcp
```

## 2. Install dependencies

```bash
uv sync --dev
```

Or use the setup recipe:

```bash
just setup
```

## 3. Configure environment

```bash
cp .env.example .env
chmod 600 .env
```

Edit `.env` and set the proxy-confs path based on your access mode:

### Local filesystem mode

```bash
# SWAG runs on the same machine or the directory is volume-mounted
SWAG_MCP_PROXY_CONFS_PATH=/mnt/appdata/swag/nginx/proxy-confs
```

### Remote SSH mode

```bash
# SWAG runs on a different machine
SWAG_MCP_PROXY_CONFS_URI=admin@swag-server:/mnt/appdata/swag/nginx/proxy-confs
```

SSH mode requires passwordless key-based authentication. The server reads `~/.ssh/config` for host aliases and key paths.

### Log path

```bash
# Point to the SWAG log directory (on the same host as proxy-confs)
SWAG_MCP_SWAG_LOG_BASE_PATH=/mnt/appdata/swag/log
```

See [CONFIG](CONFIG.md) for all environment variables.

## 4. Start locally

```bash
just dev
```

Or directly:

```bash
uv run python -m swag_mcp
```

The server starts on `http://localhost:8000` by default.

## 5. Start via Docker

```bash
just up
```

Or manually:

```bash
docker compose up -d
```

The Docker Compose configuration mounts `~/.ssh` as read-only for remote SSH access and reads environment from `~/.claude-homelab/.env`.

## 6. Verify

```bash
just health
```

Or:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status": "healthy", "service": "swag-mcp", "version": "1.0.1"}
```

## 7. Install as Claude Code plugin

```bash
/plugin marketplace add jmagar/claude-homelab
/plugin install swag-mcp @jmagar-claude-homelab
```

Configure the proxy-confs path when prompted, or set it in the plugin's userConfig.

## Troubleshooting

### "Connection refused" on health check

- Confirm the server is running: `docker compose ps` or check process list
- Verify `SWAG_MCP_PORT` matches the port you are curling
- If running in Docker, ensure the port is published in `docker-compose.yaml`

### "SSH connection failed" for remote access

- Verify SSH key-based auth works: `ssh swag-server ls /mnt/appdata/swag/nginx/proxy-confs/`
- Check the URI format: `[user@]host[:port]:/absolute/path`
- Ensure `asyncssh` is installed: `uv add asyncssh`
- In Docker, verify `~/.ssh` is mounted: check `docker compose.yaml` volumes

### "Template not found" at startup

- Confirm the `templates/` directory exists and contains `mcp.subdomain.conf.j2`
- If running in Docker, verify the template path is `/app/templates`
- For local dev, the default relative path `templates` resolves from the working directory

### "Environment variable not set" at startup

- Confirm `.env` exists and is readable: `ls -la .env`
- Confirm required variables are set: `grep SWAG_MCP_PROXY_CONFS .env`
- Check file permissions: `chmod 600 .env`

### Docker cannot reach SWAG server

- `localhost` in `SWAG_MCP_PROXY_CONFS_URI` does not resolve inside the container
- Use `host.docker.internal` or the machine's LAN IP
- For SSH mode, the container needs network access to the SWAG host on port 22 (or custom)

### Plugin not discovered by Claude Code

- Run `/plugin list` and confirm the plugin appears
- Check `~/.claude/plugins/cache/` for the plugin directory
- Re-run `/plugin marketplace add jmagar/claude-homelab` to refresh
