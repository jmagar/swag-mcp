# SWAG MCP - Claude Memory Reference

See @README.md for complete project documentation and @.env.example for configuration options.

## Project Overview

**SWAG MCP** is a Model Context Protocol (MCP) server that provides AI assistants with tools to manage SWAG (Secure Web Application Gateway) reverse proxy configurations through natural language commands.

### Core Architecture

- **MCP Server Framework**: FastMCP 2.11.3+ with streamable-http transport
- **Unified Tool Design**: Single `swag` tool with 10 distinct actions instead of separate tools
- **Natural Language Interface**: AI assistants translate commands to structured parameters
- **Docker Deployment**: Production-ready containerized service
- **Template System**: Secure Jinja2 templates for nginx config generation

### Key Components

- **`swag_mcp/`**: Core application package with modular architecture
- **`templates/`**: Nginx configuration templates (4 types: subdomain, subfolder, mcp-subdomain, mcp-subfolder)
- **`tests/`**: Comprehensive test suite with performance, integration, and validation tests
- **`docs/`**: Test command documentation with 600+ examples

## Common Development Commands

### Testing & Quality
```bash
# Run full test suite with coverage
uv run pytest --cov=swag_mcp --cov-report=term-missing

# Run specific test categories
uv run pytest tests/test_swag_actions.py      # Action functionality
uv run pytest tests/test_validation.py       # Input validation
uv run pytest tests/test_integration.py      # End-to-end tests

# Code quality checks
uv run ruff check swag_mcp/                  # Linting
uv run mypy swag_mcp/                       # Type checking
pre-commit run --all-files                  # All pre-commit hooks
```

### Development Server
```bash
# Development mode with auto-reload
fastmcp dev swag_mcp/server.py

# Direct module execution
python -m swag_mcp

# Production Docker deployment
docker compose up -d
```

### Build & Deploy
```bash
# Build Docker image
docker build -t swag-mcp .

# Run installer script
bash install.sh

# View container logs
docker compose logs -f swag-mcp
```

## Tool Actions Reference

The unified `swag` tool supports 10 actions:

| Action | Purpose | Natural Language Example |
|--------|---------|--------------------------|
| `list` | List configurations | "Show all active proxy configurations" |
| `create` | Create new config | "Create jellyfin proxy at media.example.com:8096" |
| `view` | Read config content | "Show the jellyfin configuration file" |
| `edit` | Update config content | "Edit the jellyfin config with new content" |
| `update` | Update specific field | "Change jellyfin port to 8097" |
| `config` | View current defaults | "Show default configuration settings" |
| `remove` | Delete configuration | "Remove the jellyfin proxy configuration" |
| `logs` | View SWAG logs | "Show last 100 nginx error log lines" |
| `cleanup_backups` | Clean old backups | "Clean up backup files older than 7 days" |
| `health_check` | Test service health | "Check if media.example.com is accessible" |

## Environment Variables

All configuration uses `SWAG_MCP_*` prefix:

### Core Settings (Required)
- `SWAG_MCP_PROXY_CONFS_PATH`: Path to SWAG proxy configurations directory
- `SWAG_MCP_LOG_DIRECTORY`: Directory for MCP server logs

### Server Settings
- `SWAG_MCP_HOST`: Server bind interface (default: 0.0.0.0)
- `SWAG_MCP_PORT`: External port (default: 8000, internal always 8000)

### Defaults
- `SWAG_MCP_DEFAULT_AUTH_METHOD`: Default auth (authelia, ldap, authentik, tinyauth, none)
- `SWAG_MCP_DEFAULT_CONFIG_TYPE`: Config type (subdomain, subfolder, mcp-subdomain, mcp-subfolder)
- `SWAG_MCP_DEFAULT_QUIC_ENABLED`: Enable QUIC by default (true/false)

### Performance & Logging
- `SWAG_MCP_LOG_LEVEL`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)
- `SWAG_MCP_SLOW_OPERATION_THRESHOLD_MS`: Slow operation warning threshold
- `SWAG_MCP_RATE_LIMIT_RPS`: Requests per second limit

## Project Structure

```
swag-mcp/
├── swag_mcp/          # @swag_mcp/CLAUDE.md - Core application package
│   ├── core/          # @swag_mcp/core/CLAUDE.md - Configuration & constants
│   ├── models/        # @swag_mcp/models/CLAUDE.md - Data models & validation
│   ├── services/      # @swag_mcp/services/CLAUDE.md - Business logic layer
│   ├── tools/         # @swag_mcp/tools/CLAUDE.md - MCP tool implementation
│   ├── middleware/    # @swag_mcp/middleware/CLAUDE.md - Request processing
│   └── utils/         # @swag_mcp/utils/CLAUDE.md - Utility functions
├── templates/         # @templates/CLAUDE.md - Nginx config templates
└── tests/            # @tests/CLAUDE.md - Testing strategies & commands
```

## Important Development Notes

### Security Considerations
- Templates use sandboxed Jinja2 environment to prevent SSTI attacks
- Input validation blocks path traversal and command injection
- Unicode normalization prevents encoding-based attacks
- File operations use atomic transactions with rollback

### Performance Features
- Streamable-HTTP transport for zero-buffering proxy configs
- Per-file locking prevents race conditions
- Async I/O throughout with proper error handling
- Connection pooling for health checks

### Common Gotchas
- Docker port mapping: External `SWAG_MCP_PORT` maps to internal 8000
- Template path is relative to working directory, not package
- Health checks require SWAG container to be running for log access
- Config names auto-resolve .conf extensions but be explicit when possible

## Quick Start Checklist

1. **Environment Setup**: Copy `.env.example` to `.env` and configure paths
2. **Dependencies**: Run `uv sync` to install all dependencies
3. **Development**: Start with `fastmcp dev swag_mcp/server.py`
4. **Testing**: Run `uv run pytest` to verify everything works
5. **Production**: Deploy with `docker compose up -d`

## Debugging Tips

- **Health endpoint**: Check `http://localhost:8000/health` for server status
- **Logs**: Use `docker compose logs -f swag-mcp` for real-time logs
- **Validation errors**: Check Pydantic model constraints in `swag_mcp/models/`
- **Template issues**: Verify template syntax with secure Jinja2 patterns
- **File permissions**: Ensure Docker has access to proxy-confs and log directories
