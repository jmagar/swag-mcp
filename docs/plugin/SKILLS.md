# Skill Definitions -- swag-mcp

Patterns for defining skills (domain knowledge modules) within a Claude Code plugin.

## Directory structure

```
skills/
  swag/
    SKILL.md    # Client-facing skill definition
```

## SKILL.md

The skill file at `skills/swag/SKILL.md` defines:

- **Frontmatter**: `name` and `description` with trigger keywords
- **Mode detection**: MCP mode (preferred) vs HTTP fallback
- **Tool reference**: All actions with parameters and examples
- **Workflows**: Common task sequences (expose service, update backend, diagnose)
- **Destructive operations**: Warnings for remove and edit
- **Notes**: DNS requirements, auth method prerequisites, QUIC port requirements

### Trigger keywords

The skill activates when the user mentions:
- "add proxy config", "create reverse proxy"
- "SWAG config", "nginx proxy"
- "expose service", "proxy configuration"
- "subdomain config", "configure SWAG"
- "list proxy configs", "view proxy config"
- "check proxy health", "SWAG logs"
- "add domain", "configure SSL"
- Any mention of SWAG, reverse proxy, or nginx configuration

### MCP mode

When the `mcp__swag-mcp__swag` tool is available, the skill uses it directly. The server manages nginx config files on the filesystem (local or remote).

### HTTP fallback

No meaningful curl equivalent exists for SWAG config management. If the MCP server is unavailable, the skill surfaces the issue and suggests restarting it.
