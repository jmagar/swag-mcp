# SWAG MCP Middleware - Claude Memory Reference

This directory contains the middleware stack that processes all MCP requests and responses, providing cross-cutting concerns like error handling, timing, rate limiting, and logging.

## Directory Purpose

The `middleware/` module implements a comprehensive request processing pipeline:
- Global error handling with user-friendly error messages
- Performance timing with slow operation warnings
- Token bucket rate limiting for abuse prevention
- Detailed request/response logging with optional payload capture
- Proper middleware ordering and configuration

## Key Files

### `__init__.py` - Middleware Setup Function
Centralizes middleware registration and ordering:

```python
from fastmcp import FastMCP
from .error_handling import error_handling_middleware
from .timing import timing_middleware
from .rate_limiting import rate_limiting_middleware
from .request_logging import request_logging_middleware

def setup_middleware(app: FastMCP) -> None:
    """
    Setup middleware stack in correct order.

    Middleware order is critical:
    1. Error handling (outermost - catches everything)
    2. Timing (measures total request time)
    3. Rate limiting (before processing heavy operations)
    4. Request logging (innermost - detailed logging)
    """
    app.add_middleware(error_handling_middleware)
    app.add_middleware(timing_middleware)
    app.add_middleware(rate_limiting_middleware)
    app.add_middleware(request_logging_middleware)
```

### `error_handling.py` - Global Exception Handling
Catches all unhandled exceptions and converts them to user-friendly responses:

```python
from fastmcp.middleware import middleware
from swag_mcp.utils.error_handlers import handle_os_error
from pydantic import ValidationError
import logging

@middleware
async def error_handling_middleware(ctx, call_next):
    """
    Global error handling middleware.

    Catches and processes:
    - Pydantic ValidationError -> Parameter validation messages
    - OSError/FileNotFoundError -> File system error messages
    - PermissionError -> Permission and access messages
    - TimeoutError -> Timeout and performance messages
    - Generic Exception -> Safe error messages with logging
    """
    try:
        return await call_next(ctx)

    except ValidationError as e:
        # Parameter validation errors
        error_details = []
        for err in e.errors():
            field = ".".join(str(loc) for loc in err['loc'])
            error_details.append(f"{field}: {err['msg']}")

        error_msg = f"Parameter validation failed: {'; '.join(error_details)}"
        logger.warning(f"Validation error: {error_msg}")
        return error_msg

    except FileNotFoundError as e:
        # File system errors with helpful context
        error_msg = f"File not found: {handle_os_error(e)}"
        logger.error(f"File system error: {error_msg}")
        return error_msg

    except PermissionError as e:
        # Permission errors with actionable advice
        error_msg = f"Permission denied: {handle_os_error(e)}. Check file permissions and Docker volume mounts."
        logger.error(f"Permission error: {error_msg}")
        return error_msg

    except TimeoutError as e:
        # Timeout errors with performance advice
        error_msg = f"Operation timed out: {str(e)}. Try increasing timeout or check network connectivity."
        logger.error(f"Timeout error: {error_msg}")
        return error_msg

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return f"An unexpected error occurred: {str(e)}. Check server logs for details."
```

### `timing.py` - Performance Monitoring
Tracks request processing time and warns about slow operations:

```python
import time
import logging
from fastmcp.middleware import middleware
from swag_mcp.core.config import SwagConfig

@middleware
async def timing_middleware(ctx, call_next):
    """
    Performance timing middleware.

    Features:
    - Measures total request processing time
    - Warns about slow operations based on configuration
    - Logs performance metrics for monitoring
    - Adds timing context to request context
    """
    start_time = time.time()

    try:
        # Execute request with timing context
        ctx.start_time = start_time
        result = await call_next(ctx)

        # Calculate processing time
        end_time = time.time()
        processing_time_ms = (end_time - start_time) * 1000

        # Log timing information
        config = getattr(ctx, 'config', SwagConfig())
        threshold = config.slow_operation_threshold_ms

        if processing_time_ms > threshold:
            logger.warning(
                f"Slow operation detected: {processing_time_ms:.1f}ms "
                f"(threshold: {threshold}ms)"
            )
        else:
            logger.info(f"Request completed in {processing_time_ms:.1f}ms")

        return result

    except Exception as e:
        # Log timing even for failed requests
        end_time = time.time()
        processing_time_ms = (end_time - start_time) * 1000
        logger.error(f"Request failed after {processing_time_ms:.1f}ms: {str(e)}")
        raise
```

### `rate_limiting.py` - Request Throttling
Implements token bucket rate limiting to prevent abuse:

