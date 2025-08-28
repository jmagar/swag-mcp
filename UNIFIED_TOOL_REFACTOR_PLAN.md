# SWAG MCP Unified Tool Refactor Plan

## Overview

This plan outlines the refactoring of 9 separate FastMCP tools into a single unified `swag` tool using Pydantic's discriminated union pattern. This approach will:

- Reduce token usage and MCP protocol overhead
- Provide better validation with clear error messages
- Create a more CLI-like interface
- Simplify maintenance and extensibility
- Maintain full type safety and MyPy compliance

## Current State

### Existing Tools
1. `swag_list` - List configuration files
2. `swag_create` - Create new configurations
3. `swag_view` - View configuration content
4. `swag_edit` - Edit existing configurations
5. `swag_config` - View/update defaults
6. `swag_remove` - Remove configurations
7. `swag_logs` - View Docker logs
8. `swag_cleanup_backups` - Clean old backups
9. `swag_health_check` - Health check endpoints

### Issues with Current Approach
- High MCP protocol overhead (9 tool registrations)
- Increased token usage in LLM context
- Repetitive code patterns
- More surface area to maintain

## Proposed Solution

### Architecture Overview

```
SwagCommand (Discriminated Union)
├── ListCommand
├── CreateCommand
├── ViewCommand
├── EditCommand
├── ConfigCommand
├── RemoveCommand
├── LogsCommand
├── CleanupCommand
└── HealthCheckCommand
```

## Implementation Plan

### Phase 1: Create Command Models

**File:** `swag_mcp/models/commands.py`

