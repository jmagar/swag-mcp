"""Core SWAG configuration management service."""

import logging
from datetime import datetime
from pathlib import Path

import aiofiles
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from ..core.config import config
from ..models.config import (
    SwagConfigRequest,
    SwagConfigResult,
    SwagEditRequest,
    SwagHealthCheckRequest,
    SwagHealthCheckResult,
    SwagListResult,
    SwagLogsRequest,
    SwagRemoveRequest,
    SwagResourceList,
)

logger = logging.getLogger(__name__)


class SwagManagerService:
    """Service for managing SWAG proxy configurations."""

    def __init__(
        self,
        config_path: Path | None = None,
        template_path: Path | None = None,
    ) -> None:
        """Initialize the SWAG manager service."""
        self.config_path = config_path or config.proxy_confs_path
        self.template_path = template_path or config.template_path
        self._directory_checked = False

        # Initialize Jinja2 environment
        self.template_env = Environment(
            loader=FileSystemLoader(str(self.template_path)),
            autoescape=False,  # NGINX configs don't need HTML escaping
            trim_blocks=True,
            lstrip_blocks=True,
        )

        logger.info(f"Initialized SWAG manager with proxy configs path: {self.config_path}")

    def _ensure_config_directory(self) -> None:
        """Ensure the configuration directory exists."""
        if not self._directory_checked:
            self.config_path.mkdir(parents=True, exist_ok=True)
            self._directory_checked = True

    async def list_configs(self, config_type: str = "all") -> SwagListResult:
        """List configuration files based on type."""
        logger.info(f"Listing configurations of type: {config_type}")
        self._ensure_config_directory()

        configs = []

        if config_type in ["all", "active"]:
            # List active configurations (.conf files, not .sample)
            active_configs = [
                f.name for f in self.config_path.glob("*.conf") if not f.name.endswith(".sample")
            ]
            configs.extend(active_configs)

        if config_type in ["all", "samples"]:
            # List sample configurations (.sample files)
            sample_configs = [f.name for f in self.config_path.glob("*.sample")]
            configs.extend(sample_configs)

        # Remove duplicates and sort
        configs = sorted(set(configs))

        logger.info(f"Found {len(configs)} configurations")

        return SwagListResult(configs=configs, total_count=len(configs), config_type=config_type)

    async def read_config(self, config_name: str) -> str:
        """Read configuration file content."""
        logger.info(f"Reading configuration: {config_name}")
        self._ensure_config_directory()

        config_file = self.config_path / config_name
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration {config_name} not found")

        async with aiofiles.open(config_file) as f:
            content = await f.read()

        logger.info(f"Successfully read {len(content)} characters from {config_name}")
        return content

    async def create_config(self, request: SwagConfigRequest) -> SwagConfigResult:
        """Create new configuration from template."""
        logger.info(f"Creating {request.config_type} configuration for {request.service_name}")
        self._ensure_config_directory()

        # Determine template and filename
        if request.config_type == "mcp-subdomain":
            template_name = "mcp-subdomain.conf.j2"
            filename = f"{request.service_name}.subdomain.conf"
        elif request.config_type == "mcp-subfolder":
            template_name = "mcp-subfolder.conf.j2"
            filename = f"{request.service_name}.subfolder.conf"
        else:
            template_name = f"{request.config_type}.conf.j2"
            filename = f"{request.service_name}.{request.config_type}.conf"

        # Check if configuration already exists
        config_file = self.config_path / filename
        if config_file.exists():
            raise ValueError(f"Configuration {filename} already exists")

        try:
            # Render template
            template = self.template_env.get_template(template_name)
            content = template.render(
                service_name=request.service_name,
                server_name=request.server_name,
                upstream_app=request.upstream_app,
                upstream_port=request.upstream_port,
                upstream_proto=request.upstream_proto,
                auth_method=request.auth_method,
                enable_quic=request.enable_quic,
            )
        except TemplateNotFound as e:
            raise ValueError(f"Template {template_name} not found") from e
        except Exception as e:
            raise ValueError(f"Failed to render template: {str(e)}") from e

        # Write configuration
        async with aiofiles.open(config_file, "w") as f:
            await f.write(content)

        logger.info(f"Successfully created configuration: {filename}")

        return SwagConfigResult(filename=filename, content=content)

    async def update_config(self, edit_request: SwagEditRequest) -> SwagConfigResult:
        """Update configuration with optional backup."""
        logger.info(f"Updating configuration: {edit_request.config_name}")

        config_file = self.config_path / edit_request.config_name
        backup_name = None

        # Create backup if requested and file exists
        if edit_request.create_backup and config_file.exists():
            backup_name = await self._create_backup(edit_request.config_name)
            logger.info(f"Created backup: {backup_name}")

        # Write new content
        async with aiofiles.open(config_file, "w") as f:
            await f.write(edit_request.new_content)

        logger.info(f"Successfully updated configuration: {edit_request.config_name}")

        return SwagConfigResult(
            filename=edit_request.config_name,
            content=edit_request.new_content,
            backup_created=backup_name,
        )

    async def _create_backup(self, config_name: str) -> str:
        """Create timestamped backup of configuration file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{config_name}.backup.{timestamp}"
        backup_file = self.config_path / backup_name

        # Read original content
        config_file = self.config_path / config_name
        async with aiofiles.open(config_file) as src:
            content = await src.read()

        # Write backup
        async with aiofiles.open(backup_file, "w") as dst:
            await dst.write(content)

        return backup_name

    async def validate_template_exists(self, config_type: str) -> bool:
        """Validate that the required template exists."""
        if config_type == "mcp-subdomain":
            template_name = "mcp-subdomain.conf.j2"
        elif config_type == "mcp-subfolder":
            template_name = "mcp-subfolder.conf.j2"
        else:
            template_name = f"{config_type}.conf.j2"
        try:
            self.template_env.get_template(template_name)
            return True
        except TemplateNotFound:
            return False

    async def remove_config(self, remove_request: SwagRemoveRequest) -> SwagConfigResult:
        """Remove configuration with optional backup."""
        logger.info(f"Removing configuration: {remove_request.config_name}")

        config_file = self.config_path / remove_request.config_name

        # Check if file exists
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration {remove_request.config_name} not found")

        # Read content for backup and response
        async with aiofiles.open(config_file) as f:
            content = await f.read()

        backup_name = None

        # Create backup if requested
        if remove_request.create_backup:
            backup_name = await self._create_backup(remove_request.config_name)
            logger.info(f"Created backup: {backup_name}")

        # Remove the configuration file
        config_file.unlink()

        logger.info(f"Successfully removed configuration: {remove_request.config_name}")

        return SwagConfigResult(
            filename=remove_request.config_name, content=content, backup_created=backup_name
        )

    async def get_docker_logs(self, logs_request: SwagLogsRequest) -> str:
        """Get SWAG docker container logs."""
        logger.info(f"Getting SWAG docker logs: {logs_request.lines} lines")

        import subprocess

        try:
            # Build docker logs command
            cmd = ["docker", "logs", "--tail", str(logs_request.lines)]
            if logs_request.follow:
                cmd.append("--follow")

            # Try common SWAG container names
            container_names = ["swag", "letsencrypt", "nginx", "swag-nginx"]

            for container_name in container_names:
                try:
                    result = subprocess.run(
                        cmd + [container_name], capture_output=True, text=True, timeout=30
                    )
                    if result.returncode == 0:
                        logger.info(f"Successfully retrieved logs from container: {container_name}")
                        return result.stdout + result.stderr
                    else:
                        logger.debug(
                            f"Container {container_name} failed with return code "
                            f"{result.returncode}: {result.stderr}"
                        )
                except subprocess.TimeoutExpired:
                    logger.warning(f"Timeout retrieving logs from container: {container_name}")
                except Exception as e:
                    logger.debug(f"Exception for container {container_name}: {e}")

            # If no container found, list available containers
            result = subprocess.run(
                ["docker", "ps", "--format", "table {{.Names}}\t{{.Image}}"],
                capture_output=True,
                text=True,
            )

            available_containers = (
                result.stdout if result.returncode == 0 else "Unable to list containers"
            )

            raise FileNotFoundError(
                f"No SWAG container found. Tried: {', '.join(container_names)}\n"
                f"Available containers:\n{available_containers}"
            )

        except Exception as e:
            logger.error(f"Failed to retrieve docker logs: {str(e)}")
            raise

    async def get_resource_configs(self) -> SwagResourceList:
        """Get list of active configuration files for resources."""
        logger.info("Getting active configuration files for resources")

        # Get active configurations (excluding samples and backups)
        active_configs = [
            f.name
            for f in self.config_path.glob("*.conf")
            if not f.name.endswith(".sample") and ".backup." not in f.name
        ]

        # Sort the list
        active_configs = sorted(active_configs)

        logger.info(f"Found {len(active_configs)} active configurations")

        return SwagResourceList(configs=active_configs, total_count=len(active_configs))

    async def get_sample_configs(self) -> SwagResourceList:
        """Get list of sample configuration files for resources."""
        logger.info("Getting sample configuration files for resources")

        # Get sample configurations
        sample_configs = [f.name for f in self.config_path.glob("*.sample")]

        # Sort the list
        sample_configs = sorted(sample_configs)

        logger.info(f"Found {len(sample_configs)} sample configurations")

        return SwagResourceList(configs=sample_configs, total_count=len(sample_configs))

    async def get_service_samples(self, service_name: str) -> SwagResourceList:
        """Get sample configurations for a specific service."""
        logger.info(f"Getting sample configurations for service: {service_name}")

        # Look for both subdomain and subfolder samples for the service
        patterns = [
            f"{service_name}.subdomain.conf.sample",
            f"{service_name}.subfolder.conf.sample",
        ]

        found_configs = []
        for pattern in patterns:
            config_file = self.config_path / pattern
            if config_file.exists():
                found_configs.append(pattern)

        logger.info(f"Found {len(found_configs)} sample configurations for {service_name}")

        return SwagResourceList(configs=sorted(found_configs), total_count=len(found_configs))

    async def cleanup_old_backups(self, retention_days: int | None = None) -> int:
        """Clean up old backup files beyond retention period."""
        import re

        if retention_days is None:
            retention_days = config.backup_retention_days

        logger.info(f"Cleaning up backups older than {retention_days} days")

        cutoff_time = datetime.now().timestamp() - (retention_days * 24 * 60 * 60)
        cleaned_count = 0

        # Strict pattern: filename.backup.YYYYMMDD_HHMMSS
        # This ensures we only match backups created by our _create_backup method
        backup_pattern = re.compile(r"^.+\.backup\.\d{8}_\d{6}$")

        for backup_file in self.config_path.glob("*.backup.*"):
            # Additional safety checks:
            # 1. Must match our exact timestamp format
            # 2. Must be a regular file (not directory)
            # 3. Must be older than retention period
            if (
                backup_pattern.match(backup_file.name)
                and backup_file.is_file()
                and backup_file.stat().st_mtime < cutoff_time
            ):
                try:
                    logger.debug(f"Deleting old backup: {backup_file.name}")
                    backup_file.unlink()
                    cleaned_count += 1
                except (PermissionError, OSError) as e:
                    logger.warning(f"Failed to delete backup {backup_file.name}: {e}")
                    continue
            else:
                # Log files that matched glob but failed our strict checks
                if not backup_pattern.match(backup_file.name):
                    logger.debug(f"Skipping file (wrong format): {backup_file.name}")
                elif not backup_file.is_file():
                    logger.debug(f"Skipping non-file: {backup_file.name}")

        logger.info(f"Cleaned up {cleaned_count} old backup files")
        return cleaned_count

    async def health_check(self, request: SwagHealthCheckRequest) -> SwagHealthCheckResult:
        """Perform health check on a service endpoint."""
        import time

        logger.info(f"Performing health check for domain: {request.domain}")

        # Try multiple endpoints to test if the reverse proxy is working
        endpoints_to_try = ["/health", "/mcp", "/"]
        urls_to_try = [f"https://{request.domain}{endpoint}" for endpoint in endpoints_to_try]

        for url in urls_to_try:
            logger.debug(f"Trying health check URL: {url}")

            try:
                # Configure SSL context for self-signed certificates
                import ssl

                import aiohttp

                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

                # Create connector with SSL context
                connector = aiohttp.TCPConnector(ssl=ssl_context)

                # Record start time
                start_time = time.time()

                async with (
                    aiohttp.ClientSession(
                        connector=connector, timeout=aiohttp.ClientTimeout(total=request.timeout)
                    ) as session,
                    session.get(url, allow_redirects=request.follow_redirects) as response,
                ):
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
