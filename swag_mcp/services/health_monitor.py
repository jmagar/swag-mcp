"""Health monitoring module for SWAG MCP."""

import asyncio
import ipaddress
import logging
import socket
import ssl
import time
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

import aiohttp
from aiohttp.abc import AbstractResolver, ResolveResult
from aiohttp.resolver import DefaultResolver

from swag_mcp.models.config import (
    HealthEndpointResult,
    SwagHealthCheckRequest,
    SwagHealthCheckResult,
    SwagLogsRequest,
)
from swag_mcp.services.filesystem import FilesystemBackend, LocalFilesystem

logger = logging.getLogger(__name__)


_EndpointCheckOutcome = tuple[HealthEndpointResult, str | None]
_MAX_HEALTH_REDIRECTS = 5


class _PinnedPublicResolver(AbstractResolver):
    """Resolver that only returns public IPs approved by health target validation."""

    def __init__(
        self,
        allowed_host_ips: dict[str, set[str]],
        validate_public_ip: Callable[
            [ipaddress.IPv4Address | ipaddress.IPv6Address],
            str | None,
        ],
    ) -> None:
        self._resolver: AbstractResolver = DefaultResolver()
        self._allowed_host_ips = allowed_host_ips
        self._validate_public_ip = validate_public_ip

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_INET,
    ) -> list[ResolveResult]:
        """Resolve a host and reject DNS-rebinding or non-public responses."""
        results = await self._resolver.resolve(host, port, family)
        allowed_ips = self._allowed_host_ips.get(host.lower())
        resolved_ips: set[str] = set()

        for result in results:
            try:
                resolved_ip = ipaddress.ip_address(result["host"])
            except ValueError as e:
                raise OSError(f"Resolver returned a non-IP address for {host}") from e

            ip_error = self._validate_public_ip(resolved_ip)
            if ip_error is not None:
                raise OSError(ip_error)
            resolved_ips.add(str(resolved_ip))

        if allowed_ips is not None and not resolved_ips.issubset(allowed_ips):
            unexpected_ips = sorted(resolved_ips - allowed_ips)
            raise OSError(
                f"Health check DNS response changed after validation: {', '.join(unexpected_ips)}"
            )

        return results

    async def close(self) -> None:
        """Close the wrapped aiohttp resolver."""
        await self._resolver.close()


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
        self._validated_health_ips: dict[str, set[str]] = {}

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
                    resolver=_PinnedPublicResolver(
                        self._validated_health_ips,
                        self._validate_public_ip,
                    ),
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

        validation_error = await self._validate_health_check_host(request.domain)
        if validation_error is not None:
            return SwagHealthCheckResult(
                domain=request.domain,
                url=f"https://{request.domain}/health",
                status_code=None,
                response_time_ms=None,
                response_body=None,
                success=False,
                error=validation_error,
                endpoint_results=[
                    HealthEndpointResult(
                        endpoint="/health",
                        url=f"https://{request.domain}/health",
                        success=False,
                        error=validation_error,
                    )
                ],
            )

        # Try multiple endpoints to test if the reverse proxy is working
        endpoints_to_try = ["/health", "/mcp", "/"]
        urls_to_try = [f"https://{request.domain}{endpoint}" for endpoint in endpoints_to_try]

        endpoint_results: list[HealthEndpointResult] = []
        for endpoint, url in zip(endpoints_to_try, urls_to_try, strict=True):
            endpoint_result, response_body = await self._check_health_endpoint(
                request, endpoint, url
            )
            endpoint_results.append(endpoint_result)
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

    async def _validate_health_check_host(self, host: str) -> str | None:
        """Return an error message when a health-check host resolves internally."""
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
            return "Health check target must not be localhost"

        try:
            literal_ip = ipaddress.ip_address(host)
        except ValueError:
            literal_ip = None
        if literal_ip is not None:
            ip_error = self._validate_public_ip(literal_ip)
            if ip_error is None:
                self._validated_health_ips[host.lower()] = {str(literal_ip)}
            return ip_error

        try:
            address_infos = await asyncio.get_running_loop().getaddrinfo(
                host,
                None,
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as e:
            return f"Could not resolve health check target: {e}"

        resolved_ips: set[ipaddress.IPv4Address | ipaddress.IPv6Address] = set()
        for address_info in address_infos:
            sockaddr = address_info[4]
            resolved_ips.add(ipaddress.ip_address(sockaddr[0]))

        if not resolved_ips:
            return "Health check target did not resolve to an IP address"

        for resolved_ip in resolved_ips:
            ip_error = self._validate_public_ip(resolved_ip)
            if ip_error is not None:
                return ip_error
        self._validated_health_ips[host.lower()] = {
            str(resolved_ip) for resolved_ip in resolved_ips
        }
        return None

    def _validate_public_ip(
        self, ip_address: ipaddress.IPv4Address | ipaddress.IPv6Address
    ) -> str | None:
        """Return an error message when an IP address is unsafe for health checks."""
        if (
            ip_address.is_loopback
            or ip_address.is_private
            or ip_address.is_link_local
            or ip_address.is_multicast
            or ip_address.is_reserved
            or ip_address.is_unspecified
        ):
            return f"Health check target resolves to a non-public address: {ip_address}"
        return None

    async def _check_health_endpoint(
        self, request: SwagHealthCheckRequest, endpoint: str, url: str
    ) -> _EndpointCheckOutcome:
        """Check one health endpoint and return structured endpoint detail."""
        logger.debug("Trying health check URL: %s", url)

        try:
            session = await self.get_session()
            start_time = time.perf_counter()
            timeout = aiohttp.ClientTimeout(total=request.timeout)
            current_url = url

            for _ in range(_MAX_HEALTH_REDIRECTS + 1):
                async with session.get(
                    current_url, allow_redirects=False, timeout=timeout
                ) as response:
                    if (
                        request.follow_redirects
                        and response.status in {301, 302, 303, 307, 308}
                        and response.headers.get("Location")
                    ):
                        redirect_url = urljoin(current_url, response.headers["Location"])
                        redirect_error = await self._validate_redirect_target(
                            request.domain, redirect_url
                        )
                        if redirect_error is not None:
                            raise ValueError(redirect_error)
                        current_url = redirect_url
                        continue

                    response_time_ms = int((time.perf_counter() - start_time) * 1000)
                    response_text = await response.text()
                    response_body = response_text[:1000]
                    if len(response_text) > 1000:
                        response_body += "... (truncated)"

                    success = self._is_successful_health_response(endpoint, response.status)
                    logger.info(
                        "Health check for %s - URL: %s, Status: %s, Time: %dms, Success: %s",
                        request.domain,
                        current_url,
                        response.status,
                        response_time_ms,
                        success,
                    )

                    return (
                        HealthEndpointResult(
                            endpoint=endpoint,
                            url=current_url,
                            success=success,
                            status_code=response.status,
                            response_time_ms=response_time_ms,
                            error=None if success else f"HTTP status {response.status}",
                        ),
                        response_body,
                    )

            raise ValueError("Too many redirects during health check")

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
        except ValueError as e:
            error_msg = str(e)
            logger.warning("Health check validation error for %s: %s", url, error_msg)
            return (
                HealthEndpointResult(endpoint=endpoint, url=url, success=False, error=error_msg),
                None,
            )
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.warning("Health check unexpected error for %s: %s", url, error_msg)
            return (
                HealthEndpointResult(endpoint=endpoint, url=url, success=False, error=error_msg),
                None,
            )

    async def _validate_redirect_target(
        self, original_domain: str, redirect_url: str
    ) -> str | None:
        """Validate that redirects stay on the original public health-check host."""
        parsed = urlparse(redirect_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "Health check redirect target is invalid"
        if parsed.hostname.lower() != original_domain:
            return "Health check redirects must stay on the original host"
        return None

    def _is_successful_health_response(self, endpoint: str, status_code: int) -> bool:
        """Return whether an endpoint HTTP status proves the proxy is reachable."""
        if 200 <= status_code < 300:
            return True
        # Streamable HTTP may reject GETs, and protected MCP endpoints may reject
        # anonymous probes while still proving that the proxy reached the upstream.
        return endpoint == "/mcp" and status_code in {401, 403, 406}

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
