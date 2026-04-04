#!/usr/bin/env bash
# =============================================================================
# test_live.sh — Canonical integration test for swag-mcp
#
# Tests the swag-mcp MCP server in http, docker, and stdio modes.
# Covers: health, protocol (initialize + tools/list), and read-only tool calls.
#
# Usage:
#   bash tests/test_live.sh [--mode http|docker|stdio|all] [--url URL]
#                           [--token TOKEN] [--verbose] [--help]
#
# Modes:
#   http    — Test against a running server at --url (default: http://localhost:8000)
#   docker  — Build image, start container, run tests, tear down
#   stdio   — Skipped: swag-mcp only supports streamable-http transport
#   all     — Run http and docker modes (default)
#
# Environment variables (alternatives to flags):
#   SWAG_MCP_URL    Base URL of the running server (http mode)
#   SWAG_MCP_TOKEN  Bearer token (unused by swag-mcp itself, kept for compat)
#
# Exit codes:
#   0 — all tests passed (or skipped)
#   1 — one or more tests failed
#   2 — prerequisite check failed
# =============================================================================

set -uo pipefail

# ---------------------------------------------------------------------------
# Script paths
# ---------------------------------------------------------------------------
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPO_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd -P)"
readonly SCRIPT_NAME="$(basename -- "${BASH_SOURCE[0]}")"
readonly TS_START="$(date +%s%N 2>/dev/null || date +%s)000000"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
MODE="all"
BASE_URL="${SWAG_MCP_URL:-http://localhost:8000}"
TOKEN="${SWAG_MCP_TOKEN:-ci-integration-token}"
VERBOSE=false

# Docker-specific
DOCKER_IMAGE="swag-mcp:ci-test-$$"
DOCKER_CONTAINER="swag-mcp-ci-test-$$"
DOCKER_HOST_PORT=18082
DOCKER_BASE_URL="http://localhost:${DOCKER_HOST_PORT}"
DOCKER_PROXY_CONFS_DIR=""

# Counters (global, updated by run_test/skip_test)
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
declare -a FAIL_NAMES=()

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
if [[ -t 1 ]]; then
  C_RESET='\033[0m'
  C_BOLD='\033[1m'
  C_GREEN='\033[0;32m'
  C_RED='\033[0;31m'
  C_YELLOW='\033[0;33m'
  C_CYAN='\033[0;36m'
  C_DIM='\033[2m'
else
  C_RESET='' C_BOLD='' C_GREEN='' C_RED='' C_YELLOW='' C_CYAN='' C_DIM=''
fi

# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
usage() {
  cat <<EOF
Usage: ${SCRIPT_NAME} [OPTIONS]

Canonical integration test for swag-mcp.

OPTIONS:
  --mode http|docker|stdio|all   Test mode (default: all)
  --url URL                      Base URL for http mode (default: ${BASE_URL})
  --token TOKEN                  Bearer token (for auth-proxy setups, default: ${TOKEN})
  --verbose                      Print raw responses for each test
  --help                         Show this help and exit

MODES:
  http    Test against a running server at --url
  docker  Build, start, test, and tear down a Docker container
  stdio   Not supported (swag-mcp uses streamable-http transport only) — skipped
  all     Run http and docker modes (default)

ENVIRONMENT:
  SWAG_MCP_URL    Overrides --url
  SWAG_MCP_TOKEN  Overrides --token
EOF
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --mode)
        MODE="${2:?--mode requires a value: http|docker|stdio|all}"
        case "${MODE}" in
          http|docker|stdio|all) ;;
          *) die "Invalid --mode '${MODE}'. Must be: http, docker, stdio, or all." ;;
        esac
        shift 2
        ;;
      --url)
        BASE_URL="${2:?--url requires a value}"
        shift 2
        ;;
      --token)
        TOKEN="${2:?--token requires a value}"
        shift 2
        ;;
      --verbose)
        VERBOSE=true
        shift
        ;;
      --help|-h)
        usage
        exit 0
        ;;
      *)
        die "Unknown argument: $1"
        ;;
    esac
  done
}

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log_info()    { printf "${C_CYAN}[INFO]${C_RESET}  %s\n" "$*"; }
log_warn()    { printf "${C_YELLOW}[WARN]${C_RESET}  %s\n" "$*"; }
log_error()   { printf "${C_RED}[ERROR]${C_RESET} %s\n" "$*" >&2; }
log_section() { printf "\n${C_BOLD}== %s ==${C_RESET}\n" "$*"; }

