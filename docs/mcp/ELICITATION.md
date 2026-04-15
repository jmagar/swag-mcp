# MCP Elicitation

Interactive credential and configuration entry via the MCP elicitation protocol.

## Overview

swag-mcp supports configuration via the Claude Code plugin `userConfig` system. When installed as a plugin, users are prompted for configuration values during setup.

## Elicitation fields

| Field | Key | Type | Sensitive | Description |
| --- | --- | --- | --- | --- |
| SWAG MCP Server URL | `swag_mcp_url` | string | no | URL of the MCP server endpoint |
| SWAG Proxy Configs Path | `swag_proxy_confs_path` | string | no | Local filesystem path to proxy-confs |
| SWAG Proxy Configs URI | `swag_proxy_confs_uri` | string | no | SSH URI for remote proxy-confs |
| MCP Server Bearer Token | `swag_mcp_token` | string | yes | Bearer token for authentication |

## Sync mechanism

The `sync-uv.sh` hook keeps the repository lockfile and persistent Python environment in sync at session start.

1. Reads userConfig values from the Claude Code plugin context
2. Writes them to `.env` with appropriate `SWAG_MCP_` prefixes
3. Uses `flock` for safe concurrent writes
4. Sets `chmod 600` on the `.env` file

This means users configure once via the plugin UI and the server picks up values from `.env` on next startup.

## Manual configuration

If not using the plugin system, copy `.env.example` to `.env` and edit directly:

```bash
cp .env.example .env
chmod 600 .env
```

See [CONFIG](../CONFIG.md) for the complete variable reference.
