#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${CLAUDE_PLUGIN_ROOT}/.env"
BACKUP_DIR="${CLAUDE_PLUGIN_ROOT}/backups"
mkdir -p "$BACKUP_DIR"

declare -A MANAGED=(
  [SWAG_MCP_PROXY_CONFS_PATH]="${CLAUDE_PLUGIN_OPTION_SWAG_PROXY_CONFS_PATH:-}"
  [SWAG_MCP_PROXY_CONFS_URI]="${CLAUDE_PLUGIN_OPTION_SWAG_PROXY_CONFS_URI:-}"
  [SWAG_MCP_URL]="${CLAUDE_PLUGIN_OPTION_SWAG_MCP_URL:-}"
)

touch "$ENV_FILE"

if [ -s "$ENV_FILE" ]; then
  cp "$ENV_FILE" "${BACKUP_DIR}/.env.bak.$(date +%s)"
fi

(
  flock -x 200

  for key in "${!MANAGED[@]}"; do
    value="${MANAGED[$key]}"
    [ -z "$value" ] && continue
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
      awk -v k="$key" -v v="$value" \
        'BEGIN{FS="="; OFS="="} $1==k {$2=v; print; next} {print}' \
        "$ENV_FILE" > "${ENV_FILE}.tmp" && mv "${ENV_FILE}.tmp" "$ENV_FILE"
    else
      echo "${key}=${value}" >> "$ENV_FILE"
    fi
  done

  chmod 600 "$ENV_FILE"

  mapfile -t baks < <(ls -t "${BACKUP_DIR}"/.env.bak.* 2>/dev/null)
  for bak in "${baks[@]}"; do
    chmod 600 "$bak"
  done
  for bak in "${baks[@]:3}"; do
    rm -f "$bak"
  done

) 200>/tmp/swag-sync-env.lock
