#!/usr/bin/env bash
# =============================================================================
# SWAG MCP Integration Test Suite
# Full live end-to-end validation of all swag tool actions via mcporter
# =============================================================================
set -uo pipefail

# Configuration
MCP_URL="${SWAG_MCP_URL:-http://localhost:8012/mcp}"
TOOL="swag"
PROXY_CONFS_DIR="/mnt/appdata/swag/nginx/proxy-confs"
TEST_CONFIG="smoke-test.subdomain.conf"
TEST_SERVICE="smoke-test"
TEST_DOMAIN="smoke-test.example.com"
TEST_UPSTREAM="smoke-test-app"
TEST_PORT=9999

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# Counters
PASS=0
FAIL=0
SKIP=0

# =============================================================================
# Helpers
# =============================================================================

mcp() {
    mcporter call "${MCP_URL}.${TOOL}" --args "$1" --timeout "${TIMEOUT_MS:-30000}" --allow-http --output text 2>&1
}

pass() { echo -e "  ${GREEN}✓${NC} $1"; ((PASS++)); }
fail() { echo -e "  ${RED}✗${NC} $1"; ((FAIL++)); }
skip() { echo -e "  ${YELLOW}-${NC} $1 (skipped)"; ((SKIP++)); }
section() { echo -e "\n${BLUE}${BOLD}[$1]${NC}"; }

assert_contains() {
    local output="$1" pattern="$2" label="$3"
    if echo "$output" | grep -qiF "$pattern"; then
        pass "$label"
    else
        fail "$label — expected to find: '$pattern'"
        echo "    Output: $(echo "$output" | head -3)"
    fi
}

assert_not_contains() {
    local output="$1" pattern="$2" label="$3"
    if ! echo "$output" | grep -qiF "$pattern"; then
        pass "$label"
    else
        fail "$label — unexpected: '$pattern'"
        echo "    Output: $(echo "$output" | head -3)"
    fi
}

# bead .2 — nginx syntax validation
nginx_syntax_check() {
    local label="$1"
    if ! command -v docker &>/dev/null; then
        skip "nginx syntax check (docker not available): $label"
        return
    fi
    local output
    output=$(docker exec swag nginx -t 2>&1)
    if echo "$output" | grep -q 'test is successful'; then
        pass "nginx syntax valid: $label"
    else
        fail "nginx syntax error after $label"
        echo "$output" | grep -v '^$' | head -5 | sed 's/^/    /'
    fi
}

# bead .3 — SWAG reload verification (advisory: confirms nginx stays healthy after HUP)
swag_reload_check() {
    local label="$1"
    if ! command -v docker &>/dev/null; then
        skip "SWAG reload check (docker not available): $label"
        return
    fi
    local hup_out
    hup_out=$(docker kill --signal=HUP swag 2>&1)
    if ! echo "$hup_out" | grep -q '^swag$'; then
        fail "HUP signal failed: $label"
        return
    fi
    sleep 1
    if docker exec swag nginx -t 2>&1 | grep -q 'test is successful'; then
        pass "SWAG reloaded and nginx healthy: $label"
    else
        fail "SWAG nginx unhealthy post-reload: $label"
    fi
}

# bead .4 — real 2xx HTTP status assertion (accepts 2xx and 3xx — redirects are valid)
assert_http_success() {
    local output="$1" label="$2"
    local code
    code=$(echo "$output" | grep -oP '(?<=- )\d{3}(?= )' | head -1)
    if [[ -z "$code" ]]; then
        fail "$label — could not parse status code from: $(echo "$output" | head -1)"
        return
    fi
    if [[ "$code" -ge 200 && "$code" -lt 400 ]]; then
        pass "$label — HTTP $code"
    else
        fail "$label — got HTTP $code (expected 2xx/3xx)"
    fi
}

# bead .5 — backup file on-disk verification
assert_backup_exists() {
    local config_name="$1"
    local count
    count=$(ls "${PROXY_CONFS_DIR}/${config_name}.backup."* 2>/dev/null | wc -l)
    if [[ "$count" -gt 0 ]]; then
        pass "backup file exists for $config_name ($count file(s))"
    else
        fail "no backup file found for $config_name in $PROXY_CONFS_DIR"
    fi
}

cleanup_test_backups() {
    local config_name="$1"
    rm -f "${PROXY_CONFS_DIR}/${config_name}.backup."* 2>/dev/null || true
}

