"""Tests for middleware components to improve coverage."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError
from swag_mcp.middleware.error_handling import (
    SecurityErrorMiddleware,
    create_user_friendly_error,
    get_error_handling_middleware,
    get_security_error_middleware,
    sanitize_error_message,
)
from swag_mcp.middleware.rate_limiting import (
    get_rate_limiting_middleware,
    get_sliding_window_rate_limiting_middleware,
)
from swag_mcp.services.errors import SwagServiceError


class TestErrorHandling:
    """Test error handling utilities."""

    def test_sanitize_error_message(self):
        """Test error message sanitization."""
        # Safe message
        safe_msg = "Invalid port number"
        result = sanitize_error_message(safe_msg)
        assert result == safe_msg

        # Message with sensitive patterns
        sensitive_msg = "Error in /etc/passwd with password=secret123"
        result = sanitize_error_message(sensitive_msg)
        assert "[REDACTED]" in result
        assert "password=secret123" not in result
        assert "/etc/passwd" not in result

    def test_create_user_friendly_error(self):
        """Test creation of user-friendly error messages."""
        # ValidationError - create directly without complex try-except
        from pydantic import BaseModel, Field

        class TestModel(BaseModel):
            port: int = Field(gt=0)

        with pytest.raises(ValidationError) as exc_info:
            TestModel(port=0)  # This will raise ValidationError

        validation_error = exc_info.value
        result = create_user_friendly_error(validation_error)
        assert "Port number must be between" in result or "Invalid" in result

        # FileNotFoundError
        error = FileNotFoundError("test.conf not found")
        result = create_user_friendly_error(error)
        assert "not found" in result.lower()

        # PermissionError
        permission_error = PermissionError("Permission denied")
        result = create_user_friendly_error(permission_error)
        assert "Access denied" in result or "permission" in result.lower()

    def test_security_error_middleware_creation(self):
        """Test security error middleware creation."""
        middleware = get_security_error_middleware()
        assert isinstance(middleware, SecurityErrorMiddleware)

    def test_error_handling_middleware_creation(self):
        """Test error handling middleware creation."""
        middleware = get_error_handling_middleware()
        assert middleware is not None


class TestRateLimitingMiddleware:
    """Test rate limiting middleware configuration."""

    def test_get_rate_limiting_middleware_disabled(self):
        """Test rate limiting middleware when disabled."""
        with patch("swag_mcp.middleware.rate_limiting.config") as mock_config:
            mock_config.rate_limit_enabled = False

            middleware = get_rate_limiting_middleware()
            assert middleware is None

    def test_get_rate_limiting_middleware_enabled(self):
        """Test rate limiting middleware when enabled."""
        with patch("swag_mcp.middleware.rate_limiting.config") as mock_config:
            mock_config.rate_limit_enabled = True
            mock_config.rate_limit_rps = 10.0
            mock_config.rate_limit_burst = 20

            middleware = get_rate_limiting_middleware()
            assert middleware is not None

    def test_get_sliding_window_middleware_disabled(self):
        """Test sliding window middleware when disabled."""
        with patch("swag_mcp.middleware.rate_limiting.config") as mock_config:
            mock_config.rate_limit_enabled = False

            middleware = get_sliding_window_rate_limiting_middleware()
            assert middleware is None

    def test_get_sliding_window_middleware_enabled(self):
        """Test sliding window middleware when enabled."""
        with patch("swag_mcp.middleware.rate_limiting.config") as mock_config:
            mock_config.rate_limit_enabled = True
            mock_config.rate_limit_rps = 10.0

            middleware = get_sliding_window_rate_limiting_middleware()
            assert middleware is not None


class TestMiddlewareUtilities:
    """Test middleware utility functions."""

    def test_empty_error_message_sanitization(self):
        """Test sanitization of empty error messages."""
        result = sanitize_error_message("")
        assert result == "Invalid request parameters"

        result = sanitize_error_message("   ")
        assert result == "Invalid request parameters"

    def test_long_error_message_truncation(self):
        """Test truncation of overly long error messages."""
        long_message = "A" * 600  # Longer than 500 char limit
        result = sanitize_error_message(long_message)
        assert len(result) <= 500
        assert result.endswith("...")

    def test_multiple_redaction_cleanup(self):
        """Test cleanup of multiple consecutive redactions."""
        message_with_multiple = "Error password=secret token=abc key=123 end"
        result = sanitize_error_message(message_with_multiple)
        # Should not have multiple consecutive [REDACTED] entries
        assert "[REDACTED] [REDACTED]" not in result

    def test_error_message_pattern_matching(self):
        """Test specific error message pattern matching."""
        patterns_to_test = [
            ("File /etc/passwd not found", "/etc/passwd"),
            ("Connection to 192.168.1.1:8080 failed", "192.168.1.1:8080"),
            ("Template {{config.evil}} failed", "{{config.evil}}"),
            ("Query SELECT * FROM users", "SELECT * FROM users"),
        ]

        for message, pattern in patterns_to_test:
            result = sanitize_error_message(message)
            assert pattern not in result
            assert "[REDACTED]" in result

    def test_swag_service_error_handling(self):
        """Test SwagServiceError handling."""
        error = SwagServiceError("Configuration template not found")
        result = create_user_friendly_error(error)
        assert "Configuration template not found" in result

    def test_timeout_error_handling(self):
        """Test TimeoutError handling."""
        error = TimeoutError("Operation timed out after 30s")
        result = create_user_friendly_error(error)
        assert "timed out" in result.lower()

    def test_generic_exception_handling(self):
        """Test handling of generic exceptions."""
        error = ValueError("Unexpected value error")
        result = create_user_friendly_error(error)
        # Should sanitize but still be informative
        assert isinstance(result, str)
        assert len(result) > 0

    def test_dangerous_pattern_sanitization(self):
        """Test sanitization of dangerous patterns."""
        dangerous_patterns = [
            "{{7*7}}",  # Template injection
            "eval('malicious code')",  # Code execution
            "/etc/passwd",  # File paths
            "password=secret123",  # Credentials
            "127.0.0.1:8080",  # Internal services
        ]

        for pattern in dangerous_patterns:
            result = sanitize_error_message(f"Error: {pattern}")
            assert pattern not in result
            assert "[REDACTED]" in result

    def test_unicode_error_handling(self):
        """Test handling of Unicode characters in error messages."""
        unicode_message = "Error with café and naïve characters"
        result = sanitize_error_message(unicode_message)
        assert isinstance(result, str)
        assert len(result) > 0

        # Should preserve non-dangerous Unicode
        assert "café" in result or "caf" in result
        assert "naïve" in result or "na" in result
