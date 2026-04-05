# CI/CD Workflows

GitHub Actions configuration for swag-mcp.

## Workflows

| File | Trigger | Purpose |
| --- | --- | --- |
| `test.yml` | push, PR | Lint, typecheck, test |
| `docker-publish.yml` | tag push | Build and publish Docker image to GHCR |
| `publish-pypi.yml` | tag push | Build and publish Python package to PyPI |
| `dependencies.yml` | scheduled | Dependency update checks |

## test.yml

Runs on every push and pull request.

Steps:
1. Checkout code
2. Set up Python 3.11
3. Install uv
4. `uv sync --dev` -- install dependencies
5. `uv run ruff check .` -- linting
6. `uv run ty check` -- type checking
7. `uv run pytest --cov=swag_mcp` -- test suite with coverage

All steps must pass before a PR can be merged.

## docker-publish.yml

Triggered by version tags (`v*`).

Steps:
1. Checkout code
2. Set up Docker Buildx
3. Log in to GHCR
4. Build multi-platform image (linux/amd64, linux/arm64)
5. Push to `ghcr.io/jmagar/swag-mcp:{tag}`
6. Tag `latest` for main branch releases

## publish-pypi.yml

Triggered by version tags (`v*`).

Steps:
1. Checkout code
2. Set up Python 3.11
3. Build distribution with `uv build`
4. Publish to PyPI via trusted publisher

## Version tagging

Use the Justfile recipe to bump, tag, and push:

```bash
# Patch bump (1.0.1 -> 1.0.2)
just publish patch

# Minor bump (1.0.1 -> 1.1.0)
just publish minor

# Major bump (1.0.1 -> 2.0.0)
just publish major
```

The recipe updates version in `pyproject.toml`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, and `gemini-extension.json`, then commits, tags, and pushes.
