# Tool Schema Documentation

## Overview

Tool schemas define the transport-level input contract for MCP tools. swag-mcp defines the public `swag` tool schema using annotated `Field()` descriptors in the tool function signature. FastMCP exports that single broad function as JSON Schema for client-side validation.

Action-specific requirements are enforced after dispatch by handler checks and Pydantic request models. The exported JSON Schema can validate universal types, defaults, enum values, ranges, and string patterns, but it does not express conditional requirements such as "`config_name` is required only when `action=view`" or "`update_value` format depends on `update_field`".

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

### Transport-level constraints

| Constraint | Used on | Purpose |
| --- | --- | --- |
| `max_length` | config_name (255), server_name (253), upstream_app (100) | Prevent oversized inputs |
| `ge`, `le` | upstream_port (0-65535), lines (1-1000), limit (1-200) | Range validation |
| `pattern` | upstream_app | Regex for valid container names/IPs |
| `BeforeValidator` | action | Reject null/boolean actions before enum validation and coerce other values to strings |

These constraints are always present in the FastMCP tool schema. They are intentionally permissive for fields that belong to other actions, because the unified `swag` tool exposes one parameter set for all actions.

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

Pydantic models in `swag_mcp/models/config.py` provide action-level validation after the handler has selected an action:

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

For `swag`, the only universally required field is `action`. Per-action required fields are documented in [TOOLS.md](TOOLS.md) and validated at runtime by the corresponding handler/model. Clients should not assume the exported schema will reject a missing `config_name`, `domain`, or `new_content` before the tool call reaches the server.

No manual schema export is needed.
