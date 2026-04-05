# Web MCP Integration

Browser-accessible MCP endpoints for web dashboards, admin panels, and browser extensions.

## Endpoints

The swag-mcp server exposes the following HTTP endpoints:

| Path | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/mcp` | POST | External | MCP tool calls (JSON-RPC over HTTP) |
| `/mcp` | GET | External | SSE stream for server-initiated messages |
| `/health` | GET | None | Liveness probe |

## CORS configuration

The generated nginx configs include CORS headers via `mcp.conf`:

```nginx
add_header Access-Control-Allow-Origin $http_origin always;
add_header Access-Control-Allow-Methods "GET, POST, DELETE, OPTIONS" always;
add_header Access-Control-Allow-Headers "Authorization, Content-Type, Accept, MCP-Protocol-Version, Mcp-Session-Id, Last-Event-ID" always;
add_header Access-Control-Allow-Credentials "true" always;
add_header Access-Control-Max-Age "3600" always;
```

OPTIONS preflight requests return 204 with appropriate CORS headers.

## Origin validation

The generated template includes DNS rebinding protection:

```nginx
set $origin_valid 0;
if ($http_origin = "") { set $origin_valid 1; }
if ($http_origin = "https://$server_name") { set $origin_valid 1; }
if ($http_origin ~ "^https://(localhost|127\.0\.0\.1)(:[0-9]+)?$") { set $origin_valid 1; }
if ($http_origin ~ "^https://(.*\.)?anthropic\.com$") { set $origin_valid 1; }
if ($http_origin ~ "^https://(.*\.)?claude\.ai$") { set $origin_valid 1; }
```

Requests from invalid origins receive a 403 JSON response.

## Browser extension access

Browser extensions can connect to the MCP server if:
1. The origin matches the allowlist (or is empty for extension contexts)
2. The request includes valid OAuth credentials (via the proxy's `/_oauth_verify`)
3. The `Content-Type` header is set to `application/json`

## Session management

MCP sessions are identified by the `Mcp-Session-Id` header. The nginx config forwards this header to the upstream server:

```nginx
proxy_set_header Mcp-Session-Id $http_mcp_session_id;
proxy_set_header MCP-Protocol-Version $http_mcp_protocol_version;
```

Sessions at the `/session` and `/sessions` paths are routed to the MCP upstream with OAuth protection.
