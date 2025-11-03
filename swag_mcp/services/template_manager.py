"""Template management module for SWAG MCP."""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from jinja2.sandbox import SandboxedEnvironment

from swag_mcp.utils.formatters import build_template_filename

logger = logging.getLogger(__name__)


class TemplateManager:
    """Handles template rendering and management."""

    def __init__(self, template_path: Path) -> None:
        """Initialize template manager.

        Args:
            template_path: Path to the templates directory

        """
        self.template_path = template_path

        # Initialize secure Jinja2 environment with sandboxing
        self.template_env: Environment = self._create_secure_template_environment()

        # Testable hooks for template rendering
        self._pre_render_hook: Callable[[str, dict], None] | None = (
            None  # Called before template rendering
        )
        self._post_render_hook: Callable[[str, dict, str], None] | None = (
            None  # Called after template rendering
        )
        self._template_vars_hook: Callable[[dict], dict] | None = (
            None  # Called to modify template variables
        )

    def set_template_hooks(
        self,
        pre_render_hook: Callable[[str, dict], None] | None = None,
        post_render_hook: Callable[[str, dict, str], None] | None = None,
        template_vars_hook: Callable[[dict], dict] | None = None,
    ) -> None:
        """Set testable hooks for template rendering.

        Args:
            pre_render_hook: Called before template rendering with (template_name, variables)
            post_render_hook: Called after template rendering with (template_name, variables,
                rendered_content)
            template_vars_hook: Called to modify template variables, should return modified dict

        """
        self._pre_render_hook = pre_render_hook
        self._post_render_hook = post_render_hook
        self._template_vars_hook = template_vars_hook

    def clear_template_hooks(self) -> None:
        """Clear all template rendering hooks (useful for test cleanup)."""
        self._pre_render_hook = None
        self._post_render_hook = None
        self._template_vars_hook = None

    def get_template_path(self) -> Path:
        """Return the root path for Jinja templates (testable hook)."""
        return self.template_path

    def validate_template_variables(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Validate and sanitize template variables before rendering.

        Args:
            variables: Template variables to validate

        Returns:
            Sanitized variables dictionary

        """
        # Apply template_vars_hook if set (for testing)
        if self._template_vars_hook:
            variables = self._template_vars_hook(variables)

        # Basic validation - ensure all values are safe for template rendering
        safe_vars: dict[str, Any] = {}
        for key, value in variables.items():
            # Convert Path objects to strings for template compatibility
            if isinstance(value, Path):
                safe_vars[key] = str(value)
            # Ensure string values are safe
            elif isinstance(value, str | int | bool | float):
                safe_vars[key] = value
            # Skip None values
            elif value is None:
                continue
            else:
                # Convert other types to string representation
                safe_vars[key] = str(value)

        return safe_vars

    async def render_template(self, template_name: str, variables: dict[str, Any]) -> str:
        """Render a template with validated variables (testable hook).

        Args:
            template_name: Name of the template file to render
            variables: Variables to pass to the template

        Returns:
            Rendered template content

        Raises:
            ValueError: If template not found or rendering fails

        """
        # Validate/sanitize variables before rendering
        safe_vars = self.validate_template_variables(variables)

        # Call pre-render hook if set (for testing)
        if self._pre_render_hook:
            self._pre_render_hook(template_name, safe_vars)

        try:
            template = self.template_env.get_template(template_name)
            content = template.render(**safe_vars)

            # Call post-render hook if set (for testing)
            if self._post_render_hook:
                self._post_render_hook(template_name, safe_vars, content)

            return content
        except TemplateNotFound as e:
            raise ValueError(f"Template {template_name} not found") from e
        except Exception as e:
            raise ValueError(f"Failed to render template: {str(e)}") from e

    def _create_secure_template_environment(self) -> SandboxedEnvironment:
        """Create a secure sandboxed Jinja2 environment to prevent SSTI attacks.

        Returns:
            SandboxedEnvironment configured with security restrictions

        """
        # Create sandboxed environment to prevent dangerous operations
        env = SandboxedEnvironment(
            loader=FileSystemLoader(str(self.template_path)),
            autoescape=True,  # Enable autoescape for security
            undefined=StrictUndefined,  # Fail on undefined variables
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Remove dangerous globals and built-ins to prevent code execution
        # Minimal set of globals required for NGINX config templates
        env.globals = {
            # Only essential type conversion functions for template rendering
            "str": str,
            "int": int,
            "bool": bool,
        }

        # Customize sandbox to block additional dangerous operations
        def is_safe_attribute(obj: Any, attr: str, value: Any) -> bool:
            """Check if attribute access is safe."""
            # Block access to private/dunder methods
            if attr.startswith("_"):
                return False

            # Block access to dangerous attributes
            dangerous_attrs = [
                "import",
                "eval",
                "exec",
                "compile",
                "open",
                "file",
                "input",
                "raw_input",
                "reload",
                "help",
                "copyright",
                "credits",
                "license",
                "quit",
                "exit",
                "globals",
                "locals",
                "vars",
                "dir",
                "hasattr",
                "getattr",
                "setattr",
                "delattr",
                "isinstance",
                "issubclass",
                "callable",
                "classmethod",
                "staticmethod",
                "property",
                "super",
                "type",
                "__import__",
                "__builtins__",
                "__dict__",
                "__class__",
                "__bases__",
                "__name__",
                "__module__",
                "func_globals",
                "f_globals",
                "gi_frame",
                "gi_code",
                "cr_frame",
                "cr_code",
            ]

            if attr.lower() in dangerous_attrs:
                return False

            # Block access to subprocess-related attributes
            if "subprocess" in str(type(obj)).lower() or "popen" in attr.lower():
                return False

            # Block access to file system operations - return True if safe, False if blocked
            fs_access = any(
                fs_attr in attr.lower() for fs_attr in ["file", "open", "read", "write"]
            )
            safe_type = isinstance(obj, str | int | float | bool | list | dict | tuple)
            return not (fs_access and not safe_type)

        # Override the sandboxed environment's security checks
        # Note: is_safe_attribute signature doesn't perfectly match Jinja2 expectations
        # but this works for our security model
        env.is_safe_attribute = is_safe_attribute  # type: ignore[method-assign]

        # Disable dangerous template features
        env.filters.clear()  # Remove potentially dangerous filters
        env.tests.clear()  # Remove potentially dangerous tests

        # Add back only safe filters
        safe_filters = {
            "upper": str.upper,
            "lower": str.lower,
            "title": str.title,
            "capitalize": str.capitalize,
            "strip": str.strip,
            "replace": lambda s, old, new: str(s).replace(old, new),
            "length": len,
            "default": lambda val, default_val: val if val else default_val,
        }
        env.filters.update(safe_filters)

        logger.debug("Created secure sandboxed template environment")
        return env

    async def validate_template_exists(self, config_type: str) -> bool:
        """Validate that the required template exists."""
        try:
            template_name = build_template_filename(config_type)
        except ValueError:
            # Invalid config_type, template doesn't exist
            return False

        try:
            self.template_env.get_template(template_name)
            return True
        except TemplateNotFound:
            return False

    async def validate_all_templates(self) -> dict[str, bool]:
        """Validate that all required templates exist.

        Returns:
            Dictionary mapping template names to their existence status

        """
        from swag_mcp.core.constants import ALL_CONFIG_TYPES

        results = {}
        for config_type in ALL_CONFIG_TYPES:
            template_name = build_template_filename(config_type)
            # Check template existence directly to avoid duplicate template_name assignment
            try:
                self.template_env.get_template(template_name)
                exists = True
            except TemplateNotFound:
                exists = False

            results[config_type] = exists

            if exists:
                logger.debug(f"Template validation passed: {template_name}")
            else:
                logger.warning(f"Template validation failed: {template_name}")

        return results
