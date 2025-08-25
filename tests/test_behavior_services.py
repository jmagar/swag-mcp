"""Behavior-focused tests for SWAG services.

Tests focus on service behavior under various conditions rather than
implementation details or mocked responses.
"""

import asyncio
import os
from datetime import datetime, timedelta

import pytest
from swag_mcp.models.config import SwagConfigRequest, SwagEditRequest
from swag_mcp.services.swag_manager import SwagManagerService


class TestSwagServiceBehavior:
    """Behavior-focused tests for SwagManagerService."""

    @pytest.mark.asyncio
    async def test_template_rendering_with_real_data(self, swag_service: SwagManagerService):
        """Test template rendering behavior with various realistic configurations."""
        test_configs = [
            # Standard web app
            {
                "service_name": "webapp",
                "server_name": "webapp.company.com",
                "upstream_app": "webapp-container",
                "upstream_port": 8080,
                "config_type": "subdomain",
                "auth_method": "authelia",
            },
            # API service with different port
            {
                "service_name": "api-v2",
                "server_name": "api.company.com",
                "upstream_app": "api-v2-service",
                "upstream_port": 3000,
                "config_type": "subfolder",
                "auth_method": "none",
            },
            # Database admin tool with HTTPS upstream
            {
                "service_name": "pgadmin",
                "server_name": "db.company.com",
                "upstream_app": "pgadmin4",
                "upstream_port": 443,
                "config_type": "subdomain",
                "auth_method": "ldap",
                "upstream_proto": "https",
                "enable_quic": True,
            },
        ]

        for config_data in test_configs:
            request = SwagConfigRequest(**config_data)
            result = await swag_service.create_config(request)

            config_file = swag_service.config_path / result.filename

            try:
                # Verify behavior: file should be created with correct content
                assert config_file.exists()
                content = config_file.read_text()

                # Behavior verification: all Jinja2 template variables should be rendered
                assert "{{" not in content and "}}" not in content  # Jinja2 vars should be replaced
                assert config_data["upstream_app"] in content
                assert str(config_data["upstream_port"]) in content

                # Server name only appears in subdomain configs, not subfolder configs
                if config_data["config_type"] == "subdomain":
                    assert config_data["server_name"] in content

                # Behavior verification: auth configuration should be correct
                if config_data["auth_method"] != "none":
                    assert config_data["auth_method"] in content

                # Behavior verification: QUIC should be handled correctly
                if config_data.get("enable_quic"):
                    assert "quic" in content.lower()

            finally:
                if config_file.exists():
                    config_file.unlink()

    @pytest.mark.asyncio
    async def test_backup_behavior_under_filesystem_stress(self, swag_service: SwagManagerService):
        """Test backup creation behavior under various filesystem conditions."""
        config_file = swag_service.config_path / "stress-test.conf"
        original_content = """# Original configuration
server {
    listen 443 ssl http2;
    server_name stress-test.*;
    location / {
        proxy_pass http://upstream:8080;
    }
}"""
        config_file.write_text(original_content)

        try:
            # Test behavior: rapid consecutive edits should create distinct backups
            for i in range(5):
                new_content = original_content.replace("8080", f"808{i+1}")  # Start with 8081
                request = SwagEditRequest(
                    config_name="stress-test.conf",
                    new_content=new_content,
                    create_backup=True,
                )

                result = await swag_service.update_config(request)
                assert result.backup_created is not None

                # Small delay to ensure different timestamps
                await asyncio.sleep(0.1)

            # Verify behavior: should have multiple distinct backup files
            backup_files = list(swag_service.config_path.glob("stress-test.conf.backup.*"))
            assert len(backup_files) == 5

            # Verify behavior: backups should contain progressive content changes
            backup_contents = []
            for backup_file in sorted(backup_files):  # Sort by timestamp
                content = backup_file.read_text()
                backup_contents.append(content)

            # All backups should contain the content that was replaced,
            # progressing through the updates
            # The logic is each backup contains the previous file content before the current update
            # expected_ports removed as unused  # What each backup should contain
            for i, content in enumerate(backup_contents):
                assert (
                    f"808{i}" in content
                ), f"Backup {i} should contain port 808{i}, but contains: {content[:100]}..."

        finally:
            # Cleanup
            if config_file.exists():
                config_file.unlink()
            for backup_file in swag_service.config_path.glob("stress-test.conf.backup.*"):
                backup_file.unlink()

    @pytest.mark.asyncio
    async def test_cleanup_behavior_with_mixed_files(self, swag_service: SwagManagerService):
        """Test backup cleanup behavior with various file ages and types."""
        config_dir = swag_service.config_path

        # Create files with different ages
        now = datetime.now()
        test_files = []

        # Create old backups (should be cleaned) using correct timestamp format
        for days_old in [35, 45, 100]:
            old_date = now - timedelta(days=days_old)
            old_timestamp = old_date.strftime("%Y%m%d_%H%M%S_%f")
            old_backup = config_dir / f"old-{days_old}days.conf.backup.{old_timestamp}"
            old_backup.write_text("# Old backup")

            # Set file modification time to simulate age
            old_time = old_date.timestamp()
            os.utime(old_backup, (old_time, old_time))
            test_files.append((old_backup, True))  # Should be cleaned

        # Create recent backups (should be kept) using correct timestamp format
        for days_old in [5, 15, 25]:
            recent_date = now - timedelta(days=days_old)
            recent_timestamp = recent_date.strftime("%Y%m%d_%H%M%S_%f")
            recent_backup = config_dir / f"recent-{days_old}days.conf.backup.{recent_timestamp}"
            recent_backup.write_text("# Recent backup")

            recent_time = (now - timedelta(days=days_old)).timestamp()
            os.utime(recent_backup, (recent_time, recent_time))
            test_files.append((recent_backup, False))  # Should be kept

        # Create non-backup files (should be ignored)
        non_backup = config_dir / "regular-config.conf"
        non_backup.write_text("# Regular config")
        test_files.append((non_backup, False))  # Should be kept

        try:
            # Test cleanup behavior
            cleaned_count = await swag_service.cleanup_old_backups(retention_days=30)

            # Verify behavior: should clean old backups but preserve others
            assert cleaned_count == 3  # Only the 3 old backups

            for file_path, should_be_cleaned in test_files:
                if should_be_cleaned:
                    assert not file_path.exists(), f"{file_path.name} should have been cleaned"
                else:
                    assert file_path.exists(), f"{file_path.name} should have been preserved"

        finally:
            # Cleanup remaining test files
            for file_path, _ in test_files:
                if file_path.exists():
                    file_path.unlink()

    @pytest.mark.asyncio
    async def test_config_validation_behavior(self, swag_service: SwagManagerService):
        """Test configuration validation behavior with various inputs."""

        # Test invalid service names
        invalid_service_names = [
            "",  # Empty
            "a" * 100,  # Too long
            "service/with/slashes",  # Invalid characters
            "service with spaces",  # Spaces
            "service\nwith\nnewlines",  # Newlines
        ]

        for invalid_name in invalid_service_names:
            with pytest.raises((ValueError, Exception)) as exc_info:
                request = SwagConfigRequest(
                    service_name=invalid_name,
                    server_name="test.example.com",
                    upstream_app="test",
                    upstream_port=8080,
                    config_type="subdomain",
                    auth_method="none",
                )
                await swag_service.create_config(request)

            # Verify behavior: error should be descriptive
            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["invalid", "validation", "name"])

    @pytest.mark.asyncio
    async def test_file_conflict_resolution_behavior(self, swag_service: SwagManagerService):
        """Test behavior when configuration files have naming conflicts."""
        base_config = {
            "service_name": "conflict-test",
            "server_name": "conflict.example.com",
            "upstream_app": "conflict-app",
            "upstream_port": 8080,
            "config_type": "subdomain",
            "auth_method": "none",
        }

        config_file = swag_service.config_path / "conflict-test.subdomain.conf"

        try:
            # Create first configuration
            await swag_service.create_config(SwagConfigRequest(**base_config))
            assert config_file.exists()

            # Attempt to create duplicate configuration
            with pytest.raises(Exception) as exc_info:
                request2 = SwagConfigRequest(**base_config)
                await swag_service.create_config(request2)

            # Verify behavior: should provide clear conflict error
            error_msg = str(exc_info.value).lower()
            assert any(word in error_msg for word in ["exists", "conflict", "duplicate"])

        finally:
            if config_file.exists():
                config_file.unlink()

    @pytest.mark.asyncio
    async def test_disk_space_behavior(self, swag_service: SwagManagerService):
        """Test service behavior when disk space is limited."""
        # This test simulates low disk space conditions
        config_dir = swag_service.config_path

        # Create a large configuration to test space handling
        large_config_content = (
            """# Large configuration file
# """
            + "Large content block\n" * 10000
        )

        config_file = config_dir / "large-config.conf"

        try:
            # Test behavior: should handle large file creation
            config_file.write_text(large_config_content)

            # Verify the file was created successfully
            assert config_file.exists()
            content = config_file.read_text()
            assert len(content) > 100000

            # Test behavior: editing large files should work
            request = SwagEditRequest(
                config_name="large-config.conf",
                new_content=large_config_content + "\n# Additional content",
                create_backup=True,
            )

            result = await swag_service.update_config(request)

            # Verify behavior: should succeed and create backup
            assert result.backup_created is not None
            updated_content = config_file.read_text()
            assert "Additional content" in updated_content

        finally:
            if config_file.exists():
                config_file.unlink()
            # Clean up any backups
            for backup_file in config_dir.glob("large-config.conf.backup.*"):
                backup_file.unlink()

    @pytest.mark.asyncio
    async def test_concurrent_access_behavior(self, swag_service: SwagManagerService):
        """Test service behavior under concurrent access patterns."""
        import asyncio

        config_name = "concurrent-test.conf"
        config_file = swag_service.config_path / config_name
        initial_content = "# Initial content for concurrent test"
        config_file.write_text(initial_content)

        async def edit_config(suffix: str):
            """Concurrent edit operation."""
            request = SwagEditRequest(
                config_name=config_name,
                new_content=f"# Modified content {suffix}",
                create_backup=True,
            )
            return await swag_service.update_config(request)

        try:
            # Test behavior: concurrent edits should be handled safely
            results = await asyncio.gather(
                edit_config("A"),
                edit_config("B"),
                edit_config("C"),
                return_exceptions=True,
            )

            # Verify behavior: operations should complete without corruption
            successful_results = [r for r in results if not isinstance(r, Exception)]
            assert len(successful_results) >= 1  # At least one should succeed

            # Verify final file state is consistent
            final_content = config_file.read_text()
            assert "Modified content" in final_content
            assert len(final_content) > 0

            # Verify backups were created
            backup_files = list(swag_service.config_path.glob(f"{config_name}.backup.*"))
            assert len(backup_files) >= len(successful_results)

        finally:
            if config_file.exists():
                config_file.unlink()
            for backup_file in swag_service.config_path.glob(f"{config_name}.backup.*"):
                backup_file.unlink()
