# MCP UI Patterns

Protocol-level UI hints for MCP servers to improve client-side rendering of tools and results.

## Progress reporting

swag-mcp uses `ctx.info()` to send progress messages during long operations. MCP clients display these as status updates:

```python
await ctx.info("Validating configuration parameters...")
await ctx.info("Creating proxy configuration...")
await ctx.info("Running health verification...")
await ctx.info("Configuration created successfully")
```

Each action reports at least a start and completion message. Create and update actions include intermediate steps.

## Token-efficient output

All tool results are formatted by `TokenEfficientFormatter` to minimize token consumption. The formatter produces compact representations:

- **List results**: Tabular format with config names and status
- **Create results**: Filename, content preview, backup status, health check result
- **View results**: Full config content with filename header
- **Error results**: Action name, error message, no stack traces

## Action categorization

| Action | Category | Client rendering hint |
| --- | --- | --- |
| `list` | Read | Table/list view |
| `create` | Write | Success banner with health check |
| `view` | Read | Code block (nginx syntax) |
| `edit` | Write | Diff view or success confirmation |
| `update` | Write | Field change summary + health check |
| `remove` | Destructive | Warning banner with backup confirmation |
| `logs` | Read | Log viewer (monospace) |
| `backups` | Read/Write | List or cleanup summary |
| `health_check` | Read | Status indicator (pass/fail) |

## Error presentation

Errors include the action that failed and a sanitized message:

```
Error in 'create': Configuration 'app.subdomain.conf' already exists
```

Security-sensitive details (file paths, template expressions, internal errors) are stripped by the security error middleware before reaching the client.
