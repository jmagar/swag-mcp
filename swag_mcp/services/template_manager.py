"""Template management service for SWAG configurations."""

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from ..constants import (
    JINJA2_EXTENSION,
    TEMPLATE_MCP_SUBDOMAIN,
    TEMPLATE_MCP_SUBFOLDER,
    TEMPLATE_SUBDOMAIN,
    TEMPLATE_SUBFOLDER,
)

logger = logging.getLogger(__name__)


class TemplateManager:
    """Manages Jinja2 templates for SWAG configurations."""
    
    def __init__(self, template_path: Path) -> None:
        """Initialize the template manager.
        
        Args:
            template_path: Path to the directory containing templates
        """
        self.template_path = template_path
        self._ensure_template_directory()
        
        # Initialize Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.template_path)),
            autoescape=False,  # NGINX configs don't need HTML escaping
            trim_blocks=True,
            lstrip_blocks=True,
        )
        
        # Cache for template type mappings
        self._template_map = {
            TEMPLATE_MCP_SUBDOMAIN: f"mcp-subdomain.conf{JINJA2_EXTENSION}",
            TEMPLATE_MCP_SUBFOLDER: f"mcp-subfolder.conf{JINJA2_EXTENSION}",
            TEMPLATE_SUBDOMAIN: f"subdomain.conf{JINJA2_EXTENSION}",
            TEMPLATE_SUBFOLDER: f"subfolder.conf{JINJA2_EXTENSION}",
        }
        
        logger.info(f"Initialized template manager with path: {self.template_path}")
    
    def _ensure_template_directory(self) -> None:
        """Ensure the template directory exists."""
        if not self.template_path.exists():
            logger.warning(f"Template directory {self.template_path} does not exist, creating...")
            self.template_path.mkdir(parents=True, exist_ok=True)
    
    def get_template_name(self, config_type: str) -> str:
        """Get the template filename for a given configuration type.
        
        Args:
            config_type: Type of configuration
            
        Returns:
            Template filename
        """
        if config_type in self._template_map:
            return self._template_map[config_type]
        
        # Fallback for custom types
        return f"{config_type}.conf{JINJA2_EXTENSION}"
    
    def get_config_filename(self, service_name: str, config_type: str) -> str:
        """Generate the configuration filename for a service.
        
        Args:
            service_name: Name of the service
            config_type: Type of configuration
            
        Returns:
            Configuration filename
        """
        if config_type in [TEMPLATE_MCP_SUBDOMAIN, TEMPLATE_SUBDOMAIN]:
            return f"{service_name}.subdomain.conf"
        elif config_type in [TEMPLATE_MCP_SUBFOLDER, TEMPLATE_SUBFOLDER]:
            return f"{service_name}.subfolder.conf"
        else:
            return f"{service_name}.{config_type}.conf"
    
    def validate_template_exists(self, config_type: str) -> bool:
        """Check if a template exists for the given configuration type.
        
        Args:
            config_type: Type of configuration
            
        Returns:
            True if template exists, False otherwise
        """
        template_name = self.get_template_name(config_type)
        try:
            self.env.get_template(template_name)
            return True
        except TemplateNotFound:
            logger.warning(f"Template not found: {template_name}")
            return False
    
    def render_template(self, config_type: str, context: dict[str, Any]) -> str:
        """Render a template with the given context.
        
        Args:
            config_type: Type of configuration
            context: Template context variables
            
        Returns:
            Rendered template content
            
        Raises:
            TemplateNotFound: If template doesn't exist
            ValueError: If template rendering fails
        """
        template_name = self.get_template_name(config_type)
        
        try:
            template = self.env.get_template(template_name)
            content = template.render(**context)
            logger.debug(f"Successfully rendered template: {template_name}")
            return content
        except TemplateNotFound as e:
            raise ValueError(f"Template {template_name} not found") from e
        except Exception as e:
            raise ValueError(f"Failed to render template {template_name}: {str(e)}") from e
    
    def validate_templates(self) -> dict[str, bool]:
        """Validate all expected templates exist.
        
        Returns:
            Dictionary mapping template types to existence status
        """
        results = {}
        for config_type in self._template_map:
            results[config_type] = self.validate_template_exists(config_type)
        
        missing = [k for k, v in results.items() if not v]
        if missing:
            logger.error(f"Missing templates for: {', '.join(missing)}")
        else:
            logger.info("All expected templates are present")
        
        return results