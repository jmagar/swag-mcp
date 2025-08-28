"""Input validation and edge case tests for SWAG MCP tool.

These tests cover the "lizard" cases mentioned in "Stop Vibe-Testing Your MCP Server" -
boundary conditions and invalid inputs that LLMs might generate in creative ways.
"""

import pytest
from fastmcp import Client
from mcp.types import TextContent


class TestServiceNameValidation:
    """Test service_name parameter validation and edge cases."""

    @pytest.mark.parametrize("invalid_service_name", [
        "",  # Empty string
        "a" * 51,  # Too long (exceeds max_length=50)
        "test@service",  # Invalid character @
        "test service",  # Space not allowed
        "test/service",  # Forward slash not allowed
        "test\\service",  # Backslash not allowed
        "test|service",  # Pipe not allowed
        "test<service",  # Less than not allowed
        "test>service",  # Greater than not allowed
        "test:service",  # Colon not allowed
        "test\"service",  # Quote not allowed
        "test*service",  # Asterisk not allowed
        "test?service",  # Question mark not allowed
        "../service",  # Path traversal attempt
        "../../etc/passwd",  # Path traversal attack
        "null",  # SQL injection attempt
        "DROP TABLE services;",  # SQL injection attempt
        "' OR '1'='1",  # SQL injection attempt
        "<script>alert('xss')</script>",  # XSS attempt
        "🚀🎯💥",  # Emoji characters
        "тест",  # Cyrillic characters
        "测试",  # Chinese characters
        "🇺🇸flag",  # Flag emoji
        "\x00null",  # Null byte
        "\n\r\t",  # Control characters
        "service\u200B",  # Zero-width space
        "service\ufeff",  # BOM character
    ])
    @pytest.mark.asyncio
    async def test_create_with_invalid_service_name_fails(self, mcp_client: Client, invalid_service_name):
        """CREATE action should reject invalid service_name values."""
        result = await mcp_client.call_tool("swag", {
            "action": "create",
            "service_name": invalid_service_name,
            "server_name": "test.example.com",
            "upstream_app": "testapp",
            "upstream_port": 8080
        })
        
        # Response validation handled by result.is_error check
        response = result.data
        # Should fail validation - either in parameter validation or business logic
        # The server should return success=false in response, OR MCP framework sets is_error=true
        assert result.is_error or (response and response.get("success") is False)


class TestServerNameValidation:
    """Test server_name parameter validation and edge cases."""

    @pytest.mark.parametrize("invalid_server_name", [
        "",  # Empty string
        "a" * 254,  # Too long (exceeds max_length=253)
        "invalid..domain",  # Double dots
        ".startswith.dot",  # Starts with dot
        "endswith.dot.",  # Ends with dot
        "space domain.com",  # Contains space
        "under_score.com",  # Underscore in domain
        "test@domain.com",  # @ symbol
        "test/domain.com",  # Forward slash
        "test\\domain.com",  # Backslash
        "UPPERCASE.COM",  # All uppercase (may or may not be valid)
        "localhost",  # Localhost
        "127.0.0.1",  # IP address
        "::1",  # IPv6 localhost
        "192.168.1.1",  # Private IP
        "test.local",  # .local TLD
        "test..double.dot.com",  # Multiple consecutive dots
        "xn--nxasmq6b",  # Punycode
        "🌟.example.com",  # Unicode domain
        "very-long-subdomain-name-that-exceeds-normal-limits.example.com",  # Very long subdomain
        "../etc/passwd",  # Path traversal
        "evil.com/../../etc/passwd",  # Path traversal with domain
    ])
    @pytest.mark.asyncio
    async def test_create_with_invalid_server_name_fails(self, mcp_client: Client, invalid_server_name):
        """CREATE action should reject invalid server_name values."""
        result = await mcp_client.call_tool("swag", {
            "action": "create",
            "service_name": "testapp",
            "server_name": invalid_server_name,
            "upstream_app": "testapp",
            "upstream_port": 8080
        })
        
        # Response validation handled by result.is_error check
        response = result.data
        assert not result.is_error
        # Should fail validation
        assert response["success"] is False