```python
"""Pydantic models for unified SWAG command interface."""

from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field, field_validator

from ..utils.validators import validate_domain_format


class SwagCommandBase(BaseModel):
    """Base class for all SWAG commands with common functionality."""

    class Config:
        extra = "forbid"  # Prevent additional fields


# Command Models
class ListCommand(SwagCommandBase):
    """List SWAG configuration files."""

    command: Literal["list"] = Field(
        default="list",
        description="List configuration files"
    )
    config_type: Annotated[
        str,
        Field(
            default="all",
            pattern="^(all|active|samples)$",
            description="Type of configurations to list"
        )
    ]


class CreateCommand(SwagCommandBase):
    """Create new SWAG reverse proxy configuration."""

    command: Literal["create"] = Field(
        default="create",
        description="Create new reverse proxy configuration"
    )
    service_name: Annotated[
        str,
        Field(
            ...,
            pattern=r"^[\w-]+$",
            max_length=50,
            description="Service identifier used for filename"
        )
    ]
    server_name: Annotated[
        str,
        Field(
            ...,
            max_length=253,
            description="Domain name (e.g., 'test.tootie.tv')"
        )
    ]
    upstream_app: Annotated[
        str,
        Field(
            ...,
            pattern=r"^[a-zA-Z0-9_.-]+$",
            max_length=100,
            description="Container name or IP address"
        )
    ]
    upstream_port: Annotated[
        int,
        Field(
            ...,
            ge=1,
            le=65535,
            description="Port number the service runs on"
        )
    ]
    upstream_proto: Annotated[
        Literal["http", "https"],
        Field(
            default="http",
            description="Protocol for upstream connection"
        )
    ]
    config_type: Annotated[
        Literal["subdomain", "subfolder", "mcp-subdomain", "mcp-subfolder"],
        Field(
            default="subdomain",
            description="Type of configuration to generate"
        )
    ]
    auth_method: Annotated[
        Literal["none", "ldap", "authelia", "authentik", "tinyauth"],
        Field(
            default="none",
            description="Authentication method to use"
        )
    ]
    enable_quic: Annotated[
        bool,
        Field(
            default=False,
            description="Enable QUIC support"
        )
    ]

    @field_validator("server_name")
    @classmethod
    def validate_server_name(cls, v: str) -> str:
        """Validate server name format."""
        return validate_domain_format(v)

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v: str) -> str:
        """Validate service name."""
        if not v or v.startswith("-") or v.endswith("-"):
            raise ValueError("Service name cannot start or end with hyphen")
        return v.lower()


class ViewCommand(SwagCommandBase):
    """View contents of existing configuration file."""

    command: Literal["view"] = Field(
        default="view",
        description="View configuration file contents"
    )
    config_name: Annotated[
        str,
        Field(
            ...,
            pattern=r"^[a-zA-Z0-9_.-]+\.(conf|sample)$",
            description="Name of configuration file to view"
        )
    ]


class EditCommand(SwagCommandBase):
    """Edit existing configuration file."""

    command: Literal["edit"] = Field(
        default="edit",
        description="Edit existing configuration file"
    )
    config_name: Annotated[
        str,
        Field(
            ...,
            pattern=r"^[a-zA-Z0-9_.-]+\.(conf|sample)$",
            description="Name of configuration file to edit"
        )
    ]
    new_content: Annotated[
        str,
        Field(
            ...,
            min_length=1,
            description="New content for the configuration file"
        )
    ]
    create_backup: Annotated[
        bool,
        Field(
            default=True,
            description="Whether to create a backup before editing"
        )
    ]


class ConfigCommand(SwagCommandBase):
    """Configure default settings."""

    command: Literal["config"] = Field(
        default="config",
        description="View current default configuration settings"
    )
    # Note: This command only shows current env vars, no modification


class RemoveCommand(SwagCommandBase):
    """Remove existing SWAG configuration file."""

    command: Literal["remove"] = Field(
        default="remove",
        description="Remove configuration file"
    )
    config_name: Annotated[
        str,
        Field(
            ...,
            pattern=r"^[a-zA-Z0-9_.-]+\.conf$",
            description="Name of configuration file to remove (must be .conf, not .sample)"
        )
    ]
    create_backup: Annotated[
        bool,
        Field(
            default=True,
            description="Whether to create a backup before removing"
        )
    ]


class LogsCommand(SwagCommandBase):
    """Show SWAG docker container logs."""

    command: Literal["logs"] = Field(
        default="logs",
        description="Show SWAG docker container logs"
    )
    lines: Annotated[
        int,
        Field(
            default=100,
            ge=1,
            le=1000,
            description="Number of log lines to retrieve"
        )
    ]
    follow: Annotated[
        bool,
        Field(
            default=False,
            description="Follow log output (not recommended for normal use)"
        )
    ]


class CleanupCommand(SwagCommandBase):
    """Clean up old backup files."""

    command: Literal["cleanup-backups"] = Field(
        default="cleanup-backups",
        description="Clean up old backup files"
    )
    retention_days: Annotated[
        int | None,
        Field(
            default=None,
            description="Days to retain backup files (uses config default if not specified)"
        )
    ]


class HealthCheckCommand(SwagCommandBase):
    """Perform health check on SWAG-managed service endpoint."""

    command: Literal["health-check"] = Field(
        default="health-check",
        description="Perform health check on service endpoint"
    )
    domain: Annotated[
        str,
        Field(
            ...,
            max_length=253,
            description="Full domain to check health for (e.g., 'docker-mcp.tootie.tv')"
        )
    ]
    timeout: Annotated[
        int,
        Field(
            default=30,
            ge=1,
            le=300,
            description="Request timeout in seconds"
        )
    ]
    follow_redirects: Annotated[
        bool,
        Field(
            default=True,
            description="Whether to follow HTTP redirects"
        )
    ]

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Validate domain format."""
        return validate_domain_format(v)


# Discriminated Union Type
SwagCommand = Annotated[
    Union[
        ListCommand,
        CreateCommand,
        ViewCommand,
        EditCommand,
        ConfigCommand,
        RemoveCommand,
        LogsCommand,
        CleanupCommand,
        HealthCheckCommand,
    ],
    Field(discriminator="command")
]
```

