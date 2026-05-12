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
| FastMCP | >=3.2.4,<4.0.0 | MCP server framework with streamable-http transport |
| Pydantic | >=2.11.7,<3.0.0 | Data validation, request/response models |
| Pydantic Settings | >=2.7.0,<3.0.0 | Environment-based configuration with `SWAG_MCP_` prefix |
| Jinja2 | >=3.1.6,<4.0.0 | Sandboxed template rendering for nginx configs |

## Async I/O

| Package | Version | Purpose |
| --- | --- | --- |
| aiofiles | >=24.1.0,<25.0.0 | Async file read/write for local filesystem |
| aiohttp | >=3.9.0,<4.0.0 | Async HTTP client for health checks |
| asyncssh | >=2.14.0,<3.0.0 | Async SSH/SFTP for remote filesystem access |

## Infrastructure

| Package | Version | Purpose |
| --- | --- | --- |
| docker | >=7.1.0,<8.0.0 | Docker API client for container log access |
| pyyaml | >=6.0.0,<7.0.0 | YAML parsing |
| regex | >=2024.5.15,<2027.0.0 | Advanced regex for input validation |

Direct dependency ranges use a reviewed lower bound and an upper bound. `uv.lock`
pins transitive versions for reproducible installs.

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
| Base image | `python:3.11-slim` by default; override `PYTHON_BASE_IMAGE` with a reviewed digest for production builds |
| Builder | Multi-stage (builder + runtime) |
| Package installer | uv (copied from `ghcr.io/astral-sh/uv:0.10.10`; override `UV_IMAGE` with a reviewed digest for production builds) |
| Process manager | Direct `python -m swag_mcp` (no supervisor) |
| Health check | Python readiness probe against `http://127.0.0.1:8000/health` plus writable log/proxy path checks |
| User | Entrypoint may start as root for bind-mount ownership, then runs the app as non-root `swagmcp` (UID 1000 by default) |

## Upstream service

**SWAG (Secure Web Application Gateway)** -- LinuxServer.io's nginx-based reverse proxy with Let's Encrypt SSL, Authelia/Authentik SSO, and fail2ban protection.

SWAG stores proxy configurations as `.conf` files in the `proxy-confs` directory. swag-mcp manages these files directly via the filesystem (local or SSH).
