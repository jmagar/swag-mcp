"""Common validators for SWAG MCP."""

import re
from typing import Any


def validate_domain(value: str) -> str:
    """Validate domain/hostname format.
    
    Args:
        value: Domain string to validate
        
    Returns:
        Normalized domain string (lowercase)
        
    Raises:
        ValueError: If domain format is invalid
    """
    if not value or ".." in value or value.startswith(".") or value.endswith("."):
        raise ValueError("Invalid domain format")
    
    # Basic domain validation regex
    domain_pattern = (
        r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
        r"(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
    )
    
    if not re.match(domain_pattern, value):
        raise ValueError(f"Invalid hostname format: {value}")
    
    return value.lower()


def validate_service_name(value: str) -> str:
    """Validate service name format.
    
    Args:
        value: Service name to validate
        
    Returns:
        Normalized service name (lowercase)
        
    Raises:
        ValueError: If service name format is invalid
    """
    if not value or value.startswith("-") or value.endswith("-"):
        raise ValueError("Service name cannot start or end with hyphen")
    return value.lower()


def validate_config_filename(value: str) -> str:
    """Validate configuration filename format.
    
    Args:
        value: Filename to validate
        
    Returns:
        Original filename if valid
        
    Raises:
        ValueError: If filename format is invalid
    """
    if not value:
        raise ValueError("Filename cannot be empty")
    
    # Check for path traversal attempts
    if "/" in value or "\\" in value or ".." in value:
        raise ValueError("Invalid filename: contains path separators or traversal")
    
    return value


def create_empty_string_validator(field_name: str, default_value: str) -> classmethod:
    """Factory to create validators for handling empty string fields.
    
    Args:
        field_name: Name of the field for error messages
        default_value: Default value to use for empty strings
        
    Returns:
        Validator method for Pydantic models
    """
    @classmethod
    def validator(cls, v: Any) -> Any:
        """Convert empty string to default value."""
        if isinstance(v, str) and v.strip() == "":
            return default_value
        return v
    
    validator.__name__ = f"handle_empty_{field_name}"
    validator.__doc__ = f"Convert empty {field_name} string to default value."
    return validator


def sanitize_template_input(value: str) -> str:
    """Sanitize user input for template rendering.
    
    Args:
        value: Input string to sanitize
        
    Returns:
        Sanitized string safe for template rendering
    """
    if not value:
        return ""
    
    # Remove any potential template injection attempts
    # Escape special nginx config characters
    value = value.replace("$", "\\$")
    value = value.replace(";", "\\;")
    value = value.replace("{", "\\{")
    value = value.replace("}", "\\}")
    value = value.replace("`", "\\`")
    
    return value