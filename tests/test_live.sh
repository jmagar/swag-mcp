#!/usr/bin/env bash
set -euo pipefail
TOKEN="${SWAG_MCP_TOKEN:?SWAG_MCP_TOKEN must be set}"
BASE_URL="${SWAG_MCP_URL:-http://localhost:8082}"

echo "Testing unauthenticated rejection..."
status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/mcp")
[ "$status" = "401" ] || { echo "FAIL: expected 401, got $status"; exit 1; }

echo "Testing bad token rejection..."
status=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer bad-token" "$BASE_URL/mcp")
[ "$status" = "401" ] || { echo "FAIL: expected 401 for bad token, got $status"; exit 1; }

echo "Testing health endpoint..."
timeout 30 curl -sf -H "Authorization: Bearer $TOKEN" "$BASE_URL/health" | jq .

echo "All live tests passed."
