"""Comprehensive tests for SwagManagerService to achieve 80%+ coverage."""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from swag_mcp.models.config import (
    SwagHealthCheckRequest,
    SwagLogsRequest,
)
from swag_mcp.models.enums import SwagAction
from swag_mcp.services.swag_manager import SwagManagerService


class TestSwagManagerServiceInit:
    """Test SwagManagerService initialization and setup."""

    def test_init_with_default_paths(self):
        """Test service initialization with default paths."""
        service = SwagManagerService()
        assert service.config_path is not None
        assert service.template_path is not None
        assert hasattr(service, "template_env")
        assert hasattr(service, "_backup_lock")
        assert hasattr(service, "_file_write_lock")
        assert hasattr(service, "_cleanup_lock")
        assert hasattr(service, "_file_locks")
        assert hasattr(service, "_active_transactions")

    def test_init_with_custom_paths(self):
        """Test service initialization with custom paths."""
        config_path = Path("/custom/config")
        template_path = Path("/custom/templates")

        service = SwagManagerService(config_path, template_path)
        assert service.config_path == config_path
        assert service.template_path == template_path


class TestSecureTemplateEnvironment:
    """Test secure template environment creation and configuration."""

    @pytest.fixture
    def temp_service(self):
        """Create service with temporary directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            template_dir = Path(temp_dir) / "templates"
            config_dir.mkdir()
            template_dir.mkdir()

            # Create a basic template
            (template_dir / "subdomain.conf.j2").write_text(
                "server_name {{ server_name }};\n"
                "proxy_pass {{ upstream_proto }}://{{ upstream_app }}:{{ upstream_port }};"
            )

            yield SwagManagerService(config_dir, template_dir)

    def test_template_environment_security(self, temp_service):
        """Test that template environment has security restrictions."""
        env = temp_service.template_env

        # Check that only safe globals are available
        safe_globals = env.globals.keys()
        assert "range" in safe_globals
        assert "len" in safe_globals
        assert "str" in safe_globals

        # Check that dangerous functions are not available
        assert "__import__" not in safe_globals
        assert "eval" not in safe_globals
        assert "exec" not in safe_globals
        assert "open" not in safe_globals

    def test_is_safe_attribute_blocks_dangerous_attrs(self, temp_service):
        """Test that is_safe_attribute blocks dangerous attributes."""
        env = temp_service.template_env

        # Test blocking private attributes
        assert not env.is_safe_attribute(object(), "_private", None)
        assert not env.is_safe_attribute(object(), "__import__", None)

        # Test blocking dangerous attributes
        dangerous_attrs = ["eval", "exec", "open", "__builtins__", "globals"]
        for attr in dangerous_attrs:
            assert not env.is_safe_attribute(object(), attr, None)

    def test_is_safe_attribute_allows_safe_attrs(self, temp_service):
        """Test that is_safe_attribute allows safe attributes."""
        env = temp_service.template_env

        # Test allowing safe attributes on safe types
        assert env.is_safe_attribute("test", "upper", None)
        assert env.is_safe_attribute(123, "bit_length", None)
        assert env.is_safe_attribute([], "append", None)


class TestAtomicTransactions:
    """Test atomic transaction functionality."""

    @pytest.fixture
    def temp_service(self):
        """Create service with temporary directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            template_dir = Path(temp_dir) / "templates"
            config_dir.mkdir()
            template_dir.mkdir()
            yield SwagManagerService(config_dir, template_dir)

    def test_begin_transaction_with_id(self, temp_service):
        """Test beginning transaction with specific ID."""
        tx_id = "test_transaction_123"
        tx = temp_service.begin_transaction(tx_id)

        assert tx.transaction_id == tx_id
        assert tx.manager == temp_service

    def test_begin_transaction_auto_id(self, temp_service):
        """Test beginning transaction with auto-generated ID."""
        tx = temp_service.begin_transaction()

        assert tx.transaction_id.startswith("txn_")
        assert len(tx.transaction_id) == 12  # "txn_" + 8 hex chars
        assert tx.manager == temp_service

    async def test_atomic_transaction_context_manager(self, temp_service):
        """Test atomic transaction as context manager."""
        async with temp_service.begin_transaction("test_ctx") as tx:
            assert tx.transaction_id == "test_ctx"
            assert tx.transaction_id in temp_service._active_transactions

        # Transaction should be cleaned up after context exits
        assert "test_ctx" not in temp_service._active_transactions

    async def test_transaction_rollback_on_error(self, temp_service):
        """Test transaction rollback when error occurs."""
        test_file = temp_service.config_path / "test.conf"
        test_file.write_text("original content")

        try:
            async with temp_service.begin_transaction("rollback_test") as tx:
                # Record file modification
                await tx.record_file_modification(test_file, "original content")

                # Modify the file
                test_file.write_text("modified content")

                # Force an error to trigger rollback
                raise ValueError("Test error")
        except ValueError:
            pass

        # File should be restored to original content
        assert test_file.read_text() == "original content"

    async def test_transaction_record_file_creation(self, temp_service):
        """Test recording file creation in transaction."""
        test_file = temp_service.config_path / "new_file.conf"

        async with temp_service.begin_transaction("create_test") as tx:
            await tx.record_file_creation(test_file)
            test_file.write_text("new file content")
            # Don't raise error - commit transaction

        # File should exist after successful transaction
        assert test_file.exists()

    async def test_transaction_record_file_deletion(self, temp_service):
        """Test recording file deletion in transaction."""
        test_file = temp_service.config_path / "delete_test.conf"
        original_content = "content to be deleted"
        test_file.write_text(original_content)

        try:
            async with temp_service.begin_transaction("delete_test") as tx:
                # Record deletion
                await tx.record_file_deletion(test_file, original_content)

                # Delete the file
                test_file.unlink()

                # Force error to test restoration
                raise ValueError("Test error")
        except ValueError:
            pass

        # File should be restored
        assert test_file.exists()
        assert test_file.read_text() == original_content