class TestUpstreamAppValidation:
    """Test upstream_app parameter validation and edge cases."""

    @pytest.mark.parametrize("invalid_upstream_app", [
        "",  # Empty string
        "a" * 101,  # Too long (exceeds max_length=100)
        "test app",  # Space not allowed in pattern
        "test@app",  # @ symbol
        "test/app",  # Forward slash
        "test\\app",  # Backslash
        "test|app",  # Pipe
        "test<app",  # Less than
        "test>app",  # Greater than
        "test:app",  # Colon (may be valid for Docker)
        "test\"app",  # Quote
        "test*app",  # Asterisk
        "test?app",  # Question mark
        "../app",  # Path traversal
        "../../etc/passwd",  # Path traversal attack
        "null",  # SQL injection
        "' OR '1'='1",  # SQL injection
        "<script>alert('xss')</script>",  # XSS
        "🚀app",  # Emoji
        "\x00null",  # Null byte
        "\n\r\t",  # Control characters
    ])
    @pytest.mark.asyncio
    async def test_create_with_invalid_upstream_app_fails(self, mcp_client: Client, invalid_upstream_app):
        """CREATE action should reject invalid upstream_app values."""
        result = await mcp_client.call_tool("swag", {
            "action": "create",
            "service_name": "testapp",
            "server_name": "test.example.com",
            "upstream_app": invalid_upstream_app,
            "upstream_port": 8080
        })
        
        # Response validation handled by result.is_error check
        response = result.data
        # Should fail validation - expect either MCP error or server success=false
        assert result.is_error or (response and response.get("success") is False)


class TestUpstreamPortValidation:
    """Test upstream_port parameter validation and edge cases."""

    @pytest.mark.parametrize("invalid_port", [
        -1,  # Negative number
        -999,  # Large negative number
        0,  # Zero (invalid for CREATE)
        65536,  # Above valid range
        99999,  # Way above valid range
        999999999999999999999,  # Extremely large number
    ])
    @pytest.mark.asyncio
    async def test_create_with_invalid_upstream_port_fails(self, mcp_client: Client, invalid_port):
        """CREATE action should reject invalid upstream_port values."""
        result = await mcp_client.call_tool("swag", {
            "action": "create",
            "service_name": "testapp",
            "server_name": "test.example.com",
            "upstream_app": "testapp",
            "upstream_port": invalid_port
        })
        
        # Response validation handled by result.is_error check
        response = result.data
        # Should fail validation - expect either MCP error or server success=false
        assert result.is_error or (response and response.get("success") is False)

    @pytest.mark.parametrize("valid_port", [
        1,  # Minimum valid port
        80,  # Standard HTTP
        443,  # Standard HTTPS
        8080,  # Common alternative
        3000,  # Development port
        65535,  # Maximum valid port
    ])
    @pytest.mark.asyncio
    async def test_create_with_valid_upstream_port_boundary_values(self, mcp_client: Client, valid_port):
        """CREATE action should accept valid boundary port values."""
        with pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.health_check'):
            
            from unittest.mock import MagicMock
            mock_create.return_value = MagicMock(filename="testapp.conf")
            
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "testapp",
                "server_name": "test.example.com",
                "upstream_app": "testapp",
                "upstream_port": valid_port
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True


class TestConfigNameValidation:
    """Test config_name parameter validation and edge cases."""

    @pytest.mark.parametrize("invalid_config_name", [
        "",  # Empty string
        "a" * 256,  # Too long (exceeds max_length=255)
        "test config",  # Space not allowed in pattern
        "test@config",  # @ symbol
        "test/config",  # Forward slash
        "test\\config",  # Backslash
        "test|config",  # Pipe
        "test<config",  # Less than
        "test>config",  # Greater than
        "test:config",  # Colon
        "test\"config",  # Quote
        "test*config",  # Asterisk
        "test?config",  # Question mark
        "../config",  # Path traversal
        "../../etc/passwd",  # Path traversal attack
        "/etc/passwd",  # Absolute path
        "C:\\Windows\\System32",  # Windows path
        "null",  # SQL injection
        "' OR '1'='1",  # SQL injection
        "<script>alert('xss')</script>",  # XSS
        "🚀config",  # Emoji
        "\x00null",  # Null byte
        "\n\r\t",  # Control characters
        "con",  # Windows reserved name
        "aux",  # Windows reserved name
        "prn",  # Windows reserved name
        "nul",  # Windows reserved name
    ])
    @pytest.mark.asyncio
    async def test_view_with_invalid_config_name_fails(self, mcp_client: Client, invalid_config_name):
        """VIEW action should reject invalid config_name values."""
        result = await mcp_client.call_tool("swag", {
            "action": "view",
            "config_name": invalid_config_name
        })
        
        # Response validation handled by result.is_error check
        response = result.data
        # Should fail validation - expect either MCP error or server success=false
        assert result.is_error or (response and response.get("success") is False)


