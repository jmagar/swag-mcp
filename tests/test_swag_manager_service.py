"""Comprehensive unit tests for SwagManagerService."""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from swag_mcp.core.config import SwagConfig
from swag_mcp.models.config import (
    SwagConfigRequest,
    SwagEditRequest,
    SwagHealthCheckRequest,
    SwagLogsRequest,
    SwagRemoveRequest,
    SwagUpdateRequest,
)
from swag_mcp.models.enums import SwagAction
from swag_mcp.services.errors import ConfigurationNotFoundError, SwagServiceError
from swag_mcp.services.swag_manager import SwagManagerService


class TestSwagManagerService:
    """Comprehensive tests for SwagManagerService."""

    @pytest_asyncio.fixture
    async def temp_config(self):
        """Create temporary configuration for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            proxy_confs_path = temp_path / "proxy-confs"
            log_directory = temp_path / "logs"
            proxy_confs_path.mkdir()
            log_directory.mkdir()

            config = SwagConfig(
                proxy_confs_path=proxy_confs_path,
                log_directory=log_directory,
                template_path=Path("templates"),
            )
            yield config

    @pytest_asyncio.fixture
    async def service(self, temp_config):
        """Create SwagManagerService with temporary config."""
        service = SwagManagerService(temp_config)
        yield service
        # Cleanup
        if hasattr(service, "_http_session") and service._http_session:
            await service._http_session.close()

    @pytest_asyncio.fixture
    async def sample_config_file(self, temp_config):
        """Create a sample configuration file."""
        config_path = temp_config.proxy_confs_path / "test.subdomain.conf"
        config_content = """
server {
    listen 443 ssl http2;
    server_name test.example.com;

    location / {
        proxy_pass http://test-app:8080;
        proxy_set_header Host $host;
    }
}
"""
        config_path.write_text(config_content)
        return config_path

    # Core CRUD Operations Tests

    async def test_list_configs_all(self, service, sample_config_file):
        """Test listing all configurations."""
        result = await service.list_configs("all")

        assert result.success is True
        assert len(result.configs) >= 1
        assert any(config.name == "test.subdomain.conf" for config in result.configs)

    async def test_list_configs_active(self, service, sample_config_file):
        """Test listing active configurations."""
        result = await service.list_configs("active")

        assert result.success is True
        assert len(result.configs) >= 1

    async def test_list_configs_samples(self, service, temp_config):
        """Test listing sample configurations."""
        # Create a sample file
        sample_path = temp_config.proxy_confs_path / "test.subdomain.conf.sample"
        sample_path.write_text("sample config")

        result = await service.list_configs("samples")

        assert result.success is True
        assert len(result.configs) >= 1
        assert any(config.name.endswith(".sample") for config in result.configs)

    async def test_list_configs_empty_directory(self, service):
        """Test listing configurations in empty directory."""
        result = await service.list_configs("all")

        assert result.success is True
        assert len(result.configs) == 0

    async def test_read_config_existing(self, service, sample_config_file):
        """Test reading existing configuration."""
        content = await service.read_config("test.subdomain.conf")

        assert "test.example.com" in content
        assert "test-app:8080" in content

    async def test_read_config_not_found(self, service):
        """Test reading non-existent configuration."""
        with pytest.raises(ConfigurationNotFoundError):
            await service.read_config("nonexistent.conf")

    async def test_read_config_invalid_name(self, service):
        """Test reading config with invalid name."""
        with pytest.raises(SwagServiceError):
            await service.read_config("../etc/passwd")

    @patch("swag_mcp.services.swag_manager.SwagManagerService._render_template")
    async def test_create_config_success(self, mock_render, service, temp_config):
        """Test successful config creation."""
        mock_render.return_value = "rendered config content"

        request = SwagConfigRequest(
            action=SwagAction.CREATE,
            config_name="testapp.subdomain.conf",
            server_name="testapp.example.com",
            upstream_app="testapp",
            upstream_port=8080,
        )

        result = await service.create_config(request)

        assert result.success is True
        assert "created successfully" in result.message.lower()
        assert (temp_config.proxy_confs_path / "testapp.subdomain.conf").exists()

    async def test_create_config_invalid_service_name(self, service):
        """Test config creation with invalid service name."""
        request = SwagConfigRequest(
            action=SwagAction.CREATE,
            config_name="test.subdomain.conf",
            server_name="test.example.com",
            upstream_app="test",
            upstream_port=8080,
        )

        with pytest.raises(SwagServiceError):
            await service.create_config(request)

    async def test_create_config_file_exists(self, service, sample_config_file):
        """Test config creation when file already exists."""
        request = SwagConfigRequest(
            action=SwagAction.CREATE,
            config_name="test.subdomain.conf",
            server_name="test.example.com",
            upstream_app="test",
            upstream_port=8080,
        )

        with pytest.raises(SwagServiceError):
            await service.create_config(request)

    async def test_update_config_success(self, service, sample_config_file):
        """Test successful config update."""
        new_content = """
