"""Tests for SwagManagerService."""

import contextlib
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from swag_mcp.models.config import (
    SwagConfigRequest,
    SwagEditRequest,
    SwagListResult,
    SwagRemoveRequest,
)
from swag_mcp.services.swag_manager import SwagManagerService


class TestSwagManagerService:
    """Test suite for SwagManagerService."""

    @pytest.mark.asyncio
    async def test_list_configs_all(self, swag_service: SwagManagerService, sample_configs):
        """Test listing all configurations."""
        result = await swag_service.list_configs("all")

        assert isinstance(result, SwagListResult)
        assert result.total_count >= 1  # At least our test.conf
        assert result.config_type == "all"

        # Check for expected files
        assert "test.conf" in result.configs

    @pytest.mark.asyncio
    async def test_list_configs_active_only(self, swag_service: SwagManagerService, sample_configs):
        """Test listing active configurations only."""
        result = await swag_service.list_configs("active")

        assert result.config_type == "active"
        config_names = result.configs

        # Should include .conf files but not .sample files
        assert "testapp.subdomain.conf" in config_names
        assert "webapp.subfolder.conf" in config_names
        assert "sampleapp.conf.sample" not in config_names

    @pytest.mark.asyncio
    async def test_list_configs_samples_only(
        self, swag_service: SwagManagerService, sample_configs
    ):
        """Test listing sample configurations only."""
        result = await swag_service.list_configs("samples")

        assert result.config_type == "samples"
        config_names = result.configs

        # Should include .sample files only
        assert "sampleapp.conf.sample" in config_names
        assert "testapp.subdomain.conf" not in config_names
        assert "webapp.subfolder.conf" not in config_names

    @pytest.mark.asyncio
    async def test_get_config_content(self, swag_service: SwagManagerService, sample_configs):
        """Test reading configuration file content."""
        content = await swag_service.read_config("testapp.subdomain.conf")

        assert "testapp" in content
        assert "server_name testapp.*;" in content
        assert "set $upstream_app testapp;" in content

    @pytest.mark.asyncio
    async def test_get_config_content_not_found(self, swag_service: SwagManagerService):
        """Test reading non-existent configuration file."""
        with pytest.raises(FileNotFoundError):
            await swag_service.read_config("nonexistent.conf")

    @pytest.mark.asyncio
    async def test_create_config_subdomain(self, swag_service: SwagManagerService):
        """Test creating subdomain configuration."""
        config_file = swag_service.config_path / "myapp.subdomain.conf"

        # Clean up any existing file from previous runs
        if config_file.exists():
            config_file.unlink()

        try:
            request = SwagConfigRequest(
                service_name="myapp",
                server_name="myapp.example.com",
                upstream_app="myapp",
                upstream_port=3000,
                upstream_proto="http",
                auth_method="authelia",
                enable_quic=False,
                config_type="subdomain",
            )

            result = await swag_service.create_config(request)

            assert result.filename == "myapp.subdomain.conf"
            assert "myapp" in result.content

            # Check file was created
            assert config_file.exists()

            # Check content
            content = config_file.read_text()
            assert "server_name myapp.example.com;" in content
            assert "set $upstream_app myapp;" in content
            assert "set $upstream_port 3000;" in content
            assert "authelia-location.conf" in content
        finally:
            # Cleanup created file
            if config_file.exists():
                config_file.unlink()

    @pytest.mark.asyncio
    async def test_create_config_subfolder(self, swag_service: SwagManagerService):
        """Test creating subfolder configuration."""
        config_file = swag_service.config_path / "webapp.subfolder.conf"

        # Clean up any existing file from previous runs
        if config_file.exists():
            config_file.unlink()

        try:
            request = SwagConfigRequest(
                service_name="webapp",
                server_name="example.com",  # Fixed: removed /webapp path
                upstream_app="webapp-container",
                upstream_port=8080,
                upstream_proto="https",
                auth_method="none",
                enable_quic=False,
                config_type="subfolder",
            )

            result = await swag_service.create_config(request)

            assert result.filename == "webapp.subfolder.conf"
            assert "webapp" in result.content

            # Check file was created
            assert config_file.exists()

            # Check content
            content = config_file.read_text()
            assert "location /webapp" in content
            assert "set $upstream_app webapp-container;" in content
            assert "set $upstream_port 8080;" in content
            assert "set $upstream_proto https;" in content
        finally:
            # Cleanup created file
            if config_file.exists():
                config_file.unlink()

    @pytest.mark.asyncio
    async def test_create_config_file_exists(
        self, swag_service: SwagManagerService, sample_configs
    ):
        """Test creating configuration when file already exists."""
        request = SwagConfigRequest(
            service_name="testapp",
            server_name="testapp.example.com",
            upstream_app="testapp",
            upstream_port=8080,
            config_type="subdomain",
        )

        with pytest.raises(ValueError, match="Configuration.*already exists"):
            await swag_service.create_config(request)

    @pytest.mark.asyncio
    async def test_update_config(self, swag_service: SwagManagerService, sample_configs):
        """Test updating configuration file content."""
        new_content = "# Updated configuration\nserver { listen 443; }"

        request = SwagEditRequest(
            config_name="testapp.subdomain.conf", new_content=new_content, create_backup=True
        )
        result = await swag_service.update_config(request)

        assert result.filename == "testapp.subdomain.conf"
        assert result.content == new_content
        assert result.backup_created is not None

        # Check content was updated
        config_file = swag_service.config_path / "testapp.subdomain.conf"
        assert config_file.read_text() == new_content

        # Verify backup was created
        backup_file = swag_service.config_path / result.backup_created
        assert backup_file.exists()

        # Clean up backup file (the autouse fixture will also clean it up, but be explicit)
        with contextlib.suppress(PermissionError, OSError):
            backup_file.unlink()

    @pytest.mark.asyncio
    async def test_update_config_not_found(self, swag_service: SwagManagerService):
        """Test updating non-existent configuration file."""
        request = SwagEditRequest(
            config_name="nonexistent.conf", new_content="new content", create_backup=False
        )
        result = await swag_service.update_config(request)

        # Service will create the file even if it doesn't exist
        assert result.filename == "nonexistent.conf"
        assert result.content == "new content"

        # Clean up created file
        config_file = swag_service.config_path / "nonexistent.conf"
        if config_file.exists():
            config_file.unlink()

    @pytest.mark.asyncio
    async def test_delete_config_with_backup(
        self, swag_service: SwagManagerService, sample_configs, test_helpers
    ):
        """Test deleting configuration with backup creation."""
        request = SwagRemoveRequest(config_name="testapp.subdomain.conf", create_backup=True)
        result = await swag_service.remove_config(request)

        assert result.filename == "testapp.subdomain.conf"
        assert result.backup_created is not None

        # Check original file is deleted
        config_file = swag_service.config_path / "testapp.subdomain.conf"
        assert not config_file.exists()

        # Check backup was created
        backup_file = test_helpers.assert_backup_created(
            swag_service.config_path, "testapp.subdomain.conf"
        )

        # Clean up backup file since we created it for testing
        with contextlib.suppress(PermissionError, OSError):
            backup_file.unlink()

    @pytest.mark.asyncio
    async def test_delete_config_without_backup(
        self, swag_service: SwagManagerService, sample_configs
    ):
        """Test deleting configuration without backup."""
        request = SwagRemoveRequest(config_name="webapp.subfolder.conf", create_backup=False)
        result = await swag_service.remove_config(request)

        assert result.filename == "webapp.subfolder.conf"
        assert result.backup_created is None

        # Check file is deleted
        config_file = swag_service.config_path / "webapp.subfolder.conf"
        assert not config_file.exists()

        # Check no backup was created
        backup_files = list(swag_service.config_path.glob("webapp.subfolder.conf.backup.*"))
        assert len(backup_files) == 0

    @pytest.mark.asyncio
    async def test_delete_config_not_found(self, swag_service: SwagManagerService):
        """Test deleting non-existent configuration file."""
        with pytest.raises(FileNotFoundError):
            request = SwagRemoveRequest(config_name="nonexistent.conf")
            await swag_service.remove_config(request)

    @pytest.mark.asyncio
    async def test_cleanup_old_backups(self, swag_service: SwagManagerService):
        """Test cleaning up old backup files."""
        # Create some old backup files using correct format
        old_date = datetime.now() - timedelta(days=31)
        old_timestamp = old_date.strftime("%Y%m%d_%H%M%S")

        recent_date = datetime.now() - timedelta(days=7)
        recent_timestamp = recent_date.strftime("%Y%m%d_%H%M%S")

        old_backup = swag_service.config_path / f"testapp.conf.backup.{old_timestamp}"
        recent_backup = swag_service.config_path / f"testapp.conf.backup.{recent_timestamp}"

        old_backup.write_text("# Old backup")
        recent_backup.write_text("# Recent backup")

        # Set modification times
        import os

        os.utime(old_backup, (old_date.timestamp(), old_date.timestamp()))
        os.utime(recent_backup, (recent_date.timestamp(), recent_date.timestamp()))

        try:
            # Run cleanup
            count = await swag_service.cleanup_old_backups()

            assert count == 1
            assert not old_backup.exists()
            assert recent_backup.exists()
        finally:
            # Cleanup any remaining test backup files
            if old_backup.exists():
                old_backup.unlink()
            if recent_backup.exists():
                recent_backup.unlink()

    @pytest.mark.asyncio
    async def test_validate_config_name_valid(
        self, swag_service: SwagManagerService, sample_configs
    ):
        """Test validation of valid configuration names."""
        valid_names = [
            "test.conf",
            "testapp.subdomain.conf",
            "webapp.subfolder.conf",
            "sampleapp.conf.sample",
        ]

        for name in valid_names:
            # Should not raise any exception (files exist via sample_configs fixture)
            content = await swag_service.read_config(name)
            assert isinstance(content, str)
            assert len(content) > 0

    @pytest.mark.asyncio
    async def test_template_rendering_error(self, swag_service: SwagManagerService):
        """Test handling of template rendering errors."""
        # Create a test that passes validation but will fail at template level
        # We'll temporarily move the template to simulate missing template
        template_file = swag_service.template_path / "subdomain.conf.j2"
        backup_name = None

        if template_file.exists():
            backup_name = str(template_file) + ".backup"
            template_file.rename(backup_name)

        try:
            request = SwagConfigRequest(
                service_name="test",
                server_name="test.com",
                upstream_app="test",
                upstream_port=8080,
                config_type="subdomain",
            )

            with pytest.raises(ValueError, match="Template.*not found"):
                await swag_service.create_config(request)
        finally:
            # Restore template if we moved it
            if backup_name and Path(backup_name).exists():
                Path(backup_name).rename(template_file)

    @pytest.mark.asyncio
    async def test_permission_error_handling(self, swag_service: SwagManagerService):
        """Test handling of permission errors."""
        # Create read-only directory with unique name to avoid conflicts
        import uuid

        readonly_dir = swag_service.config_path / f"readonly_{uuid.uuid4().hex[:8]}"

        # Clean up if it already exists
        if readonly_dir.exists():
            readonly_dir.chmod(0o755)  # Make writable to remove
            readonly_dir.rmdir()

        readonly_dir.mkdir(mode=0o444)

        try:
            # Temporarily change the service config path
            original_path = swag_service.config_path
            swag_service.config_path = readonly_dir

            request = SwagConfigRequest(
                service_name="test",
                server_name="test.com",
                upstream_app="test",
                upstream_port=8080,
                config_type="subdomain",
            )

            with pytest.raises(PermissionError):
                await swag_service.create_config(request)
        finally:
            # Restore original path and cleanup
            swag_service.config_path = original_path
            if readonly_dir.exists():
                readonly_dir.chmod(0o755)  # Make writable to remove
                readonly_dir.rmdir()

    @pytest.mark.asyncio
    async def test_create_config_template_render_error(self, swag_service: SwagManagerService):
        """Test creating configuration with template render error (line 122-123)."""
        import uuid

        service_name = f"errorapp{uuid.uuid4().hex[:8]}"
        config_file = swag_service.config_path / f"{service_name}.subdomain.conf"

        # Ensure the file doesn't exist
        if config_file.exists():
            config_file.unlink()

        # Patch the template_env instance attribute correctly
        original_get_template = swag_service.template_env.get_template

        def mock_get_template(template_name):
            mock_template = MagicMock()
            mock_template.render.side_effect = Exception("Template render error")
            return mock_template

        swag_service.template_env.get_template = mock_get_template

        try:
            request = SwagConfigRequest(
                service_name=service_name,
                server_name=f"{service_name}.example.com",
                upstream_app=service_name,
                upstream_port=3000,
                config_type="subdomain",
            )

            with pytest.raises(
                ValueError, match="Failed to render template: Template render error"
            ):
                await swag_service.create_config(request)
        finally:
            # Restore original method
            swag_service.template_env.get_template = original_get_template
            # Cleanup any created file
            if config_file.exists():
                config_file.unlink()

    @pytest.mark.asyncio
    async def test_validate_template_not_found(self, swag_service: SwagManagerService):
        """Test template validation with TemplateNotFound (lines 180-181)."""
        from jinja2 import TemplateNotFound

        # Patch the instance method correctly
        original_get_template = swag_service.template_env.get_template

        def mock_get_template(template_name):
            raise TemplateNotFound("missing.j2")

        swag_service.template_env.get_template = mock_get_template

        try:
            result = await swag_service.validate_template_exists("missing")
            assert result is False
        finally:
            # Restore original method
            swag_service.template_env.get_template = original_get_template

    @pytest.mark.asyncio
    async def test_get_docker_logs_timeout_error(self, swag_service: SwagManagerService):
        """Test docker logs with timeout error (lines 241-242)."""
        from swag_mcp.models.config import SwagLogsRequest

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker logs", timeout=5)

            with pytest.raises(FileNotFoundError, match="No SWAG container found"):
                await swag_service.get_docker_logs(SwagLogsRequest())

    @pytest.mark.asyncio
    async def test_get_docker_logs_general_exception(self, swag_service: SwagManagerService):
        """Test docker logs with general exception (lines 243-244)."""
        from swag_mcp.models.config import SwagLogsRequest

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Docker error")

            with pytest.raises(FileNotFoundError, match="No SWAG container found"):
                await swag_service.get_docker_logs(SwagLogsRequest())

    @pytest.mark.asyncio
    async def test_get_docker_logs_no_container_found(self, swag_service: SwagManagerService):
        """Test docker logs when no container is found (lines 247-260)."""
        from swag_mcp.models.config import SwagLogsRequest

        # Mock the docker logs commands to fail (no container)
        def mock_run_side_effect(cmd, **kwargs):
            if "docker logs" in " ".join(cmd):
                # Return non-zero exit code for logs commands
                mock_result = MagicMock()
                mock_result.returncode = 1
                mock_result.stderr = "Container not found"
                return mock_result
            elif "docker ps" in " ".join(cmd):
                # Return container list
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = "NAMES\tIMAGE\ntest-container\ttest-image"
                return mock_result
            return MagicMock(returncode=1)

        with patch("subprocess.run", side_effect=mock_run_side_effect):
            with pytest.raises(FileNotFoundError) as exc_info:
                await swag_service.get_docker_logs(SwagLogsRequest())

            assert "No SWAG container found" in str(exc_info.value)
            assert "Available containers:" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_docker_logs_general_error_handling(self, swag_service: SwagManagerService):
        """Test docker logs general error handling (lines 262-264)."""
        from swag_mcp.models.config import SwagLogsRequest

        with (
            patch("subprocess.run", side_effect=OSError("Docker not found")),
            pytest.raises(OSError, match="Docker not found"),
        ):
            await swag_service.get_docker_logs(SwagLogsRequest())

    @pytest.mark.asyncio
    async def test_cleanup_old_backups_error_handling(self, swag_service: SwagManagerService):
        """Test cleanup old backups with permission error during unlink."""
        from datetime import datetime, timedelta
        from unittest.mock import patch

        # Create a temporary backup file that matches the pattern
        old_date = datetime.now() - timedelta(days=31)
        old_timestamp = old_date.strftime("%Y%m%d_%H%M%S")
        backup_name = f"test.conf.backup.{old_timestamp}"
        backup_file = swag_service.config_path / backup_name

        # Create the backup file
        backup_file.write_text("# Test backup")

        # Set the file modification time to be old
        import os

        os.utime(backup_file, (old_date.timestamp(), old_date.timestamp()))

        # Patch pathlib.Path.unlink to raise PermissionError for our specific file

        def mock_unlink_side_effect():
            raise PermissionError("Permission denied")

        with patch("pathlib.Path.unlink", side_effect=mock_unlink_side_effect):
            # This should handle the PermissionError gracefully
            removed_count = await swag_service.cleanup_old_backups()

            # Should return 0 since the file couldn't be removed due to permissions
            assert removed_count == 0
            assert backup_file.exists()  # File should still exist

        # Cleanup the test file
        if backup_file.exists():
            backup_file.unlink()
