#!/usr/bin/env bash
# =============================================================================
# test-tools.sh — Integration smoke-test for swag-mcp MCP server tools
#
# Exercises non-destructive smoke coverage of the `swag` tool (action pattern).
# The server is launched ad-hoc via mcporter's --stdio flag.
#
# Credentials are sourced from ~/.claude-homelab/.env
# (SWAG_MCP_PROXY_CONFS_URI).
#
# Usage:
#   ./tests/mcporter/test-tools.sh [--timeout-ms N] [--parallel] [--verbose]
#
# Options:
#   --timeout-ms N   Per-call timeout in milliseconds (default: 25000)
#   --parallel       Run independent test groups in parallel (default: off)
#   --verbose        Print raw mcporter output for each call
#
# Exit codes:
#   0 — all tests passed or skipped
#   1 — one or more tests failed
#   2 — prerequisite check failed (mcporter, uv, server startup)
# =============================================================================

set -uo pipefail

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)"
readonly SCRIPT_NAME="$(basename -- "${BASH_SOURCE[0]}")"
readonly TS_START="$(date +%s%N)"
readonly LOG_FILE="${TMPDIR:-/tmp}/${SCRIPT_NAME%.sh}.$(date +%Y%m%d-%H%M%S).log"
readonly ENV_FILE="${HOME}/.claude-homelab/.env"
readonly STDIO_CMD="uv run python -m swag_mcp"

# Colours (disabled automatically when stdout is not a terminal)
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
# Defaults (overridable via flags)
# ---------------------------------------------------------------------------
CALL_TIMEOUT_MS=25000
USE_PARALLEL=false
VERBOSE=false

# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
declare -a FAIL_NAMES=()

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --timeout-ms)
        CALL_TIMEOUT_MS="${2:?--timeout-ms requires a value}"
        shift 2
        ;;
      --parallel)
        USE_PARALLEL=true
        shift
        ;;
      --verbose)
        VERBOSE=true
        shift
        ;;
      -h|--help)
        printf 'Usage: %s [--timeout-ms N] [--parallel] [--verbose]\n' "${SCRIPT_NAME}"
        exit 0
        ;;
      *)
        printf '[ERROR] Unknown argument: %s\n' "$1" >&2
        exit 2
        ;;
    esac
  done
}

# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------
log_info()  { printf "${C_CYAN}[INFO]${C_RESET}  %s\n" "$*" | tee -a "${LOG_FILE}"; }
log_warn()  { printf "${C_YELLOW}[WARN]${C_RESET}  %s\n" "$*" | tee -a "${LOG_FILE}"; }
log_error() { printf "${C_RED}[ERROR]${C_RESET} %s\n" "$*" | tee -a "${LOG_FILE}" >&2; }

# ---------------------------------------------------------------------------
# Cleanup trap
# ---------------------------------------------------------------------------
cleanup() {
  local rc=$?
  if [[ $rc -ne 0 ]]; then
    log_warn "Script exited with rc=${rc}. Log: ${LOG_FILE}"
  fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Load credentials from ~/.claude-homelab/.env
# ---------------------------------------------------------------------------
load_credentials() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    log_error "Credentials file not found: ${ENV_FILE}"
    log_error "Run scripts/setup-creds.sh or copy .env.example to ${ENV_FILE}"
    return 2
  fi

  # shellcheck source=/dev/null
  set -a
  source "${ENV_FILE}"
  set +a

  if [[ -z "${SWAG_MCP_PROXY_CONFS_URI:-}" ]]; then
    log_error "SWAG_MCP_PROXY_CONFS_URI is not set in ${ENV_FILE}"
    return 2
  fi

  log_info "Credentials loaded (SWAG_MCP_PROXY_CONFS_URI=${SWAG_MCP_PROXY_CONFS_URI})"
}

# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------
check_prerequisites() {
  local missing=false

  if ! command -v mcporter &>/dev/null; then
    log_error "mcporter not found in PATH. Install it and re-run."
    missing=true
  fi

  if ! command -v uv &>/dev/null; then
    log_error "uv not found in PATH. Install it and re-run."
    missing=true
  fi

  if ! command -v python3 &>/dev/null; then
    log_error "python3 not found in PATH."
    missing=true
  fi

  if ! command -v jq &>/dev/null; then
    log_error "jq not found in PATH. Install it and re-run."
    missing=true
  fi

  if [[ ! -f "${PROJECT_DIR}/pyproject.toml" ]]; then
    log_error "pyproject.toml not found at ${PROJECT_DIR}. Wrong directory?"
    missing=true
  fi

  if [[ "${missing}" == true ]]; then
    return 2
  fi
}

