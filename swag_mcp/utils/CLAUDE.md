# SWAG MCP Utilities - Claude Memory Reference

This directory contains utility functions and helpers that provide common functionality across the SWAG MCP application, including validation, error handling, formatting, and tool decorators.

## Directory Purpose

The `utils/` module provides shared utility functions for:
- Input validation with security-focused patterns
- OS error handling with user-friendly messages
- Response formatting and template filename building
- Tool decorators for error handling and logging
- Unicode text processing and normalization
- File safety checks and encoding detection

## Key Files

### `validators.py` - Input Validation Functions
Comprehensive validation functions used throughout the application:

```python
import re
import ipaddress
from pathlib import Path
from urllib.parse import urlparse

def validate_domain_format(domain: str) -> bool:
    """
    Validate domain name format according to RFC standards.

    Features:
    - RFC 1123 compliant hostname validation
    - Internationalized Domain Name (IDN) support
    - Length limits per RFC (253 chars total, 63 per label)
    - Prevents common domain spoofing attempts
    """
    if not domain or len(domain) > 253:
        return False

    # Remove trailing dot if present
    if domain.endswith('.'):
        domain = domain[:-1]

    # Check each label
    labels = domain.split('.')
    for label in labels:
        if not label or len(label) > 63:
            return False
        if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$', label):
            return False

    return True

def validate_service_name(service_name: str) -> bool:
    """
    Validate service name for file safety and convention compliance.

    Security checks:
    - Path traversal prevention (no .. or /)
    - Shell injection prevention (alphanumeric, dash, underscore only)
    - Leading/trailing dash prevention
    - Empty string prevention
    """
    if not service_name:
        return False

    # Path traversal protection
    if '..' in service_name or '/' in service_name:
        return False

    # Character whitelist
    if not re.match(r'^[a-zA-Z0-9_-]+$', service_name):
        return False

    # Prevent leading/trailing dashes (invalid for some contexts)
    if service_name.startswith('-') or service_name.endswith('-'):
        return False

    return True

def validate_port_range(port: int) -> bool:
    """Validate port number is in valid range (1-65535)"""
    return isinstance(port, int) and 1 <= port <= 65535

def validate_upstream_app(upstream_app: str) -> bool:
    """
    Validate upstream application identifier.

    Accepts:
    - Container names (alphanumeric, dash, underscore, dot)
    - IPv4 addresses
    - IPv6 addresses (bracketed or unbracketed)
    - Hostnames and FQDNs
    """
    if not upstream_app:
        return False

    # Try IPv4 address
    try:
        ipaddress.IPv4Address(upstream_app)
        return True
    except ValueError:
        pass

    # Try IPv6 address (with or without brackets)
    try:
        addr = upstream_app.strip('[]')
        ipaddress.IPv6Address(addr)
        return True
    except ValueError:
        pass

    # Container name or hostname validation
    if re.match(r'^[a-zA-Z0-9._-]+$', upstream_app):
        return True

    return False

def validate_file_path_safety(file_path: str) -> bool:
    """
    Validate file path for security.

    Prevents:
    - Path traversal attacks (../, .\, etc.)
    - Absolute path access outside configured directories
    - Hidden file access (files starting with .)
    - Windows reserved names (CON, PRN, etc.)
    """
    if not file_path:
        return False

    # Path traversal protection
    if '..' in file_path or file_path.startswith('/'):
        return False

    # Hidden file protection
    path_parts = Path(file_path).parts
    for part in path_parts:
        if part.startswith('.'):
            return False

    # Windows reserved names
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }

    for part in path_parts:
        if part.upper() in reserved_names:
            return False

    return True
```

### `error_handlers.py` - OS Error Mapping
Converts system-level errors to user-friendly messages:

