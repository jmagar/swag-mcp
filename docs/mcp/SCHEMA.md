# Tool Schema Documentation

## Overview

Tool schemas define the input validation contract for MCP tools. swag-mcp defines schemas using Pydantic models with annotated `Field()` descriptors in the tool function signature. FastMCP automatically exports these as JSON Schema for client-side validation.

## Schema definition pattern

Tool parameters are defined inline using `Annotated` types:

```python
@mcp.tool
async def swag(
    ctx: Context,
    action: Annotated[SwagAction, BeforeValidator(_coerce_action), Field(description="Action to perform")],
    config_name: Annotated[str, Field(default="", max_length=255, description="Configuration filename")],
    upstream_port: Annotated[int, Field(default=0, ge=0, le=65535, description="Port number")],
    ...
) -> ToolResult:
```

### Validation constraints

| Constraint | Used on | Purpose |
| --- | --- | --- |
| `max_length` | config_name (255), server_name (253), upstream_app (100) | Prevent oversized inputs |
| `ge`, `le` | upstream_port (0-65535), lines (1-1000), limit (1-200) | Range validation |
| `pattern` | upstream_app | Regex for valid container names/IPs |
| `BeforeValidator` | action | Coerce non-string types (booleans, nulls) before enum validation |

## Enum types

### SwagAction

```python
class SwagAction(StrEnum):
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

### BackupSubAction

```python
class BackupSubAction(StrEnum):
    CLEANUP = "cleanup"
    LIST = "list"
```

## Request models

Pydantic models in `swag_mcp/models/config.py` provide secondary validation for service-layer operations:

| Model | Used by | Key validations |
| --- | --- | --- |
| `SwagConfigRequest` | create | Required fields, proto enum, MCP upstream inheritance |
| `SwagEditRequest` | edit | Required config_name and new_content |
| `SwagUpdateRequest` | update | Required field/value, valid update_field enum |
| `SwagRemoveRequest` | remove | Required config_name |
| `SwagLogsRequest` | logs | Valid log_type enum |
| `SwagHealthCheckRequest` | health_check | Required domain, timeout bounds |

## JSON Schema export

FastMCP automatically exposes tool schemas via the MCP protocol's `tools/list` method. Clients receive the full JSON Schema including:

- Parameter descriptions
- Type constraints
- Default values
- Enum options
- Required fields

No manual schema export is needed.
