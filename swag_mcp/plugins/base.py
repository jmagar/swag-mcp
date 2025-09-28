"""Base classes and protocols for plugin architecture."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Protocol

from fastmcp import Context

logger = logging.getLogger(__name__)


class ToolPlugin(Protocol):
    """Protocol defining the interface for tool plugins.

    This enables a plugin architecture where new tools can be added
    dynamically without modifying the core codebase.
    """

    @property
    def name(self) -> str:
        """Return the unique name of this plugin."""
        ...

    @property
    def description(self) -> str:
        """Return a description of what this plugin does."""
        ...

    async def execute(self, ctx: Context, **kwargs: Any) -> str:
        """Execute the plugin with the given context and parameters.

        Args:
            ctx: FastMCP context
            **kwargs: Plugin-specific parameters

        Returns:
            Result string (usually formatted output)

        """
        ...

    def get_schema(self) -> dict[str, Any]:
        """Return the JSON schema for this plugin's parameters.

        Returns:
            JSON schema dictionary defining expected parameters

        """
        ...

    def validate_parameters(self, **kwargs: Any) -> dict[str, str] | None:
        """Validate plugin parameters.

        Args:
            **kwargs: Parameters to validate

        Returns:
            Dictionary of validation errors, or None if valid

        """
        ...


class BaseToolPlugin(ABC):
    """Abstract base class for tool plugins with common functionality."""

    def __init__(self, name: str, description: str):
        """Initialize plugin with name and description."""
        self._name = name
        self._description = description

    @property
    def name(self) -> str:
        """Get plugin name."""
        return self._name

    @property
    def description(self) -> str:
        """Get plugin description."""
        return self._description

    @abstractmethod
    async def execute(self, ctx: Context, **kwargs: Any) -> str:
        """Execute the plugin - must be implemented by subclasses."""
        pass

    @abstractmethod
    def get_schema(self) -> dict[str, Any]:
        """Return parameter schema - must be implemented by subclasses."""
        pass

    def validate_parameters(self, **kwargs: Any) -> dict[str, str] | None:
        """Override for custom parameter validation."""
        # Basic implementation - subclasses should override for specific validation
        return None


class PluginRegistry:
    """Registry for managing tool plugins.

    Provides centralized plugin management with discovery, registration,
    and execution capabilities.
    """

    def __init__(self) -> None:
        """Initialize plugin registry with empty plugin collections."""
        self._plugins: dict[str, ToolPlugin] = {}
        self._enabled_plugins: set[str] = set()
        logger.info("Initialized plugin registry")

    def register(self, plugin: ToolPlugin) -> None:
        """Register a plugin in the registry.

        Args:
            plugin: Plugin instance to register

        Raises:
            ValueError: If plugin name is already registered

        """
        if plugin.name in self._plugins:
            raise ValueError(f"Plugin '{plugin.name}' is already registered")

        self._plugins[plugin.name] = plugin
        self._enabled_plugins.add(plugin.name)
        logger.info(f"Registered plugin: {plugin.name}")

    def unregister(self, plugin_name: str) -> None:
        """Unregister a plugin from the registry.

        Args:
            plugin_name: Name of plugin to unregister

        """
        if plugin_name in self._plugins:
            del self._plugins[plugin_name]
            self._enabled_plugins.discard(plugin_name)
            logger.info(f"Unregistered plugin: {plugin_name}")

    def get_plugin(self, name: str) -> ToolPlugin | None:
        """Get a plugin by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None if not found

        """
        return self._plugins.get(name)

    def list_plugins(self, enabled_only: bool = True) -> dict[str, ToolPlugin]:
        """List registered plugins.

        Args:
            enabled_only: If True, only return enabled plugins

        Returns:
            Dictionary of plugin name -> plugin instance

        """
        if enabled_only:
            return {
                name: plugin for name, plugin in self._plugins.items()
                if name in self._enabled_plugins
            }
        return self._plugins.copy()

    def enable_plugin(self, plugin_name: str) -> bool:
        """Enable a registered plugin.

        Args:
            plugin_name: Name of plugin to enable

        Returns:
            True if enabled successfully, False if not found

        """
        if plugin_name in self._plugins:
            self._enabled_plugins.add(plugin_name)
            logger.info(f"Enabled plugin: {plugin_name}")
            return True
        return False

    def disable_plugin(self, plugin_name: str) -> bool:
        """Disable a registered plugin.

        Args:
            plugin_name: Name of plugin to disable

        Returns:
            True if disabled successfully, False if not found

        """
        if plugin_name in self._plugins:
            self._enabled_plugins.discard(plugin_name)
            logger.info(f"Disabled plugin: {plugin_name}")
            return True
        return False

    def is_enabled(self, plugin_name: str) -> bool:
        """Check if a plugin is enabled.

        Args:
            plugin_name: Plugin name to check

        Returns:
            True if plugin is enabled, False otherwise

        """
        return plugin_name in self._enabled_plugins

    async def execute_plugin(
        self,
        plugin_name: str,
        ctx: Context,
        **kwargs: Any
    ) -> str:
        """Execute a plugin by name.

        Args:
            plugin_name: Name of plugin to execute
            ctx: FastMCP context
            **kwargs: Plugin parameters

        Returns:
            Plugin execution result

        Raises:
            ValueError: If plugin not found or not enabled

        """
        if plugin_name not in self._plugins:
            raise ValueError(f"Plugin '{plugin_name}' not found")

        if not self.is_enabled(plugin_name):
            raise ValueError(f"Plugin '{plugin_name}' is disabled")

        plugin = self._plugins[plugin_name]

        # Validate parameters
        validation_errors = plugin.validate_parameters(**kwargs)
        if validation_errors:
            error_msg = "; ".join(f"{k}: {v}" for k, v in validation_errors.items())
            raise ValueError(f"Parameter validation failed: {error_msg}")

        # Execute plugin
        try:
            logger.info(f"Executing plugin: {plugin_name}")
            result = await plugin.execute(ctx, **kwargs)
            logger.info(f"Plugin {plugin_name} executed successfully")
            return result
        except Exception as e:
            logger.error(f"Plugin {plugin_name} execution failed: {e}")
            raise

    def get_plugin_schemas(self) -> dict[str, dict[str, Any]]:
        """Get schemas for all enabled plugins.

        Returns:
            Dictionary of plugin name -> schema

        """
        return {
            name: plugin.get_schema()
            for name, plugin in self._plugins.items()
            if name in self._enabled_plugins
        }


# Global plugin registry instance
registry = PluginRegistry()
