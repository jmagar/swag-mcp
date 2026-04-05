# Agent Definitions -- swag-mcp

Patterns for defining autonomous agents within a Claude Code plugin.

## Current status

swag-mcp does not define any agents. All operations are handled through the `swag` tool via MCP.

## When to add agents

Consider adding an agent when a workflow requires:
- Multi-step orchestration across multiple services
- Decision-making based on intermediate results
- Long-running background operations
- Cross-plugin coordination

Potential future agents:
- **SWAG migration agent** -- batch-migrate proxy configs between SWAG instances
- **Config audit agent** -- review all proxy configs for security issues, outdated settings
- **Certificate renewal monitor** -- watch Let's Encrypt renewal logs and alert on failures