# ---------------------------------------------------------------------------
# Server startup smoke-test
# ---------------------------------------------------------------------------
smoke_test_server() {
  log_info "Smoke-testing server startup..."

  local output
  output="$(
    SWAG_MCP_PROXY_CONFS_URI="${SWAG_MCP_PROXY_CONFS_URI}" \
    mcporter call \
      --stdio "${STDIO_CMD}" \
      --cwd "${PROJECT_DIR}" \
      --name "swag-smoke" \
      --tool swag_help \
      --args '{}' \
      --timeout 30000 \
      --output json \
      2>&1
  )" || true

  if printf '%s' "${output}" | grep -q '"kind": "offline"'; then
    log_error "Server failed to start. Output:"
    printf '%s\n' "${output}" >&2
    log_error "Common causes:"
    log_error "  • Missing module: check 'uv run python -m swag_mcp' locally"
    log_error "  • SWAG_MCP_PROXY_CONFS_URI missing or unreachable"
    return 2
  fi

  log_info "Server started successfully."
  return 0
}

# ---------------------------------------------------------------------------
# mcporter call wrapper — passes env vars for each call
# ---------------------------------------------------------------------------
mcporter_call() {
  local tool="${1:?tool required}"
  local args_json="${2:?args_json required}"

  SWAG_MCP_PROXY_CONFS_URI="${SWAG_MCP_PROXY_CONFS_URI}" \
  mcporter call \
    --stdio "${STDIO_CMD}" \
    --cwd "${PROJECT_DIR}" \
    --name "swag" \
    --tool "${tool}" \
    --args "${args_json}" \
    --timeout "${CALL_TIMEOUT_MS}" \
    --output json \
    2>>"${LOG_FILE}"
}

# ---------------------------------------------------------------------------
# Test runner
#   Usage: run_test <label> <tool> <args_json> [expected_key]
# ---------------------------------------------------------------------------
run_test() {
  local label="${1:?label required}"
  local tool="${2:?tool required}"
  local args="${3:?args required}"
  local expected_key="${4:-}"

  local t0
  t0="$(date +%s%N)"

  local output
  output="$(mcporter_call "${tool}" "${args}")" || true

  local elapsed_ms
  elapsed_ms="$(( ( $(date +%s%N) - t0 ) / 1000000 ))"

  if [[ "${VERBOSE}" == true ]]; then
    printf '%s\n' "${output}" | tee -a "${LOG_FILE}"
  else
    printf '%s\n' "${output}" >> "${LOG_FILE}"
  fi

  # Detect server-offline
  if printf '%s' "${output}" | grep -q '"kind": "offline"'; then
    printf "${C_RED}[FAIL]${C_RESET} %-55s ${C_DIM}%dms${C_RESET}\n" \
      "${label}" "${elapsed_ms}" | tee -a "${LOG_FILE}"
    printf '       server offline — check startup errors in %s\n' "${LOG_FILE}" | tee -a "${LOG_FILE}"
    FAIL_COUNT=$(( FAIL_COUNT + 1 ))
    FAIL_NAMES+=("${label}")
    return 1
  fi

  # Validate JSON and check for error payload
  local json_check
  json_check="$(
    printf '%s' "${output}" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    if isinstance(d, dict) and ('error' in d or d.get('kind') == 'error'):
        print('error: ' + str(d.get('error', d.get('message', 'unknown error'))))
    else:
        print('ok')
except Exception as e:
    print('invalid_json: ' + str(e))
" 2>/dev/null
  )" || json_check="parse_error"

  if [[ "${json_check}" != "ok" ]]; then
    printf "${C_RED}[FAIL]${C_RESET} %-55s ${C_DIM}%dms${C_RESET}\n" \
      "${label}" "${elapsed_ms}" | tee -a "${LOG_FILE}"
    printf '       response validation failed: %s\n' "${json_check}" | tee -a "${LOG_FILE}"
    FAIL_COUNT=$(( FAIL_COUNT + 1 ))
    FAIL_NAMES+=("${label}")
    return 1
  fi

  # Validate optional key presence
  if [[ -n "${expected_key}" ]]; then
    local key_check
    key_check="$(
      printf '%s' "${output}" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    keys = '${expected_key}'.split('.')
    node = d
    for k in keys:
        if k:
            node = node[k]
    print('ok')