```python
import time
import asyncio
from typing import Dict
from fastmcp.middleware import middleware
from swag_mcp.core.config import SwagConfig

class TokenBucket:
    """
    Token bucket implementation for rate limiting.

    Features:
    - Configurable fill rate and burst capacity
    - Thread-safe token consumption
    - Automatic token replenishment
    - Per-client rate limiting support
    """

    def __init__(self, rate: float, burst: int):
        self.rate = rate  # Tokens per second
        self.burst = burst  # Maximum tokens
        self.tokens = float(burst)  # Current tokens
        self.last_update = time.time()
        self.lock = asyncio.Lock()

    async def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens, return True if successful"""
        async with self.lock:
            now = time.time()
            # Add tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_update = now

            # Check if enough tokens available
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

# Global rate limiter instance
_rate_limiters: Dict[str, TokenBucket] = {}

@middleware
async def rate_limiting_middleware(ctx, call_next):
    """
    Rate limiting middleware using token bucket algorithm.

    Features:
    - Configurable rate limits per client
    - Burst capacity for short spikes
    - Per-IP rate limiting (when available)
    - Graceful degradation when limits exceeded
    """
    config = getattr(ctx, 'config', SwagConfig())

    if not config.rate_limit_enabled:
        return await call_next(ctx)

    # Get client identifier (IP or generic)
    client_id = getattr(ctx, 'client_ip', 'default')

    # Get or create rate limiter for client
    if client_id not in _rate_limiters:
        _rate_limiters[client_id] = TokenBucket(
            rate=config.rate_limit_rps,
            burst=config.rate_limit_burst
        )

    limiter = _rate_limiters[client_id]

    # Try to consume a token
    if await limiter.consume():
        return await call_next(ctx)
    else:
        logger.warning(f"Rate limit exceeded for client {client_id}")
        return "Rate limit exceeded. Please slow down your requests."
```

### `request_logging.py` - Detailed Request Logging
Provides comprehensive logging of requests and responses:

```python
import json
import logging
from typing import Any, Dict
from fastmcp.middleware import middleware
from swag_mcp.core.config import SwagConfig

@middleware
async def request_logging_middleware(ctx, call_next):
    """
    Request/response logging middleware.

    Features:
    - Structured request logging
    - Optional payload logging (configurable)
    - Sensitive data redaction
    - Performance-aware logging levels
    - JSON structured logging support
    """
    config = getattr(ctx, 'config', SwagConfig())

    # Extract request information
    request_info = {
        'request_id': getattr(ctx, 'request_id', 'unknown'),
        'tool_name': getattr(ctx, 'tool_name', 'unknown'),
        'action': getattr(ctx, 'action', 'unknown'),
        'client_ip': getattr(ctx, 'client_ip', 'unknown'),
        'timestamp': time.time()
    }

    # Log request with optional payload
    if config.log_payloads:
        # Redact sensitive parameters
        safe_params = _redact_sensitive_data(getattr(ctx, 'parameters', {}))
        if len(str(safe_params)) <= config.log_payload_max_length:
            request_info['parameters'] = safe_params
        else:
            request_info['parameters'] = '[TRUNCATED - TOO LARGE]'

    logger.info(f"Request started: {json.dumps(request_info)}")

    try:
        # Process request
        result = await call_next(ctx)

        # Log successful response
        response_info = {
            'request_id': request_info['request_id'],
            'success': True,
            'processing_time_ms': getattr(ctx, 'processing_time_ms', 0)
        }

        if config.log_payloads and len(str(result)) <= config.log_payload_max_length:
            response_info['result'] = result

        logger.info(f"Request completed: {json.dumps(response_info)}")
        return result

    except Exception as e:
        # Log failed response
        error_info = {
            'request_id': request_info['request_id'],
            'success': False,
            'error_type': type(e).__name__,
            'error_message': str(e),
            'processing_time_ms': getattr(ctx, 'processing_time_ms', 0)
        }

        logger.error(f"Request failed: {json.dumps(error_info)}")
        raise

def _redact_sensitive_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Redact sensitive information from request parameters"""
    sensitive_fields = ['password', 'token', 'key', 'secret', 'auth']

    redacted = data.copy()
    for key, value in data.items():
        if any(sensitive in key.lower() for sensitive in sensitive_fields):
            redacted[key] = '[REDACTED]'

    return redacted
```

## Middleware Configuration

### Environment Variables
Middleware behavior is controlled through configuration:

```bash
# Performance monitoring
SWAG_MCP_SLOW_OPERATION_THRESHOLD_MS=1000

# Rate limiting
SWAG_MCP_RATE_LIMIT_ENABLED=false
SWAG_MCP_RATE_LIMIT_RPS=10.0
SWAG_MCP_RATE_LIMIT_BURST=20

# Request logging
SWAG_MCP_LOG_PAYLOADS=false
SWAG_MCP_LOG_PAYLOAD_MAX_LENGTH=1000
SWAG_MCP_ENABLE_STRUCTURED_LOGGING=false
```

### Middleware Ordering
The order of middleware registration is critical for proper operation:

```python
# Correct order (outermost to innermost):
1. error_handling_middleware    # Catches all exceptions
2. timing_middleware           # Measures total time including error handling
3. rate_limiting_middleware    # Prevents abuse before heavy processing
4. request_logging_middleware  # Logs detailed request information
```

