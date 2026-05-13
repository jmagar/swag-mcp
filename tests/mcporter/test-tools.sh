#!/usr/bin/env bash
# =============================================================================
# test-tools.sh — Live integration contract test for swag-mcp MCP tools/resources
#
# Exercises every `swag` action plus `swag_help`, validates action-specific
# structured results, checks generated files on disk when a host bind path is
# available, and validates all advertised MCP resources through mcporter.
#
# Environment is sourced from .env when present.
#
# Usage:
#   ./tests/mcporter/test-tools.sh [--url URL] [--token TOKEN] [--env-file PATH]
#                                  [--health-domain DOMAIN] [--timeout-ms N]
#                                  [--verbose]
#
# Exit codes:
#   0 — all tests passed
#   1 — one or more tests failed
#   2 — prerequisite or endpoint check failed
# =============================================================================

set -uo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)"
readonly SCRIPT_NAME="$(basename -- "${BASH_SOURCE[0]}")"
readonly TS_START="$(date +%s%N)"
readonly LOG_FILE="${TMPDIR:-/tmp}/${SCRIPT_NAME%.sh}.$(date +%Y%m%d-%H%M%S).log"
readonly DEFAULT_ENV_FILE="${PROJECT_DIR}/.env"
readonly TEST_ID="mcporter-$(( $(date +%s) % 1000000 ))-$$"
readonly TEST_CONFIG="${TEST_ID}.subdomain.conf"
readonly TEST_DOMAIN="${TEST_ID}.example.com"
readonly TEST_UPSTREAM="mcporter-app"
readonly TEST_UPDATED_UPSTREAM="mcporter-updated-app"
readonly TEST_PORT="65530"
readonly TEST_UPDATED_PORT="65531"
readonly TEST_MCP_PATH="/mcp-${TEST_ID}"

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

CALL_TIMEOUT_MS=25000
VERBOSE=false
ENV_FILE="${SWAG_MCP_ENV_FILE:-${DEFAULT_ENV_FILE}}"
BASE_URL=""
TOKEN="${SWAG_MCP_TOKEN:-}"
HEALTH_DOMAIN="${SWAG_MCP_HEALTH_DOMAIN:-}"
MCP_URL=""
MCPORTER_CONFIG_FILE=""
MCPORTER_ROOT=""
PROXY_CONFS_HOST_PATH="${SWAG_MCP_PROXY_CONFS_HOST_PATH:-}"

PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
BLOCK_COUNT=0
declare -a FAIL_NAMES=()
declare -a BLOCK_NAMES=()
declare -a BLOCK_REASONS=()
WRITE_CAPABILITY="unknown"
DISK_VERIFY_CAPABILITY="unknown"

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --timeout-ms)
        CALL_TIMEOUT_MS="${2:?--timeout-ms requires a value}"
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
      --env-file)
        ENV_FILE="${2:?--env-file requires a value}"
        shift 2
        ;;
      --health-domain)
        HEALTH_DOMAIN="${2:?--health-domain requires a value}"
        shift 2
        ;;
      --parallel)
        log_warn "--parallel is no longer supported; full lifecycle/resource tests are ordered"
        shift
        ;;
      --verbose)
        VERBOSE=true
        shift
        ;;
      -h|--help)
        printf 'Usage: %s [--url URL] [--token TOKEN] [--env-file PATH] [--health-domain DOMAIN] [--timeout-ms N] [--verbose]\n' "${SCRIPT_NAME}"
        exit 0
        ;;
      *)
        printf '[ERROR] Unknown argument: %s\n' "$1" >&2
        exit 2
        ;;
    esac
  done
}

log_info()  { printf "${C_CYAN}[INFO]${C_RESET}  %s\n" "$*" | tee -a "${LOG_FILE}"; }
log_warn()  { printf "${C_YELLOW}[WARN]${C_RESET}  %s\n" "$*" | tee -a "${LOG_FILE}"; }
log_error() { printf "${C_RED}[ERROR]${C_RESET} %s\n" "$*" | tee -a "${LOG_FILE}" >&2; }

cleanup() {
  local rc=$?
  if [[ -n "${MCPORTER_CONFIG_FILE}" && -f "${MCPORTER_CONFIG_FILE}" ]]; then
    mcporter_call swag "$(_json_payload '{"action":"remove","config_name":$name,"create_backup":false}' name="${TEST_CONFIG}")" >/dev/null 2>&1 || true
    rm -f -- "${MCPORTER_CONFIG_FILE}"
  fi
  if [[ $rc -ne 0 ]]; then
    log_warn "Script exited with rc=${rc}. Log: ${LOG_FILE}"
  fi
}
trap cleanup EXIT