except Exception as e:
    print('missing: ' + str(e))
" 2>/dev/null
    )" || key_check="parse_error"

    if [[ "${key_check}" != "ok" ]]; then
      printf "${C_RED}[FAIL]${C_RESET} %-55s ${C_DIM}%dms${C_RESET}\n" \
        "${label}" "${elapsed_ms}" | tee -a "${LOG_FILE}"
      printf '       expected key .%s not found: %s\n' "${expected_key}" "${key_check}" | tee -a "${LOG_FILE}"
      FAIL_COUNT=$(( FAIL_COUNT + 1 ))
      FAIL_NAMES+=("${label}")
      return 1
    fi
  fi

  printf "${C_GREEN}[PASS]${C_RESET} %-55s ${C_DIM}%dms${C_RESET}\n" \
    "${label}" "${elapsed_ms}" | tee -a "${LOG_FILE}"
  PASS_COUNT=$(( PASS_COUNT + 1 ))
  return 0
}

# ---------------------------------------------------------------------------
# Skip helper
# ---------------------------------------------------------------------------
skip_test() {
  local label="${1:?label required}"
  local reason="${2:-prerequisite returned empty}"
  printf "${C_YELLOW}[SKIP]${C_RESET} %-55s %s\n" "${label}" "${reason}" | tee -a "${LOG_FILE}"
  SKIP_COUNT=$(( SKIP_COUNT + 1 ))
}

# ---------------------------------------------------------------------------
# Safe JSON payload builder
# ---------------------------------------------------------------------------
_json_payload() {
  local template="${1:?template required}"; shift
  local jq_args=()
  local pair k v
  for pair in "$@"; do
    k="${pair%%=*}"
    v="${pair#*=}"
    jq_args+=(--arg "$k" "$v")
  done
  jq -n "${jq_args[@]}" "$template"
}

# ---------------------------------------------------------------------------
# ID extractors
# ---------------------------------------------------------------------------

