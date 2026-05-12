# Architecture Overview -- swag-mcp

MCP server architecture patterns used in swag-mcp.

## Request flow

```
MCP Client (Claude Code / Gemini / etc.)
  |
  | MCP JSON-RPC (streamable-http or stdio)
  v
FastMCP Server (swag_mcp/server.py)
  |
  | Middleware Stack (7 layers)
  v
Tool Router (swag_mcp/tools/swag.py)
  |
  | match action
  v
Action Handler (swag_mcp/tools/handlers/*.py)
  |
  | Service call
  v
SwagManagerService (orchestrator)
  |
  | Delegates to sub-manager
  v
Sub-Manager (file_operations, template_manager, etc.)
  |
  | FilesystemBackend (local or SSH)
  v
Filesystem (local disk or remote SFTP)
```

## Middleware stack

Middleware executes in order (outermost first):

| Order | Middleware | Purpose |
| --- | --- | --- |
| 1 | Security error | Sanitize error messages, strip sensitive info |
| 2 | MCP error enhancement | Add MCP-specific error context |
| 3 | Error handling | Catch unhandled exceptions |
| 4 | Retry | Retry transient failures (if enabled) |
| 5 | Rate limiting | Token bucket rate limit (if enabled) |
| 6 | Timing | Performance monitoring, slow operation warnings |
| 7 | Logging | Request audit trail |

## Service layer

The `SwagManagerService` is the single orchestration point. It creates the appropriate filesystem backend based on configuration and delegates to 9 sub-managers:

```
SwagManagerService
  +-- FileOperations         File I/O, transactions, per-file locking
  +-- TemplateManager        Jinja2 rendering, sandboxed environment
  +-- ValidationService      Input validation, diff/preview
  +-- BackupManager          Backup create/cleanup/list
  +-- HealthMonitor          HTTP health checks, log retrieval
  +-- ResourceManager        MCP resource queries, sample listing
  +-- MCPOperations          MCP location block add/remove
  +-- ConfigFieldUpdaters    Field updates (port, upstream, app, add_mcp)
  +-- ConfigOperations       CRUD operations
```

## Filesystem abstraction

The `FilesystemBackend` protocol enables transparent local/remote access:

```
FilesystemBackend (Protocol)
  |-- LocalFilesystem       aiofiles + pathlib + subprocess tail
  |-- SSHFilesystem         asyncssh SFTP with lazy connect + auto-reconnect
```

Selection is determined by `SWAG_MCP_PROXY_CONFS_URI`:
- Starts with `/` or not set: LocalFilesystem
- Matches `[user@]host[:port]:/path`: SSHFilesystem

## Operational constraints

Service lifecycle

- Each `swag` tool call opens `SwagManagerService` with an async context manager and closes it before returning.
- Remote SSH/SFTP and HTTP health-check sessions are scoped to the request. Long-running clients should expect connection setup cost per operation.
- Handler timeouts protect expensive operations: create uses 180 seconds, edit uses 300 seconds, update uses 120 seconds, logs use 60 seconds, and health checks use the requested timeout plus a small buffer.

Filesystem safety

- File writes use atomic temp-file-and-rename behavior where supported by the backend.
- Per-file locks serialize concurrent changes to the same config file, but they do not make multi-file workflows transactional.
- Backup creation is part of destructive edit/update/remove paths; restore remains an operator workflow using the generated backup files.
- Nginx syntax validation depends on an available nginx binary or container context. Treat validation warnings or validation unavailability as operational risk before deployment.

Health and readiness

- The `/health` endpoint proves the MCP process is alive. It does not prove proxy-confs are writable, SSH is reachable, nginx validation is available, or SWAG can reload generated configs.
- The `health_check` action tests external HTTP reachability for a domain and records per-endpoint attempts, but it does not replace SWAG reload validation or auth-path testing.

## Template system

Single template: `templates/mcp.subdomain.conf.j2`

The template generates nginx server blocks with:
- SSL termination
- Auth method includes (authelia, authentik, etc.)
- MCP server sidecar via `mcp-server.conf` and streaming overrides via `mcp-location.conf`
- Health check endpoint
- Split routing support (main app + separate MCP upstream)
- DNS rebinding protection
- MCP protocol version headers

## Resources

Four MCP resources:
- `swag://` -- static directory listing
- `swag://configs/live` -- filesystem watcher stream
- `swag://health/stream` -- periodic health check stream
- `swag://logs/stream` -- live nginx error log stream
