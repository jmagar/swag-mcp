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
| `just check-network` | validate/create `${DOCKER_NETWORK:-swag-mcp}` | Ensure external Compose network exists |
| `just check-port` | inspect `${SWAG_MCP_BIND_ADDRESS:-127.0.0.1}:${SWAG_MCP_PORT:-49152}` | Ensure published host port is free |
| `just preflight` | network, port, compose config | Validate deployment prerequisites |
| `just up` | `just preflight` then `docker compose up -d` | Start containers |
| `just down` | `docker compose down` | Stop containers |
| `just restart` | `docker compose restart` | Restart containers |
| `just redeploy` | `docker compose down` then validated startup | Stop existing service, start clean, and log deployment |
| `just rollback <image>` | run selected image tag/digest | Roll back container image and log deployment |
| `just logs` | `docker compose logs -f` | Stream container logs |
| `just health` | `curl http://127.0.0.1:${SWAG_MCP_PORT:-49152}/health` | Check server health |

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
