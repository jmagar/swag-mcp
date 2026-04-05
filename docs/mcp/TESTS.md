# Testing Guide

Testing patterns for swag-mcp. See [MCPORTER](MCPORTER.md) for end-to-end smoke tests.

## Unit tests

```bash
uv run pytest
```

### Test categories

| File | Coverage area |
| --- | --- |
| `test_filesystem.py` | Local filesystem backend operations |
| `test_uri.py` | SSH URI parsing and validation |
| `test_validators_coverage.py` | Input validation (config names, ports, domains) |
| `test_server_simple.py` | Server creation and middleware setup |
| `test_server_coverage.py` | Server lifecycle, version caching, template setup |
| `test_middleware_simple.py` | Individual middleware components |
| `test_middleware_coverage.py` | Middleware integration and ordering |
| `test_swag_manager_simple.py` | SwagManagerService basic operations |
| `test_swag_manager_focused.py` | Focused service method tests |
| `test_swag_manager_comprehensive.py` | Full service coverage |
| `test_swag_manager_service.py` | Service orchestration tests |
| `test_tool_integration.py` | Tool registration and action dispatch |
| `test_coverage_boost.py` | Gap-filling tests for uncovered paths |

### Running specific tests

```bash
# Single file
uv run pytest tests/test_uri.py

# Single test
uv run pytest tests/test_uri.py::test_parse_local_path

# With verbose output
uv run pytest -v tests/test_filesystem.py

# With coverage
uv run pytest --cov=swag_mcp --cov-report=term-missing
```

## Property-based tests

Uses Hypothesis for fuzzing:

```bash
uv run pytest tests/test_property_based.py
```

Tests input validation with random data to find edge cases in:
- Config name validation
- URI parsing
- Port range validation
- Domain pattern matching

## Performance benchmarks

```bash
uv run pytest tests/test_performance_benchmarks.py
```

Benchmarks measure:
- Config listing performance at scale
- Template rendering speed
- File operation throughput
- Middleware overhead

## Concurrency tests

```bash
uv run pytest tests/test_concurrency.py
```

Validates thread safety of:
- File operations with per-file locking
- SSH connection reuse under concurrent access
- Backup creation during simultaneous edits

## Live integration tests

Requires a running server:

```bash
# Start server
just dev

# Run live tests
just test-live
# or: bash tests/test_live.sh
```

The live test script:
1. Checks server health
2. Lists configurations
3. Creates a test configuration
4. Views the created config
5. Updates a field
6. Removes the test config
7. Verifies cleanup

## Remote access tests

```bash
uv run pytest tests/test_mcp_remote_upstream.py
```

Tests the SSH filesystem backend with mock asyncssh connections for:
- Remote file read/write
- Connection pooling and reconnection
- Error handling for network failures

## CI pipeline

The `test.yml` workflow runs on every push and PR:

1. `ruff check .` -- linting
2. `ty check` -- type checking
3. `pytest --cov` -- test suite with coverage

All three must pass before merge.
