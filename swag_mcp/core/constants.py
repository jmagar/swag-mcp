"""Constants used throughout the SWAG MCP server."""

# File patterns and extensions
CONF_PATTERN = "*.conf"
SAMPLE_PATTERN = "*.sample"
CONF_EXTENSION = ".conf"
SAMPLE_EXTENSION = ".sample"
BACKUP_MARKER = ".backup."

# Validation regex patterns
VALID_NAME_PATTERN = r"^[\w-]+$"  # Service names, alphanumeric + hyphens/underscores
VALID_UPSTREAM_PATTERN = r"^[a-zA-Z0-9_.\[\]:-]+$"  # Container names/IP addresses, IPv6 support
VALID_CONFIG_NAME_PATTERN = r"^[a-zA-Z0-9_.-]+\.(conf|sample)$"  # Config filenames
VALID_CONFIG_ONLY_PATTERN = r"^[a-zA-Z0-9_.-]+\.conf$"  # Only .conf files
VALID_CONFIG_NAME_FORMAT = (
    r"^[a-zA-Z0-9_-]+\.(subdomain|subfolder)\.conf$"  # Full config filename format
)

# Configuration types
CONFIG_TYPE_SUBDOMAIN = "subdomain"
CONFIG_TYPE_SUBFOLDER = "subfolder"
CONFIG_TYPE_MCP_SUBDOMAIN = "mcp-subdomain"
CONFIG_TYPE_MCP_SUBFOLDER = "mcp-subfolder"

# Configuration types tuple for efficient validation and iteration
CONFIG_TYPES = (
    CONFIG_TYPE_SUBDOMAIN,
    CONFIG_TYPE_SUBFOLDER,
    CONFIG_TYPE_MCP_SUBDOMAIN,
    CONFIG_TYPE_MCP_SUBFOLDER,
)

# Backwards-compat alias (if referenced elsewhere)
ALL_CONFIG_TYPES = list(CONFIG_TYPES)

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
AUTH_METHOD_BASIC = "basic"
AUTH_METHOD_AUTHELIA = "authelia"
AUTH_METHOD_LDAP = "ldap"
AUTH_METHOD_AUTHENTIK = "authentik"
AUTH_METHOD_TINYAUTH = "tinyauth"

# All available authentication methods
AUTH_METHODS = (
    AUTH_METHOD_NONE,
    AUTH_METHOD_BASIC,
    AUTH_METHOD_AUTHELIA,
    AUTH_METHOD_LDAP,
    AUTH_METHOD_AUTHENTIK,
    AUTH_METHOD_TINYAUTH,
)

# List filter options
LIST_FILTERS = ["all", "active", "samples"]
DEFAULT_LIST_FILTER = "all"

# Default values
DEFAULT_AUTH_METHOD = AUTH_METHOD_AUTHELIA
DEFAULT_HOST = "127.0.0.1"
DEFAULT_LOG_LEVEL = "INFO"

# MCP-specific default constants
DEFAULT_MCP_PATH = "/mcp"  # Default MCP endpoint path
DEFAULT_MCP_STREAM_TIMEOUT = 86400  # 24 hours in seconds for long-running AI operations
DEFAULT_MCP_SESSION_TIMEOUT = 3600  # 1 hour in seconds for session management

# Path validation regex - prevents traversal attacks while allowing valid paths
LOCATION_PATH_REGEX = r"^[a-zA-Z0-9/_.-]+$"  # Alphanumerics, slashes, underscores, hyphens, dots

# Domain validation pattern (RFC compliant)
DOMAIN_PATTERN = (
    r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
    r"(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
)

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
