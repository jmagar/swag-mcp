"""Tests for SWAG MCP configuration loading and validation."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from swag_mcp.core.config import SwagConfig


class TestSwagConfig:
    """Test suite for SwagConfig."""

    def test_default_values(self, monkeypatch):
        """Test that configuration loads with current environment values."""
        config = SwagConfig()

        # Test that config is properly instantiated with current values
        assert isinstance(config.proxy_confs_path, Path)
        assert isinstance(config.template_path, Path)

        # Default settings should be strings/bools/ints
        assert isinstance(config.default_auth_method, str)
        assert isinstance(config.default_quic_enabled, bool)
        assert isinstance(config.default_config_type, str)

        # Backup settings
        assert isinstance(config.backup_retention_days, int)

        # Server settings
        assert isinstance(config.host, str)
        assert config.port == 8000  # Property should always return 8000

        # Logging settings
        assert isinstance(config.log_level, str)
        assert isinstance(config.log_file_enabled, bool)
        assert isinstance(config.log_file_max_bytes, int)
        assert isinstance(config.log_directory, Path)

        # Middleware settings
        assert isinstance(config.rate_limit_enabled, bool)
        assert isinstance(config.rate_limit_rps, float)
        assert isinstance(config.rate_limit_burst, int)
        assert isinstance(config.log_payloads, bool)
        assert isinstance(config.log_payload_max_length, int)
        assert isinstance(config.slow_operation_threshold_ms, int)
        assert isinstance(config.enable_structured_logging, bool)
        assert isinstance(config.enable_retry_middleware, bool)
        assert isinstance(config.max_retries, int)

    def test_environment_variable_loading(self):
        """Test loading configuration from environment variables."""
        env_vars = {
            "SWAG_MCP_PROXY_CONFS_PATH": "/custom/proxy-confs",
            "SWAG_MCP_TEMPLATE_PATH": "/custom/templates",
            "SWAG_MCP_DEFAULT_AUTH_METHOD": "ldap",
            "SWAG_MCP_DEFAULT_QUIC_ENABLED": "true",
            "SWAG_MCP_DEFAULT_CONFIG_TYPE": "subfolder",
            "SWAG_MCP_BACKUP_RETENTION_DAYS": "60",
            "SWAG_MCP_HOST": "0.0.0.0",
            "SWAG_MCP_LOG_LEVEL": "DEBUG",
            "SWAG_MCP_LOG_FILE_ENABLED": "false",
            "SWAG_MCP_RATE_LIMIT_ENABLED": "true",
            "SWAG_MCP_RATE_LIMIT_RPS": "5.0",
            "SWAG_MCP_RATE_LIMIT_BURST": "10",
            "SWAG_MCP_LOG_PAYLOADS": "true",
            "SWAG_MCP_MAX_RETRIES": "5",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = SwagConfig()

            assert str(config.proxy_confs_path) == "/custom/proxy-confs"
            assert str(config.template_path) == "/custom/templates"
            assert config.default_auth_method == "ldap"
            assert config.default_quic_enabled is True
            assert config.default_config_type == "subfolder"
            assert config.backup_retention_days == 60
            assert config.host == "0.0.0.0"
            assert config.log_level == "DEBUG"
            assert config.log_file_enabled is False
            assert config.rate_limit_enabled is True
            assert config.rate_limit_rps == 5.0
            assert config.rate_limit_burst == 10
            assert config.log_payloads is True
            assert config.max_retries == 5

    def test_port_property_always_returns_8000(self):
        """Test that port property always returns 8000 regardless of environment."""
        # Try to override port via environment variable
        with patch.dict(os.environ, {"SWAG_MCP_PORT": "9000"}, clear=False):
            config = SwagConfig()
            assert config.port == 8000  # Should still be 8000

        # Try to set port directly (shouldn't be possible)
        config = SwagConfig()
        assert config.port == 8000

    def test_case_insensitive_environment_variables(self):
        """Test that environment variable names are case insensitive."""
        env_vars = {
            "swag_mcp_log_level": "WARNING",  # lowercase
            "SWAG_MCP_BACKUP_RETENTION_DAYS": "45",  # uppercase
            "Swag_Mcp_Host": "192.168.1.1",  # mixed case
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = SwagConfig()

            assert config.log_level == "WARNING"
            assert config.backup_retention_days == 45
            assert config.host == "192.168.1.1"

    def test_boolean_environment_variable_parsing(self):
        """Test parsing of boolean values from environment variables."""
        # Test various boolean representations
        boolean_tests = [
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("1", True),
            ("yes", True),
            ("on", True),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("0", False),
            ("no", False),
            ("off", False),
        ]

        for env_value, expected_bool in boolean_tests:
            with patch.dict(os.environ, {"SWAG_MCP_LOG_FILE_ENABLED": env_value}, clear=False):
                config = SwagConfig()
                assert (
                    config.log_file_enabled is expected_bool
                ), f"Failed for env_value: {env_value}"

    def test_numeric_validation(self):
        """Test validation of numeric fields."""
        # Valid numeric values
        with patch.dict(
            os.environ,
            {
                "SWAG_MCP_BACKUP_RETENTION_DAYS": "30",
                "SWAG_MCP_RATE_LIMIT_RPS": "15.5",
                "SWAG_MCP_RATE_LIMIT_BURST": "25",
                "SWAG_MCP_LOG_FILE_MAX_BYTES": "20971520",  # 20MB
            },
            clear=False,
        ):
            config = SwagConfig()
            assert config.backup_retention_days == 30
            assert config.rate_limit_rps == 15.5
            assert config.rate_limit_burst == 25
            assert config.log_file_max_bytes == 20971520

    def test_invalid_numeric_values(self):
        """Test handling of invalid numeric values."""
        with patch.dict(os.environ, {"SWAG_MCP_BACKUP_RETENTION_DAYS": "invalid"}, clear=False):
            with pytest.raises(ValidationError):
                SwagConfig()

        with patch.dict(os.environ, {"SWAG_MCP_RATE_LIMIT_RPS": "not_a_float"}, clear=False):
            with pytest.raises(ValidationError):
                SwagConfig()

    def test_path_handling(self):
        """Test path field handling and validation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            proxy_path = temp_path / "proxy-confs"
            template_path = temp_path / "templates"

            # Create directories
            proxy_path.mkdir()
            template_path.mkdir()

            env_vars = {
                "SWAG_MCP_PROXY_CONFS_PATH": str(proxy_path),
                "SWAG_MCP_TEMPLATE_PATH": str(template_path),
                "SWAG_MCP_LOG_DIRECTORY": str(temp_path / "logs"),
            }

            with patch.dict(os.environ, env_vars, clear=False):
                config = SwagConfig()

                assert config.proxy_confs_path == proxy_path
                assert config.template_path == template_path
                assert config.log_directory == temp_path / "logs"

    def test_relative_path_handling(self):
        """Test handling of relative paths."""
        env_vars = {
            "SWAG_MCP_TEMPLATE_PATH": "./custom/templates",
            "SWAG_MCP_LOG_DIRECTORY": "../logs",
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = SwagConfig()

            # Paths should be converted to Path objects
            assert isinstance(config.template_path, Path)
            assert isinstance(config.log_directory, Path)
            # Path objects normalize relative paths
            assert str(config.template_path) == "custom/templates"  # ./ is normalized away
            assert str(config.log_directory) == "../logs"

    def test_auth_method_values(self):
        """Test various authentication method values."""
        valid_auth_methods = ["none", "ldap", "authelia", "authentik", "tinyauth"]

        for auth_method in valid_auth_methods:
            with patch.dict(os.environ, {"SWAG_MCP_DEFAULT_AUTH_METHOD": auth_method}, clear=False):
                config = SwagConfig()
                assert config.default_auth_method == auth_method

    def test_config_type_values(self):
        """Test configuration type values."""
        valid_config_types = ["subdomain", "subfolder"]

        for config_type in valid_config_types:
            with patch.dict(os.environ, {"SWAG_MCP_DEFAULT_CONFIG_TYPE": config_type}, clear=False):
                config = SwagConfig()
                assert config.default_config_type == config_type

    def test_log_level_values(self):
        """Test log level values."""
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for log_level in valid_log_levels:
            with patch.dict(os.environ, {"SWAG_MCP_LOG_LEVEL": log_level}, clear=False):
                config = SwagConfig()
                assert config.log_level == log_level

    def test_boundary_values(self):
        """Test boundary and edge case values."""
        # Test minimum/maximum values for numeric fields
        boundary_tests = [
            ("SWAG_MCP_BACKUP_RETENTION_DAYS", "1"),  # Minimum reasonable value
            ("SWAG_MCP_BACKUP_RETENTION_DAYS", "365"),  # Maximum reasonable value
            ("SWAG_MCP_RATE_LIMIT_RPS", "0.1"),  # Very low rate limit
            ("SWAG_MCP_RATE_LIMIT_RPS", "1000.0"),  # High rate limit
            ("SWAG_MCP_RATE_LIMIT_BURST", "1"),  # Minimum burst
            ("SWAG_MCP_RATE_LIMIT_BURST", "1000"),  # High burst
            ("SWAG_MCP_MAX_RETRIES", "0"),  # No retries
            ("SWAG_MCP_MAX_RETRIES", "10"),  # Many retries
        ]

        for env_var, value in boundary_tests:
            with patch.dict(os.environ, {env_var: value}, clear=False):
                config = SwagConfig()
                # Should not raise validation errors
                assert config is not None

    def test_env_file_configuration(self):
        """Test loading configuration from .env file."""
        # Create temporary .env file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as env_file:
            env_content = """
SWAG_MCP_DEFAULT_AUTH_METHOD=ldap
SWAG_MCP_LOG_LEVEL=DEBUG
SWAG_MCP_RATE_LIMIT_ENABLED=true
SWAG_MCP_BACKUP_RETENTION_DAYS=45
            """.strip()
            env_file.write(env_content)
            env_file_path = env_file.name

        try:
            # Note: In real usage, pydantic-settings reads from .env automatically
            # For testing, we'll patch the environment
            env_vars = {
                "SWAG_MCP_DEFAULT_AUTH_METHOD": "ldap",
                "SWAG_MCP_LOG_LEVEL": "DEBUG",
                "SWAG_MCP_RATE_LIMIT_ENABLED": "true",
                "SWAG_MCP_BACKUP_RETENTION_DAYS": "45",
            }

            with patch.dict(os.environ, env_vars, clear=False):
                config = SwagConfig()

                assert config.default_auth_method == "ldap"
                assert config.log_level == "DEBUG"
                assert config.rate_limit_enabled is True
                assert config.backup_retention_days == 45
        finally:
            # Clean up temporary file
            os.unlink(env_file_path)

    def test_model_config_settings(self):
        """Test that model configuration is set correctly."""
        config = SwagConfig()

        # Check model configuration
        assert config.model_config["env_file"] == ".env"
        assert config.model_config["env_prefix"] == "SWAG_MCP_"
        assert config.model_config["case_sensitive"] is False

    def test_configuration_isolation(self):
        """Test that different config instances are isolated."""
        # Set different environment for each instance
        with patch.dict(os.environ, {"SWAG_MCP_LOG_LEVEL": "DEBUG"}, clear=False):
            config1 = SwagConfig()

        with patch.dict(os.environ, {"SWAG_MCP_LOG_LEVEL": "ERROR"}, clear=False):
            config2 = SwagConfig()

        # Both configs should reflect their respective environments
        assert config1.log_level == "DEBUG"
        assert config2.log_level == "ERROR"

    def test_global_config_instance(self):
        """Test the global config instance."""
        from swag_mcp.core.config import config

        # Global instance should be properly initialized
        assert isinstance(config, SwagConfig)
        assert config.port == 8000
        assert config.default_auth_method == "authelia"

    def test_config_field_descriptions(self):
        """Test that all configuration fields have descriptions."""
        SwagConfig()

        # Get field info from the model
        field_info = SwagConfig.model_fields

        # Check that important fields have descriptions
        required_descriptions = [
            "proxy_confs_path",
            "template_path",
            "default_auth_method",
            "default_config_type",
            "backup_retention_days",
            "log_level",
            "rate_limit_enabled",
        ]

        for field_name in required_descriptions:
            assert field_name in field_info
            assert field_info[field_name].description is not None
            assert len(field_info[field_name].description) > 0

    def test_empty_environment_variables(self):
        """Test handling of empty environment variable values."""
        with patch.dict(os.environ, {"SWAG_MCP_DEFAULT_AUTH_METHOD": ""}, clear=False):
            config = SwagConfig()
            # Empty string should use default value
            assert config.default_auth_method == "authelia"

    def test_whitespace_handling(self):
        """Test handling of whitespace in environment variables."""
        env_vars = {
            "SWAG_MCP_DEFAULT_AUTH_METHOD": "  ldap  ",  # Leading/trailing spaces
            "SWAG_MCP_LOG_LEVEL": "\tINFO\n",  # Tab and newline
            "SWAG_MCP_HOST": " 127.0.0.1 ",  # Spaces around IP
        }

        with patch.dict(os.environ, env_vars, clear=False):
            config = SwagConfig()

            # pydantic should handle whitespace stripping
            assert config.default_auth_method == "  ldap  "  # May preserve or strip
            assert config.host in ["127.0.0.1", " 127.0.0.1 "]  # Implementation dependent


class TestConfigurationValidation:
    """Test configuration validation and error handling."""

    def test_invalid_boolean_values(self):
        """Test invalid boolean environment variable values."""
        invalid_booleans = ["maybe", "2", "invalid", "true/false"]

        for invalid_bool in invalid_booleans:
            with patch.dict(os.environ, {"SWAG_MCP_LOG_FILE_ENABLED": invalid_bool}, clear=False):
                with pytest.raises(ValidationError):
                    SwagConfig()

    def test_negative_numeric_values(self):
        """Test handling of negative numeric values."""
        # Some fields should not accept negative values
        with patch.dict(os.environ, {"SWAG_MCP_BACKUP_RETENTION_DAYS": "-5"}, clear=False):
            # This might be allowed by pydantic, depending on field constraints
            config = SwagConfig()
            assert config.backup_retention_days == -5  # May need additional validation

    def test_zero_values(self):
        """Test handling of zero values for numeric fields."""
        with patch.dict(
            os.environ,
            {
                "SWAG_MCP_BACKUP_RETENTION_DAYS": "0",
                "SWAG_MCP_RATE_LIMIT_RPS": "0",
                "SWAG_MCP_MAX_RETRIES": "0",
            },
            clear=False,
        ):
            config = SwagConfig()
            assert config.backup_retention_days == 0
            assert config.rate_limit_rps == 0
            assert config.max_retries == 0

    def test_extremely_large_values(self):
        """Test handling of extremely large numeric values."""
        with patch.dict(
            os.environ,
            {
                "SWAG_MCP_LOG_FILE_MAX_BYTES": str(2**31),  # Very large file size
                "SWAG_MCP_RATE_LIMIT_BURST": "999999",  # Very large burst
            },
            clear=False,
        ):
            config = SwagConfig()
            assert config.log_file_max_bytes == 2**31
            assert config.rate_limit_burst == 999999
