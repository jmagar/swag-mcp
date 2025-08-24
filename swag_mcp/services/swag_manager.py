"""Core SWAG configuration management service."""

import logging
from datetime import datetime
from pathlib import Path

import aiofiles

from ..constants import (
    BACKUP_FILE_PATTERN,
    BACKUP_PATTERN,
    CONF_EXTENSION,
    CONFIG_TYPE_ACTIVE,
    CONFIG_TYPE_ALL,
    CONFIG_TYPE_SAMPLES,
    DOCKER_COMMAND_TIMEOUT,
    HEALTH_CHECK_TIMEOUT,
    HTTP_NOT_ACCEPTABLE,
    HTTP_NOT_FOUND,
    HTTP_OK_MAX,
    HTTP_OK_MIN,
    MCP_ENDPOINT_PATH,
    RESPONSE_BODY_MAX_LENGTH,
    SAMPLE_EXTENSION,
    SWAG_CONTAINER_NAMES,
)
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
from .health_check import get_health_check_service
from .template_manager import TemplateManager

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

        # Initialize template manager
        self.template_manager = TemplateManager(self.template_path)

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

        if config_type in [CONFIG_TYPE_ALL, CONFIG_TYPE_ACTIVE]:
            # List active configurations (.conf files, not .sample)
            active_configs = [
                f.name for f in self.config_path.glob(f"*{CONF_EXTENSION}") 
                if not f.name.endswith(SAMPLE_EXTENSION)
            ]
            configs.extend(active_configs)

        if config_type in [CONFIG_TYPE_ALL, CONFIG_TYPE_SAMPLES]:
            # List sample configurations (.sample files)
            sample_configs = [f.name for f in self.config_path.glob(f"*{SAMPLE_EXTENSION}")]
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

        # Get template and filename from template manager
        filename = self.template_manager.get_config_filename(
            request.service_name, request.config_type
        )

        # Check if configuration already exists
        config_file = self.config_path / filename
        if config_file.exists():
            raise ValueError(f"Configuration {filename} already exists")

        # Render template using template manager
        template_context = {
            "service_name": request.service_name,
            "server_name": request.server_name,
            "upstream_app": request.upstream_app,
            "upstream_port": request.upstream_port,
            "upstream_proto": request.upstream_proto,
            "auth_method": request.auth_method,
            "enable_quic": request.enable_quic,
        }
        
        content = self.template_manager.render_template(
            request.config_type, template_context
        )

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
        return self.template_manager.validate_template_exists(config_type)

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
        """Get SWAG docker container logs using async subprocess."""
        logger.info(f"Getting SWAG docker logs: {logs_request.lines} lines")

        import asyncio

        try:
            # Build docker logs command
            cmd = ["docker", "logs", "--tail", str(logs_request.lines)]
            if logs_request.follow:
                cmd.append("--follow")

            # Try common SWAG container names from constants
            container_names = list(SWAG_CONTAINER_NAMES)

            for container_name in container_names:
                try:
                    # Use async subprocess for non-blocking execution
                    proc = await asyncio.create_subprocess_exec(
                        *cmd, container_name,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    
                    # Wait for command with timeout
                    try:
                        stdout, stderr = await asyncio.wait_for(
                            proc.communicate(), 
                            timeout=DOCKER_COMMAND_TIMEOUT
                        )
                    except asyncio.TimeoutError:
                        proc.kill()
                        await proc.wait()
                        logger.warning(f"Timeout retrieving logs from container: {container_name}")
                        continue
                    
                    if proc.returncode == 0:
                        logger.info(f"Successfully retrieved logs from container: {container_name}")
                        # Decode bytes to string
                        return stdout.decode('utf-8') + stderr.decode('utf-8')
                    else:
                        logger.debug(
                            f"Container {container_name} failed with return code "
                            f"{proc.returncode}: {stderr.decode('utf-8')}"
                        )
                except Exception as e:
                    logger.debug(f"Exception for container {container_name}: {e}")

            # If no container found, list available containers (async)
            proc = await asyncio.create_subprocess_exec(
                "docker", "ps", "--format", "table {{.Names}}\t{{.Image}}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await proc.communicate()
            
            available_containers = (
                stdout.decode('utf-8') if proc.returncode == 0 else "Unable to list containers"
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
            for f in self.config_path.glob(f"*{CONF_EXTENSION}")
            if not f.name.endswith(SAMPLE_EXTENSION) and BACKUP_PATTERN not in f.name
        ]

        # Sort the list
        active_configs = sorted(active_configs)

        logger.info(f"Found {len(active_configs)} active configurations")

        return SwagResourceList(configs=active_configs, total_count=len(active_configs))

    async def get_sample_configs(self) -> SwagResourceList:
        """Get list of sample configuration files for resources."""
        logger.info("Getting sample configuration files for resources")

        # Get sample configurations
        sample_configs = [f.name for f in self.config_path.glob(f"*{SAMPLE_EXTENSION}")]

        # Sort the list
        sample_configs = sorted(sample_configs)

        logger.info(f"Found {len(sample_configs)} sample configurations")

        return SwagResourceList(configs=sample_configs, total_count=len(sample_configs))

    async def get_service_samples(self, service_name: str) -> SwagResourceList:
        """Get sample configurations for a specific service."""
        logger.info(f"Getting sample configurations for service: {service_name}")

        # Look for both subdomain and subfolder samples for the service
        patterns = [
            f"{service_name}.subdomain{CONF_EXTENSION}{SAMPLE_EXTENSION}",
            f"{service_name}.subfolder{CONF_EXTENSION}{SAMPLE_EXTENSION}",
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
        backup_pattern = re.compile(BACKUP_FILE_PATTERN)

        for backup_file in self.config_path.glob(f"*{BACKUP_PATTERN}*"):
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
        """Perform health check on a service endpoint using connection pooling."""
        health_service = get_health_check_service()
        return await health_service.health_check_parallel(request)
