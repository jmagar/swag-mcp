"""Focused tests to boost coverage above 80%."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from swag_mcp.core.config import config
from swag_mcp.core.constants import (
    AUTH_METHOD_AUTHELIA,
    AUTH_METHOD_NONE,
    CONFIG_TYPES,
    VALID_NAME_PATTERN,
)
from swag_mcp.middleware.rate_limiting import (
    get_rate_limiting_middleware,
    get_sliding_window_rate_limiting_middleware,
)
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.utils.error_handlers import handle_os_error
from swag_mcp.utils.formatters import (
    build_template_filename,
    format_config_list,
    format_duration,
    format_health_check_result,
    get_possible_sample_filenames,
)
from swag_mcp.utils.validators import (
    detect_and_handle_encoding,
    normalize_unicode_text,
    validate_config_filename,
    validate_domain_format,
    validate_service_name,
    validate_upstream_port,
)


class TestValidators:
    """Test validation functions."""

    def test_validate_domain_format_valid(self):
        """Test valid domain formats."""
        valid_domains = [
            "example.com",
            "sub.example.com",
            "test-site.co.uk",
            "a.b.c.com",
            "123.example.com",
        ]
        for domain in valid_domains:
            assert validate_domain_format(domain) == domain.lower()

    def test_validate_domain_format_invalid(self):
        """Test invalid domain formats."""
        invalid_domains = [
            "",
            ".",
            ".com",
            # "example.",  # Gets normalized to "example" which is valid
            "example..com",
            "-example.com",
            "example-.com",
        ]
        for domain in invalid_domains:
            with pytest.raises(ValueError):
                validate_domain_format(domain)

    def test_validate_service_name_valid(self):
        """Test valid service names."""
        valid_names = [
            "app",
            "my-app",
            "my_app",
            "app123",
            "test-app-123",
        ]
        for name in valid_names:
            assert validate_service_name(name, allow_emoji=False) == name

    def test_validate_service_name_invalid(self):
        """Test invalid service names."""
        invalid_names = [
            "",
            "-app",
            "app-",
            "app name",
            "../app",
            # "con",  # Windows reserved names are not checked by validate_service_name
        ]
        for name in invalid_names:
            with pytest.raises(ValueError):
                validate_service_name(name, allow_emoji=False)

    def test_validate_upstream_port_valid(self):
        """Test valid port numbers."""
        valid_ports = [1, 80, 443, 8080, 65535]
        for port in valid_ports:
            assert validate_upstream_port(port) == port

    def test_validate_upstream_port_invalid(self):
        """Test invalid port numbers."""
        invalid_ports = [0, -1, 65536, 100000]
        for port in invalid_ports:
            with pytest.raises(ValueError):
                validate_upstream_port(port)

    def test_validate_config_filename(self):
        """Test config filename validation."""
        assert validate_config_filename("test.subdomain.conf") == "test.subdomain.conf"
        # Bare names now get auto-extended with .conf
        assert validate_config_filename("test") == "test.conf"

        with pytest.raises(ValueError):
            validate_config_filename("")

    def test_normalize_unicode_text(self):
        """Test Unicode text normalization."""
        assert normalize_unicode_text("café") == "café"
        assert normalize_unicode_text("\ufeffHello", remove_bom=True) == "Hello"
        assert normalize_unicode_text("") == ""
        # Disallowed characters should raise
        import pytest
        with pytest.raises(ValueError):
            normalize_unicode_text("\u202E")  # RLO (Right-to-Left Override)

    def test_detect_and_handle_encoding(self):
        """Test encoding detection."""
        assert detect_and_handle_encoding(b"Hello") == "Hello"
        assert detect_and_handle_encoding(b"") == ""
        # UTF encodings with BOMs
        assert detect_and_handle_encoding("Hello".encode("utf-16")) == "Hello"
        assert detect_and_handle_encoding("Hello".encode("utf-32")) == "Hello"
        # cp1252 example ("é")
        assert detect_and_handle_encoding("caf\xe9".encode("cp1252")) == "café"


class TestFormatters:
    """Test formatting functions."""

    def test_format_duration(self):
        """Test duration formatting."""
        assert "ms" in format_duration(500)
        assert "s" in format_duration(1500)

    def test_build_template_filename(self):
        """Test template filename building with SWAG-compliant types."""
        assert build_template_filename("swag-compliant-mcp-subdomain") == "swag-compliant-mcp-subdomain.conf.j2"
        assert build_template_filename("swag-compliant-mcp-subfolder") == "swag-compliant-mcp-subfolder.conf.j2"

        with pytest.raises(ValueError):
            build_template_filename("invalid")

        # Legacy template types should raise ValueError
        with pytest.raises(ValueError):
            build_template_filename("subdomain")

    def test_format_health_check_result(self):
        """Test health check result formatting."""
        result = {"accessible": True, "status_code": 200}
        message, status = format_health_check_result(result)
        assert "✅" in message
        assert "200" in message
        assert status == "successful"

    def test_get_possible_sample_filenames(self):
        """Test sample filename generation."""
        filenames = get_possible_sample_filenames("test")
        assert filenames == ["test.subdomain.conf.sample", "test.subfolder.conf.sample"]

    def test_format_config_list(self):
        """Test config list formatting."""
        result = format_config_list("all", 5)
        assert isinstance(result, str)
        assert "5" in result


class TestErrorHandlers:
    """Test error handling utilities."""

    def test_handle_os_error(self):
        """Test OS error handling."""
        import errno

        error = OSError(errno.ENOENT, "No such file", "test.conf")
        with pytest.raises(OSError):
            handle_os_error(error, "testing")

        permission_error = OSError(errno.EACCES, "Permission denied", "test.conf")
        with pytest.raises(OSError):
            handle_os_error(permission_error, "testing")

        disk_full = OSError(errno.ENOSPC, "No space left on device", "test.conf")
        with pytest.raises(OSError) as e1:
            handle_os_error(disk_full, "writing", "test.conf")
        assert e1.value.errno == errno.ENOSPC

        read_only = OSError(errno.EROFS, "Read-only file system", "test.conf")
        with pytest.raises(OSError) as e2:
            handle_os_error(read_only, "writing", "test.conf")
        assert e2.value.errno == errno.EROFS


class TestConstants:
    """Test constants are properly defined."""

    def test_config_types(self):
        """Test config types constant for SWAG-compliant types only."""
        assert "swag-compliant-mcp-subdomain" in CONFIG_TYPES
        assert "swag-compliant-mcp-subfolder" in CONFIG_TYPES
        # Legacy types should not be in CONFIG_TYPES
        assert "subdomain" not in CONFIG_TYPES
        assert "subfolder" not in CONFIG_TYPES

    def test_auth_methods(self):
        """Test auth methods constant."""
        assert AUTH_METHOD_AUTHELIA == "authelia"
        assert AUTH_METHOD_NONE == "none"

    def test_patterns(self):
        """Test regex patterns."""
        assert VALID_NAME_PATTERN is not None


class TestConfig:
    """Test configuration access."""

    def test_config_properties(self):
        """Test config has required properties."""
        assert hasattr(config, "proxy_confs_path")
        assert hasattr(config, "host")
        assert hasattr(config, "port")


class TestSwagManagerBasics:
    """Test basic SwagManager functionality."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories."""
        with (
            tempfile.TemporaryDirectory() as config_dir,
            tempfile.TemporaryDirectory() as template_dir,
        ):
            # Create basic template
            (Path(template_dir) / "subdomain.conf.j2").write_text("server_name {{ server_name }};")
            yield Path(config_dir), Path(template_dir)

    def test_init(self, temp_dirs):
        """Test service initialization."""
        config_dir, template_dir = temp_dirs
        service = SwagManagerService(config_dir, template_dir)
        assert service.config_path == config_dir
        assert service.template_path == template_dir

    @pytest.mark.asyncio
    async def test_get_file_lock(self, temp_dirs):
        """Test file locking mechanism."""
        config_dir, template_dir = temp_dirs
        service = SwagManagerService(config_dir, template_dir)

        test_file = config_dir / "test.conf"
        lock1 = await service._get_file_lock(test_file)
        lock2 = await service._get_file_lock(test_file)
        assert lock1 is lock2

    def test_transaction_begin(self, temp_dirs):
        """Test transaction creation."""
        config_dir, template_dir = temp_dirs
        service = SwagManagerService(config_dir, template_dir)

        tx = service.begin_transaction("test")
        assert hasattr(tx, "transaction_id")

    def test_ensure_config_directory(self, temp_dirs):
        """Test directory creation."""
        config_dir, template_dir = temp_dirs
        service = SwagManagerService(config_dir, template_dir)

        # Should not raise exception
        service._ensure_config_directory()
        assert config_dir.exists()

    def test_validate_template_variables(self, temp_dirs):
        """Test template variable validation."""
        config_dir, template_dir = temp_dirs
        service = SwagManagerService(config_dir, template_dir)

        vars_dict = {"service_name": "test", "server_name": "example.com"}
        result = service._validate_template_variables(vars_dict)
        assert isinstance(result, dict)

    def test_extract_upstream_value(self, temp_dirs):
        """Test upstream value extraction."""
        config_dir, template_dir = temp_dirs
        service = SwagManagerService(config_dir, template_dir)

        content = 'set $upstream_app "test-app";'
        result = service._extract_upstream_value(content, "upstream_app")
        assert result == "test-app"

    def test_extract_auth_method(self, temp_dirs):
        """Test auth method extraction."""
        config_dir, template_dir = temp_dirs
        service = SwagManagerService(config_dir, template_dir)

        content = "include /config/nginx/authelia-server.conf;"
        result = service._extract_auth_method(content)
        assert result == "authelia"

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_list_backups(self, temp_dirs):
        """Test backup listing."""
        config_dir, template_dir = temp_dirs
        service = SwagManagerService(config_dir, template_dir)

        result = await service.list_backups()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_cleanup_old_backups_zero(self, temp_dirs):
        """Test backup cleanup."""
        config_dir, template_dir = temp_dirs
        service = SwagManagerService(config_dir, template_dir)

        result = await service.cleanup_old_backups(0)
        assert isinstance(result, int)


