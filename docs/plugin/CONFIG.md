# Plugin Settings -- swag-mcp

Plugin configuration, user-facing settings, and environment sync.

## Configuration layers

swag-mcp has three configuration layers:

1. **Plugin userConfig** -- set via Claude Code plugin UI, synced to `.env` by hooks
2. **Environment variables** -- `.env` file or container environment
3. **Pydantic defaults** -- hardcoded in `SwagConfig` class

### Precedence

Plugin userConfig -> `.env` file -> container env -> Pydantic defaults

The `sync-env.sh` hook bridges layer 1 to layer 2 at session start.

## userConfig fields

Defined in `.claude-plugin/plugin.json`:

| Key | Type | Sensitive | Default | Description |
| --- | --- | --- | --- | --- |
| `swag_mcp_url` | string | no | `https://swag.tootie.tv/mcp` | MCP server URL |
| `swag_proxy_confs_path` | string | no | — | Local proxy-confs path |
| `swag_proxy_confs_uri` | string | no | — | SSH proxy-confs URI |
| `swag_mcp_token` | string | yes | — | Bearer token |

Sensitive fields are stored encrypted by the Claude Code plugin system.

## Environment mapping

| userConfig key | Environment variable |
| --- | --- |
| `swag_mcp_url` | Used directly by MCP client (not in `.env`) |
| `swag_proxy_confs_path` | `SWAG_MCP_PROXY_CONFS_PATH` |
| `swag_proxy_confs_uri` | `SWAG_MCP_PROXY_CONFS_URI` |
| `swag_mcp_token` | `SWAG_MCP_TOKEN` |

## Pydantic settings

The `SwagConfig` class in `swag_mcp/core/config.py` uses `pydantic-settings` with:

- `env_prefix = "SWAG_MCP_"` -- all variables prefixed
- `case_sensitive = False` -- case-insensitive matching
- `extra = "ignore"` -- unknown variables silently ignored
- `env_file = ".env"` -- reads `.env` from working directory

Empty strings are coerced to default values for `default_auth_method`, `host`, and `log_level`.
