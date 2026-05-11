# Authentication Reference

## Overview

swag-mcp has two authentication boundaries:

1. **MCP server access** -- who can call the `swag` and `swag_help` tools
2. **Generated proxy configs** -- how the nginx configs authenticate end users

## MCP server authentication

swag-mcp does not enforce bearer token authentication internally. The server logs authentication-related configuration at startup but does not reject unauthenticated requests.

Authentication must be enforced at the network or proxy layer:

- Place the MCP server behind SWAG with Authelia, Authentik, or OAuth
- Use Docker network isolation to restrict access to trusted clients
- Use SSH tunneling for remote access

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `SWAG_MCP_TOKEN` | — | Bearer token (logged at startup, not enforced) |
| `SWAG_MCP_NO_AUTH` | `false` | When `true`, suppresses the "no token" warning |

### Why external auth

MCP servers sit behind reverse proxies in production. Implementing auth at both the proxy and application layers creates maintenance overhead and token synchronization issues. The proxy layer (SWAG, Traefik, Caddy) is the canonical auth enforcement point.

## Google OAuth support

The server supports optional Google OAuth via FastMCP's built-in GoogleProvider. Enable by setting:

```bash
FASTMCP_SERVER_AUTH=fastmcp.server.auth.providers.google.GoogleProvider
FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID=your-client-id
FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET=your-secret
FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL=https://swag.example.com
FASTMCP_SERVER_AUTH_GOOGLE_REQUIRED_SCOPES=openid,email
```

This is independent of the generated proxy config auth and is used for direct MCP server access without a proxy.

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

The default is configured via `SWAG_MCP_DEFAULT_AUTH_METHOD` (default: `authelia`).

## OAuth 2.1 and Axon Standard for MCP Endpoints

Generated configs use the **Axon Standard**, which implements explicit `location =` (exact match) routing for all security-sensitive OAuth 2.1 and MCP discovery endpoints. This approach replaces the legacy dependency on global `oauth.conf` includes and catch-all regexes, ensuring higher reliability and performance.

The `/mcp` location block and all related auth routes proxy directly to the service's own Authorization Server (typically integrated into the MCP engine itself).

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
3. **Internal AuthLayer**: Authentication is enforced by the service's internal AuthLayer rather than a global gateway, allowing for fine-grained, per-service permission management.

The main application location (`/`) still uses the standard auth method (Authelia, Authentik, etc.), while the MCP engine handles its own security handshake.

## Health endpoint

The `/health` endpoint is always unauthenticated in both the MCP server and generated proxy configs. It returns:

```json
{"status": "healthy", "service": "swag-mcp", "version": "1.0.1"}
```

This is required for Docker health checks and monitoring.
