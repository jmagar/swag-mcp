# SWAG MCP Tool Refactoring Plan - Complete & Updated

## Summary
Refactor the SWAG MCP tool to:
1. Use `config_name` (full filename) instead of `service_name` for CREATE action
2. Keep MCP designation with clearer parameter name `mcp_enabled` (boolean)
3. Rename `cleanup_backups` action to `backups` with sub-actions (cleanup, list)
4. Update logs action description from "Show SWAG docker container logs" to "Show SWAG logs"
5. Enhance edit action to support all create fields
6. Update all examples to natural language format

## Detailed Changes

### 1. Replace service_name with config_name in CREATE action

**Files to modify:**
- `swag_mcp/tools/swag.py` - Update parameter from service_name to config_name
- `swag_mcp/models/config.py` - Update SwagConfigRequest model
- `swag_mcp/services/swag_manager.py` - Update create_config method
- `swag_mcp/utils/validators.py` - Add config_name validator
- `swag_mcp/core/constants.py` - Add new validation patterns

**Key changes:**
- `config_name` must match pattern: `^[a-zA-Z0-9_-]+\.(subdomain|subfolder)\.conf$`
- Extract service_name and base config_type from config_name:
  - `jellyfin.subdomain.conf` → service_name="jellyfin", base_type="subdomain"
  - `plex.subfolder.conf` → service_name="plex", base_type="subfolder"
- Replace `config_type_create` with `mcp_enabled` (boolean, default=false)
- When `mcp_enabled=true`:
  - Use "mcp-subdomain" template if base_type is "subdomain"
  - Use "mcp-subfolder" template if base_type is "subfolder"

**Example usage:**
```
# Standard subdomain
"Create jellyfin.subdomain.conf for media.example.com using jellyfin:8096"
→ config_name="jellyfin.subdomain.conf", mcp_enabled=false

# MCP-enabled subdomain
"Create claude-mcp.subdomain.conf for ai.example.com using claude-mcp:8080 with MCP support"
→ config_name="claude-mcp.subdomain.conf", mcp_enabled=true
```

### 2. Rename cleanup_backups to backups with sub-actions

**Files to modify:**
- `swag_mcp/models/enums.py`:
  - Change `CLEANUP_BACKUPS = "cleanup_backups"` to `BACKUPS = "backups"`
  - Add new enum: `BackupSubAction` with values "cleanup" and "list"
- `swag_mcp/tools/swag.py`:
  - Replace `cleanup_backups` action with `backups`
  - Add `backup_action` parameter (required when action="backups")
  - Implement dispatch for cleanup vs list
- `swag_mcp/services/swag_manager.py`:
  - Keep existing `cleanup_old_backups` method
  - Add new `list_backups` method to return backup files with metadata
- All test files referencing cleanup_backups

**Implementation details:**
```python
# In enums.py
class SwagAction(str, Enum):
    ...
    BACKUPS = "backups"  # Replaces CLEANUP_BACKUPS
    ...

class BackupSubAction(str, Enum):
    CLEANUP = "cleanup"
    LIST = "list"

# In swag.py
elif action == SwagAction.BACKUPS:
    if backup_action == "cleanup":
        # Existing cleanup logic
    elif backup_action == "list":
        # New list logic
```

**Natural language examples:**
```
"Clean up backup files older than 7 days"
→ action="backups", backup_action="cleanup", retention_days=7

"List all backup files"
→ action="backups", backup_action="list"
```

### 3. Update logs action description

**Files to modify:**
- `swag_mcp/tools/swag.py` - Change docstring line 300:
  - FROM: `• logs: Show SWAG docker container logs`
  - TO: `• logs: Show SWAG logs`

### 4. Enhance edit action to support all create fields

**Files to modify:**
- `swag_mcp/tools/swag.py` - Add parameters to edit action:
  - server_name (optional)
  - upstream_app (optional)
  - upstream_port (optional)
  - upstream_proto (optional)
  - auth_method (optional)
  - enable_quic (optional)
