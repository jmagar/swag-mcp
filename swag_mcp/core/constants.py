"""Constants used throughout the SWAG MCP server."""

# File patterns and extensions
CONF_PATTERN = "*.conf"
SAMPLE_PATTERN = "*.sample"
CONF_EXTENSION = ".conf"
SAMPLE_EXTENSION = ".sample"
BACKUP_MARKER = ".backup."

# Configuration types
CONFIG_TYPE_SUBDOMAIN = "subdomain"
CONFIG_TYPE_SUBFOLDER = "subfolder"
CONFIG_TYPE_MCP_SUBDOMAIN = "mcp-subdomain"
CONFIG_TYPE_MCP_SUBFOLDER = "mcp-subfolder"

# All available configuration types
ALL_CONFIG_TYPES = [
    CONFIG_TYPE_SUBDOMAIN,
    CONFIG_TYPE_SUBFOLDER,
    CONFIG_TYPE_MCP_SUBDOMAIN,
    CONFIG_TYPE_MCP_SUBFOLDER,
]

# URI schemes and paths
SWAG_URI_BASE = "swag://"
SWAG_URI_SAMPLES = "swag://samples/"

# HTTP endpoints
HEALTH_ENDPOINT = "/health"

# MIME types
MIME_TYPE_TEXT_PLAIN = "text/plain"
MIME_TYPE_APPLICATION_JSON = "application/json"

# Authentication methods
AUTH_METHOD_NONE = "none"
AUTH_METHOD_AUTHELIA = "authelia"
AUTH_METHOD_LDAP = "ldap"
AUTH_METHOD_AUTHENTIK = "authentik"
AUTH_METHOD_TINYAUTH = "tinyauth"

# Default values
DEFAULT_AUTH_METHOD = "authelia"
DEFAULT_CONFIG_TYPE = "subdomain"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_LOG_LEVEL = "INFO"

# Docker and health check
DOCKER_CONTAINER_NAME = "swag"
HEALTH_CHECK_TIMEOUT = 30

# Backup settings
DEFAULT_BACKUP_RETENTION_DAYS = 7

# HTTP methods
HTTP_METHOD_GET = "GET"

# Status messages
STATUS_HEALTHY = "healthy"
SERVICE_NAME = "swag-mcp"
