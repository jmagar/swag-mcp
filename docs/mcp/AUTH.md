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

## OAuth 2.1 for MCP endpoints

Generated configs include OAuth 2.1 endpoints via `oauth.conf` for MCP-specific routes. The `/mcp` location uses `auth_request /_oauth_verify` which delegates to the mcp-oauth gateway container.

OAuth endpoints included in every generated config:

| Endpoint | RFC | Purpose |
| --- | --- | --- |
| `/_oauth_verify` | — | Internal auth_request target |
| `/.well-known/oauth-protected-resource` | RFC 9728 | Protected Resource Metadata |
| `/.well-known/oauth-authorization-server` | RFC 8414 | Authorization Server Metadata |
| `/.well-known/openid-configuration` | — | OpenID Connect Discovery |
| `/jwks` | — | JSON Web Key Set |
| `/register` | RFC 7591 | Dynamic Client Registration |
| `/authorize` | — | Authorization endpoint |
| `/token` | — | Token endpoint |
| `/revoke` | RFC 7009 | Token revocation |
| `/callback` | — | OAuth callback handler |
| `/success` | — | Post-auth success page |

The main application location (`/`) uses the standard auth method (Authelia, Authentik, etc.). The MCP location (`/mcp`) uses OAuth. This split allows traditional web apps to keep their existing auth while MCP clients use OAuth 2.1.

## Health endpoint

The `/health` endpoint is always unauthenticated in both the MCP server and generated proxy configs. It returns:

```json
{"status": "healthy", "service": "swag-mcp", "version": "1.0.1"}
```

This is required for Docker health checks and monitoring.
