"""Pytest configuration and shared fixtures for SWAG MCP tests."""

import asyncio
import contextlib
import os
import time
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP
from swag_mcp.server import create_mcp_server


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    # Use environment-specific paths for testing
    # Default to CI-friendly paths if not set, fallback to local dev paths
    proxy_confs_path = os.environ.get("SWAG_MCP_PROXY_CONFS_PATH")
    if not proxy_confs_path:
        # Check if we're in CI environment
        if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            proxy_confs_path = "/tmp/swag-test/proxy-confs"
        else:
            # Local development environment
            proxy_confs_path = "/mnt/appdata/swag/nginx/proxy-confs"
        os.environ["SWAG_MCP_PROXY_CONFS_PATH"] = proxy_confs_path

    # Set log directory
    os.environ["SWAG_MCP_LOG_DIRECTORY"] = "/tmp/.swag-mcp-test/logs"

    # Create necessary directories
    proxy_path = Path(proxy_confs_path)
    log_dir = Path("/tmp/.swag-mcp-test/logs")

    proxy_path.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create sample configuration files for testing if they don't exist
    _create_sample_configs(proxy_path)

    yield

    # Cleanup test directories only if we created them
    try:
        import shutil

        if proxy_confs_path.startswith("/tmp/"):
            shutil.rmtree(proxy_path, ignore_errors=True)
        shutil.rmtree("/tmp/.swag-mcp-test", ignore_errors=True)
    except Exception:
        pass


def _create_sample_configs(proxy_path: Path) -> None:
    """Create sample configuration files for testing."""
    # Create a few sample .conf files that tests can list and view
    sample_configs = {
        "jellyfin.subdomain.conf.sample": """# Jellyfin sample configuration
server {
    listen 443 ssl;
    server_name jellyfin.*;

    location / {
        proxy_pass http://jellyfin:8096;
    }
}""",
        "plex.subdomain.conf.sample": """# Plex sample configuration
server {
    listen 443 ssl;
    server_name plex.*;

    location / {
        proxy_pass http://plex:32400;
    }
}""",
        "_template.subdomain.conf.sample": """# Template sample configuration
server {
    listen 443 ssl;
    server_name app.*;

    location / {
        proxy_pass http://app:8080;
    }
}""",
    }

    for filename, content in sample_configs.items():
        config_file = proxy_path / filename
        if not config_file.exists():
            with contextlib.suppress(Exception):
                config_file.write_text(content)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture
async def mcp_server(monkeypatch) -> AsyncGenerator[FastMCP, None]:
    """Create a FastMCP server instance for testing."""
    # Patch multiple places that use the config
    from pathlib import Path

    from swag_mcp.core import config as config_module
    from swag_mcp.core.config import SwagConfig
    from swag_mcp.services.swag_manager import SwagManagerService

    # Use the configured proxy confs path from environment
    proxy_confs_path = os.environ.get("SWAG_MCP_PROXY_CONFS_PATH", "/tmp/swag-test/proxy-confs")

    # Create test configuration
    test_config = SwagConfig(
        proxy_confs_path=proxy_confs_path,
        log_directory="/tmp/.swag-mcp-test/logs",
        template_path="templates",
    )

    # Patch the global config object in multiple modules
    monkeypatch.setattr(config_module, "config", test_config)

    # Also patch config in server module
    from swag_mcp import server as server_module

    monkeypatch.setattr(server_module, "config", test_config)

    # Tools module doesn't need config patching - it gets config via Context

    # Also patch the SwagManagerService constructor as a backup
    original_init = SwagManagerService.__init__

    def patched_init(self, config_path=None, template_path=None):
        # Force the config_path to our test path
        test_config_path = Path(proxy_confs_path)
        test_template_path = Path("templates")
        return original_init(self, test_config_path, test_template_path)

    monkeypatch.setattr(SwagManagerService, "__init__", patched_init)

    # Tools module service gets created via Context, no need to patch

    server = await create_mcp_server()
    yield server
    # Cleanup will happen automatically when server goes out of scope


@pytest.fixture
async def mcp_client(mcp_server: FastMCP) -> AsyncGenerator[Client, None]:
    """Create a FastMCP client connected to the server for testing."""
    async with Client(mcp_server) as client:
        yield client


@pytest.fixture
def test_timestamp() -> str:
    """Generate a unique timestamp for test isolation."""
    return str(int(time.time() * 1000000))  # Microsecond precision


@pytest.fixture
def test_config_name(test_timestamp: str) -> str:
    """Generate a unique test configuration name."""
    return f"swag-mcp-test-{test_timestamp}"


@pytest.fixture
def test_domain() -> str:
    """Generate a test domain name."""
    return "test.example.com"


@pytest.fixture
def test_upstream() -> dict:
    """Generate test upstream configuration."""
    return {"app": "test-app", "port": 8080}


@pytest.fixture
async def test_config_cleanup():
    """Fixture to track and cleanup test configurations."""
    created_configs = []

    def add_config(config_name: str):
        """Add a config to the cleanup list."""
        created_configs.append(config_name)

    yield add_config

    # Cleanup: Remove any test configurations that were created
    proxy_confs_path = Path(
        os.environ.get("SWAG_MCP_PROXY_CONFS_PATH", "/tmp/swag-test/proxy-confs")
    )

    for config_name in created_configs:
        # Ensure proper file extension
        if not config_name.endswith(".conf"):
            config_name = f"{config_name}.conf"

        config_file = proxy_confs_path / config_name
        if config_file.exists():
            try:
                config_file.unlink()  # Remove the file
                print(f"Cleaned up test config: {config_name}")
            except Exception as e:
                print(f"Failed to cleanup test config {config_name}: {e}")

        # Also cleanup any backup files
        backup_pattern = f"{config_name}.backup.*"
        for backup_file in proxy_confs_path.glob(backup_pattern):
            try:
                backup_file.unlink()
                print(f"Cleaned up backup file: {backup_file.name}")
            except Exception as e:
                print(f"Failed to cleanup backup {backup_file.name}: {e}")


class TestHelpers:
    """Helper methods for tests."""

    @staticmethod
    def assert_success_response(response: dict) -> None:
        """Assert that a response indicates success."""
        assert isinstance(response, dict)
        assert response.get("success") is True
        assert "message" in response

    @staticmethod
    def assert_error_response(response: dict) -> None:
        """Assert that a response indicates an error."""
        assert isinstance(response, dict)
        assert response.get("success") is False
        assert "message" in response

    @staticmethod
    def extract_config_name_with_extension(config_name: str) -> str:
        """Ensure config name has proper .conf extension."""
        if not config_name.endswith(".conf"):
            return f"{config_name}.conf"
        return config_name
