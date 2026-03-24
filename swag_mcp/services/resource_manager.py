"""Resource management module for SWAG MCP."""

import logging
from pathlib import Path

from swag_mcp.models.config import SwagResourceList
from swag_mcp.services.filesystem import FilesystemBackend, LocalFilesystem
from swag_mcp.utils.formatters import get_possible_sample_filenames

logger = logging.getLogger(__name__)


class ResourceManager:
    """Handles resource and sample config management."""

    def __init__(self, config_path: Path, fs: FilesystemBackend | None = None) -> None:
        """Initialize resource manager.

        Args:
            config_path: Path to the configuration directory
            fs: Filesystem backend to use (defaults to LocalFilesystem)

        """
        self.config_path = config_path
        self.fs: FilesystemBackend = fs or LocalFilesystem()

    async def get_resource_configs(self) -> SwagResourceList:
        """Get list of active configuration files for resources."""
        logger.info("Getting active configuration files for resources")

        # Get active configurations (excluding samples and backups)
        filenames = await self.fs.glob(str(self.config_path), "*.conf")
        active_configs = [f for f in filenames if not f.endswith(".sample") and ".backup." not in f]

        # Sort the list
        active_configs = sorted(active_configs)

        logger.info(f"Found {len(active_configs)} active configurations")

        return SwagResourceList(configs=active_configs, total_count=len(active_configs))

    async def get_sample_configs(self) -> SwagResourceList:
        """Get list of sample configuration files for resources."""
        logger.info("Getting sample configuration files for resources")

        # Get sample configurations
        sample_configs = await self.fs.glob(str(self.config_path), "*.sample")

        # Sort the list
        sample_configs = sorted(sample_configs)

        logger.info(f"Found {len(sample_configs)} sample configurations")

        return SwagResourceList(configs=sample_configs, total_count=len(sample_configs))

    async def get_service_samples(self, service_name: str) -> SwagResourceList:
        """Get sample configurations for a specific service."""
        logger.info(f"Getting sample configurations for service: {service_name}")

        # Look for both subdomain and subfolder samples for the service
        patterns = get_possible_sample_filenames(service_name)

        found_configs = []
        for pattern in patterns:
            if await self.fs.exists(str(self.config_path / pattern)):
                found_configs.append(pattern)

        logger.info(f"Found {len(found_configs)} sample configurations for {service_name}")

        return SwagResourceList(configs=sorted(found_configs), total_count=len(found_configs))
