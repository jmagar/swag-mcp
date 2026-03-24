"""URI parsing for SWAG MCP remote server support.

Parses URIs in scp/rsync-style format:
- Local: /path/to/dir
- Remote: hostname:/path/to/dir
- Remote with user: user@hostname:/path/to/dir
- Remote with port: hostname:22:/path/to/dir
- Remote full: user@hostname:22:/path/to/dir
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedURI:
    """Parsed SWAG path URI."""

    is_remote: bool
    host: str | None = None
    port: int = 22
    username: str | None = None
    path: str = ""


# Pattern: [user@]host[:port]:/path
# Host cannot start with / (that would be a local path)
# Port is numeric and optional between host and :/path
_REMOTE_PATTERN = re.compile(
    r"^(?:(?P<username>[a-zA-Z0-9_][\w.-]*)@)?"  # optional user@
    r"(?P<host>[a-zA-Z0-9][\w.-]*)"  # hostname (must start with alphanumeric)
    r"(?::(?P<port>\d+))?"  # optional :port
    r":(?P<path>/.+)$"  # :/absolute/path (required)
)


def parse_swag_uri(uri: str) -> ParsedURI:
    """Parse a SWAG path URI into its components.

    Supports two formats:
    - Local path: ``/path/to/dir`` (absolute path starting with /)
    - Remote path: ``[user@]host[:port]:/path/to/dir``

    Args:
        uri: The URI string to parse

    Returns:
        ParsedURI with parsed components

    Raises:
        ValueError: If the URI format is invalid

    """
    if not uri or not uri.strip():
        raise ValueError("URI cannot be empty")

    uri = uri.strip()

    # Local path: starts with /
    if uri.startswith("/"):
        return ParsedURI(is_remote=False, path=uri)

    # Try remote pattern
    match = _REMOTE_PATTERN.match(uri)
    if match:
        port_str = match.group("port")
        port = int(port_str) if port_str else 22

        if not (1 <= port <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got: {port}")

        return ParsedURI(
            is_remote=True,
            host=match.group("host"),
            port=port,
            username=match.group("username"),
            path=match.group("path"),
        )

    # Neither local nor valid remote
    raise ValueError(
        f"Invalid URI format: '{uri}'. "
        "Expected local path (/path/to/dir) or remote (host:/path/to/dir)"
    )
