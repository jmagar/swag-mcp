# Justfile Recipes -- swag-mcp

Standard task runner recipes. Run `just --list` to see all available recipes.

## Development

| Recipe | Command | Description |
| --- | --- | --- |
| `just dev` | `uv run python -m swag_mcp` | Start development server |
| `just lint` | `uv run ruff check .` | Run linter |
| `just fmt` | `uv run ruff format .` | Format code |
| `just typecheck` | `uv run ty check` | Type checking |
| `just test` | `uv run pytest` | Run test suite |
| `just setup` | copy `.env.example`, `uv sync --all-extras --dev` | Initial project setup |
| `just clean` | remove cache/build artifacts | Clean build outputs |

## Docker

| Recipe | Command | Description |
| --- | --- | --- |
| `just build` | `docker build -t swag-mcp .` | Build Docker image |
| `just up` | `docker compose up -d` | Start containers |
| `just down` | `docker compose down` | Stop containers |
| `just restart` | `docker compose restart` | Restart containers |
| `just logs` | `docker compose logs -f` | Stream container logs |
| `just health` | `curl http://localhost:8082/health` | Check server health |

## Testing

| Recipe | Command | Description |
| --- | --- | --- |
| `just test` | `uv run pytest` | Run unit/integration tests |
| `just test-live` | `bash tests/test_live.sh` | Run live smoke tests |

## Validation

| Recipe | Command | Description |
| --- | --- | --- |
| `just check-contract` | `bash scripts/lint-plugin.sh` | Check plugin contract drift |
| `just validate-skills` | check `skills/swag/SKILL.md` exists | Validate skill files |

## Utilities

| Recipe | Command | Description |
| --- | --- | --- |
| `just gen-token` | Python secrets.token_urlsafe | Generate random auth token |

## Release

| Recipe | Command | Description |
| --- | --- | --- |
| `just publish [bump]` | bump version, tag, push | Release new version (patch/minor/major) |

The publish recipe:
1. Verifies clean `main` branch
2. Bumps version in `pyproject.toml`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `gemini-extension.json`
3. Commits, tags, pushes
4. CI workflows handle PyPI and Docker publishing
