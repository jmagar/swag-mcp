# swag-mcp Justfile
# Run `just` to see available recipes

default:
    @just --list

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

# Start services via Docker Compose
up:
    docker compose up -d

# Stop services
down:
    docker compose down

# Restart services
restart:
    docker compose restart

# Show logs
logs:
    docker compose logs -f

# Health check
health:
    curl -sf http://localhost:8082/health | jq .

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
      [ -f "$f" ] && python3 -c "import json; d=json.load(open(\"$f\")); d[\"version\"]=\"${NEW}\"; json.dump(d,open(\"$f\",\"w\"),indent=2); open(\"$f\",\"a\").write(\"
\")"
    done
    git add -A && git commit -m "release: v${NEW}" && git tag "v${NEW}" && git push origin main --tags
    echo "Tagged v${NEW} — publish workflow will run automatically"

