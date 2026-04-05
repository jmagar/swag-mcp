# Coding Rules -- swag-mcp

Standards and conventions enforced across the repository.

## Git workflow

- `main` branch is production-ready
- Feature branches for all changes
- PR required before merge
- CI must pass (lint, typecheck, test)

### Commit conventions

```
<type>(<scope>): <description>
```

| Type | Use |
| --- | --- |
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code restructuring |
| `test` | Adding or fixing tests |
| `chore` | Maintenance, dependencies |
| `release` | Version bump and tag |

## Python standards

- **Python 3.11+** minimum
- **Ruff** for linting and formatting (line length 100)
- **ty** for type checking (not mypy)
- **Google-style docstrings** on all public functions
- **Type hints** on all function signatures
- **f-strings** for string formatting
- **async/await** for all I/O operations
- No `any` types unless unavoidable (type-checked exceptions in `tool_decorators.py` and `mcp_cache.py`)

### Ruff configuration

From `pyproject.toml`:
- Select: E, W, F, I, N, D, UP, B, C4, SIM, TCH
- Ignore: D100 (module docstrings), D104 (package docstrings), D213, D203
- Tests: no docstring requirements

### Import ordering

Ruff `isort` rules:
1. Standard library
2. Third-party packages
3. Local application imports

## File conventions

- All bash scripts: `set -euo pipefail`
- All bash scripts: executable (`chmod +x`)
- `.env`: always `chmod 600`
- Config files: JSON with 2-space indent
- Markdown: ATX headers, no trailing spaces

## Version management

All version-bearing files must stay in sync:
- `pyproject.toml`
- `.claude-plugin/plugin.json`
- `.codex-plugin/plugin.json`
- `gemini-extension.json`
- `server.json`

Use `just publish` to update atomically. See [PUBLISH](../mcp/PUBLISH.md).

## Security rules

- Never commit `.env` or credential files
- Never log tokens or API keys
- Sanitize error messages before returning to clients
- Validate all user input via Pydantic models
- Atomic file writes only (temp + rename)
- Per-file locking for concurrent access
