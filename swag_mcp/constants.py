"""Constants for SWAG MCP server."""

# Server configuration
DEFAULT_PORT = 8000
DEFAULT_HOST = "127.0.0.1"
HEALTH_CHECK_PATH = "/health"
MCP_ENDPOINT_PATH = "/mcp"

# Timeouts (in seconds)
DEFAULT_TIMEOUT = 30
HEALTH_CHECK_TIMEOUT = 15
DOCKER_COMMAND_TIMEOUT = 30
DEFAULT_HEALTH_CHECK_INTERVAL = 30
HEALTH_CHECK_START_PERIOD = 5
HEALTH_CHECK_RETRIES = 3

# Rate limiting
DEFAULT_RATE_LIMIT_RPS = 10.0
DEFAULT_RATE_LIMIT_BURST = 20

# Logging
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_MAX_BYTES = 10485760  # 10MB
DEFAULT_PAYLOAD_MAX_LENGTH = 1000
SLOW_OPERATION_THRESHOLD_MS = 1000

# Docker container names to try
SWAG_CONTAINER_NAMES = ["swag", "letsencrypt", "nginx", "swag-nginx"]

# File operations
DEFAULT_BACKUP_RETENTION_DAYS = 30
MAX_LOG_LINES = 1000
DEFAULT_LOG_LINES = 100
MIN_LOG_LINES = 1

# Port ranges
MIN_PORT = 1
MAX_PORT = 65535

# String length limits
MAX_SERVICE_NAME_LENGTH = 50
MAX_DOMAIN_LENGTH = 253
MAX_UPSTREAM_APP_LENGTH = 100
MAX_CONFIG_CONTENT_LENGTH = 1000000  # 1MB

# Template types
TEMPLATE_SUBDOMAIN = "subdomain"
TEMPLATE_SUBFOLDER = "subfolder"
TEMPLATE_MCP_SUBDOMAIN = "mcp-subdomain"
TEMPLATE_MCP_SUBFOLDER = "mcp-subfolder"

# Authentication methods
AUTH_NONE = "none"
AUTH_LDAP = "ldap"
AUTH_AUTHELIA = "authelia"
AUTH_AUTHENTIK = "authentik"
AUTH_TINYAUTH = "tinyauth"

# Upstream protocols
PROTO_HTTP = "http"
PROTO_HTTPS = "https"

# Config types for listing
CONFIG_TYPE_ALL = "all"
CONFIG_TYPE_ACTIVE = "active"
CONFIG_TYPE_SAMPLES = "samples"

# File extensions
CONF_EXTENSION = ".conf"
SAMPLE_EXTENSION = ".sample"
BACKUP_PATTERN = ".backup."
JINJA2_EXTENSION = ".j2"

# Regex patterns
SERVICE_NAME_PATTERN = r"^[a-zA-Z0-9_-]+$"
UPSTREAM_APP_PATTERN = r"^[a-zA-Z0-9_.-]+$"
CONFIG_FILE_PATTERN = r"^[a-zA-Z0-9_.-]+\.(conf|sample)$"
ACTIVE_CONFIG_PATTERN = r"^[a-zA-Z0-9_.-]+\.conf$"
BACKUP_FILE_PATTERN = r"^.+\.backup\.\d{8}_\d{6}$"

# HTTP status codes for health checks
HTTP_OK_MIN = 200
HTTP_OK_MAX = 299
HTTP_NOT_ACCEPTABLE = 406
HTTP_NOT_FOUND = 404

# Retry configuration
DEFAULT_MAX_RETRIES = 3
RETRY_EXCEPTIONS = (ConnectionError, TimeoutError, OSError)

# Response truncation
RESPONSE_BODY_MAX_LENGTH = 1000

# Environment variable prefixes
ENV_PREFIX = "SWAG_MCP_"

# Default values
DEFAULT_AUTH_METHOD = AUTH_AUTHELIA
DEFAULT_CONFIG_TYPE = TEMPLATE_SUBDOMAIN
DEFAULT_QUIC_ENABLED = False