load_environment() {
  if [[ -f "${ENV_FILE}" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${ENV_FILE}"
    set +a
    log_info "Environment loaded from ${ENV_FILE}"
  else
    log_warn "Environment file not found: ${ENV_FILE}; using shell environment and defaults"
  fi

  TOKEN="${TOKEN:-${SWAG_MCP_TOKEN:-}}"
  HEALTH_DOMAIN="${HEALTH_DOMAIN:-${SWAG_MCP_HEALTH_DOMAIN:-}}"
  PROXY_CONFS_HOST_PATH="${PROXY_CONFS_HOST_PATH:-${SWAG_MCP_PROXY_CONFS_HOST_PATH:-}}"

  if [[ -z "${BASE_URL}" ]]; then
    if [[ -n "${SWAG_MCP_URL:-}" ]]; then
      BASE_URL="${SWAG_MCP_URL}"
    else
      BASE_URL="http://${SWAG_MCP_BIND_ADDRESS:-localhost}:${SWAG_MCP_PORT:-49152}"
    fi
  fi

  MCP_URL="${BASE_URL%/}"
  if [[ "${MCP_URL}" != */mcp ]]; then
    MCP_URL="${MCP_URL}/mcp"
  fi

  MCPORTER_CONFIG_FILE="$(mktemp "${TMPDIR:-/tmp}/swag-mcp.mcporter.XXXXXX.json")"
  if [[ -n "${TOKEN}" ]]; then
    jq -n --arg url "${MCP_URL}" --arg token "Bearer ${TOKEN}" \
      '{mcpServers: {"swag-http": {baseUrl: $url, headers: {Authorization: $token}}}}' \
      > "${MCPORTER_CONFIG_FILE}"
    log_info "Configured mcporter HTTP endpoint ${MCP_URL} with bearer auth"
  else
    jq -n --arg url "${MCP_URL}" \
      '{mcpServers: {"swag-http": {baseUrl: $url}}}' \
      > "${MCPORTER_CONFIG_FILE}"
    log_info "Configured mcporter HTTP endpoint ${MCP_URL} without bearer auth"
  fi

  if [[ -n "${PROXY_CONFS_HOST_PATH}" && -d "${PROXY_CONFS_HOST_PATH}" ]]; then
    DISK_VERIFY_CAPABILITY="available"
  else
    DISK_VERIFY_CAPABILITY="blocked"
  fi
}

json_assert_tool_named() {
  local label="${1:?label required}" json_payload="${2:?json payload required}" tool_name="${3:?tool name required}"
  local t0
  t0="$(date +%s%N)"
  local check
  check="$(
    printf '%s' "${json_payload}" | TOOL_NAME="${tool_name}" python3 -c '
import json
import os
import sys

data = json.load(sys.stdin)
tool_name = os.environ["TOOL_NAME"]
tools = data.get("tools", [])
if any(isinstance(tool, dict) and tool.get("name") == tool_name for tool in tools):
    print("ok")
else:
    print(f"tool not found: {tool_name}")
    raise SystemExit(1)
'
  )" || {
    record_fail "${label}" "${check}" "$(( ( $(date +%s%N) - t0 ) / 1000000 ))"
    return 1
  }
  record_pass "${label}" "$(( ( $(date +%s%N) - t0 ) / 1000000 ))"
}

json_assert_tool_has_property() {
  local label="${1:?label required}" json_payload="${2:?json payload required}" tool_name="${3:?tool name required}" property="${4:?property required}"
  local t0
  t0="$(date +%s%N)"
  local check
  check="$(
    printf '%s' "${json_payload}" | TOOL_NAME="${tool_name}" PROPERTY="${property}" python3 -c '
import json
import os
import sys

data = json.load(sys.stdin)
tool_name = os.environ["TOOL_NAME"]
property_name = os.environ["PROPERTY"]
for tool in data.get("tools", []):
    if isinstance(tool, dict) and tool.get("name") == tool_name:
        properties = tool.get("inputSchema", {}).get("properties", {})
        if property_name in properties:
            print("ok")
            raise SystemExit(0)
print(f"property {property_name} not found on tool {tool_name}")
raise SystemExit(1)
'
  )" || {
    record_fail "${label}" "${check}" "$(( ( $(date +%s%N) - t0 ) / 1000000 ))"
    return 1
  }
  record_pass "${label}" "$(( ( $(date +%s%N) - t0 ) / 1000000 ))"
}

json_assert_string_contains_all() {
  local label="${1:?label required}" json_payload="${2:?json payload required}"
  shift 2
  local t0
  t0="$(date +%s%N)"
  local check
  local payload="${json_payload}"
  check="$(
    JSON_PAYLOAD="${payload}" python3 - "$@" <<'PY'
import json
import os
import sys

needles = sys.argv[1:]
data = json.loads(os.environ["JSON_PAYLOAD"])
text = str(data)
missing = [needle for needle in needles if needle not in text]
if missing:
    print(f"missing strings: {missing}")
    raise SystemExit(1)
print("ok")
PY
  )" || {
    record_fail "${label}" "${check}" "$(( ( $(date +%s%N) - t0 ) / 1000000 ))"
    return 1
  }
  record_pass "${label}" "$(( ( $(date +%s%N) - t0 ) / 1000000 ))"
}

assert_tool_error() {
  local label="${1:?label required}" output="${2:?output required}" expected_action="${3:-}" expected_fragment="${4:-}"
  local json_payload
  json_payload="$(printf '%s' "${output}" | extract_tool_json 2>>"${LOG_FILE}")" || {
    record_fail "${label}" "could not extract structured JSON"
    return 1
  }

  local check
  check="$(
    printf '%s' "${json_payload}" | EXPECTED_ACTION="${expected_action}" EXPECTED_FRAGMENT="${expected_fragment}" python3 -c '
import json
import os
import sys

data = json.load(sys.stdin)
expected_action = os.environ.get("EXPECTED_ACTION", "")
expected_fragment = os.environ.get("EXPECTED_FRAGMENT", "")
if not isinstance(data, dict):
    print(f"expected structured success=false error, got {data!r}")
    raise SystemExit(1)

error_text = str(data.get("error", ""))
is_error = data.get("success") is False
if data.get("isError") is True:
    is_error = True
    error_text = " ".join(
        str(item.get("text", "")) for item in data.get("content", []) if isinstance(item, dict)
    )

if not is_error:
    print(f"expected structured error, got {data!r}")
    raise SystemExit(1)
if expected_action and data.get("action") not in ("", None, expected_action):
    print(f"expected action {expected_action!r}, got {data.get('action')!r}")
    raise SystemExit(1)
if expected_fragment and expected_fragment.lower() not in error_text.lower():
    print(f"expected error to contain {expected_fragment!r}, got {error_text!r}")
    raise SystemExit(1)
print("ok")
'
  )" || {
    record_fail "${label}" "${check}"
    return 1
  }
  record_pass "${label}"
}

