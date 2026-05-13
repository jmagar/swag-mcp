"""Handlers for SWAG config actions: list, create, view, edit, remove, update."""

import asyncio
import logging
import re
from collections.abc import Coroutine
from typing import Any, Literal, cast

from fastmcp import Context
from fastmcp.tools import ToolResult

from swag_mcp.models.config import (
    ListFilterType,
    SwagConfigRequest,
    SwagEditRequest,
    SwagHealthCheckRequest,
    SwagRemoveRequest,
    SwagUpdateRequest,
)
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter
from swag_mcp.utils.tool_helpers import (
    log_action_start,
    log_action_success,
    validate_list_filter,
    validate_required_params,
)

logger = logging.getLogger(__name__)
_BACKGROUND_TASKS: set[asyncio.Task[str]] = set()

# Type alias for update field values
UpdateFieldType = Literal["port", "upstream", "app", "add_mcp"]


async def _extract_server_name_from_config(
    swag_service: SwagManagerService, config_name: str
) -> str | None:
    """Extract server_name from nginx config file.

    Args:
        swag_service: Service instance for configuration operations
        config_name: Configuration file name

    Returns:
        Server name if found, None otherwise

    """
    try:
        config_content = await swag_service.read_config(config_name)
        match = re.search(r"server_name\s+([^;]+);", config_content)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return None


async def _run_health_check(swag_service: SwagManagerService, server_name: str) -> str:
    """Run health check for a domain and return formatted status.

    Args:
        swag_service: Service instance for health check operations
        server_name: Domain name to check

    Returns:
        Formatted health check status

    """
    logger.info("Running post-write health check for %s", server_name)

    try:
        health_request = SwagHealthCheckRequest(
            domain=server_name,
            timeout=15,
            follow_redirects=True,
        )

        health_result = await swag_service.health_check(health_request)

        if health_result.success:
            status_code = health_result.status_code or "unknown"
            response_time = health_result.response_time_ms or 0
            health_status = f"✅ Health check passed: {status_code} ({response_time}ms)"
            logger.info("Post-write health check successful for %s", server_name)
        else:
            health_status = f"⚠️ Health check failed: {health_result.error or 'Unknown error'}"
            logger.info(
                "Post-write health check failed for %s: %s",
                server_name,
                health_result.error,
            )

        return health_status

    except Exception as e:
        health_status = f"⚠️ Health check error: {str(e)}"
        logger.info("Post-write health check encountered an error: %s", e)
        return health_status


async def _run_post_create_health_check(
    swag_service: SwagManagerService, server_name: str, filename: str
) -> str:
    """Run health check after config creation and format results."""
    health_status = await _run_health_check(swag_service, server_name)
    return f"Created configuration: {filename}\n{health_status}"


async def _run_post_update_health_check(
    swag_service: SwagManagerService,
    server_name: str | None,
    config_name: str,
    field: str,
    new_value: str,
) -> str:
    """Run health check after config update and format results."""
    if not server_name:
        return f"Updated {field} in {config_name} to {new_value}"

    health_status = await _run_health_check(swag_service, server_name)
    return f"Updated {field} in {config_name} to {new_value}\n{health_status}"


async def _run_post_create_health_check_in_background(
    source_service: SwagManagerService,
    server_name: str,
    filename: str,
) -> str:
    """Run post-create health check with a service lifetime owned by the background task."""
    async with SwagManagerService(
        config_path=source_service.config_path,
        template_path=source_service.template_path,
        settings=source_service.settings,
    ) as health_service:
        return await _run_post_create_health_check(health_service, server_name, filename)


async def _run_post_update_health_check_in_background(
    source_service: SwagManagerService,
    server_name: str | None,
    config_name: str,
    field: str,
    new_value: str,
) -> str:
    """Run post-update health check with a service lifetime owned by the background task."""
    async with SwagManagerService(
        config_path=source_service.config_path,
        template_path=source_service.template_path,
        settings=source_service.settings,
    ) as health_service:
        return await _run_post_update_health_check(
            health_service, server_name, config_name, field, new_value
        )


def _schedule_post_write_health_check(coro: Coroutine[Any, Any, str], description: str) -> None:
    """Schedule post-write health verification without blocking tool responses."""
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)

    def _log_background_result(done_task: asyncio.Task[str]) -> None:
        _BACKGROUND_TASKS.discard(done_task)
        try:
            done_task.result()
        except asyncio.CancelledError:
            logger.debug("Post-write health verification cancelled: %s", description)
        except Exception:
            logger.exception("Post-write health verification failed: %s", description)

    task.add_done_callback(_log_background_result)


