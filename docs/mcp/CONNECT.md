# Connect to MCP

How to connect to the swag-mcp MCP server from every supported client and transport.

## Claude Code (plugin)

Install from the homelab marketplace:

```bash
/plugin marketplace add jmagar/claude-homelab
/plugin install swag-mcp @jmagar-claude-homelab
```

Configure userConfig when prompted:
- **SWAG MCP Server URL**: `https://swag.tootie.tv/mcp` (or your server URL)
- **SWAG Proxy Configs Path**: `/mnt/appdata/swag/nginx/proxy-confs`
- **SWAG Proxy Configs URI**: `admin@swag-server:/path/to/proxy-confs` (for SSH mode)

## Claude Code (manual MCP config)

Add to `.mcp.json` in your project or `~/.claude.json`:

### HTTP transport

```json
{
  "mcpServers": {
    "swag-mcp": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Stdio transport

```json
{
  "mcpServers": {
    "swag-mcp": {
      "command": "uv",
      "args": ["run", "python", "-m", "swag_mcp"],
      "cwd": "/path/to/swag-mcp",
      "env": {
        "SWAG_MCP_PROXY_CONFS_PATH": "/mnt/appdata/swag/nginx/proxy-confs"
      }
    }
  }
}
```

## Gemini (extension)

The `gemini-extension.json` manifest configures stdio transport:

```json
{
  "mcpServers": {
    "swag-mcp": {
      "command": "uv",
      "args": ["run", "python", "-m", "swag_mcp"],
      "cwd": "${extensionPath}"
    }
  }
}
```

Settings configured via the extension settings UI:
- `SWAG_MCP_PROXY_CONFS_PATH`: Path to proxy-confs directory
- `SWAG_MCP_DEFAULT_AUTH_METHOD`: Default auth method

## Codex CLI

The `.codex-plugin/plugin.json` provides discovery metadata. Configure the MCP server via `.mcp.json`:

```json
{
  "mcpServers": {
    "swag-mcp": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

## MCP Inspector

For testing and debugging:

```bash
# Start the server
just dev

# In another terminal, use fastmcp dev
fastmcp dev swag_mcp/server.py
```

## Verifying the connection

After connecting, call `swag_help` to confirm the tools are available:

```
swag_help()
```

Then test with a list operation:

```
swag(action="list", list_filter="active")
```
