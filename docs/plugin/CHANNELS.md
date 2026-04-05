# Channel Integration -- swag-mcp

Bidirectional messaging between Claude Code and external services.

## Current status

swag-mcp does not define any channels. The MCP server handles all communication via the standard MCP protocol (tool calls and resources).

## When to add channels

Consider adding channels when:
- Real-time notifications need to reach an external system (Discord, Slack, Gotify)
- External events should trigger MCP operations
- Bidirectional communication is needed beyond request/response

Potential future channels:
- **Gotify channel** -- push notifications when proxy configs change or health checks fail
- **Synapse channel** -- receive Docker events and auto-update proxy configs for new containers