### Phase 2: Refactor Main Tool File

**File:** `swag_mcp/tools/swag.py`

```python
"""Unified FastMCP tool for SWAG configuration management."""

import logging
from typing import Annotated

from fastmcp import Context, FastMCP
from pydantic import Field

from ..core.config import config
from ..models.commands import SwagCommand
from ..models.config import (
    SwagConfigRequest,
    SwagEditRequest,
    SwagHealthCheckRequest,
    SwagLogsRequest,
    SwagRemoveRequest,
)
from ..services.swag_manager import SwagManagerService
from ..utils.formatters import format_health_check_result
from ..utils.tool_decorators import handle_tool_errors

logger = logging.getLogger(__name__)

# Initialize the SWAG manager service
swag_service = SwagManagerService()


async def _run_post_create_health_check(ctx: Context, server_name: str, filename: str) -> str:
    """Run health check after config creation and format results."""
    await ctx.info(f"Running health check for {server_name}...")

    try:
        health_request = SwagHealthCheckRequest(
            domain=server_name,
            timeout=15,  # Shorter timeout for create flow
            follow_redirects=True,
        )

        health_result = await swag_service.health_check(health_request)

        if health_result.success:
            health_status = (
                f"✅ Health check passed: {health_result.status_code} "
                f"({health_result.response_time_ms}ms)"
            )
            await ctx.info(f"Health check successful for {server_name}")
        else:
            health_status = f"⚠️ Health check failed: {health_result.error or 'Unknown error'}"
            await ctx.info(f"Health check failed for {server_name}: {health_result.error}")

        return f"Created configuration: {filename}\n{health_status}"

    except Exception as e:
        health_status = f"⚠️ Health check error: {str(e)}"
        await ctx.info(f"Health check encountered an error: {str(e)}")
        return f"Created configuration: {filename}\n{health_status}"


def register_tools(mcp: FastMCP) -> None:
    """Register the unified SWAG tool with the FastMCP server."""

    @mcp.tool
    @handle_tool_errors
    async def swag(
        ctx: Context,
        request: Annotated[
            SwagCommand,
            Field(
                description="SWAG configuration management command. "
                "Use 'command' field to specify operation: "
                "list, create, view, edit, config, remove, logs, "
                "cleanup-backups, health-check. "
                "Additional fields vary by command type."
            )
        ]
    ) -> str:
        """Unified SWAG reverse proxy configuration management tool.

        This single tool handles all SWAG operations through a command-based interface.
        The 'command' field determines the operation, and additional fields vary by command.

        Available Commands:

        • list: List configuration files
          - config_type: "all" | "active" | "samples" (default: "all")

        • create: Create new reverse proxy configuration
          - service_name: Service identifier for filename (required)
          - server_name: Domain name like "test.tootie.tv" (required)
          - upstream_app: Container name or IP (required)
          - upstream_port: Port number 1-65535 (required)
          - upstream_proto: "http" | "https" (default: "http")
          - config_type: "subdomain" | "subfolder" | "mcp-subdomain" | "mcp-subfolder" (default: "subdomain")
          - auth_method: "none" | "ldap" | "authelia" | "authentik" | "tinyauth" (default: "none")
          - enable_quic: Enable QUIC support (default: false)

        • view: View existing configuration content
          - config_name: Configuration file name with .conf or .sample extension (required)

        • edit: Edit existing configuration
          - config_name: Configuration file name to edit (required)
          - new_content: New configuration content (required)
          - create_backup: Create backup before editing (default: true)

        • config: View current default settings from environment variables
          - No additional parameters

        • remove: Remove configuration file
          - config_name: Configuration file name with .conf extension (required)
          - create_backup: Create backup before removal (default: true)

        • logs: View Docker container logs
          - lines: Number of lines to retrieve 1-1000 (default: 100)
          - follow: Follow log output (default: false)

        • cleanup-backups: Clean up old backup files
          - retention_days: Days to retain backups (optional, uses config default)

        • health-check: Check service endpoint health
          - domain: Full domain to check like "docker-mcp.tootie.tv" (required)
          - timeout: Request timeout 1-300 seconds (default: 30)
          - follow_redirects: Follow HTTP redirects (default: true)

        Examples:
        - {"command": "list", "config_type": "active"}
        - {"command": "create", "service_name": "my-app", "server_name": "app.tootie.tv", "upstream_app": "my-app-container", "upstream_port": 3000}
        - {"command": "view", "config_name": "my-app.conf"}
        - {"command": "health-check", "domain": "app.tootie.tv"}
        """

        # Dispatch based on command using pattern matching (Python 3.10+)
        match request.command:
            case "list":
                await ctx.info(f"Listing SWAG configurations: {request.config_type}")

                if request.config_type not in ["all", "active", "samples"]:
                    raise ValueError("config_type must be 'all', 'active', or 'samples'")

                result = await swag_service.list_configs(request.config_type)
                await ctx.info(f"Found {result.total_count} configurations")
                return str(result.configs)

            case "create":
                # Prepare configuration defaults
                auth_method, enable_quic, config_type = swag_service.prepare_config_defaults(
                    request.auth_method, request.enable_quic, request.config_type
                )

                await ctx.info(f"Creating {config_type} configuration for {request.service_name}")

                # Convert command model to existing request model
                config_request = SwagConfigRequest(
                    service_name=request.service_name,
                    server_name=request.server_name,
                    upstream_app=request.upstream_app,
                    upstream_port=request.upstream_port,
                    upstream_proto=request.upstream_proto,
                    config_type=config_type,
                    auth_method=auth_method,
                    enable_quic=enable_quic,
                )

                # Check if template exists
                if not await swag_service.validate_template_exists(config_type):
                    raise ValueError(f"Template for {config_type} configuration not found")

                # Create configuration
                result = await swag_service.create_config(config_request)
                await ctx.info(f"Successfully created {result.filename}")

                # Run health check and return formatted result
                return await _run_post_create_health_check(ctx, request.server_name, result.filename)

            case "view":
                await ctx.info(f"Reading configuration: {request.config_name}")

                content = await swag_service.read_config(request.config_name)
                await ctx.info(f"Successfully read {request.config_name} ({len(content)} characters)")
                return content

            case "edit":
                await ctx.info(f"Editing configuration: {request.config_name}")

                edit_request = SwagEditRequest(
                    config_name=request.config_name,
                    new_content=request.new_content,
                    create_backup=request.create_backup
                )

                result = await swag_service.update_config(edit_request)

                if result.backup_created:
                    message = f"Updated {request.config_name}, backup created: {result.backup_created}"
                    await ctx.info(message)
                    return message
                else:
                    message = f"Updated {request.config_name} (no backup created)"
                    await ctx.info(message)
                    return message

            case "config":
                await ctx.info("Retrieving current default configuration from environment variables")
                current_defaults = {
                    "default_auth_method": config.default_auth_method,
                    "default_quic_enabled": config.default_quic_enabled,
                    "default_config_type": config.default_config_type,
                }
                message = (
                    f"Current defaults: {current_defaults}\n\n"
                    "Note: To change these values, update your .env file and restart the server."
                )
                await ctx.info(message)
                return message

            case "remove":
                await ctx.info(f"Removing configuration: {request.config_name}")

                remove_request = SwagRemoveRequest(
                    config_name=request.config_name,
                    create_backup=request.create_backup
                )

                result = await swag_service.remove_config(remove_request)

                if result.backup_created:
                    message = f"Removed {request.config_name}, backup created: {result.backup_created}"
                    await ctx.info(message)
                    return message
                else:
                    message = f"Removed {request.config_name} (no backup created)"
                    await ctx.info(message)
                    return message

            case "logs":
                await ctx.info(f"Retrieving SWAG docker logs: {request.lines} lines")

                logs_request = SwagLogsRequest(lines=request.lines, follow=request.follow)

                logs_output = await swag_service.get_docker_logs(logs_request)
                await ctx.info(f"Successfully retrieved {len(logs_output)} characters of log output")

                return logs_output

            case "cleanup-backups":
                await ctx.info("Running backup cleanup...")

                cleaned_count = await swag_service.cleanup_old_backups(request.retention_days)

                if cleaned_count > 0:
                    message = f"Cleaned up {cleaned_count} old backup files"
                    await ctx.info(message)
                    return message
                else:
                    message = "No old backup files to clean up"
                    await ctx.info(message)
                    return message

            case "health-check":
                await ctx.info(f"Starting health check for domain: {request.domain}")

                # Validate and create health check request
                health_request = SwagHealthCheckRequest(
                    domain=request.domain,
                    timeout=request.timeout,
                    follow_redirects=request.follow_redirects
                )

                # Perform health check
                result = await swag_service.health_check(health_request)

                # Format the response using helper function
                message, status = format_health_check_result(result)
                await ctx.info(f"Health check {status} for {request.domain}")

                return message

            case _:
                # This should never happen due to Pydantic validation
                raise ValueError(f"Unknown command: {request.command}")
```