server {
    listen 443 ssl http2;
    server_name updated.example.com;

    location / {
        proxy_pass http://updated-app:9000;
    }
}
"""

        request = SwagEditRequest(
            action=SwagAction.EDIT, config_name="test.subdomain.conf", new_content=new_content
        )

        result = await service.update_config(request)

        assert result.success is True
        assert "updated successfully" in result.message.lower()

        # Verify content was updated
        updated_content = await service.read_config("test.subdomain.conf")
        assert "updated.example.com" in updated_content
        assert "updated-app:9000" in updated_content

    async def test_update_config_not_found(self, service):
        """Test updating non-existent config."""
        request = SwagEditRequest(
            action=SwagAction.EDIT, config_name="nonexistent.conf", new_content="new content"
        )

        with pytest.raises(ConfigurationNotFoundError):
            await service.update_config(request)

    async def test_update_config_field_port(self, service, sample_config_file):
        """Test updating port field."""
        request = SwagUpdateRequest(
            action=SwagAction.UPDATE,
            config_name="test.subdomain.conf",
            update_field="port",
            update_value="9000",
        )

        result = await service.update_config_field(request)

        assert result.success is True

        # Verify port was updated
        updated_content = await service.read_config("test.subdomain.conf")
        assert "9000" in updated_content

    async def test_update_config_field_upstream(self, service, sample_config_file):
        """Test updating upstream field."""
        request = SwagUpdateRequest(
            action=SwagAction.UPDATE,
            config_name="test.subdomain.conf",
            update_field="upstream",
            update_value="new-test-app",
        )

        result = await service.update_config_field(request)

        assert result.success is True

        # Verify upstream was updated
        updated_content = await service.read_config("test.subdomain.conf")
        assert "new-test-app" in updated_content

    async def test_update_config_field_app(self, service, sample_config_file):
        """Test updating app field."""
        request = SwagUpdateRequest(
            action=SwagAction.UPDATE,
            config_name="test.subdomain.conf",
            update_field="app",
            update_value="new-app:7000",
        )

        result = await service.update_config_field(request)

        assert result.success is True

        # Verify app was updated
        updated_content = await service.read_config("test.subdomain.conf")
        assert "new-app:7000" in updated_content

    async def test_update_config_field_invalid_field(self, service, sample_config_file):
        """Test updating with invalid field."""
        request = SwagUpdateRequest(
            action=SwagAction.UPDATE,
            config_name="test.subdomain.conf",
            update_field="port",
            update_value="value",
        )

        with pytest.raises(SwagServiceError):
            await service.update_config_field(request)

    async def test_remove_config_success(self, service, sample_config_file):
        """Test successful config removal."""
        request = SwagRemoveRequest(action=SwagAction.REMOVE, config_name="test.subdomain.conf")

        result = await service.remove_config(request)

        assert result.success is True
        assert not sample_config_file.exists()

    async def test_remove_config_not_found(self, service):
        """Test removing non-existent config."""
        request = SwagRemoveRequest(action=SwagAction.REMOVE, config_name="nonexistent.conf")

        with pytest.raises(ConfigurationNotFoundError):
            await service.remove_config(request)

    async def test_remove_config_with_backup(self, service, sample_config_file):
        """Test config removal with backup creation."""
        request = SwagRemoveRequest(
            action=SwagAction.REMOVE, config_name="test.subdomain.conf", create_backup=True
        )

        result = await service.remove_config(request)

        assert result.success is True
        assert not sample_config_file.exists()

        # Check backup was created
        backups = await service.list_backups()
        assert len(backups) > 0
        assert any("test.subdomain.conf" in backup["original_name"] for backup in backups)

    # Backup Management Tests

    async def test_create_backup(self, service, sample_config_file):
        """Test backup creation."""
        backup_path = await service._create_backup("test.subdomain.conf")

        assert backup_path.endswith(".backup")
        assert Path(service.config.proxy_confs_path / backup_path).exists()

    async def test_list_backups_empty(self, service):
        """Test listing backups when none exist."""
        backups = await service.list_backups()

        assert isinstance(backups, list)
        assert len(backups) == 0

    async def test_list_backups_with_files(self, service, temp_config):
        """Test listing backups with existing backup files."""
        # Create a backup file
        backup_path = temp_config.proxy_confs_path / "test.subdomain.conf.backup"
        backup_path.write_text("backup content")

        backups = await service.list_backups()

        assert len(backups) == 1
        assert backups[0]["name"] == "test.subdomain.conf.backup"
        assert backups[0]["original_name"] == "test.subdomain.conf"

    async def test_cleanup_old_backups(self, service, temp_config):
        """Test cleanup of old backup files."""
        import time

        # Create old backup file
        old_backup = temp_config.proxy_confs_path / "old.subdomain.conf.backup"
        old_backup.write_text("old backup")

        # Set file modification time to 2 days ago
        old_time = time.time() - (2 * 24 * 60 * 60)
        old_backup.touch(times=(old_time, old_time))

        # Create recent backup file
        new_backup = temp_config.proxy_confs_path / "new.subdomain.conf.backup"
        new_backup.write_text("new backup")

        # Cleanup with 1 day retention
        cleaned_count = await service.cleanup_old_backups(retention_days=1)

        assert cleaned_count == 1
        assert not old_backup.exists()
        assert new_backup.exists()

    # Template Validation Tests

    @patch("swag_mcp.services.swag_manager.SwagManagerService._get_template_path")
    async def test_validate_template_exists_true(self, mock_get_path, service):
        """Test template validation when template exists."""
        mock_path = Mock()
        mock_path.exists.return_value = True
        mock_get_path.return_value = mock_path

        result = await service.validate_template_exists("subdomain")

        assert result is True

    @patch("swag_mcp.services.swag_manager.SwagManagerService._get_template_path")
    async def test_validate_template_exists_false(self, mock_get_path, service):
        """Test template validation when template doesn't exist."""
        mock_path = Mock()
        mock_path.exists.return_value = False
        mock_get_path.return_value = mock_path

        result = await service.validate_template_exists("nonexistent")

        assert result is False

    @patch("swag_mcp.services.swag_manager.SwagManagerService.validate_template_exists")
    async def test_validate_all_templates(self, mock_validate, service):
        """Test validation of all templates."""
        mock_validate.side_effect = lambda t: t in ["subdomain", "subfolder"]

        result = await service.validate_all_templates()

        assert isinstance(result, dict)
        assert "subdomain" in result
        assert "subfolder" in result

    # Health Check Tests

    @patch("aiohttp.ClientSession.get")
    async def test_health_check_success(self, mock_get, service):
        """Test successful health check."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_get.return_value.__aenter__.return_value = mock_response

        request = SwagHealthCheckRequest(
            action=SwagAction.HEALTH_CHECK, domain="test.example.com", timeout=10
        )

        result = await service.health_check(request)

        assert result.success is True
        assert result.accessible is True
        assert result.status_code == 200

    @patch("aiohttp.ClientSession.get")
    async def test_health_check_failure(self, mock_get, service):
        """Test failed health check."""
        mock_get.side_effect = TimeoutError()

        request = SwagHealthCheckRequest(
            action=SwagAction.HEALTH_CHECK, domain="unreachable.example.com", timeout=10
        )

        result = await service.health_check(request)

        assert result.success is False
        assert result.accessible is False
        assert "timeout" in result.error_message.lower()

    @patch("aiohttp.ClientSession.get")
    async def test_health_check_multiple_endpoints(self, mock_get, service):
        """Test health check trying multiple endpoints."""
        # First endpoint fails, second succeeds
        mock_response_fail = AsyncMock()
        mock_response_fail.status = 404

        mock_response_success = AsyncMock()
        mock_response_success.status = 200

        mock_get.return_value.__aenter__.side_effect = [
            mock_response_fail,  # /health fails
            mock_response_success,  # /mcp succeeds
        ]

        request = SwagHealthCheckRequest(action=SwagAction.HEALTH_CHECK, domain="test.example.com")

        result = await service.health_check(request)

        assert result.success is True
        assert result.accessible is True

    # Log Access Tests

    @patch("swag_mcp.services.swag_manager.SwagManagerService._get_docker_logs")
    async def test_get_swag_logs_success(self, mock_get_logs, service):
        """Test successful log retrieval."""
        mock_get_logs.return_value = "test log line 1\ntest log line 2"

        request = SwagLogsRequest(action=SwagAction.LOGS, log_type="nginx-error", lines=50)

        result = await service.get_swag_logs(request)

        assert "test log line 1" in result
        assert "test log line 2" in result

    @patch("swag_mcp.services.swag_manager.SwagManagerService._get_docker_logs")
    async def test_get_swag_logs_error(self, mock_get_logs, service):
        """Test log retrieval error."""
        mock_get_logs.side_effect = Exception("Docker not available")

        request = SwagLogsRequest(action=SwagAction.LOGS, log_type="nginx-error", lines=50)

        with pytest.raises(SwagServiceError):
            await service.get_swag_logs(request)

    # Resource Management Tests

    async def test_get_resource_configs(self, service, sample_config_file):
        """Test getting resource configurations."""
        result = await service.get_resource_configs()

        assert result.success is True
        assert len(result.configs) >= 1
        assert any(config.name == "test.subdomain.conf" for config in result.configs)

    async def test_get_sample_configs(self, service, temp_config):
        """Test getting sample configurations."""
        # Create sample file
        sample_path = temp_config.proxy_confs_path / "test.subdomain.conf.sample"
        sample_path.write_text("sample config")

        result = await service.get_sample_configs()

        assert result.success is True
        assert len(result.configs) >= 1
        assert any(config.name.endswith(".sample") for config in result.configs)

    async def test_get_service_samples(self, service, temp_config):
        """Test getting samples for specific service."""
        # Create service-specific sample
        sample_path = temp_config.proxy_confs_path / "testapp.subdomain.conf.sample"
        sample_path.write_text("testapp sample")

        result = await service.get_service_samples("testapp")

        assert result.success is True
        assert len(result.configs) >= 1

    # Error Condition Tests

    async def test_file_permission_error(self, service, temp_config):
        """Test handling of file permission errors."""
        # Make directory read-only
        temp_config.proxy_confs_path.chmod(0o444)

        request = SwagConfigRequest(
            action=SwagAction.CREATE,
            config_name="test.subdomain.conf",
            server_name="test.example.com",
            upstream_app="test",
            upstream_port=8080,
        )

        try:
            with pytest.raises(SwagServiceError):
                await service.create_config(request)
        finally:
            # Restore permissions for cleanup
            temp_config.proxy_confs_path.chmod(0o755)

    async def test_concurrent_file_access(self, service, sample_config_file):
        """Test concurrent file access with locking."""

        async def update_config():
            request = SwagEditRequest(
                action=SwagAction.EDIT,
                config_name="test.subdomain.conf",
                new_content="updated content",
            )
            return await service.update_config(request)

        # Run multiple concurrent updates
        results = await asyncio.gather(update_config(), update_config(), return_exceptions=True)

        # At least one should succeed
        success_count = sum(1 for r in results if hasattr(r, "success") and r.success)
        assert success_count >= 1

    async def test_invalid_utf8_content(self, service, temp_config):
        """Test handling of invalid UTF-8 content."""
        # Create file with invalid UTF-8
        config_path = temp_config.proxy_confs_path / "invalid.subdomain.conf"
        config_path.write_bytes(b"\xff\xfe invalid utf-8 \x80\x81")

        with pytest.raises(SwagServiceError):
            await service.read_config("invalid.subdomain.conf")

    # Edge Case Tests

    async def test_very_long_config_name(self, service):
        """Test handling of very long configuration names."""
        long_name = "a" * 300 + ".subdomain.conf"

        request = SwagConfigRequest(
            action=SwagAction.CREATE,
            config_name=long_name,
            server_name="test.example.com",
            upstream_app="test",
            upstream_port=8080,
        )

        with pytest.raises(SwagServiceError):
            await service.create_config(request)

    async def test_empty_config_content(self, service, temp_config):
        """Test handling of empty configuration files."""
        config_path = temp_config.proxy_confs_path / "empty.subdomain.conf"
        config_path.write_text("")

        content = await service.read_config("empty.subdomain.conf")
        assert content == ""

    async def test_binary_file_detection(self, service, temp_config):
        """Test detection and rejection of binary files."""
        binary_path = temp_config.proxy_confs_path / "binary.subdomain.conf"
        binary_path.write_bytes(bytes(range(256)))  # Binary data

        with pytest.raises(SwagServiceError):
            await service.read_config("binary.subdomain.conf")
