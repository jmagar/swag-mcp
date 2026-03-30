"""Tests for URI parsing module."""

import pytest
from swag_mcp.utils.uri import ParsedURI, parse_swag_uri


class TestParseSwagUri:
    """Tests for parse_swag_uri function."""

    def test_local_absolute_path(self):
        """Test parsing a simple local absolute path."""
        result = parse_swag_uri("/swag/nginx/proxy-confs")
        assert result == ParsedURI(is_remote=False, path="/swag/nginx/proxy-confs")

    def test_local_root_path(self):
        """Test parsing root path."""
        result = parse_swag_uri("/")
        assert result == ParsedURI(is_remote=False, path="/")

    def test_remote_simple(self):
        """Test parsing simple remote URI."""
        result = parse_swag_uri("squirts:/mnt/appdata/swag/nginx/proxy-confs")
        assert result == ParsedURI(
            is_remote=True,
            host="squirts",
            port=22,
            username=None,
            path="/mnt/appdata/swag/nginx/proxy-confs",
        )

    def test_remote_with_user(self):
        """Test parsing remote URI with username."""
        result = parse_swag_uri("admin@myhost:/path/to/confs")
        assert result == ParsedURI(
            is_remote=True,
            host="myhost",
            port=22,
            username="admin",
            path="/path/to/confs",
        )

    def test_remote_with_port(self):
        """Test parsing remote URI with custom port."""
        result = parse_swag_uri("myhost:2222:/path/to/confs")
        assert result == ParsedURI(
            is_remote=True,
            host="myhost",
            port=2222,
            username=None,
            path="/path/to/confs",
        )

    def test_remote_full(self):
        """Test parsing fully qualified remote URI."""
        result = parse_swag_uri("jmagar@squirts:2222:/mnt/appdata/swag/nginx/proxy-confs")
        assert result == ParsedURI(
            is_remote=True,
            host="squirts",
            port=2222,
            username="jmagar",
            path="/mnt/appdata/swag/nginx/proxy-confs",
        )

    def test_remote_with_dots_in_hostname(self):
        """Test parsing remote URI with FQDN hostname."""
        result = parse_swag_uri("swag.example.com:/etc/nginx/proxy-confs")
        assert result == ParsedURI(
            is_remote=True,
            host="swag.example.com",
            port=22,
            username=None,
            path="/etc/nginx/proxy-confs",
        )

    def test_remote_with_ip(self):
        """Test parsing remote URI with IP address."""
        result = parse_swag_uri("192.168.1.100:/mnt/data/swag")
        assert result == ParsedURI(
            is_remote=True,
            host="192.168.1.100",
            port=22,
            username=None,
            path="/mnt/data/swag",
        )

    def test_empty_uri_raises(self):
        """Test that empty URI raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_swag_uri("")

    def test_whitespace_uri_raises(self):
        """Test that whitespace-only URI raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_swag_uri("   ")

    def test_relative_path_raises(self):
        """Test that relative path raises ValueError."""
        with pytest.raises(ValueError, match="Invalid URI format"):
            parse_swag_uri("relative/path")

    def test_invalid_port_raises(self):
        """Test that invalid port raises ValueError."""
        with pytest.raises(ValueError, match="Port must be between"):
            parse_swag_uri("host:99999:/path")

    def test_strips_whitespace(self):
        """Test that surrounding whitespace is stripped."""
        result = parse_swag_uri("  /path/to/dir  ")
        assert result.path == "/path/to/dir"

    def test_frozen_dataclass(self):
        """Test that ParsedURI is immutable."""
        result = parse_swag_uri("/path")
        with pytest.raises(AttributeError):
            result.path = "/other"  # type: ignore[misc]