### Phase 3: Update Tests

**File:** `tests/test_unified_tool.py`

```python
"""Tests for unified SWAG tool."""

import pytest
from unittest.mock import AsyncMock, patch

from swag_mcp.models.commands import SwagCommand, ListCommand, CreateCommand
from swag_mcp.tools.swag import register_tools


class TestUnifiedSwagTool:
    """Test the unified SWAG tool."""

    @pytest.fixture
    def mock_ctx(self):
        """Mock FastMCP context."""
        ctx = AsyncMock()
        return ctx

    @pytest.fixture
    def mock_mcp(self):
        """Mock FastMCP instance."""
        mcp = AsyncMock()
        return mcp

    def test_list_command_validation(self):
        """Test ListCommand validation."""
        # Valid command
        cmd = ListCommand(config_type="active")
        assert cmd.command == "list"
        assert cmd.config_type == "active"

        # Invalid config_type
        with pytest.raises(ValueError):
            ListCommand(config_type="invalid")

    def test_create_command_validation(self):
        """Test CreateCommand validation."""
        # Valid command
        cmd = CreateCommand(
            service_name="test-app",
            server_name="test.tootie.tv",
            upstream_app="test-container",
            upstream_port=3000
        )
        assert cmd.command == "create"
        assert cmd.service_name == "test-app"
        assert cmd.upstream_port == 3000

        # Invalid port
        with pytest.raises(ValueError):
            CreateCommand(
                service_name="test",
                server_name="test.com",
                upstream_app="test",
                upstream_port=99999  # Invalid port
            )

    def test_discriminated_union(self):
        """Test discriminated union works correctly."""
        # List command
        list_data = {"command": "list", "config_type": "all"}
        parsed = SwagCommand.model_validate(list_data)
        assert isinstance(parsed, ListCommand)

        # Create command
        create_data = {
            "command": "create",
            "service_name": "test",
            "server_name": "test.com",
            "upstream_app": "test",
            "upstream_port": 3000
        }
        parsed = SwagCommand.model_validate(create_data)
        assert isinstance(parsed, CreateCommand)

    @pytest.mark.asyncio
    async def test_tool_registration(self, mock_mcp):
        """Test tool registration works."""
        register_tools(mock_mcp)

        # Verify tool was registered
        mock_mcp.tool.assert_called_once()

    @pytest.mark.asyncio
    @patch('swag_mcp.tools.swag.swag_service')
    async def test_list_command_execution(self, mock_service, mock_ctx):
        """Test list command execution."""
        # Setup mock
        mock_result = AsyncMock()
        mock_result.configs = ["test.conf"]
        mock_result.total_count = 1
        mock_service.list_configs.return_value = mock_result

        # Import and call the registered function
        from swag_mcp.tools.swag import register_tools
        mcp = AsyncMock()
        register_tools(mcp)

        # Get the registered function
        swag_tool = mcp.tool.call_args[0][0]

        # Create test request
        request = ListCommand(config_type="all")

        # Execute
        result = await swag_tool(mock_ctx, request)

        # Verify
        assert "test.conf" in result
        mock_service.list_configs.assert_called_once_with("all")
```

