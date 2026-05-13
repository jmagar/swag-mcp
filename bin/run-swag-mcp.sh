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
  DATA_ROOT="${REPO_ROOT}/.cache/claude-plugin-data"
else
  DATA_ROOT="${CLAUDE_PLUGIN_DATA}"
fi

mkdir -p "${DATA_ROOT}"
export UV_PROJECT_ENVIRONMENT="${DATA_ROOT}/.venv"

exec uv run --project "${REPO_ROOT}" python -m swag_mcp "$@"
