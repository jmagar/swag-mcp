# SWAG MCP Data Models - Claude Memory Reference

This directory contains Pydantic data models that define request/response schemas, validation rules, and enum types for all SWAG MCP operations.

## Directory Purpose

The `models/` module provides type-safe data structures using Pydantic v2 for:
- Request validation for all supported tool actions
- Enum definitions for tool actions and configuration options
- Custom validators for domain names, service names, and port ranges
- Consistent error handling and field constraints

## Key Files

### `enums.py` - Action and Configuration Enums
Defines the core SwagAction enum and configuration option enums:

```python
class SwagAction(str, Enum):
    """Supported SWAG MCP tool actions"""
    LIST = "list"
    CREATE = "create"
    VIEW = "view"
    EDIT = "edit"
    UPDATE = "update"
    REMOVE = "remove"
    LOGS = "logs"
    BACKUPS = "backups"
    HEALTH_CHECK = "health_check"
```

**Usage in Tools:**
```python
from swag_mcp.models.enums import SwagAction

# Action dispatch pattern
if action == SwagAction.CREATE:
    return await handle_create(...)
elif action == SwagAction.UPDATE:
    return await handle_update(...)
```

### `config.py` - Request and Result Models
Pydantic models validate action-specific requests and service-layer results. Public MCP responses are `ToolResult` objects formatted by `TokenEfficientFormatter`, not a single shared response model.

#### Core Request Models
```python
# Base request model with common fields
class SwagBaseRequest(BaseModel):
    action: SwagAction = Field(description="The action to perform")

class SwagConfigRequest(SwagBaseRequest):
    config_name: str = Field(
        description="Configuration filename",
        pattern=VALID_CONFIG_NAME_FORMAT
    )
    server_name: str = Field(
        description="Domain name",
        max_length=253,
        # Custom domain validator applied
    )
    upstream_app: str = Field(
        description="Container name or IP address",
        pattern=r"^[a-zA-Z0-9_.-]+$",
        max_length=100
    )
    upstream_port: int = Field(
        description="Port number",
        ge=1,
        le=65535
    )
    upstream_proto: str = Field(
        default="http",
        description="Protocol for upstream connection",
        pattern=r"^(http|https)$"
    )
    # ... additional fields with validation
```

#### Response Shape

The MCP layer returns `ToolResult(content=[TextContent(...)], structured_content={...})`. Structured content is action-specific:

| Action | Common structured keys |
| --- | --- |
| `list` | `items`, `total`, `limit`, `offset`, `has_more`, `configs`, `total_count`, `list_filter` |
| `create` | `success`, `filename`, `content`, `backup_created`, `health_check` |
| `view` | `success`, `filename`, `config_name`, `content`, `character_count` |
| `edit` | `success`, `backup_created` |
| `update` | `success`, `filename`, `backup_created`, `health_check`; `content` for `add_mcp` |
| `remove` | `success`, `backup_created` |
| `logs` | `logs`, `character_count` |
| `backups` | `backup_files`, `total_count` or `cleaned_count`, `retention_days` |
| `health_check` | `success`, `domain`, `status_code`, `response_time_ms`, `error`, `endpoint_results` |
| error | `success=false`, `error`, `action` |

## Action-Specific Models

### LIST Action Models
```python
class SwagListRequest(SwagBaseRequest):
    config_type: str = Field(
        default="all",
        description="Type of configurations to list",
        pattern=r"^(all|active|samples)$"
    )

class SwagConfigInfo(BaseModel):
    name: str = Field(description="Configuration filename")
    path: Path = Field(description="Full file path")
    size_bytes: int = Field(description="File size in bytes")
    modified_time: datetime = Field(description="Last modification time")
    is_sample: bool = Field(description="Whether file is a sample")
```

### CREATE Action Models
```python
class SwagConfigRequest(SwagBaseRequest):
    # Required fields
    config_name: str = Field(pattern=VALID_CONFIG_NAME_FORMAT)
    server_name: str = Field(max_length=253)  # Domain validation applied
    upstream_app: str = Field(pattern=VALID_UPSTREAM_PATTERN, max_length=100)
    upstream_port: int = Field(ge=1, le=65535)

    # Optional fields with defaults
    upstream_proto: Literal["http", "https"] = "http"
    mcp_upstream_app: str | None = None
    mcp_upstream_port: int | None = Field(default=None, ge=1, le=65535)
    mcp_upstream_proto: Literal["http", "https"] | None = None
    auth_method: str = "authelia"
    enable_quic: bool = Field(default=False, description="Enable QUIC support")
```