### Phase 4: Update Documentation

**File:** `docs/unified-tool.md`

```markdown
# Unified SWAG Tool

The SWAG MCP server now provides a single unified `swag` tool that handles all operations through a command-based interface.

## Usage

All operations use the same tool name `swag` with a `command` field to specify the operation:

### List Configurations
```json
{
  "command": "list",
  "config_type": "all"  // "all" | "active" | "samples"
}
```

### Create Configuration
```json
{
  "command": "create",
  "service_name": "my-app",
  "server_name": "app.tootie.tv",
  "upstream_app": "my-app-container",
  "upstream_port": 3000,
  "config_type": "subdomain",  // optional
  "auth_method": "none",       // optional
  "enable_quic": false         // optional
}
```

### View Configuration
```json
{
  "command": "view",
  "config_name": "my-app.conf"
}
```

### Edit Configuration
```json
{
  "command": "edit",
  "config_name": "my-app.conf",
  "new_content": "server { ... }",
  "create_backup": true  // optional
}
```

### Health Check
```json
{
  "command": "health-check",
  "domain": "app.tootie.tv",
  "timeout": 30,           // optional
  "follow_redirects": true // optional
}
```

## Benefits

- **Single Tool**: Only one tool to learn and use
- **Better Validation**: Pydantic ensures correct parameters for each command
- **Type Safety**: Full TypeScript-like experience in Python
- **Extensible**: Easy to add new commands
- **Token Efficient**: Reduces MCP protocol overhead
```

