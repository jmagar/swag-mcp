# SwagManagerService Orchestrator Refactoring Plan

## Executive Summary

This document provides a complete, step-by-step plan to refactor `swag_manager.py` from a monolithic 2101-line service into a clean orchestrator pattern that delegates to 9 focused sub-managers.

## Current State Analysis

### Already Extracted (6 modules)
1. **FileOperations** (`file_operations.py`) - File I/O, transactions, locking
2. **TemplateManager** (`template_manager.py`) - Template rendering, security
3. **ValidationService** (`validation.py`) - Validation, diff/preview
4. **BackupManager** (`backup_manager.py`) - Backup operations
5. **HealthMonitor** (`health_monitor.py`) - Health checks, logs
6. **ResourceManager** (`resource_manager.py`) - Resource/sample queries

### To Be Extracted (3 new modules)
1. **MCPOperations** (`mcp_operations.py`) - MCP location operations
2. **ConfigFieldUpdaters** (`config_updaters.py`) - Field updaters (port/upstream/app/mcp)
3. **ConfigOperations** (`config_operations.py`) - CRUD operations

### Will Remain in SwagManagerService
- Orchestrator class with manager composition
- Public API methods that delegate to sub-managers
- Resource lifecycle management (`__aenter__`, `__aexit__`)
- Minimal coordination logic

---

## Dependency Graph

```
SwagManagerService (orchestrator)
├── FileOperations (no deps)
├── TemplateManager (no deps)
├── ValidationService (no deps)
├── BackupManager (deps: FileOperations)
├── HealthMonitor (no deps)
├── ResourceManager (no deps)
├── MCPOperations (deps: TemplateManager, ValidationService, FileOperations)
├── ConfigFieldUpdaters (deps: ValidationService, FileOperations, MCPOperations)
└── ConfigOperations (deps: TemplateManager, ValidationService, BackupManager, FileOperations, ConfigFieldUpdaters)
```

**Instantiation Order** (bottom-up):
1. FileOperations, TemplateManager, ValidationService, HealthMonitor, ResourceManager (no deps)
2. BackupManager (needs FileOperations)
3. MCPOperations (needs TemplateManager, ValidationService, FileOperations)
4. ConfigFieldUpdaters (needs ValidationService, FileOperations, MCPOperations)
5. ConfigOperations (needs TemplateManager, ValidationService, BackupManager, FileOperations, ConfigFieldUpdaters)

---

## Module 1: MCPOperations (`mcp_operations.py`)

### Responsibilities
- Add MCP location blocks to existing configurations
- Extract upstream values and auth methods from configs
- Render MCP location block templates
- Insert location blocks into nginx server blocks

### Code to Extract from swag_manager.py

**Lines to extract:**
- `add_mcp_location()` - lines 1923-2002
- `_extract_upstream_value()` - lines 2004-2013
- `_extract_auth_method()` - lines 2015-2041
- `_render_mcp_location_block()` - lines 2043-2071
- `_insert_location_block()` - lines 2073-2100

### Class Structure

```python
"""MCP operations module for SWAG MCP."""

import logging
import re
from pathlib import Path
from typing import Any, Literal

from swag_mcp.services.errors import ValidationError
from swag_mcp.utils.error_handlers import handle_os_error
from swag_mcp.utils.validators import validate_mcp_path

logger = logging.getLogger(__name__)


class MCPOperations:
    """Handles MCP location block operations."""

    def __init__(
        self,
        config_path: Path,
        template_manager: Any,  # TemplateManager
        validation_service: Any,  # ValidationService
        file_ops: Any,  # FileOperations
    ) -> None:
        """Initialize MCP operations.

        Args:
            config_path: Path to the configuration directory
            template_manager: TemplateManager instance for rendering templates
            validation_service: ValidationService instance for validation
            file_ops: FileOperations instance for file operations
        """
        self.config_path = config_path
        self.template_manager = template_manager
        self.validation_service = validation_service
        self.file_ops = file_ops

    async def add_mcp_location(
        self, config_name: str, mcp_path: str = "/mcp", create_backup: bool = True
    ) -> dict[str, Any]:
        """Add MCP location block to existing SWAG configuration."""
        # Implementation from lines 1923-2002
        pass

    def extract_upstream_value(self, content: str, variable_name: str) -> str:
        """Extract upstream variable value from nginx configuration content."""
        # Implementation from lines 2004-2013
        pass

    def extract_auth_method(self, content: str) -> str:
        """Extract authentication method from nginx configuration content."""
        # Implementation from lines 2015-2041
        pass

    async def render_mcp_location_block(
        self,
        mcp_path: str,
        upstream_app: str,
        upstream_port: str,
        upstream_proto: Literal["http", "https"],
        auth_method: str,
    ) -> str:
        """Render MCP location block template with provided variables."""
        # Implementation from lines 2043-2071
        pass

    def insert_location_block(self, content: str, location_block: str) -> str:
        """Insert location block before the closing brace of the outermost server block."""
        # Implementation from lines 2073-2100
        pass
```

