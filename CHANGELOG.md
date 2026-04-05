# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.2] - 2026-04-04

### Added
- **tests/TEST_COVERAGE.md**: Comprehensive test coverage documentation
- **tests/mcporter/**: MCPorter-based integration test suite

### Changed
- Updated `.gitignore` with additional exclusion patterns

## [1.0.1] - 2026-04-03

### Fixed
- **OAuth discovery 401 cascade**: BearerAuthMiddleware was blocking GET /.well-known/oauth-protected-resource, causing MCP clients to surface generic "unknown error". Added WellKnownMiddleware (RFC 9728) to return resource metadata.

### Added
- **docs/AUTHENTICATION.md**: New setup guide covering token generation and client config.
- **README Authentication section**: Added quick-start examples and link to full guide.




### Added
- `swag_help` tool — second required MCP tool listing all actions
- Pagination support for list actions (offset, limit, sort_by, sort_order, query)
- `entrypoint.sh` — startup env validation with `set -euo pipefail`
- `Justfile` — standardized dev/test/lint/build/deploy recipes
- `tests/test_live.sh` — mcporter-based live integration test
- `.codex-plugin/plugin.json` and `.app.json` for Codex CLI compatibility
- `.pre-commit-config.yaml` — required hooks (skills-validate, docker-security, no-baked-env, ensure-ignore-files)

### Changed
- `hooks/scripts/sync-env.sh` — replaced `sed` with `awk`, added `flock` for safe concurrent writes
- `hooks/scripts/ensure-gitignore.sh` — added `--check` mode (exits non-zero without modifying file)
- CI workflow — typecheck now uses `ty` (not mypy); added version-sync and contract-drift jobs