resource_text_json() {
  python3 -c '
import json
import sys

data = json.load(sys.stdin)
contents = data.get("contents", [])
if not contents:
    raise SystemExit(1)
text = contents[0].get("text", "")
print(json.dumps(json.loads(text)))
'
}

assert_resource_text_json_field() {
  local label="${1:?label required}" output="${2-}" field="${3:?field required}" expected="${4:?expected required}"
  if [[ -z "${output}" ]]; then
    record_fail "${label}" "empty resource output"
    return 1
  fi

  local json_payload
  json_payload="$(printf '%s' "${output}" | resource_text_json 2>>"${LOG_FILE}")" || {
    record_fail "${label}" "resource text was not JSON"
    return 1
  }
  json_assert_equals "${label}" "${json_payload}" "${field}" "${expected}"
}

check_prerequisites() {
  local missing=false

  for cmd in mcporter jq python3 node; do
    if ! command -v "${cmd}" &>/dev/null; then
      log_error "${cmd} not found in PATH"
      missing=true
    fi
  done

  if [[ ! -f "${PROJECT_DIR}/pyproject.toml" ]]; then
    log_error "pyproject.toml not found at ${PROJECT_DIR}. Wrong directory?"
    missing=true
  fi

  if command -v mcporter &>/dev/null; then
    local mcporter_bin
    mcporter_bin="$(readlink -f "$(command -v mcporter)")"
    MCPORTER_ROOT="$(cd -- "$(dirname -- "${mcporter_bin}")/.." && pwd -P)"
    if [[ ! -f "${MCPORTER_ROOT}/dist/index.js" ]]; then
      log_error "Could not locate mcporter runtime at ${MCPORTER_ROOT}/dist/index.js"
      missing=true
    fi
  fi

  if [[ "${missing}" == true ]]; then
    return 2
  fi
}

preflight_write_capability() {
  WRITE_CAPABILITY="available"

  if command -v docker &>/dev/null && [[ -f "${PROJECT_DIR}/docker-compose.yaml" ]]; then
    if docker compose ps swag-mcp --status running --format json >/dev/null 2>&1; then
      if ! docker compose exec -T swag-mcp sh -lc 'command -v nginx >/dev/null 2>&1' >/dev/null 2>&1; then
        WRITE_CAPABILITY="blocked"
        block_test "write lifecycle preflight" "nginx is unavailable in the running swag-mcp container; create/edit/update validation will fail closed"
      fi
    fi
  fi

  if [[ "${DISK_VERIFY_CAPABILITY}" != "available" ]]; then
    block_test "disk verification preflight" "SWAG_MCP_PROXY_CONFS_HOST_PATH is unavailable; on-disk content checks will be skipped"
  fi

  log_info "Write capability: ${WRITE_CAPABILITY}; disk verification: ${DISK_VERIFY_CAPABILITY}"
}

mcporter_call() {
  local tool="${1:?tool required}"
  local args_json="${2:?args_json required}"

  mcporter --config "${MCPORTER_CONFIG_FILE}" call \
    "swag-http.${tool}" \
    --args "${args_json}" \
    --timeout "${CALL_TIMEOUT_MS}" \
    --output json \
    2>>"${LOG_FILE}"
}

mcporter_list_resources() {
  node --input-type=module - "${MCPORTER_ROOT}" "${MCPORTER_CONFIG_FILE}" <<'NODE'
import { pathToFileURL } from "node:url";

const [root, configPath] = process.argv.slice(2);
const { createRuntime } = await import(pathToFileURL(`${root}/dist/index.js`).href);
const runtime = await createRuntime({ configPath });
try {
  const result = await runtime.listResources("swag-http");
  console.log(JSON.stringify(result, null, 2));
} finally {
  await runtime.close().catch(() => {});
}
NODE
}

mcporter_read_resource() {
  local uri="${1:?resource uri required}"
  node --input-type=module - "${MCPORTER_ROOT}" "${MCPORTER_CONFIG_FILE}" "${uri}" <<'NODE'
import { pathToFileURL } from "node:url";

const [root, configPath, uri] = process.argv.slice(2);
const { createRuntime } = await import(pathToFileURL(`${root}/dist/index.js`).href);
const runtime = await createRuntime({ configPath });
try {
  const context = await runtime.connect("swag-http");
  const result = await context.client.readResource({ uri });
  console.log(JSON.stringify(result, null, 2));
} finally {
  await runtime.close().catch(() => {});
}
NODE
}

record_pass() {
  local label="${1:?label required}" elapsed_ms="${2:-0}"
  printf "${C_GREEN}[PASS]${C_RESET} %-64s ${C_DIM}%dms${C_RESET}\n" "${label}" "${elapsed_ms}" | tee -a "${LOG_FILE}"
  PASS_COUNT=$(( PASS_COUNT + 1 ))
}

record_fail() {
  local label="${1:?label required}" reason="${2:-failed}" elapsed_ms="${3:-0}"
  printf "${C_RED}[FAIL]${C_RESET} %-64s ${C_DIM}%dms${C_RESET}\n" "${label}" "${elapsed_ms}" | tee -a "${LOG_FILE}"
  printf '       %s\n' "${reason}" | tee -a "${LOG_FILE}"
  FAIL_COUNT=$(( FAIL_COUNT + 1 ))
  FAIL_NAMES+=("${label}")
}

