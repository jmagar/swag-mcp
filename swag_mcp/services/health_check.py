"""Health check service with connection pooling and async operations."""

import asyncio
import logging
import ssl
import time
from typing import Optional

import aiohttp

from ..constants import (
    HTTP_NOT_ACCEPTABLE,
    HTTP_NOT_FOUND,
    HTTP_OK_MAX,
    HTTP_OK_MIN,
    MCP_ENDPOINT_PATH,
    RESPONSE_BODY_MAX_LENGTH,
)
from ..models.config import SwagHealthCheckRequest, SwagHealthCheckResult

logger = logging.getLogger(__name__)


class HealthCheckService:
    """Service for performing health checks with connection pooling."""
    
    def __init__(self) -> None:
        """Initialize the health check service."""
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an HTTP session with connection pooling.
        
        Returns:
            Configured aiohttp ClientSession
        """
        if self._session is None or self._session.closed:
            # Configure SSL context for self-signed certificates
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Create connector with connection pooling
            self._connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                limit=100,  # Total connection pool limit
                limit_per_host=30,  # Per-host connection limit
                ttl_dns_cache=300,  # DNS cache timeout
                enable_cleanup_closed=True,
            )
            
            # Create session with connector
            self._session = aiohttp.ClientSession(connector=self._connector)
            logger.debug("Created new HTTP session with connection pooling")
        
        return self._session
    
    async def close(self) -> None:
        """Close the HTTP session and cleanup resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self._connector = None
            logger.debug("Closed HTTP session")
    
    async def check_endpoint(
        self, 
        url: str, 
        timeout: int, 
        follow_redirects: bool
    ) -> tuple[bool, SwagHealthCheckResult]:
        """Check a single endpoint.
        
        Args:
            url: URL to check
            timeout: Request timeout in seconds
            follow_redirects: Whether to follow redirects
            
        Returns:
            Tuple of (success, result)
        """
        session = await self._get_session()
        start_time = time.time()
        
        try:
            async with session.get(
                url, 
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=follow_redirects,
                ssl=False  # SSL context is in connector
            ) as response:
                # Calculate response time
                response_time_ms = int((time.time() - start_time) * 1000)
                
                # Read response body (limited to max length)
                response_text = await response.text()
                response_body = response_text[:RESPONSE_BODY_MAX_LENGTH]
                if len(response_text) > RESPONSE_BODY_MAX_LENGTH:
                    response_body += "... (truncated)"
                
                # Determine success based on endpoint and status code
                endpoint = url.split("/")[-1] if "/" in url else ""
                
                if HTTP_OK_MIN <= response.status <= HTTP_OK_MAX:
                    success = True
                elif response.status == HTTP_NOT_ACCEPTABLE and MCP_ENDPOINT_PATH in url:
                    success = True  # MCP endpoint exists but requires POST
                elif response.status == HTTP_NOT_FOUND and endpoint in ["health", ""]:
                    success = False  # Try next endpoint
                else:
                    success = True  # Any other response means proxy is working
                
                return success, SwagHealthCheckResult(
                    domain=url.split("//")[1].split("/")[0] if "//" in url else url,
                    url=url,
                    status_code=response.status,
                    response_time_ms=response_time_ms,
                    response_body=response_body,
                    success=success,
                    error=None,
                )
                
        except asyncio.TimeoutError:
            error_msg = f"Timeout after {timeout} seconds"
            logger.warning(f"Health check timeout for {url}: {error_msg}")
            return False, SwagHealthCheckResult(
                domain=url.split("//")[1].split("/")[0] if "//" in url else url,
                url=url,
                status_code=None,
                response_time_ms=None,
                response_body=None,
                success=False,
                error=error_msg,
            )
            
        except aiohttp.ClientError as e:
            error_msg = f"Connection failed: {str(e)}"
            logger.warning(f"Health check error for {url}: {error_msg}")
            return False, SwagHealthCheckResult(
                domain=url.split("//")[1].split("/")[0] if "//" in url else url,
                url=url,
                status_code=None,
                response_time_ms=None,
                response_body=None,
                success=False,
                error=error_msg,
            )
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Health check unexpected error for {url}: {error_msg}")
            return False, SwagHealthCheckResult(
                domain=url.split("//")[1].split("/")[0] if "//" in url else url,
                url=url,
                status_code=None,
                response_time_ms=None,
                response_body=None,
                success=False,
                error=error_msg,
            )
    
    async def health_check_parallel(
        self, request: SwagHealthCheckRequest
    ) -> SwagHealthCheckResult:
        """Perform health check with parallel endpoint testing.
        
        Args:
            request: Health check request parameters
            
        Returns:
            Health check result
        """
        logger.info(f"Performing parallel health check for domain: {request.domain}")
        
        # Build URLs to try
        endpoints = ["/health", MCP_ENDPOINT_PATH, "/"]
        urls = [f"https://{request.domain}{endpoint}" for endpoint in endpoints]
        
        # Check all endpoints in parallel
        tasks = [
            self.check_endpoint(url, request.timeout, request.follow_redirects)
            for url in urls
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results - return first success or last failure
        last_result = None
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Task exception for {urls[i]}: {result}")
                continue
                
            success, check_result = result
            if success:
                logger.info(f"Health check successful for {request.domain} at {urls[i]}")
                return check_result
            
            last_result = check_result
        
        # If we get here, all checks failed
        if last_result:
            return last_result
        
        # Fallback if all tasks failed
        return SwagHealthCheckResult(
            domain=request.domain,
            url=urls[0],
            status_code=None,
            response_time_ms=None,
            response_body=None,
            success=False,
            error="All health check endpoints failed",
        )


# Global instance for connection pooling
_health_check_service: Optional[HealthCheckService] = None


def get_health_check_service() -> HealthCheckService:
    """Get or create the global health check service instance.
    
    Returns:
        HealthCheckService instance
    """
    global _health_check_service
    if _health_check_service is None:
        _health_check_service = HealthCheckService()
    return _health_check_service


async def cleanup_health_check_service() -> None:
    """Cleanup the global health check service."""
    global _health_check_service
    if _health_check_service:
        await _health_check_service.close()
        _health_check_service = None