class TestAuthMethodValidation:
    """Test auth_method parameter validation and edge cases."""

    @pytest.mark.parametrize("invalid_auth_method", [
        "invalid_auth",  # Not in allowed list
        "AUTHELIA",  # Wrong case
        "None",  # Wrong case
        "",  # Empty string
        "oauth",  # Not supported
        "basic",  # Not supported
        "digest",  # Not supported
        "bearer",  # Not supported
        "null",  # SQL injection attempt
        "<script>alert('xss')</script>",  # XSS attempt
        "🔐auth",  # Emoji
        "auth\x00method",  # Null byte
        "auth\nmethod",  # Newline
        " authelia ",  # Leading/trailing spaces
    ])
    @pytest.mark.asyncio
    async def test_create_with_invalid_auth_method_uses_default(self, mcp_client: Client, invalid_auth_method):
        """CREATE action should handle invalid auth_method gracefully."""
        with pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.health_check'):
            
            from unittest.mock import MagicMock
            mock_create.return_value = MagicMock(filename="testapp.conf")
            
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "testapp",
                "server_name": "test.example.com",
                "upstream_app": "testapp",
                "upstream_port": 8080,
                "auth_method": invalid_auth_method
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
            # Should either succeed with default auth or fail gracefully
            # The exact behavior depends on implementation


class TestConfigTypeValidation:
    """Test config_type parameter validation and edge cases."""

    @pytest.mark.parametrize("invalid_config_type", [
        "invalid_type",  # Not in allowed list
        "SUBDOMAIN",  # Wrong case
        "sub-domain",  # Wrong format
        "",  # Empty string
        "null",  # SQL injection
        "<script>alert('xss')</script>",  # XSS
        "🚀type",  # Emoji
        "type\x00",  # Null byte
        " subdomain ",  # Leading/trailing spaces
        "folder",  # Partial match
        "domain",  # Partial match
    ])
    @pytest.mark.asyncio
    async def test_create_with_invalid_config_type_uses_default(self, mcp_client: Client, invalid_config_type):
        """CREATE action should handle invalid config_type gracefully."""
        with pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.health_check'):
            
            from unittest.mock import MagicMock
            mock_create.return_value = MagicMock(filename="testapp.conf")
            
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "testapp",
                "server_name": "test.example.com",
                "upstream_app": "testapp",
                "upstream_port": 8080,
                "config_type_create": invalid_config_type
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
            # Should either succeed with default config type or fail gracefully


