#!/usr/bin/env bash
set -euo pipefail

GITIGNORE="${CLAUDE_PLUGIN_ROOT}/.gitignore"

REQUIRED=(
  ".env"
  ".env.*"
  "!.env.example"
  "backups/*"
  "!backups/.gitkeep"
  "logs/*"
  "!logs/.gitkeep"
)

# --check mode: exit non-zero if any pattern is missing, without modifying the file
if [[ "${1:-}" == "--check" ]]; then
  missing=0
  for pattern in "${REQUIRED[@]}"; do
    if ! grep -qxF "$pattern" "$GITIGNORE" 2>/dev/null; then
      echo "MISSING from .gitignore: $pattern" >&2
      missing=1
    fi
  done
  exit $missing
fi

touch "$GITIGNORE"

for pattern in "${REQUIRED[@]}"; do
  if ! grep -qxF "$pattern" "$GITIGNORE" 2>/dev/null; then
    echo "$pattern" >> "$GITIGNORE"
  fi
done
