# SWAG MCP Services - Claude Memory Reference

This directory contains the business logic layer for SWAG MCP operations, primarily the `SwagManagerService` class that handles all SWAG configuration management.

## Directory Purpose

The `services/` module implements the core business logic for SWAG reverse proxy configuration management:
- File operations with atomic transactions and rollback support
- Template rendering with security safeguards (SSTI prevention)
- Health check operations with smart endpoint detection
- Backup management with automatic cleanup
- Unicode handling and encoding detection
- Per-file locking to prevent race conditions

## Key Files

### `swag_manager.py` - Core Service Implementation (1494 lines)
The main `SwagManagerService` class that provides all SWAG configuration operations:

```python
class SwagManagerService:
    """
    Core service for managing SWAG reverse proxy configurations.

    Features:
    - Atomic file operations with rollback
    - Sandboxed Jinja2 template rendering
    - Concurrent operations with per-file locking
    - Comprehensive error handling and validation
    - Health checks with multiple endpoint fallbacks
    """

    def __init__(self, config: SwagConfig):
        self.config = config
        self.template_env = self._setup_secure_template_env()
        self.file_locks = {}  # Per-file operation locking
        self.http_session = None  # Lazy-initialized for health checks
```

## Core Service Methods

### Configuration Management
```python
async def create_configuration(
    self,
    service_name: str,
    server_name: str,
    upstream_app: str,
    upstream_port: int,
    upstream_proto: str = "http",
    config_type: str = "subdomain",
    auth_method: str = "authelia",
    enable_quic: bool = False
) -> Dict[str, Any]:
    """
    Creates new SWAG configuration with atomic transaction support.

    Process:
    1. Validate inputs and resolve template
    2. Render template with security checks
    3. Write file atomically with backup
    4. Verify configuration syntax
    5. Rollback on any failure
    """
```

### File Operations
```python
async def list_configurations(self, config_type: str = "all") -> Dict[str, Any]:
    """List configurations with metadata and filtering"""

async def view_configuration(self, config_name: str) -> Dict[str, Any]:
    """Read configuration file content with encoding detection"""

async def edit_configuration(
    self,
    config_name: str,
    new_content: str,
    create_backup: bool = True
) -> Dict[str, Any]:
    """Edit configuration with atomic replacement and backup"""

async def update_configuration_field(
    self,
    config_name: str,
    field: str,
    value: str,
    create_backup: bool = True
) -> Dict[str, Any]:
    """Update specific field in configuration (port, upstream, app)"""

async def remove_configuration(
    self,
    config_name: str,
    create_backup: bool = True
) -> Dict[str, Any]:
    """Remove configuration with optional backup"""
```

### Health Check Operations
```python
async def check_service_health(
    self,
    domain: str,
    timeout: int = 30,
    follow_redirects: bool = True
) -> Dict[str, Any]:
    """
    Comprehensive health check with smart endpoint detection.

    Tries multiple endpoints in order:
    1. /health (standard health check)
    2. /mcp (MCP-specific endpoint)
    3. / (root endpoint)

    Features:
    - Connection pooling for performance
    - Detailed timing metrics
    - SSL/TLS validation
    - Redirect following with loop detection
    """
```

### Backup Management
```python
async def cleanup_backups(self, retention_days: int = None) -> Dict[str, Any]:
    """
    Clean up old backup files based on retention policy.

    Features:
    - Configurable retention period
    - Size-based cleanup reporting
    - Atomic cleanup operations
    - Detailed cleanup statistics
    """
```

### Log Access
```python
async def get_logs(
    self,
    log_type: str = "nginx-error",
    lines: int = 50
) -> Dict[str, Any]:
    """
    Access SWAG container logs with type filtering.

    Supported log types:
    - nginx-error: Nginx error logs
    - nginx-access: Nginx access logs
    - fail2ban: Fail2ban logs
    - letsencrypt: SSL certificate logs
    - renewal: Certificate renewal logs
    """
```

## Security Features

### Sandboxed Template Environment
```python
def _setup_secure_template_env(self) -> Environment:
    """
    Creates secure Jinja2 environment to prevent SSTI attacks.

    Security measures:
    - Restricted access to Python built-ins
    - Disabled dangerous functions (eval, exec, import)
    - File system access prevention
    - Attribute access limitations
    """
    loader = FileSystemLoader(self.config.template_path)
    env = Environment(
        loader=loader,
        autoescape=True,  # Prevent XSS
        undefined=StrictUndefined  # Fail on undefined variables
    )

    # Remove dangerous globals
    env.globals.pop('range', None)
    env.globals.pop('dict', None)
    env.globals.pop('list', None)

    return env
```

### File Safety Checks
```python
def _is_safe_text_file(self, file_path: Path) -> bool:
    """
    Validates file is safe text before operations.

    Checks:
    - File exists and is readable
    - Not a binary file
    - Reasonable size limits
    - Valid text encoding
    """
```

### Unicode Handling
```python
def _normalize_text_content(self, content: str) -> str:
    """
    Normalizes text content for safe processing.

    Features:
    - BOM removal (UTF-8, UTF-16, UTF-32)
    - Unicode normalization (NFC form)
    - Line ending normalization
    - Encoding validation
    """
```

## Atomic Transaction Pattern

