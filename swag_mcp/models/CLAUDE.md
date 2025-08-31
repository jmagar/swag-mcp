# SWAG MCP Data Models - Claude Memory Reference

This directory contains Pydantic data models that define request/response schemas, validation rules, and enum types for all SWAG MCP operations.

## Directory Purpose

The `models/` module provides type-safe data structures using Pydantic v2 for:
- Request/response validation for all 10 tool actions
- Enum definitions for tool actions and configuration options
- Custom validators for domain names, service names, and port ranges
- Consistent error handling and field constraints

## Key Files

### `enums.py` - Action and Configuration Enums
Defines the core SwagAction enum and configuration option enums:

```python
class SwagAction(str, Enum):
    """All 10 supported SWAG MCP tool actions"""
    LIST = "list"
    CREATE = "create"
    VIEW = "view"
    EDIT = "edit"
    UPDATE = "update"
    CONFIG = "config"
    REMOVE = "remove"
    LOGS = "logs"
    CLEANUP_BACKUPS = "cleanup_backups"
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

### `config.py` - Request/Response Models
Comprehensive Pydantic models for each tool action with full validation:

#### Core Request Models
```python
# Base request model with common fields
class SwagBaseRequest(BaseModel):
    action: SwagAction = Field(description="The action to perform")

# CREATE action - most complex model
class SwagCreateRequest(SwagBaseRequest):
    service_name: str = Field(
        description="Service identifier for filename",
        pattern=r"^[\w-]+$",
        max_length=50
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

#### Response Models
```python
class SwagResponse(BaseModel):
    """Standard response format for all actions"""
    success: bool = Field(description="Operation success status")
    message: str = Field(description="Human-readable message")
    data: Optional[Dict[str, Any]] = Field(default=None, description="Response data")

class SwagListResponse(SwagResponse):
    """Specialized response for LIST action"""
    data: Optional[SwagListData] = Field(default=None)

class SwagListData(BaseModel):
    configs: List[SwagConfigInfo] = Field(description="Configuration file information")
    total_count: int = Field(description="Total configurations found")
    config_type_filter: Optional[str] = Field(description="Applied filter type")
```

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
class SwagCreateRequest(SwagBaseRequest):
    # Required fields
    service_name: str = Field(pattern=r"^[\w-]+$", max_length=50)
    server_name: str = Field(max_length=253)  # Domain validation applied
    upstream_app: str = Field(pattern=r"^[a-zA-Z0-9_.-]+$", max_length=100)
    upstream_port: int = Field(ge=1, le=65535)

    # Optional fields with defaults
    upstream_proto: str = Field(default="http", pattern=r"^(http|https)$")
    config_type_create: str = Field(
        default="subdomain",
        pattern=r"^(subdomain|subfolder|mcp-subdomain|mcp-subfolder)$"
    )
    auth_method: str = Field(
        default="authelia",
        pattern=r"^(none|ldap|authelia|authentik|tinyauth)$"
    )
    enable_quic: bool = Field(default=False, description="Enable QUIC support")
```

### UPDATE Action Models
```python
class SwagUpdateRequest(SwagBaseRequest):
    config_name: str = Field(pattern=r"^[a-zA-Z0-9_.-]+$", max_length=255)
    update_field: str = Field(pattern=r"^(port|upstream|app)$")
    update_value: str = Field(min_length=1)
    create_backup: bool = Field(default=True)

# Field-specific validation
@field_validator('update_value')
def validate_update_value(cls, v, values):
    field = values.get('update_field')
    if field == 'port':
        port = int(v)
        if not (1 <= port <= 65535):
            raise ValueError("Port must be 1-65535")
    return v
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

class SwagHealthCheckData(BaseModel):
    domain: str = Field(description="Domain that was checked")
    status_code: Optional[int] = Field(description="HTTP status code")
    response_time_ms: Optional[float] = Field(description="Response time")
    accessible: bool = Field(description="Whether domain is accessible")
    error_message: Optional[str] = Field(description="Error details if failed")
    redirect_url: Optional[str] = Field(description="Final URL after redirects")
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

### Service Name Validation
```python
@field_validator('service_name', 'config_name')
def validate_service_name(cls, v):
    """Validates service names for file safety"""
    if not v:
        raise ValueError("Service name cannot be empty")
    if v.startswith('-') or v.endswith('-'):
        raise ValueError("Service name cannot start or end with '-'")
    # Additional path traversal protection
    if '..' in v or '/' in v:
        raise ValueError("Service name contains invalid characters")
    return v
```

## Model Usage Patterns

### Request Validation in Tools
```python
from swag_mcp.models.config import SwagCreateRequest

async def handle_create_action(ctx: Context, **kwargs):
    try:
        # Automatic validation from kwargs
        request = SwagCreateRequest(**kwargs)

        # All fields are now validated and typed
        service = SwagManagerService(ctx.config)
        result = await service.create_configuration(
            service_name=request.service_name,
            server_name=request.server_name,  # Already validated domain
            upstream_port=request.upstream_port,  # Already validated port range
            # ...
        )
        return SwagResponse(success=True, message="Created successfully")

    except ValidationError as e:
        return SwagResponse(
            success=False,
            message=f"Validation error: {e.errors()}"
        )
```

### Response Construction
```python
def build_list_response(configs: List[ConfigInfo], config_type: str) -> SwagListResponse:
    """Build properly typed response for LIST action"""
    return SwagListResponse(
        success=True,
        message=f"Found {len(configs)} configurations",
        data=SwagListData(
            configs=[
                SwagConfigInfo(
                    name=config.name,
                    path=config.path,
                    size_bytes=config.size,
                    modified_time=config.modified,
                    is_sample=config.name.endswith('.sample')
                )
                for config in configs
            ],
            total_count=len(configs),
            config_type_filter=config_type
        )
    )
```

## Development Commands

### Model Testing
```bash
# Test all model validation
uv run pytest tests/test_validation.py -v

# Test specific action models
uv run pytest tests/test_validation.py::TestCreateValidation -v

# Test field validators
python -c "from swag_mcp.models.config import SwagCreateRequest; print(SwagCreateRequest.model_validate({...}))"
```

### Schema Generation
```bash
# Generate JSON schema for API documentation
python -c "
from swag_mcp.models.config import SwagCreateRequest
print(SwagCreateRequest.model_json_schema())
"

# Validate example requests
python -c "
from swag_mcp.models.config import SwagCreateRequest
request = SwagCreateRequest(
    action='create',
    service_name='test',
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
- **Automatic Conversion**: String ports converted to integers automatically
- **Error Aggregation**: Multiple validation errors collected and reported together
- **Custom Messages**: Field validators provide user-friendly error messages

### Performance Considerations
- **Model Caching**: Pydantic models are compiled for faster validation
- **Field Validation**: Complex validators (domain, regex) have performance cost
- **Memory Usage**: Large response models should use generators for lists

### Security Features
- **Input Sanitization**: All string fields validated for safety
- **Path Traversal Prevention**: Service names and config names checked
- **Command Injection Protection**: Pattern matching prevents shell injection
- **Unicode Normalization**: Domain names normalized to prevent spoofing

### Common Gotchas
- **Enum String Values**: SwagAction enum values are strings, not integers
- **Optional vs Required**: Default values make fields optional, be explicit
- **Validation Order**: Field validators run after type conversion
- **Error Messages**: Validation errors are in Pydantic format, may need translation
