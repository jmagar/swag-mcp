#!/usr/bin/env bash
set -euo pipefail

is_placeholder() {
  local value="${1:-}"
  [[ -z "${value}" || "${value}" == *'${'* || "${value}" == *'$CLAUDE_PLUGIN_'* ]]
}

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if is_placeholder "${CLAUDE_PLUGIN_ROOT:-}"; then
  REPO_ROOT="${SCRIPT_ROOT}"
else
  REPO_ROOT="${CLAUDE_PLUGIN_ROOT}"
fi

if is_placeholder "${CLAUDE_PLUGIN_DATA:-}"; then
  export SWAG_MCP_HOME="${REPO_ROOT}/.cache/claude-plugin-data"
else
  export SWAG_MCP_HOME="${CLAUDE_PLUGIN_DATA}"
fi

for option_name in \
  SWAG_MCP_PROXY_CONFS_PATH \
  SWAG_MCP_PROXY_CONFS_URI \
  SWAG_MCP_SWAG_LOG_BASE_PATH \
  SWAG_MCP_LOG_DIRECTORY \
  SWAG_MCP_TOKEN \
  SWAG_MCP_URL \
  SWAG_MCP_NO_AUTH \
  FASTMCP_SERVER_AUTH \
  FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID \
  FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET \
  FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL \
  FASTMCP_SERVER_AUTH_RESOURCE_BASE_URL \
  FASTMCP_SERVER_AUTH_GOOGLE_REQUIRED_SCOPES \
  FASTMCP_SERVER_AUTH_GOOGLE_REDIRECT_PATH \
  SWAG_MCP_HOST \
  SWAG_MCP_BIND_ADDRESS \
  SWAG_MCP_PORT \
  SWAG_MCP_DEFAULT_WEB_AUTH_METHOD \
  SWAG_MCP_DEFAULT_QUIC_ENABLED \
  SWAG_MCP_BACKUP_RETENTION_DAYS \
  SWAG_MCP_LOG_LEVEL \
  SWAG_MCP_RATE_LIMIT_ENABLED \
  SWAG_MCP_RATE_LIMIT_RPS \
  SWAG_MCP_RATE_LIMIT_BURST \
  SWAG_MCP_HEALTH_CHECK_INSECURE; do
  plugin_var="CLAUDE_PLUGIN_OPTION_${option_name}"
  if [[ -n "${!plugin_var:-}" ]]; then
    export "${option_name}=${!plugin_var}"
  fi
done

uv run --project "${REPO_ROOT}" python -m swag_mcp setup repair --home "${SWAG_MCP_HOME}"
