# Git Hook Configuration

Git hooks for swag-mcp. These run locally before each commit and are also enforced in CI.

## Setup

```bash
# Install lefthook
npm install -g @evilmartians/lefthook

# Install hooks
lefthook install

# Run all hooks manually
lefthook run pre-commit
```

## Configured hooks

From `lefthook.yml`:

| Hook | Purpose |
| --- | --- |
| `diff_check` | Detect trailing whitespace and merge conflict markers in staged diff |
| `yaml` | Validate staged YAML syntax |
| `lint` | Ruff linting |
| `format` | Ruff formatting |
| `typecheck` | `ty` type checking |
| `skills` | Validate skills |
| `env_guard` | Block `.env` commits |

## Session hooks

Separate from git hooks, swag-mcp has Claude Code session hooks defined in `hooks/hooks.json`:

SessionStart

The `sync-uv.sh` hook keeps the repository lockfile and persistent Python environment in sync at session start.



1. `` -- sets `.env` to `chmod 600`


These hooks run automatically during Claude Code sessions and prevent credential leaks.