die() {
  log_error "$*"
  exit 2
}

# ---------------------------------------------------------------------------
# Elapsed time helper
# ---------------------------------------------------------------------------
elapsed_ms() {
  local start="${1:?}"
  local now
  now="$(date +%s%N 2>/dev/null || date +%s)000000"
  echo "$(( ( now - start ) / 1000000 ))"
}

# ---------------------------------------------------------------------------
# Test result helpers
# ---------------------------------------------------------------------------
pass_test() {
  local label="${1:?}" ms="${2:-0}"
  printf "${C_GREEN}[PASS]${C_RESET} %-60s ${C_DIM}%dms${C_RESET}\n" "${label}" "${ms}"
  PASS_COUNT=$(( PASS_COUNT + 1 ))
}

fail_test() {
  local label="${1:?}" reason="${2:-}" ms="${3:-0}"
  printf "${C_RED}[FAIL]${C_RESET} %-60s ${C_DIM}%dms${C_RESET}\n" "${label}" "${ms}"
  [[ -n "${reason}" ]] && printf '       %s\n' "${reason}"
  FAIL_COUNT=$(( FAIL_COUNT + 1 ))
  FAIL_NAMES+=("${label}")
}

skip_test() {
  local label="${1:?}" reason="${2:-}"
  printf "${C_YELLOW}[SKIP]${C_RESET} %-60s %s\n" "${label}" "${reason}"
  SKIP_COUNT=$(( SKIP_COUNT + 1 ))
}

# ---------------------------------------------------------------------------
# HTTP helper — sends MCP JSON-RPC over streamable-http
# ---------------------------------------------------------------------------
# swag-mcp uses FastMCP streamable-http transport.
# The MCP endpoint is POST /mcp with Content-Type: application/json
# and Accept: application/json, text/event-stream
mcp_call() {
  local url="${1:?}" payload="${2:?}"
  curl -s -X POST \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    --max-time 30 \
    -d "${payload}" \
    "${url}/mcp"
}

# Plain GET for health
http_get() {
  local url="${1:?}"
  curl -s --max-time 15 "${url}"
}

# ---------------------------------------------------------------------------
# run_test: execute one test, validate jq path, update counters
#
# Usage: run_test <label> <url> <payload> [<jq_check>]
#   jq_check — jq expression that must output "ok" on success
#              default: checks response is valid JSON without "error" key
# ---------------------------------------------------------------------------
run_test() {
  local label="${1:?}" url="${2:?}" payload="${3:?}" jq_check="${4:-}"
  local t0 response ms

  t0="$(date +%s%N 2>/dev/null || date +%s)000000"

  response="$(mcp_call "${url}" "${payload}" 2>&1)" || true

  ms="$(( ( $(date +%s%N 2>/dev/null || date +%s)000000 - t0 ) / 1000000 ))"

  if [[ "${VERBOSE}" == true ]]; then
    printf '%s\n' "${response}"
  fi

  # Must be non-empty
  if [[ -z "${response}" ]]; then
    fail_test "${label}" "empty response from server" "${ms}"
    return 1
  fi

  # Must be valid JSON
  if ! printf '%s' "${response}" | jq -e . >/dev/null 2>&1; then
    fail_test "${label}" "response is not valid JSON: ${response:0:200}" "${ms}"
    return 1
  fi

  # Run custom jq check if provided
  if [[ -n "${jq_check}" ]]; then
    local check_result
    check_result="$(printf '%s' "${response}" | jq -r "${jq_check}" 2>/dev/null || echo "jq_error")"
    if [[ "${check_result}" != "ok" ]]; then
      fail_test "${label}" "jq check failed (got '${check_result}'): ${jq_check}" "${ms}"
      return 1
    fi
  fi

  pass_test "${label}" "${ms}"
  return 0
}

