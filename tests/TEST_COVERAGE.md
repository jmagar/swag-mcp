# TEST_COVERAGE.md — `tests/test_live.sh`

Canonical reference for the swag-mcp integration test script. A QA engineer reading
this document should be able to verify the script is testing what it claims without
executing it.

---

## 1. Overview

`tests/test_live.sh` is the **canonical integration test** for the `swag-mcp` MCP
server. It exercises the server end-to-end over the network, verifying:

- The HTTP health endpoint responds correctly
- Authentication behaviour matches the server's design (no built-in auth enforcement)
- The MCP JSON-RPC protocol handshake works (initialize + tools/list)
- Every exposed tool can be called and returns a structurally valid result

**Service under test:** SWAG (Secure Web Application Gateway) — an nginx-based
reverse-proxy manager for self-hosted services.

**MCP server under test:** `swag-mcp` — a FastMCP server that exposes the `swag` and
`swag_help` tools, allowing an AI assistant to list, read, manage, and back up SWAG
nginx proxy configurations.

**Transport:** Streamable-HTTP only (`POST /mcp`). The server does **not** implement
stdio transport; that mode is explicitly skipped.

---

## 2. How to Run

### Prerequisites

The following binaries must be in `PATH` before the script is called:

| Binary | Required for |
|--------|-------------|
| `curl` | All modes |
| `jq`   | All modes |
| `docker` | `docker` mode only |
| `uv`   | `stdio` mode only (but stdio is always skipped) |

If `curl` or `jq` are missing the script exits with **code 2** before running any tests.

### Command syntax

```
bash tests/test_live.sh [--mode http|docker|stdio|all] [--url URL]
                        [--token TOKEN] [--verbose] [--help]
```

### Environment variable overrides

| Variable | Equivalent flag | Default |
|----------|----------------|---------|
| `SWAG_MCP_URL` | `--url` | `http://localhost:8000` |
| `SWAG_MCP_TOKEN` | `--token` | `ci-integration-token` |

### Mode: `http`

Tests an already-running server instance.

```bash
# Against the default local server
bash tests/test_live.sh --mode http

# Against a custom URL
bash tests/test_live.sh --mode http --url http://192.168.1.50:8000

# With verbose raw-response output
bash tests/test_live.sh --mode http --url http://localhost:8000 --verbose
```

**Required:** the server must already be running. Start it with:

```bash
cd /path/to/swag-mcp && uv run python -m swag_mcp
```

The script checks `GET /health` for reachability before starting phases. If the
endpoint is not reachable it records a failure and returns without running any phases.

### Mode: `docker`

Builds a Docker image from the repo root, starts a container, runs all phases against
it, then tears down.

```bash
bash tests/test_live.sh --mode docker
bash tests/test_live.sh --mode docker --verbose
```

No `--url` is needed; the container is always reached at `http://localhost:18082`.

### Mode: `stdio`

Always skipped. See Section 5 for the reason.

```bash
bash tests/test_live.sh --mode stdio
# Output: [SKIP] stdio: all tests  (server does not support stdio transport)
```

### Mode: `all` (default)

Runs `http` and `docker` in sequence.

```bash
bash tests/test_live.sh
bash tests/test_live.sh --mode all
```

In `all` mode, the `http` sub-mode is only executed if `--url` was explicitly supplied
(i.e., `BASE_URL != http://localhost:8000`). Otherwise it is skipped with the message
"no --url provided". Docker mode always runs.

```bash
# Skips http mode (no explicit --url):
bash tests/test_live.sh --mode all

# Runs both http and docker:
bash tests/test_live.sh --mode all --url http://localhost:8000
```

---

## 3. Test Phases

Every mode that reaches the test suite runs the same four phases in order:

| Phase | Name | Purpose |
|-------|------|---------|
| 1 | Health | Prove the HTTP health endpoint is alive and returning the correct status |
| 2 | Auth | Prove the server accepts unauthenticated requests (no built-in token enforcement) |
| 3 | Protocol | Prove the MCP JSON-RPC handshake works and the tool registry is correct |
| 4 | Tool Calls | Exercise every exposed tool with read-only operations |

---

## 4. Phase Details

### Phase 1 — Health

**Purpose:** Verify `GET /health` returns HTTP 200 with a JSON body whose `.status`
field equals `"ok"`.

**HTTP method:** Plain `GET` (not a JSON-RPC call).

