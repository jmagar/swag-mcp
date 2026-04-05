# Pre-commit Hook Configuration

Pre-commit hooks for swag-mcp. These run locally before each commit and are also enforced in CI.

## Setup

```bash
# Install pre-commit
uv add --dev pre-commit

# Install hooks
pre-commit install

# Run all hooks manually
pre-commit run --all-files
```

## Configured hooks

From `.pre-commit-config.yaml`:

| Hook | Purpose |
| --- | --- |
| `ruff` (check) | Linting with auto-fix |
| `ruff` (format) | Code formatting |
| `check-yaml` | YAML syntax validation |
| `check-json` | JSON syntax validation |
| `end-of-file-fixer` | Ensure files end with newline |
| `trailing-whitespace` | Remove trailing whitespace |
| `check-merge-conflict` | Detect merge conflict markers |
| `detect-private-key` | Prevent committing private keys |

## Session hooks

Separate from git pre-commit hooks, swag-mcp has Claude Code session hooks defined in `hooks/hooks.json`:

### SessionStart

1. `sync-env.sh` -- syncs userConfig to `.env`
2. `ensure-gitignore.sh` -- verifies `.gitignore` patterns

### PostToolUse (Write/Edit/Bash)

1. `fix-env-perms.sh` -- sets `.env` to `chmod 600`
2. `ensure-gitignore.sh` -- re-verifies `.gitignore` patterns

These hooks run automatically during Claude Code sessions and prevent credential leaks.