# ---------------------------------------------------------------------------
# Phase 1 — Health
# ---------------------------------------------------------------------------
phase_health() {
  local base_url="${1:?}"
  log_section "Phase 1: Health"

  local t0 response ms
  t0="$(date +%s%N 2>/dev/null || date +%s)000000"
  response="$(http_get "${base_url}/health" 2>&1)" || true
  ms="$(( ( $(date +%s%N 2>/dev/null || date +%s)000000 - t0 ) / 1000000 ))"

  if [[ "${VERBOSE}" == true ]]; then
    printf '%s\n' "${response}"
  fi

  if [[ -z "${response}" ]]; then
    fail_test "GET /health → non-empty response" "empty response" "${ms}"
    return 1
  fi

  if ! printf '%s' "${response}" | jq -e . >/dev/null 2>&1; then
    fail_test "GET /health → valid JSON" "not JSON: ${response:0:100}" "${ms}"
    return 1
  fi

  local status
  status="$(printf '%s' "${response}" | jq -r '.status // empty' 2>/dev/null)"

  if [[ "${status}" == "ok" ]]; then
    pass_test "GET /health → {\"status\":\"ok\"}" "${ms}"
  else
    fail_test "GET /health → {\"status\":\"ok\"}" ".status='${status}' (expected 'ok')" "${ms}"
    return 1
  fi

  return 0
}

# ---------------------------------------------------------------------------
# Phase 2 — Auth
#
# swag-mcp does NOT enforce bearer token auth internally.
# Auth is expected to be handled by an upstream proxy (e.g., SWAG itself).
# We verify the server responds to requests without requiring a token.
# ---------------------------------------------------------------------------
phase_auth() {
  local base_url="${1:?}"
  log_section "Phase 2: Auth"

  log_warn "swag-mcp does not enforce bearer token auth internally."
  log_warn "Auth is delegated to the upstream proxy (SWAG, Authelia, etc.)."
  log_warn "Verifying server accepts unauthenticated requests (expected behaviour)."

  local t0 response http_code ms
  t0="$(date +%s%N 2>/dev/null || date +%s)000000"
  http_code="$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${base_url}/health")" || http_code="000"
  ms="$(( ( $(date +%s%N 2>/dev/null || date +%s)000000 - t0 ) / 1000000 ))"

  if [[ "${http_code}" == "200" ]]; then
    pass_test "GET /health unauthenticated → 200 (no built-in auth)" "${ms}"
  else
    fail_test "GET /health unauthenticated → 200 (no built-in auth)" "got HTTP ${http_code}" "${ms}"
    return 1
  fi

  return 0
}

# ---------------------------------------------------------------------------
# Phase 3 — Protocol (initialize + tools/list)
# ---------------------------------------------------------------------------
phase_protocol() {
  local base_url="${1:?}"
  log_section "Phase 3: Protocol"

  # 3a. initialize
  local init_payload
  init_payload='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test_live","version":"1.0.0"}}}'

  run_test \
    "initialize → result.protocolVersion present" \
    "${base_url}" \
    "${init_payload}" \
    'if .result.protocolVersion then "ok" else "missing .result.protocolVersion" end'

  # 3b. tools/list
  local list_payload
  list_payload='{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'

  run_test \
    "tools/list → result.tools is array" \
    "${base_url}" \
    "${list_payload}" \
    'if (.result.tools | type) == "array" then "ok" else "not an array: \((.result.tools | type))" end'

  # 3c. Verify 'swag' tool is present
  run_test \
    "tools/list → 'swag' tool present" \
    "${base_url}" \
    "${list_payload}" \
    'if (.result.tools | map(.name) | contains(["swag"])) then "ok" else "swag tool not found in \(.result.tools | map(.name))" end'

  # 3d. Verify 'swag_help' tool is present
  run_test \
    "tools/list → 'swag_help' tool present" \
    "${base_url}" \
    "${list_payload}" \
    'if (.result.tools | map(.name) | contains(["swag_help"])) then "ok" else "swag_help tool not found in \(.result.tools | map(.name))" end'
}