block_test() {
  local label="${1:?label required}" reason="${2:-blocked by environment}"
  printf "${C_YELLOW}[BLOCK]${C_RESET} %-63s %s\n" "${label}" "${reason}" | tee -a "${LOG_FILE}"
  BLOCK_COUNT=$(( BLOCK_COUNT + 1 ))
  BLOCK_NAMES+=("${label}")
  BLOCK_REASONS+=("${reason}")
}

skip_test() {
  local label="${1:?label required}" reason="${2:-not available}"
  printf "${C_YELLOW}[SKIP]${C_RESET} %-64s %s\n" "${label}" "${reason}" | tee -a "${LOG_FILE}"
  SKIP_COUNT=$(( SKIP_COUNT + 1 ))
}

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

extract_tool_json() {
  python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception as exc:
    print(f"invalid_json: {exc}", file=sys.stderr)
    raise SystemExit(2)

if isinstance(data, dict) and "error" in data and (
    "server" in data or "issue" in data or data.get("kind") == "error"
):
    print("mcporter_error: {}".format(data.get("error")), file=sys.stderr)
    raise SystemExit(2)

if isinstance(data, dict) and isinstance(data.get("structuredContent"), dict):
    data = data["structuredContent"]
elif isinstance(data, dict) and isinstance(data.get("result"), dict):
    result = data["result"]
    if isinstance(result.get("structuredContent"), dict):
        data = result["structuredContent"]

print(json.dumps(data))
'
}

json_assert() {
  local label="${1:?label required}" json_payload="${2-}" mode="${3:?mode required}"
  local path="${4:-}" expected="${5:-}"
  local t0
  t0="$(date +%s%N)"

  if [[ -z "${json_payload}" ]]; then
    record_fail "${label}" "empty JSON payload" 0
    return 1
  fi

  local check
  check="$(
    printf '%s' "${json_payload}" | MODE="${mode}" PATH_EXPR="${path}" EXPECTED="${expected}" python3 -c '
import json
import os
import sys

data = json.load(sys.stdin)
mode = os.environ["MODE"]
path = os.environ.get("PATH_EXPR", "")
expected = os.environ.get("EXPECTED", "")

def lookup(node, dotted):
    if not dotted:
        return node
    current = node
    for part in dotted.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(dotted)
    return current

try:
    value = lookup(data, path)
except Exception as exc:
    print(f"missing path {path}: {exc}")
    raise SystemExit(1)

ok = False
if mode == "equals":
    ok = str(value) == expected
elif mode == "truthy":
    ok = bool(value)
elif mode == "type":
    ok = (
        (expected == "list" and isinstance(value, list))
        or (expected == "dict" and isinstance(value, dict))
        or (expected == "str" and isinstance(value, str))
        or (expected == "int" and isinstance(value, int))
        or (expected == "bool" and isinstance(value, bool))
    )
elif mode == "not_none":
    ok = value is not None
elif mode == "list_contains":
    ok = isinstance(value, list) and expected in [str(item) for item in value]
elif mode == "resource_uri":
    ok = isinstance(value, list) and any(
        isinstance(item, dict) and item.get("uri") == expected for item in value
    )
elif mode == "text_contains":
    ok = expected in str(value)
else:
    print(f"unknown assertion mode: {mode}")
    raise SystemExit(1)

if not ok:
    print(f"assertion failed: mode={mode} path={path} expected={expected!r} value={value!r}")
    raise SystemExit(1)
print("ok")
'
  )" || {
    record_fail "${label}" "${check}" "$(( ( $(date +%s%N) - t0 ) / 1000000 ))"
    return 1
  }

  record_pass "${label}" "$(( ( $(date +%s%N) - t0 ) / 1000000 ))"
}

assert_json_expr() {
  local label="${1:?label required}" json_payload="${2-}" _expr="${3:?expr required}"
  record_fail "${label}" "legacy assert_json_expr is disabled; use named JSON assertions" 0
  return 1
}

json_assert_equals() { json_assert "$1" "$2" "equals" "$3" "$4"; }
json_assert_truthy() { json_assert "$1" "$2" "truthy" "$3"; }
json_assert_type() { json_assert "$1" "$2" "type" "$3" "$4"; }
json_assert_not_none() { json_assert "$1" "$2" "not_none" "$3"; }
json_assert_list_contains() { json_assert "$1" "$2" "list_contains" "$3" "$4"; }
json_assert_resource_uri() { json_assert "$1" "$2" "resource_uri" "resources" "$3"; }
json_assert_text_contains() { json_assert "$1" "$2" "text_contains" "$3" "$4"; }

assert_tool_success() {
  local label="${1:?label required}" output="${2:?output required}"
  local json_payload
  json_payload="$(printf '%s' "${output}" | extract_tool_json 2>>"${LOG_FILE}")" || {
    record_fail "${label}" "tool output was not valid success JSON"
    return 1
  }

  local check
  check="$(printf '%s' "${json_payload}" | python3 -c '
import json
import sys

data = json.load(sys.stdin)
if isinstance(data, dict) and data.get("success") is False:
    print(data.get("error", "success=false"))
    raise SystemExit(1)
if isinstance(data, dict) and "error" in data and not {"logs", "endpoint_results"} & set(data):
    print(data.get("error"))
    raise SystemExit(1)
print("ok")
')" || {
    record_fail "${label}" "${check}"
    return 1
  }

  record_pass "${label}"
}

assert_filename_result() {
  local label="${1:?label required}" output="${2:?output required}" expected="${3:?filename required}"
  local json_payload
  json_payload="$(printf '%s' "${output}" | extract_tool_json 2>>"${LOG_FILE}")" || {
    record_fail "${label}" "could not extract structured JSON"
    return 1
  }
  json_assert_equals "${label}" "${json_payload}" "filename" "${expected}"
}

