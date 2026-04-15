# Technology Choices -- swag-mcp

Technology stack reference for the swag-mcp MCP server.

## Language

**Python 3.11+**

Chosen for:
- FastMCP framework (Python-native)
- Rich async ecosystem (aiofiles, aiohttp, asyncssh)
- Pydantic for validation and settings
- Jinja2 for template rendering

## Core framework

| Package | Version | Purpose |
| --- | --- | --- |
| FastMCP | >=2.11.3 | MCP server framework with streamable-http transport |
| Pydantic | >=2.11.7 | Data validation, request/response models |
| Pydantic Settings | >=2.7.0 | Environment-based configuration with `SWAG_MCP_` prefix |
| Jinja2 | >=3.1.6 | Sandboxed template rendering for nginx configs |

## Async I/O

| Package | Version | Purpose |
| --- | --- | --- |
| aiofiles | >=24.1.0 | Async file read/write for local filesystem |
| aiohttp | >=3.9.0 | Async HTTP client for health checks |
| asyncssh | >=2.14.0 | Async SSH/SFTP for remote filesystem access |

## Infrastructure

| Package | Version | Purpose |
| --- | --- | --- |
| docker | >=7.1.0 | Docker API client for container log access |
| pyyaml | >=6.0.0 | YAML parsing |
| regex | >=2024.5.15 | Advanced regex for input validation |

## Development tools

| Tool | Purpose |
| --- | --- |
| uv | Package management, virtual environments |
| ruff | Linting and formatting (replaces flake8, isort, black) |
| ty | Type checking (replaces mypy) |
| pytest | Test framework with async support |
| hypothesis | Property-based testing |
| pytest-benchmark | Performance benchmarking |
| bandit | Security linting |
| pip-audit | Dependency vulnerability scanning |
| lefthook | Git hook management |
| just | Task runner (Justfile) |

## Container stack

| Component | Value |
| --- | --- |
| Base image | `python:3.11-slim` |
| Builder | Multi-stage (builder + runtime) |
| Package installer | uv (copied from `ghcr.io/astral-sh/uv:0.10.10`) |
| Process manager | Direct `python -m swag_mcp` (no supervisor) |
| Health check | `curl http://localhost:8000/health` |
| User | Non-root `swagmcp` (UID 1000) |

## Upstream service

**SWAG (Secure Web Application Gateway)** -- LinuxServer.io's nginx-based reverse proxy with Let's Encrypt SSL, Authelia/Authentik SSO, and fail2ban protection.

SWAG stores proxy configurations as `.conf` files in the `proxy-confs` directory. swag-mcp manages these files directly via the filesystem (local or SSH).
