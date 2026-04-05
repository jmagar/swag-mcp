"""Pytest configuration and shared fixtures for SWAG MCP tests."""

import functools
import logging
import os
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import AsyncMock, patch  # noqa: F401

import pytest
from fastmcp import Client, FastMCP
from pytest import MonkeyPatch
from swag_mcp.server import create_mcp_server

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
async def mock_nginx_validation():
    """Mock nginx syntax validation for all tests.

    The generated configs reference /config/nginx/*.conf include files that only
    exist inside the SWAG Docker container. Running `nginx -t` on these configs in
    CI will always fail due to missing includes even when nginx is installed.
    This fixture skips the external process call and treats all configs as valid.
    """
    with patch(
        "swag_mcp.services.validation.ValidationService.validate_nginx_syntax",
        new=AsyncMock(return_value=True),
    ):
        yield


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment(tmp_path_factory):
    """Set up test environment variables.

    IMPORTANT: Always uses an isolated temp directory for proxy-confs to prevent
    tests from writing to the real SWAG proxy-confs directory (which triggers
    SWAG's inotify watcher and nginx reload).
    """

    # Always use an isolated temp directory — never write to real proxy-confs
    test_base = tmp_path_factory.mktemp("swag-test")
    proxy_confs_path = str(test_base / "proxy-confs")
    log_dir_path = str(test_base / "logs")

    proxy_path = Path(proxy_confs_path)
    log_dir = Path(log_dir_path)

    proxy_path.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    os.environ["SWAG_MCP_PROXY_CONFS_PATH"] = proxy_confs_path
    os.environ["SWAG_MCP_LOG_DIRECTORY"] = log_dir_path

    # Create sample configuration files for testing
    _create_sample_configs(proxy_path)

    yield

    # tmp_path_factory handles cleanup automatically


def _create_sample_configs(proxy_path: Path) -> None:
    """Create sample configuration files for testing."""
    # Create a few sample .conf files that tests can list and view
    sample_configs = {
        "jellyfin.subdomain.conf.sample": """# Jellyfin sample configuration
server {
    listen 443 ssl;
    server_name jellyfin.*;

    include /config/nginx/ssl.conf;

    location / {
        include /config/nginx/proxy.conf;
        include /config/nginx/resolver.conf;
        proxy_pass http://jellyfin:8096;
    }
}""",
        "plex.subdomain.conf.sample": """# Plex sample configuration
server {
    listen 443 ssl;
    server_name plex.*;

    include /config/nginx/ssl.conf;

    location / {
        include /config/nginx/proxy.conf;
        include /config/nginx/resolver.conf;
        proxy_pass http://plex:32400;
    }
}""",
        "_template.subdomain.conf.sample": """# Template sample configuration
server {
    listen 443 ssl;
    server_name app.*;

    include /config/nginx/ssl.conf;

    location / {
        include /config/nginx/proxy.conf;
        include /config/nginx/resolver.conf;
        proxy_pass http://app:8080;
    }
}""",
    }

    for filename, content in sample_configs.items():
        config_file = proxy_path / filename
        if not config_file.exists():
            try:
                config_file.write_text(content)
            except Exception:
                logger.exception("Failed to create sample config file %s", filename)


# Removed session-scoped event_loop fixture to avoid pytest-asyncio ≥0.22 deprecation
# pytest-asyncio now handles event loop management automatically


@pytest.fixture
async def mcp_server(monkeypatch: MonkeyPatch) -> AsyncGenerator[FastMCP, None]:
    """Create a FastMCP server instance for testing."""
    # Patch multiple places that use the config

    from swag_mcp.core import config as config_module
    from swag_mcp.core.config import SwagConfig
    from swag_mcp.services.swag_manager import SwagManagerService

    # Use the configured proxy confs path from environment
    proxy_confs_path = os.environ.get("SWAG_MCP_PROXY_CONFS_PATH", "/tmp/swag-test/proxy-confs")

    # Create test configuration
    test_config = SwagConfig(
        proxy_confs_path=Path(proxy_confs_path),
        log_directory=Path("/tmp/.swag-mcp-test/logs"),
        template_path=Path("templates"),
    )

    # Patch the global config object in multiple modules
    monkeypatch.setattr(config_module, "config", test_config)

    # Also patch config in server module
    from swag_mcp import server as server_module

    monkeypatch.setattr(server_module, "config", test_config)

    # Tools module doesn't need config patching - it gets config via Context

    # Also patch the SwagManagerService constructor as a backup
    original_init = SwagManagerService.__init__

    @functools.wraps(original_init)
    def patched_init(self, config_path=None, template_path=None, *args, **kwargs):
        # Force the config_path to our test path
        test_config_path = Path(proxy_confs_path)
        test_template_path = Path("templates")
        return original_init(self, test_config_path, test_template_path, *args, **kwargs)

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

    def add_config(config_name: str) -> None:
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
                logger.info("Cleaned up test config: %s", config_name)
            except Exception as e:
                logger.error("Failed to cleanup test config %s: %s", config_name, e, exc_info=True)

        # Also cleanup any backup files
        backup_pattern = f"{config_name}.backup.*"
        for backup_file in proxy_confs_path.glob(backup_pattern):
            try:
                backup_file.unlink()
                logger.info("Cleaned up backup file: %s", backup_file.name)
            except Exception as e:
                logger.error("Failed to cleanup backup %s: %s", backup_file.name, e, exc_info=True)


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
