# Plugin Settings -- swag-mcp

Plugin configuration and user-facing settings for native HTTP deployment.

## How it works

Claude Code plugins use a two-layer config model:

1. **`plugin.json`** -- declares `userConfig` fields that Claude Code prompts for at install time
2. **Hooks** -- receive those values as `CLAUDE_PLUGIN_OPTION_*`, map them to
   runtime env vars, and run `swag setup repair`
3. **Local files** -- `~/.swag-mcp/config.toml` holds preferences and
   `~/.swag-mcp/.env` holds runtime values and secrets

Claude Code connects directly to the server's streamable-HTTP endpoint. No
`mcp-remote` adapter is used.

## Deployment topologies

swag-mcp supports one plugin deployment topology:

| Entry | Transport | When to use |
| --- | --- | --- |
| `swag-mcp` | http | SWAG MCP server running locally or on a remote host |

The plugin connects to `SWAG_MCP_URL` and sends `Authorization: Bearer <SWAG_MCP_TOKEN>`.

## userConfig fields

| Key | Title | Sensitive | Purpose |
| --- | --- | --- | --- |
| `swag_mcp_proxy_confs_path` | SWAG Proxy Configs Path | no | Container/local path where SWAG proxy configs are mounted |
| `swag_mcp_proxy_confs_uri` | SWAG Proxy Configs URI | no | Optional local path or SSH URI for SWAG proxy configs |
| `swag_mcp_swag_log_base_path` | SWAG Log Base Path | no | Base path for SWAG logs |
| `swag_mcp_log_directory` | SWAG MCP Log Directory | no | Server log directory |
| `swag_mcp_host` | SWAG MCP Host | no | Server bind interface |
| `swag_mcp_port` | SWAG MCP Port | no | Published HTTP server port |
| `swag_mcp_url` | SWAG MCP URL | no | Public HTTP MCP endpoint including `/mcp` |
| `swag_mcp_token` | SWAG MCP Token | yes | Bearer token for HTTP MCP requests |
| `swag_mcp_default_web_auth_method` | Default Web Endpoint Auth Method | no | Default SWAG/nginx auth for generated web endpoints, not MCP auth |
| `fastmcp_server_auth_google_client_secret` | Google OAuth Client Secret | yes | Optional FastMCP Google OAuth secret |

`SWAG_MCP_URL` should include `/mcp` exactly once, for example `https://swag.example.com/mcp` or `http://localhost:49152/mcp`.

## Setup repair

`scripts/plugin-setup.sh` runs at `SessionStart` and `ConfigChange`:

```
plugins/swag-mcp/hooks/hooks.json -> scripts/plugin-setup.sh
  --> CLAUDE_PLUGIN_OPTION_* -> runtime env vars
  --> python -m swag_mcp setup repair
  --> ~/.swag-mcp/config.toml from config.example.toml when missing
  --> merge-updated ~/.swag-mcp/.env with 0600 permissions
```

The env writer is merge-based: existing secrets are preserved when plugin
options are absent, and supplied plugin options intentionally replace the
corresponding managed keys. Symlinked config targets are rejected.

## Cross-references

- [HOOKS.md](HOOKS.md) -- Hook definitions
- [CONFIG](../CONFIG.md) -- Full environment variable reference
- [ENV](../mcp/ENV.md) -- Transport-specific variable details