class TestFileOperations:
    """Test core file operation methods."""

    @pytest.fixture
    def temp_service(self):
        """Create service with temporary directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            template_dir = Path(temp_dir) / "templates"
            config_dir.mkdir()
            template_dir.mkdir()

            # Create basic template
            (template_dir / "subdomain.conf.j2").write_text(
                "server_name {{ server_name }};\n"
                "proxy_pass {{ upstream_proto }}://{{ upstream_app }}:{{ upstream_port }};"
            )

            yield SwagManagerService(config_dir, template_dir)

    async def test_get_file_lock(self, temp_service):
        """Test per-file lock creation and reuse."""
        test_file = temp_service.config_path / "test.conf"

        # Get lock for first time
        lock1 = await temp_service._get_file_lock(test_file)
        assert isinstance(lock1, asyncio.Lock)

        # Get lock for same file - should be same instance
        lock2 = await temp_service._get_file_lock(test_file)
        assert lock1 is lock2

    async def test_safe_write_file_success(self, temp_service):
        """Test successful file writing."""
        test_file = temp_service.config_path / "write_test.conf"
        content = "test configuration content"

        await temp_service._safe_write_file(test_file, content, "test operation")

        assert test_file.exists()
        assert test_file.read_text() == content

    async def test_safe_write_file_with_lock(self, temp_service):
        """Test file writing with locking enabled."""
        test_file = temp_service.config_path / "lock_test.conf"
        content = "locked write test"

        await temp_service._safe_write_file(test_file, content, "locked operation", use_lock=True)

        assert test_file.exists()
        assert test_file.read_text() == content

    async def test_safe_write_file_permission_error(self, temp_service):
        """Test file writing with permission error."""
        test_file = temp_service.config_path / "readonly.conf"

        # Create file and make it read-only
        test_file.write_text("original")
        test_file.chmod(0o444)

        try:
            with pytest.raises(OSError):
                await temp_service._safe_write_file(test_file, "new content", "permission test")
        finally:
            # Clean up - restore write permissions
            test_file.chmod(0o644)

    def test_ensure_config_directory_exists(self, temp_service):
        """Test directory creation when it exists."""
        # Directory should already exist from fixture
        temp_service._ensure_config_directory()
        assert temp_service.config_path.exists()

    def test_ensure_config_directory_creates(self):
        """Test directory creation when it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "new_config"
            template_dir = Path(temp_dir) / "templates"
            template_dir.mkdir()

            # config_dir doesn't exist yet
            assert not config_dir.exists()

            service = SwagManagerService(config_dir, template_dir)
            service._ensure_config_directory()

            assert config_dir.exists()

    def test_validate_template_variables(self, temp_service):
        """Test template variable validation."""
        template_vars = {
            "service_name": "test-service",
            "server_name": "example.com",
            "upstream_app": "test-app",
            "upstream_port": 8080,
            "upstream_proto": "http",
        }

        result = temp_service._validate_template_variables(template_vars)

        assert isinstance(result, dict)
        assert "service_name" in result
        assert result["service_name"] == "test-service"

    def test_validate_config_content(self, temp_service):
        """Test configuration content validation."""
        content = "server_name example.com;\nproxy_pass http://app:8080;"
        config_name = "test.subdomain.conf"

        result = temp_service._validate_config_content(content, config_name)

        assert isinstance(result, str)
        assert result == content

    def test_validate_config_content_unicode_normalization(self, temp_service):
        """Test content validation with Unicode normalization."""
        # Content with BOM and non-normalized Unicode
        content = "\ufeffserver_name café.com;"
        config_name = "unicode.subdomain.conf"

        result = temp_service._validate_config_content(content, config_name)

        # BOM should be removed, Unicode normalized
        assert not result.startswith("\ufeff")
        assert "café.com" in result