assert_list_result() {
  local label="${1:?label required}" output="${2:?output required}" expected_filter="${3:?filter required}"
  local json_payload
  json_payload="$(printf '%s' "${output}" | extract_tool_json 2>>"${LOG_FILE}")" || {
    record_fail "${label}" "could not extract structured JSON"
    return 1
  }
  json_assert_equals "${label}: filter" "${json_payload}" "list_filter" "${expected_filter}"
  json_assert_not_none "${label}: total" "${json_payload}" "total_count"
  json_assert_type "${label}: configs" "${json_payload}" "configs" "list"
}

assert_view_content() {
  local label="${1:?label required}" output="${2:?output required}" expected_filename="${3:?filename required}"
  local json_payload
  json_payload="$(printf '%s' "${output}" | extract_tool_json 2>>"${LOG_FILE}")" || {
    record_fail "${label}" "could not extract structured JSON"
    return 1
  }
  json_assert_equals "${label}: filename" "${json_payload}" "filename" "${expected_filename}"
  json_assert_truthy "${label}: content present" "${json_payload}" "content"
}

assert_backup_created() {
  local label="${1:?label required}" output="${2:?output required}"
  local json_payload
  json_payload="$(printf '%s' "${output}" | extract_tool_json 2>>"${LOG_FILE}")" || {
    record_fail "${label}" "could not extract structured JSON"
    return 1
  }
  json_assert_truthy "${label}" "${json_payload}" "backup_created"
}

assert_health_result() {
  local label="${1:?label required}" output="${2:?output required}" expected="${3:?domain required}"
  local json_payload
  json_payload="$(printf '%s' "${output}" | extract_tool_json 2>>"${LOG_FILE}")" || {
    record_fail "${label}" "could not extract structured JSON"
    return 1
  }
  json_assert_equals "${label}: domain" "${json_payload}" "domain" "${expected}"
  json_assert_type "${label}: endpoint results" "${json_payload}" "endpoint_results" "list"
}

config_path() {
  printf '%s/%s' "${PROXY_CONFS_HOST_PATH%/}" "${TEST_CONFIG}"
}

assert_file_contains() {
  local label="${1:?label required}" pattern="${2:?pattern required}"
  if [[ -z "${PROXY_CONFS_HOST_PATH}" || ! -d "${PROXY_CONFS_HOST_PATH}" ]]; then
    block_test "${label}" "SWAG_MCP_PROXY_CONFS_HOST_PATH is unavailable"
    return 0
  fi

  if grep -Fq -- "${pattern}" "$(config_path)"; then
    record_pass "${label}"
  else
    record_fail "${label}" "expected $(config_path) to contain: ${pattern}"
    return 1
  fi
}

assert_file_not_exists() {
  local label="${1:?label required}"
  if [[ -z "${PROXY_CONFS_HOST_PATH}" || ! -d "${PROXY_CONFS_HOST_PATH}" ]]; then
    block_test "${label}" "SWAG_MCP_PROXY_CONFS_HOST_PATH is unavailable"
    return 0
  fi

  if [[ ! -e "$(config_path)" ]]; then
    record_pass "${label}"
  else
    record_fail "${label}" "expected file to be removed: $(config_path)"
    return 1
  fi
}

assert_backups_for_test_config() {
  local label="${1:?label required}"
  if [[ "${DISK_VERIFY_CAPABILITY}" != "available" ]]; then
    block_test "${label}" "SWAG_MCP_PROXY_CONFS_HOST_PATH is unavailable"
    return 0
  fi

  local count
  count="$(find "${PROXY_CONFS_HOST_PATH}" -maxdepth 1 -type f -name "${TEST_CONFIG}.backup.*" | wc -l)"
  if [[ "${count}" -gt 0 ]]; then
    record_pass "${label}"
  else
    record_fail "${label}" "expected at least one backup for ${TEST_CONFIG}"
    return 1
  fi
}

cleanup_test_backups() {
  local label="${1:-cleanup test backups}"
  if [[ "${DISK_VERIFY_CAPABILITY}" != "available" ]]; then
    block_test "${label}" "SWAG_MCP_PROXY_CONFS_HOST_PATH is unavailable"
    return 0
  fi

  find "${PROXY_CONFS_HOST_PATH}" -maxdepth 1 -type f -name "${TEST_CONFIG}.backup.*" -delete
  local count
  count="$(find "${PROXY_CONFS_HOST_PATH}" -maxdepth 1 -type f -name "${TEST_CONFIG}.backup.*" | wc -l)"
  if [[ "${count}" -eq 0 ]]; then
    record_pass "${label}"
  else
    record_fail "${label}" "backup cleanup left ${count} files for ${TEST_CONFIG}"
    return 1
  fi
}

call_and_log() {
  local tool="${1:?tool required}" args_json="${2:?args_json required}"
  local output
  output="$(mcporter_call "${tool}" "${args_json}")" || true
  if [[ "${VERBOSE}" == true ]]; then
    printf '%s\n' "${output}" | tee -a "${LOG_FILE}" >&2
  else
    printf '%s\n' "${output}" >> "${LOG_FILE}"
  fi
  printf '%s' "${output}"
}

smoke_test_server() {
  log_info "Smoke-testing HTTP MCP endpoint..."
  local output
  output="$(call_and_log swag_help '{}')"

  if printf '%s' "${output}" | grep -q '"kind": "offline"'; then
    log_error "HTTP MCP endpoint is offline at ${MCP_URL}"
    return 2
  fi

  local json_payload
  json_payload="$(printf '%s' "${output}" | extract_tool_json 2>>"${LOG_FILE}")" || {
    log_error "Smoke-test response was not valid mcporter JSON"
    return 2
  }

  if ! printf '%s' "${json_payload}" | grep -q 'SWAG MCP Server'; then
    log_error "swag_help response did not contain expected help text"
    return 2
  fi

  log_info "HTTP MCP endpoint responded successfully."
}

