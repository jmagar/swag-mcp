# swag-mcp Justfile
# Run `just` to see available recipes

set dotenv-load := true

default:
    @just --list

docker-network := env_var_or_default("DOCKER_NETWORK", "swag-mcp")
swag-port := env_var_or_default("SWAG_MCP_PORT", "49152")
swag-bind := env_var_or_default("SWAG_MCP_BIND_ADDRESS", "127.0.0.1")

# Development
dev:
    uv run python -m swag_mcp

# Linting
lint:
    uv run ruff check .

# Formatting
fmt:
    uv run ruff format .

# Type checking (uses ty, not mypy)
typecheck:
    uv run ty check

# Run tests
test:
    uv run pytest

# Build Docker image
build:
    docker build -t swag-mcp .

# Validate or create the external Compose network
check-network:
    #!/usr/bin/env bash
    set -euo pipefail
    network="{{docker-network}}"
    if docker network inspect "$network" >/dev/null 2>&1; then
      echo "OK: Docker network exists: $network"
    else
      docker network create "$network" >/dev/null
      echo "OK: Docker network created: $network"
    fi

# Verify the published host port is free before first deployment
check-port:
    #!/usr/bin/env bash
    set -euo pipefail
    port="{{swag-port}}"
    bind="{{swag-bind}}"
    if command -v ss >/dev/null 2>&1; then
      if ss -tuln | awk '{print $5}' | grep -Eq "(^|:)${port}$"; then
        echo "ERROR: Port ${port} is already in use on ${bind}" >&2
        exit 1
      fi
    elif command -v lsof >/dev/null 2>&1; then
      if lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
        echo "ERROR: Port ${port} is already in use on ${bind}" >&2
        exit 1
      fi
    else
      echo "WARN: Neither ss nor lsof is available; cannot verify port ${port}" >&2
    fi
    echo "OK: Port ${port} is available on ${bind}"

# Validate deployment prerequisites
preflight: check-network check-port
    docker compose config --quiet

# Start services via Docker Compose
up: preflight
    docker compose up -d

# Stop services
down:
    docker compose down

# Restart services
restart:
    docker compose restart

# Safe redeploy: remove the existing container, validate prerequisites, then start
redeploy: down preflight
    #!/usr/bin/env bash
    set -euo pipefail
    docker compose up -d
    mkdir -p .docs
    timestamp="$(TZ=America/New_York date '+%H:%M:%S | %m/%d/%Y EST')"
    image="${SWAG_MCP_IMAGE:-ghcr.io/jmagar/swag-mcp:latest}"
    port="${SWAG_MCP_PORT:-49152}"
    {
      printf '\n## %s - swag-mcp\n\n' "$timestamp"
      printf -- '- Service: `swag-mcp`\n'
      printf -- '- Deployment method: `just redeploy` (`docker compose down && docker compose up -d`)\n'
      printf -- '- Image: `%s`\n' "$image"
      printf -- '- Port: `%s -> 8000`\n' "$port"
      printf -- '- Status: Started; run `just health` for readiness details.\n'
      printf -- '- Notes: Existing Compose service was stopped before redeploy; external network and port were validated before startup.\n'
    } >> .docs/deployment-log.md

# Roll back to a known image tag, for example: just rollback ghcr.io/jmagar/swag-mcp:1.1.4
rollback image:
    #!/usr/bin/env bash
    set -euo pipefail
    SWAG_MCP_IMAGE="{{image}}" docker compose pull swag-mcp
    SWAG_MCP_IMAGE="{{image}}" docker compose down
    SWAG_MCP_IMAGE="{{image}}" docker compose up -d
    mkdir -p .docs
    timestamp="$(TZ=America/New_York date '+%H:%M:%S | %m/%d/%Y EST')"
    port="${SWAG_MCP_PORT:-49152}"
    {
      printf '\n## %s - swag-mcp rollback\n\n' "$timestamp"
      printf -- '- Service: `swag-mcp`\n'
      printf -- '- Deployment method: `just rollback {{image}}`\n'
      printf -- '- Image: `{{image}}`\n'
      printf -- '- Port: `%s -> 8000`\n' "$port"
      printf -- '- Status: Started; run `just health` for readiness details.\n'
      printf -- '- Notes: Previous Compose service was stopped before starting the rollback image.\n'
    } >> .docs/deployment-log.md

