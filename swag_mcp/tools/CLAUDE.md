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
    config_name: str = "",
    server_name: str = "",
    upstream_app: str = "",
    upstream_port: int = 0,
    # ... 20+ more parameters
) -> ToolResult:
    """
    Unified SWAG reverse proxy configuration management tool.

    Supports the unified action set:
    - list, create, view, edit, update, remove, logs, backups, health_check
    """
```

## Tool Architecture

### Action Dispatch Pattern
The tool uses a centralized dispatch pattern to route requests to appropriate handlers:

```python
async def swag(ctx: Context, action: SwagAction, **kwargs) -> str:
    """Main tool function with action-based routing"""

    formatter = TokenEfficientFormatter()

    async with SwagManagerService() as service:
        match action:
            case SwagAction.LIST:
                return await _handle_list_action(ctx, service, formatter, ...)
            case SwagAction.CREATE:
                return await _handle_create_action(ctx, service, formatter, ...)
            case SwagAction.VIEW:
                return await _handle_view_action(ctx, service, formatter, ...)
            # ... handle all supported actions
            case _:
                raise ValueError(f"Unsupported action: {action}")
```

### Parameter Validation Strategy
Each action handler validates parameters using Pydantic models:

```python
async def _handle_create_action(ctx: Context, service: SwagManagerService, formatter: TokenEfficientFormatter, ...) -> ToolResult:
    """Handle CREATE action with comprehensive validation"""
    try:
        # Validate parameters against Pydantic model
        request = SwagConfigRequest(...)

        # Call service method with validated parameters
        result = await service.create_config(request)

        # Format ToolResult with text content and structured_content
        return formatter.format_create_result(result_data, request.config_name)

    except ValidationError as e:
        return formatter.format_error_result(str(e), "create")
    except SwagServiceError as e:
        return formatter.format_error_result(str(e), "create")
```

## Action Handlers Deep Dive

### LIST Action Handler
The list handler validates `list_filter`, applies query/sort/pagination in the handler, and returns a `ToolResult` whose structured content contains `items`, `total`, `limit`, `offset`, `has_more`, plus legacy formatter keys `configs`, `total_count`, and `list_filter`.

### CREATE Action Handler
Create requires `config_name`, `server_name`, `upstream_app`, and `upstream_port`. Optional split-routing fields are `mcp_upstream_app`, `mcp_upstream_port`, and `mcp_upstream_proto`; omitted MCP upstream values inherit from the main upstream. The handler builds `SwagConfigRequest`, calls `create_config`, runs a post-create health check, and returns structured keys `success`, `filename`, `content`, `backup_created`, and `health_check`.

### UPDATE Action Handler
```python
async def _handle_update_action(service: SwagManagerService, params: Dict) -> str:
    """
    Update specific fields in existing configuration.

    Supported update fields:
    - port: Update upstream port (validates 1-65535 range)
    - upstream: Update upstream app name/IP
    - app: Update upstream app and port; requires app:port format

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

    return formatter.format_update_result(result_data, request.config_name, request.update_field, request.update_value)
```

### HEALTH_CHECK Action Handler

The health-check handler validates `domain`, builds `SwagHealthCheckRequest`, calls `health_check`, and returns formatter output with `success`, `domain`, `status_code`, `response_time_ms`, `error`, and `endpoint_results`.

## Response Formatting

`TokenEfficientFormatter` builds every MCP response as a `ToolResult` with two parts:

- `content`: concise text optimized for interactive assistants.
- `structured_content`: action-specific JSON-like data for programmatic clients.

Do not document a universal success schema. Some successful actions include `success`; list/log/backup-list responses currently rely on action-specific keys. Error responses include at least `success=false`, `error`, and `action`.

## Natural Language Integration

### Parameter Mapping Examples
The tool is designed to work with natural language commands from AI assistants:

```python
# Natural language: "Create jellyfin proxy at media.example.com on port 8096"
# Maps to parameters:
{
    "action": "create",
    "config_name": "jellyfin.subdomain.conf",
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
    request = SwagConfigRequest(...)
except ValidationError as e:
    return formatter.format_error_result(str(e), "create")

# Service-level errors (business logic)
try:
    result = await service.create_config(request)
except SwagServiceError as e:
    return formatter.format_error_result(str(e), "create")

# System-level errors (I/O, permissions)
try:
    result = await service.create_config(request)
except OSError as e:
    return formatter.format_error_result(handle_os_error(e), "create")

# Unexpected errors (programming bugs)
except Exception as e:
    logger.error("Unexpected error in %s: %s", action, e, exc_info=True)
    return formatter.format_error_result("Tool execution failed due to an unexpected error.", action)
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
    config_name: str = Field(
        default="",
        description="Configuration filename",
        max_length=255
    ),
    # ... all parameters with full metadata
) -> str:
    """
    Unified SWAG reverse proxy configuration management tool.

    This tool provides comprehensive management of SWAG (Secure Web Application Gateway)
    reverse proxy configurations through natural language commands.

    Supports actions: list, create, view, edit, update, remove, logs,
    backups, health_check
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
- Responses are `ToolResult` objects with assistant-friendly text plus structured content
- View and log actions intentionally return full requested content; list responses are paginated
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
- Responses formatted for AI assistant parsing and programmatic structured access
- Service instances are scoped to one tool invocation via async context management
- Error messages provide actionable feedback for users
- Success responses include relevant details for follow-up actions
