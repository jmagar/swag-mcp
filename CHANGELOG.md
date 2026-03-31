# Changelog

All notable changes to swag-mcp are documented here.

## [Unreleased]

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
