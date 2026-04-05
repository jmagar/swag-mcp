# Memory Files -- swag-mcp

Claude Code memory system for persistent knowledge across sessions.

## What is memory

Claude Code stores per-project knowledge in `CLAUDE.md` files. These files persist between sessions and provide context about the project's architecture, conventions, and current state.

## Memory file locations

| File | Scope | Purpose |
| --- | --- | --- |
| `CLAUDE.md` (repo root) | Project-wide | Architecture overview, dev commands, tool reference, environment variables |
| `swag_mcp/CLAUDE.md` | Package | Core package structure and module roles |
| `swag_mcp/core/CLAUDE.md` | Module | Configuration and constants reference |
| `swag_mcp/middleware/CLAUDE.md` | Module | Middleware stack ordering and configuration |
| `swag_mcp/models/CLAUDE.md` | Module | Data models and enum definitions |
| `swag_mcp/services/CLAUDE.md` | Module | Service layer architecture (9 sub-managers) |
| `swag_mcp/tools/CLAUDE.md` | Module | Tool registration and handler patterns |
| `swag_mcp/utils/CLAUDE.md` | Module | Utility function reference |
| `templates/CLAUDE.md` | Module | Template system and Jinja2 patterns |

## Conventions

- Root `CLAUDE.md` is the primary entry point -- read first
- Sub-module `CLAUDE.md` files reference root with `@CLAUDE.md`
- `AGENTS.md` and `GEMINI.md` are symlinks to `CLAUDE.md` for cross-platform compatibility
- Keep memory files concise -- link to detailed docs rather than duplicating
- Update memory files when architecture changes