```python
import errno
import os
from pathlib import Path

def handle_os_error(error: OSError) -> str:
    """
    Convert OS errors to user-friendly messages with actionable advice.

    Handles common scenarios:
    - File not found with suggested locations
    - Permission denied with chmod advice
    - Disk full with cleanup suggestions
    - Network errors with connectivity advice
    """
    error_code = error.errno
    filename = getattr(error, 'filename', 'unknown file')

    if error_code == errno.ENOENT:
        # File not found
        return f"File '{filename}' not found. Check the path and ensure the file exists."

    elif error_code == errno.EACCES:
        # Permission denied
        return f"Permission denied accessing '{filename}'. Check file permissions and Docker volume mounts."

    elif error_code == errno.ENOSPC:
        # No space left on device
        return f"Disk full when accessing '{filename}'. Free up space and try again."

    elif error_code == errno.EMFILE:
        # Too many open files
        return f"Too many open files. Close unused files or increase system limits."

    elif error_code == errno.EISDIR:
        # Is a directory
        return f"'{filename}' is a directory, not a file."

    elif error_code == errno.ENOTDIR:
        # Not a directory
        return f"'{filename}' is not a directory."

    elif error_code in (errno.ETIMEDOUT, errno.ECONNREFUSED):
        # Network errors
        return f"Network error accessing '{filename}'. Check connectivity and service availability."

    else:
        # Generic OS error with errno
        return f"System error ({error_code}): {str(error)}"

def get_file_safety_info(file_path: Path) -> dict:
    """
    Get comprehensive file safety and accessibility information.

    Returns detailed info for debugging:
    - File existence and type
    - Permissions (read, write, execute)
    - Size and modification time
    - Parent directory accessibility
    - Potential issues and recommendations
    """
    info = {
        'path': str(file_path),
        'exists': file_path.exists(),
        'is_file': False,
        'is_dir': False,
        'readable': False,
        'writable': False,
        'size_bytes': 0,
        'issues': []
    }

    if file_path.exists():
        info['is_file'] = file_path.is_file()
        info['is_dir'] = file_path.is_dir()

        try:
            info['readable'] = os.access(file_path, os.R_OK)
            info['writable'] = os.access(file_path, os.W_OK)

            if info['is_file']:
                info['size_bytes'] = file_path.stat().st_size

        except OSError as e:
            info['issues'].append(f"Permission check failed: {handle_os_error(e)}")

    else:
        # Check parent directory
        parent = file_path.parent
        if parent.exists():
            try:
                parent_writable = os.access(parent, os.W_OK)
                if not parent_writable:
                    info['issues'].append("Parent directory is not writable")
            except OSError as e:
                info['issues'].append(f"Parent directory check failed: {handle_os_error(e)}")
        else:
            info['issues'].append("Parent directory does not exist")

    return info
```

### `formatters.py` - Response and Output Formatting
Functions for consistent response formatting and template filename building:

```python
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format"""
    if size_bytes == 0:
        return "0 B"

    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    size = float(size_bytes)

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.1f} {units[unit_index]}"

def format_timestamp(timestamp: datetime) -> str:
    """Format timestamp for user display"""
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")

def format_duration(milliseconds: float) -> str:
    """Format duration in human-readable format"""
    if milliseconds < 1000:
        return f"{milliseconds:.1f}ms"
    elif milliseconds < 60000:
        return f"{milliseconds/1000:.1f}s"
    else:
        minutes = int(milliseconds // 60000)
        seconds = (milliseconds % 60000) / 1000
        return f"{minutes}m {seconds:.1f}s"

def build_template_filename(service_name: str, config_type: str) -> str:
    """
    Build template filename from service name and configuration type.

    Template naming convention:
    - subdomain: service.subdomain.conf
    - subfolder: service.subfolder.conf
    - mcp-subdomain: service.mcp-subdomain.conf
    - mcp-subfolder: service.mcp-subfolder.conf
    """
    valid_config_types = ["subdomain", "subfolder", "mcp-subdomain", "mcp-subfolder"]

    if config_type not in valid_config_types:
        raise ValueError(f"Invalid config type. Must be one of: {valid_config_types}")

    return f"{service_name}.{config_type}.conf"

def format_health_check_result(result: Dict[str, Any]) -> str:
    """Format health check results for user display"""
    data = result.get('data', {})
    domain = data.get('domain', 'unknown')
    accessible = data.get('accessible', False)

    if accessible:
        status_code = data.get('status_code', 'unknown')
        response_time = data.get('response_time_ms', 0)

        status = f"✅ {domain} is accessible"
        status += f" (HTTP {status_code}, {format_duration(response_time)})"

        redirect_url = data.get('redirect_url')
        if redirect_url and redirect_url != f"https://{domain}":
            status += f" → {redirect_url}"

        return status
    else:
        error_msg = data.get('error_message', 'Unknown error')
        return f"❌ {domain} is not accessible: {error_msg}"

def format_config_list(configs: List[Dict[str, Any]], total_count: int) -> str:
    """Format configuration list for user display"""
    if not configs:
        return "No configurations found."

    lines = [f"Found {total_count} configurations:"]

    for config in configs:
        name = config.get('name', 'unknown')
        size = format_file_size(config.get('size_bytes', 0))
        modified = config.get('modified_time', 'unknown')
        is_sample = config.get('is_sample', False)

        status = "📄" if not is_sample else "📝"
        lines.append(f"  {status} {name} ({size}, modified {modified})")

    return "\n".join(lines)
```