### Transaction Context Manager
```python
class FileTransaction:
    """Context manager for atomic file operations with rollback"""

    def __init__(self, file_path: Path, create_backup: bool = True):
        self.file_path = file_path
        self.backup_path = None
        self.temp_path = None
        self.create_backup = create_backup

    async def __aenter__(self):
        # Create backup if requested
        if self.create_backup and self.file_path.exists():
            self.backup_path = self._create_backup()

        # Create temporary file for atomic write
        self.temp_path = self.file_path.with_suffix('.tmp')
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            # Success: atomic move
            self.temp_path.rename(self.file_path)
        else:
            # Failure: rollback and cleanup
            if self.temp_path.exists():
                self.temp_path.unlink()
            if self.backup_path and self.backup_path.exists():
                # Restore from backup
                self.backup_path.rename(self.file_path)
```

### Usage Example
```python
async def create_configuration(self, ...):
    config_path = self.config.proxy_confs_path / f"{service_name}.subdomain.conf"

    async with FileTransaction(config_path, create_backup=False) as tx:
        # Render template
        content = await self._render_template(template_name, template_vars)

        # Write to temporary file
        async with aiofiles.open(tx.temp_path, 'w', encoding='utf-8') as f:
            await f.write(content)

        # Validate syntax
        if not await self._validate_nginx_syntax(tx.temp_path):
            raise ConfigurationError("Invalid nginx syntax")

        # Transaction commits automatically on success
```

## Concurrency Management

### Per-File Locking
```python
async def _acquire_file_lock(self, file_path: Path) -> asyncio.Lock:
    """Get or create lock for specific file to prevent race conditions"""
    lock_key = str(file_path.resolve())
    if lock_key not in self.file_locks:
        self.file_locks[lock_key] = asyncio.Lock()
    return self.file_locks[lock_key]

async def _with_file_lock(self, file_path: Path, operation):
    """Execute operation with file-specific lock"""
    lock = await self._acquire_file_lock(file_path)
    async with lock:
        return await operation()
```

### Connection Pooling
```python
async def _get_http_session(self) -> aiohttp.ClientSession:
    """Lazy-initialized HTTP session with connection pooling"""
    if self.http_session is None:
        connector = aiohttp.TCPConnector(
            limit=10,  # Connection pool size
            ttl_dns_cache=300,  # DNS cache TTL
            use_dns_cache=True
        )
        timeout = aiohttp.ClientTimeout(total=30)
        self.http_session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout
        )
    return self.http_session
```

## Error Handling Patterns

### Service-Level Exceptions
```python
class SwagServiceError(Exception):
    """Base exception for service-level errors"""
    pass

class ConfigurationNotFoundError(SwagServiceError):
    """Configuration file not found"""
    pass

class TemplateRenderError(SwagServiceError):
    """Template rendering failed"""
    pass

class ValidationError(SwagServiceError):
    """Configuration validation failed"""
    pass
```

### Error Context Enrichment
```python
async def create_configuration(self, ...):
    try:
        # ... implementation
    except TemplateNotFound as e:
        raise TemplateRenderError(
            f"Template '{template_name}' not found. "
            f"Available templates: {await self._list_available_templates()}"
        ) from e
    except UnicodeDecodeError as e:
        raise ValidationError(
            f"Invalid character encoding in content: {e}"
        ) from e
```

## Development Commands

### Service Testing
```bash
# Test service operations
uv run pytest tests/test_swag_actions.py::TestSwagManagerService -v

# Test specific service methods
uv run pytest tests/test_swag_actions.py -k "test_create_configuration" -v

# Test error handling
uv run pytest tests/test_error_handling.py::TestServiceErrors -v
```

### Manual Service Testing
```bash
# Test service instantiation
python -c "
from swag_mcp.core.config import SwagConfig
from swag_mcp.services.swag_manager import SwagManagerService
config = SwagConfig()
service = SwagManagerService(config)
print('Service created successfully')
"

# Test template rendering
python -c "
import asyncio
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.core.config import SwagConfig

async def test():
    service = SwagManagerService(SwagConfig())
    templates = await service._list_available_templates()
    print('Available templates:', templates)

asyncio.run(test())
"
```

## Performance Optimization

### Template Caching
- Jinja2 templates are compiled once and cached
- Template environment initialized at service creation
- Template loading is synchronous but cached for reuse

### File I/O Optimization
- All file operations use `aiofiles` for async I/O
- Batch operations where possible
- Memory-mapped file reading for large files
- Streaming writes for large configuration files

### Health Check Optimization
- Connection pooling reduces connection overhead
- DNS caching prevents repeated lookups
- Timeout management prevents hanging requests
- Parallel health checks for multiple domains

## Important Notes

### Service Lifecycle
- Service instances should be created per-request or operation
- HTTP session is lazy-initialized and reused
- File locks are maintained per service instance
- Cleanup required for long-running services

### Configuration Dependencies
- Service requires valid `SwagConfig` with accessible paths
- Template directory must exist with valid templates
- Proxy configurations directory must be writable
- Log directory must be accessible for cleanup operations

### Thread Safety
- Service is async-safe but not thread-safe
- File locks prevent concurrent access to same files
- HTTP session can be shared safely across async operations
- Template environment is read-only after initialization

### Memory Management
- Large configuration files are streamed, not loaded into memory
- Template rendering uses streaming where possible
- Health check responses are limited in size
- Backup files are cleaned up automatically based on retention policy