async def _handle_list_action(
    ctx: Context,
    swag_service: SwagManagerService,
    formatter: TokenEfficientFormatter,
    list_filter: str,
    offset: int = 0,
    limit: int = 50,
    sort_by: str = "name",
    sort_order: str = "asc",
    query: str = "",
) -> ToolResult:
    """Handle LIST action with pagination."""
    await log_action_start(ctx, "Listing SWAG configurations", list_filter)

    if error := validate_list_filter(cast("Literal['all', 'active', 'samples']", list_filter)):
        return formatter.format_error_result(error.get("message", "Invalid list filter"), "list")

    _allowed_sort_fields = {"name", "filename"}
    if sort_by not in _allowed_sort_fields:
        return formatter.format_error_result(
            f"Invalid sort_by value '{sort_by}'. Allowed values: {sorted(_allowed_sort_fields)}",
            "list",
        )

    validated_list_filter = cast("ListFilterType", list_filter)
    result = await swag_service.list_configs(validated_list_filter)

    # Apply query filter, sort, and pagination
    configs = result.configs or []
    if query:
        configs = [c for c in configs if query.lower() in str(c).lower()]

    def _get_sort_key(c: object) -> str:
        value = getattr(c, sort_by, None)
        return str(value) if value is not None else str(c)

    if sort_order == "desc":
        configs = sorted(configs, key=_get_sort_key, reverse=True)
    else:
        configs = sorted(configs, key=_get_sort_key)
    total = len(configs)
    page = configs[offset : offset + limit]

    # Standard pagination response shape
    result_data = {
        "items": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
        # Legacy fields for formatter compatibility
        "configs": page,
        "total_count": total,
        "list_filter": result.list_filter,
    }

    await log_action_success(ctx, f"Listed {total} configurations (offset={offset}, limit={limit})")
    return formatter.format_list_result(result_data, validated_list_filter)


async def _handle_create_action(
    ctx: Context,
    swag_service: SwagManagerService,
    formatter: TokenEfficientFormatter,
    config_name: str,
    server_name: str,
    upstream_app: str,
    upstream_port: int,
    upstream_proto: str,
    auth_method: str,
    enable_quic: bool,
    mcp_upstream_app: str | None = None,
    mcp_upstream_port: int | None = None,
    mcp_upstream_proto: str | None = None,
) -> ToolResult:
    """Handle CREATE action with comprehensive progress reporting."""
    if error := validate_required_params(
        {
            "config_name": (config_name, "config_name"),
            "server_name": (server_name, "server_name"),
            "upstream_app": (upstream_app, "upstream_app"),
            "upstream_port": (
                upstream_port if upstream_port != 0 else None,
                "upstream_port",
            ),
        },
        "create",
    ):
        return formatter.format_error_result(
            error.get("message", "Missing required parameters"), "create"
        )

    await log_action_start(ctx, "Creating configuration", config_name)

    try:
        await ctx.info("Validating configuration parameters...")

        config_request = SwagConfigRequest(
            config_name=config_name,
            server_name=server_name,
            upstream_app=upstream_app,
            upstream_port=upstream_port,
            upstream_proto=cast("Literal['http', 'https']", upstream_proto),
            auth_method=auth_method,
            enable_quic=enable_quic,
            mcp_upstream_app=mcp_upstream_app,
            mcp_upstream_port=mcp_upstream_port,
            mcp_upstream_proto=(
                cast("Literal['http', 'https']", mcp_upstream_proto) if mcp_upstream_proto else None
            ),
        )

        await ctx.info("Creating proxy configuration...")
        result = await asyncio.wait_for(
            swag_service.create_config(config_request),
            timeout=180,  # 3 minute timeout for creation
        )

        await ctx.info("Scheduling health verification...")
        health_check_result = f"Health verification scheduled for {server_name}"
        _schedule_post_write_health_check(
            _run_post_create_health_check_in_background(swag_service, server_name, result.filename),
            f"create:{result.filename}",
        )

        await log_action_success(ctx, f"Created configuration {config_name}")
        await ctx.info("Configuration created successfully")

        result_data = {
            "success": True,
            "filename": result.filename,
            "content": result.content,
            "backup_created": result.backup_created,
            "health_check": health_check_result,
        }

        return formatter.format_create_result(result_data, config_name)

    except asyncio.CancelledError:
        await ctx.info("Configuration creation cancelled by user")
        raise
    except TimeoutError:
        await ctx.info("Configuration creation timed out")
        return formatter.format_error_result("Create operation timed out", "create")


async def _handle_view_action(
    ctx: Context,
    swag_service: SwagManagerService,
    formatter: TokenEfficientFormatter,
    config_name: str,
) -> ToolResult:
    """Handle VIEW action."""
    await log_action_start(ctx, "Viewing configuration", config_name)

    if error := validate_required_params({"config_name": (config_name, "config_name")}, "view"):
        return formatter.format_error_result(error.get("message", "Missing config name"), "view")

    try:
        content = await swag_service.read_config(config_name)
        await log_action_success(ctx, f"Read configuration {config_name}")

        result_data = {"filename": config_name, "content": content}
        return formatter.format_view_result(result_data, config_name)
    except FileNotFoundError:
        return formatter.format_error_result(f"Configuration '{config_name}' not found", "view")


