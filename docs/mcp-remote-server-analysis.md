# MCP Remote Server Support Analysis

## Executive Summary

This document analyzes the current SWAG MCP architecture and proposes solutions for supporting MCP servers running on different machines than the main web service they're attached to.

**Current Limitation**: All location blocks in a configuration file share the same upstream variables (`$upstream_app`, `$upstream_port`, `$upstream_proto`).

**Goal**: Enable configurations where:
- Main service (e.g., Jellyfin) runs on `jellyfin:8096`
- MCP endpoint runs on a different server (e.g., `ai-server:8080`)

---

## Current Architecture Analysis

### 1. Template Variable System

**Location**: `swag_mcp/services/config_operations.py:252-261`

```python
template_vars = {
    "service_name": validated_service_name,
    "server_name": validated_server_name,
    "upstream_app": request.upstream_app,      # Single upstream
    "upstream_port": validated_port,           # Single port
    "upstream_proto": request.upstream_proto,  # Single protocol
    "auth_method": request.auth_method,
    "enable_quic": request.enable_quic,
}
```

**Key Finding**: Templates receive a single set of upstream variables for the entire configuration.

### 2. Template Implementation

**Subdomain Template**: `templates/swag-compliant-mcp-subdomain.conf.j2:28-31`

```nginx
# Upstream target variables (SWAG standard pattern)
set $upstream_app "{{ upstream_app }}";
set $upstream_port "{{ upstream_port }}";
set $upstream_proto "{{ upstream_proto }}";
```

**All location blocks reference these same variables**:

```nginx
# Line 125 - Main MCP endpoint
proxy_pass $upstream_proto://$upstream_app:$upstream_port;

# Line 144 - OAuth metadata endpoint
proxy_pass $upstream_proto://$upstream_app:$upstream_port;

# Line 294 - Default location (main service)
proxy_pass $upstream_proto://$upstream_app:$upstream_port;
```

**Problem**: No mechanism to override upstream for specific location blocks.

### 3. Data Model

**Location**: `swag_mcp/models/config.py:86-117`

```python
class SwagConfigRequest(SwagBaseRequest):
    config_name: str = Field(...)
    server_name: str = Field(...)
    upstream_app: str = Field(...)         # Single upstream app
    upstream_port: int = Field(...)        # Single port
    upstream_proto: Literal["http", "https"] = Field(...)
    mcp_enabled: bool = Field(default=False)
    auth_method: AuthMethodType = Field(...)
    enable_quic: bool = Field(...)
```

**Key Finding**: The request model only supports a single upstream configuration.

### 4. MCP Location Addition

**Location**: `swag_mcp/services/mcp_operations.py:102-150`

The `add_mcp_location()` method adds MCP blocks to existing configs, but it uses the template block from `templates/mcp_location_block.j2` which references `$upstream_app` and `$upstream_port` variables already defined in the parent configuration.

**Key Finding**: Even dynamically added MCP locations use the same upstream variables.

---

## Use Case Examples

### Use Case 1: Jellyfin + Remote AI Service

**Scenario**:
- Jellyfin media server: `jellyfin:8096`
- AI subtitle generator MCP: `ai-gpu-server:8080`

**Desired Configuration**:
```nginx
# jellyfin.subdomain.conf
server {
    # ... SSL config ...

    set $upstream_app "jellyfin";
    set $upstream_port "8096";
    set $upstream_proto "http";

    # Main Jellyfin service
    location / {
        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    # Remote MCP service (DIFFERENT upstream!)
    location /mcp {
        set $mcp_upstream_app "ai-gpu-server";
        set $mcp_upstream_port "8080";
        proxy_pass http://$mcp_upstream_app:$mcp_upstream_port;
    }
}
```

### Use Case 2: Plex + Multiple MCP Services

**Scenario**:
- Plex media server: `plex:32400`
- Transcoding MCP: `transcode-server:9000`
- Metadata MCP: `metadata-server:9001`

**Desired Configuration**:
```nginx
location / {
    proxy_pass https://plex:32400;
}

location /mcp/transcode {
    proxy_pass http://transcode-server:9000;
}

location /mcp/metadata {
    proxy_pass http://metadata-server:9001;
}
```

---

## Proposed Solutions

### Solution 1: Separate MCP Upstream Variables (Recommended)

**Approach**: Add dedicated MCP upstream fields to the data model and template system.

#### Advantages
- ✅ Clean separation of concerns
- ✅ Backward compatible (optional fields)
- ✅ Natural to understand and use
- ✅ Minimal template complexity