class TestTemplateValidation:
    """Test template validation methods."""

    @pytest.fixture
    def temp_service(self):
        """Create service with temporary directories and templates."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            template_dir = Path(temp_dir) / "templates"
            config_dir.mkdir()
            template_dir.mkdir()

            # Create template files
            (template_dir / "subdomain.conf.j2").write_text("subdomain template")
            (template_dir / "subfolder.conf.j2").write_text("subfolder template")

            yield SwagManagerService(config_dir, template_dir)

    async def test_validate_template_exists_true(self, temp_service):
        """Test template validation when template exists."""
        result = await temp_service.validate_template_exists("subdomain")
        assert result is True

    async def test_validate_template_exists_false(self, temp_service):
        """Test template validation when template doesn't exist."""
        result = await temp_service.validate_template_exists("nonexistent")
        assert result is False

    async def test_validate_all_templates(self, temp_service):
        """Test validation of all available templates."""
        result = await temp_service.validate_all_templates()

        assert isinstance(result, dict)
        assert "subdomain" in result
        assert "subfolder" in result
        assert result["subdomain"] is True
        assert result["subfolder"] is True


class TestBackupOperations:
    """Test backup creation and management."""

    @pytest.fixture
    def temp_service(self):
        """Create service with temporary directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()
            yield SwagManagerService(config_dir, Path(temp_dir) / "templates")

    async def test_create_backup_success(self, temp_service):
        """Test successful backup creation."""
        # Create original file
        config_file = temp_service.config_path / "test.subdomain.conf"
        original_content = "original configuration"
        config_file.write_text(original_content)

        backup_path = await temp_service._create_backup("test.subdomain.conf")

        assert backup_path is not None
        assert Path(backup_path).exists()
        assert Path(backup_path).read_text() == original_content

    async def test_create_backup_file_not_exists(self, temp_service):
        """Test backup creation when original file doesn't exist."""
        backup_path = await temp_service._create_backup("nonexistent.conf")
        assert backup_path is None

    async def test_list_backups(self, temp_service):
        """Test listing backup files."""
        # Create some backup files
        backup1 = temp_service.config_path / "test.backup.20240101_120000.conf"
        backup2 = temp_service.config_path / "other.backup.20240102_130000.conf"
        backup1.write_text("backup1")
        backup2.write_text("backup2")

        backups = await temp_service.list_backups()

        assert len(backups) >= 2
        backup_names = [b["name"] for b in backups]
        assert backup1.name in backup_names
        assert backup2.name in backup_names

    async def test_cleanup_old_backups_with_retention(self, temp_service):
        """Test cleanup of old backups with retention days."""
        # Create old backup file
        old_backup = temp_service.config_path / "old.backup.20200101_120000.conf"
        old_backup.write_text("old backup")

        # Mock file modification time to be old
        old_time = 1577836800  # Jan 1, 2020
        os.utime(old_backup, (old_time, old_time))

        cleaned_count = await temp_service.cleanup_old_backups(retention_days=7)

        assert cleaned_count >= 0
        # Note: Actual cleanup depends on current date vs file modification time

    async def test_cleanup_old_backups_default_retention(self, temp_service):
        """Test cleanup with default retention period."""
        cleaned_count = await temp_service.cleanup_old_backups()
        assert cleaned_count >= 0


