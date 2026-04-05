# Common MCP Code Patterns

Reusable patterns used in the swag-mcp server implementation.

## Unified action router

All operations go through a single `swag` tool using Python match/case:

```python
match action:
    case SwagAction.LIST:
        return await _handle_list_action(ctx, swag_service, formatter, ...)
    case SwagAction.CREATE:
        return await _handle_create_action(ctx, swag_service, formatter, ...)
    ...
```

Each action has a dedicated handler in `swag_mcp/tools/handlers/`.

## Service orchestration

The `SwagManagerService` delegates to 9 specialized sub-managers:

| Sub-manager | Responsibility |
| --- | --- |
| `FileOperations` | File I/O, transactions, per-file locking |
| `TemplateManager` | Jinja2 rendering with sandboxed environment |
| `ValidationService` | Input validation, diff/preview |
| `BackupManager` | Backup creation, cleanup, listing |
| `HealthMonitor` | HTTP health checks, log retrieval |
| `ResourceManager` | MCP resource and sample queries |
| `MCPOperations` | MCP location block operations |
| `ConfigFieldUpdaters` | Field-level updates (port, upstream, app, add_mcp) |
| `ConfigOperations` | Create, read, edit, remove operations |

## Filesystem abstraction

A `FilesystemBackend` protocol allows transparent local/remote access:

```python
@runtime_checkable
class FilesystemBackend(Protocol):
    async def read_text(self, path: str) -> str: ...
    async def write_text(self, path: str, content: str) -> None: ...
    async def exists(self, path: str) -> bool: ...
    async def glob(self, directory: str, pattern: str) -> list[str]: ...
    ...
```

Two implementations:
- `LocalFilesystem` -- uses `aiofiles` and `pathlib`
- `SSHFilesystem` -- uses `asyncssh` with lazy connection and auto-reconnect

## Atomic file writes

Both backends use a temp-file-then-rename pattern:

```python
temp_path = f"{path}.tmp.{os.getpid()}"
# Write to temp file
await sftp.open(temp_path, "wb") ...
# Atomic rename
await sftp.rename(temp_path, path)
```

## Error handling decorator

The `@handle_tool_errors` decorator wraps tool handlers:

```python
@mcp.tool
@handle_tool_errors
async def swag(ctx: Context, action: ..., ...) -> ToolResult:
```

Catches exceptions and returns formatted error results via `TokenEfficientFormatter`.

## Progress reporting

Actions report progress via `ctx.info()` for client-side display:

```python
await ctx.info("Validating configuration parameters...")
await ctx.info("Creating proxy configuration...")
await ctx.info("Running health verification...")
```

## Token-efficient formatting

All tool results go through `TokenEfficientFormatter` which produces compact output optimized for LLM token consumption. Different formatters exist per action type (list, create, view, edit, etc.).

## Post-action health checks

Create and update actions automatically run HTTP health checks against the configured `server_name`:

```python
health_check_result = await _run_post_create_health_check(
    swag_service, ctx, server_name, result.filename
)
```

This provides immediate feedback on whether the new/updated proxy configuration is working.
