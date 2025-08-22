"""Shared fixtures and configuration for SWAG MCP server tests."""

import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastmcp import Client, FastMCP
from swag_mcp.core.config import SwagConfig
from swag_mcp.server import create_mcp_server
from swag_mcp.services.swag_manager import SwagManagerService

from .fixtures.sample_configs import TEST_CONFIGS

# No temp directories needed - we'll use our actual config paths


@pytest.fixture
def mock_config(tmp_path) -> SwagConfig:
    """Create a mock configuration for testing using temporary paths."""
    # Create temporary directories for testing
    proxy_confs_dir = tmp_path / "proxy-confs"
    proxy_confs_dir.mkdir(exist_ok=True)

    template_dir = Path(__file__).parent.parent / "templates"  # Use real templates directory

    # Set up test environment variables
    test_env = {
        "SWAG_MCP_LOG_FILE_ENABLED": "false",
        "SWAG_MCP_PROXY_CONFS_PATH": str(proxy_confs_dir),
        "SWAG_MCP_TEMPLATE_PATH": str(template_dir),
    }

    with patch.dict(os.environ, test_env, clear=False):
        config = SwagConfig()
        yield config


@pytest.fixture
async def swag_service(mock_config: SwagConfig) -> SwagManagerService:
    """Create SwagManagerService with test configuration."""
    service = SwagManagerService(
        config_path=mock_config.proxy_confs_path, template_path=mock_config.template_path
    )
    return service


@pytest.fixture
async def mcp_server(mock_config: SwagConfig, swag_service: SwagManagerService) -> FastMCP:
    """Create in-memory FastMCP server for testing."""
    # Patch the global config import to use our mock config
    # Also patch the global swag_service to use our test service
    with (
        patch("swag_mcp.core.config.config", mock_config),
        patch("swag_mcp.server.config", mock_config),
        patch("swag_mcp.tools.swag.config", mock_config),
        patch("swag_mcp.services.swag_manager.config", mock_config),
        patch("swag_mcp.tools.swag.swag_service", swag_service),
    ):
        # Create the server instance
        server = await create_mcp_server()
        yield server


@pytest.fixture
async def mcp_client(mcp_server: FastMCP) -> AsyncGenerator[Client, None]:
    """Create in-memory client connected to test server."""
    async with Client(mcp_server) as client:
        yield client


@pytest.fixture
def environment_vars() -> dict[str, str]:
    """Provide test environment variables."""
    return {
        "SWAG_MCP_DEFAULT_AUTH_METHOD": "authelia",
        "SWAG_MCP_DEFAULT_QUIC_ENABLED": "false",
        "SWAG_MCP_DEFAULT_CONFIG_TYPE": "subdomain",
        "SWAG_MCP_LOG_LEVEL": "INFO",
        "SWAG_MCP_LOG_FILE_ENABLED": "false",
    }


@pytest.fixture(autouse=True)
def set_test_environment(environment_vars: dict[str, str]):
    """Automatically set test environment variables for all tests."""
    # Store original values
    original_values = {}
    for key, value in environment_vars.items():
        original_values[key] = os.environ.get(key)
        os.environ[key] = value

    yield

    # Restore original values
    for key, original_value in original_values.items():
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value


# Test helpers and utilities
class TestHelpers:
    """Helper methods for testing."""

    @staticmethod
    def assert_config_contains(config_content: str, expected_values: dict[str, Any]) -> None:
        """Assert that configuration content contains expected values."""
        for key, value in expected_values.items():
            if key == "upstream_app":
                assert f"set $upstream_app {value};" in config_content
            elif key == "upstream_port":
                assert f"set $upstream_port {value};" in config_content
            elif key == "upstream_proto":
                assert f"set $upstream_proto {value};" in config_content
            elif key == "server_name":
                assert f"server_name {value}" in config_content
            elif key == "auth_method" and value != "none":
                assert f"{value}-location.conf" in config_content

    @staticmethod
    def assert_backup_created(config_dir: Path, config_name: str) -> Path:
        """Assert that a backup file was created and return its path."""
        backup_files = list(config_dir.glob(f"{config_name}.backup.*"))
        assert len(backup_files) >= 1, f"No backup files found for {config_name}"
        return backup_files[-1]  # Return the most recent backup

    @staticmethod
    def cleanup_test_artifacts(config_dir: Path) -> int:
        """Utility function to clean up all test artifacts manually."""
        patterns = [
            "test.*",
            "testapp.*",
            "webapp.*",
            "myapp.*",
            "sampleapp.*",
            "nonexistent.*",
            "*.backup.*",  # All backup files
        ]

        cleaned_count = 0
        for pattern in patterns:
            for file_path in config_dir.glob(pattern):
                if file_path.is_file():
                    try:
                        file_path.unlink()
                        cleaned_count += 1
                    except (PermissionError, OSError) as e:
                        print(f"Warning: Could not clean up {file_path.name}: {e}")

        return cleaned_count


@pytest.fixture
def test_helpers() -> TestHelpers:
    """Provide test helper methods."""
    return TestHelpers()


@pytest.fixture(autouse=True)
async def test_cleanup(mock_config: SwagConfig):
    """Automatically clean up test artifacts after each test."""
    config_path = mock_config.proxy_confs_path

    # Track files that exist before the test
    initial_files = {f.name for f in config_path.glob("*") if f.is_file()}

    yield

    # After test completion, clean up any new files
    current_files = {f.name for f in config_path.glob("*") if f.is_file()}
    new_files = current_files - initial_files

    # Clean up test-related files (more aggressive cleanup for known test patterns)
    test_patterns = [
        "test.*",
        "testapp.*",
        "webapp.*",
        "myapp.*",
        "sampleapp.*",
        "nonexistent.*",
        "*.backup.*",  # All backup files
    ]

    files_to_remove = set()

    # Add new files
    files_to_remove.update(new_files)

    # Add files matching test patterns (be more aggressive about cleaning test artifacts)
    for pattern in test_patterns:
        for file_path in config_path.glob(pattern):
            if file_path.is_file():
                files_to_remove.add(file_path.name)

    # Remove the files
    for filename in files_to_remove:
        file_path = config_path / filename
        try:
            if file_path.exists():
                file_path.unlink()
        except (PermissionError, OSError) as e:
            # Log but don't fail tests if cleanup fails
            print(f"Warning: Could not clean up test file {filename}: {e}")


@pytest.fixture
async def sample_configs(mock_config: SwagConfig):
    """Create sample configuration files for testing in the real SWAG directory."""
    config_path = mock_config.proxy_confs_path
    created_files = []

    # Create test.conf file that some tests expect
    test_conf_path = config_path / "test.conf"
    test_conf_content = """# Test configuration
server {
    listen 443 ssl http2;
    server_name test.*;
    location / {
        set $upstream_app test;
        set $upstream_port 8080;
        proxy_pass http://$upstream_app:$upstream_port;
    }
}
"""
    test_conf_path.write_text(test_conf_content)
    created_files.append(test_conf_path)

    # Create the test config files from TEST_CONFIGS
    for filename, content in TEST_CONFIGS.items():
        config_file = config_path / filename
        config_file.write_text(content)
        created_files.append(config_file)

    yield created_files

    # Cleanup: remove created test files and their associated backups
    for file_path in created_files:
        if file_path.exists():
            file_path.unlink()

        # Also remove any backup files created from these test files
        backup_pattern = f"{file_path.name}.backup.*"
        for backup_file in config_path.glob(backup_pattern):
            try:
                backup_file.unlink()
            except (PermissionError, OSError):
                pass  # Ignore cleanup errors
