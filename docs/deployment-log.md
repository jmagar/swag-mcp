# Deployment Log

## Rollback Procedure

- Updated: `10:59:34 | 05/12/2026 EST`
- Scope: `swag-mcp` Docker Compose deployments.
- Prerequisites: `.env` configured, Docker available, `DOCKER_NETWORK` valid or creatable, and the rollback image tag known.
- Command: `just rollback ghcr.io/jmagar/swag-mcp:<version>`
- Safety behavior: the recipe pulls the requested image, stops the existing Compose service, starts the rollback image, and appends the action to this log.
- Readiness check: run `just health` after rollback and verify Docker reports the container as healthy.
- Recovery note: if rollback fails before startup, restore the previous image by running `just rollback <previous-image-tag>`.

## 11:50:21 | 05/11/2026 EST - swag-mcp

- Service: `swag-mcp`
- Deployment method: `docker compose up -d --build`
- Port: `8012 -> 8000`
- Version: `1.1.1`
- Source: `main` at merge commit `d96fe15f6e9eb6adb652c15163951c298df8b947`
- Status: Healthy; `/health` returned `{"status":"healthy","service":"swag-mcp","version":"1.1.1"}`
- Notes: Container recreated after stopping and removing the previous `swag-mcp` instance. Port `8012` was verified free before redeploy. File logging warning observed because `/mnt/appdata/swag-mcp/logs` is not writable from the container; console logging remains active.

## 11:56:27 | 05/11/2026 EST - swag-mcp

- Service: `swag-mcp`
- Deployment method: `docker compose up -d --build`
- Port: `8012 -> 8000`
- Version: `1.1.2`
- Source: `main` at commit `2754e45`
- Status: Healthy; `/health` returned `{"status":"healthy","service":"swag-mcp","version":"1.1.2"}`
- Notes: Added and deployed the Docker entrypoint runtime-directory preparation. Compose now uses `SWAG_MCP_LOG_HOST_PATH` for the host bind path and sets the container log directory to `/app/.swag-mcp/logs`. Verified UID/GID `1000:1000` can write the log directory and the previous file-logging permission warning is gone.

## 00:59:14 | 05/13/2026 EST - swag-mcp

- Service: `swag-mcp`
- Deployment method: `docker build -t ghcr.io/jmagar/swag-mcp:1.1.4 .` then `docker compose up -d --force-recreate swag-mcp`
- Port: `127.0.0.1:8012 -> 8000`
- Version: `1.1.4`
- Status: Healthy; `https://swag.tootie.tv/health` returned `{"status":"healthy","service":"swag-mcp","version":"1.1.4"}`
- Notes: Redeployed after fixing FastMCP protected-resource metadata from `https://swag.tootie.tv/mcp/mcp` to `https://swag.tootie.tv/mcp`. Enabled combined bearer-token and Google OAuth auth. Updated SWAG proxy upstream for `swag.tootie.tv` to `swag-mcp:8000`, validated with `docker exec swag nginx -t`, reloaded SWAG, and verified mcporter HTTP smoke tests with `PASS 7`, `FAIL 0`, `SKIP 1`.

## 11:24:01 | 05/13/2026 EST - swag-mcp

- Service: `swag-mcp`
- Deployment method: `docker build --no-cache -t ghcr.io/jmagar/swag-mcp:1.1.5 .` then `docker compose up -d --force-recreate swag-mcp`
- Port: `127.0.0.1:8012 -> 8000`
- Version: `1.1.5`
- Status: Healthy; `http://127.0.0.1:8012/health` returned `{"status":"healthy","service":"swag-mcp","version":"1.1.5"}`
- Notes: Recreated only `swag-mcp` after stabilizing FastMCP consent CSRF reuse and nginx OAuth helper rewrites. Verified duplicate consent GETs keep the same CSRF token and the first rendered form POST returns `302` instead of `400`.
