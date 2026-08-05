# Plugin Manifest Reference -- swag-mcp

Structure and conventions for plugin manifest files.

## File locations

| File | Platform | Purpose |
| --- | --- | --- |
| `.claude-plugin/plugin.json` | Claude Code | Plugin metadata, userConfig, MCP server |
| `.codex-plugin/plugin.json` | Codex CLI | Plugin metadata, skills, MCP, apps |
| `gemini-extension.json` | Gemini | Extension metadata, MCP server, settings |
| `server.json` | MCP Registry | Registry entry (`tv.nashost/swag-mcp`) |

## Claude Code manifest

`.claude-plugin/plugin.json`:

```json
{
  "name": "swag-mcp",
  "version": "1.0.1",
  "description": "SWAG reverse proxy configuration management via MCP.",
  "author": { "name": "Jacob Magar" },
  "repository": "https://github.com/jmagar/swag-mcp",
  "license": "MIT",
  "keywords": ["swag", "nginx", "reverse-proxy", "homelab", "mcp"],
  "mcpServers": "./plugins/swag-mcp/.mcp.json",
  "userConfig": {
    "swag_mcp_proxy_confs_path": { "type": "string" },
    "swag_mcp_proxy_confs_uri": { "type": "string" },
    "swag_mcp_url": { "type": "string" },
    "swag_mcp_token": { "type": "string", "sensitive": true },
    "swag_mcp_default_web_auth_method": { "type": "string" }
  }
}
```

## Codex CLI manifest

`.codex-plugin/plugin.json`:

```json
{
  "name": "swag-mcp",
  "version": "1.0.1",
  "skills": "./plugins/swag-mcp/skills/",
  "mcpServers": "./plugins/swag-mcp/.mcp.json",
  "apps": "./plugins/swag-mcp/.app.json",
  "interface": {
    "displayName": "SWAG MCP",
    "category": "Infrastructure",
    "capabilities": ["Read", "Write"]
  }
}
```

## Gemini extension

`gemini-extension.json`:

```json
{
  "name": "swag-mcp",
  "version": "1.0.1",
  "mcpServers": {
    "swag-mcp": {
      "command": "uv",
      "args": ["run", "python", "-m", "swag_mcp"],
      "cwd": "${extensionPath}"
    }
  },
  "settings": [
    { "envVar": "SWAG_MCP_PROXY_CONFS_PATH" },
    { "envVar": "SWAG_MCP_DEFAULT_WEB_AUTH_METHOD" }
  ]
}
```

## Version sync

All manifests must have the same version. The `just publish` recipe updates all 5 version-bearing files atomically.