class TestRateLimiting:
    """Test rate limiting middleware."""

    @patch("swag_mcp.middleware.rate_limiting.config")
    def test_get_rate_limiting_middleware_disabled(self, mock_config):
        """Test rate limiting when disabled."""
        mock_config.rate_limit_enabled = False

        middleware = get_rate_limiting_middleware()
        assert middleware is None

    @patch("swag_mcp.middleware.rate_limiting.config")
    def test_get_rate_limiting_middleware_enabled(self, mock_config):
        """Test rate limiting when enabled."""
        mock_config.rate_limit_enabled = True
        mock_config.rate_limit_rps = 10.0
        mock_config.rate_limit_burst = 20

        middleware = get_rate_limiting_middleware()
        assert middleware is not None

    @patch("swag_mcp.middleware.rate_limiting.config")
    def test_get_sliding_window_middleware_disabled(self, mock_config):
        """Test sliding window when disabled."""
        mock_config.rate_limit_enabled = False

        middleware = get_sliding_window_rate_limiting_middleware()
        assert middleware is None

    @patch("swag_mcp.middleware.rate_limiting.config")
    def test_get_sliding_window_middleware_enabled(self, mock_config):
        """Test sliding window when enabled."""
        mock_config.rate_limit_enabled = True
        mock_config.rate_limit_rps = 10.0

        middleware = get_sliding_window_rate_limiting_middleware()
        assert middleware is not None