**curl flags:** `-s --max-time 15`

**Validation steps (sequential — failure at any step ends the phase):**

1. Response body must be non-empty.
2. Response body must be valid JSON (`jq -e .`).
3. `.status` (extracted via `jq -r '.status // empty'`) must equal the string `"ok"`.

**Single test recorded:**

| Test label | PASS condition | FAIL condition |
|------------|---------------|----------------|
| `GET /health → {"status":"ok"}` | `.status == "ok"` | empty response, non-JSON, or `.status != "ok"` |

---

### Phase 2 — Auth

**Purpose:** Document and verify that `swag-mcp` intentionally has **no built-in
bearer token authentication**. Auth is fully delegated to an upstream proxy (SWAG,
Authelia, Authentik, etc.). The phase confirms the server returns HTTP 200 for a
completely unauthenticated request to `/health`.

**HTTP method:** `GET /health` with no `Authorization` header whatsoever.

**curl flags:** `-s -o /dev/null -w "%{http_code}" --max-time 10`

The script prints three `[WARN]` lines before the test, explicitly stating:

```
swag-mcp does not enforce bearer token auth internally.
Auth is delegated to the upstream proxy (SWAG, Authelia, etc.).
Verifying server accepts unauthenticated requests (expected behaviour).
```

**Single test recorded:**

| Test label | PASS condition | FAIL condition |
|------------|---------------|----------------|
| `GET /health unauthenticated → 200 (no built-in auth)` | HTTP status code is `200` | Any status code other than `200` |

**Note on `--token`:** The `TOKEN` variable (default `ci-integration-token`) is
passed to the Docker container as `SWAG_MCP_TOKEN` (an env var the server reads) but
is **never sent as an HTTP header** in any test. This is intentional — the server
does not inspect `Authorization` headers.

---

### Phase 3 — Protocol

**Purpose:** Verify the MCP JSON-RPC handshake works and the server's tool registry
contains the expected tools.

**Transport detail:** All MCP calls use `POST /mcp` with headers:

```
Content-Type: application/json
Accept: application/json, text/event-stream
```

`--max-time 30` is applied to every call.

#### Test 3a — `initialize`

