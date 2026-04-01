#!/usr/bin/env bash
set -euo pipefail

# ensure-ignore-files.sh — ensures .gitignore and .dockerignore have required patterns
#
# Usage:
#   ensure-ignore-files.sh              # auto-fix mode (SessionStart hook)
#   ensure-ignore-files.sh --check .    # report-only mode (pre-commit / CI)

CHECK_MODE=false
if [[ "${1:-}" == "--check" ]]; then
  CHECK_MODE=true
  shift
fi

ROOT="${1:-${CLAUDE_PLUGIN_ROOT:-.}}"
GITIGNORE="${ROOT}/.gitignore"
DOCKERIGNORE="${ROOT}/.dockerignore"

GITIGNORE_PATTERNS=(
  ".env"
  ".env.*"
  "!.env.example"
  "backups/*"
  "!backups/.gitkeep"
  "logs/*"
  "!logs/.gitkeep"
  "*.log"
  ".claude/settings.local.json"
  ".claude/worktrees/"
  ".omc/"
  ".lavra/"
  ".beads/"
  ".serena/"
  ".worktrees"
  ".full-review/"
  ".full-review-archive-*"
  ".vscode/"
  ".cursor/"
  ".windsurf/"
  ".1code/"
  ".cache/"
  "docs/plans/"
  "docs/sessions/"
  "docs/reports/"
  "docs/research/"
  "docs/superpowers/"
)

DOCKERIGNORE_PATTERNS=(
  ".git"
  ".github"
  ".env"
  ".env.*"
  "!.env.example"
  ".claude"
  ".claude-plugin"
  ".codex-plugin"
  ".omc"
  ".lavra"
  ".beads"
  ".serena"
  ".worktrees"
  ".full-review"
  ".full-review-archive-*"
  ".vscode"
  ".cursor"
  ".windsurf"
  ".1code"
  "docs"
  "tests"
  "scripts"
  "*.md"
  "!README.md"
  "logs"
  "backups"
  "*.log"
  ".cache"
)

failures=0

check_or_fix() {
  local file="$1"
  shift
  local patterns=("$@")

  # In check mode, do not create or modify files — report missing patterns only
  if [ "$CHECK_MODE" != true ]; then
    touch "$file"
  fi

  for pattern in "${patterns[@]}"; do
    if ! grep -qxF "$pattern" "$file" 2>/dev/null; then
      if [ "$CHECK_MODE" = true ]; then
        echo "MISSING in ${file}: ${pattern}"
        failures=$((failures + 1))
      else
        echo "$pattern" >> "$file"
      fi
    fi
  done
}

check_or_fix "$GITIGNORE" "${GITIGNORE_PATTERNS[@]}"
check_or_fix "$DOCKERIGNORE" "${DOCKERIGNORE_PATTERNS[@]}"

if [ "$CHECK_MODE" = true ] && [ "$failures" -gt 0 ]; then
  echo "ensure-ignore-files: $failures pattern(s) missing — run without --check to auto-fix"
  exit 1
fi
