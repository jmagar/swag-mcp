# SWAG MCP Core Package - Claude Memory Reference

This directory contains the core SWAG MCP application package with modular architecture for MCP server functionality.

## Package Purpose

The `swag_mcp` package implements a FastMCP server that provides AI assistants with tools to manage SWAG reverse proxy configurations through natural language commands. It uses a unified tool architecture with comprehensive middleware and service layers.

## Module Organization

### Entry Points
- **`__main__.py`**: Module execution entry point (`python -m swag_mcp`)
- **`server.py`**: FastMCP server setup, middleware registration, resource discovery

### Core Subdirectories
- **`core/`**: @core/CLAUDE.md - Configuration management, constants, logging setup
- **`models/`**: @models/CLAUDE.md - Pydantic data models, validation, request/response schemas
- **`services/`**: @services/CLAUDE.md - Business logic layer, SwagManagerService (1494 lines)
- **`tools/`**: @tools/CLAUDE.md - MCP tool implementation, unified `swag` tool (621 lines)
- **`middleware/`**: @middleware/CLAUDE.md - Request processing pipeline, error handling, rate limiting
- **`utils/`**: @utils/CLAUDE.md - Utility functions, validators, formatters, helpers

## Key Files Deep Dive

### `server.py` - FastMCP Server Setup
```python
# Main server initialization and middleware registration
app = create_mcp_server()
setup_middleware(app)  # Error handling, timing, rate limiting
register_tools(app)    # Unified swag tool registration
register_resources(app)  # Dynamic SWAG config discovery
```

**Key Functions:**
- `create_mcp_server()`: Initializes FastMCP with streamable-http transport
- `setup_middleware()`: Registers middleware stack in correct order
- `register_resources()`: Discovers and exposes SWAG config files as MCP resources
- `main()`: Production server startup with error handling

### `__main__.py` - Module Entry Point
```python
# Enables: python -m swag_mcp
if __name__ == "__main__":
    from swag_mcp.server import main
    main()
```

Simple entry point that imports and runs the main server function.

## Dependencies & Import Patterns

### FastMCP Framework
```python
from fastmcp import FastMCP, Context
from fastmcp.middleware import middleware
```

### Internal Imports
```python
# Configuration
from swag_mcp.core.config import SwagConfig
from swag_mcp.core.logging_config import setup_logging

# Tools and Services
from swag_mcp.tools.swag import swag
from swag_mcp.services.swag_manager import SwagManagerService

# Models and Utilities
from swag_mcp.models.enums import SwagAction
from swag_mcp.utils.error_handlers import handle_os_error
```

## Development Workflow

### Local Development
```bash
# Start development server with auto-reload
fastmcp dev swag_mcp/server.py

# Direct module execution
python -m swag_mcp

# Run from package directory
cd swag_mcp && python -m swag_mcp
```

### Testing Package Structure
```bash
# Test imports work correctly
python -c "import swag_mcp; print('Package loads successfully')"

# Test server starts
python -m swag_mcp --help

# Verify middleware registration
curl http://localhost:8000/health
```

### Module-Specific Testing
```bash
# Test core configuration
uv run pytest tests/ -k "config"

# Test tool registration
uv run pytest tests/test_swag_actions.py

# Test server setup
uv run pytest tests/test_integration.py
```

## Architecture Patterns

### Dependency Injection
- `SwagConfig` injected into services via Pydantic Settings
- `SwagManagerService` instantiated with configuration
- Context passed through middleware stack

### Error Handling Strategy
- Global error middleware catches all exceptions
- Service-level error handling with typed exceptions
- Tool-level error responses with user-friendly messages
- OS error mapping to human-readable descriptions

### Async/Await Patterns
- All I/O operations are async (file operations, HTTP requests)
- Proper async context management with `async with`
- Event loop detection for both sync/async execution contexts

## Configuration Flow

1. **Environment Variables**: Loaded via `SwagConfig` (Pydantic Settings)
2. **Default Values**: Applied from `core/constants.py`
3. **Runtime Overrides**: Possible through FastMCP context
4. **Service Injection**: Configuration injected into `SwagManagerService`

## Middleware Stack Order

1. **Error Handling**: Global exception catching (first)
2. **Timing**: Performance monitoring
3. **Rate Limiting**: Request throttling
4. **Request Logging**: Detailed request/response logging (last)

## Resource Discovery

The server dynamically discovers and registers SWAG configuration files:
- Scans `SWAG_MCP_PROXY_CONFS_PATH` directory
- Exposes `.conf` files as MCP resources
- Provides file metadata (size, modified time)
- Enables direct file access through MCP clients

## Common Development Tasks

### Adding New Middleware
1. Create middleware function in `middleware/` subdirectory
2. Import in `middleware/__init__.py`
3. Register in `server.py` `setup_middleware()` function
4. Test middleware behavior with integration tests

### Extending Tool Functionality
1. Add new action to `models/enums.py` SwagAction enum
2. Create request/response models in `models/config.py`
3. Implement action handler in `services/swag_manager.py`
4. Add action branch to `tools/swag.py` dispatch logic
5. Write comprehensive tests in `tests/test_swag_actions.py`

### Configuration Changes
1. Add new environment variable to `core/config.py` SwagConfig
2. Update default values in `core/constants.py`
3. Document in root `.env.example`
4. Add validation if needed

## Important Notes

### Package Import Structure
- Always import from package root: `from swag_mcp.core.config import SwagConfig`
- Avoid relative imports across subdirectories
- Use absolute imports for better IDE support and clarity

### Service Instantiation
- `SwagManagerService` is heavy (1494 lines) - instantiate once per request
- Configuration is read once at startup and cached
- File operations use async I/O with proper resource cleanup

### Development vs Production
- Development: `fastmcp dev` enables auto-reload and detailed logging
- Production: `python -m swag_mcp` optimized for performance
- Docker: Always uses production mode with proper signal handling

### Performance Considerations
- Middleware order affects request processing time
- Resource discovery happens at startup, not per-request
- File operations are locked per-file to prevent race conditions
- HTTP client connection pooling for health checks
