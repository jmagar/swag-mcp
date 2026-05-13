# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.6] - 2026-05-13

### Fixed

- **Health checks** — Treat authenticated MCP `/mcp` responses (`401` and `403`) as successful reachability probes, matching existing `406` streamable-HTTP handling.

## [1.1.5] - 2026-05-13

### Fixed

- **OAuth consent flow** — Reused unexpired consent CSRF tokens across duplicate consent page loads so browser preloads or refreshes no longer invalidate the first rendered approval form.
- **OAuth discovery routing** — Added nginx contract coverage for path-scoped metadata and `/mcp`-prefixed OAuth helper endpoints.

## [1.1.4] - 2026-05-12

### Fixed

- **Security: direct MCP auth enforcement** — `SWAG_MCP_TOKEN` now wires a FastMCP bearer-token verifier, and startup fails closed unless token auth, `FASTMCP_SERVER_AUTH`, or explicit `SWAG_MCP_NO_AUTH=true` is configured.
- **Security: session route OAuth** — generated `/session` and `/sessions` nginx routes now use `auth_request /_oauth_verify`.
- **Security: Compose exposure** — Docker Compose now publishes the MCP server on `127.0.0.1:49152` by default instead of all interfaces on port 8000.
- **Resource lifecycle** — Tool-created `SwagManagerService` instances now use the async context manager so HTTP sessions, file locks, and filesystem backends are cleaned up after each tool call.
- **Testing stability** — `bounded_gather()` now cancels outstanding wrapper tasks and closes unstarted coroutines after exceptions, eliminating unawaited-coroutine warnings.
- **Testing stability** — Removed the ignored `aiohttp.TCPConnector(enable_cleanup_closed=True)` flag to eliminate Python 3.12 deprecation warnings.
- **Security: symlink disclosure** — Config reads and shared safe-read operations now reject symlinks through the configured filesystem backend, including remote backends.
- **Security: nginx validation fail-closed** — Missing `nginx` now fails syntax validation instead of treating configs as valid.
- **Migration: SSH backend validation** — SSH-backed create/update operations now fail closed until authoritative nginx validation can run on the remote SWAG host. Use a local config mount or add a backend-supported remote validation hook before enabling remote writes.
- **Health checks** — Health check results now include per-endpoint attempt details while preserving existing top-level success/failure fields.
- **Update semantics** — `upstream` updates now reject `app:port`; docs now state that `upstream` updates app only and `app` updates app plus port.
- **Logging** — Rotating file logs now retain configurable backups via `SWAG_MCP_LOG_FILE_BACKUP_COUNT`.
- **Timing** — Health-check response timing and live-stream duration tracking now use monotonic clocks.
- **Documentation** — Updated auth, environment, and deployment docs to match the enforced auth and safer Compose defaults.

## [1.1.3] - 2026-05-12

### Fixed

- **Security: SSH command injection** — `shlex.quote()` now escapes paths in the SSH `tail` command (`ssh_filesystem.py`).
- **Security: OAuth fails-open** — Exceptions during Google OAuth setup now propagate instead of silently disabling auth.
- **Security: Exception details leaked to clients** — Catch-all handler in `swag.py` now returns a generic message and keeps full details in server logs only.
- **Security: Symlink traversal** — `read_config()` now rejects symlinks before reading config files.
- **Security: CORS comment** — Added prominent security warning in `mcp-location.conf` about reflected-origin risk.
- **Correct Dockerfile ENV vars** — Fixed `SWAG_MCP_SWAG_CONFIG_PATH` → `SWAG_MCP_PROXY_CONFS_PATH`, `SWAG_MCP_MCP_HOST` → `SWAG_MCP_HOST`, removed redundant `SWAG_MCP_MCP_PORT`. Health check now uses hardcoded port 8000.
- **mcp_operations.py error wrapping** — `FileNotFoundError` and `ValueError` are now re-raised unchanged; only unexpected exceptions become `RuntimeError`.
- **nginx validation fail-open** — Unexpected exceptions in `validate_nginx_syntax` now return `False` instead of silently returning `True`.
- **Bare re-raise** — `except ValueError as e: raise e` replaced with bare `raise` in `config_operations.py`.
- **Startup cleanup non-blocking** — `cleanup_old_backups()` is now scheduled as a background task on startup, not awaited before serving.
- **Lazy logging** — Replaced eager f-string logger calls with `%s` lazy formatting in `server.py`, `health_monitor.py`, and `middleware/error_handling.py`.
- **SettingsConfigDict** — `SwagConfig.model_config` now uses typed `SettingsConfigDict` instead of a plain dict.
- **Docker publish gated on tests** — `docker-publish.yml` now requires the test job to pass before building the image.
- **Documentation** — Added `swag_help` tool to README tools table; updated `.env.example` auth comments to accurately describe server behaviour.

### Removed

- `swag_mcp/services/swag_manager.py.backup` and `.monolith` — stale archive files deleted from the package directory.

### Fixed

- Wired the Docker entrypoint to prepare writable runtime directories before starting the app.
- Split Docker Compose host log bind path from the container log directory.

## [1.1.1] - 2026-05-11

### Fixed

- Addressed remaining PR review comments for MCP origin enforcement, Docker Compose host bind paths, and FastMCP import compatibility.

## [1.1.0] - 2026-05-11

### Added

- Standardized Axon MCP nginx sidecar and transport include layout.
- Restored proxy-level OAuth verification for MCP locations.

### Changed

- Updated split-routing behavior to preserve separate MCP upstreams during main app updates.
- Migrated uv development dependencies to `dependency-groups.dev`.
- Removed committed `.beads` issue export artifact.

## [1.0.3] - 2026-04-15

### Changed

- Repository maintenance updates committed from the current working tree.
- Version-bearing manifests synchronized to 1.0.3.


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
- `swag_help` tool — second required MCP tool listing all actions
- Pagination support for list actions (offset, limit, sort_by, sort_order, query)
- `entrypoint.sh` — startup env validation with `set -euo pipefail`
- `Justfile` — standardized dev/test/lint/build/deploy recipes
- `tests/test_live.sh` — mcporter-based live integration test
- `.codex-plugin/plugin.json` and `.app.json` for Codex CLI compatibility
- `.pre-commit-config.yaml` — required hooks (skills-validate, docker-security, no-baked-env, ensure-ignore-files)

### Changed
- `bin/sync-uv.sh` — replaced `sed` with `awk`, added `flock` for safe concurrent writes

- CI workflow — typecheck now uses `ty` (not mypy); added version-sync and contract-drift jobs