get_first_config_name() {
  local raw
  raw="$(mcporter_call swag '{"action":"list","list_filter":"active","limit":5}' 2>/dev/null)" || return 0
  printf '%s' "${raw}" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    configs = d.get('configs', d.get('items', d if isinstance(d, list) else []))
    if configs:
        name = configs[0].get('name', configs[0].get('filename', ''))
        print(name)
except Exception:
    pass
" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Grouped test suites
# ---------------------------------------------------------------------------

suite_help() {
  printf '\n%b== help ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"
  run_test "swag: help" "swag_help" '{}'
}

suite_list() {
  printf '\n%b== list configurations ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"

  run_test "swag: list all"     "swag" '{"action":"list","list_filter":"all"}'
  run_test "swag: list active"  "swag" '{"action":"list","list_filter":"active"}'
  run_test "swag: list samples" "swag" '{"action":"list","list_filter":"samples"}'
}

suite_view() {
  printf '\n%b== view configuration ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"

  local config_name
  config_name="$(get_first_config_name)" || config_name=''
  if [[ -n "${config_name}" ]]; then
    run_test "swag: view config" \
      "swag" \
      "$(_json_payload '{"action":"view","config_name":$name}' name="${config_name}")"
  else
    skip_test "swag: view config" "no active config found to view"
  fi
}

suite_health() {
  printf '\n%b== health check ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"

  run_test "swag: health_check" "swag" '{"action":"health_check"}'
}

suite_backups() {
  printf '\n%b== backups (read-only) ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"

  run_test "swag: backups list" "swag" '{"action":"backups","backup_subaction":"list"}'
  # backups cleanup is destructive — skipped
}

suite_logs() {
  printf '\n%b== logs ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"

  run_test "swag: logs" "swag" '{"action":"logs"}'
}

# ---------------------------------------------------------------------------
# Print final summary
# ---------------------------------------------------------------------------
print_summary() {
  local total_ms="$(( ( $(date +%s%N) - TS_START ) / 1000000 ))"
  local total=$(( PASS_COUNT + FAIL_COUNT + SKIP_COUNT ))

  printf '\n%b%s%b\n' "${C_BOLD}" "$(printf '=%.0s' {1..65})" "${C_RESET}"
  printf '%b%-20s%b  %b%d%b\n' "${C_BOLD}" "PASS" "${C_RESET}" "${C_GREEN}" "${PASS_COUNT}" "${C_RESET}"
  printf '%b%-20s%b  %b%d%b\n' "${C_BOLD}" "FAIL" "${C_RESET}" "${C_RED}"   "${FAIL_COUNT}" "${C_RESET}"
  printf '%b%-20s%b  %b%d%b\n' "${C_BOLD}" "SKIP" "${C_RESET}" "${C_YELLOW}" "${SKIP_COUNT}" "${C_RESET}"
  printf '%b%-20s%b  %d\n' "${C_BOLD}" "TOTAL" "${C_RESET}" "${total}"
  printf '%b%-20s%b  %ds (%dms)\n' "${C_BOLD}" "ELAPSED" "${C_RESET}" \
    "$(( total_ms / 1000 ))" "${total_ms}"
  printf '%b%s%b\n' "${C_BOLD}" "$(printf '=%.0s' {1..65})" "${C_RESET}"

  if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    printf '\n%bFailed tests:%b\n' "${C_RED}" "${C_RESET}"
    local name
    for name in "${FAIL_NAMES[@]}"; do
      printf '  • %s\n' "${name}"
    done
    printf '\nFull log: %s\n' "${LOG_FILE}"
  fi
}

# ---------------------------------------------------------------------------
# Sequential runner
# ---------------------------------------------------------------------------
run_sequential() {
  suite_help
  suite_list
  suite_view
  suite_health
  suite_backups
  suite_logs
}

# ---------------------------------------------------------------------------
# Parallel runner
# ---------------------------------------------------------------------------
run_parallel() {
  log_warn "--parallel mode: per-suite counters aggregated via temp files."

  local tmp_dir
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf -- "${tmp_dir}"' RETURN

  local suites=(
    suite_help
    suite_list
    suite_view
    suite_health
    suite_backups
    suite_logs
  )

  local pids=()
  local suite
  for suite in "${suites[@]}"; do
    (
      PASS_COUNT=0; FAIL_COUNT=0; SKIP_COUNT=0; FAIL_NAMES=()
      "${suite}"
      printf '%d %d %d\n' "${PASS_COUNT}" "${FAIL_COUNT}" "${SKIP_COUNT}" \
        > "${tmp_dir}/${suite}.counts"
      printf '%s\n' "${FAIL_NAMES[@]:-}" > "${tmp_dir}/${suite}.fails"
    ) &
    pids+=($!)
  done

  local pid
  for pid in "${pids[@]}"; do
    wait "${pid}" || true
  done

  local f
  for f in "${tmp_dir}"/*.counts; do
    [[ -f "${f}" ]] || continue
    local p fl s
    read -r p fl s < "${f}"
    PASS_COUNT=$(( PASS_COUNT + p ))
    FAIL_COUNT=$(( FAIL_COUNT + fl ))
    SKIP_COUNT=$(( SKIP_COUNT + s ))
  done

  for f in "${tmp_dir}"/*.fails; do
    [[ -f "${f}" ]] || continue
    while IFS= read -r line; do
      [[ -n "${line}" ]] && FAIL_NAMES+=("${line}")
    done < "${f}"
  done
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  parse_args "$@"

  printf '%b%s%b\n' "${C_BOLD}" "$(printf '=%.0s' {1..65})" "${C_RESET}"
  printf '%b  swag-mcp integration smoke-test (single swag tool)%b\n' "${C_BOLD}" "${C_RESET}"
  printf '%b  Project: %s%b\n' "${C_BOLD}" "${PROJECT_DIR}" "${C_RESET}"
  printf '%b  Timeout: %dms/call | Parallel: %s%b\n' \
    "${C_BOLD}" "${CALL_TIMEOUT_MS}" "${USE_PARALLEL}" "${C_RESET}"
  printf '%b  Log: %s%b\n' "${C_BOLD}" "${LOG_FILE}" "${C_RESET}"
  printf '%b%s%b\n\n' "${C_BOLD}" "$(printf '=%.0s' {1..65})" "${C_RESET}"

  load_credentials || exit 2
  check_prerequisites || exit 2

  smoke_test_server || {
    log_error ""
    log_error "Server startup failed. Aborting — no tests will run."
    log_error ""
    log_error "To diagnose, run:"
    log_error "  cd ${PROJECT_DIR} && SWAG_MCP_PROXY_CONFS_URI=... uv run python -m swag_mcp"
    exit 2
  }

  if [[ "${USE_PARALLEL}" == true ]]; then
    run_parallel
  else
    run_sequential
  fi

  print_summary

  if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
  fi
  exit 0
}

main "$@"