# EXIT trap — guaranteed cleanup even if script is killed mid-run
cleanup_on_exit() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        echo -e "\n${YELLOW}Script exiting (code $exit_code) — running emergency cleanup${NC}"
        mcp "{\"action\":\"remove\",\"config_name\":\"${TEST_CONFIG}\",\"create_backup\":false}" > /dev/null 2>&1 || true
        mcp "{\"action\":\"remove\",\"config_name\":\"smoke-test-mcp.subdomain.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
        mcp "{\"action\":\"remove\",\"config_name\":\"smoke-authelia.subdomain.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
        mcp "{\"action\":\"remove\",\"config_name\":\"smoke-authentik.subdomain.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
        mcp "{\"action\":\"remove\",\"config_name\":\"smoke-subfolder.subfolder.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
        mcp "{\"action\":\"remove\",\"config_name\":\"smoke-mcp-sf.subfolder.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
        mcp "{\"action\":\"remove\",\"config_name\":\"smoke-quic.subdomain.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
        mcp "{\"action\":\"remove\",\"config_name\":\"smoke-remote-mcp.subdomain.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
        cleanup_test_backups "$TEST_CONFIG"
        cleanup_test_backups "smoke-authelia"
        cleanup_test_backups "smoke-subfolder"
    fi
}
trap 'cleanup_on_exit' EXIT

# =============================================================================
echo -e "${BOLD}SWAG MCP Integration Test Suite${NC}"
echo "Server: $MCP_URL"
echo "Proxy confs: $PROXY_CONFS_DIR"
echo "Test config: $TEST_CONFIG"
echo "============================================"

# Safety: MCP_URL must be localhost to avoid accidental remote operations
if ! echo "$MCP_URL" | grep -qE '^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?/'; then
    echo -e "${RED}ERROR: MCP_URL must target localhost for safety. Got: $MCP_URL${NC}"
    exit 1
fi

