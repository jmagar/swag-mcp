# SWAG MCP Tools - Claude Memory Reference

This directory contains the MCP tool implementations that provide the interface between AI assistants and the SWAG configuration management system.

## Directory Purpose

The `tools/` module implements the unified MCP tool interface using FastMCP framework:
- Single `swag` tool with action-based dispatch pattern
- Natural language parameter mapping to structured requests
- Comprehensive error handling with user-friendly messages
- Integration with middleware stack for logging and rate limiting
- Automatic health checks after configuration changes

## Key Files

### `swag.py` - Unified MCP Tool Implementation (621 lines)
The main `swag()` function that handles all SWAG operations through a single MCP tool:

```python
@tool
async def swag(
    ctx: Context,
    action: SwagAction,
    # Action-specific parameters (most optional)
    service_name: str = "",
    server_name: str = "",
    upstream_app: str = "",
    upstream_port: int = 0,
    config_name: str = "",
    # ... 20+ more parameters
) -> str:
    """
    Unified SWAG reverse proxy configuration management tool.

    Supports 10 actions through single tool interface:
    - list, create, view, edit, update, config, remove, logs, cleanup_backups, health_check
    """
```

## Tool Architecture

### Action Dispatch Pattern
The tool uses a centralized dispatch pattern to route requests to appropriate handlers:

```python
async def swag(ctx: Context, action: SwagAction, **kwargs) -> str:
    """Main tool function with action-based routing"""

    # Initialize service with configuration
    service = SwagManagerService(ctx.config)

    # Action dispatch with parameter validation
    if action == SwagAction.LIST:
        return await _handle_list_action(service, kwargs)
    elif action == SwagAction.CREATE:
        return await _handle_create_action(service, kwargs)
    elif action == SwagAction.VIEW:
        return await _handle_view_action(service, kwargs)
    # ... handle all 10 actions
    else:
        raise ValueError(f"Unsupported action: {action}")
```

### Parameter Validation Strategy
Each action handler validates parameters using Pydantic models:

```python
async def _handle_create_action(service: SwagManagerService, params: Dict) -> str:
    """Handle CREATE action with comprehensive validation"""
    try:
        # Validate parameters against Pydantic model
        request = SwagCreateRequest(**params)

        # Call service method with validated parameters
        result = await service.create_configuration(
            service_name=request.service_name,
            server_name=request.server_name,
            upstream_app=request.upstream_app,
            upstream_port=request.upstream_port,
            upstream_proto=request.upstream_proto,
            config_type=request.config_type_create,
            auth_method=request.auth_method,
            enable_quic=request.enable_quic
        )

        # Format response for AI assistant
        return _format_success_response(result)

    except ValidationError as e:
        return _format_validation_error(e)
    except SwagServiceError as e:
        return _format_service_error(e)
```

## Action Handlers Deep Dive

### LIST Action Handler
```python
async def _handle_list_action(service: SwagManagerService, params: Dict) -> str:
    """
    List SWAG configurations with filtering options.

    Parameters:
    - config_type: "all" (default), "active", "samples"

    Response includes:
    - Configuration count by type
    - File details (name, size, modified time)
    - Summary statistics
    """
    request = SwagListRequest(**params)
    result = await service.list_configurations(request.config_type)

    # Format user-friendly response
    configs = result.get('data', {}).get('configs', [])
    return f"Found {len(configs)} configurations of type '{request.config_type}'"
```

### CREATE Action Handler
```python
async def _handle_create_action(service: SwagManagerService, params: Dict) -> str:
    """
    Create new SWAG reverse proxy configuration.

    Required Parameters:
    - service_name: Identifier for the service
    - server_name: Domain name for the proxy
    - upstream_app: Container name or IP
    - upstream_port: Port number (1-65535)

    Optional Parameters:
    - upstream_proto: "http" or "https" (default: "http")
    - config_type_create: Template type (default: "subdomain")
    - auth_method: Authentication method (default: "authelia")
    - enable_quic: QUIC support (default: false)

    Post-creation actions:
    - Automatic health check of created service
    - Backup creation if file exists
    - Template validation before writing
    """
    request = SwagCreateRequest(**params)

    # Create configuration
    result = await service.create_configuration(
        service_name=request.service_name,
        server_name=request.server_name,
        upstream_app=request.upstream_app,
        upstream_port=request.upstream_port,
        upstream_proto=request.upstream_proto,
        config_type=request.config_type_create,
        auth_method=request.auth_method,
        enable_quic=request.enable_quic
    )

    # Automatic health check after creation
    if result['success']:
        try:
            health_result = await service.check_service_health(
                domain=request.server_name,
                timeout=10
            )
            health_status = "accessible" if health_result['data']['accessible'] else "not accessible"
            return f"Created {request.service_name} configuration. Service is {health_status}."
        except Exception:
            return f"Created {request.service_name} configuration. Health check failed."

    return _format_service_error(result)
```

