# Plugin Settings -- swag-mcp

Plugin configuration and user-facing settings for stdio deployment.

## How it works

Claude Code plugins use a two-layer config model:

1. **`plugin.json`** -- declares `userConfig` fields that Claude Code prompts for at install time
2. **`.mcp.json`** -- references those fields as `${userConfig.<key>}` in the `env` section

No `.env` file is needed for plugin deployment. Claude Code handles interpolation directly.

## Deployment topologies

swag-mcp supports two plugin deployment topologies:

| Entry | Transport | When to use |
| --- | --- | --- |
| `swag-mcp` (stdio) | stdio | SWAG configs accessible locally or via SSH from this machine |
| `swag-mcp-remote` (mcp-remote) | HTTP gateway | SWAG MCP server running on a remote Docker host |

The stdio entry is the default for plugin installs. The mcp-remote entry is available in `.mcp.json` for users who run swag-mcp as a remote Docker service.

## userConfig fields

| Key | Title | Sensitive | Purpose |
| --- | --- | --- | --- |
| `swag_proxy_confs_path` | SWAG Proxy Configs Path | no | Local path to proxy-confs directory |
| `swag_proxy_confs_uri` | SWAG Proxy Configs URI | yes | SSH URI for remote access (key-auth only) |

One of `swag_proxy_confs_path` or `swag_proxy_confs_uri` is required.

### SSH URI security

The `swag_proxy_confs_uri` field is marked `sensitive: true`. Only SSH-key authentication is supported -- password-in-URI is NOT supported and is a security risk. The URI format is: `[user@]host[:port]:/absolute/path`.

## Hardcoded defaults in .mcp.json

| Variable | Value | Reason |
| --- | --- | --- |
| `SWAG_MCP_NO_AUTH` | `true` | No HTTP auth needed for stdio |
| `SWAG_MCP_LOG_LEVEL` | `INFO` | Sensible default |
| `SWAG_MCP_LOG_FILE_ENABLED` | `false` | Avoid file writes in plugin context |
| `SWAG_MCP_DEFAULT_AUTH_METHOD` | `authelia` | Standard default |

## SessionStart hook

The `sync-uv.sh` hook runs at session start to keep Python dependencies in sync:

```
hooks/hooks.json -> bin/sync-uv.sh
  --> uv sync --project ${CLAUDE_PLUGIN_ROOT}
  --> venv at ${CLAUDE_PLUGIN_DATA}/.venv
```

## Cross-references

- [HOOKS.md](HOOKS.md) -- Hook definitions
- [CONFIG](../CONFIG.md) -- Full environment variable reference
- [ENV](../mcp/ENV.md) -- Transport-specific variable details