- `swag_mcp/models/config.py` - Enhance SwagEditRequest model
- `swag_mcp/services/swag_manager.py` - Update edit_configuration method

**Implementation approach:**
- Edit action will parse existing config to extract current values
- Apply only the provided new values, preserving others
- Re-render template with merged configuration

### 5. Update all examples to natural language

**Files to modify:**
- `swag_mcp/tools/swag.py` - Docstring examples (lines 312-318)
- `README.md` - All example sections
- `CLAUDE.md` - All example sections
- All test files with hardcoded examples

**Example transformations:**

**CREATE:**
```
OLD: swag(action="create", service_name="jellyfin", server_name="media.example.com",
     upstream_app="jellyfin", upstream_port=8096)
NEW: "Create jellyfin.subdomain.conf for media.example.com using jellyfin:8096"
```

**LIST:**
```
OLD: swag(action="list", config_type="active")
NEW: "List all active proxy configurations"
```

**VIEW:**
```
OLD: swag(action="view", config_name="plex")
NEW: "Show the plex.subdomain.conf configuration"
```

**UPDATE:**
```
OLD: swag(action="update", config_name="crawler.subdomain.conf", update_field="port",
     update_value="8011")
NEW: "Update port for crawler.subdomain.conf to 8011"
```

**BACKUPS:**
```
OLD: swag(action="cleanup_backups", retention_days=7)
NEW: "Clean up backup files older than 7 days"
NEW: "List all backup files"
```

## File-by-File Changes

### swag_mcp/core/constants.py
```python
# Add new pattern
VALID_CONFIG_NAME_FORMAT = r"^[a-zA-Z0-9_-]+\.(subdomain|subfolder)\.conf$"
```

### swag_mcp/models/enums.py
```python
class SwagAction(str, Enum):
    ...
    BACKUPS = "backups"  # Replaces CLEANUP_BACKUPS
    ...

class BackupSubAction(str, Enum):
    """Sub-actions for backup management."""
    CLEANUP = "cleanup"
    LIST = "list"
```

### swag_mcp/models/config.py
```python
class SwagConfigRequest(BaseModel):
    config_name: str = Field(
        ...,
        pattern=VALID_CONFIG_NAME_FORMAT,
        description="Configuration filename (e.g., 'jellyfin.subdomain.conf')"
    )
    # Remove service_name field
    server_name: str = Field(...)
    upstream_app: str = Field(...)
    upstream_port: int = Field(...)
    upstream_proto: Literal["http", "https"] = Field(default="http")
    mcp_enabled: bool = Field(
        default=False,
        description="Enable MCP/SSE support for AI services"
    )
    auth_method: Literal["none", "ldap", "authelia", "authentik", "tinyauth"] = Field(...)
    enable_quic: bool = Field(default=False)

class SwagEditRequest(BaseModel):
    config_name: str = Field(...)
    new_content: str | None = Field(default=None)  # Make optional
    # Add all create fields as optional
    server_name: str | None = Field(default=None)
    upstream_app: str | None = Field(default=None)
    upstream_port: int | None = Field(default=None)
    upstream_proto: Literal["http", "https"] | None = Field(default=None)
    auth_method: Literal["none", "ldap", "authelia", "authentik", "tinyauth"] | None = Field(default=None)
    enable_quic: bool | None = Field(default=None)
    create_backup: bool = Field(default=True)

class SwagBackupRequest(BaseModel):
    backup_action: Literal["cleanup", "list"] = Field(...)
    retention_days: int | None = Field(default=None)  # Only for cleanup
```

### swag_mcp/tools/swag.py
Key parameter changes:
```python
async def swag(
    ctx: Context,
    action: SwagAction,
    # CREATE parameters
    config_name: str = "",  # Replaces service_name
    server_name: str = "",
    upstream_app: str = "",
    upstream_port: int = 0,
    upstream_proto: str = "http",
    mcp_enabled: bool = False,  # Replaces config_type_create
    auth_method: str = "authelia",
    enable_quic: bool = False,
    # BACKUPS parameters
    backup_action: str = "",  # New: "cleanup" or "list"
    retention_days: int = 0,
    # ... rest unchanged
)
```