### UPDATE Action Handler
```python
async def _handle_update_action(service: SwagManagerService, params: Dict) -> str:
    """
    Update specific fields in existing configuration.

    Supported update fields:
    - port: Update upstream port (validates 1-65535 range)
    - upstream: Update upstream app name/IP
    - app: Update app name (with optional :port)

    Features:
    - Atomic updates with rollback on failure
    - Automatic backup creation (optional)
    - Field-specific validation
    - Configuration syntax validation
    """
    request = SwagUpdateRequest(**params)

    result = await service.update_configuration_field(
        config_name=request.config_name,
        field=request.update_field,
        value=request.update_value,
        create_backup=request.create_backup
    )

    if result['success']:
        return f"Updated {request.update_field} for {request.config_name} to {request.update_value}"
    return _format_service_error(result)
```

### HEALTH_CHECK Action Handler
```python
async def _handle_health_check_action(service: SwagManagerService, params: Dict) -> str:
    """
    Comprehensive health check of service endpoints.

    Parameters:
    - domain: Domain to check (required)
    - timeout: Request timeout in seconds (default: 30, max: 300)
    - follow_redirects: Follow HTTP redirects (default: true)

    Health check process:
    1. Try /health endpoint (standard health check)
    2. Try /mcp endpoint (MCP-specific)
    3. Try / root endpoint (fallback)
    4. Report detailed results with timing
    """
    request = SwagHealthCheckRequest(**params)

    result = await service.check_service_health(
        domain=request.domain,
        timeout=request.timeout,
        follow_redirects=request.follow_redirects
    )

    health_data = result.get('data', {})
    if health_data.get('accessible'):
        status_code = health_data.get('status_code', 'unknown')
        response_time = health_data.get('response_time_ms', 0)
        return f"✅ {request.domain} is accessible (HTTP {status_code}, {response_time:.1f}ms)"
    else:
        error_msg = health_data.get('error_message', 'Unknown error')
        return f"❌ {request.domain} is not accessible: {error_msg}"
```

## Response Formatting

### Success Response Formatting
```python
def _format_success_response(result: Dict[str, Any]) -> str:
    """Format successful operation response for AI assistant"""
    if not result.get('success', False):
        return _format_service_error(result)

    message = result.get('message', 'Operation completed successfully')
    data = result.get('data')

    if data:
        # Add relevant data details to response
        if 'total_count' in data:
            message += f" (Found {data['total_count']} items)"
        if 'backup_created' in data:
            message += f" (Backup: {data['backup_created']})"

    return message
```

### Error Response Formatting
```python
def _format_validation_error(error: ValidationError) -> str:
    """Convert Pydantic validation errors to user-friendly messages"""
    errors = []
    for err in error.errors():
        field = ".".join(str(loc) for loc in err['loc'])
        msg = err['msg']
        errors.append(f"{field}: {msg}")

    return f"Validation failed: {'; '.join(errors)}"

def _format_service_error(result: Dict[str, Any]) -> str:
    """Format service-level errors for user display"""
    if isinstance(result, dict) and 'message' in result:
        return f"Error: {result['message']}"
    return f"Error: {str(result)}"
```

## Natural Language Integration

### Parameter Mapping Examples
The tool is designed to work with natural language commands from AI assistants:

```python
# Natural language: "Create jellyfin proxy at media.example.com on port 8096"
# Maps to parameters:
{
    "action": "create",
    "service_name": "jellyfin",
    "server_name": "media.example.com",
    "upstream_app": "jellyfin",
    "upstream_port": 8096
}

# Natural language: "Update port for jellyfin config to 8097"
# Maps to parameters:
{
    "action": "update",
    "config_name": "jellyfin.subdomain.conf",
    "update_field": "port",
    "update_value": "8097"
}

# Natural language: "Check if media.example.com is accessible"
# Maps to parameters:
{
    "action": "health_check",
    "domain": "media.example.com"
}
```

