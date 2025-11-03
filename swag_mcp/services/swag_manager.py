"""Core SWAG configuration management service - Orchestrator."""

import logging
from pathlib import Path
from typing import Any

from swag_mcp.core.config import config
from swag_mcp.models.config import (
    ListFilterType,
    SwagConfigRequest,
    SwagConfigResult,
    SwagEditRequest,
    SwagHealthCheckRequest,
    SwagHealthCheckResult,
    SwagListResult,
    SwagLogsRequest,
    SwagRemoveRequest,
    SwagResourceList,
    SwagUpdateRequest,
)

# Import all sub-managers
from swag_mcp.services.backup_manager import BackupManager
from swag_mcp.services.config_operations import ConfigOperations
from swag_mcp.services.config_updaters import ConfigFieldUpdaters
from swag_mcp.services.file_operations import FileOperations
from swag_mcp.services.health_monitor import HealthMonitor
from swag_mcp.services.mcp_operations import MCPOperations
from swag_mcp.services.resource_manager import ResourceManager
from swag_mcp.services.template_manager import TemplateManager
from swag_mcp.services.validation import ValidationService

logger = logging.getLogger(__name__)


class SwagManagerService:
    """Orchestrator service for managing SWAG proxy configurations.

    This class coordinates between 9 specialized sub-managers:
    - FileOperations: File I/O, transactions, locking
    - TemplateManager: Template rendering, security
    - ValidationService: Validation, diff/preview
    - BackupManager: Backup operations
    - HealthMonitor: Health checks, logs
    - ResourceManager: Resource/sample queries
    - MCPOperations: MCP location operations
    - ConfigFieldUpdaters: Field updaters (port/upstream/app/mcp)
    - ConfigOperations: CRUD operations
    """

    def __init__(
        self,
        config_path: Path | None = None,
        template_path: Path | None = None,
    ) -> None:
        """Initialize the SWAG manager orchestrator service.

        Args:
            config_path: Path to SWAG proxy configurations directory
            template_path: Path to Jinja2 templates directory
        """
        self.config_path: Path = (
            Path(config_path) if config_path is not None else Path(config.proxy_confs_path)
        )
        self.template_path: Path = (
            Path(template_path) if template_path is not None else Path(config.template_path)
        )

        logger.info(f"Initializing SWAG manager with proxy configs path: {self.config_path}")

        # ===== PHASE 1: Instantiate managers with no dependencies =====
        self.file_ops = FileOperations(config_path=self.config_path)
        self.template_manager = TemplateManager(template_path=self.template_path)
        self.validation_service = ValidationService()
        self.health_monitor = HealthMonitor()
        self.resource_manager = ResourceManager(config_path=self.config_path)

        # ===== PHASE 2: Instantiate managers with single-level dependencies =====
        self.backup_manager = BackupManager(
            config_path=self.config_path,
            file_ops=self.file_ops,
        )

        # ===== PHASE 3: Instantiate managers with multi-level dependencies =====
        self.mcp_operations = MCPOperations(
            config_path=self.config_path,
            template_manager=self.template_manager,
            validation=self.validation_service,
            file_ops=self.file_ops,
        )

        # Create temporary wrapper for ConfigFieldUpdaters (circular dependency workaround)
        from swag_mcp.services.config_updaters import MCPOperations as MCPOperationsWrapper
        mcp_ops_wrapper = MCPOperationsWrapper(swag_manager=self)

        self.config_updaters = ConfigFieldUpdaters(
            config_path=self.config_path,
            validation=self.validation_service,
            file_ops=self.file_ops,
            mcp_ops=mcp_ops_wrapper,
        )

        # ===== PHASE 4: Instantiate top-level managers =====
        self.config_operations = ConfigOperations(
            config_path=self.config_path,
            template_manager=self.template_manager,
            validation=self.validation_service,
            backup_manager=self.backup_manager,
            file_ops=self.file_ops,
            updaters=self.config_updaters,
        )

        logger.info("Successfully initialized all sub-managers")

    async def __aenter__(self) -> "SwagManagerService":
        """Async context manager entry - initialize resources."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit - cleanup resources."""
        # Close HTTP session in health monitor
        await self.health_monitor.close_session()

        # Cleanup file locks
        await self.file_ops.cleanup_file_locks()

        logger.info("Cleaned up SWAG manager resources")

    # ========================================================================
    # PUBLIC API METHODS - Delegate to sub-managers
    # ========================================================================

    # ----- Configuration Operations -----

    async def list_configs(self, list_filter: ListFilterType = "all") -> SwagListResult:
        """List configuration files based on type.

        Delegates to: ConfigOperations
        """
        return await self.config_operations.list_configs(list_filter)

    async def read_config(self, config_name: str) -> str:
        """Read configuration file content.

        Delegates to: ConfigOperations
        """
        return await self.config_operations.read_config(config_name)

    async def create_config(self, request: SwagConfigRequest) -> SwagConfigResult:
        """Create new configuration from template.

        Delegates to: ConfigOperations
        """
        return await self.config_operations.create_config(request)

    async def update_config(self, edit_request: SwagEditRequest) -> SwagConfigResult:
        """Update configuration with optional backup.

        Delegates to: ConfigOperations
        """
        return await self.config_operations.update_config(edit_request)

    async def update_config_field(self, update_request: SwagUpdateRequest) -> SwagConfigResult:
        """Update specific field in existing configuration.

        Delegates to: ConfigOperations which uses ConfigFieldUpdaters
        """
        return await self.config_operations.update_config_field(update_request)

    async def remove_config(self, remove_request: SwagRemoveRequest) -> SwagConfigResult:
        """Remove configuration with optional backup.

        Delegates to: ConfigOperations
        """
        return await self.config_operations.remove_config(remove_request)

    # ----- MCP Operations -----

    async def add_mcp_location(
        self, config_name: str, mcp_path: str = "/mcp", create_backup: bool = True
    ) -> SwagConfigResult:
        """Add MCP location block to existing SWAG configuration.

        Delegates to: MCPOperations
        """
        return await self.mcp_operations.add_mcp_location(config_name, mcp_path, create_backup)

    # ----- Health Check Operations -----

    async def health_check(self, request: SwagHealthCheckRequest) -> SwagHealthCheckResult:
        """Perform health check on a service endpoint.

        Delegates to: HealthMonitor
        """
        return await self.health_monitor.health_check(request)

    # ----- Log Operations -----

    async def get_swag_logs(self, logs_request: SwagLogsRequest) -> str:
        """Get SWAG logs by reading log files directly from mounted volume.

        Delegates to: HealthMonitor
        """
        return await self.health_monitor.get_swag_logs(logs_request)

    # ----- Resource Operations -----

    async def get_resource_configs(self) -> SwagResourceList:
        """Get list of active configuration files for resources.

        Delegates to: ResourceManager
        """
        return await self.resource_manager.get_resource_configs()

    async def get_sample_configs(self) -> SwagResourceList:
        """Get list of sample configuration files for resources.

        Delegates to: ResourceManager
        """
        return await self.resource_manager.get_sample_configs()

    async def get_service_samples(self, service_name: str) -> SwagResourceList:
        """Get sample configurations for a specific service.

        Delegates to: ResourceManager
        """
        return await self.resource_manager.get_service_samples(service_name)

    # ----- Backup Operations -----

    async def list_backups(self) -> list[dict[str, Any]]:
        """List all backup files with metadata.

        Delegates to: BackupManager
        """
        return await self.backup_manager.list_backups()

    async def cleanup_old_backups(self, retention_days: int | None = None) -> int:
        """Clean up old backup files beyond retention period.

        Delegates to: BackupManager
        """
        return await self.backup_manager.cleanup_old_backups(retention_days)

    # ----- Template Operations -----

    async def validate_template_exists(self, config_type: str) -> bool:
        """Validate that the required template exists.

        Delegates to: TemplateManager
        """
        return await self.template_manager.validate_template_exists(config_type)

    async def validate_all_templates(self) -> dict[str, bool]:
        """Validate that all required templates exist.

        Delegates to: TemplateManager
        """
        return await self.template_manager.validate_all_templates()

    # ----- File Operations (Exposed for transactions) -----

    def begin_transaction(self, transaction_id: str | None = None) -> Any:
        """Begin an atomic transaction for multi-file operations.

        Delegates to: FileOperations
        """
        return self.file_ops.begin_transaction(transaction_id)

    # ----- Template Hooks (For testing) -----

    def set_template_hooks(
        self,
        pre_render_hook: Any = None,
        post_render_hook: Any = None,
        template_vars_hook: Any = None,
    ) -> None:
        """Set testable hooks for template rendering.

        Delegates to: TemplateManager
        """
        self.template_manager.set_template_hooks(
            pre_render_hook, post_render_hook, template_vars_hook
        )

    def clear_template_hooks(self) -> None:
        """Clear all template rendering hooks.

        Delegates to: TemplateManager
        """
        self.template_manager.clear_template_hooks()

    # ========================================================================
    # INTERNAL METHOD PROXIES - For backwards compatibility with tests
    # ========================================================================

    # Expose attributes for tests
    @property
    def template_env(self):
        """Access template environment (for tests).

        Delegates to: TemplateManager
        """
        return self.template_manager.template_env

    @property
    def _file_locks(self):
        """Access file locks dict (for tests).

        Delegates to: FileOperations
        """
        return self.file_ops._file_locks

    @property
    def _file_locks_lock(self):
        """Access file locks lock (for tests).

        Delegates to: FileOperations
        """
        return self.file_ops._file_locks_lock

    @property
    def _backup_lock(self):
        """Access backup lock (for tests).

        Delegates to: BackupManager
        """
        return self.backup_manager._backup_lock

    @_backup_lock.setter
    def _backup_lock(self, value):
        """Set backup lock (for tests).

        Delegates to: BackupManager
        """
        self.backup_manager._backup_lock = value

    @property
    def _cleanup_lock(self):
        """Access cleanup lock (for tests).

        Delegates to: BackupManager
        """
        return self.backup_manager._cleanup_lock

    @_cleanup_lock.setter
    def _cleanup_lock(self, value):
        """Set cleanup lock (for tests).

        Delegates to: BackupManager
        """
        self.backup_manager._cleanup_lock = value

    @property
    def _http_session(self):
        """Access HTTP session (for tests).

        Delegates to: HealthMonitor
        """
        return self.health_monitor._http_session

    @property
    def _directory_checked(self):
        """Access directory checked flag (for tests).

        Delegates to: ConfigOperations
        """
        return self.config_operations._directory_checked

    # File operations proxies
    async def _safe_write_file(self, file_path, content, operation_name="file write", use_lock=True):
        """Proxy to FileOperations.safe_write_file (for tests)."""
        return await self.file_ops.safe_write_file(file_path, content, operation_name, use_lock)

    async def _get_file_lock(self, file_path):
        """Proxy to FileOperations.get_file_lock (for tests)."""
        return await self.file_ops.get_file_lock(file_path)

    async def _cleanup_file_locks(self):
        """Proxy to FileOperations.cleanup_file_locks (for tests)."""
        return await self.file_ops.cleanup_file_locks()

    def _ensure_config_directory(self):
        """Proxy to ConfigOperations._ensure_config_directory (for tests)."""
        return self.config_operations._ensure_config_directory()

    # Template operations proxies
    def _validate_template_variables(self, variables):
        """Proxy to TemplateManager.validate_template_variables (for tests)."""
        return self.template_manager.validate_template_variables(variables)

    async def _render_template(self, template_name, variables):
        """Proxy to TemplateManager.render_template (for tests)."""
        return await self.template_manager.render_template(template_name, variables)

    def _get_template_path(self):
        """Proxy to TemplateManager.get_template_path (for tests)."""
        return self.template_manager.get_template_path()

    def _create_secure_template_environment(self):
        """Proxy to TemplateManager._create_secure_template_environment (for tests)."""
        return self.template_manager._create_secure_template_environment()

    # Validation proxies
    def _validate_config_content(self, content, config_name):
        """Proxy to ValidationService.validate_config_content (for tests)."""
        return self.validation_service.validate_config_content(content, config_name)

    async def _validate_nginx_syntax(self, config_path):
        """Proxy to ValidationService.validate_nginx_syntax (for tests)."""
        return await self.validation_service.validate_nginx_syntax(config_path)

    # Backup operations proxies
    async def _create_backup(self, config_name):
        """Proxy to BackupManager.create_backup (for tests)."""
        return await self.backup_manager.create_backup(config_name)

    # MCP operations proxies
    def _extract_upstream_value(self, content, variable_name):
        """Proxy to MCPOperations.extract_upstream_value (for tests)."""
        return self.mcp_operations.extract_upstream_value(content, variable_name)

    def _extract_auth_method(self, content):
        """Proxy to MCPOperations.extract_auth_method (for tests)."""
        return self.mcp_operations.extract_auth_method(content)

    async def _render_mcp_location_block(self, mcp_path, upstream_app, upstream_port, upstream_proto, auth_method):
        """Proxy to MCPOperations.render_mcp_location_block (for tests)."""
        return await self.mcp_operations.render_mcp_location_block(
            mcp_path, upstream_app, upstream_port, upstream_proto, auth_method
        )

    def _insert_location_block(self, content, location_block):
        """Proxy to MCPOperations.insert_location_block (for tests)."""
        return self.mcp_operations.insert_location_block(content, location_block)

    # HTTP session proxies
    async def _get_session(self):
        """Proxy to HealthMonitor.get_session (for tests)."""
        return await self.health_monitor.get_session()

    async def _close_session(self):
        """Proxy to HealthMonitor.close_session (for tests)."""
        return await self.health_monitor.close_session()