suite_tool_contract() {
  printf '\n%b== tool contract ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"

  local list_output
  list_output="$(mcporter --config "${MCPORTER_CONFIG_FILE}" list swag-http --schema --all-parameters --json --timeout "${CALL_TIMEOUT_MS}" 2>>"${LOG_FILE}")" || true
  if [[ "${VERBOSE}" == true ]]; then
    printf '%s\n' "${list_output}" | tee -a "${LOG_FILE}"
  else
    printf '%s\n' "${list_output}" >> "${LOG_FILE}"
  fi

  json_assert_tool_named "tools/list exposes swag" "${list_output}" "swag"
  json_assert_tool_named "tools/list exposes swag_help" "${list_output}" "swag_help"
  json_assert_tool_has_property "swag schema exposes action" "${list_output}" "swag" "action"

  local help_output
  help_output="$(call_and_log swag_help '{}')"
  assert_tool_success "swag_help returns help text" "${help_output}"
  local help_json
  help_json="$(printf '%s' "${help_output}" | extract_tool_json 2>>"${LOG_FILE}")" || return 1
  json_assert_string_contains_all \
    "swag_help documents all actions" \
    "${help_json}" \
    "list" "create" "view" "edit" "update" "remove" "logs" "backups" "health_check"
}

suite_list() {
  printf '\n%b== list configurations ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"

  local output
  output="$(call_and_log swag '{"action":"list","list_filter":"all","limit":5}')"
  assert_list_result "swag: list all" "${output}" "all"
  local all_json
  all_json="$(printf '%s' "${output}" | extract_tool_json 2>>"${LOG_FILE}")" || return 1
  json_assert_equals "swag: list all exact filter" "${all_json}" "list_filter" "all"

  output="$(call_and_log swag '{"action":"list","list_filter":"active","limit":5}')"
  assert_list_result "swag: list active" "${output}" "active"

  output="$(call_and_log swag '{"action":"list","list_filter":"samples","limit":5}')"
  assert_list_result "swag: list samples" "${output}" "samples"
}

suite_negative_contracts() {
  printf '\n%b== negative contracts ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"

  local output
  output="$(call_and_log swag '{"action":"not_a_real_action"}')"
  assert_tool_error "swag: invalid action returns structured error" "${output}" "" "action"

  output="$(call_and_log swag '{"action":"create"}')"
  assert_tool_error "swag: create missing params returns structured error" "${output}" "create" "required"

  output="$(call_and_log swag '{"action":"list","list_filter":"invalid"}')"
  assert_tool_error "swag: invalid list_filter returns structured error" "${output}" "list" "list_filter"

  output="$(call_and_log swag "$(_json_payload '{"action":"view","config_name":$name}' name="../bad.subdomain.conf")")"
  assert_tool_error "swag: path traversal config_name rejected" "${output}" "view" "path"

  output="$(call_and_log swag '{"action":"update","config_name":"missing.subdomain.conf","update_field":"invalid","update_value":"x"}')"
  assert_tool_error "swag: invalid update_field returns structured error" "${output}" "update" "update_field"
}

