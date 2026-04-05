# Publishing Strategy

Versioning and release workflow for swag-mcp.

## Versioning

swag-mcp uses semantic versioning (MAJOR.MINOR.PATCH). Version is stored in 5 files that must stay in sync:

| File | Field |
| --- | --- |
| `pyproject.toml` | `[project] version` |
| `.claude-plugin/plugin.json` | `"version"` |
| `.codex-plugin/plugin.json` | `"version"` |
| `gemini-extension.json` | `"version"` |
| `server.json` | `"version"` and packages `"version"` |

## Release process

### Automated (recommended)

```bash
just publish patch   # 1.0.1 -> 1.0.2
just publish minor   # 1.0.1 -> 1.1.0
just publish major   # 1.0.1 -> 2.0.0
```

The recipe:
1. Verifies you are on `main` with a clean working tree
2. Pulls latest changes
3. Bumps version in all 5 files
4. Commits with message `release: vX.Y.Z`
5. Creates git tag `vX.Y.Z`
6. Pushes to origin with tags

Tag push triggers CI workflows for PyPI and Docker publishing.

### Manual

1. Update version in all 5 files
2. Update `CHANGELOG.md`
3. Commit: `git commit -m "release: vX.Y.Z"`
4. Tag: `git tag vX.Y.Z`
5. Push: `git push origin main --tags`

## Publishing targets

### PyPI

Package name: `swag-mcp`

Published automatically by `publish-pypi.yml` on tag push. Uses trusted publisher (no API token needed).

Install via:
```bash
pip install swag-mcp
# or
uvx swag-mcp
```

### Docker (GHCR)

Image: `ghcr.io/jmagar/swag-mcp`

Published automatically by `docker-publish.yml` on tag push. Multi-platform: linux/amd64, linux/arm64.

### MCP Registry

Registry entry: `tv.tootie/swag-mcp`

The `server.json` file defines the MCP registry entry with PyPI as the package source and stdio as the transport.

DNS verification via `tootie.tv` domain.

## CHANGELOG

Update `CHANGELOG.md` with every release. Follow [Keep a Changelog](https://keepachangelog.com/) format:

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- New feature description

### Changed
- Change description

### Fixed
- Bug fix description
```
