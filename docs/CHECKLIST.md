# Plugin Checklist -- swag-mcp

Pre-release and quality checklist. Complete all items before tagging a release.

## Version and metadata

- [ ] All version-bearing files in sync: `pyproject.toml`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `gemini-extension.json`, `server.json`
- [ ] `CHANGELOG.md` has an entry for the new version
- [ ] README version badge is correct

## Configuration

- [ ] `.env.example` documents every environment variable the server reads
- [ ] `.env.example` has no actual secrets -- only placeholders
- [ ] `.env` is in `.gitignore` and `.dockerignore`

## Documentation

- [ ] `CLAUDE.md` is current and matches repo structure
- [ ] `README.md` has up-to-date tool reference and environment variable table
- [ ] `skills/swag/SKILL.md` has correct frontmatter and action reference
- [ ] Setup instructions work from a clean clone

## Security

- [ ] No credentials in code, docs, or git history
- [ ] `.gitignore` includes `.env`, `*.secret`, credentials files
- [ ] `.dockerignore` includes `.env`, `.git/`, `*.secret`

- [ ] `remove` action creates backup before deletion
- [ ] `/health` endpoint is unauthenticated; access control documented as external responsibility
- [ ] Container runs as non-root (UID 1000)
- [ ] No baked environment variables in Docker image
- [ ] Jinja2 templates use sandboxed environment to prevent SSTI
- [ ] Error messages sanitized to prevent information disclosure

## Build and test

- [ ] Docker image builds: `just build`
- [ ] Docker healthcheck passes: `just health`
- [ ] CI pipeline passes: lint (`ruff`), typecheck (`ty`), test (`pytest`)
- [ ] Live integration test passes: `just test-live`
- [ ] Pre-commit hooks configured and passing

## Deployment

- [ ] `docker-compose.yaml` uses correct image tag and port
- [ ] `entrypoint.sh` is executable and handles startup validation
- [ ] SSH volume mount configured for remote access mode

## Registry (if publishing)

- [ ] `server.json` for MCP registry is valid (tv.tootie/swag-mcp)
- [ ] Package published to PyPI (`swag-mcp`)
- [ ] Docker image published to GHCR (`ghcr.io/jmagar/swag-mcp`)

## Marketplace

- [ ] Entry in `claude-homelab` marketplace manifest
- [ ] Plugin installs correctly: `/plugin marketplace add jmagar/claude-homelab`