# ---------------------------------------------------------------------------
# MCP tool call helper
# ---------------------------------------------------------------------------
# Sends a tools/call request and validates:
#   - response is valid JSON
#   - no JSON-RPC error field
#   - optional jq check on the result
mcp_tool_call() {
  local label="${1:?}" base_url="${2:?}" tool="${3:?}" args_json="${4:?}" jq_check="${5:-}"
  local id="${RANDOM}"
  local payload
  payload="$(printf '{"jsonrpc":"2.0","id":%d,"method":"tools/call","params":{"name":"%s","arguments":%s}}' \
    "${id}" "${tool}" "${args_json}")"

  # Add JSON-RPC error check to the jq_check
  local full_check='if .error then "rpc-error: \(.error.message // .error | tostring)" else "ok" end'
  if [[ -n "${jq_check}" ]]; then
    full_check="if .error then \"rpc-error: \(.error.message // .error | tostring)\" else (${jq_check}) end"
  fi

  run_test "${label}" "${base_url}" "${payload}" "${full_check}"
}

# ---------------------------------------------------------------------------
# Phase 4 — Tool calls (read-only)
# ---------------------------------------------------------------------------
phase_tools() {
  local base_url="${1:?}" proxy_confs_dir="${2:-}"
  log_section "Phase 4: Tool Calls (read-only)"

  # 4a. swag_help — always safe, no params
  mcp_tool_call \
    "tools/call swag_help → result.content present" \
    "${base_url}" \
    "swag_help" \
    '{}' \
    'if (.result.content | length) > 0 then "ok" else "empty content" end'

  # 4b. swag action=list filter=all
  mcp_tool_call \
    "tools/call swag action=list filter=all → result present" \
    "${base_url}" \
    "swag" \
    '{"action":"list","list_filter":"all"}' \
    'if .result != null then "ok" else "null result" end'

  # 4c. swag action=list filter=active
  mcp_tool_call \
    "tools/call swag action=list filter=active → result present" \
    "${base_url}" \
    "swag" \
    '{"action":"list","list_filter":"active"}' \
    'if .result != null then "ok" else "null result" end'

  # 4d. swag action=list filter=samples
  mcp_tool_call \
    "tools/call swag action=list filter=samples → result present" \
    "${base_url}" \
    "swag" \
    '{"action":"list","list_filter":"samples"}' \
    'if .result != null then "ok" else "null result" end'

  # 4e. swag action=backups backup_action=list
  mcp_tool_call \
    "tools/call swag action=backups backup_action=list → result present" \
    "${base_url}" \
    "swag" \
    '{"action":"backups","backup_action":"list"}' \
    'if .result != null then "ok" else "null result" end'

  # 4f. swag action=logs (read nginx-error log, last 10 lines)
  # Note: In CI the log path may not exist; result may contain an error message but
  # that is still a valid (non-null) result — the tool returns structured errors.
  mcp_tool_call \
    "tools/call swag action=logs → result present (log path may not exist in CI)" \
    "${base_url}" \
    "swag" \
    '{"action":"logs","log_type":"nginx-error","lines":10}' \
    'if .result != null then "ok" else "null result" end'

  # 4g. swag action=list with pagination params
  mcp_tool_call \
    "tools/call swag action=list offset=0 limit=5 → result present" \
    "${base_url}" \
    "swag" \
    '{"action":"list","list_filter":"all","offset":0,"limit":5,"sort_by":"name","sort_order":"asc"}' \
    'if .result != null then "ok" else "null result" end'
}

# ---------------------------------------------------------------------------
# Prerequisites check
# ---------------------------------------------------------------------------
check_prerequisites() {
  local missing=false

  for cmd in curl jq; do
    if ! command -v "${cmd}" &>/dev/null; then
      log_error "Required command not found: ${cmd}"
      missing=true
    fi
  done

  if [[ "${missing}" == true ]]; then
    return 2
  fi
}

check_docker_prerequisites() {
  if ! command -v docker &>/dev/null; then
    log_error "docker not found in PATH — required for docker mode"
    return 2
  fi
}

check_uv_prerequisites() {
  if ! command -v uv &>/dev/null; then
    log_error "uv not found in PATH — required for stdio mode"
    return 2
  fi
}

