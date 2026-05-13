# Authentication Reference

## Overview

swag-mcp has two authentication boundaries:

1. **MCP server access** -- who can call the `swag` and `swag_help` tools
2. **Generated proxy configs** -- how the nginx configs authenticate end users

## MCP server authentication

swag-mcp enforces authentication for direct MCP server access when either
`SWAG_MCP_TOKEN` or `FASTMCP_SERVER_AUTH` is configured. If neither is set,
startup fails unless `SWAG_MCP_NO_AUTH=true` is explicitly configured.

For the default static bearer-token mode, generate and set a token:

```bash
SWAG_MCP_TOKEN="$(openssl rand -hex 32)"
```

Unauthenticated mode is reserved for loopback-only, stdio, or proxy-isolated
deployments. When using it, keep the Docker published port bound to
`127.0.0.1` or place the service behind an authenticated proxy.

Authentication can also be enforced at the network or proxy layer:

- Place the MCP server behind SWAG with Authelia, Authentik, or OAuth.
- Use Docker network isolation to restrict access to trusted clients.
- Use SSH tunneling for remote access.

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `SWAG_MCP_TOKEN` | — | Static bearer token enforced by FastMCP |
| `SWAG_MCP_NO_AUTH` | `false` | Explicitly allow startup without server auth |

### Why fail closed

The HTTP MCP transport can perform configuration writes, read generated configs,
and inspect logs. Direct network exposure without authentication is unsafe, so
the server requires a concrete auth decision at startup.

## Google OAuth support

The server supports optional Google OAuth via FastMCP's built-in GoogleProvider. Enable by setting:

```bash
FASTMCP_SERVER_AUTH=fastmcp.server.auth.providers.google.GoogleProvider
FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID=your-client-id
FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET=your-secret
FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL=https://swag.example.com/mcp
FASTMCP_SERVER_AUTH_RESOURCE_BASE_URL=https://swag.example.com
FASTMCP_SERVER_AUTH_GOOGLE_REQUIRED_SCOPES=openid,email
```

`FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL` is the public OAuth/MCP endpoint. If it
includes `/mcp`, set `FASTMCP_SERVER_AUTH_RESOURCE_BASE_URL` to the public
origin so protected-resource metadata advertises `https://swag.example.com/mcp`
instead of duplicating the mount path.

This is independent of the generated proxy config auth and is used for direct MCP server access without a proxy. `SWAG_MCP_TOKEN` can be configured at the same time; in that mode either the static bearer token or a valid OAuth token is accepted.

## Generated proxy config authentication

When creating nginx proxy configurations, the `auth_method` parameter controls how end users authenticate:

| Method | Include file | Description |
| --- | --- | --- |
| `none` | — | No authentication (public) |
| `basic` | `basic-server.conf` / `basic-location.conf` | HTTP Basic auth |
| `ldap` | `ldap-server.conf` / `ldap-location.conf` | LDAP authentication |
| `authelia` | `authelia-server.conf` / `authelia-location.conf` | Authelia SSO (default) |
| `authentik` | `authentik-server.conf` / `authentik-location.conf` | Authentik SSO |
| `tinyauth` | `tinyauth-server.conf` / `tinyauth-location.conf` | Tinyauth lightweight SSO |

The default is configured via `SWAG_MCP_DEFAULT_WEB_AUTH_METHOD` (default: `authelia`). This controls generated SWAG/nginx web endpoint auth, not MCP server authentication.

## OAuth 2.1 and Axon Standard for MCP Endpoints

Generated configs use the **Axon Standard**, which implements explicit `location =` (exact match) routing for all security-sensitive OAuth 2.1 and MCP discovery endpoints. This approach replaces the legacy dependency on global `oauth.conf` includes and catch-all regexes, ensuring higher reliability and performance.

The `/mcp` location must include proxy-level OAuth verification with `auth_request /_oauth_verify;`. The internal `/_oauth_verify` route forwards bearer-token validation to `SWAG_MCP_OAUTH_UPSTREAM`, while OAuth discovery and auth routes can proxy to the MCP service's own Authorization Server.

### Standardized Endpoints

Every generated config includes these explicit routes:

| Endpoint | RFC | Purpose | Cache Policy |
| --- | --- | --- | --- |
| `/.well-known/oauth-protected-resource` | RFC 9728 | Resource Metadata | 300s |
| `/mcp/.well-known/oauth-protected-resource` | RFC 9728 | Path-based Metadata | 300s |
| `/.well-known/oauth-authorization-server` | RFC 8414 | Server Metadata | 300s |
| `/.well-known/openid-configuration` | — | OIDC Discovery | 300s |
| `/jwks` | — | JSON Web Key Set | 3600s |
| `/register` | RFC 7591 | Dynamic Registration | No-cache |
| `/authorize` | — | Authorization endpoint | No-cache |
| `/token` | — | Token endpoint | No-cache |
| `/revoke` | RFC 7009 | Token revocation | No-cache |

### Security Features

1. **DNS Rebinding Protection**: All configurations include origin validation against authorized domains (including `claude.ai` and `anthropic.com`).
2. **Standardized Headers**: Consistent `X-MCP-Version` and `Referrer-Policy` headers across the fleet.
3. **Proxy OAuth Gate**: `/mcp`, `/session`, and `/sessions` requests are checked by nginx via `auth_request /_oauth_verify` before reaching the MCP upstream.
4. **Internal AuthLayer**: The MCP service can still enforce its own AuthLayer after proxy verification for fine-grained, per-service permissions.

The main application location (`/`) still uses the standard auth method (Authelia, Authentik, etc.), while MCP endpoints use proxy-level OAuth verification plus any service-level AuthLayer.

## Health endpoint

The `/health` endpoint is always unauthenticated in both the MCP server and generated proxy configs. It returns:

```json
{"status": "healthy", "service": "swag-mcp", "version": "1.1.6"}
```

This is required for Docker health checks and monitoring.
