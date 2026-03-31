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
