"""Centralized error message templates for SWAG MCP."""

from typing import Any


class ValidationErrorMessages:
    """Error message templates for validation failures."""

    # Domain validation errors
    DOMAIN_EMPTY = "Domain name cannot be empty"
    DOMAIN_TOO_LONG = "Domain name is too long (maximum 253 characters)"
    DOMAIN_CONSECUTIVE_DOTS = "Domain name cannot contain consecutive dots"
    DOMAIN_START_END_DOT = "Domain name cannot start or end with a dot"
    DOMAIN_NO_DOT = "Domain name must contain at least one dot (e.g., example.com)"
    DOMAIN_EMPTY_PARTS = "Domain name cannot have empty parts"
    DOMAIN_PART_TOO_LONG = "Domain part '{part}' is too long (maximum 63 characters)"
    DOMAIN_PART_HYPHEN = "Domain part '{part}' cannot start or end with hyphen"
    DOMAIN_TLD_INVALID = "Top-level domain '{part}' contains invalid characters"
    DOMAIN_TLD_NUMERIC = "Top-level domain '{part}' cannot be purely numeric"

    # Service name validation errors
    SERVICE_NAME_EMPTY = "Service name cannot be empty"
    SERVICE_NAME_TOO_LONG = "Service name too long (maximum 100 characters)"
    SERVICE_NAME_UNICODE_ERROR = "Service name contains invalid Unicode characters: {error}"
    SERVICE_NAME_INVALID_START = "Service name must start with a letter, number, or emoji"
    SERVICE_NAME_INVALID_START_NO_EMOJI = "Service name must start with a letter or number"
    SERVICE_NAME_EMPTY_AFTER_NORM = "Service name cannot be empty after normalization"
    SERVICE_NAME_INVALID_EMOJI_POS = (
        "Emoji characters in service names must be at the beginning or end"
    )
    SERVICE_NAME_DANGEROUS_PATTERNS = "Service name contains potentially dangerous patterns"
    SERVICE_NAME_INVALID_UNICODE_CATEGORY = (
        "Service name contains disallowed Unicode character category: {category}"
    )

    # Config filename validation errors
    CONFIG_FILENAME_EMPTY = "Configuration filename cannot be empty"
    CONFIG_FILENAME_TOO_LONG = "Configuration filename too long"
    CONFIG_FILENAME_PATH_TRAVERSAL = "Path traversal not allowed in configuration names"
    CONFIG_FILENAME_ABSOLUTE_PATH = "Absolute paths not allowed in configuration names"
    CONFIG_FILENAME_INVALID_CHAR = "Invalid character in configuration name: {char}"
    CONFIG_FILENAME_INVALID_EXTENSION = "Configuration filename must end with .conf or .conf.sample"
    CONFIG_FILENAME_INVALID_PATTERNS = "Invalid characters or patterns in configuration name"

    # Port validation errors
    PORT_NOT_INTEGER = "Port must be an integer"
    PORT_OUT_OF_RANGE = "Port must be between 1 and 65535"

    # General validation errors
    INPUT_NOT_STRING = "Input must be a string"
    INPUT_UNICODE_ERROR = "Invalid Unicode characters in text: {error}"
    BINARY_CONTENT_NOT_BYTES = "Input must be bytes"
    BINARY_CONTENT_DECODE_ERROR = "Unable to decode content as text - may be binary data"
    CONTENT_SAFETY_DANGER = "Input contains potentially dangerous patterns"

    @classmethod
    def format_message(cls, template: str, **kwargs: Any) -> str:
        """Format an error message template with provided values.

        Args:
            template: Error message template
            **kwargs: Values to format into the template

        Returns:
            Formatted error message

        """
        return template.format(**kwargs)


class SwagManagerErrorMessages:
    """Error message templates for SWAG manager service errors."""

    # Transaction errors
    TRANSACTION_ALREADY_ACTIVE = "Transaction {transaction_id} is already active"

    # Template variable errors
    TEMPLATE_VAR_INVALID_NAME = "Invalid template variable name: {key}"
    TEMPLATE_VAR_DANGEROUS = "Template variable '{key}' contains potentially dangerous content"
    TEMPLATE_VAR_INVALID_PATH_CHARS = "Template variable '{key}' contains invalid path characters"
    TEMPLATE_VAR_TOO_LONG = "Template variable '{key}' is too long"

    # Configuration content errors
    CONFIG_CONTENT_EMPTY = "Configuration content cannot be empty"
    CONFIG_CONTENT_DANGEROUS = "Configuration content contains potentially dangerous patterns"
    CONFIG_CONTENT_TOO_LARGE = "Configuration content is too large"
    CONFIG_UNICODE_ERROR = "Invalid Unicode content for {operation}: {error}"

    # File operation errors
    CONFIG_ALREADY_EXISTS = "Configuration {filename} already exists"
    CONFIG_NOT_FOUND = "Configuration {config_name} not found"
    TEMPLATE_NOT_FOUND = "Template {template_name} not found"
    TEMPLATE_RENDER_ERROR = "Failed to render template: {error}"
    FILE_SAFETY_ERROR = "File safety check failed for {filename}"

    # Update operation errors
    UPDATE_FIELD_APP_FORMAT = "app field requires format 'app:port'"
    UPDATE_FIELD_UNSUPPORTED = "Unsupported update field: {field}"

    # Log operation errors
    LOG_TYPE_INVALID = "Invalid log type: {log_type}"

    @classmethod
    def format_message(cls, template: str, **kwargs: Any) -> str:
        """Format an error message template with provided values.

        Args:
            template: Error message template
            **kwargs: Values to format into the template

        Returns:
            Formatted error message

        """
        return template.format(**kwargs)
