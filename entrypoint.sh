#!/bin/bash
set -euo pipefail
: "${SWAG_MCP_TOKEN:?SWAG_MCP_TOKEN must be set}"
exec uv run python -m swag_mcp "$@"