suite_lifecycle() {
  printf '\n%b== lifecycle: create/view/update/edit/remove ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"

  if [[ "${WRITE_CAPABILITY}" == "blocked" ]]; then
    block_test "swag: lifecycle write actions" "write lifecycle skipped because preflight found nginx validation unavailable"
    return 0
  fi

  call_and_log swag "$(_json_payload '{"action":"remove","config_name":$name,"create_backup":false}' name="${TEST_CONFIG}")" >/dev/null

  local output
  output="$(call_and_log swag "$(
    jq -n \
      --arg config_name "${TEST_CONFIG}" \
      --arg server_name "${TEST_DOMAIN}" \
      --arg upstream_app "${TEST_UPSTREAM}" \
      --argjson upstream_port "${TEST_PORT}" \
      '{"action":"create","config_name":$config_name,"server_name":$server_name,"upstream_app":$upstream_app,"upstream_port":$upstream_port,"upstream_proto":"http","auth_method":"none","enable_quic":false}'
  )")"
  if ! assert_filename_result "swag: create returns filename" "${output}" "${TEST_CONFIG}"; then
    log_error "Create failed; skipping dependent lifecycle assertions for ${TEST_CONFIG}"
    return 0
  fi
  assert_file_contains "create wrote server_name" "${TEST_DOMAIN}"
  assert_file_contains "create wrote upstream app" "${TEST_UPSTREAM}"
  assert_file_contains "create wrote upstream port" "${TEST_PORT}"

  output="$(call_and_log swag "$(_json_payload '{"action":"list","list_filter":"all","query":$query,"limit":10}' query="${TEST_ID}")")"
  assert_list_result "swag: list query includes created config" "${output}" "all"
  local list_json
  list_json="$(printf '%s' "${output}" | extract_tool_json 2>>"${LOG_FILE}")" || return 1
  json_assert_list_contains "swag: list query exact config" "${list_json}" "configs" "${TEST_CONFIG}"

  output="$(call_and_log swag "$(_json_payload '{"action":"view","config_name":$name}' name="${TEST_CONFIG}")")"
  assert_view_content "swag: view config" "${output}" "${TEST_CONFIG}"

  output="$(call_and_log swag "$(_json_payload '{"action":"update","config_name":$name,"update_field":"port","update_value":$value,"create_backup":false}' name="${TEST_CONFIG}" value="${TEST_UPDATED_PORT}")")"
  assert_filename_result "swag: update port returns filename" "${output}" "${TEST_CONFIG}"
  assert_file_contains "update port persisted" "${TEST_UPDATED_PORT}"

  output="$(call_and_log swag "$(_json_payload '{"action":"update","config_name":$name,"update_field":"upstream","update_value":$value,"create_backup":false}' name="${TEST_CONFIG}" value="${TEST_UPDATED_UPSTREAM}")")"
  assert_filename_result "swag: update upstream returns filename" "${output}" "${TEST_CONFIG}"
  assert_file_contains "update upstream persisted" "${TEST_UPDATED_UPSTREAM}"

  output="$(call_and_log swag "$(_json_payload '{"action":"update","config_name":$name,"update_field":"app","update_value":$value,"create_backup":false}' name="${TEST_CONFIG}" value="${TEST_UPSTREAM}:${TEST_PORT}")")"
  assert_filename_result "swag: update app returns filename" "${output}" "${TEST_CONFIG}"
  assert_file_contains "update app restored upstream" "${TEST_UPSTREAM}"
  assert_file_contains "update app restored port" "${TEST_PORT}"

  output="$(call_and_log swag "$(_json_payload '{"action":"update","config_name":$name,"update_field":"add_mcp","update_value":$value,"create_backup":false}' name="${TEST_CONFIG}" value="${TEST_MCP_PATH}")")"
  assert_filename_result "swag: update add_mcp returns filename" "${output}" "${TEST_CONFIG}"
  assert_file_contains "update add_mcp persisted path" "${TEST_MCP_PATH}"

  local edit_content
  edit_content="# mcporter edit smoke
server {
    listen 127.0.0.1:8443;
    server_name ${TEST_DOMAIN};
    location / {
        proxy_pass http://${TEST_UPSTREAM}:${TEST_PORT};
    }
}
"
  output="$(call_and_log swag "$(
    jq -n \
      --arg config_name "${TEST_CONFIG}" \
      --arg new_content "${edit_content}" \
      '{"action":"edit","config_name":$config_name,"new_content":$new_content,"create_backup":true}'
  )")"
  assert_filename_result "swag: edit returns filename" "${output}" "${TEST_CONFIG}"
  assert_backup_created "swag: edit created backup" "${output}"
  assert_file_contains "edit content persisted" "mcporter edit smoke"

  output="$(call_and_log swag "$(_json_payload '{"action":"remove","config_name":$name,"create_backup":true}' name="${TEST_CONFIG}")")"
  assert_filename_result "swag: remove returns filename" "${output}" "${TEST_CONFIG}"
  assert_backup_created "swag: remove created backup" "${output}"
  assert_file_not_exists "remove deleted config file"
  assert_backups_for_test_config "remove backup exists on disk"
  cleanup_test_backups "cleanup test backups"
}

suite_logs() {
  printf '\n%b== logs ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"

  local log_type output json_payload
  for log_type in nginx-error nginx-access fail2ban letsencrypt renewal; do
    output="$(call_and_log swag "$(_json_payload '{"action":"logs","log_type":$log_type,"lines":"3"}' log_type="${log_type}")")"
    json_payload="$(printf '%s' "${output}" | extract_tool_json 2>>"${LOG_FILE}")" || {
      record_fail "swag: logs ${log_type}" "could not extract structured JSON"
      continue
    }
    json_assert_truthy "swag: logs ${log_type} returns logs" "${json_payload}" "logs"
    json_assert_type "swag: logs ${log_type} returns character_count" "${json_payload}" "character_count" "int"
  done
}

suite_backups() {
  printf '\n%b== backups ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"

  local output json_payload
  output="$(call_and_log swag '{"action":"backups","backup_action":"list"}')"
  json_payload="$(printf '%s' "${output}" | extract_tool_json 2>>"${LOG_FILE}")" || {
    record_fail "swag: backups list" "could not extract structured JSON"
    return 1
  }
  json_assert_not_none "swag: backups list total_count" "${json_payload}" "total_count"
  json_assert_type "swag: backups list files" "${json_payload}" "backup_files" "list"

  output="$(call_and_log swag '{"action":"backups","backup_action":"cleanup","retention_days":999999}')"
  json_payload="$(printf '%s' "${output}" | extract_tool_json 2>>"${LOG_FILE}")" || {
    record_fail "swag: backups cleanup" "could not extract structured JSON"
    return 1
  }
  json_assert_equals "swag: backups cleanup retention" "${json_payload}" "retention_days" "999999"
  json_assert_type "swag: backups cleanup cleaned_count" "${json_payload}" "cleaned_count" "int"
}

suite_health() {
  printf '\n%b== health check ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"

  local output invalid_domain
  invalid_domain="nonexistent-${TEST_ID}.invalid"
  output="$(call_and_log swag "$(_json_payload '{"action":"health_check","domain":$domain,"timeout":"5","follow_redirects":true}' domain="${invalid_domain}")")"
  assert_health_result "swag: health_check invalid domain handled" "${output}" "${invalid_domain}"

  if [[ -n "${HEALTH_DOMAIN}" ]]; then
    output="$(call_and_log swag "$(_json_payload '{"action":"health_check","domain":$domain,"timeout":"10","follow_redirects":true}' domain="${HEALTH_DOMAIN}")")"
    assert_health_result "swag: health_check configured domain" "${output}" "${HEALTH_DOMAIN}"
  else
    skip_test "swag: health_check configured domain" "set SWAG_MCP_HEALTH_DOMAIN or pass --health-domain"
  fi
}