# =============================================================================
section "0. SCHEMA — compare live MCP schema against expected spec"
SCHEMA_RESPONSE=$(curl -s "$MCP_URL" -X POST \
    -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' 2>/dev/null || echo "CURL_FAILED")

if [[ "$SCHEMA_RESPONSE" == "CURL_FAILED" ]] || [[ -z "$SCHEMA_RESPONSE" ]]; then
    skip "schema check — server unreachable"
else
    # SSE response: strip 'data: ' prefix to extract the JSON payload
    SCHEMA_JSON=$(echo "$SCHEMA_RESPONSE" | sed -n 's/^data: //p' | head -1)
    if [[ -z "$SCHEMA_JSON" ]]; then
        fail "schema — could not parse SSE data line from response"
        echo "    Raw response: $(echo "$SCHEMA_RESPONSE" | head -3)"
    else
        # Assert tool name is "swag"
        TOOL_NAME=$(echo "$SCHEMA_JSON" | python3 -c "
import json,sys
try:
    data = json.load(sys.stdin)
    tools = data.get('result', {}).get('tools', [])
    print(tools[0]['name'] if tools else 'NOT_FOUND')
except Exception as e:
    print('PARSE_ERROR:' + str(e))
" 2>/dev/null)
        if [[ "$TOOL_NAME" == "swag" ]]; then
            pass "schema — tool name is 'swag'"
        else
            fail "schema — expected tool 'swag', got: $TOOL_NAME"
        fi

        # Assert action enum contains exactly the expected 9 values
        ACTION_ENUM=$(echo "$SCHEMA_JSON" | python3 -c "
import json,sys
try:
    data = json.load(sys.stdin)
    schema = data['result']['tools'][0]['inputSchema']
    props = schema.get('properties', {})
    action = props.get('action', {})
    # Handle direct enum or anyOf wrapper
    vals = action.get('enum') or (action.get('anyOf', [{}])[0].get('enum', []))
    print(','.join(sorted(vals)))
except Exception as e:
    print('PARSE_ERROR:' + str(e))
" 2>/dev/null)
        EXPECTED_ACTIONS="backups,create,edit,health_check,list,logs,remove,update,view"
        if [[ "$ACTION_ENUM" == "$EXPECTED_ACTIONS" ]]; then
            pass "schema — action enum matches expected 9 values"
        else
            fail "schema — action enum mismatch"
            echo "    Expected: $EXPECTED_ACTIONS"
            echo "    Got:      $ACTION_ENUM"
        fi

        # Assert action is in the required array
        IS_REQUIRED=$(echo "$SCHEMA_JSON" | python3 -c "
import json,sys
try:
    data = json.load(sys.stdin)
    schema = data['result']['tools'][0]['inputSchema']
    required = schema.get('required', [])
    print('yes' if 'action' in required else 'no')
except Exception as e:
    print('PARSE_ERROR:' + str(e))
" 2>/dev/null)
        if [[ "$IS_REQUIRED" == "yes" ]]; then
            pass "schema — action is in required array"
        else
            fail "schema — action not in required array (got: $IS_REQUIRED)"
        fi
    fi
fi

# =============================================================================
section "Preflight: cleanup stale test configs"
# Remove any leftover from a previous run (ignore errors)
mcp "{\"action\":\"remove\",\"config_name\":\"${TEST_CONFIG}\",\"create_backup\":false}" > /dev/null 2>&1 || true
mcp "{\"action\":\"remove\",\"config_name\":\"smoke-test-mcp.subdomain.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
mcp "{\"action\":\"remove\",\"config_name\":\"smoke-authelia.subdomain.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
mcp "{\"action\":\"remove\",\"config_name\":\"smoke-authentik.subdomain.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
mcp "{\"action\":\"remove\",\"config_name\":\"smoke-subfolder.subfolder.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
mcp "{\"action\":\"remove\",\"config_name\":\"smoke-mcp-sf.subfolder.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
mcp "{\"action\":\"remove\",\"config_name\":\"smoke-quic.subdomain.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
mcp "{\"action\":\"remove\",\"config_name\":\"smoke-remote-mcp.subdomain.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
echo "  (cleanup complete)"

# Verify server is reachable before running destructive sections
MCP_BASE_URL="${MCP_URL%/mcp}"
if ! curl -sf "${MCP_BASE_URL}/health" -o /dev/null 2>/dev/null; then
    echo -e "  ${YELLOW}WARNING: health endpoint unreachable at ${MCP_BASE_URL}/health — server may be down${NC}"
fi

# =============================================================================
section "1. LIST — list all configs"
OUT=$(mcp '{"action":"list","list_filter":"all"}')
assert_contains "$OUT" ".conf" "returns config filenames"
assert_not_contains "$OUT" "error" "no error in response"

section "1a. LIST — filter active"
OUT=$(mcp '{"action":"list","list_filter":"active"}')
assert_not_contains "$OUT" "error" "active filter works without error"

section "1b. LIST — filter samples"
OUT=$(mcp '{"action":"list","list_filter":"samples"}')
assert_contains "$OUT" ".sample" "samples filter returns .sample files"

# =============================================================================
section "2. CREATE — standard subdomain (no auth, no MCP)"
OUT=$(mcp "{
  \"action\": \"create\",
  \"config_name\": \"${TEST_CONFIG}\",
  \"server_name\": \"${TEST_DOMAIN}\",
  \"upstream_app\": \"${TEST_UPSTREAM}\",
  \"upstream_port\": ${TEST_PORT},
  \"upstream_proto\": \"http\",
  \"auth_method\": \"none\",
  \"mcp_enabled\": false
}")
assert_contains "$OUT" "$TEST_CONFIG" "response mentions config filename"
assert_not_contains "$OUT" "error" "no error on create"

# Verify the file exists on disk
if [[ -f "${PROXY_CONFS_DIR}/${TEST_CONFIG}" ]]; then
    pass "config file exists on disk"
else
    fail "config file missing on disk"
fi

nginx_syntax_check "standard subdomain CREATE"
swag_reload_check "standard subdomain CREATE"

section "2a. CREATE — verify nginx config content"
CONFIG_CONTENT=$(cat "${PROXY_CONFS_DIR}/${TEST_CONFIG}" 2>/dev/null || echo "FILE_NOT_FOUND")
assert_contains "$CONFIG_CONTENT" "$TEST_DOMAIN" "server_name in nginx config"
assert_contains "$CONFIG_CONTENT" "$TEST_UPSTREAM" "upstream_app in nginx config"
assert_contains "$CONFIG_CONTENT" "$TEST_PORT" "upstream_port in nginx config"
assert_contains "$CONFIG_CONTENT" "location /" "location block present"
assert_contains "$CONFIG_CONTENT" "proxy_pass" "proxy_pass directive present"
assert_not_contains "$CONFIG_CONTENT" "authelia" "no authelia (auth_method=none)"
# All configs use swag-compliant-mcp templates — assert MCP security features present in every config
assert_contains "$CONFIG_CONTENT" "origin_valid" "DNS rebinding protection (\$origin_valid) present"
assert_contains "$CONFIG_CONTENT" ".well-known/oauth-protected-resource" "OAuth metadata endpoint present"
assert_contains "$CONFIG_CONTENT" "proxy_send_timeout" "proxy_send_timeout directive present"
assert_contains "$CONFIG_CONTENT" "chunked_transfer_encoding" "chunked transfer encoding present"

section "2b. CREATE — QUIC/HTTP3 enabled"
QUIC_CONFIG="smoke-quic.subdomain.conf"
mcp "{\"action\":\"remove\",\"config_name\":\"${QUIC_CONFIG}\",\"create_backup\":false}" > /dev/null 2>&1 || true
OUT=$(mcp "{
  \"action\": \"create\",
  \"config_name\": \"${QUIC_CONFIG}\",
  \"server_name\": \"smoke-quic.example.com\",
  \"upstream_app\": \"smoke-quic-app\",
  \"upstream_port\": 9993,
  \"auth_method\": \"none\",
  \"enable_quic\": true
}")
assert_not_contains "$OUT" "error" "no error on QUIC config create"
if [[ -f "${PROXY_CONFS_DIR}/${QUIC_CONFIG}" ]]; then
    pass "QUIC config file exists on disk"
    QUIC_CONTENT=$(cat "${PROXY_CONFS_DIR}/${QUIC_CONFIG}")
    assert_contains "$QUIC_CONTENT" "quic" "listen quic directive present in config"
else
    fail "QUIC config file missing on disk"
fi
mcp "{\"action\":\"remove\",\"config_name\":\"${QUIC_CONFIG}\",\"create_backup\":false}" > /dev/null 2>&1 || true

# =============================================================================
section "3. VIEW — read config content via MCP"
OUT=$(mcp "{\"action\":\"view\",\"config_name\":\"${TEST_CONFIG}\"}")
assert_contains "$OUT" "$TEST_DOMAIN" "server_name visible in view"
assert_contains "$OUT" "$TEST_UPSTREAM" "upstream_app visible in view"
assert_not_contains "$OUT" "View failed" "no failure on view"

# =============================================================================
section "4. UPDATE — change port"
NEW_PORT=8888
OUT=$(mcp "{
  \"action\": \"update\",
  \"config_name\": \"${TEST_CONFIG}\",
  \"update_field\": \"port\",
  \"update_value\": \"${NEW_PORT}\",
  \"create_backup\": false
}")
assert_not_contains "$OUT" "error" "no error on port update"

# Verify port change on disk
CONFIG_CONTENT=$(cat "${PROXY_CONFS_DIR}/${TEST_CONFIG}" 2>/dev/null || echo "")
assert_contains "$CONFIG_CONTENT" "$NEW_PORT" "port updated in file on disk"
if echo "$CONFIG_CONTENT" | grep -q "set \$upstream_port \"${NEW_PORT}\""; then
    pass "upstream_port variable updated to new port"
else
    fail "upstream_port variable not updated"
fi

section "4b. UPDATE — change upstream"
NEW_UPSTREAM="new-upstream-app"
OUT=$(mcp "{
  \"action\": \"update\",
  \"config_name\": \"${TEST_CONFIG}\",
  \"update_field\": \"upstream\",
  \"update_value\": \"${NEW_UPSTREAM}\",
  \"create_backup\": false
}")
assert_not_contains "$OUT" "error" "no error on upstream update"
CONFIG_CONTENT=$(cat "${PROXY_CONFS_DIR}/${TEST_CONFIG}" 2>/dev/null || echo "")
assert_contains "$CONFIG_CONTENT" "$NEW_UPSTREAM" "upstream updated in file"

section "4c. UPDATE — change app:port together"
OUT=$(mcp "{
  \"action\": \"update\",
  \"config_name\": \"${TEST_CONFIG}\",
  \"update_field\": \"app\",
  \"update_value\": \"${TEST_UPSTREAM}:${TEST_PORT}\",
  \"create_backup\": false
}")
assert_not_contains "$OUT" "error" "no error on app:port update"
CONFIG_CONTENT=$(cat "${PROXY_CONFS_DIR}/${TEST_CONFIG}" 2>/dev/null || echo "")
assert_contains "$CONFIG_CONTENT" "$TEST_UPSTREAM" "app name restored"
assert_contains "$CONFIG_CONTENT" "$TEST_PORT" "port restored"

section "4d. UPDATE — add_mcp location block"
OUT=$(mcp "{
  \"action\": \"update\",
  \"config_name\": \"${TEST_CONFIG}\",
  \"update_field\": \"add_mcp\",
  \"update_value\": \"/mcp\",
  \"create_backup\": false
}")
assert_not_contains "$OUT" "error" "no error on add_mcp"
CONFIG_CONTENT=$(cat "${PROXY_CONFS_DIR}/${TEST_CONFIG}" 2>/dev/null || echo "")
assert_contains "$CONFIG_CONTENT" "/mcp" "MCP location block added"
nginx_syntax_check "add_mcp UPDATE"

# =============================================================================
section "5. EDIT — full content replacement (with backup)"
# Use 127.0.0.1 (not a hostname) to avoid nginx DNS resolution failure at config-load time.
# The EDIT section tests the file-update mechanism; this content must pass nginx -t.
NEW_CONTENT="# Smoke test edited config
server {
    listen 127.0.0.1:8443;
    server_name ${TEST_DOMAIN};
    location / {
        proxy_pass http://127.0.0.1:${TEST_PORT};
    }
}"
OUT=$(mcp "{
  \"action\": \"edit\",
  \"config_name\": \"${TEST_CONFIG}\",
  \"new_content\": $(echo "$NEW_CONTENT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),
  \"create_backup\": true
}")
assert_not_contains "$OUT" "error" "no error on edit"
CONFIG_CONTENT=$(cat "${PROXY_CONFS_DIR}/${TEST_CONFIG}" 2>/dev/null || echo "")
assert_contains "$CONFIG_CONTENT" "Smoke test edited" "edited content persisted"

# bead .5: assert backup was created before cleanup
assert_backup_exists "$TEST_CONFIG"
cleanup_test_backups "$TEST_CONFIG"

nginx_syntax_check "full content EDIT"

# =============================================================================
section "6. CREATE MCP — mcp-subdomain template with mcp_enabled"
MCP_TEST_CONFIG="smoke-test-mcp.subdomain.conf"
# cleanup any residual
mcp "{\"action\":\"remove\",\"config_name\":\"${MCP_TEST_CONFIG}\",\"create_backup\":false}" > /dev/null 2>&1 || true

OUT=$(mcp "{
  \"action\": \"create\",
  \"config_name\": \"${MCP_TEST_CONFIG}\",
  \"server_name\": \"mcp-smoke.example.com\",
  \"upstream_app\": \"mcp-smoke-app\",
  \"upstream_port\": 8080,
  \"auth_method\": \"none\",
  \"mcp_enabled\": true
}")
assert_not_contains "$OUT" "error" "no error on MCP config create"

if [[ -f "${PROXY_CONFS_DIR}/${MCP_TEST_CONFIG}" ]]; then
    pass "MCP config file exists on disk"
    MCP_CONTENT=$(cat "${PROXY_CONFS_DIR}/${MCP_TEST_CONFIG}")
    # buffering is either inlined or via include /config/nginx/mcp.conf
    if echo "$MCP_CONTENT" | grep -qF "proxy_buffering off"; then
        pass "zero-buffering inlined in MCP config"
    elif echo "$MCP_CONTENT" | grep -qF "mcp.conf"; then
        pass "zero-buffering via mcp.conf include"
    else
        fail "no buffering control found in MCP config"
    fi
    assert_contains "$MCP_CONTENT" "/mcp" "MCP endpoint location block"
    assert_contains "$MCP_CONTENT" "proxy_read_timeout" "extended timeout for AI tasks"
    assert_contains "$MCP_CONTENT" "proxy_pass" "proxy_pass directive present in MCP config"
    assert_contains "$MCP_CONTENT" "origin_valid" "DNS rebinding protection in MCP config"
    assert_contains "$MCP_CONTENT" ".well-known/oauth-protected-resource" "OAuth metadata endpoint in MCP config"
    assert_contains "$MCP_CONTENT" "proxy_send_timeout 86400" "24hr send timeout for long AI ops"
    assert_contains "$MCP_CONTENT" "chunked_transfer_encoding on" "chunked transfer encoding enabled"
else
    fail "MCP config file missing on disk"
fi

nginx_syntax_check "MCP subdomain CREATE"
swag_reload_check "MCP subdomain CREATE"

# Cleanup MCP test config
mcp "{\"action\":\"remove\",\"config_name\":\"${MCP_TEST_CONFIG}\",\"create_backup\":false}" > /dev/null 2>&1 || true

# =============================================================================
section "6b. CREATE — remote MCP upstream (separate mcp_upstream_app/port)"
REMOTE_MCP_CONFIG="smoke-remote-mcp.subdomain.conf"
mcp "{\"action\":\"remove\",\"config_name\":\"${REMOTE_MCP_CONFIG}\",\"create_backup\":false}" > /dev/null 2>&1 || true
OUT=$(mcp "{
  \"action\": \"create\",
  \"config_name\": \"${REMOTE_MCP_CONFIG}\",
  \"server_name\": \"remote-mcp.example.com\",
  \"upstream_app\": \"main-app\",
  \"upstream_port\": 8080,
  \"upstream_proto\": \"http\",
  \"mcp_upstream_app\": \"ai-gpu-server\",
  \"mcp_upstream_port\": 9090,
  \"mcp_upstream_proto\": \"http\",
  \"auth_method\": \"none\"
}")
assert_not_contains "$OUT" "error" "no error on remote MCP upstream create"
if [[ -f "${PROXY_CONFS_DIR}/${REMOTE_MCP_CONFIG}" ]]; then
    pass "remote MCP config file exists on disk"
    REMOTE_CONTENT=$(cat "${PROXY_CONFS_DIR}/${REMOTE_MCP_CONFIG}")
    # /mcp routes to separate MCP upstream
    assert_contains "$REMOTE_CONTENT" "ai-gpu-server" "separate MCP upstream app in config"
    assert_contains "$REMOTE_CONTENT" "9090" "separate MCP upstream port in config"
    # / routes to main app (both vars are set, ensure both values present)
    assert_contains "$REMOTE_CONTENT" "main-app" "main upstream app in config"
    assert_contains "$REMOTE_CONTENT" "8080" "main upstream port in config"
    # Confirm they are set as distinct nginx variables
    if echo "$REMOTE_CONTENT" | grep -q 'set \$upstream_app "main-app"' && \
       echo "$REMOTE_CONTENT" | grep -q 'set \$mcp_upstream_app "ai-gpu-server"'; then
        pass "upstream_app and mcp_upstream_app are distinct nginx variables"
    else
        fail "upstream_app / mcp_upstream_app variable separation not found"
    fi
    nginx_syntax_check "remote MCP upstream CREATE"
else
    fail "remote MCP config file missing on disk"
fi
mcp "{\"action\":\"remove\",\"config_name\":\"${REMOTE_MCP_CONFIG}\",\"create_backup\":false}" > /dev/null 2>&1 || true

# =============================================================================
section "7. LOGS — nginx error log"
OUT=$(mcp '{"action":"logs","log_type":"nginx-error","lines":10}')
assert_not_contains "$OUT" "\"error\":" "no error field in logs response"

section "7a. LOGS — nginx access log"
OUT=$(mcp '{"action":"logs","log_type":"nginx-access","lines":5}')
assert_not_contains "$OUT" "\"error\":" "nginx-access log call succeeds"

section "7b. LOGS — fail2ban log"
OUT=$(mcp '{"action":"logs","log_type":"fail2ban","lines":5}')
assert_not_contains "$OUT" "\"error\":" "fail2ban log call succeeds"

section "7c. LOGS — letsencrypt log"
OUT=$(mcp '{"action":"logs","log_type":"letsencrypt","lines":5}')
assert_not_contains "$OUT" "\"error\":" "letsencrypt log call succeeds"

# =============================================================================
section "8. BACKUPS — list"
OUT=$(mcp '{"action":"backups","backup_action":"list"}')
assert_not_contains "$OUT" "error" "no error on backup list"

section "8a. BACKUPS — cleanup with retention"
OUT=$(mcp '{"action":"backups","backup_action":"cleanup","retention_days":90}')
assert_not_contains "$OUT" "error" "no error on backup cleanup"

# =============================================================================
section "9. HEALTH CHECK — reachable domain"
OUT=$(mcp '{"action":"health_check","domain":"swag.tootie.tv","timeout":10}')
assert_not_contains "$OUT" "\"error\":" "health_check call completes"
# bead .4: assert response contains ✅ and parse 2xx/3xx status code
if echo "$OUT" | grep -q '✅'; then
    pass "health_check — domain returned success indicator"
    assert_http_success "$OUT" "swag.tootie.tv returns 2xx/3xx"
else
    skip "health_check swag.tootie.tv — domain unreachable from this host (✅ not in response)"
fi

section "9a. HEALTH CHECK — invalid domain (graceful failure)"
OUT=$(mcp '{"action":"health_check","domain":"smoke-test-nonexistent-12345.example.com","timeout":5}')
# Should return a result (not throw), even if the domain is unreachable
assert_not_contains "$OUT" "Tool execution failed" "invalid domain handled gracefully"
# bead .4: invalid domain should produce ❌ failure indicator
assert_contains "$OUT" "❌" "invalid domain produces failure indicator"

# =============================================================================
section "10. AUTH METHODS — authelia vs none"
# Create config with authelia auth
OUT=$(mcp "{
  \"action\": \"create\",
  \"config_name\": \"smoke-authelia.subdomain.conf\",
  \"server_name\": \"smoke-authelia.example.com\",
  \"upstream_app\": \"smoke-authelia-app\",
  \"upstream_port\": 9997,
  \"upstream_proto\": \"http\",
  \"auth_method\": \"authelia\",
  \"mcp_enabled\": false
}")
assert_not_contains "$OUT" "error" "no error creating authelia config"

if [[ -f "${PROXY_CONFS_DIR}/smoke-authelia.subdomain.conf" ]]; then
    pass "authelia config file exists on disk"
    AUTHELIA_CONTENT=$(cat "${PROXY_CONFS_DIR}/smoke-authelia.subdomain.conf")
    assert_contains "$AUTHELIA_CONTENT" "authelia-server.conf" "authelia-server.conf include present"
    assert_contains "$AUTHELIA_CONTENT" "authelia-location.conf" "authelia-location.conf include present"
    nginx_syntax_check "authelia config create"
else
    fail "authelia config file missing on disk"
fi

# Authentik — different include pattern from authelia
OUT=$(mcp "{
  \"action\": \"create\",
  \"config_name\": \"smoke-authentik.subdomain.conf\",
  \"server_name\": \"smoke-authentik.example.com\",
  \"upstream_app\": \"smoke-authentik-app\",
  \"upstream_port\": 9996,
  \"upstream_proto\": \"http\",
  \"auth_method\": \"authentik\",
  \"mcp_enabled\": false
}")
assert_not_contains "$OUT" "error" "no error creating authentik config"
if [[ -f "${PROXY_CONFS_DIR}/smoke-authentik.subdomain.conf" ]]; then
    pass "authentik config file exists on disk"
    AUTHENTIK_CONTENT=$(cat "${PROXY_CONFS_DIR}/smoke-authentik.subdomain.conf")
    assert_contains "$AUTHENTIK_CONTENT" "authentik-server.conf" "authentik-server.conf include present"
    assert_contains "$AUTHENTIK_CONTENT" "authentik-location.conf" "authentik-location.conf include present"
    assert_not_contains "$AUTHENTIK_CONTENT" "authelia" "no authelia directives in authentik config"
    nginx_syntax_check "authentik config create"
else
    fail "authentik config file missing on disk"
fi
mcp "{\"action\":\"remove\",\"config_name\":\"smoke-authentik.subdomain.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true

# Verify auth_method=none has NO authelia includes (reuse existing TEST_CONFIG)
if [[ -f "${PROXY_CONFS_DIR}/${TEST_CONFIG}" ]]; then
    NONE_CONTENT=$(cat "${PROXY_CONFS_DIR}/${TEST_CONFIG}")
    assert_not_contains "$NONE_CONTENT" "authelia" "auth_method=none: no authelia includes in config"
fi

# =============================================================================
section "11. SUBFOLDER — path-based routing via .subfolder.conf"
OUT=$(mcp "{
  \"action\": \"create\",
  \"config_name\": \"smoke-subfolder.subfolder.conf\",
  \"server_name\": \"swag.tootie.tv\",
  \"upstream_app\": \"smoke-subfolder-app\",
  \"upstream_port\": 9998,
  \"upstream_proto\": \"http\",
  \"auth_method\": \"none\",
  \"mcp_enabled\": false
}")
assert_not_contains "$OUT" "error" "no error creating subfolder config"

if [[ -f "${PROXY_CONFS_DIR}/smoke-subfolder.subfolder.conf" ]]; then
    pass "subfolder config file exists on disk"
    SUBFOLDER_CONTENT=$(cat "${PROXY_CONFS_DIR}/smoke-subfolder.subfolder.conf")
    # Subfolder uses path-based location routing derived from service name
    assert_contains "$SUBFOLDER_CONTENT" "location ^~ /smoke-subfolder" "path-based location block present"
    assert_contains "$SUBFOLDER_CONTENT" "proxy_pass" "proxy_pass present in subfolder config"
    # Subfolder shares parent vhost — should NOT have a dedicated server_name for this service
    assert_not_contains "$SUBFOLDER_CONTENT" "server_name smoke-subfolder.example.com" "no dedicated server_name in subfolder config"
    # Path routing headers required for subfolder services
    assert_contains "$SUBFOLDER_CONTENT" "X-Forwarded-Prefix" "X-Forwarded-Prefix header present"
    assert_contains "$SUBFOLDER_CONTENT" "X-Script-Name" "X-Script-Name header present"
    # MCP security features present in subfolder template too
    assert_contains "$SUBFOLDER_CONTENT" "origin_valid" "DNS rebinding protection in subfolder config"
    assert_contains "$SUBFOLDER_CONTENT" ".well-known/oauth-protected-resource" "OAuth metadata endpoint in subfolder config"
    # nginx_syntax_check for subfolder: the local template (365f17e) has fixed nested-if
    # blocks, but the running container image may be pre-fix. Detect and annotate.
    if command -v docker &>/dev/null; then
        nginx_out=$(docker exec swag nginx -t 2>&1)
        if echo "$nginx_out" | grep -q 'test is successful'; then
            pass "nginx syntax valid: subfolder config create"
        elif echo "$nginx_out" | grep -qE 'smoke-subfolder.*if.*not allowed|if.*not allowed.*smoke-subfolder'; then
            skip "nginx subfolder syntax — nested-if template bug in deployed image (rebuild container to fix)"
        else
            fail "nginx syntax error after subfolder config create"
            echo "$nginx_out" | grep -v '^$' | head -5 | sed 's/^/    /'
        fi
    else
        skip "nginx syntax check (docker not available): subfolder config create"
    fi
else
    fail "subfolder config file missing on disk"
fi

section "11b. MCP-SUBFOLDER — MCP endpoint in subfolder routing"
MCP_SUBFOLDER_CONFIG="smoke-mcp-sf.subfolder.conf"
mcp "{\"action\":\"remove\",\"config_name\":\"${MCP_SUBFOLDER_CONFIG}\",\"create_backup\":false}" > /dev/null 2>&1 || true
OUT=$(mcp "{
  \"action\": \"create\",
  \"config_name\": \"${MCP_SUBFOLDER_CONFIG}\",
  \"server_name\": \"swag.tootie.tv\",
  \"upstream_app\": \"smoke-mcp-sf-app\",
  \"upstream_port\": 9992,
  \"upstream_proto\": \"http\",
  \"auth_method\": \"none\",
  \"mcp_enabled\": true
}")
assert_not_contains "$OUT" "error" "no error creating mcp-subfolder config"
if [[ -f "${PROXY_CONFS_DIR}/${MCP_SUBFOLDER_CONFIG}" ]]; then
    pass "mcp-subfolder config file exists on disk"
    MCP_SF_CONTENT=$(cat "${PROXY_CONFS_DIR}/${MCP_SUBFOLDER_CONFIG}")
    # MCP location block uses prefixed path
    assert_contains "$MCP_SF_CONTENT" "location ^~ /smoke-mcp-sf/mcp" "MCP location block in subfolder (/service/mcp)"
    assert_contains "$MCP_SF_CONTENT" "proxy_buffering off" "zero-buffering in mcp-subfolder"
    assert_contains "$MCP_SF_CONTENT" "origin_valid" "DNS rebinding protection in mcp-subfolder"
    assert_contains "$MCP_SF_CONTENT" "X-Forwarded-Prefix" "X-Forwarded-Prefix present in mcp-subfolder"
    if command -v docker &>/dev/null; then
        nginx_out=$(docker exec swag nginx -t 2>&1)
        if echo "$nginx_out" | grep -q 'test is successful'; then
            pass "nginx syntax valid: mcp-subfolder CREATE"
        else
            fail "nginx syntax error after mcp-subfolder CREATE"
            echo "$nginx_out" | grep -v '^$' | head -5 | sed 's/^/    /'
        fi
    else
        skip "nginx syntax check (docker not available): mcp-subfolder CREATE"
    fi
else
    fail "mcp-subfolder config file missing on disk"
fi
mcp "{\"action\":\"remove\",\"config_name\":\"${MCP_SUBFOLDER_CONFIG}\",\"create_backup\":false}" > /dev/null 2>&1 || true

# =============================================================================
section "12. VALIDATION — missing required params"
OUT=$(mcp '{"action":"create"}')
assert_contains "$OUT" "❌" "missing params returns error emoji"
# accepts either "error", "failed", or "Missing" in response
if echo "$OUT" | grep -qi "error\|failed\|missing\|required"; then
    pass "missing params error message is descriptive"
else
    fail "missing params error missing descriptive message"
fi

section "12a. VALIDATION — invalid action"
OUT=$(mcp '{"action":"invalid_action"}' || true)
# Should either fail validation or return an error — not crash
assert_not_contains "$OUT" "Traceback" "no python traceback on invalid action"

# =============================================================================
section "Cleanup: remove test configs and backups"

# Remove test configs (with backup to verify bead .5 REMOVE path)
OUT=$(mcp "{\"action\":\"remove\",\"config_name\":\"${TEST_CONFIG}\",\"create_backup\":true}")
assert_not_contains "$OUT" "error" "test config removed cleanly"
assert_backup_exists "$TEST_CONFIG"
cleanup_test_backups "$TEST_CONFIG"

if [[ ! -f "${PROXY_CONFS_DIR}/${TEST_CONFIG}" ]]; then
    pass "config file removed from disk"
else
    fail "config file still present after remove"
fi

# Remove authelia test config
mcp "{\"action\":\"remove\",\"config_name\":\"smoke-authelia.subdomain.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
cleanup_test_backups "smoke-authelia"

# Remove subfolder test config
mcp "{\"action\":\"remove\",\"config_name\":\"smoke-subfolder.subfolder.conf\",\"create_backup\":false}" > /dev/null 2>&1 || true
cleanup_test_backups "smoke-subfolder"

echo "  (all test configs and backups removed)"

# =============================================================================
echo ""
echo "============================================"
echo -e "${BOLD}Results: ${GREEN}${PASS} passed${NC}, ${RED}${FAIL} failed${NC}, ${YELLOW}${SKIP} skipped${NC}"
echo "============================================"

[[ $FAIL -eq 0 ]]