#### Disadvantages
- ⚠️ Requires data model changes
- ⚠️ Template updates needed
- ⚠️ Migration path for existing configs

#### Implementation

**1. Update Data Model** (`swag_mcp/models/config.py`)

```python
class SwagConfigRequest(SwagBaseRequest):
    # Existing fields
    config_name: str = Field(...)
    server_name: str = Field(...)
    upstream_app: str = Field(...)
    upstream_port: int = Field(...)
    upstream_proto: Literal["http", "https"] = Field(default="http")

    # NEW: MCP-specific upstream configuration (optional)
    mcp_upstream_app: str | None = Field(
        default=None,
        pattern=VALID_UPSTREAM_PATTERN,
        max_length=100,
        description="Container name or IP for MCP service (defaults to upstream_app)"
    )
    mcp_upstream_port: int | None = Field(
        default=None,
        ge=1,
        le=65535,
        description="Port for MCP service (defaults to upstream_port)"
    )
    mcp_upstream_proto: Literal["http", "https"] | None = Field(
        default=None,
        description="Protocol for MCP service (defaults to upstream_proto)"
    )

    # Existing fields
    mcp_enabled: bool = Field(default=False)
    auth_method: AuthMethodType = Field(default="authelia")
    enable_quic: bool = Field(default=False)

    @model_validator(mode="after")
    def set_mcp_upstream_defaults(self) -> "SwagConfigRequest":
        """Set MCP upstream defaults to main upstream if not specified."""
        if self.mcp_enabled:
            if self.mcp_upstream_app is None:
                self.mcp_upstream_app = self.upstream_app
            if self.mcp_upstream_port is None:
                self.mcp_upstream_port = self.upstream_port
            if self.mcp_upstream_proto is None:
                self.mcp_upstream_proto = self.upstream_proto
        return self
```

**2. Update Template** (`templates/swag-compliant-mcp-subdomain.conf.j2`)

```jinja2
server {
    # ... SSL config ...

    # Main service upstream variables
    set $upstream_app "{{ upstream_app }}";
    set $upstream_port "{{ upstream_port }}";
    set $upstream_proto "{{ upstream_proto }}";

    # MCP service upstream variables (may differ from main service)
    set $mcp_upstream_app "{{ mcp_upstream_app }}";
    set $mcp_upstream_port "{{ mcp_upstream_port }}";
    set $mcp_upstream_proto "{{ mcp_upstream_proto }}";

    # MCP endpoint - uses dedicated MCP upstream
    location /mcp {
        # ... MCP configuration ...
        proxy_pass $mcp_upstream_proto://$mcp_upstream_app:$mcp_upstream_port;
    }

    # OAuth endpoints - use MCP upstream (part of MCP service)
    location = /.well-known/oauth-protected-resource {
        # ... config ...
        proxy_pass $mcp_upstream_proto://$mcp_upstream_app:$mcp_upstream_port;
    }

    # Health check - could be either, let's use main service
    location /health {
        # ... config ...
        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    # Default location - main service
    location / {
        # ... config ...
        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }
}
```

**3. Update Template Variable Passing** (`swag_mcp/services/config_operations.py`)

```python
# Prepare template variables
template_vars = {
    "service_name": validated_service_name,
    "server_name": validated_server_name,
    "upstream_app": request.upstream_app,
    "upstream_port": validated_port,
    "upstream_proto": request.upstream_proto,

    # MCP upstream variables (with defaults)
    "mcp_upstream_app": request.mcp_upstream_app or request.upstream_app,
    "mcp_upstream_port": request.mcp_upstream_port or validated_port,
    "mcp_upstream_proto": request.mcp_upstream_proto or request.upstream_proto,

    "auth_method": request.auth_method,
    "enable_quic": request.enable_quic,
}
```

**4. Usage Examples**

**Same machine (backward compatible)**:
```python
SwagConfigRequest(
    config_name="jellyfin.subdomain.conf",
    server_name="jellyfin.example.com",
    upstream_app="jellyfin",
    upstream_port=8096,
    mcp_enabled=True
    # MCP uses same upstream: jellyfin:8096
)
```

**Different machine**:
```python
SwagConfigRequest(
    config_name="jellyfin.subdomain.conf",
    server_name="jellyfin.example.com",
    upstream_app="jellyfin",
    upstream_port=8096,
    mcp_enabled=True,
    mcp_upstream_app="ai-gpu-server",
    mcp_upstream_port=8080,
    mcp_upstream_proto="http"
    # Main service: jellyfin:8096
    # MCP service: ai-gpu-server:8080
)
```