### Phase 5: Migration Steps

1. **Create new command models file**
   - Add discriminated union models
   - Include all validation logic
   - Add comprehensive type annotations

2. **Refactor main tool file**
   - Replace multiple tool functions with single unified function
   - Use pattern matching for command dispatch
   - Maintain all existing functionality

3. **Update tests**
   - Test command validation
   - Test discriminated union behavior
   - Test tool execution for each command

4. **Update documentation**
   - Document new unified interface
   - Provide usage examples
   - Explain migration benefits

5. **Remove old code**
   - Remove individual tool functions
   - Clean up unused imports
   - Update any references

## Validation Benefits

### Automatic Field Validation
Pydantic automatically validates:
- Required vs optional fields per command
- Field types and constraints
- Enum values for Literal types
- Pattern matching for strings
- Range validation for numbers

### Clear Error Messages
When validation fails, users get clear messages like:
```
ValidationError: 1 validation error for CreateCommand
upstream_port
  ensure this value is greater than or equal to 1
```

### IDE Support
Full autocomplete and type checking in IDEs when using the command models.

## FastMCP Alignment

This approach follows FastMCP best practices:

1. **Annotated Types**: Uses `Annotated[Type, Field(...)]` pattern for parameter descriptions
2. **Pydantic Integration**: Leverages Pydantic's validation and serialization
3. **Type Safety**: Maintains full MyPy compliance
4. **Documentation**: Rich docstrings and parameter descriptions
5. **Error Handling**: Proper exception handling with meaningful messages

## Conclusion

The unified tool approach provides:
- Better developer experience
- Reduced complexity
- Improved maintainability
- Enhanced validation
- Lower resource usage

This refactoring positions the SWAG MCP server for easier future enhancements while maintaining backward compatibility in functionality.