# Show logs
logs:
    docker compose logs -f

# Health check
health:
    curl -sf http://{{swag-bind}}:{{swag-port}}/health | jq .

# Run live integration tests
test-live:
    bash tests/test_live.sh

# Setup environment
setup:
    cp -n .env.example .env || true
    uv sync --all-extras --dev

# Generate a random token
gen-token:
    python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Check contract drift (plugin lint)
check-contract:
    bash scripts/lint-plugin.sh

# Validate skills
validate-skills:
    @echo "Validating skills..."
    @test -f skills/swag/SKILL.md && echo "OK: skills/swag/SKILL.md" || echo "MISSING: skills/swag/SKILL.md"

# Generate a standalone CLI for this server (requires running server)
generate-cli:
    #!/usr/bin/env bash
    set -euo pipefail
    port="${SWAG_MCP_PORT:-49152}"
    bind="${SWAG_MCP_BIND_ADDRESS:-127.0.0.1}"
    token="${SWAG_MCP_TOKEN:-${MCP_TOKEN:-}}"
    if [[ -z "$token" ]]; then
      echo "ERROR: Set SWAG_MCP_TOKEN or MCP_TOKEN before generating the CLI." >&2
      exit 1
    fi
    echo "Server must be running at http://${bind}:${port} (run 'just up' first)"
    echo "⚠  Generated CLI embeds your OAuth token — do not commit or share"
    mkdir -p dist dist/.cache
    current_hash=$(timeout 10 curl -sf \
      -H "Authorization: Bearer ${token}" \
      -H "Accept: application/json, text/event-stream" \
      "http://${bind}:${port}/mcp/tools/list" 2>/dev/null | sha256sum | cut -d' ' -f1 || echo "nohash")
    cache_file="dist/.cache/swag-mcp-cli.schema_hash"
    if [[ -f "$cache_file" ]] && [[ "$(cat "$cache_file")" == "$current_hash" ]] && [[ -f "dist/swag-mcp-cli" ]]; then
      echo "SKIP: swag-mcp tool schema unchanged — use existing dist/swag-mcp-cli"
      exit 0
    fi
    timeout 30 mcporter generate-cli \
      --command "http://${bind}:${port}/mcp" \
      --header "Authorization: Bearer ${token}" \
      --name swag-mcp-cli \
      --output dist/swag-mcp-cli
    printf '%s' "$current_hash" > "$cache_file"
    echo "✓ Generated dist/swag-mcp-cli (requires bun at runtime)"

# Clean build artifacts
clean:
    rm -rf dist/ build/ *.egg-info/ .pytest_cache/ .coverage htmlcov/ .cache/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Publish: bump version, tag, push (triggers PyPI + Docker publish)
publish bump="patch":
    #!/usr/bin/env bash
    set -euo pipefail
    [ "$(git branch --show-current)" = "main" ] || { echo "Switch to main first"; exit 1; }
    [ -z "$(git status --porcelain)" ] || { echo "Commit or stash changes first"; exit 1; }
    git pull origin main
    CURRENT=$(grep -m1 "^version" pyproject.toml | sed "s/.*\"\(.*\)\".*/\1/")
    IFS="." read -r major minor patch <<< "$CURRENT"
    case "{{bump}}" in
      major) major=$((major+1)); minor=0; patch=0 ;;
      minor) minor=$((minor+1)); patch=0 ;;
      patch) patch=$((patch+1)) ;;
      *) echo "Usage: just publish [major|minor|patch]"; exit 1 ;;
    esac
    NEW="${major}.${minor}.${patch}"
    echo "Version: ${CURRENT} → ${NEW}"
    sed -i "s/^version = \"${CURRENT}\"/version = \"${NEW}\"/" pyproject.toml
    for f in .claude-plugin/plugin.json .codex-plugin/plugin.json gemini-extension.json; do
      [ -f "$f" ] && python3 -c 'import json, pathlib, sys; p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text()); d["version"]=sys.argv[2]; p.write_text(json.dumps(d, indent=2) + "\n")' "$f" "${NEW}"
    done
    git add -A && git commit -m "release: v${NEW}" && git tag "v${NEW}" && git push origin main --tags
    echo "Tagged v${NEW} — publish workflow will run automatically"