### UPDATE Action Models
```python
class SwagUpdateRequest(SwagBaseRequest):
    config_name: str = Field(pattern=r"^[a-zA-Z0-9_.-]+$", max_length=255)
    update_field: str = Field(pattern=r"^(port|upstream|app|add_mcp)$")
    update_value: str = Field(min_length=1)
    create_backup: bool = Field(default=True)

# Field-specific validation
# port: requires 1-65535
# upstream: requires app/container/IP only, without :port
# app: requires app:port and updates both upstream_app and upstream_port
# add_mcp: requires a valid MCP path such as /mcp
```

### HEALTH_CHECK Action Models
```python
class SwagHealthCheckRequest(SwagBaseRequest):
    domain: str = Field(
        description="Full domain to check health for",
        max_length=253
        # Domain format validation applied
    )
    timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Request timeout in seconds"
    )
    follow_redirects: bool = Field(
        default=True,
        description="Whether to follow HTTP redirects"
    )

class SwagHealthCheckResult(BaseModel):
    domain: str = Field(description="Domain that was checked")
    url: str = Field(description="URL that was checked")
    status_code: Optional[int] = Field(description="HTTP status code")
    response_time_ms: Optional[int] = Field(description="Response time")
    success: bool = Field(description="Whether the check succeeded")
    error: Optional[str] = Field(description="Error details if failed")
    endpoint_results: list[HealthEndpointResult] = Field(default_factory=list)
```

## Custom Validators

### Domain Name Validation
```python
from pydantic import field_validator
import re

@field_validator('server_name', 'domain')
def validate_domain_format(cls, v):
    """Validates domain name format according to RFC standards"""
    pattern = r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
    if not re.match(pattern, v):
        raise ValueError("Invalid domain format")
    if v.startswith('.') or v.endswith('.'):
        raise ValueError("Domain cannot start or end with '.'")
    return v.lower()  # Normalize to lowercase
```

### Config Name Validation
```python
@field_validator('config_name')
def validate_config_name(cls, v):
    """Validates configuration filenames for file safety"""
    if not v:
        raise ValueError("Config name cannot be empty")
    if v.startswith('-') or v.endswith('-'):
        raise ValueError("Config name cannot start or end with '-'")
    # Additional path traversal protection
    if '..' in v or '/' in v or '\\' in v:
        raise ValueError("Config name contains invalid characters")
    return v
```

## Model Usage Patterns

### Request Validation in Tools
```python
from swag_mcp.models.config import SwagConfigRequest

async def handle_create_action(ctx: Context, **kwargs):
    try:
        # Automatic validation from kwargs
        request = SwagConfigRequest(**kwargs)

        # All fields are now validated and typed
        async with SwagManagerService() as service:
            result = await service.create_config(
                request,
            )
        # request.server_name and request.upstream_port are already validated
        return result

    except ValidationError as e:
        raise ValueError(f"Validation error: {e.errors()}") from e
```

### Response Construction

Action handlers construct dictionaries and pass them to `TokenEfficientFormatter`, which builds the `ToolResult`. Do not add or document a universal response wrapper unless the formatter and handlers are changed together.

## Development Commands

### Model Testing
```bash
# Test all model validation
uv run pytest tests/test_validation.py -v

# Test specific action models
uv run pytest tests/test_validation.py::TestCreateValidation -v

# Test field validators
python -c "from swag_mcp.models.config import SwagConfigRequest; print(SwagConfigRequest.model_json_schema())"
```

### Schema Generation
```bash
# Generate JSON schema for API documentation
python -c "
from swag_mcp.models.config import SwagConfigRequest
print(SwagConfigRequest.model_json_schema())
"

# Validate example requests
python -c "
from swag_mcp.models.config import SwagConfigRequest
request = SwagConfigRequest(
    action='create',
    config_name='test.subdomain.conf',
    server_name='example.com',
    upstream_app='test-app',
    upstream_port=8080
)
print('Valid request:', request.model_dump())
"
```

## Important Notes

### Validation Behavior
- **Strict Typing**: All fields are validated at assignment time
- **Runtime Conversion**: Pydantic may coerce compatible input types, but handlers should pass typed values from the FastMCP signature
- **Error Aggregation**: Multiple validation errors collected and reported together
- **Custom Messages**: Field validators provide user-friendly error messages

### Performance Considerations
- **Model Caching**: Pydantic models are compiled for faster validation
- **Field Validation**: Complex validators (domain, regex) have performance cost
- **Memory Usage**: Large response models should use generators for lists

### Security Features
- **Input Sanitization**: All string fields validated for safety
- **Path Traversal Prevention**: Config names and upstream identifiers checked
- **Command Injection Protection**: Pattern matching prevents shell injection
- **Unicode Normalization**: Inputs normalized before validation; homograph detection is documented as a signal, not a hard block

### Common Gotchas
- **Enum String Values**: SwagAction enum values are strings, not integers
- **Optional vs Required**: Default values make fields optional, be explicit
- **Validation Order**: Field validators run after type conversion
- **Error Messages**: Validation errors are in Pydantic format, may need translation