---

## Module 2: ConfigFieldUpdaters (`config_updaters.py`)

### Responsibilities
- Update specific fields in configurations (port, upstream, app)
- Dispatch to field-specific updater methods
- Validate and finalize config updates
- Add MCP endpoints to existing configs

### Code to Extract from swag_manager.py

**Lines to extract:**
- `update_config_field()` - lines 1032-1060 (dispatcher)
- `_update_port_field()` - lines 1062-1125
- `_update_upstream_field()` - lines 1127-1186
- `_update_app_field()` - lines 1188-1273
- `_update_mcp_field()` - lines 1275-1299
- `_finalize_config_update()` - lines 1301-1373

### Class Structure

```python
"""Configuration field updaters module for SWAG MCP."""

import logging
import re
import tempfile
from pathlib import Path
from re import Match
from typing import Any

from swag_mcp.models.config import SwagConfigResult, SwagUpdateRequest
from swag_mcp.utils.error_codes import ErrorCode, create_operation_error, create_validation_error

logger = logging.getLogger(__name__)


class ConfigFieldUpdaters:
    """Handles field-specific configuration updates."""

    def __init__(
        self,
        config_path: Path,
        validation_service: Any,  # ValidationService
        file_ops: Any,  # FileOperations
        mcp_operations: Any,  # MCPOperations
    ) -> None:
        """Initialize config field updaters.

        Args:
            config_path: Path to the configuration directory
            validation_service: ValidationService instance for validation
            file_ops: FileOperations instance for file operations
            mcp_operations: MCPOperations instance for MCP operations
        """
        self.config_path = config_path
        self.validation_service = validation_service
        self.file_ops = file_ops
        self.mcp_operations = mcp_operations

    async def update_config_field(
        self, update_request: SwagUpdateRequest, content: str, backup_name: str | None
    ) -> SwagConfigResult:
        """Update specific field in existing configuration using targeted updaters."""
        # Implementation from lines 1032-1060
        pass

    async def update_port_field(
        self, update_request: SwagUpdateRequest, content: str, backup_name: str | None
    ) -> SwagConfigResult:
        """Update port field in configuration."""
        # Implementation from lines 1062-1125
        pass

    async def update_upstream_field(
        self, update_request: SwagUpdateRequest, content: str, backup_name: str | None
    ) -> SwagConfigResult:
        """Update upstream app field in configuration."""
        # Implementation from lines 1127-1186
        pass

    async def update_app_field(
        self, update_request: SwagUpdateRequest, content: str, backup_name: str | None
    ) -> SwagConfigResult:
        """Update both app and port field in configuration."""
        # Implementation from lines 1188-1273
        pass

    async def update_mcp_field(
        self, update_request: SwagUpdateRequest, content: str, backup_name: str | None
    ) -> SwagConfigResult:
        """Add MCP location block to configuration."""
        # Implementation from lines 1275-1299
        pass

    async def finalize_config_update(
        self,
        update_request: SwagUpdateRequest,
        updated_content: str,
        backup_name: str | None,
        changes_made: bool,
    ) -> SwagConfigResult:
        """Finalize configuration update with validation and file writing."""
        # Implementation from lines 1301-1373
        pass
```

---

## Module 3: ConfigOperations (`config_operations.py`)

### Responsibilities
- CRUD operations on configurations (create, read, update, delete, list)
- Coordinate with other managers for complex operations
- Manage configuration lifecycle

### Code to Extract from swag_manager.py

**Lines to extract:**
- `list_configs()` - lines 852-883
- `read_config()` - lines 885-927
- `create_config()` - lines 929-997
- `update_config()` - lines 999-1030
- `remove_config()` - lines 1485-1547

### Class Structure