**Payload:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "test_live", "version": "1.0.0"}
  }
}
```

**jq assertion:** `if .result.protocolVersion then "ok" else "missing .result.protocolVersion" end`

| Test label | PASS condition | FAIL condition |
|------------|---------------|----------------|
| `initialize → result.protocolVersion present` | `.result.protocolVersion` is truthy (non-null, non-empty) | field absent or falsy |

---

#### Test 3b — `tools/list` (array shape)

**Payload:**

```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
```

**jq assertion:** `if (.result.tools | type) == "array" then "ok" else "not an array: \((.result.tools | type))" end`

| Test label | PASS condition | FAIL condition |
|------------|---------------|----------------|
| `tools/list → result.tools is array` | `type(.result.tools) == "array"` | `.result.tools` is any other JSON type (object, null, etc.) |

---

#### Test 3c — `tools/list` (`swag` tool present)

Same payload as 3b (re-sent as a new request).

**jq assertion:** `if (.result.tools | map(.name) | contains(["swag"])) then "ok" else "swag tool not found in \(.result.tools | map(.name))" end`

**Exact check:** Extracts `[.name]` from each element of `.result.tools` and checks
the resulting array contains the string `"swag"` via `contains(["swag"])`.

| Test label | PASS condition | FAIL condition |
|------------|---------------|----------------|
| `tools/list → 'swag' tool present` | `"swag"` appears in the list of `.name` values | `"swag"` not in the name list |

---

#### Test 3d — `tools/list` (`swag_help` tool present)

Same payload as 3b (re-sent as a new request).

**jq assertion:** `if (.result.tools | map(.name) | contains(["swag_help"])) then "ok" else "swag_help tool not found in \(.result.tools | map(.name))" end`

| Test label | PASS condition | FAIL condition |
|------------|---------------|----------------|
| `tools/list → 'swag_help' tool present` | `"swag_help"` appears in the list of `.name` values | `"swag_help"` not in the name list |

---

### Phase 4 — Tool Calls (read-only)

**Purpose:** Exercise every tool the server exposes with real `tools/call` requests
and verify that: (a) no JSON-RPC error is returned, and (b) the result is structurally
present and non-null.

**MCP method for all tests in this phase:** `tools/call`

**Payload template:**

```json
{
  "jsonrpc": "2.0",
  "id": <random integer>,
  "method": "tools/call",
  "params": {
    "name": "<tool_name>",
    "arguments": <args_json>
  }
}
```

**Universal jq check prepended to every tool call:** Before the tool-specific check,
the framework always evaluates:

```jq
if .error then "rpc-error: \(.error.message // .error | tostring)" else ... end
```

If `.error` is present, the test fails with `rpc-error: <message>` regardless of any
other check. Only when `.error` is absent does the tool-specific check run.

---

#### Test 4a — `swag_help`

**Tool:** `swag_help`
**Arguments:** `{}`
**jq check (tool-specific part):** `if (.result.content | length) > 0 then "ok" else "empty content" end`

**What is being tested:** The help tool returns at least one content item. The server
must not return an empty `content` array.

| Test label | PASS | FAIL |
|------------|------|------|
| `tools/call swag_help → result.content present` | No `.error` AND `(.result.content | length) > 0` | `.error` present, OR `content` array is empty |

---

#### Test 4b — `swag` action=list filter=all

**Tool:** `swag`
**Arguments:** `{"action":"list","list_filter":"all"}`
**jq check:** `if .result != null then "ok" else "null result" end`

**What is being tested:** The `list` action with `filter=all` returns a non-null result
(i.e., the tool completes and returns data — which may be an empty list if no proxy
configs exist in the test environment).

| Test label | PASS | FAIL |
|------------|------|------|
| `tools/call swag action=list filter=all → result present` | No `.error` AND `.result != null` | `.error` present OR `.result == null` |

---

#### Test 4c — `swag` action=list filter=active

**Tool:** `swag`
**Arguments:** `{"action":"list","list_filter":"active"}`
**jq check:** `if .result != null then "ok" else "null result" end`

**What is being tested:** The `list` action filtered to only active (non-sample)
configurations. Same structural assertion as 4b.

| Test label | PASS | FAIL |
|------------|------|------|
| `tools/call swag action=list filter=active → result present` | No `.error` AND `.result != null` | `.error` present OR `.result == null` |

---

#### Test 4d — `swag` action=list filter=samples

**Tool:** `swag`
**Arguments:** `{"action":"list","list_filter":"samples"}`
**jq check:** `if .result != null then "ok" else "null result" end`

**What is being tested:** The `list` action filtered to only sample configuration
files. Same structural assertion as 4b.

| Test label | PASS | FAIL |
|------------|------|------|
| `tools/call swag action=list filter=samples → result present` | No `.error` AND `.result != null` | `.error` present OR `.result == null` |

---

#### Test 4e — `swag` action=backups backup_action=list

**Tool:** `swag`
**Arguments:** `{"action":"backups","backup_action":"list"}`
**jq check:** `if .result != null then "ok" else "null result" end`

**What is being tested:** The backup sub-system's list operation. The tool must
complete without error and return a non-null result (an empty list is valid if no
backups exist).

| Test label | PASS | FAIL |
|------------|------|------|
| `tools/call swag action=backups backup_action=list → result present` | No `.error` AND `.result != null` | `.error` present OR `.result == null` |

---

#### Test 4f — `swag` action=logs

**Tool:** `swag`
**Arguments:** `{"action":"logs","log_type":"nginx-error","lines":10}`
**jq check:** `if .result != null then "ok" else "null result" end`

**What is being tested:** The log-reading operation requesting the last 10 lines of
the nginx error log.

**Important CI caveat (documented inline in the script):** The log path
(`/swag/log/nginx/error.log` by default) will not exist in a CI or clean Docker
environment. The server is designed to return a **structured error message** inside the
result body rather than a JSON-RPC error. The test accepts this: a non-null `.result`
that contains an "error" or "not found" message still counts as PASS, because the
tool handled the situation gracefully.

| Test label | PASS | FAIL |
|------------|------|------|
| `tools/call swag action=logs → result present (log path may not exist in CI)` | No `.error` AND `.result != null` | `.error` present OR `.result == null` |

---

#### Test 4g — `swag` action=list with pagination

**Tool:** `swag`
**Arguments:** `{"action":"list","list_filter":"all","offset":0,"limit":5,"sort_by":"name","sort_order":"asc"}`
**jq check:** `if .result != null then "ok" else "null result" end`

**What is being tested:** The `list` action with all optional pagination and sorting
parameters supplied simultaneously: `offset`, `limit`, `sort_by`, and `sort_order`.
Verifies that the parameter-parsing path accepts these optional fields without error.

| Test label | PASS | FAIL |
|------------|------|------|
| `tools/call swag action=list offset=0 limit=5 → result present` | No `.error` AND `.result != null` | `.error` present OR `.result == null` |

---

## 5. Skipped Tests

### stdio mode

**Label:** `stdio: all tests`
**Reason:** `swag-mcp` is implemented using FastMCP's **streamable-http transport**
only. It exposes `POST /mcp` and `GET /health` over HTTP; it does not implement an
`stdio` subprocess transport. There is no code path for JSON-RPC over stdin/stdout.

The `stdio` mode branch calls `run_stdio_mode()` which unconditionally calls
`skip_test` and returns — it does **not** attempt to start the server process or send
any data.

### http sub-mode in `all` mode (conditional skip)

**Label:** `http-mode: all tests`
**Reason:** In `all` mode, the HTTP sub-mode is skipped if `BASE_URL` is still the
default `http://localhost:8000` (meaning no explicit `--url` was provided). This
prevents false failures in CI environments where no local server is running. The docker
mode is self-contained and always runs.

