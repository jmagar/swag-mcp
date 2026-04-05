# Marketplace Publishing -- swag-mcp

Registration and publishing patterns for Claude, Codex, and Gemini marketplaces.

## Marketplace locations

| Platform | Manifest | Registry name |
| --- | --- | --- |
| Claude Code | `.claude-plugin/plugin.json` | `jmagar/claude-homelab` marketplace |
| Codex CLI | `.codex-plugin/plugin.json` | `jmagar/claude-homelab` marketplace |
| Gemini | `gemini-extension.json` | Gemini extension registry |
| MCP Registry | `server.json` | `tv.tootie/swag-mcp` |

## Claude Code marketplace

swag-mcp is published as part of the `jmagar/claude-homelab` marketplace. Install with:

```bash
/plugin marketplace add jmagar/claude-homelab
/plugin install swag-mcp @jmagar-claude-homelab
```

The marketplace entry is defined in `claude-homelab/.claude-plugin/marketplace.json` as an external repo-sourced plugin (not a bundled skill).

## MCP Registry

The `server.json` file defines the public MCP registry entry:

- **Name**: `tv.tootie/swag-mcp`
- **Registry**: PyPI
- **Identifier**: `swag-mcp`
- **Transport**: stdio (via `uvx swag-mcp`)
- **DNS verification**: `tootie.tv` domain

## PyPI

Published as `swag-mcp` on PyPI. Install with:

```bash
pip install swag-mcp
# or run directly
uvx swag-mcp
```

## Docker (GHCR)

Published as `ghcr.io/jmagar/swag-mcp`. Pull with:

```bash
docker pull ghcr.io/jmagar/swag-mcp:latest
```

## Version coordination

All marketplace manifests must have the same version. Use `just publish` to update all files atomically. See [PUBLISH](../mcp/PUBLISH.md) for the release workflow.
