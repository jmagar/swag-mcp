# Development Workflow

Day-to-day development guide for swag-mcp MCP server.

## Setup

```bash
git clone https://github.com/jmagar/swag-mcp.git
cd swag-mcp
just setup
```

This copies `.env.example` to `.env` and runs `uv sync --all-extras --dev`.

## Running locally

```bash
# Start the MCP server
just dev

# In another terminal, test health
just health
```

## Code quality

```bash
# Lint
just lint
# or: uv run ruff check .

# Format
just fmt
# or: uv run ruff format .

# Type check
just typecheck
# or: uv run ty check

# Run tests
just test
# or: uv run pytest

# Run tests with coverage
uv run pytest --cov=swag_mcp --cov-report=term-missing

# All checks at once
just lint && just typecheck && just test
```

## Testing

```bash
# Full test suite
uv run pytest

# Specific test file
uv run pytest tests/test_swag_manager_comprehensive.py

# Property-based tests
uv run pytest tests/test_property_based.py

# Performance benchmarks
uv run pytest tests/test_performance_benchmarks.py

# Live integration test (requires running server)
just test-live
```

See [TESTS](TESTS.md) for detailed testing documentation.

## Project structure

```
swag_mcp/
  core/         Config, constants, logging, DI container
  middleware/   Error handling, rate limiting, timing, logging
  models/       Pydantic models, enums, request/response types
  services/     Business logic (9 sub-managers)
  tools/        MCP tool registration and action handlers
  utils/        Formatters, validators, URI parser, caching, streaming
```

## Adding a new tool action

1. Add the action to `SwagAction` enum in `swag_mcp/models/enums.py`
2. Add parameters to the `swag` tool function in `swag_mcp/tools/swag.py`
3. Create a handler in `swag_mcp/tools/handlers/`
4. Add the service method in `swag_mcp/services/swag_manager.py`
5. Add the match case in the tool's dispatch block
6. Update `swag_help` return value
7. Add tests in `tests/`

## Adding a new environment variable

1. Add the field to `SwagConfig` in `swag_mcp/core/config.py` with `Field()`
2. Add the variable to `.env.example` with documentation
3. Add to `docs/CONFIG.md` and `docs/INVENTORY.md`
4. If needed, add to `userConfig` in `.claude-plugin/plugin.json`

## Pre-commit hooks

```bash
# Install hooks
pre-commit install

# Run all hooks manually
pre-commit run --all-files
```

See [PRE-COMMIT](PRE-COMMIT.md) for hook details.

## Debugging

- Health endpoint: `curl http://localhost:8000/health`
- Server logs: `docker compose logs -f swag-mcp`
- Enable debug logging: `SWAG_MCP_LOG_LEVEL=DEBUG`
- Enable payload logging: `SWAG_MCP_LOG_PAYLOADS=true`
- Template issues: check `templates/mcp.subdomain.conf.j2` syntax
- Validation errors: inspect Pydantic constraints in `swag_mcp/models/config.py`