```python
"""Configuration operations module for SWAG MCP."""

import errno
import logging
import re
from pathlib import Path
from typing import Any

import aiofiles

from swag_mcp.core.constants import LIST_FILTERS
from swag_mcp.models.config import (
    ListFilterType,
    SwagConfigRequest,
    SwagConfigResult,
    SwagEditRequest,
    SwagListResult,
    SwagRemoveRequest,
)
from swag_mcp.utils.error_handlers import handle_os_error
from swag_mcp.utils.validators import (
    detect_and_handle_encoding,
    validate_config_filename,
    validate_domain_format,
    validate_file_content_safety_async,
    validate_service_name,
    validate_upstream_port,
)

logger = logging.getLogger(__name__)


class ConfigOperations:
    """Handles CRUD operations on SWAG configurations."""

    def __init__(
        self,
        config_path: Path,
        template_manager: Any,  # TemplateManager
        validation_service: Any,  # ValidationService
        backup_manager: Any,  # BackupManager
        file_ops: Any,  # FileOperations
        config_updaters: Any,  # ConfigFieldUpdaters
    ) -> None:
        """Initialize config operations.

        Args:
            config_path: Path to the configuration directory
            template_manager: TemplateManager instance for rendering templates
            validation_service: ValidationService instance for validation
            backup_manager: BackupManager instance for backups
            file_ops: FileOperations instance for file operations
            config_updaters: ConfigFieldUpdaters instance for field updates
        """
        self.config_path = config_path
        self.template_manager = template_manager
        self.validation_service = validation_service
        self.backup_manager = backup_manager
        self.file_ops = file_ops
        self.config_updaters = config_updaters

    async def list_configs(self, list_filter: ListFilterType = "all") -> SwagListResult:
        """List configuration files based on type."""
        # Implementation from lines 852-883
        pass

    async def read_config(self, config_name: str) -> str:
        """Read configuration file content."""
        # Implementation from lines 885-927
        pass

    async def create_config(self, request: SwagConfigRequest) -> SwagConfigResult:
        """Create new configuration from template."""
        # Implementation from lines 929-997
        pass

    async def update_config(self, edit_request: SwagEditRequest) -> SwagConfigResult:
        """Update configuration with optional backup."""
        # Implementation from lines 999-1030
        pass

    async def remove_config(self, remove_request: SwagRemoveRequest) -> SwagConfigResult:
        """Remove configuration with optional backup."""
        # Implementation from lines 1485-1547
        pass
```

---

## Refactored SwagManagerService (Orchestrator)

### Complete Implementation

```python
"""Core SWAG configuration management service - Orchestrator."""

import asyncio
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
from swag_mcp.services.config_field_updaters import ConfigFieldUpdaters
from swag_mcp.services.config_operations import ConfigOperations
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
            validation_service=self.validation_service,
            file_ops=self.file_ops,
        )

        self.config_updaters = ConfigFieldUpdaters(
            config_path=self.config_path,
            validation_service=self.validation_service,
            file_ops=self.file_ops,
            mcp_operations=self.mcp_operations,
        )

        # ===== PHASE 4: Instantiate top-level managers =====
        self.config_operations = ConfigOperations(
            config_path=self.config_path,
            template_manager=self.template_manager,
            validation_service=self.validation_service,
            backup_manager=self.backup_manager,
            file_ops=self.file_ops,
            config_updaters=self.config_updaters,
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

        Delegates to: ConfigFieldUpdaters (via ConfigOperations read)
        """
        # Read existing config
        content = await self.config_operations.read_config(update_request.config_name)

        # Create backup if requested
        backup_name = None
        if update_request.create_backup:
            backup_name = await self.backup_manager.create_backup(update_request.config_name)

        # Delegate to config updaters
        return await self.config_updaters.update_config_field(
            update_request, content, backup_name
        )

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

    def begin_transaction(self, transaction_id: str | None = None):
        """Begin an atomic transaction for multi-file operations.

        Delegates to: FileOperations
        """
        return self.file_ops.begin_transaction(transaction_id)

    # ----- Template Hooks (For testing) -----

    def set_template_hooks(
        self,
        pre_render_hook=None,
        post_render_hook=None,
        template_vars_hook=None,
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
```

---

## Import Statements Required

Add these to the top of the refactored `swag_manager.py`:

```python
"""Core SWAG configuration management service - Orchestrator."""

import asyncio
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
from swag_mcp.services.config_field_updaters import ConfigFieldUpdaters
from swag_mcp.services.config_operations import ConfigOperations
from swag_mcp.services.file_operations import FileOperations
from swag_mcp.services.health_monitor import HealthMonitor
from swag_mcp.services.mcp_operations import MCPOperations
from swag_mcp.services.resource_manager import ResourceManager
from swag_mcp.services.template_manager import TemplateManager
from swag_mcp.services.validation import ValidationService

logger = logging.getLogger(__name__)
```

