# Transport Methods Reference

## Overview

swag-mcp supports two transport methods for MCP communication:

| Transport | Protocol | Default | Auth |
| --- | --- | --- | --- |
| `streamable-http` | HTTP POST/SSE | yes | External (proxy layer) |
| `stdio` | stdin/stdout | no | Process-level |

## Streamable HTTP (default)

The server listens on `SWAG_MCP_HOST:SWAG_MCP_PORT` (default `127.0.0.1:8000`) using FastMCP's streamable-http transport.

```bash
# Default startup
uv run python -m swag_mcp
```

The server binds to `0.0.0.0` when running in Docker (overrides `127.0.0.1` and `localhost` to ensure container accessibility).

### Endpoints

| Path | Method | Purpose |
| --- | --- | --- |
| `/mcp` | POST | MCP tool calls (JSON-RPC) |
| `/mcp` | GET | SSE stream for server-initiated messages |
| `/health` | GET | Liveness probe (unauthenticated) |

### SSE streaming

The server uses Server-Sent Events for streaming responses. The nginx template (`mcp.conf`) configures:

- `proxy_buffering off` -- real-time streaming
- `proxy_cache off` -- no caching of dynamic responses
- `proxy_set_header Connection ''` -- SSE-compatible connection handling
- 24-hour timeouts for long-running AI operations

## Stdio

When published to PyPI as `swag-mcp`, the server can run in stdio mode via `uvx`:

```json
{
  "mcpServers": {
    "swag-mcp": {
      "command": "uvx",
      "args": ["swag-mcp"],
      "env": {
        "SWAG_MCP_PROXY_CONFS_URI": "admin@swag-server:/mnt/appdata/swag/nginx/proxy-confs"
      }
    }
  }
}
```

Stdio transport is useful for local development and when the MCP client runs on the same machine. Authentication is implicit (process-level access control).

## Choosing a transport

| Scenario | Transport | Reason |
| --- | --- | --- |
| Production Docker deployment | streamable-http | Network accessible, health checks |
| Claude Code plugin (local) | stdio | No network setup needed |
| Multiple clients | streamable-http | Shared server instance |
| Testing | streamable-http | Health endpoint, curl-friendly |