class TestSwagManagerAdvanced:
    """Test more complex SwagManager scenarios."""

    @pytest.fixture
    def service_with_files(self):
        """Create service with test files."""
        with (
            tempfile.TemporaryDirectory() as config_dir,
            tempfile.TemporaryDirectory() as template_dir,
        ):
            config_path = Path(config_dir)
            template_path = Path(template_dir)

            # Create template
            (template_path / "subdomain.conf.j2").write_text(
                "server_name {{ server_name }}; "
                "proxy_pass {{ upstream_proto }}://{{ upstream_app }}:{{ upstream_port }};"
            )

            # Create test config file
            (config_path / "test.subdomain.conf").write_text(
                "server_name test.example.com; proxy_pass http://test-app:8080;"
            )

            service = SwagManagerService(config_path, template_path)
            yield service, config_path

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_read_config_success(self, service_with_files):
        """Test reading existing config."""
        service, _ = service_with_files

        content = await service.read_config("test.subdomain.conf")
        assert "test.example.com" in content

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_validate_template_exists_true(self, service_with_files):
        """Test template existence validation."""
        service, _ = service_with_files

        result = await service.validate_template_exists("subdomain")
        assert result is True

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_validate_template_exists_false(self, service_with_files):
        """Test template non-existence."""
        service, _ = service_with_files

        result = await service.validate_template_exists("subfolder")
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_all_templates(self, service_with_files):
        """Test validating all templates."""
        service, _ = service_with_files

        result = await service.validate_all_templates()
        assert isinstance(result, dict)
        assert "subdomain" in result
        assert result["subdomain"] is True
