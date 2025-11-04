"""Health monitoring module for SWAG MCP."""

import asyncio
import logging
import ssl
import time
from collections import deque
from pathlib import Path
from typing import Any

import aiofiles
import aiohttp

from swag_mcp.core.config import config
from swag_mcp.models.config import (
    SwagHealthCheckRequest,
    SwagHealthCheckResult,
    SwagLogsRequest,
)

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Handles health checks and log access."""

    def __init__(self) -> None:
        """Initialize health monitor."""
        # HTTP session for health checks with connection pooling
        self._http_session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session with connection pooling.

        Returns:
            aiohttp.ClientSession configured with connection pooling and SSL context

        """
        async with self._session_lock:
            if self._http_session is None or self._http_session.closed:
                # Create SSL context for health checks
                ssl_context = ssl.create_default_context()

                # Only disable SSL verification if explicitly configured
                if config.health_check_insecure:
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE

                # Create connector with connection pooling
                connector = aiohttp.TCPConnector(
                    ssl=ssl_context,
                    limit=10,  # Connection pool size
                    limit_per_host=5,  # Max connections per host
                    ttl_dns_cache=300,  # DNS cache TTL in seconds
                    use_dns_cache=True,
                    enable_cleanup_closed=True,
                )

                # Create session with timeout and connector
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                self._http_session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout,
                )

            return self._http_session

    async def close_session(self) -> None:
        """Close HTTP session and cleanup resources."""
        async with self._session_lock:
            if self._http_session and not self._http_session.closed:
                await self._http_session.close()

    async def health_check(self, request: SwagHealthCheckRequest) -> SwagHealthCheckResult:
        """Perform health check on a service endpoint."""
        logger.info(f"Performing health check for domain: {request.domain}")

        # Try multiple endpoints to test if the reverse proxy is working
        endpoints_to_try = ["/health", "/mcp", "/"]
        urls_to_try = [f"https://{request.domain}{endpoint}" for endpoint in endpoints_to_try]

        for url in urls_to_try:
            logger.debug(f"Trying health check URL: {url}")

            try:
                # Get pooled HTTP session
                session = await self.get_session()

                # Record start time
                start_time = time.time()

                # Use custom timeout for this request
                timeout = aiohttp.ClientTimeout(total=request.timeout)

                async with session.get(
                    url, allow_redirects=request.follow_redirects, timeout=timeout
                ) as response:
                    # Calculate response time
                    response_time_ms = int((time.time() - start_time) * 1000)

                    # Read response body (limited to 1000 chars)
                    response_text = await response.text()
                    response_body = response_text[:1000]
                    if len(response_text) > 1000:
                        response_body += "... (truncated)"

                    # Determine success based on endpoint and status code
                    endpoint = url.split(request.domain)[1] if request.domain in url else "unknown"

                    if 200 <= response.status < 300:
                        # 2xx is always successful
                        success = True
                    elif response.status == 406 and endpoint == "/mcp":
                        # 406 for /mcp means endpoint exists (MCP requires POST)
                        success = True
                    elif response.status == 404 and endpoint in ["/health", "/"]:
                        # 404 for /health or / means try next endpoint
                        success = False
                    else:
                        # Any other HTTP response means proxy is working
                        success = True

                    logger.info(
                        f"Health check for {request.domain} - "
                        f"URL: {url}, Status: {response.status}, "
                        f"Time: {response_time_ms}ms, Success: {success}"
                    )

                    if success:
                        # Return successful result immediately
                        return SwagHealthCheckResult(
                            domain=request.domain,
                            url=url,
                            status_code=response.status,
                            response_time_ms=response_time_ms,
                            response_body=response_body,
                            success=True,
                            error=None,
                        )
                    else:
                        # Log the failure and continue to next endpoint
                        logger.debug(
                            f"Endpoint {endpoint} failed with {response.status}, "
                            "trying next endpoint"
                        )
                        continue

            except TimeoutError:
                error_msg = f"Timeout after {request.timeout} seconds"
                logger.warning(f"Health check timeout for {url}: {error_msg}")
                # Continue to try next URL
                continue

            except aiohttp.ClientConnectorError as e:
                error_msg = f"Connection failed: {str(e)}"
                logger.warning(f"Health check connection error for {url}: {error_msg}")
                # Continue to try next URL
                continue

            except aiohttp.ClientResponseError as e:
                error_msg = f"HTTP error: {e.status} {e.message}"
                logger.warning(f"Health check HTTP error for {url}: {error_msg}")
                # Continue to try next URL for HTTP errors
                continue

            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                logger.warning(f"Health check unexpected error for {url}: {error_msg}")
                # Continue to try next URL
                continue

        # If we get here, all URLs failed
        error_msg = f"All health check URLs failed for domain {request.domain}"
        logger.error(error_msg)

        return SwagHealthCheckResult(
            domain=request.domain,
            url=urls_to_try[0],  # Report the first URL attempted
            status_code=None,
            response_time_ms=None,
            response_body=None,
            success=False,
            error=error_msg,
        )

    async def get_swag_logs(self, logs_request: SwagLogsRequest) -> str:
        """Get SWAG logs by reading log files directly from mounted volume.

        Uses memory-efficient streaming to handle large log files.
        """
        logger.info(f"Getting SWAG logs: {logs_request.log_type}, {logs_request.lines} lines")

        # Map log types to file paths (using /swag mount point)
        log_paths = {
            "nginx-access": Path("/swag/log/nginx/access.log"),
            "nginx-error": Path("/swag/log/nginx/error.log"),
            "fail2ban": Path("/swag/log/fail2ban/fail2ban.log"),
            "letsencrypt": Path("/swag/log/letsencrypt/letsencrypt.log"),
            "renewal": Path("/swag/log/letsencrypt/renewal.log"),
        }

        log_file_path = log_paths.get(logs_request.log_type)

        if not log_file_path:
            raise ValueError(f"Invalid log type: {logs_request.log_type}")

        try:
            if not log_file_path.exists():
                # Return helpful message if file doesn't exist
                return (
                    f"Log file not found: {log_file_path}\n"
                    "The log file may not exist yet or SWAG may not be running."
                )

            # Memory-efficient streaming approach using deque
            # Read file in chunks and maintain only the requested number of lines in memory
            max_lines = logs_request.lines

            # Use deque with maxlen to automatically maintain only the last N lines
            line_buffer: deque[str] = deque(maxlen=max_lines)

            # Read file in streaming fashion
            async with aiofiles.open(log_file_path, encoding="utf-8", errors="ignore") as f:
                # For large files, we need to be memory-efficient
                # Read the file line by line to avoid loading everything into memory
                async for line in f:
                    line_buffer.append(line)

                    # Optional: If file is extremely large, we could add periodic yielding
                    # This prevents blocking the event loop for too long
                    # Every 1000 lines, yield control back to the event loop
                    if len(line_buffer) == max_lines and len(line_buffer) % 1000 == 0:
                        await asyncio.sleep(0)  # Yield control

            if not line_buffer:
                return f"No log entries found in {logs_request.log_type} log."

            # Convert deque to string efficiently
            result = "".join(line_buffer)
            logger.info(
                f"Successfully retrieved {len(line_buffer)} lines from {logs_request.log_type} "
                f"(memory-efficient streaming)"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to read SWAG log file: {str(e)}")
            raise FileNotFoundError(
                f"Unable to read SWAG {logs_request.log_type} logs: {str(e)}\n"
                f"Please check that SWAG is running and log files are accessible"
            ) from e