---

## 6. What "Correct Operation" Means Per Tool

These are the precise claims the tests make — not just "endpoint responded":

| Tool / action | Claim |
|--------------|-------|
| `GET /health` | Returns HTTP 200 with valid JSON body where `.status == "ok"` |
| `GET /health` (no auth) | Returns HTTP 200 (server enforces no token auth) |
| `initialize` | Returns JSON-RPC result with a truthy `.result.protocolVersion` field |
| `tools/list` | Returns JSON-RPC result where `.result.tools` is a JSON array |
| `tools/list` | The tools array contains an entry with `.name == "swag"` |
| `tools/list` | The tools array contains an entry with `.name == "swag_help"` |
| `swag_help {}` | Returns no JSON-RPC error AND `(.result.content \| length) > 0` |
| `swag list all` | Returns no JSON-RPC error AND `.result != null` |
| `swag list active` | Returns no JSON-RPC error AND `.result != null` |
| `swag list samples` | Returns no JSON-RPC error AND `.result != null` |
| `swag backups list` | Returns no JSON-RPC error AND `.result != null` |
| `swag logs nginx-error 10` | Returns no JSON-RPC error AND `.result != null` (may contain structured "file not found" message) |
| `swag list all + pagination` | Returns no JSON-RPC error AND `.result != null` when all optional params are present |

The tests do **not** assert on specific list counts, specific file names, or specific
log content — the environment under test may have zero proxy configs.

---

## 7. Authentication Design

`swag-mcp` has **no built-in bearer token enforcement** at the HTTP layer. This is a
deliberate architecture decision documented explicitly in Phase 2:

- The server trusts an upstream proxy (SWAG itself, Authelia, Authentik, etc.) to
  reject unauthenticated requests before they reach the MCP server.
- Inside a Docker Compose stack, the MCP server is typically not port-forwarded to
  the internet; access goes through SWAG's nginx, which enforces the auth rules.
- The `SWAG_MCP_TOKEN` environment variable exists as a configuration token for the
  server's own settings (e.g., identifying itself to the upstream), not as an HTTP
  bearer token it validates on incoming requests.
- The `--token` flag / `SWAG_MCP_TOKEN` env var is accepted by the script for
  compatibility with test harnesses that pass tokens generically, but the value is
  never injected into any `Authorization` header.

**Test implication:** Phase 2 deliberately sends a request with **no** `Authorization`
header and asserts HTTP 200. A 401 or 403 response would be a test *failure* because
it would mean the server unexpectedly started enforcing its own auth.

---

## 8. Docker Mode Specifics

### Image build

```bash
docker build -t swag-mcp:ci-test-<PID> /path/to/swag-mcp
```

- Built from the repo root (`Dockerfile` must exist there).
- Image tag includes the shell PID to avoid conflicts with concurrent test runs.
- If `--verbose` is set, full build output is printed; otherwise only the last 5 lines.
- Build failure records `docker-mode: image build failed` and returns without running phases.

### Container run