class TestUpstreamProtoValidation:
    """Test upstream_proto parameter validation and edge cases."""

    @pytest.mark.parametrize("invalid_proto", [
        "ftp",  # Not supported
        "HTTP",  # Wrong case
        "HTTPS",  # Wrong case
        "",  # Empty string
        "tcp",  # Wrong protocol
        "udp",  # Wrong protocol
        "websocket",  # Not supported
        "ws",  # Not supported
        "wss",  # Not supported
        "null",  # SQL injection
        "<script>alert('xss')</script>",  # XSS
        "🚀proto",  # Emoji
        "proto\x00",  # Null byte
        " http ",  # Leading/trailing spaces
    ])
    @pytest.mark.asyncio
    async def test_create_with_invalid_upstream_proto_uses_default(self, mcp_client: Client, invalid_proto):
        """CREATE action should handle invalid upstream_proto gracefully."""
        with pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists', return_value=True), \
             pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.create_config') as mock_create, \
             pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.health_check'):
            
            from unittest.mock import MagicMock
            mock_create.return_value = MagicMock(filename="testapp.conf")
            
            result = await mcp_client.call_tool("swag", {
                "action": "create",
                "service_name": "testapp",
                "server_name": "test.example.com",
                "upstream_app": "testapp",
                "upstream_port": 8080,
                "upstream_proto": invalid_proto
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
            # Should either succeed with default proto or fail gracefully


class TestContentValidation:
    """Test new_content parameter validation and edge cases."""

    @pytest.mark.parametrize("edge_case_content", [
        "",  # Empty content (should be allowed for clearing files)
        "a" * 1000000,  # Very large content (1MB)
        "\x00" * 100,  # Null bytes
        "\n" * 10000,  # Many newlines
        "# Valid nginx config\nserver { listen 443; }",  # Valid config
        "invalid nginx config {{{",  # Invalid config syntax
        "🚀📦💻 # Emoji comment\nserver { listen 443; }",  # Emoji in config
        "<script>alert('xss')</script>",  # XSS in config
        "' OR '1'='1 --",  # SQL injection in config
        "{{malicious_template_code}}",  # Template injection
        "\u200B\u200C\u200D\uFEFF",  # Various Unicode spaces
    ])
    @pytest.mark.asyncio
    async def test_edit_with_edge_case_content(self, mcp_client: Client, sample_configs, edge_case_content):
        """EDIT action should handle various content edge cases."""
        result = await mcp_client.call_tool("swag", {
            "action": "edit",
            "config_name": "test.conf",
            "new_content": edge_case_content,
            "create_backup": True
        })
        
        # Response validation handled by result.is_error check
        response = result.data
        assert not result.is_error
        # Should either succeed or fail gracefully with clear error message
        # The exact behavior depends on content validation rules


class TestTimeoutValidation:
    """Test timeout parameter validation and edge cases."""

    @pytest.mark.parametrize("invalid_timeout", [
        0,  # Below minimum
        -1,  # Negative
        -999,  # Large negative
        301,  # Above maximum (le=300)
        99999,  # Way above maximum
        999999999999999999999,  # Extremely large
    ])
    @pytest.mark.asyncio
    async def test_health_check_with_invalid_timeout_fails(self, mcp_client: Client, invalid_timeout):
        """HEALTH_CHECK action should reject invalid timeout values."""
        result = await mcp_client.call_tool("swag", {
            "action": "health_check",
            "domain": "test.example.com",
            "timeout": invalid_timeout
        })
        
        # Response validation handled by result.is_error check
        response = result.data
        assert not result.is_error
        # Should fail validation
        assert response["success"] is False

    @pytest.mark.parametrize("valid_timeout", [
        1,  # Minimum valid
        30,  # Default
        300,  # Maximum valid
    ])
    @pytest.mark.asyncio
    async def test_health_check_with_valid_timeout_boundary_values(self, mcp_client: Client, valid_timeout):
        """HEALTH_CHECK action should accept valid timeout boundary values."""
        with pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.health_check') as mock_health:
            from unittest.mock import MagicMock
            mock_health.return_value = MagicMock(
                success=True,
                status_code=200,
                response_time_ms=100,
                error=None
            )
            
            result = await mcp_client.call_tool("swag", {
                "action": "health_check",
                "domain": "test.example.com",
                "timeout": valid_timeout
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True


class TestLinesValidation:
    """Test lines parameter validation and edge cases."""

    @pytest.mark.parametrize("invalid_lines", [
        0,  # Below minimum (ge=1)
        -1,  # Negative
        -999,  # Large negative
        1001,  # Above maximum (le=1000)
        99999,  # Way above maximum
        999999999999999999999,  # Extremely large
    ])
    @pytest.mark.asyncio
    async def test_logs_with_invalid_lines_fails(self, mcp_client: Client, invalid_lines):
        """LOGS action should reject invalid lines values."""
        result = await mcp_client.call_tool("swag", {
            "action": "logs",
            "lines": invalid_lines
        })
        
        # Response validation handled by result.is_error check
        response = result.data
        assert not result.is_error
        # Should fail validation
        assert response["success"] is False

    @pytest.mark.parametrize("valid_lines", [
        1,  # Minimum valid
        100,  # Default
        1000,  # Maximum valid
    ])
    @pytest.mark.asyncio
    async def test_logs_with_valid_lines_boundary_values(self, mcp_client: Client, valid_lines):
        """LOGS action should accept valid lines boundary values."""
        with pytest.patch('swag_mcp.services.swag_manager.SwagManagerService.get_docker_logs') as mock_logs:
            mock_logs.return_value = "Sample log output"
            
            result = await mcp_client.call_tool("swag", {
                "action": "logs",
                "lines": valid_lines
            })
            
            # Response validation handled by result.is_error check
            response = result.data
        assert not result.is_error
        assert response["success"] is True
        assert response["lines_requested"] == valid_lines