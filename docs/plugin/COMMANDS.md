# Slash Commands -- swag-mcp

Patterns for defining user-invocable slash commands in Claude Code.

## Current status

swag-mcp does not define any slash commands. All operations are handled through the `swag` MCP tool, which the user invokes via natural language.

## When to add commands

Consider adding slash commands when:
- A frequent operation benefits from a short alias
- The operation has a fixed parameter pattern
- Users need a discoverable entry point in the autocomplete menu

Potential future commands:
- `/swag:list` -- quick list of active configs
- `/swag:health` -- health check all proxied domains
- `/swag:create <service>` -- guided config creation