```bash
docker run -d \
  --name swag-mcp-ci-test-<PID> \
  -p 18082:8000 \
  -v <tmpdir>:/proxy-confs \
  -e SWAG_MCP_TOKEN=<token> \
  -e SWAG_MCP_NO_AUTH=true \
  -e SWAG_MCP_LOG_FILE_ENABLED=false \
  -e SWAG_MCP_PROXY_CONFS_PATH=/proxy-confs \
  -e SWAG_MCP_LOG_DIRECTORY=/tmp/swag-mcp-logs \
  swag-mcp:ci-test-<PID>
```

- Host port **18082** maps to container port **8000** (the fixed internal port from `SwagConfig.port`).
- A temporary directory is created with `mktemp -d` and bind-mounted to `/proxy-confs`
  inside the container. This gives the server a valid (empty) proxy-confs directory —
  avoiding "path not found" errors while keeping test isolation.
- `SWAG_MCP_LOG_FILE_ENABLED=false` prevents the server from attempting to write log
  files to `/app/.swag-mcp/logs` (which may not be writable in the container).
- `SWAG_MCP_LOG_DIRECTORY=/tmp/swag-mcp-logs` redirects log output to a writable temp path.

### Health polling

```python
wait_for_health("http://localhost:18082", attempts=30, interval=1)
```

Polls `GET http://localhost:18082/health` every 1 second, up to 30 attempts (30
seconds maximum). The check uses `curl -s -o /dev/null -w "%{http_code}" --max-time 2`.
Pass condition: HTTP status code `200`.

If the container does not become healthy in 30 seconds, the script prints the last 20
lines of `docker logs <container>` and records `docker-mode: server health timeout` as
a failure.

### Teardown

Registered via `trap cleanup_docker EXIT`. On exit (regardless of pass/fail):

```bash
docker stop swag-mcp-ci-test-<PID>   # graceful stop
docker rm   swag-mcp-ci-test-<PID>   # remove container
docker rmi  swag-mcp:ci-test-<PID>   # remove image
rm -rf <tmpdir>                       # remove temp proxy-confs dir
```

All cleanup commands use `|| true` — failures during teardown are silently ignored so
they do not mask actual test failures.

---

## 9. Output Format and Interpretation

### Per-test line format

```
[PASS] <label padded to 60 chars>                       <Nms>
[FAIL] <label padded to 60 chars>                       <Nms>
       <reason string>
[SKIP] <label padded to 60 chars>  <reason string>
```

Colors are enabled when stdout is a terminal (TTY detection via `[[ -t 1 ]]`).

### Summary block

Printed after all modes complete:

```
=================================================================
PASS                  <N>
FAIL                  <N>
SKIP                  <N>
TOTAL                 <N>
ELAPSED               <Ns> (<Nms>)
=================================================================

Failed tests:
  - <label of first failed test>
  - <label of second failed test>
  ...
```

The "Failed tests" section only appears when `FAIL_COUNT > 0`.

### Exit codes

| Code | Meaning |
|------|---------|
| `0`  | All tests passed or skipped; no failures |
| `1`  | One or more tests failed |
| `2`  | Prerequisite check failed (missing `curl`, `jq`, or `docker`); no tests ran |

### Verbose mode

Passing `--verbose` causes the raw HTTP response body to be printed to stdout before
each test's PASS/FAIL line. This is useful for debugging unexpected `jq` check failures.

### Timing

Each test records wall-clock duration in milliseconds using `date +%s%N` (nanoseconds,
falling back to seconds-only on platforms where `%N` is unsupported). The elapsed
time displayed is `(end_ns - start_ns) / 1_000_000`.

---

## 10. Test Count Summary

In a complete run with a healthy server, the test suite produces the following counts
per mode execution:

| Phase | Tests |
|-------|-------|
| Phase 1 — Health | 1 |
| Phase 2 — Auth | 1 |
| Phase 3 — Protocol | 4 |
| Phase 4 — Tool Calls | 7 |
| **Total per mode** | **13** |

In `all` mode with a live server at `--url`:
- HTTP mode: 13 tests
- Docker mode: 13 tests
- **Grand total: 26 tests** (plus 0 skips for stdio since it is not run in `all`)

In `all` mode with no explicit `--url` (default CI behaviour):
- HTTP mode: 0 tests + 1 skip
- Docker mode: 13 tests
- **Grand total: 13 tests, 1 skip**

In `stdio` mode only:
- 0 tests + 1 skip