---

### Solution 2: Location-Specific Overrides

**Approach**: Allow per-location upstream overrides via template syntax.

#### Advantages
- ✅ Maximum flexibility
- ✅ Supports multiple MCP endpoints
- ✅ No data model changes needed initially

#### Disadvantages
- ❌ More complex template logic
- ❌ Harder to validate
- ❌ Less type-safe

#### Implementation Sketch

```jinja2
{% if mcp_locations %}
  {% for location in mcp_locations %}
    location {{ location.path }} {
        set $location_upstream_app "{{ location.upstream_app }}";
        set $location_upstream_port "{{ location.upstream_port }}";
        proxy_pass http://$location_upstream_app:$location_upstream_port;
    }
  {% endfor %}
{% endif %}
```

**Not recommended** due to complexity and validation challenges.

---

### Solution 3: Multiple Configuration Files

**Approach**: Create separate nginx configuration files for different services.

#### Advantages
- ✅ No code changes needed
- ✅ Uses existing SWAG patterns

#### Disadvantages
- ❌ Requires separate domains/subdomains
- ❌ Doesn't solve the single-domain use case
- ❌ More complex management

**Example**:
- `jellyfin.subdomain.conf` → `jellyfin.example.com` → `jellyfin:8096`
- `jellyfin-mcp.subdomain.conf` → `ai.example.com` → `ai-gpu-server:8080`

**Not recommended** as it doesn't solve the core use case.

---

## Recommended Implementation Plan

**Adopt Solution 1: Separate MCP Upstream Variables**

### Phase 1: Core Implementation

1. **Update Data Models** (1-2 hours)
   - Add `mcp_upstream_app`, `mcp_upstream_port`, `mcp_upstream_proto` fields
   - Add model validator for defaults
   - Update `SwagEditRequest` for consistency
   - Add validators for MCP upstream fields

2. **Update Templates** (2-3 hours)
   - Update `swag-compliant-mcp-subdomain.conf.j2`
   - Update `swag-compliant-mcp-subfolder.conf.j2`
   - Add MCP upstream variables
   - Update all MCP-related location blocks to use MCP upstream

3. **Update Template Variable Passing** (1 hour)
   - Modify `config_operations.py:create_config()`
   - Add MCP upstream variables to template_vars
   - Implement default fallback logic

4. **Update Tests** (2-3 hours)
   - Test same-machine configurations (backward compatibility)
   - Test different-machine configurations
   - Test validation logic
   - Test template rendering

### Phase 2: Enhanced Features

5. **Update `add_mcp_location()` Method** (2 hours)
   - Support specifying custom upstream for added MCP locations
   - Update `mcp_location_block.j2` template
   - Add parameters to `SwagUpdateRequest` for `add_mcp` action

6. **CLI/Tool Interface** (1 hour)
   - Update natural language processing in tool
   - Add examples to documentation

7. **Documentation** (2 hours)
   - Update README.md with examples
   - Update CLAUDE.md
   - Create migration guide for existing configs

### Phase 3: Testing & Validation

8. **Integration Testing** (2-3 hours)
   - End-to-end tests with real containers
   - Test with Docker Compose setup
   - Validate nginx configuration syntax

9. **Documentation Review** (1 hour)
   - Code examples
   - Natural language command examples
   - Troubleshooting guide

---

## Testing Strategy

### Unit Tests

```python
async def test_create_config_with_remote_mcp_server():
    """Test creating config with MCP on different server."""
    request = SwagConfigRequest(
        config_name="jellyfin.subdomain.conf",
        server_name="jellyfin.example.com",
        upstream_app="jellyfin",
        upstream_port=8096,
        mcp_enabled=True,
        mcp_upstream_app="ai-server",
        mcp_upstream_port=8080,
    )

    result = await swag_manager.create_config(request)

    # Verify main service uses jellyfin:8096
    assert 'set $upstream_app "jellyfin"' in result.content
    assert 'set $upstream_port "8096"' in result.content

    # Verify MCP uses ai-server:8080
    assert 'set $mcp_upstream_app "ai-server"' in result.content
    assert 'set $mcp_upstream_port "8080"' in result.content

    # Verify MCP location uses MCP upstream
    assert re.search(
        r'location /mcp \{.*?proxy_pass \$mcp_upstream_proto://\$mcp_upstream_app:\$mcp_upstream_port',
        result.content,
        re.DOTALL
    )
```

### Integration Tests