### swag_mcp/services/swag_manager.py
```python
async def create_config(self, request: SwagConfigRequest) -> SwagConfigResult:
    # Extract service_name and base_type from config_name
    config_name = request.config_name  # e.g., "jellyfin.subdomain.conf"
    parts = config_name.rsplit('.', 2)  # ['jellyfin', 'subdomain', 'conf']
    service_name = parts[0]
    base_type = parts[1]  # 'subdomain' or 'subfolder'

    # Determine template based on base_type and mcp_enabled
    if request.mcp_enabled:
        template_type = f"mcp-{base_type}"  # mcp-subdomain or mcp-subfolder
    else:
        template_type = base_type  # subdomain or subfolder

    # Rest of implementation...

async def list_backups(self) -> List[Dict[str, Any]]:
    """List all backup files with metadata."""
    backup_files = []
    backup_pattern = "*" + BACKUP_MARKER + "*"

    for backup_path in self.config.proxy_confs_path.glob(backup_pattern):
        backup_files.append({
            "name": backup_path.name,
            "size_bytes": backup_path.stat().st_size,
            "modified_time": backup_path.stat().st_mtime,
            "original_config": backup_path.name.split(BACKUP_MARKER)[0]
        })

    return sorted(backup_files, key=lambda x: x['modified_time'], reverse=True)
```

## Testing Impact

**Test files to update:**
- `tests/test_swag_actions.py`:
  - Update all CREATE tests to use config_name instead of service_name
  - Update all CLEANUP_BACKUPS tests to use BACKUPS with backup_action
  - Add new tests for list_backups functionality
- `tests/test_validation.py`:
  - Add config_name format validation tests
  - Remove service_name validation tests
- `tests/test_integration.py`:
  - Update integration flows with new parameters
- `tests/test_error_handling.py`:
  - Update error scenarios for new parameter structure
- `tests/test_performance.py`:
  - Update performance tests for BACKUPS action
- `tests/test_mocking.py`:
  - Update all mocked calls

## Migration Notes

**Breaking changes:**
1. CREATE: `service_name` → `config_name` (must include .subdomain.conf or .subfolder.conf)
2. CREATE: `config_type_create` → `mcp_enabled` (boolean)
3. Action: `cleanup_backups` → `backups` with `backup_action` parameter
4. Examples: All changed from function calls to natural language

**Validation rules:**
- config_name must match: `^[a-zA-Z0-9_-]+\.(subdomain|subfolder)\.conf$`
- backup_action must be "cleanup" or "list" when action="backups"
- retention_days only valid when backup_action="cleanup"

## Implementation Order

1. **Phase 1: Core Changes** ✅
   - Add new constants and validation patterns ✅
   - Update enums (SwagAction, add BackupSubAction) ✅
   - Update models (SwagConfigRequest, SwagEditRequest, SwagBackupRequest)

2. **Phase 2: Service Layer**
   - Update create_config to extract service_name from config_name
   - Add list_backups method
   - Enhance edit_configuration for field updates

3. **Phase 3: Tool Layer**
   - Update swag.py parameters
   - Implement new dispatch logic for backups action
   - Update all docstrings and examples

4. **Phase 4: Documentation**
   - Update README.md with new examples
   - Update CLAUDE.md memory reference
   - Update inline documentation

5. **Phase 5: Testing**
   - Update all test files
   - Add new test cases for list_backups
   - Verify all tests pass

6. **Phase 6: Validation**
   - Manual testing with Docker deployment
   - Test backward compatibility scenarios
   - Performance validation

## Current Progress

- ✅ Added VALID_CONFIG_NAME_FORMAT constant
- ✅ Changed CLEANUP_BACKUPS to BACKUPS in SwagAction enum
- ✅ Added BackupSubAction enum
- 🚧 Currently updating SwagConfigRequest model