---

## Implementation Checklist

### Phase 1: Create New Modules
- [ ] Create `swag_mcp/services/mcp_operations.py`
  - [ ] Extract methods from swag_manager.py (lines 1923-2100)
  - [ ] Add proper imports and dependencies
  - [ ] Update method signatures to use `self.template_manager`, `self.validation_service`, `self.file_ops`
  - [ ] Write unit tests

- [ ] Create `swag_mcp/services/config_field_updaters.py`
  - [ ] Extract methods from swag_manager.py (lines 1032-1373)
  - [ ] Add proper imports and dependencies
  - [ ] Update method signatures to use `self.validation_service`, `self.file_ops`, `self.mcp_operations`
  - [ ] Write unit tests

- [ ] Create `swag_mcp/services/config_operations.py`
  - [ ] Extract methods from swag_manager.py (lines 852-997, 999-1030, 1485-1547)
  - [ ] Add proper imports and dependencies
  - [ ] Update method signatures to use all required managers
  - [ ] Write unit tests

### Phase 2: Update SwagManagerService
- [ ] Update `__init__()` to instantiate all 9 managers in correct dependency order
- [ ] Replace all method bodies with delegation calls
- [ ] Remove extracted code from swag_manager.py
- [ ] Update docstrings to indicate delegation
- [ ] Verify all public API methods are preserved

### Phase 3: Update Imports
- [ ] Update `swag_mcp/services/__init__.py` to export new modules
- [ ] Update any code that directly instantiates SwagManagerService
- [ ] Update tests to work with new structure

### Phase 4: Testing
- [ ] Run full test suite: `uv run pytest`
- [ ] Run integration tests: `uv run pytest tests/test_integration.py`
- [ ] Run performance tests: `uv run pytest tests/test_performance.py`
- [ ] Verify no regressions in functionality

### Phase 5: Documentation
- [ ] Update CLAUDE.md files for each module
- [ ] Update README.md if needed
- [ ] Add architecture diagram showing manager composition
- [ ] Document migration guide for anyone extending SwagManagerService

---

## Key Design Decisions

### 1. **Dependency Injection Pattern**
- All managers receive their dependencies in `__init__()`
- No circular dependencies between managers
- Bottom-up instantiation order ensures dependencies are ready

### 2. **Type Hints with `Any`**
- Using `Any` for manager types to avoid circular imports
- Alternative: Use `TYPE_CHECKING` and forward references (more complex)

### 3. **Public API Preservation**
- All existing public methods remain in SwagManagerService
- External code continues to work without changes
- Internal implementation is hidden from users

### 4. **Delegation Pattern**
- Each public method simply delegates to appropriate sub-manager
- Docstrings indicate which manager handles the operation
- Minimal coordination logic in orchestrator

### 5. **Resource Lifecycle**
- `__aenter__` and `__aexit__` coordinate resource cleanup
- HTTP session closed in HealthMonitor
- File locks cleaned up in FileOperations

---

## Benefits of Orchestrator Pattern

1. **Separation of Concerns**: Each manager has a single, well-defined responsibility
2. **Testability**: Managers can be tested in isolation with mocked dependencies
3. **Maintainability**: Changes to one area don't affect others
4. **Scalability**: Easy to add new managers or functionality
5. **Reusability**: Managers can be composed differently for different use cases
6. **Code Organization**: 200-line focused modules vs 2100-line monolith

---

## Migration Path

### For Developers Extending SwagManagerService

**Before (monolithic):**
```python
class SwagManagerService:
    async def my_new_method(self):
        # Directly access file operations, templates, etc.
        await self._safe_write_file(...)
```

**After (orchestrator):**
```python
class SwagManagerService:
    async def my_new_method(self):
        # Delegate to appropriate manager
        await self.file_ops.safe_write_file(...)

# OR create a new manager for your functionality:
class MyNewManager:
    def __init__(self, dependency1, dependency2):
        ...

    async def my_method(self):
        ...

# Add to SwagManagerService.__init__():
self.my_new_manager = MyNewManager(dep1, dep2)
```

---

## Appendix: Line-by-Line Extraction Map

### swag_manager.py Current Structure (2101 lines)

**Keep in SwagManagerService:**
- Lines 1-108: Imports, logger, class definition, `__init__()` ← **REFACTOR**
- Lines 109-142: Template hooks (delegate to TemplateManager)
- Lines 134-142: Context managers `__aenter__`, `__aexit__` ← **KEEP**