```python
async def test_remote_mcp_server_health_check():
    """Test health checks work with remote MCP server."""
    # Create config with remote MCP
    await swag_manager.create_config(...)

    # Verify main service is accessible
    main_health = await swag_manager.health_check(
        SwagHealthCheckRequest(domain="jellyfin.example.com")
    )
    assert main_health.success

    # Verify MCP endpoint is accessible
    mcp_health = await swag_manager.health_check(
        SwagHealthCheckRequest(domain="jellyfin.example.com/mcp")
    )
    assert mcp_health.success
```

---

## Natural Language Interface

### Example Commands

**Create config with remote MCP server**:
- *"Create a jellyfin proxy at jellyfin.example.com using jellyfin:8096 with MCP on ai-server:8080"*
- *"Set up jellyfin at jellyfin.example.com port 8096, but use ai-gpu-server port 8080 for the MCP endpoint"*
- *"Add jellyfin subdomain proxy with main service on jellyfin:8096 and MCP service on remote-ai:8080"*

**Update existing config to use remote MCP**:
- *"Update jellyfin config to use ai-server:8080 for MCP instead of jellyfin"*
- *"Change the MCP upstream for jellyfin to point to remote-gpu:9000"*

---

## Backward Compatibility

**Critical Requirement**: Existing configurations must continue to work.

### Compatibility Strategy

1. **Default Behavior**: If MCP upstream fields are not specified, they default to the main upstream
2. **Model Validator**: Automatically sets MCP upstream to main upstream if null
3. **Template Logic**: Templates work with both old and new variable sets
4. **Migration**: No migration needed - new fields are optional

### Example

**Old API Call** (still works):
```python
SwagConfigRequest(
    config_name="jellyfin.subdomain.conf",
    server_name="jellyfin.example.com",
    upstream_app="jellyfin",
    upstream_port=8096,
    mcp_enabled=True
)
# Result: Both main and MCP use jellyfin:8096
```

**New API Call**:
```python
SwagConfigRequest(
    config_name="jellyfin.subdomain.conf",
    server_name="jellyfin.example.com",
    upstream_app="jellyfin",
    upstream_port=8096,
    mcp_enabled=True,
    mcp_upstream_app="ai-server",
    mcp_upstream_port=8080
)
# Result: Main uses jellyfin:8096, MCP uses ai-server:8080
```

---

## Edge Cases & Considerations

### 1. Health Check Endpoints

**Question**: Should `/health` check the main service or MCP service?

**Recommendation**:
- `/health` → Main service (existing behavior)
- Add `/mcp/health` → MCP service (new)

### 2. OAuth Endpoints

