"""Test MCP remote upstream support."""

import pytest
from pathlib import Path
from swag_mcp.models.config import SwagConfigRequest
from swag_mcp.services.swag_manager import SwagManagerService


class TestMCPRemoteUpstream:
    """Test MCP remote upstream server support."""

    @pytest.fixture
    async def swag_manager(self, tmp_path):
        """Create a SWAG manager instance with temporary directories."""
        config_path = tmp_path / "proxy-confs"
        config_path.mkdir(parents=True, exist_ok=True)

        template_path = Path(__file__).parent.parent / "templates"

        async with SwagManagerService(
            config_path=config_path, template_path=template_path
        ) as manager:
            yield manager

    @pytest.mark.asyncio
    async def test_mcp_upstream_defaults_to_main_upstream(self, swag_manager):
        """Test that MCP upstream defaults to main upstream (backward compatibility)."""
        request = SwagConfigRequest(
            action="create",
            config_name="test.subdomain.conf",
            server_name="test.example.com",
            upstream_app="testapp",
            upstream_port=8080,
            upstream_proto="http",
            mcp_enabled=True,
        )

        # Model validator should set defaults
        assert request.mcp_upstream_app == "testapp"
        assert request.mcp_upstream_port == 8080
        assert request.mcp_upstream_proto == "http"

        # Create config and verify it contains the correct upstream variables
        result = await swag_manager.create_config(request)
        assert "test.subdomain.conf" == result.filename

        # Verify main upstream variables
        assert 'set $upstream_app "testapp"' in result.content
        assert 'set $upstream_port "8080"' in result.content
        assert 'set $upstream_proto "http"' in result.content

        # Verify MCP upstream variables (should match main)
        assert 'set $mcp_upstream_app "testapp"' in result.content
        assert 'set $mcp_upstream_port "8080"' in result.content
        assert 'set $mcp_upstream_proto "http"' in result.content

        # Verify MCP location uses MCP upstream
        assert (
            "proxy_pass $mcp_upstream_proto://$mcp_upstream_app:$mcp_upstream_port"
            in result.content
        )

    @pytest.mark.asyncio
    async def test_mcp_upstream_separate_from_main_upstream(self, swag_manager):
        """Test MCP upstream on different server than main service."""
        request = SwagConfigRequest(
            action="create",
            config_name="jellyfin.subdomain.conf",
            server_name="jellyfin.example.com",
            upstream_app="jellyfin",
            upstream_port=8096,
            upstream_proto="http",
            mcp_enabled=True,
            # MCP runs on different server
            mcp_upstream_app="ai-gpu-server",
            mcp_upstream_port=8080,
            mcp_upstream_proto="http",
        )

        # Verify fields are set correctly
        assert request.upstream_app == "jellyfin"
        assert request.upstream_port == 8096
        assert request.mcp_upstream_app == "ai-gpu-server"
        assert request.mcp_upstream_port == 8080

        # Create config and verify it contains separate upstream variables
        result = await swag_manager.create_config(request)
        assert "jellyfin.subdomain.conf" == result.filename

        # Verify main service uses jellyfin upstream
        assert 'set $upstream_app "jellyfin"' in result.content
        assert 'set $upstream_port "8096"' in result.content

        # Verify MCP service uses ai-gpu-server upstream
        assert 'set $mcp_upstream_app "ai-gpu-server"' in result.content
        assert 'set $mcp_upstream_port "8080"' in result.content

        # Verify MCP location uses MCP upstream (remote server)
        assert (
            "proxy_pass $mcp_upstream_proto://$mcp_upstream_app:$mcp_upstream_port"
            in result.content
        )

        # Verify main location uses main upstream
        # The default location / should use $upstream_app:$upstream_port
        assert "location / {" in result.content

    @pytest.mark.asyncio
    async def test_subfolder_template_with_remote_mcp(self, swag_manager):
        """Test subfolder template with remote MCP server."""
        request = SwagConfigRequest(
            action="create",
            config_name="plex.subfolder.conf",
            server_name="example.com",
            upstream_app="plex",
            upstream_port=32400,
            upstream_proto="https",
            mcp_enabled=True,
            mcp_upstream_app="transcoder",
            mcp_upstream_port=9000,
            mcp_upstream_proto="http",
        )

        result = await swag_manager.create_config(request)
        assert "plex.subfolder.conf" == result.filename

        # Verify both upstreams are configured
        assert 'set $upstream_app "plex"' in result.content
        assert 'set $upstream_port "32400"' in result.content
        assert 'set $mcp_upstream_app "transcoder"' in result.content
        assert 'set $mcp_upstream_port "9000"' in result.content

        # Verify MCP location uses remote transcoder
        assert "location ^~ /plex/mcp {" in result.content or "location /mcp {" in result.content

    @pytest.mark.asyncio
    async def test_mcp_upstream_validation(self):
        """Test that MCP upstream fields are validated."""
        from pydantic import ValidationError

        # Valid upstream app with special characters
        request = SwagConfigRequest(
            action="create",
            config_name="test.subdomain.conf",
            server_name="test.example.com",
            upstream_app="test-app",
            upstream_port=8080,
            mcp_upstream_app="ai_server-01.local",  # Valid
            mcp_upstream_port=8081,
        )
        assert request.mcp_upstream_app == "ai_server-01.local"

        # Invalid upstream app should raise error
        with pytest.raises(ValidationError, match="MCP upstream app name.*contains invalid characters"):
            SwagConfigRequest(
                action="create",
                config_name="test.subdomain.conf",
                server_name="test.example.com",
                upstream_app="test",
                upstream_port=8080,
                mcp_upstream_app="invalid/app",  # Invalid - contains /
                mcp_upstream_port=8080,
            )

    @pytest.mark.asyncio
    async def test_edit_mcp_upstream_fields_only(self):
        """Test that we can edit only MCP upstream fields (P1 bug fix)."""
        from swag_mcp.models.config import SwagEditRequest

        # This should NOT raise an error - editing only MCP upstream fields is valid
        request = SwagEditRequest(
            action="edit",
            config_name="test.subdomain.conf",
            mcp_upstream_app="new-mcp-server",
            mcp_upstream_port=9000,
        )

        assert request.mcp_upstream_app == "new-mcp-server"
        assert request.mcp_upstream_port == 9000

        # Test editing only one MCP field
        request2 = SwagEditRequest(
            action="edit",
            config_name="test.subdomain.conf",
            mcp_upstream_app="another-server",
        )

        assert request2.mcp_upstream_app == "another-server"
