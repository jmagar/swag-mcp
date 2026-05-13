# MCP Elicitation

Interactive credential and configuration entry via the MCP elicitation protocol.

## Overview

swag-mcp supports configuration via the Claude Code plugin `userConfig` system. When installed as a plugin, users are prompted for configuration values during setup.

## Elicitation fields

| Field | Key | Type | Sensitive | Description |
| --- | --- | --- | --- | --- |
| SWAG MCP URL | `SWAG_MCP_URL` | string | no | Public HTTP MCP endpoint including `/mcp` |
| SWAG MCP Token | `SWAG_MCP_TOKEN` | string | yes | Bearer token for HTTP MCP requests |
| SWAG Proxy Configs Path | `SWAG_MCP_PROXY_CONFS_PATH` | string | no | Container/local path where SWAG proxy configs are mounted |
| SWAG Proxy Configs URI | `SWAG_MCP_PROXY_CONFS_URI` | string | no | Optional local path or SSH URI for SWAG proxy configs |
| Default Web Endpoint Auth Method | `SWAG_MCP_DEFAULT_WEB_AUTH_METHOD` | string | no | Default SWAG/nginx auth for generated web endpoints, not MCP auth |

## Sync mechanism

Claude Code prompts for `swag_mcp_url` and `swag_mcp_token`, then interpolates those values into `plugins/swag-mcp/.mcp.json`.
The plugin connects to `${user_config.swag_mcp_url}` with an
`Authorization: Bearer ${user_config.swag_mcp_token}` header.

## Manual configuration

If not using the plugin system, copy `.env.example` to `.env` and edit directly:

```bash
cp .env.example .env
chmod 600 .env
```

See [CONFIG](../CONFIG.md) for the complete variable reference.
