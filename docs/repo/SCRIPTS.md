# Scripts Reference -- swag-mcp

Scripts used for maintenance, hooks, and testing.

## Maintenance scripts (`scripts/`)

| Script | Purpose | Usage |
| --- | --- | --- |
| `lint-plugin.sh` | Verify plugin manifest contract against actual tools | `just check-contract` |
| `smoke-test.sh` | Quick smoke test against running server | `bash scripts/smoke-test.sh` |

### lint-plugin.sh

Checks that the MCP tools exposed by the server match the contract defined in `config/mcporter.json`. Catches drift between tool implementation and declared capabilities.

### smoke-test.sh

Minimal health and tool availability check:
1. Hits `/health` endpoint
2. Verifies JSON response format
3. Confirms server version

## Hook scripts (`hooks/scripts/`)

| Script | Trigger | Purpose |
| --- | --- | --- |
| `sync-env.sh` | SessionStart | Sync plugin userConfig to `.env` |
| `fix-env-perms.sh` | PostToolUse | Set `.env` to `chmod 600` |
| `ensure-gitignore.sh` | SessionStart, PostToolUse | Verify `.gitignore` patterns |
| `ensure-ignore-files.sh` | PostToolUse | Verify `.dockerignore` patterns |

### sync-env.sh

- Uses `awk` (not `sed`) for reliable `.env` file manipulation
- Applies `flock` for safe concurrent writes
- Creates `.env` from `.env.example` if missing
- Only updates variables that have changed

### fix-env-perms.sh

- Runs after file modifications (Write, Edit, Bash tools)
- Ensures `.env` stays at `chmod 600`
- No-op when `.env` does not exist

### ensure-gitignore.sh

- Verifies `.gitignore` includes `.env`, `*.secret`, credential patterns
- Supports `--check` mode for CI (exits non-zero without modification)
- Adds missing patterns in normal mode

## Test scripts (`tests/`)

| Script | Purpose | Usage |
| --- | --- | --- |
| `test_live.sh` | Full CRUD integration test | `just test-live` |
| `mcporter/test-tools.sh` | mcporter tool contract test | `bash tests/mcporter/test-tools.sh` |

### test_live.sh

End-to-end test that creates, views, updates, and removes a test configuration. Requires a running server. See [MCPORTER](../mcp/MCPORTER.md) for details.

## Installation scripts

| Script | Purpose |
| --- | --- |
| `install.sh` | Full installation script (clone, install deps, configure, start) |
| `entrypoint.sh` | Docker container entrypoint (startup validation) |
