"""Health monitoring module for SWAG MCP."""

import asyncio
import logging
import ssl
import time

import aiohttp

from swag_mcp.models.config import (
    HealthEndpointResult,
    SwagHealthCheckRequest,
    SwagHealthCheckResult,
    SwagLogsRequest,
)
from swag_mcp.services.filesystem import FilesystemBackend, LocalFilesystem

logger = logging.getLogger(__name__)


_EndpointCheckOutcome = tuple[HealthEndpointResult, str | None]


class HealthMonitor:
    """Handles health checks and log access."""

    def __init__(
        self,
        fs: FilesystemBackend | None = None,
        swag_log_base_path: str = "/swag/log",
        health_check_insecure: bool = False,
    ) -> None:
        """Initialize health monitor.

        Args:
            fs: Filesystem backend to use (defaults to LocalFilesystem)
            swag_log_base_path: Base path for SWAG log files
            health_check_insecure: Disable TLS verification for endpoint checks

        """
        # HTTP session for health checks with connection pooling
        self._http_session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()
        self.fs: FilesystemBackend = fs or LocalFilesystem()
        self.swag_log_base_path = swag_log_base_path
        self.health_check_insecure = health_check_insecure

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
                if self.health_check_insecure:
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE

                # Create connector with connection pooling
                connector = aiohttp.TCPConnector(
                    ssl=ssl_context,
                    limit=10,  # Connection pool size
                    limit_per_host=5,  # Max connections per host
                    ttl_dns_cache=300,  # DNS cache TTL in seconds
                    use_dns_cache=True,
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
        logger.info("Performing health check for domain: %s", request.domain)

        # Try multiple endpoints to test if the reverse proxy is working
        endpoints_to_try = ["/health", "/mcp", "/"]
        urls_to_try = [f"https://{request.domain}{endpoint}" for endpoint in endpoints_to_try]

        outcomes = await asyncio.gather(
            *(
                self._check_health_endpoint(request, endpoint, url)
                for endpoint, url in zip(endpoints_to_try, urls_to_try, strict=True)
            )
        )
        endpoint_results = [outcome[0] for outcome in outcomes]

        for endpoint_result, response_body in outcomes:
            if endpoint_result.success:
                return SwagHealthCheckResult(
                    domain=request.domain,
                    url=endpoint_result.url,
                    status_code=endpoint_result.status_code,
                    response_time_ms=endpoint_result.response_time_ms,
                    response_body=response_body,
                    success=True,
                    error=None,
                    endpoint_results=endpoint_results,
                )

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
            endpoint_results=endpoint_results,
        )

    async def _check_health_endpoint(
        self, request: SwagHealthCheckRequest, endpoint: str, url: str
    ) -> _EndpointCheckOutcome:
        """Check one health endpoint and return structured endpoint detail."""
        logger.debug("Trying health check URL: %s", url)

        try:
            session = await self.get_session()
            start_time = time.perf_counter()
            timeout = aiohttp.ClientTimeout(total=request.timeout)

            async with session.get(
                url, allow_redirects=request.follow_redirects, timeout=timeout
            ) as response:
                response_time_ms = int((time.perf_counter() - start_time) * 1000)
                response_text = await response.text()
                response_body = response_text[:1000]
                if len(response_text) > 1000:
                    response_body += "... (truncated)"

                success = self._is_successful_health_response(endpoint, response.status)
                logger.info(
                    "Health check for %s - URL: %s, Status: %s, Time: %dms, Success: %s",
                    request.domain,
                    url,
                    response.status,
                    response_time_ms,
                    success,
                )

                return (
                    HealthEndpointResult(
                        endpoint=endpoint,
                        url=url,
                        success=success,
                        status_code=response.status,
                        response_time_ms=response_time_ms,
                        error=None if success else f"HTTP status {response.status}",
                    ),
                    response_body,
                )

        except TimeoutError:
            error_msg = f"Timeout after {request.timeout} seconds"
            logger.warning("Health check timeout for %s: %s", url, error_msg)
            return (
                HealthEndpointResult(endpoint=endpoint, url=url, success=False, error=error_msg),
                None,
            )
        except aiohttp.ClientConnectorError as e:
            error_msg = f"Connection failed: {str(e)}"
            logger.warning("Health check connection error for %s: %s", url, error_msg)
            return (
                HealthEndpointResult(endpoint=endpoint, url=url, success=False, error=error_msg),
                None,
            )
        except aiohttp.ClientResponseError as e:
            error_msg = f"HTTP error: {e.status} {e.message}"
            logger.warning("Health check HTTP error for %s: %s", url, error_msg)
            return (
                HealthEndpointResult(
                    endpoint=endpoint,
                    url=url,
                    success=False,
                    status_code=e.status,
                    error=error_msg,
                ),
                None,
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.warning("Health check unexpected error for %s: %s", url, error_msg)
            return (
                HealthEndpointResult(endpoint=endpoint, url=url, success=False, error=error_msg),
                None,
            )

    def _is_successful_health_response(self, endpoint: str, status_code: int) -> bool:
        """Return whether an endpoint HTTP status proves the proxy is reachable."""
        if 200 <= status_code < 300:
            return True
        return status_code == 406 and endpoint == "/mcp"

    async def get_swag_logs(self, logs_request: SwagLogsRequest) -> str:
        """Get SWAG logs by reading log files directly from mounted volume.

        Uses memory-efficient streaming to handle large log files.
        """
        logger.info("Getting SWAG logs: %s, %d lines", logs_request.log_type, logs_request.lines)

        # Map log types to file paths (using configurable base path)
        log_paths = {
            "nginx-access": f"{self.swag_log_base_path}/nginx/access.log",
            "nginx-error": f"{self.swag_log_base_path}/nginx/error.log",
            "fail2ban": f"{self.swag_log_base_path}/fail2ban/fail2ban.log",
            "letsencrypt": f"{self.swag_log_base_path}/letsencrypt/letsencrypt.log",
            "renewal": f"{self.swag_log_base_path}/letsencrypt/renewal.log",
        }

        log_path = log_paths.get(logs_request.log_type)

        if not log_path:
            raise ValueError(f"Invalid log type: {logs_request.log_type}")

        try:
            if not await self.fs.exists(log_path):
                # Return helpful message if file doesn't exist
                return (
                    f"Log file not found: {log_path}\n"
                    "The log file may not exist yet or SWAG may not be running."
                )

            # Use filesystem backend to read last N lines efficiently
            lines = await self.fs.read_tail_lines(log_path, logs_request.lines)

            if not lines:
                return f"No log entries found in {logs_request.log_type} log."

            # Convert lines to string efficiently
            result = "".join(lines)
            logger.info(
                "Successfully retrieved %d lines from %s (filesystem backend)",
                len(lines),
                logs_request.log_type,
            )
            return result

        except Exception as e:
            logger.error("Failed to read SWAG log file: %s", e)
            raise FileNotFoundError(
                f"Unable to read SWAG {logs_request.log_type} logs: {str(e)}\n"
                f"Please check that SWAG is running and log files are accessible"
            ) from e
