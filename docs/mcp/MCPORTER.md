# Live Smoke Testing (mcporter)

End-to-end verification against a running swag-mcp server. Complements unit/integration tests in [TESTS](TESTS.md).

## Purpose

Smoke tests verify the full request path from MCP client through the server to the filesystem backend. They catch issues that unit tests cannot: transport problems, environment misconfiguration, and filesystem permission errors.

## Running smoke tests

### Using just

```bash
# Start server first
just dev

# Run live tests
just test-live
```

### Manually

```bash
bash tests/test_live.sh
```

## Test flow

The `test_live.sh` script performs:

1. **Health check** -- `GET /health`, expects `{"status": "healthy"}`
2. **List configs** -- `swag(action="list")`, expects a list response
3. **Create test config** -- creates a temporary config with a unique name
4. **View config** -- reads back the created config
5. **Update field** -- changes the upstream port
6. **Remove config** -- deletes the test config
7. **Verify cleanup** -- confirms the config no longer exists

Each step validates the response and exits on first failure.

## mcporter integration

The `config/mcporter.json` defines the tool contract for automated validation:

```json
{
  "tools": {
    "swag": {
      "actions": ["list", "create", "view", "edit", "update", "remove", "logs", "backups", "health_check"]
    },
    "swag_help": {}
  }
}
```

Use the contract check recipe to verify tool schema alignment:

```bash
just check-contract
# or: bash scripts/lint-plugin.sh
```

## Prerequisites

- Running swag-mcp server (local or Docker)
- Proxy-confs directory accessible and writable
- `curl` and `jq` installed