suite_resources() {
  printf '\n%b== resources ==%b\n' "${C_BOLD}" "${C_RESET}" | tee -a "${LOG_FILE}"

  local output
  output="$(mcporter_list_resources 2>>"${LOG_FILE}")" || true
  if [[ "${VERBOSE}" == true ]]; then
    printf '%s\n' "${output}" | tee -a "${LOG_FILE}"
  else
    printf '%s\n' "${output}" >> "${LOG_FILE}"
  fi

  json_assert_resource_uri "resources/list exposes swag://" "${output}" "swag://"
  json_assert_resource_uri "resources/list exposes configs/live" "${output}" "swag://configs/live"
  json_assert_resource_uri "resources/list exposes health/stream" "${output}" "swag://health/stream"
  json_assert_resource_uri "resources/list exposes logs/stream" "${output}" "swag://logs/stream"

  output="$(mcporter_read_resource 'swag://' 2>>"${LOG_FILE}")" || true
  printf '%s\n' "${output}" >> "${LOG_FILE}"
  json_assert_type "resources/read swag:// returns contents" "${output}" "contents" "list"
  json_assert_text_contains "resources/read swag:// contains files JSON" "${output}" "contents" "files"

  local resource_uri
  for resource_uri in 'swag://configs/live' 'swag://health/stream' 'swag://logs/stream'; do
    output="$(mcporter_read_resource "${resource_uri}" 2>>"${LOG_FILE}")" || true
    printf '%s\n' "${output}" >> "${LOG_FILE}"
    if ! json_assert_type "resources/read ${resource_uri}" "${output}" "contents" "list"; then
      continue
    fi
    case "${resource_uri}" in
      'swag://configs/live')
        assert_resource_text_json_field "resources/read configs/live type" "${output}" "type" "watcher_snapshot"
        ;;
      'swag://health/stream')
        assert_resource_text_json_field "resources/read health/stream type" "${output}" "type" "health_snapshot"
        ;;
      'swag://logs/stream')
        json_assert_text_contains "resources/read logs/stream header" "${output}" "contents" "SWAG nginx-error Log Stream"
        ;;
    esac
  done
}

print_summary() {
  local total_ms="$(( ( $(date +%s%N) - TS_START ) / 1000000 ))"
  local total=$(( PASS_COUNT + FAIL_COUNT + SKIP_COUNT + BLOCK_COUNT ))

  printf '\n%b%s%b\n' "${C_BOLD}" "$(printf '=%.0s' {1..72})" "${C_RESET}"
  printf '%b%-20s%b  %b%d%b\n' "${C_BOLD}" "PASS" "${C_RESET}" "${C_GREEN}" "${PASS_COUNT}" "${C_RESET}"
  printf '%b%-20s%b  %b%d%b\n' "${C_BOLD}" "FAIL" "${C_RESET}" "${C_RED}"   "${FAIL_COUNT}" "${C_RESET}"
  printf '%b%-20s%b  %b%d%b\n' "${C_BOLD}" "SKIP" "${C_RESET}" "${C_YELLOW}" "${SKIP_COUNT}" "${C_RESET}"
  printf '%b%-20s%b  %b%d%b\n' "${C_BOLD}" "BLOCK" "${C_RESET}" "${C_YELLOW}" "${BLOCK_COUNT}" "${C_RESET}"
  printf '%b%-20s%b  %d\n' "${C_BOLD}" "TOTAL" "${C_RESET}" "${total}"
  printf '%b%-20s%b  %ds (%dms)\n' "${C_BOLD}" "ELAPSED" "${C_RESET}" "$(( total_ms / 1000 ))" "${total_ms}"
  printf '%b%s%b\n' "${C_BOLD}" "$(printf '=%.0s' {1..72})" "${C_RESET}"

  if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    printf '\n%bFailed tests:%b\n' "${C_RED}" "${C_RESET}"
    local name
    for name in "${FAIL_NAMES[@]}"; do
      printf '  - %s\n' "${name}"
    done
    printf '\nFull log: %s\n' "${LOG_FILE}"
  fi

  print_blockers
}

print_blockers() {
  if [[ "${BLOCK_COUNT}" -eq 0 ]]; then
    return 0
  fi

  printf '\n%bBlocked checks:%b\n' "${C_YELLOW}" "${C_RESET}"
  local i
  for i in "${!BLOCK_NAMES[@]}"; do
    printf '  - %s: %s\n' "${BLOCK_NAMES[$i]}" "${BLOCK_REASONS[$i]}"
  done
}

run_all() {
  suite_tool_contract
  suite_list
  suite_negative_contracts
  suite_lifecycle
  suite_logs
  suite_backups
  suite_health
  suite_resources
}

main() {
  parse_args "$@"

  printf '%b%s%b\n' "${C_BOLD}" "$(printf '=%.0s' {1..72})" "${C_RESET}"
  printf '%b  swag-mcp live mcporter contract test%b\n' "${C_BOLD}" "${C_RESET}"
  printf '%b  Project: %s%b\n' "${C_BOLD}" "${PROJECT_DIR}" "${C_RESET}"
  printf '%b  Timeout: %dms/call%b\n' "${C_BOLD}" "${CALL_TIMEOUT_MS}" "${C_RESET}"
  printf '%b  Test config: %s%b\n' "${C_BOLD}" "${TEST_CONFIG}" "${C_RESET}"
  printf '%b  Log: %s%b\n' "${C_BOLD}" "${LOG_FILE}" "${C_RESET}"
  printf '%b%s%b\n\n' "${C_BOLD}" "$(printf '=%.0s' {1..72})" "${C_RESET}"

  check_prerequisites || exit 2
  load_environment || exit 2
  smoke_test_server || exit 2
  preflight_write_capability

  run_all
  print_summary

  if [[ "${FAIL_COUNT}" -gt 0 ]]; then
    exit 1
  fi
  exit 0
}

main "$@"
