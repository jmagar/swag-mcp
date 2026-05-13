#!/usr/bin/env bash
# Validate Claude Code marketplace and plugin structure

set -uo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Counters
CHECKS=0
PASSED=0
FAILED=0

check() {
    local test_name="$1"
    local test_cmd="$2"

    CHECKS=$((CHECKS + 1))
    echo -n "Checking: $test_name... "

    if eval "$test_cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
        PASSED=$((PASSED + 1))
        return 0
    else
        echo -e "${RED}✗${NC}"
        FAILED=$((FAILED + 1))
        return 1
    fi
}

echo "=== Validating Claude Code Marketplace Structure ==="
echo ""

# Check marketplace manifest
check "Marketplace manifest exists" "test -f .claude-plugin/marketplace.json"
check "Marketplace manifest is valid JSON" "jq empty .claude-plugin/marketplace.json"
check "Marketplace has name" "jq -e '.name' .claude-plugin/marketplace.json"
check "Marketplace has plugins array" "jq -e '.plugins | type == \"array\"' .claude-plugin/marketplace.json"

# Check plugin manifest
check "Plugin manifest exists" "test -f .claude-plugin/plugin.json"
check "Plugin manifest is valid JSON" "jq empty .claude-plugin/plugin.json"
check "Plugin has name" "jq -e '.name' .claude-plugin/plugin.json"
check "Plugin has version" "jq -e '.version' .claude-plugin/plugin.json"

# Check plugin structure
check "Plugin has SKILL.md" "test -f plugins/swag-mcp/skills/swag/SKILL.md"
check "Plugin has hooks" "test -f plugins/swag-mcp/hooks/hooks.json"
check "Plugin has MCP config" "test -f plugins/swag-mcp/.mcp.json"
check "Plugin has app config" "test -f plugins/swag-mcp/.app.json"

# Validate plugin is listed in marketplace
check "Plugin listed in marketplace" "jq -e '.plugins[] | select(.name == \"swag-mcp\")' .claude-plugin/marketplace.json"

# Check marketplace metadata
check "Marketplace has repository" "jq -e '.repository' .claude-plugin/marketplace.json"
check "Marketplace has owner" "jq -e '.owner' .claude-plugin/marketplace.json"

# Verify source path
PLUGIN_SOURCE=$(jq -r '.plugins[]? | select(.name == "swag-mcp") | .source // empty' .claude-plugin/marketplace.json 2>/dev/null || true)
if [ -n "$PLUGIN_SOURCE" ]; then
    check "Plugin source path is valid" "test -d \"$PLUGIN_SOURCE\""
else
    CHECKS=$((CHECKS + 1))
    FAILED=$((FAILED + 1))
    echo -e "Checking: Plugin source path is valid... ${RED}✗${NC} (plugin not found in marketplace)"
fi

# Check version sync between pyproject.toml and plugin.json
echo "Checking version sync..."
TOML_VER=$(grep -m1 '^version = ' pyproject.toml | sed 's/version = "//;s/"//')
PLUGIN_VER=$(python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "ERROR_READING")
if [ "$TOML_VER" != "$PLUGIN_VER" ]; then
    echo -e "${RED}FAIL: Version mismatch — pyproject.toml=$TOML_VER, plugin.json=$PLUGIN_VER${NC}"
    CHECKS=$((CHECKS + 1))
    FAILED=$((FAILED + 1))
else
    echo -e "${GREEN}PASS: Versions in sync ($TOML_VER)${NC}"
    CHECKS=$((CHECKS + 1))
    PASSED=$((PASSED + 1))
fi

echo ""
echo "=== Results ==="
echo -e "Total checks: $CHECKS"
echo -e "${GREEN}Passed: $PASSED${NC}"
if [ $FAILED -gt 0 ]; then
    echo -e "${RED}Failed: $FAILED${NC}"
    exit 1
else
    echo -e "${GREEN}All checks passed!${NC}"
    echo ""
    echo "Marketplace is ready for distribution at:"
    echo "  $(jq -r '.repository' .claude-plugin/marketplace.json)"
fi