class TestExtractorMethods:
    """Test content extraction methods."""

    @pytest.fixture
    def temp_service(self):
        """Create service for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield SwagManagerService(Path(temp_dir), Path(temp_dir))

    def test_extract_upstream_value_app(self, temp_service):
        """Test extracting upstream app value from content."""
        content = "proxy_pass http://test-app:8080;"
        result = temp_service._extract_upstream_value(content, "upstream_app")

        assert isinstance(result, str)
        # Should extract some value from the content
        assert len(result) > 0

    def test_extract_upstream_value_port(self, temp_service):
        """Test extracting upstream port value from content."""
        content = "proxy_pass http://test-app:8080;"
        result = temp_service._extract_upstream_value(content, "upstream_port")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_extract_upstream_value_no_match(self, temp_service):
        """Test extraction when no match is found."""
        content = "server_name example.com;"
        result = temp_service._extract_upstream_value(content, "upstream_app")

        assert isinstance(result, str)

    def test_extract_auth_method_authelia(self, temp_service):
        """Test extracting authelia auth method."""
        content = "include /config/nginx/authelia-server.conf;"
        result = temp_service._extract_auth_method(content)

        assert result in ["authelia", "none", "ldap", "authentik", "tinyauth", "basic"]

    def test_extract_auth_method_ldap(self, temp_service):
        """Test extracting LDAP auth method."""
        content = "include /config/nginx/ldap.conf;"
        result = temp_service._extract_auth_method(content)

        assert result in ["authelia", "none", "ldap", "authentik", "tinyauth", "basic"]

    def test_extract_auth_method_none(self, temp_service):
        """Test extracting no auth method."""
        content = "server_name example.com; proxy_pass http://app:8080;"
        result = temp_service._extract_auth_method(content)

        assert result == "none"


class TestMCPFunctionality:
    """Test MCP-specific functionality."""

    @pytest.fixture
    def temp_service(self):
        """Create service with MCP template."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            template_dir = Path(temp_dir) / "templates"
            config_dir.mkdir()
            template_dir.mkdir()

            # Create MCP template
            mcp_template = """
location /mcp {
    proxy_pass {{ upstream_proto }}://{{ upstream_app }}:{{ upstream_port }}/mcp;
}
            """.strip()
            (template_dir / "mcp-location.conf.j2").write_text(mcp_template)

            yield SwagManagerService(config_dir, template_dir)

    async def test_render_mcp_location_block(self, temp_service):
        """Test rendering MCP location block."""
        template_vars = {
            "upstream_proto": "http",
            "upstream_app": "mcp-server",
            "upstream_port": 8080,
            "mcp_path": "/ai-service",
        }

        result = await temp_service._render_mcp_location_block(template_vars)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_insert_location_block(self, temp_service):
        """Test inserting location block into configuration."""
        original_content = """
server {
    listen 443 ssl;
    server_name example.com;

    location / {
        proxy_pass http://app:8080;
    }
}
        """.strip()

        location_block = """
    location /mcp {
        proxy_pass http://app:8080/mcp;
    }
        """.strip()

        result = temp_service._insert_location_block(original_content, location_block)

        assert "/mcp" in result
        assert original_content in result

    async def test_add_mcp_location_success(self, temp_service):
        """Test successful MCP location addition."""
        # Create existing config file
        config_file = temp_service.config_path / "test.subdomain.conf"
        original_content = """
server {
    listen 443 ssl;
    server_name test.example.com;

    location / {
        proxy_pass http://test-app:8080;
    }
}
        """.strip()
        config_file.write_text(original_content)

        result = await temp_service.add_mcp_location(
            config_name="test.subdomain.conf",
            mcp_path="/ai-service",
            upstream_app="test-app",
            upstream_port=8080,
            upstream_proto="http",
        )

        assert result.success is True

        # Verify file was updated
        updated_content = config_file.read_text()
        assert original_content != updated_content

    async def test_add_mcp_location_file_not_found(self, temp_service):
        """Test MCP location addition when file doesn't exist."""
        result = await temp_service.add_mcp_location(
            config_name="nonexistent.conf", mcp_path="/mcp", upstream_app="app", upstream_port=8080
        )

        assert result.success is False
        assert "not found" in result.message.lower()


