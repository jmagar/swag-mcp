# Upstream Service Integration -- swag-mcp

How swag-mcp integrates with SWAG (Secure Web Application Gateway).

## What is SWAG

SWAG is a LinuxServer.io Docker container that provides:
- **Nginx reverse proxy** with automatic configuration management
- **Let's Encrypt SSL** with automatic certificate renewal
- **Authelia/Authentik SSO** integration for single sign-on
- **Fail2ban** intrusion prevention
- **ModSecurity** WAF (optional)

SWAG stores reverse proxy configurations as `.conf` files in the `proxy-confs` directory (typically `/config/nginx/proxy-confs/` inside the container).

## How swag-mcp interacts with SWAG

swag-mcp manages SWAG's proxy configuration files directly on the filesystem. It does not use an API -- SWAG has no REST API for configuration management.

### Operations

| Operation | Filesystem action |
| --- | --- |
| `list` | `glob(proxy_confs_path, "*.conf")` + `glob(proxy_confs_path, "*.sample")` |
| `create` | Render Jinja2 template, write `.conf` file |
| `view` | Read `.conf` file contents |
| `edit` | Write new content to `.conf` file (with backup) |
| `update` | Read, regex-replace field, write (with backup) |
| `remove` | Delete `.conf` file (with backup) |
| `logs` | Read log files from SWAG log directory |
| `backups` | List/cleanup `.backup.*` files in proxy-confs |
| `health_check` | HTTP GET to the `server_name` domain |

### File patterns

| Pattern | Description |
| --- | --- |
| `*.subdomain.conf` | Active subdomain proxy configurations |
| `*.subdomain.conf.sample` | SWAG-provided sample configurations |
| `*.backup.*` | Backup files created by swag-mcp before edits/removes |

### Nginx reload

swag-mcp creates/modifies configuration files but does not reload nginx. SWAG automatically detects file changes and reloads nginx on a schedule (typically every few minutes). For immediate effect, restart the SWAG container:

```bash
docker restart swag
```

## Configuration file format

Generated configs follow SWAG conventions:

```nginx
server {
    listen 443 ssl;
    listen [::]:443 ssl;

    server_name service.example.com;

    include /config/nginx/ssl.conf;
    client_max_body_size 0;

    set $upstream_app "service-container";
    set $upstream_port "8080";
    set $upstream_proto "http";

    # Auth method include (server level)
    include /config/nginx/authelia-server.conf;

    # OAuth 2.1 endpoints
    include /config/nginx/oauth.conf;

    # MCP endpoint with OAuth protection
    location /mcp {
        auth_request /_oauth_verify;
        include /config/nginx/proxy.conf;
        include /config/nginx/mcp.conf;
        proxy_pass $mcp_upstream_proto://$mcp_upstream_app:$mcp_upstream_port;
    }

    # Health check (no auth)
    location /health {
        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    # Main application
    location / {
        include /config/nginx/authelia-location.conf;
        include /config/nginx/proxy.conf;
        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }
}
```

## Authentication methods

SWAG supports multiple auth backends via include files:

| Method | Server include | Location include |
| --- | --- | --- |
| Authelia | `authelia-server.conf` | `authelia-location.conf` |
| Authentik | `authentik-server.conf` | `authentik-location.conf` |
| LDAP | `ldap-server.conf` | `ldap-location.conf` |
| Basic | `basic-server.conf` | `basic-location.conf` |
| Tinyauth | `tinyauth-server.conf` | `tinyauth-location.conf` |
| None | (omitted) | (omitted) |

The `auth_method` parameter in the `create` action determines which include files are added to the generated config.

## Nginx include files

The template references SWAG-provided nginx includes:

| Include | Purpose |
| --- | --- |
| `ssl.conf` | SSL/TLS configuration (ciphers, protocols, certificates) |
| `resolver.conf` | DNS resolver for dynamic upstream resolution |
| `proxy.conf` | Standard proxy headers (Host, X-Real-IP, X-Forwarded-*) |
| `mcp.conf` | MCP-specific overrides (buffering off, SSE, CORS, timeouts) |
| `oauth.conf` | OAuth 2.1 endpoints (token verification, discovery, JWKS) |

`mcp.conf` and `oauth.conf` are shipped with swag-mcp in `config/nginx/` and must be copied to SWAG's nginx configuration directory.

## Split routing

When `mcp_upstream_app` is specified during `create`, the config routes traffic to two different backends:

| Path | Backend | Auth |
| --- | --- | --- |
| `/` | `upstream_app:upstream_port` | Authelia/Authentik/etc. |
| `/mcp` | `mcp_upstream_app:mcp_upstream_port` | OAuth 2.1 |
| `/session*` | `mcp_upstream_app:mcp_upstream_port` | OAuth 2.1 |
| `/health` | `upstream_app:upstream_port` | None |

This enables running an MCP service on a separate machine (e.g., GPU server) while the main web application runs on a different host.

## SWAG container paths

| Container path | Purpose |
| --- | --- |
| `/config/nginx/proxy-confs/` | Proxy configuration files (managed by swag-mcp) |
| `/config/nginx/ssl.conf` | SSL configuration |
| `/config/nginx/resolver.conf` | DNS resolver |
| `/config/nginx/proxy.conf` | Standard proxy headers |
| `/var/log/nginx/access.log` | Nginx access log |
| `/var/log/nginx/error.log` | Nginx error log |
| `/var/log/fail2ban/fail2ban.log` | Fail2ban log |
| `/var/log/letsencrypt/letsencrypt.log` | Let's Encrypt log |
| `/var/log/letsencrypt/renewal.log` | Certificate renewal log |