**Question**: Do OAuth endpoints (/.well-known/*) belong to MCP or main service?

**Recommendation**: MCP service (they're part of MCP protocol)

```nginx
location = /.well-known/oauth-protected-resource {
    proxy_pass $mcp_upstream_proto://$mcp_upstream_app:$mcp_upstream_port;
}
```

### 3. Subfolder Configurations

**Challenge**: Subfolder configs have different path structure

**Solution**: Apply same pattern to subfolder template

```nginx
# Main service
location ^~ /jellyfin {
    proxy_pass $upstream_proto://$upstream_app:$upstream_port;
}

# MCP service
location ^~ /jellyfin/mcp {
    proxy_pass $mcp_upstream_proto://$mcp_upstream_app:$mcp_upstream_port/mcp;
}
```

### 4. Multiple MCP Endpoints

**Future Enhancement**: Support multiple MCP services per config

```python
mcp_services: list[MCPServiceConfig] | None = Field(default=None)

class MCPServiceConfig:
    path: str  # e.g., "/mcp/transcode"
    upstream_app: str
    upstream_port: int
    upstream_proto: str
```

**Not in scope for initial implementation.**

---

## Files to Modify

### Core Implementation Files

1. **`swag_mcp/models/config.py`**
   - Add MCP upstream fields to `SwagConfigRequest`
   - Add model validator for defaults
   - Update `SwagEditRequest` if needed

2. **`swag_mcp/services/config_operations.py`**
   - Update `create_config()` template variables
   - Add MCP upstream variable passing

3. **`templates/swag-compliant-mcp-subdomain.conf.j2`**
   - Add MCP upstream variables
   - Update MCP location blocks

4. **`templates/swag-compliant-mcp-subfolder.conf.j2`**
   - Add MCP upstream variables
   - Update MCP location blocks

### Enhanced Features Files

5. **`swag_mcp/services/mcp_operations.py`**
   - Update `add_mcp_location()` for custom upstreams
   - Add upstream parameters

6. **`templates/mcp_location_block.j2`**
   - Support custom upstream variables

7. **`swag_mcp/models/config.py`** (continued)
   - Update `SwagUpdateRequest` for MCP upstream updates

### Documentation Files

8. **`README.md`**
   - Add remote MCP server examples
   - Update feature list

9. **`CLAUDE.md`**
   - Document new fields
   - Add usage examples

10. **`docs/TEMPLATES.md`**
    - Document template changes
    - Add variable reference

### Test Files

11. **`tests/test_swag_actions.py`**
    - Add remote MCP server tests
    - Test backward compatibility

12. **`tests/test_integration.py`**
    - Add end-to-end tests
    - Test health checks

13. **`tests/test_validation.py`**
    - Test MCP upstream validation

---

## Risk Assessment

### Low Risk
- ✅ Backward compatibility maintained (optional fields)
- ✅ No breaking changes to API
- ✅ Well-defined scope

### Medium Risk
- ⚠️ Template complexity increases slightly
- ⚠️ More validation logic needed
- ⚠️ Nginx configuration testing required

### Mitigation
- Comprehensive unit tests
- Integration tests with real nginx
- Thorough documentation
- Gradual rollout

---

## Conclusion

**Recommendation**: Implement **Solution 1 (Separate MCP Upstream Variables)**

### Key Benefits
1. Clean, intuitive API
2. Backward compatible
3. Type-safe with Pydantic validation
4. Straightforward template implementation
5. Supports the primary use case well

### Next Steps
1. Review and approve this proposal
2. Implement Phase 1 (core functionality)
3. Test with real Docker containers
4. Document and release

### Estimated Timeline
- **Phase 1 (Core)**: 6-8 hours
- **Phase 2 (Enhanced)**: 5 hours
- **Phase 3 (Testing)**: 3-4 hours
- **Total**: 14-17 hours of development work

---

## Appendix: Complete Example Configuration

### Input Request
```python
SwagConfigRequest(
    config_name="jellyfin.subdomain.conf",
    server_name="jellyfin.example.com",
    upstream_app="jellyfin",
    upstream_port=8096,
    upstream_proto="http",
    mcp_enabled=True,
    mcp_upstream_app="ai-gpu-server",
    mcp_upstream_port=8080,
    mcp_upstream_proto="http",
    auth_method="authelia",
    enable_quic=False
)
```

### Generated Configuration
```nginx
## Version 2025/08/20 - MCP 2025-06-18 SWAG Compatible
# Generated by SWAG MCP Server
# Service: jellyfin
# Domain: jellyfin.example.com
# Main Upstream: http://jellyfin:8096
# MCP Upstream: http://ai-gpu-server:8080

server {
    listen 443 ssl;
    server_name jellyfin.example.com;

    include /config/nginx/ssl.conf;

    # Main service upstream
    set $upstream_app "jellyfin";
    set $upstream_port "8096";
    set $upstream_proto "http";

    # MCP service upstream (remote server)
    set $mcp_upstream_app "ai-gpu-server";
    set $mcp_upstream_port "8080";
    set $mcp_upstream_proto "http";

    # MCP endpoint - remote AI server
    location /mcp {
        include /config/nginx/authelia-location.conf;
        include /config/nginx/resolver.conf;
        include /config/nginx/mcp.conf;

        proxy_set_header MCP-Protocol-Version $http_mcp_protocol_version;
        proxy_set_header Mcp-Session-Id $http_mcp_session_id;

        # Routes to ai-gpu-server:8080
        proxy_pass $mcp_upstream_proto://$mcp_upstream_app:$mcp_upstream_port;
    }

    # OAuth endpoints - part of MCP service
    location = /.well-known/oauth-protected-resource {
        include /config/nginx/resolver.conf;
        include /config/nginx/proxy.conf;

        # Routes to ai-gpu-server:8080
        proxy_pass $mcp_upstream_proto://$mcp_upstream_app:$mcp_upstream_port;
    }

    # Health check - main service
    location /health {
        include /config/nginx/resolver.conf;
        include /config/nginx/mcp.conf;

        # Routes to jellyfin:8096
        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }

    # Default location - main Jellyfin service
    location / {
        include /config/nginx/authelia-location.conf;
        include /config/nginx/resolver.conf;
        include /config/nginx/proxy.conf;

        # Routes to jellyfin:8096
        proxy_pass $upstream_proto://$upstream_app:$upstream_port;
    }
}
```

This configuration successfully routes:
- `https://jellyfin.example.com/` → `http://jellyfin:8096` (main service)
- `https://jellyfin.example.com/mcp` → `http://ai-gpu-server:8080` (AI service)