# ---------------------------------------------------------------------------
# Wait for server to become healthy
# ---------------------------------------------------------------------------
wait_for_health() {
  local url="${1:?}" attempts="${2:-30}" interval="${3:-1}"
  log_info "Waiting for server at ${url}/health (up to $((attempts * interval))s)..."
  local i=0
  while [[ "${i}" -lt "${attempts}" ]]; do
    local code
    code="$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "${url}/health" 2>/dev/null)" || code="000"
    if [[ "${code}" == "200" ]]; then
      log_info "Server is healthy."
      return 0
    fi
    i=$(( i + 1 ))
    sleep "${interval}"
  done
  log_error "Server did not become healthy after $((attempts * interval))s"
  return 1
}

# ---------------------------------------------------------------------------
# MODE: http
# ---------------------------------------------------------------------------
run_http_mode() {
  log_section "Mode: HTTP (${BASE_URL})"

  # Quick connectivity check
  if ! curl -s --max-time 5 "${BASE_URL}/health" >/dev/null 2>&1; then
    log_error "Cannot reach ${BASE_URL}/health — is the server running?"
    log_error "Start the server with: cd ${REPO_DIR} && uv run python -m swag_mcp"
    FAIL_COUNT=$(( FAIL_COUNT + 1 ))
    FAIL_NAMES+=("http-mode: server not reachable")
    return 1
  fi

  # Create a temp proxy confs dir for the http mode
  local proxy_confs_dir
  proxy_confs_dir="$(mktemp -d)"
  trap 'rm -rf -- "${proxy_confs_dir}"' RETURN

  phase_health "${BASE_URL}"
  phase_auth "${BASE_URL}"
  phase_protocol "${BASE_URL}"
  phase_tools "${BASE_URL}" "${proxy_confs_dir}"
}

# ---------------------------------------------------------------------------
# MODE: docker
# ---------------------------------------------------------------------------
run_docker_mode() {
  log_section "Mode: Docker"

  check_docker_prerequisites || return 2

  # Create a temp proxy-confs dir to mount into the container
  DOCKER_PROXY_CONFS_DIR="$(mktemp -d)"
  log_info "Using proxy-confs dir: ${DOCKER_PROXY_CONFS_DIR}"

  # Ensure Docker cleanup on exit
  local docker_cleanup_registered=false
  cleanup_docker() {
    if [[ "${docker_cleanup_registered}" == true ]]; then
      log_info "Tearing down Docker container ${DOCKER_CONTAINER}..."
      docker stop "${DOCKER_CONTAINER}" >/dev/null 2>&1 || true
      docker rm "${DOCKER_CONTAINER}" >/dev/null 2>&1 || true
      docker rmi "${DOCKER_IMAGE}" >/dev/null 2>&1 || true
      rm -rf -- "${DOCKER_PROXY_CONFS_DIR}" 2>/dev/null || true
    fi
  }
  trap cleanup_docker EXIT

  # Build image
  log_info "Building Docker image ${DOCKER_IMAGE}..."
  if ! docker build -t "${DOCKER_IMAGE}" "${REPO_DIR}" 2>&1 | (
    if [[ "${VERBOSE}" == true ]]; then cat; else tail -5; fi
  ); then
    log_error "Docker build failed"
    FAIL_COUNT=$(( FAIL_COUNT + 1 ))
    FAIL_NAMES+=("docker-mode: image build failed")
    return 1
  fi
  log_info "Docker image built."
  docker_cleanup_registered=true

  # Run container
  log_info "Starting container ${DOCKER_CONTAINER} on port ${DOCKER_HOST_PORT}..."
  docker run -d \
    --name "${DOCKER_CONTAINER}" \
    -p "${DOCKER_HOST_PORT}:8000" \
    -v "${DOCKER_PROXY_CONFS_DIR}:/proxy-confs" \
    -e "SWAG_MCP_TOKEN=${TOKEN}" \
    -e "SWAG_MCP_NO_AUTH=true" \
    -e "SWAG_MCP_LOG_FILE_ENABLED=false" \
    -e "SWAG_MCP_PROXY_CONFS_PATH=/proxy-confs" \
    -e "SWAG_MCP_LOG_DIRECTORY=/tmp/swag-mcp-logs" \
    "${DOCKER_IMAGE}" \
    >/dev/null

  # Wait for health
  if ! wait_for_health "${DOCKER_BASE_URL}" 30 1; then
    log_error "Container logs:"
    docker logs "${DOCKER_CONTAINER}" 2>&1 | tail -20
    FAIL_COUNT=$(( FAIL_COUNT + 1 ))
    FAIL_NAMES+=("docker-mode: server health timeout")
    return 1
  fi

  phase_health "${DOCKER_BASE_URL}"
  phase_auth "${DOCKER_BASE_URL}"
  phase_protocol "${DOCKER_BASE_URL}"
  phase_tools "${DOCKER_BASE_URL}" "${DOCKER_PROXY_CONFS_DIR}"
}

