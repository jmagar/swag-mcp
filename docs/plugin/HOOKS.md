# Hook Configuration - swag-mcp

## Overview

`swag-mcp` registers `SessionStart` and `ConfigChange` hooks in `plugins/swag-mcp/hooks/hooks.json`.
Plugin option values are projected into durable local files by `swag setup repair`.

## Hook definition

**File**: `plugins/swag-mcp/hooks/hooks.json`

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-setup.sh"
          },
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/bin/sync-uv.sh"
          }
        ]
      }
    ],
    "ConfigChange": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/scripts/plugin-setup.sh"
          }
        ]
      }
    ]
  }
}
```

## Behavior

- `scripts/plugin-setup.sh` maps `CLAUDE_PLUGIN_OPTION_*` values into real
  runtime env vars and runs `python -m swag_mcp setup repair`.
- `swag setup repair` creates or preserves `~/.swag-mcp/config.toml` from
  `config.example.toml`.
- It merge-updates `~/.swag-mcp/.env`, preserving existing secrets unless a new
  plugin option is provided, rejecting symlinked write targets, and setting
  `0600` permissions.
- `bin/sync-uv.sh` runs `uv sync` against the repo root for local development
  workflows.
- The installed virtual environment lives under the Claude plugin data directory
  when Claude provides a real path.
- If Claude provides no data path or an unexpanded placeholder, the hook falls
  back to `.cache/claude-plugin-data/.venv`.

## See Also

- [../GUARDRAILS.md](../GUARDRAILS.md) - Security patterns enforced by hooks
- [CONFIG.md](CONFIG.md) - Repository configuration and environment variables