**Already Extracted:**
- Lines 143-244: File operations → `FileOperations`
- Lines 245-339: HTTP session, nginx validation → `HealthMonitor`, `ValidationService`
- Lines 340-481: AtomicTransaction → `FileOperations.AtomicTransaction`
- Lines 482-496: Transaction begin → `FileOperations.begin_transaction()`
- Lines 498-615: Template environment → `TemplateManager`
- Lines 617-701: Config content validation → `ValidationService`
- Lines 703-844: Safe write file → `FileOperations.safe_write_file()`
- Lines 846-851: Ensure config directory → `FileOperations.ensure_config_directory()`
- Lines 1375-1441: Create backup → `BackupManager.create_backup()`
- Lines 1443-1483: Validate templates → `TemplateManager`
- Lines 1549-1614: Get SWAG logs → `HealthMonitor.get_swag_logs()`
- Lines 1616-1663: Resource operations → `ResourceManager`
- Lines 1665-1805: Backup operations → `BackupManager`
- Lines 1807-1921: Health check → `HealthMonitor.health_check()`

**Extract to MCPOperations:**
- Lines 1923-2002: `add_mcp_location()`
- Lines 2004-2013: `_extract_upstream_value()`
- Lines 2015-2041: `_extract_auth_method()`
- Lines 2043-2071: `_render_mcp_location_block()`
- Lines 2073-2101: `_insert_location_block()`

**Extract to ConfigFieldUpdaters:**
- Lines 1032-1060: `update_config_field()` dispatcher
- Lines 1062-1125: `_update_port_field()`
- Lines 1127-1186: `_update_upstream_field()`
- Lines 1188-1273: `_update_app_field()`
- Lines 1275-1299: `_update_mcp_field()`
- Lines 1301-1373: `_finalize_config_update()`

**Extract to ConfigOperations:**
- Lines 852-883: `list_configs()`
- Lines 885-927: `read_config()`
- Lines 929-997: `create_config()`
- Lines 999-1030: `update_config()`
- Lines 1485-1547: `remove_config()`

---

## Expected Outcome

### Before Refactoring
- **swag_manager.py**: 2101 lines, single monolithic class
- **Complexity**: High - all concerns mixed together
- **Testing**: Difficult - requires full service for any test

### After Refactoring
- **swag_manager.py**: ~250 lines, orchestrator with delegation
- **mcp_operations.py**: ~180 lines, focused on MCP operations
- **config_field_updaters.py**: ~340 lines, focused on field updates
- **config_operations.py**: ~250 lines, focused on CRUD operations
- **Total**: 9 focused modules with clear boundaries
- **Complexity**: Low - single responsibility per module
- **Testing**: Easy - mock dependencies, test in isolation

---

## Questions & Clarifications

1. **Should we preserve private method names (_method_name)?**
   - Recommendation: Make all methods in sub-managers public (remove leading underscore)
   - Rationale: They're internal to the module, not exposed outside services package

2. **How to handle shared state (e.g., file locks)?**
   - Current approach: FileOperations owns all locks
   - Other managers request locks via `file_ops.get_file_lock()`
   - This centralizes concurrency control

3. **Error handling strategy?**
   - Keep existing error handling in sub-managers
   - Errors bubble up to orchestrator
   - Orchestrator doesn't add additional error handling (keep it thin)

4. **Performance impact?**
   - Negligible - method call overhead is minimal
   - Benefits of better code organization far outweigh tiny performance cost

5. **Backwards compatibility?**
   - Full backwards compatibility maintained
   - All public API methods remain in SwagManagerService
   - External code requires no changes

---

## Conclusion

This refactoring plan transforms `swag_manager.py` from a 2101-line monolith into a clean orchestrator that composes 9 focused sub-managers. The refactoring:

- **Maintains full backwards compatibility** - all public APIs preserved
- **Improves testability** - managers can be tested in isolation
- **Enhances maintainability** - clear separation of concerns
- **Enables scalability** - easy to add new functionality
- **Follows established patterns** - consistent with already-extracted modules

The dependency graph ensures clean, acyclic dependencies, and the bottom-up instantiation order guarantees all dependencies are available when needed.

**Estimated effort**: 2-3 days for implementation + testing + documentation
**Risk level**: Low - incremental changes with comprehensive test coverage
**Impact**: High - dramatically improves code quality and maintainability