# ---------------------------------------------------------------------------
# MODE: stdio
# ---------------------------------------------------------------------------
run_stdio_mode() {
  log_section "Mode: Stdio"
  log_warn "swag-mcp only supports streamable-http transport."
  log_warn "Stdio mode is not implemented by this server."
  skip_test "stdio: all tests" "server does not support stdio transport"
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print_summary() {
  local total_ms
  total_ms="$(( ( $(date +%s%N 2>/dev/null || date +%s)000000 - TS_START ) / 1000000 ))"
  local total=$(( PASS_COUNT + FAIL_COUNT + SKIP_COUNT ))

  printf '\n%b%s%b\n' "${C_BOLD}" "$(printf '=%.0s' {1..65})" "${C_RESET}"
  printf '%b%-20s%b  %b%d%b\n' "${C_BOLD}" "PASS"    "${C_RESET}" "${C_GREEN}"  "${PASS_COUNT}"  "${C_RESET}"
  printf '%b%-20s%b  %b%d%b\n' "${C_BOLD}" "FAIL"    "${C_RESET}" "${C_RED}"    "${FAIL_COUNT}"  "${C_RESET}"
  printf '%b%-20s%b  %b%d%b\n' "${C_BOLD}" "SKIP"    "${C_RESET}" "${C_YELLOW}" "${SKIP_COUNT}"  "${C_RESET}"
  printf '%b%-20s%b  %d\n'     "${C_BOLD}" "TOTAL"   "${C_RESET}" "${total}"
  printf '%b%-20s%b  %ds (%dms)\n' "${C_BOLD}" "ELAPSED" "${C_RESET}" \
    "$(( total_ms / 1000 ))" "${total_ms}"
  printf '%b%s%b\n' "${C_BOLD}" "$(printf '=%.0s' {1..65})" "${C_RESET}"

  if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    printf '\n%bFailed tests:%b\n' "${C_RED}" "${C_RESET}"
    local name
    for name in "${FAIL_NAMES[@]}"; do
      printf '  - %s\n' "${name}"
    done
  fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  parse_args "$@"

  printf '%b%s%b\n' "${C_BOLD}" "$(printf '=%.0s' {1..65})" "${C_RESET}"
  printf '%b  swag-mcp integration tests%b\n' "${C_BOLD}" "${C_RESET}"
  printf '%b  Repo:   %s%b\n' "${C_BOLD}" "${REPO_DIR}"  "${C_RESET}"
  printf '%b  Mode:   %s%b\n' "${C_BOLD}" "${MODE}"       "${C_RESET}"
  printf '%b  URL:    %s  (http mode)%b\n' "${C_BOLD}" "${BASE_URL}" "${C_RESET}"
  printf '%b%s%b\n\n' "${C_BOLD}" "$(printf '=%.0s' {1..65})" "${C_RESET}"

  check_prerequisites || exit 2

  case "${MODE}" in
    http)
      run_http_mode
      ;;
    docker)
      run_docker_mode
      ;;
    stdio)
      run_stdio_mode
      ;;
    all)
      # In CI, we have no running server, so http mode will gracefully fail.
      # Docker mode does the full build+run cycle.
      # We run docker first (self-contained), then http if --url was explicitly set.
      if [[ "${BASE_URL}" != "http://localhost:8000" ]]; then
        run_http_mode
      else
        log_info "Skipping http mode (no explicit --url provided; use --mode http --url <url>)"
        skip_test "http-mode: all tests" "no --url provided"
      fi
      run_docker_mode
      ;;
  esac

  print_summary

  if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
  fi
  exit 0
}

main "$@"