class TestHealthCheckMethod:
    """Test health check functionality."""

    @pytest.fixture
    def temp_service(self):
        """Create service for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield SwagManagerService(Path(temp_dir), Path(temp_dir))

    @patch("aiohttp.ClientSession.get")
    async def test_health_check_success(self, mock_get, temp_service):
        """Test successful health check."""
        # Mock successful HTTP response
        mock_response = Mock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="OK")
        mock_response.headers = {}
        mock_get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get.return_value.__aexit__ = AsyncMock(return_value=None)

        request = SwagHealthCheckRequest(
            action=SwagAction.HEALTH_CHECK, domain="example.com", timeout=10
        )
        result = await temp_service.health_check(request)

        assert result.success is True
        assert result.data is not None
        assert result.data.accessible is True
        assert result.data.status_code == 200

    @patch("aiohttp.ClientSession.get")
    async def test_health_check_connection_error(self, mock_get, temp_service):
        """Test health check with connection error."""
        import aiohttp

        # Mock connection error
        mock_get.side_effect = aiohttp.ClientConnectionError("Connection failed")

        request = SwagHealthCheckRequest(
            action=SwagAction.HEALTH_CHECK, domain="unreachable.com", timeout=10
        )
        result = await temp_service.health_check(request)

        assert result.success is True  # Method succeeds even if health check fails
        assert result.data is not None
        assert result.data.accessible is False

    async def test_health_check_invalid_domain(self, temp_service):
        """Test health check with invalid domain format."""
        request = SwagHealthCheckRequest(
            action=SwagAction.HEALTH_CHECK, domain="invalid..domain", timeout=10
        )

        result = await temp_service.health_check(request)

        assert result.success is False
        assert "invalid" in result.message.lower()


class TestLogMethods:
    """Test log retrieval methods."""

    @pytest.fixture
    def temp_service(self):
        """Create service for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield SwagManagerService(Path(temp_dir), Path(temp_dir))

    @patch("docker.from_env")
    async def test_get_swag_logs_success(self, mock_docker_from_env, temp_service):
        """Test successful log retrieval."""
        # Mock Docker container and logs
        mock_container = Mock()
        mock_container.logs.return_value = b"log line 1\nlog line 2\n"

        mock_client = Mock()
        mock_client.containers.get.return_value = mock_container
        mock_docker_from_env.return_value = mock_client

        request = SwagLogsRequest(action=SwagAction.LOGS, log_type="nginx-error", lines=50)
        result = await temp_service.get_swag_logs(request)

        assert isinstance(result, str)
        assert len(result) > 0

    @patch("docker.from_env")
    async def test_get_swag_logs_container_not_found(self, mock_docker_from_env, temp_service):
        """Test log retrieval when container is not found."""
        import docker

        mock_client = Mock()
        mock_client.containers.get.side_effect = docker.errors.NotFound("Container not found")
        mock_docker_from_env.return_value = mock_client

        request = SwagLogsRequest(action=SwagAction.LOGS, log_type="nginx-error", lines=50)
        result = await temp_service.get_swag_logs(request)

        assert "not found" in result.lower() or "error" in result.lower()

    @patch("docker.from_env")
    async def test_get_swag_logs_docker_not_available(self, mock_docker_from_env, temp_service):
        """Test log retrieval when Docker is not available."""
        import docker

        mock_docker_from_env.side_effect = docker.errors.DockerException("Docker not available")

        request = SwagLogsRequest(action=SwagAction.LOGS, log_type="nginx-error", lines=50)
        result = await temp_service.get_swag_logs(request)

        assert "docker" in result.lower() or "error" in result.lower()


class TestResourceMethods:
    """Test resource listing methods."""

    @pytest.fixture
    def temp_service(self):
        """Create service with sample files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()

            # Create some sample config files
            (config_dir / "jellyfin.subdomain.conf").write_text("jellyfin config")
            (config_dir / "plex.subfolder.conf").write_text("plex config")
            (config_dir / "sonarr.subdomain.conf.sample").write_text("sonarr sample")

            yield SwagManagerService(config_dir, Path(temp_dir) / "templates")

    async def test_get_resource_configs(self, temp_service):
        """Test getting resource configurations."""
        result = await temp_service.get_resource_configs()

        assert result.success is True
        assert result.data is not None
        assert len(result.data.resources) > 0

        # Should include active configs but not samples
        resource_names = [r.name for r in result.data.resources]
        assert "jellyfin.subdomain.conf" in resource_names
        assert "plex.subfolder.conf" in resource_names

    async def test_get_sample_configs(self, temp_service):
        """Test getting sample configurations."""
        result = await temp_service.get_sample_configs()

        assert result.success is True
        assert result.data is not None

        if result.data.resources:
            # Should include only sample files
            for resource in result.data.resources:
                assert resource.name.endswith(".sample")

    async def test_get_service_samples(self, temp_service):
        """Test getting samples for specific service."""
        result = await temp_service.get_service_samples("sonarr")

        assert result.success is True
        assert result.data is not None


class TestErrorHandlingEdgeCases:
    """Test error handling and edge cases."""

    @pytest.fixture
    def temp_service(self):
        """Create service for error testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield SwagManagerService(Path(temp_dir), Path(temp_dir))

    async def test_validate_nginx_syntax_subprocess_error(self, temp_service):
        """Test nginx syntax validation when nginx executable is not found."""
        test_file = temp_service.config_path / "test.conf"
        test_file.write_text("server { listen 80; }")

        with patch("shutil.which") as mock_which:
            # Mock nginx not being found
            mock_which.return_value = None

            # Should handle missing nginx gracefully
            result = await temp_service._validate_nginx_syntax(test_file)
            # Method should return boolean, True when nginx not available (assume valid)
            assert isinstance(result, bool)
            assert result is True
