# MCP Subdomain Template Enhancement Proposal

## Executive Summary

This document outlines **evidence-based proposed changes** to the `templates/mcp-subdomain.conf.j2` template based on comprehensive research conducted by 6 specialized research agents. Each proposed change is **backed by authoritative documentation sources** and verified for compatibility with the Model Context Protocol (MCP) specification.

## Research Methodology

Six specialized research agents conducted parallel investigations into:
1. **OAuth2 Header Requirements** - Authentication header analysis
2. **NGINX Rate Limiting** - DDoS protection for streaming endpoints  
3. **CORS Requirements** - Cross-origin access for MCP endpoints
4. **X-Accel-Buffering** - Application-level buffering control
5. **WebSocket Support** - Protocol upgrade requirements for MCP
6. **Security Headers** - OWASP 2025 recommendations for API endpoints

## Current Template Analysis

The existing `mcp-subdomain.conf.j2` template includes:
- ✅ **OAuth endpoints** with proper header forwarding
- ✅ **Streaming configuration** (proxy_buffering off, extended timeouts)
- ✅ **Security headers include** (`/config/nginx/security-headers.conf`)
- ✅ **Cache control headers** for token/revoke endpoints
- ✅ **QUIC/HTTP3 support** (conditional)

## Evidence-Based Proposed Changes

### 1. Health Endpoint Header Consistency ⚠️ VERIFIED BUT NOT REQUIRED

**Current Issue**: Health endpoint missing `X-Forwarded-Host` and `X-Forwarded-Port` headers

**Research Findings**: 
- **Source**: [NGINX Official Documentation](http://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- **Conclusion**: These headers are **NOT strictly required** for health check functionality
- **Best Practice**: Including them provides consistency with other endpoints

**Proposed Change**:
```nginx
# Health check endpoint (no auth required)
location /health {
    include /config/nginx/resolver.conf;

    # Disable buffering for health checks
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_cache off;
    proxy_request_buffering off;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;        # ADD
    proxy_set_header X-Forwarded-Port $server_port; # ADD

    proxy_pass $upstream_proto://$upstream_app:$upstream_port;
}
```

**Justification**: Consistency with OAuth endpoints and support for complex application requirements.

### 2. CORS Headers for Browser Compatibility ❌ REMOVE - NOT OFFICIALLY REQUIRED

**Research Findings**:
- **Source**: [MCP Official Specification](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- **Critical Finding**: **CORS is NOT mentioned in the official MCP specification**
- **Community Need**: GitHub issues indicate community desire for CORS support
- **Conclusion**: Not officially required, should not be included without explicit user request

**Proposed Change**: **REJECTED** - CORS headers should not be added to the template as they are not part of the official MCP specification.

### 3. X-Accel-Buffering Support ⚠️ OPTIONAL ENHANCEMENT

**Research Findings**:
- **Source**: [NGINX Official Documentation](http://nginx.org/en/docs/http/ngx_http_proxy_module.html)
- **Key Quote**: "The X-Accel-Buffering response header field can be used to enable or disable buffering by passing 'yes' or 'no'."
- **Best Practice**: Application-level control is preferred over server-level for mixed workloads

**Current Implementation**: Uses `proxy_buffering off` (server-level control)

**Proposed Enhancement**: **OPTIONAL** - Document that MCP servers can use `X-Accel-Buffering: no` header for per-response control, but current server-level approach is acceptable for dedicated MCP endpoints.

### 4. Rate Limiting Configuration ⚠️ OPTIONAL ENHANCEMENT

**Research Findings**:
- **Source**: [NGINX Rate Limiting Documentation](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html)
- **Security Concern**: 24-hour timeouts create DDoS vulnerability
- **Best Practice**: Implement connection limiting for persistent connections

**Proposed Change**: **OPTIONAL** - Add commented rate limiting configuration for security-conscious deployments:

```nginx
# Optional: Rate limiting for security (uncomment to enable)
# limit_req_zone $binary_remote_addr zone=mcp_limit:10m rate=10r/s;
# limit_conn_zone $binary_remote_addr zone=mcp_conn:10m;

# Main MCP endpoint for streamable-http transport
location /mcp {
    # Optional rate limiting (uncomment to enable)
    # limit_req zone=mcp_limit burst=20 nodelay;
    # limit_conn mcp_conn 5;  # Max 5 concurrent connections per IP
    
    # ... existing configuration
}
```

### 5. WebSocket Upgrade Support ❌ REMOVE - NOT OFFICIALLY SUPPORTED

**Research Findings**:
- **Source**: [MCP Official Transport Documentation](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- **Critical Finding**: **WebSocket is NOT officially supported by MCP as of March 2025**
- **Current Status**: WebSocket support is "in-review" via proposal SEP-1287/1288
- **Conclusion**: Should not be included until officially adopted

**Proposed Change**: **REJECTED** - WebSocket upgrade headers should not be added to the template.

### 6. Enhanced Security Headers ✅ VERIFIED AND RECOMMENDED

**Research Findings**:
- **Source**: [OWASP HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
- **API-Specific Requirements**: Additional headers needed for API endpoints
- **Current Implementation**: Uses external `/config/nginx/security-headers.conf` include

**Proposed Enhancement**: Add explicit security headers for MCP endpoints to ensure they're not missing:

```nginx
# Essential security headers for MCP endpoints
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'none'; connect-src 'self'; frame-ancestors 'none'" always;

# For production HTTPS (ensure HSTS is enabled)
# add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
```

**Justification**: 
- **Quote**: "HTTP Headers are a great booster for web security with easy implementation"
- **API Security**: Specific headers required for API endpoints beyond traditional web security

## Final Recommendations Summary

### ✅ IMPLEMENT THESE CHANGES:

1. **Health Endpoint Header Consistency** - Add missing X-Forwarded headers for consistency
2. **Enhanced Security Headers** - Add explicit security headers for API endpoints

### ⚠️ OPTIONAL ENHANCEMENTS:

1. **Rate Limiting Configuration** - Add commented examples for security-conscious deployments
2. **X-Accel-Buffering Documentation** - Document application-level buffering control option

### ❌ REJECT THESE CHANGES:

1. **CORS Headers** - Not part of official MCP specification
2. **WebSocket Support** - Not officially supported by MCP as of March 2025

## Implementation Priority

### High Priority (Implement First)
- Health endpoint header consistency (lines 202-206)
- Security headers enhancement (after line 27)

### Medium Priority (Optional)
- Rate limiting configuration comments
- X-Accel-Buffering documentation updates

### No Action Required
- CORS headers (not officially required)
- WebSocket upgrade (not officially supported)

## Verification Sources

All proposed changes are backed by these authoritative sources:
- [NGINX Official Documentation](http://nginx.org/en/docs/)
- [MCP Official Specification](https://modelcontextprotocol.io/specification/)
- [OWASP Security Guidelines](https://cheatsheetseries.owasp.org/)
- [RFC Standards](https://datatracker.ietf.org/)
- Production configuration examples from verified sources

## Testing Requirements

Before implementing these changes:
1. **Template Validation**: Ensure Jinja2 syntax remains valid
2. **NGINX Configuration Test**: Generated configs must pass `nginx -t`
3. **MCP Compatibility**: Verify changes don't break MCP streaming functionality
4. **Security Testing**: Validate security headers don't interfere with OAuth flows

## Conclusion

The current `mcp-subdomain.conf.j2` template is **already well-optimized** for MCP streaming. The proposed changes are **minor enhancements** focused on consistency and security rather than fundamental functionality improvements. The template already follows MCP best practices and should continue to work reliably for OAuth-enabled MCP servers.