### `tool_decorators.py` - Function Decorators for Tools
Decorators that add cross-cutting functionality to tool functions:

```python
import functools
import logging
import time
from typing import Any, Callable

def with_error_handling(func: Callable) -> Callable:
    """
    Decorator that adds comprehensive error handling to tool functions.

    Features:
    - Catches and logs all exceptions
    - Provides user-friendly error messages
    - Maintains original function signature
    - Preserves function metadata
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger = logging.getLogger(func.__module__)
            logger.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
            return f"Error in {func.__name__}: {str(e)}"

    return wrapper

def with_timing(func: Callable) -> Callable:
    """
    Decorator that adds timing measurement to tool functions.

    Features:
    - Measures execution time
    - Logs performance information
    - Detects slow operations
    - Adds timing to function context
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        logger = logging.getLogger(func.__module__)

        try:
            result = await func(*args, **kwargs)
            execution_time = (time.time() - start_time) * 1000

            if execution_time > 1000:  # Slow operation threshold
                logger.warning(f"{func.__name__} took {execution_time:.1f}ms")
            else:
                logger.debug(f"{func.__name__} completed in {execution_time:.1f}ms")

            return result

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"{func.__name__} failed after {execution_time:.1f}ms: {str(e)}")
            raise

    return wrapper

def with_validation(schema_class: Any) -> Callable:
    """
    Decorator that adds Pydantic model validation to tool functions.

    Features:
    - Validates function parameters against Pydantic model
    - Provides detailed validation error messages
    - Handles both sync and async functions
    - Preserves original function behavior on success
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                # Validate parameters using Pydantic model
                validated_params = schema_class(**kwargs)

                # Call original function with validated parameters
                return await func(*args, **validated_params.model_dump())

            except ValidationError as e:
                error_details = []
                for err in e.errors():
                    field = ".".join(str(loc) for loc in err['loc'])
                    error_details.append(f"{field}: {err['msg']}")

                return f"Parameter validation failed: {'; '.join(error_details)}"

        return wrapper
    return decorator
```

### `tool_helpers.py` - Response Building Utilities
Helper functions for building consistent tool responses:

```python
from typing import Any, Dict, List, Optional

def build_success_response(
    message: str,
    data: Optional[Dict[str, Any]] = None,
    include_metadata: bool = True
) -> str:
    """
    Build standardized success response for tool functions.

    Features:
    - Consistent success message format
    - Optional data inclusion
    - Metadata like timestamps and operation info
    - User-friendly formatting
    """
    response_parts = [message]

    if data and include_metadata:
        if 'total_count' in data:
            response_parts.append(f"({data['total_count']} items)")

        if 'backup_created' in data and data['backup_created']:
            response_parts.append("(Backup created)")

        if 'processing_time_ms' in data:
            duration = format_duration(data['processing_time_ms'])
            response_parts.append(f"(Completed in {duration})")

    return " ".join(response_parts)

def build_error_response(
    error_message: str,
    error_type: str = "Error",
    suggestions: Optional[List[str]] = None
) -> str:
    """
    Build standardized error response with helpful suggestions.

    Features:
    - Consistent error message format
    - Error type classification
    - Actionable suggestions for resolution
    - User-friendly language
    """
    response = f"{error_type}: {error_message}"

    if suggestions:
        response += "\n\nSuggestions:"
        for suggestion in suggestions:
            response += f"\n  • {suggestion}"

    return response

def build_validation_error_response(validation_errors: List[Dict]) -> str:
    """Build user-friendly validation error response"""
    error_details = []
    suggestions = []

    for err in validation_errors:
        field = ".".join(str(loc) for loc in err['loc'])
        msg = err['msg']
        error_details.append(f"{field}: {msg}")

        # Add field-specific suggestions
        if 'port' in field:
            suggestions.append("Port numbers must be between 1 and 65535")
        elif 'domain' in field or 'server_name' in field:
            suggestions.append("Domain names must be valid hostnames (e.g., example.com)")
        elif 'service_name' in field:
            suggestions.append("Service names can only contain letters, numbers, dashes, and underscores")

    error_msg = "; ".join(error_details)
    return build_error_response(error_msg, "Validation Error", list(set(suggestions)))

def extract_action_parameters(kwargs: Dict[str, Any], required_fields: List[str]) -> Dict[str, Any]:
    """
    Extract and validate required parameters for tool actions.

    Features:
    - Checks for missing required fields
    - Filters out empty/None values
    - Provides helpful error messages
    - Returns clean parameter dictionary
    """
    missing_fields = []
    extracted = {}

    for field in required_fields:
        value = kwargs.get(field)
        if value is None or value == "" or value == 0:
            missing_fields.append(field)
        else:
            extracted[field] = value

    if missing_fields:
        raise ValueError(f"Missing required parameters: {', '.join(missing_fields)}")

    return extracted
```