## Error Handling Patterns

### Exception Classification
```python
# Parameter validation (user error)
except ValidationError as e:
    return f"Parameter validation failed: {format_validation_errors(e)}"

# System errors (configuration/environment)
except (OSError, PermissionError) as e:
    return f"System error: {handle_os_error(e)}"

# Timeout errors (performance/network)
except TimeoutError as e:
    return f"Operation timed out: {str(e)}. Try increasing timeout."

# Service errors (business logic)
except SwagServiceError as e:
    return f"Configuration error: {str(e)}"

# Unexpected errors (bugs)
except Exception as e:
    logger.error(f"Unexpected error: {str(e)}", exc_info=True)
    return f"An unexpected error occurred. Check server logs."
```

### Error Message Guidelines
- **User-friendly**: Avoid technical jargon
- **Actionable**: Provide next steps when possible
- **Context-aware**: Include relevant details
- **Security-conscious**: Don't expose internal paths or secrets

## Performance Monitoring

### Timing Metrics
```python
# Automatic timing in middleware
start_time = time.time()
result = await call_next(ctx)
processing_time_ms = (time.time() - start_time) * 1000

# Slow operation detection
if processing_time_ms > config.slow_operation_threshold_ms:
    logger.warning(f"Slow operation: {processing_time_ms:.1f}ms")
```

### Performance Optimization
- Middleware runs for every request - keep overhead minimal
- Async operations throughout to prevent blocking
- Conditional logging based on configuration
- Efficient data structures for rate limiting

## Rate Limiting Strategy

### Token Bucket Algorithm
```python
class TokenBucket:
    def __init__(self, rate: float, burst: int):
        self.rate = rate      # Tokens per second
        self.burst = burst    # Maximum bucket capacity
        self.tokens = burst   # Current token count

    async def consume(self, tokens: int = 1) -> bool:
        # Replenish tokens based on elapsed time
        # Return True if enough tokens available
```

### Rate Limiting Benefits
- **Abuse Prevention**: Protects against spam and DoS attacks
- **Resource Protection**: Prevents resource exhaustion
- **Fair Usage**: Ensures equal access for all clients
- **Graceful Degradation**: Smooth handling of burst traffic

## Development Commands

### Middleware Testing
```bash
# Test middleware order
uv run pytest tests/test_middleware.py::TestMiddlewareOrder -v

# Test error handling
uv run pytest tests/test_error_handling.py::TestMiddleware -v

# Test rate limiting
uv run pytest tests/test_middleware.py::TestRateLimiting -v
```

### Manual Middleware Testing
```bash
# Test error handling
python -c "
from swag_mcp.middleware.error_handling import error_handling_middleware
print('Error handling middleware loaded')
"

# Test with rate limiting enabled
SWAG_MCP_RATE_LIMIT_ENABLED=true \
SWAG_MCP_RATE_LIMIT_RPS=1.0 \
fastmcp dev swag_mcp/server.py

# Test logging output
SWAG_MCP_LOG_PAYLOADS=true \
SWAG_MCP_ENABLE_STRUCTURED_LOGGING=true \
python -m swag_mcp
```

## Monitoring and Observability

### Logging Integration
- **Structured Logging**: JSON format for log aggregation
- **Request Correlation**: Request IDs for tracing
- **Performance Metrics**: Timing and throughput data
- **Error Tracking**: Exception details with stack traces

### Metrics Collection
```python
# Performance metrics
- request_duration_ms: Request processing time
- slow_operations_count: Operations exceeding threshold
- error_rate: Failed requests per time period
- rate_limit_hits: Requests blocked by rate limiting

# Usage metrics
- requests_per_second: Throughput measurement
- active_connections: Concurrent request count
- payload_sizes: Request/response size distribution
```

## Important Notes

### Middleware Design Principles
- **Composable**: Each middleware has single responsibility
- **Configurable**: Behavior controlled by environment variables
- **Observable**: Comprehensive logging and monitoring
- **Resilient**: Graceful error handling and recovery

### Security Considerations
- **Data Redaction**: Sensitive information removed from logs
- **Rate Limiting**: Prevents abuse and DoS attacks
- **Error Messages**: Safe error disclosure without information leakage
- **Input Validation**: Parameters validated at middleware level

### Performance Impact
- **Minimal Overhead**: Optimized for high-throughput scenarios
- **Async Operations**: Non-blocking I/O throughout
- **Conditional Processing**: Features can be disabled when not needed
- **Efficient Data Structures**: Token buckets and request correlation

### Common Issues
- **Middleware Order**: Incorrect order can break error handling or logging
- **Memory Leaks**: Rate limiter dictionaries need periodic cleanup
- **Log Verbosity**: Payload logging can impact performance and storage
- **Configuration**: Missing config can cause middleware to use defaults