async def _handle_edit_action(
    ctx: Context,
    swag_service: SwagManagerService,
    formatter: TokenEfficientFormatter,
    config_name: str,
    new_content: str,
    create_backup: bool,
) -> ToolResult:
    """Handle EDIT action with progress reporting and cancellation support."""
    await log_action_start(ctx, "Editing configuration", config_name)

    if error := validate_required_params(
        {
            "config_name": (config_name, "config_name"),
            "new_content": (new_content, "new_content"),
        },
        "edit",
    ):
        return formatter.format_error_result(
            error.get("message", "Missing required parameters"), "edit"
        )

    try:
        await ctx.info("Validating configuration content...")

        edit_request = SwagEditRequest(
            config_name=config_name,
            new_content=new_content,
            create_backup=create_backup,
        )

        await ctx.info("Applying configuration changes...")
        edit_result = await asyncio.wait_for(
            swag_service.update_config(edit_request),
            timeout=300,  # 5 minute timeout for large configs
        )

        await log_action_success(ctx, f"Successfully edited {config_name}")
        await ctx.info("Configuration edit completed successfully")

        result_data = {
            "success": True,
            "backup_created": edit_result.backup_created,
        }

        return formatter.format_edit_result(result_data, config_name)

    except asyncio.CancelledError:
        await ctx.info("Configuration edit cancelled by user")
        raise
    except TimeoutError:
        await ctx.info("Configuration edit timed out")
        return formatter.format_error_result("Edit operation timed out", "edit")


async def _handle_remove_action(
    ctx: Context,
    swag_service: SwagManagerService,
    formatter: TokenEfficientFormatter,
    config_name: str,
    create_backup: bool,
) -> ToolResult:
    """Handle REMOVE action with progress reporting."""
    await log_action_start(ctx, "Removing configuration", config_name)

    if error := validate_required_params({"config_name": (config_name, "config_name")}, "remove"):
        return formatter.format_error_result(error.get("message", "Missing config_name"), "remove")

    try:
        await ctx.info("Preparing to remove configuration...")

        remove_request = SwagRemoveRequest(config_name=config_name, create_backup=create_backup)

        await ctx.info("Removing configuration file...")
        remove_result = await swag_service.remove_config(remove_request)

        await log_action_success(ctx, f"Successfully removed {config_name}")
        await ctx.info("Configuration removal completed")

        result_data = {
            "success": True,
            "backup_created": remove_result.backup_created,
        }

        return formatter.format_remove_result(result_data, config_name)

    except asyncio.CancelledError:
        await ctx.info("Configuration removal cancelled by user")
        raise


async def _handle_update_action(
    ctx: Context,
    swag_service: SwagManagerService,
    formatter: TokenEfficientFormatter,
    config_name: str,
    update_field: str,
    update_value: str,
    create_backup: bool,
) -> ToolResult:
    """Handle UPDATE action with progress reporting and health check."""
    if error := validate_required_params(
        {
            "config_name": (config_name, "config_name"),
            "update_field": (update_field, "update_field"),
            "update_value": (update_value, "update_value"),
        },
        "update",
    ):
        return formatter.format_error_result(
            error.get("message", "Missing required parameters"), "update"
        )

    await log_action_start(ctx, f"Updating {update_field}", f"{config_name} to {update_value}")

    try:
        valid_update_fields: set[UpdateFieldType] = {"port", "upstream", "app", "add_mcp"}
        if update_field not in valid_update_fields:
            return formatter.format_error_result(
                f"Invalid update_field: '{update_field}'. "
                f"Must be one of: {', '.join(valid_update_fields)}",
                "update",
            )

        validated_update_field: UpdateFieldType = cast("UpdateFieldType", update_field)

        await ctx.info(f"Preparing to update {update_field} field...")
        server_name = await _extract_server_name_from_config(swag_service, config_name)

        update_request = SwagUpdateRequest(
            config_name=config_name,
            update_field=validated_update_field,
            update_value=update_value,
            create_backup=create_backup,
        )

        await ctx.info(f"Applying {update_field} update...")
        update_result = await asyncio.wait_for(
            swag_service.update_config_field(update_request),
            timeout=120,  # 2 minute timeout for updates
        )

        await ctx.info("Scheduling post-update health check...")
        health_check_result = f"Health verification scheduled for {config_name}"
        _schedule_post_write_health_check(
            _run_post_update_health_check_in_background(
                swag_service, server_name, config_name, update_field, update_value
            ),
            f"update:{config_name}:{update_field}",
        )

        await log_action_success(ctx, f"Successfully updated {update_field} in {config_name}")
        await ctx.info("Update completed successfully")

        result_data = {
            "success": True,
            "filename": config_name,
            "backup_created": update_result.backup_created,
            "health_check": health_check_result,
        }
        if update_field == "add_mcp":
            result_data["content"] = update_result.content

        return formatter.format_update_result(
            result_data, config_name, update_field, update_value, health_check_result
        )

    except asyncio.CancelledError:
        await ctx.info("Update operation cancelled by user")
        raise
    except TimeoutError:
        await ctx.info("Update operation timed out")
        return formatter.format_error_result("Update operation timed out", "update")