### Response Optimization for AI
Responses are formatted to be:
- **Concise**: Essential information only
- **Actionable**: Include next steps if needed
- **Status-aware**: Clear success/failure indication
- **Context-rich**: Include relevant details for follow-up

## Error Handling Strategy

### Error Categories
```python
# Parameter validation errors (Pydantic)
try:
    request = SwagCreateRequest(**params)
except ValidationError as e:
    return _format_validation_error(e)

# Service-level errors (business logic)
try:
    result = await service.create_configuration(...)
except SwagServiceError as e:
    return f"Configuration error: {str(e)}"

# System-level errors (I/O, permissions)
try:
    result = await service.create_configuration(...)
except OSError as e:
    return f"System error: {handle_os_error(e)}"

# Unexpected errors (programming bugs)
except Exception as e:
    logger.error(f"Unexpected error in {action}: {e}", exc_info=True)
    return f"Unexpected error: {str(e)}"
```

### Error Recovery Patterns
- **Validation errors**: Provide specific field requirements
- **File not found**: List available configurations
- **Permission errors**: Check file permissions and paths
- **Template errors**: List available templates
- **Health check failures**: Provide troubleshooting steps

## Tool Registration

### FastMCP Integration
```python
# In server.py
from swag_mcp.tools.swag import swag

def register_tools(app: FastMCP):
    """Register all MCP tools with the server"""
    app.add_tool(swag)  # Single unified tool registration
```

### Tool Metadata
```python
@tool
async def swag(
    ctx: Context,
    action: SwagAction,
    # Full parameter list with types and defaults
    service_name: str = Field(
        default="",
        description="Service identifier used for filename",
        max_length=50,
        pattern=r"^[\w-]*$"
    ),
    # ... all parameters with full metadata
) -> str:
    """
    Unified SWAG reverse proxy configuration management tool.

    This tool provides comprehensive management of SWAG (Secure Web Application Gateway)
    reverse proxy configurations through natural language commands.

    Supports 10 actions: list, create, view, edit, update, config, remove, logs,
    cleanup_backups, health_check
    """
```

## Development Commands

### Tool Testing
```bash
# Test tool function directly
uv run pytest tests/test_swag_actions.py::TestSwagTools -v

# Test specific action
uv run pytest tests/test_swag_actions.py -k "test_swag_create" -v

# Test error handling
uv run pytest tests/test_error_handling.py::TestToolErrors -v
```

### Manual Tool Testing
```bash
# Test tool registration
python -c "
from swag_mcp.tools.swag import swag
print('Tool function:', swag)
print('Tool name:', swag.__name__)
"

# Test parameter validation
python -c "
import asyncio
from swag_mcp.tools.swag import swag
from swag_mcp.models.enums import SwagAction
from fastmcp import Context

# Mock context for testing
class MockConfig:
    proxy_confs_path = '/tmp/test'
    log_directory = '/tmp/logs'

class MockContext:
    config = MockConfig()

async def test():
    result = await swag(
        MockContext(),
        SwagAction.CONFIG
    )
    print('Result:', result)

asyncio.run(test())
"
```

## Performance Considerations

### Parameter Processing
- Parameter validation happens at tool entry point
- Heavy validation moved to Pydantic models for reuse
- Optional parameters with defaults reduce processing overhead

### Service Integration
- Service instance created per tool invocation (stateless)
- HTTP sessions reused for health checks within same operation
- File operations use async I/O throughout

### Response Optimization
- Responses are strings optimized for AI assistant parsing
- Large data sets summarized rather than returned in full
- Error messages designed for user comprehension, not debugging

## Important Notes

### Tool Design Philosophy
- **Single tool approach**: Unified interface rather than multiple specialized tools
- **Natural language first**: Designed for AI assistant interaction
- **Error tolerance**: Graceful handling of invalid or incomplete parameters
- **Action-oriented**: Clear separation of concerns by action type

### Parameter Handling
- All parameters except `action` are optional with sensible defaults
- Parameter validation delegated to Pydantic models
- Optional parameters don't require explicit None checks

### AI Integration
- Responses formatted for AI assistant parsing
- Context includes configuration for service instantiation
- Error messages provide actionable feedback for users
- Success responses include relevant details for follow-up actions
