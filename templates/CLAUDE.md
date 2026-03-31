# SWAG MCP Templates - Claude Memory Reference

This directory contains the single unified Jinja2 template for generating nginx reverse proxy configurations with MCP, OAuth, and Authelia support.

## Directory Purpose

The `templates/` directory provides a single secure Jinja2 template for all proxy configuration generation. The previous multi-template system (subdomain, subfolder, mcp-subdomain, mcp-subfolder) has been replaced with one unified template.

## Template File

### `mcp.subdomain.conf.j2` - Unified Subdomain Template

The only template file. All configurations are generated from this single template, selected via `build_template_filename("subdomain")` which returns `"mcp.subdomain.conf.j2"`.

**Architecture:**
- Includes `oauth.conf` at server level for OAuth 2.1 endpoints
- `/` location uses Authelia authentication and `proxy.conf`
- `/mcp` location uses OAuth (`auth_request /_oauth_verify`), then includes `proxy.conf` and `mcp.conf`
- `/health` location has no authentication

**No subfolder support** - config types have been simplified to just "subdomain".

## Nginx Includes

Two nginx include files live in `nginx/` (not in this directory):

### `nginx/mcp.conf` - Location-Level MCP Overrides
Included inside the `/mcp` location block after `proxy.conf`:

```nginx
# Zero-buffering for real-time streaming
proxy_buffering off;
proxy_cache off;
proxy_request_buffering off;

# Extended timeouts for long-running MCP operations
proxy_connect_timeout 60s;
proxy_send_timeout 24h;
proxy_read_timeout 24h;

# SSE/streaming headers
proxy_set_header Connection '';
proxy_http_version 1.1;
proxy_set_header Cache-Control 'no-cache, no-store, must-revalidate';

# Chunked transfer encoding
chunked_transfer_encoding on;
```

### `nginx/oauth.conf` - Server-Level OAuth Endpoints
Included at the server block level, provides OAuth 2.1 verification:

```nginx
# OAuth verification endpoint
location = /_oauth_verify {
    # Internal-only endpoint for auth_request
    internal;
    # ... OAuth verification logic
}

# Additional OAuth callback routes
# ... token exchange, authorization endpoints
```

## Template Variables

### Required Variables
```python
template_vars = {
    'service_name': 'jellyfin',           # Service identifier
    'server_name': 'media.example.com',   # Domain name
    'upstream_app': 'jellyfin',           # Container/host name
    'upstream_port': 8096,                # Port number
    'upstream_proto': 'http',             # http or https
    'auth_method': 'authelia',            # Authentication for / location
    'enable_quic': False                  # QUIC/HTTP3 support
}
```

### Optional MCP Upstream Variables
For remote MCP servers (defaults to main upstream if not specified):

```python
mcp_vars = {
    'mcp_upstream_app': 'ai-server',      # MCP service host
    'mcp_upstream_port': 8080,            # MCP service port
    'mcp_upstream_proto': 'http',         # MCP service protocol
}
```

### Authentication Methods
- **`authelia`**: Authelia middleware for `/` location (default)
- **`authentik`**: Authentik proxy for `/` location
- **`ldap`**: LDAP authentication for `/` location
- **`tinyauth`**: TinyAuth lightweight auth for `/` location
- **`none`**: No authentication for `/` location

The `/mcp` location always uses OAuth via `auth_request /_oauth_verify`, regardless of the auth_method setting.

## Configuration Type

Only one config type is supported:

- **`subdomain`**: Uses `mcp.subdomain.conf.j2` for `service.example.com`

The old types (`subfolder`, `mcp-subdomain`, `mcp-subfolder`) are no longer available.

## Security Features

### Template Sandboxing
Templates run in a secure Jinja2 environment:

```python
env = Environment(
    loader=FileSystemLoader(template_path),
    autoescape=True,
    undefined=StrictUndefined
)
```

### Authentication Layers
- `/` - Authelia (or configured auth_method)
- `/mcp` - OAuth 2.1 via `auth_request /_oauth_verify`
- `/health` - No authentication (monitoring bypass)

### SSTI Prevention
- Input validation on all variables before templating
- Character whitelist for service names
- No user-controlled template paths
- Sandboxed execution environment

## Deprecated Functions

`render_mcp_location_block()` is deprecated and raises `NotImplementedError`. The MCP location block is now part of the unified template.

## Template Usage in Code

```python
from jinja2 import Environment, FileSystemLoader

env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=True,
    undefined=StrictUndefined
)

# Only one template exists
template = env.get_template('mcp.subdomain.conf.j2')
config_content = template.render(
    service_name='jellyfin',
    server_name='media.example.com',
    upstream_app='jellyfin',
    upstream_port=8096,
    upstream_proto='http',
    auth_method='authelia',
    enable_quic=False
)
```

## Development Commands

### Template Testing
```bash
# Test template rendering
python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'))
template = env.get_template('mcp.subdomain.conf.j2')
print(template.render(
    service_name='test',
    server_name='test.example.com',
    upstream_app='test-app',
    upstream_port=8080,
    upstream_proto='http',
    auth_method='none',
    enable_quic=False
))
"

# Validate nginx syntax
nginx -t -c /path/to/generated/config.conf
```

## Important Notes

### Template Security
- Input validation on all variables before rendering
- Sandboxed environment with no access to dangerous Python functions
- Template path is hardcoded, not user-controlled
- Automatic HTML escaping enabled

### MCP-Specific Features
- Zero buffering on `/mcp` enables real-time streaming
- Extended timeouts support long-running AI operations
- SSE headers configured for server-sent events
- OAuth protects MCP endpoints independently from main service auth

### Performance Considerations
- Template compiled once and cached by Jinja2
- Single template simplifies selection logic
- QUIC/HTTP3 support available when enabled

### Common Issues
- Template path must be relative to working directory
- Undefined variables cause template errors (StrictUndefined)
- Generated configs must pass `nginx -t` validation
- `nginx/mcp.conf` and `nginx/oauth.conf` must be accessible to SWAG