## Validation Patterns

### Security-First Validation
All validators prioritize security:

```python
# Path traversal prevention
if '..' in path or path.startswith('/'):
    return False

# Command injection prevention
if not re.match(r'^[a-zA-Z0-9_-]+$', name):
    return False

# Hidden file protection
if any(part.startswith('.') for part in path.parts):
    return False
```

### Unicode Normalization
```python
def normalize_unicode_text(text: str) -> str:
    """Normalize Unicode text for consistent processing"""
    import unicodedata

    # Remove BOM if present
    if text.startswith('\ufeff'):
        text = text[1:]

    # Normalize to NFC form
    return unicodedata.normalize('NFC', text)
```

## Error Message Guidelines

### User-Friendly Error Messages
- **Specific**: "Port 99999 is invalid" vs "Invalid port"
- **Actionable**: Include what to do next
- **Context-aware**: Reference the specific operation
- **Safe**: Don't expose internal paths or system details

### Error Classification
```python
# User errors (validation, parameters)
"Parameter validation failed: port must be 1-65535"

# System errors (permissions, files)
"Permission denied: check file permissions and Docker mounts"

# Service errors (business logic)
"Configuration error: template 'invalid' not found"

# Unexpected errors (bugs)
"Unexpected error occurred. Check server logs for details."
```

## Development Commands

### Utility Testing
```bash
# Test validation functions
uv run pytest tests/test_validation.py::TestValidators -v

# Test error handling
uv run pytest tests/test_error_handling.py::TestUtilityErrors -v

# Test formatting functions
python -c "
from swag_mcp.utils.formatters import format_file_size, format_duration
print(format_file_size(1536))  # 1.5 KB
print(format_duration(1500))   # 1.5s
"
```

### Manual Utility Testing
```bash
# Test domain validation
python -c "
from swag_mcp.utils.validators import validate_domain_format
print(validate_domain_format('example.com'))      # True
print(validate_domain_format('invalid..com'))     # False
print(validate_domain_format('.example.com'))     # False
"

# Test error handling
python -c "
import errno
from swag_mcp.utils.error_handlers import handle_os_error

error = OSError(errno.ENOENT, 'No such file', '/nonexistent/file')
print(handle_os_error(error))
"
```

## Important Notes

### Validation Philosophy
- **Security first**: All input validation prevents common attack vectors
- **User-friendly**: Clear error messages with actionable advice
- **Comprehensive**: Cover edge cases and malformed input
- **Performance-aware**: Efficient patterns and minimal overhead

### Error Handling Strategy
- **Contextual**: Errors include relevant context and suggestions
- **Classified**: Different error types handled appropriately
- **Safe**: No sensitive information exposed in error messages
- **Logged**: All errors logged with appropriate detail level

### Unicode and Encoding
- **Normalization**: All text normalized to NFC form
- **BOM handling**: UTF-8 BOM removed automatically
- **Encoding detection**: Automatic detection and conversion
- **Safety checks**: Binary file detection and prevention

### Performance Considerations
- **Efficient patterns**: Regex patterns compiled once
- **Minimal allocations**: Avoid unnecessary string operations
- **Caching**: Validation results cached where appropriate
- **Early returns**: Fail fast on obviously invalid input
