# Documentation Index -- swag-mcp

This directory contains comprehensive documentation for the swag-mcp plugin, organized by concern.

## Directory index

### Root-level docs (this directory)

| File | Purpose |
| --- | --- |
| `README.md` | Plugin overview, tools, install, config, examples |
| `SETUP.md` | Step-by-step setup guide for local, Docker, and plugin install |
| `CONFIG.md` | Complete environment variable reference |
| `CHECKLIST.md` | Pre-release quality checklist |
| `GUARDRAILS.md` | Security guardrails and safety patterns |
| `INVENTORY.md` | Component inventory: tools, resources, env vars, deps |
| `CLAUDE.md` | This file -- index and navigation |

### Subdirectories

| Directory | Scope |
| --- | --- |
| `mcp/` | MCP server docs: auth, transport, tools, resources, testing, deployment |
| `plugin/` | Plugin system docs: manifests, hooks, skills, commands, channels |
| `repo/` | Repository docs: git conventions, scripts, memory, rules |
| `stack/` | Technology stack docs: prerequisites, architecture, dependencies |
| `upstream/` | Upstream service docs: SWAG integration patterns |

### Preserved docs (pre-existing)

| File | Purpose |
| --- | --- |
| `TEMPLATES.md` | Jinja2 template system reference (MCP/OAuth/nginx) |
| `mcp-remote-server-analysis.md` | Analysis of remote MCP server patterns |
| `swag-test-commands.md` | Test command examples (600+) |
| `template-enhancement-proposal.md` | Template system improvement proposals |
| `token-efficient-formatting.md` | Token-efficient output formatting patterns |
| `plans/` | Historical planning documents |
| `sessions/` | Session notes |

## Navigation

- New to swag-mcp? Start with [SETUP](SETUP.md)
- Need environment variables? See [CONFIG](CONFIG.md)
- Looking for tool parameters? See [mcp/TOOLS](mcp/TOOLS.md)
- Deploying to production? See [mcp/DEPLOY](mcp/DEPLOY.md)
- Understanding the architecture? See [stack/ARCH](stack/ARCH.md)
- How SWAG proxy configs work? See [upstream/CLAUDE](upstream/CLAUDE.md)
