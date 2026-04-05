# Hook Configuration -- swag-mcp

Lifecycle hooks that run automatically during Claude Code sessions.

## File location

`hooks/hooks.json`

## Hook definitions

### SessionStart

Runs once when a Claude Code session begins.

| Script | Timeout | Purpose |
| --- | --- | --- |
| `hooks/scripts/sync-env.sh` | 10s | Sync userConfig values to `.env` file |
| `hooks/scripts/ensure-gitignore.sh` | 5s | Verify `.gitignore` contains security patterns |

### PostToolUse

Runs after Write, Edit, MultiEdit, or Bash tool calls.

| Script | Timeout | Purpose |
| --- | --- | --- |
| `hooks/scripts/fix-env-perms.sh` | 5s | Reset `.env` to `chmod 600` if it exists |
| `hooks/scripts/ensure-gitignore.sh` | 5s | Re-verify `.gitignore` patterns |

## Hook scripts

### sync-env.sh

- Reads userConfig values from the Claude Code plugin context
- Writes `SWAG_MCP_*` variables to `.env`
- Uses `awk` for parsing (not `sed`) for reliability
- Uses `flock` for safe concurrent writes
- Creates `.env` from `.env.example` if missing
- Sets `chmod 600` on the result

### ensure-gitignore.sh

- Checks `.gitignore` for required patterns: `.env`, `*.secret`, `credentials.*`
- Supports `--check` mode (exits non-zero without modifying the file)
- Adds missing patterns if not in check mode

### fix-env-perms.sh

- Sets `.env` to `chmod 600` if the file exists
- No-op if `.env` does not exist
- Prevents accidental permission loosening after edits

### ensure-ignore-files.sh

- Verifies both `.gitignore` and `.dockerignore` contain required patterns
- Separate from `ensure-gitignore.sh` to cover Docker-specific patterns

## Matcher

PostToolUse hooks use the matcher `Write|Edit|MultiEdit|Bash` to run only after tools that could modify files.
