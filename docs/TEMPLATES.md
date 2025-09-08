# SWAG MCP Template Documentation

> **Comprehensive guide to SWAG MCP templates for reverse proxy configuration generation**

This document provides detailed documentation for the SWAG MCP template system, including MCP-specific requirements, OAuth integration, and all necessary headers for proper functionality.

## Table of Contents

1. [Template System Overview](#template-system-overview)
2. [Template Types](#template-types)
3. [MCP-Specific Requirements](#mcp-specific-requirements)
4. [OAuth Integration](#oauth-integration)
5. [Header Documentation](#header-documentation)
6. [Template Variables Reference](#template-variables-reference)
7. [Generated Configuration Examples](#generated-configuration-examples)
8. [Troubleshooting](#troubleshooting)

---

## Template System Overview

The SWAG MCP template system uses **Jinja2** templates to generate nginx reverse proxy configurations that align with real SWAG patterns. Our templates are designed to match the exact format and functionality of manually created SWAG configurations.

### Key Design Principles

- **Real SWAG Alignment**: Templates generate configurations identical to manual SWAG setups
- **MCP Optimization**: Special templates for Model Context Protocol servers with streaming support
- **OAuth Integration**: Built-in OAuth endpoint support for AI service authentication
- **Security First**: Proper header configuration and authentication integration
- **Conditional Features**: Support for QUIC, different auth methods, and deployment scenarios

### Template Architecture

```text
templates/
├── subdomain.conf.j2          # Standard subdomain reverse proxy
├── subfolder.conf.j2          # Standard path-based routing
├── mcp-subdomain.conf.j2      # MCP-optimized subdomain with OAuth
├── mcp-subfolder.conf.j2      # MCP-optimized path-based with OAuth
└── mcp_location_block.j2      # Reusable MCP location blocks
```

---

## Template Types

### 1. Standard Templates

#### `subdomain.conf.j2`
**Purpose**: Traditional web application reverse proxy
**Pattern**: `app.domain.com` → `container:port`
**Use Cases**: Web apps, dashboards, standard services

**Key Features**:
- Clean subdomain routing
- Authelia integration by default
- Health check endpoint
- Optional QUIC support
- No explicit security headers (matches SWAG defaults)

#### `subfolder.conf.j2`
**Purpose**: Path-based application routing
**Pattern**: `domain.com/app` → `container:port`
**Use Cases**: Multiple services on single domain

**Key Features**:
- URL rewriting for subfolder routing
- X-Forwarded-Prefix headers
- Dedicated health check paths
- Security headers included

### 2. MCP Templates

#### `mcp-subdomain.conf.j2`
**Purpose**: Model Context Protocol server with OAuth
**Pattern**: `ai.domain.com` → MCP server with streaming + OAuth
**Use Cases**: AI services, Claude Code MCP servers, streaming APIs

**Key Features**:
- **Streamable-HTTP optimizations**
- **OAuth 2.0 endpoint support**
- **24-hour timeouts for AI tasks**
- **Zero-buffering configuration**
- **Server-Sent Events (SSE) support**
- **MCP-specific headers**

#### `mcp-subfolder.conf.j2`
**Purpose**: Path-based MCP server deployment
**Pattern**: `domain.com/ai-service` → MCP server
**Use Cases**: Multiple MCP servers on single domain

**Key Features**:
- All MCP optimizations from subdomain template
- URL rewriting for subfolder → root mapping
- OAuth endpoints with path prefixes
- Proper X-Forwarded-Prefix handling

#### `mcp_location_block.j2`
**Purpose**: Reusable MCP location blocks
**Use Cases**: Adding MCP endpoints to existing configurations

**Key Features**:
- Modular MCP location blocks
- Can be included in any server configuration
- All OAuth endpoints included
- Consistent header configuration

---

## MCP-Specific Requirements

### What is MCP (Model Context Protocol)?

Model Context Protocol enables AI assistants like Claude to interact with external tools and services. MCP servers require special nginx configurations for optimal performance.

### MCP Server Characteristics

1. **Long-running connections** (up to 24 hours)
2. **Server-Sent Events (SSE)** for real-time streaming
3. **JSON-RPC over HTTP** communication
4. **Session management** via headers
5. **OAuth authentication** instead of traditional auth

### Critical MCP nginx Settings

```nginx
# Zero-buffering for real-time streaming
proxy_http_version 1.1;
proxy_buffering off;
proxy_cache off;
proxy_request_buffering off;
proxy_max_temp_file_size 0;
chunked_transfer_encoding off;

# Connection management for SSE
proxy_set_header Connection '';

# Extended timeouts for AI processing
proxy_connect_timeout 60s;
proxy_send_timeout 86400s;    # 24 hours
proxy_read_timeout 86400s;    # 24 hours
```

### Why These Settings Matter

- **`proxy_buffering off`**: Enables real-time streaming responses
- **`proxy_cache off`**: Prevents caching of dynamic AI responses
- **`Connection ''`**: Essential for proper SSE connection handling
- **24-hour timeouts**: AI tasks can take hours to complete
- **`chunked_transfer_encoding off`**: Ensures proper streaming

---

## OAuth Integration

### Why OAuth for MCP Services?

MCP servers often integrate with external AI services (like Claude, ChatGPT) that use OAuth 2.0 for authentication. Traditional auth systems like Authelia interfere with OAuth flows.

### OAuth Endpoint Requirements

All MCP templates include these OAuth 2.0 endpoints:

```nginx
# OAuth Discovery (RFC 8414)
location = /.well-known/oauth-authorization-server { ... }
location = /.well-known/openid-configuration { ... }

# OAuth 2.0 Core Endpoints (RFC 6749)
location = /register { ... }      # Client registration
location = /authorize { ... }     # Authorization endpoint
location = /token { ... }         # Token endpoint
location = /revoke { ... }        # Token revocation

# OAuth Callbacks
location /auth/ { ... }           # OAuth callback handler
```

### OAuth vs Authelia

| Authentication | Use Case | Configuration |
|---------------|----------|---------------|
| **OAuth 2.0** | MCP/AI services | No Authelia, OAuth endpoints required |
| **Authelia** | Standard web apps | Include authelia-server.conf |
| **None** | Public services | No authentication (not recommended) |

### OAuth Comments in Templates

Our templates include explicit comments about OAuth authentication:

```nginx
# Authelia disabled for OAuth - remove these lines:
# include /config/nginx/authelia-server.conf;

# OAuth endpoints (no Authelia here)
location = /register { ... }
```

---

## Header Documentation

### Standard Reverse Proxy Headers

Required for all reverse proxy configurations:

```nginx
proxy_set_header Host $host;                    # Original hostname
proxy_set_header X-Real-IP $remote_addr;       # Client IP address
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;  # IP chain
proxy_set_header X-Forwarded-Proto $scheme;    # Original protocol (https)
proxy_set_header X-Forwarded-Host $host;       # Original host header
proxy_set_header X-Forwarded-Port $server_port; # Original port
```

### MCP-Specific Headers

Additional headers required for MCP protocol:

```nginx
# Content negotiation for MCP protocol
proxy_set_header Accept $http_accept;

# Session management for persistent MCP connections
proxy_set_header Mcp-Session-Id $http_mcp_session_id;
```

### Subfolder-Specific Headers

Required for path-based routing:

```nginx
# Path prefix information for applications
proxy_set_header X-Forwarded-Prefix /service-name;
proxy_set_header X-Script-Name /service-name;

# Full URI for complex routing decisions
proxy_set_header X-Forwarded-Uri $request_uri;
```

### Why Each Header Matters

| Header | Purpose | Required For |
|--------|---------|--------------|
| `Host` | Application knows its hostname | All services |
| `X-Real-IP` | Rate limiting, logging | Security, analytics |
| `X-Forwarded-For` | IP chain tracking | Security, compliance |
| `X-Forwarded-Proto` | HTTPS detection | SSL redirects, security |
| `Accept` | Content negotiation | MCP protocol communication |
| `Mcp-Session-Id` | Session persistence | Multi-request MCP operations |
| `X-Forwarded-Prefix` | Path awareness | Subfolder deployments |

---

## Template Variables Reference

### Core Variables

| Variable | Type | Required | Description | Example |
|----------|------|----------|-------------|---------|
| `service_name` | string | Yes | Service identifier | `"jellyfin"` |
| `server_name` | string | Yes | Domain name | `"media.example.com"` |
| `upstream_app` | string | Yes | Container/IP | `"jellyfin"` or `"192.168.1.100"` |
| `upstream_port` | integer | Yes | Port number | `8096` |
| `upstream_proto` | string | Yes | Protocol | `"http"` or `"https"` |

### Authentication Variables

| Variable | Type | Default | Description | Options |
|----------|------|---------|-------------|---------|
| `auth_method` | string | `"authelia"` | Authentication system | `"authelia"`, `"authentik"`, `"ldap"`, `"basic"`, `"none"` |

### Feature Variables

| Variable | Type | Default | Description | Impact |
|----------|------|---------|-------------|---------|
| `enable_quic` | boolean | `false` | Enable HTTP/3 QUIC | Adds QUIC listeners and Alt-Svc headers |
| `mcp_enabled` | boolean | `false` | Enable MCP optimizations | Selects MCP template variant |

### Variable Usage Examples

```python
# Standard web application
{
    "service_name": "plex",
    "server_name": "plex.mydomain.com",
    "upstream_app": "plex",
    "upstream_port": 32400,
    "upstream_proto": "http",
    "auth_method": "authelia",
    "enable_quic": False
}

# MCP service with OAuth
{
    "service_name": "claude-mcp",
    "server_name": "ai.mydomain.com",
    "upstream_app": "claude-mcp-server",
    "upstream_port": 8000,
    "upstream_proto": "http",
    "auth_method": "none",  # OAuth used instead
    "mcp_enabled": True,
    "enable_quic": True
}
```

---

## Generated Configuration Examples

### Example 1: Standard Subdomain (Plex)

**Input Variables**:
```python
{
    "service_name": "plex",
    "server_name": "plex.example.com",
    "upstream_app": "plex",
    "upstream_port": 32400,
    "upstream_proto": "http",
    "auth_method": "authelia"
}
```

**Generated Configuration** (`plex.subdomain.conf`):
```nginx
## Version 2025/08/18
# Generated by SWAG MCP Server
# Service: plex
# Domain: plex.example.com
# Upstream: http://plex:32400

server {
    listen 443 ssl;
    listen [::]:443 ssl;

    server_name plex.example.com;

    include /config/nginx/ssl.conf;
    client_max_body_size 0;

    # Upstream target
    set $upstream_app "plex";
    set $upstream_port "32400";
    set $upstream_proto "http";

    # enable for authelia (requires authelia-location.conf in the location block)
    include /config/nginx/authelia-server.conf;

    location / {
        # enable for authelia (requires authelia-server.conf in the server block)
        include /config/nginx/authelia-location.conf;

        include /config/nginx/proxy.conf;
        include /config/nginx/resolver.conf;
        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    location /health {
        include /config/nginx/resolver.conf;

        # Disable buffering for health checks
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_cache off;
        proxy_request_buffering off;

        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }
}
```

### Example 2: MCP Subdomain with OAuth

**Input Variables**:
```python
{
    "service_name": "claude-mcp",
    "server_name": "ai.example.com",
    "upstream_app": "claude-mcp-server",
    "upstream_port": 8000,
    "upstream_proto": "http",
    "auth_method": "none",  # OAuth authentication
    "mcp_enabled": True
}
```

**Generated Configuration** (`claude-mcp.subdomain.conf`):
```nginx
## Version 2025/08/20
# Generated by SWAG MCP Server
# MCP Streamable-HTTP Reverse Proxy Configuration
# Service: claude-mcp
# Domain: ai.example.com
# Upstream: http://claude-mcp-server:8000

server {
    listen 443 ssl;
    listen [::]:443 ssl;

    server_name ai.example.com;

    include /config/nginx/ssl.conf;
    client_max_body_size 0;

    # Authelia disabled for OAuth - remove these lines:
    # include /config/nginx/authelia-server.conf;

    # Upstream target
    set $upstream_app "claude-mcp-server";
    set $upstream_port "8000";
    set $upstream_proto "http";

    # Main MCP endpoint for streamable-http transport
    location /mcp {
        # Authelia disabled for OAuth - remove this line:
        # include /config/nginx/authelia-location.conf;
        include /config/nginx/resolver.conf;

        # Essential settings for MCP streamable-http
        proxy_http_version 1.1;
        proxy_buffering off;
        proxy_cache off;
        proxy_request_buffering off;
        proxy_max_temp_file_size 0;
        chunked_transfer_encoding off;

        # Connection management for SSE/streaming
        proxy_set_header Connection '';

        # Standard reverse proxy headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;

        # MCP-specific headers
        proxy_set_header Accept $http_accept;
        proxy_set_header Mcp-Session-Id $http_mcp_session_id;

        # Timeouts for persistent connections
        proxy_connect_timeout 60s;
        proxy_send_timeout 86400s;
        proxy_read_timeout 86400s;

        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    # OAuth discovery endpoints
    location = /.well-known/oauth-authorization-server {
        include /config/nginx/resolver.conf;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    location = /.well-known/openid-configuration {
        include /config/nginx/resolver.conf;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    # OAuth endpoints (no Authelia here)
    location = /register {
        include /config/nginx/resolver.conf;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    location = /authorize {
        include /config/nginx/resolver.conf;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    location = /token {
        include /config/nginx/resolver.conf;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    location = /revoke {
        include /config/nginx/resolver.conf;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    # Google → server callback (and any /auth/* paths)
    location /auth/ {
        include /config/nginx/resolver.conf;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    # Health check endpoint (no auth required)
    location /health {
        include /config/nginx/resolver.conf;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }
}
```

---

## Troubleshooting

### Common Issues

#### 1. MCP Connection Timeouts
**Symptoms**: MCP requests failing after 60 seconds
**Cause**: Default nginx timeouts too short for AI processing
**Solution**: Verify template includes extended timeouts:
```nginx
proxy_send_timeout 86400s;    # 24 hours
proxy_read_timeout 86400s;    # 24 hours
```

#### 2. Streaming Not Working
**Symptoms**: Delayed or chunked responses instead of real-time streaming
**Cause**: Buffering enabled in nginx configuration
**Solution**: Verify zero-buffering settings:
```nginx
proxy_buffering off;
proxy_cache off;
proxy_request_buffering off;
proxy_max_temp_file_size 0;
```

#### 3. OAuth Authentication Failures
**Symptoms**: OAuth redirects not working, authentication loops
**Cause**: Authelia interfering with OAuth flow
**Solution**: Ensure no Authelia includes in OAuth endpoints:
```nginx
# These should NOT have authelia-location.conf:
location = /authorize { ... }  # No auth include here
location = /token { ... }      # No auth include here
```

#### 4. Connection Header Issues
**Symptoms**: SSE connections dropping immediately
**Cause**: Incorrect Connection header syntax
**Solution**: Use single quotes for empty Connection header:
```nginx
# Correct
proxy_set_header Connection '';

# Incorrect
proxy_set_header Connection "";
```

#### 5. Missing MCP Headers
**Symptoms**: MCP protocol errors, session not maintained
**Cause**: Missing MCP-specific headers
**Solution**: Verify MCP headers are included:
```nginx
proxy_set_header Accept $http_accept;
proxy_set_header Mcp-Session-Id $http_mcp_session_id;
```

### Template Selection Guide

| Use Case | Template | Auth Method | Key Features |
|----------|----------|-------------|--------------|
| **Web Dashboard** | `subdomain.conf.j2` | `authelia` | Standard reverse proxy |
| **Multiple Web Apps** | `subfolder.conf.j2` | `authelia` | Path-based routing |
| **AI/MCP Service** | `mcp-subdomain.conf.j2` | `none` | OAuth + streaming |
| **Multiple AI Services** | `mcp-subfolder.conf.j2` | `none` | Path-based + OAuth |
| **Add MCP to Existing** | Include `mcp_location_block.j2` | Mixed | Modular MCP blocks |

### Validation Checklist

Before deploying MCP configurations, verify:

- [ ] **Extended timeouts**: 86400s (24 hours) for send/read
- [ ] **Zero buffering**: All buffering disabled
- [ ] **Connection header**: Single quotes, empty string
- [ ] **MCP headers**: Accept and Mcp-Session-Id included
- [ ] **OAuth endpoints**: All 7 endpoints present
- [ ] **No Authelia**: OAuth endpoints have no auth includes
- [ ] **Upstream variables**: Declared once at server level
- [ ] **SSL config**: Includes ssl.conf
- [ ] **Resolver config**: Included in all locations

### Performance Optimization

For high-traffic MCP deployments:

1. **Enable QUIC/HTTP3**:
   ```python
   "enable_quic": True
   ```

2. **Optimize worker connections**:
   ```nginx
   worker_connections 8192;
   ```

3. **Increase client timeouts**:
   ```nginx
   client_max_body_size 0;
   client_body_timeout 86400s;
   ```

4. **Monitor connection limits**:
   ```bash
   # Check active connections
   netstat -an | grep :443 | wc -l
   ```

---

## Advanced Usage

### Custom Template Modifications

To modify templates while maintaining compatibility:

1. **Never remove**: Core MCP settings, OAuth endpoints, essential headers
2. **Safe to modify**: Comments, additional headers, conditional blocks
3. **Test thoroughly**: Any changes to proxy settings or timeouts

### Template Inheritance

The `mcp_location_block.j2` can be included in custom templates:

```nginx
server {
    listen 443 ssl;
    server_name custom.example.com;

    # Your custom server configuration

    # Include MCP functionality
    {% include 'mcp_location_block.j2' %}
}
```

### Environment-Specific Variations

Templates support conditional configuration:

```jinja2
{% if environment == "production" %}
    # Production-specific settings
    proxy_send_timeout 172800s;  # 48 hours
{% else %}
    # Development settings
    proxy_send_timeout 3600s;   # 1 hour
{% endif %}
```

---

**🔗 Related Documentation**:
- [SWAG MCP README](../README.md) - Project overview and setup
- [Environment Configuration](../.env.example) - Configuration variables
- [API Reference](../swag_mcp/tools/swag.py) - Tool implementation details

---

*Last Updated: January 2025 | SWAG MCP Server v2.0*
