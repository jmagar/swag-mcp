"""Deployment security regression tests."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_compose_binds_mcp_port_to_loopback_by_default():
    """Default Compose publishing must not expose MCP on every interface."""
    compose = (REPO_ROOT / "docker-compose.yaml").read_text()

    assert '"${SWAG_MCP_BIND_ADDRESS:-127.0.0.1}:${SWAG_MCP_PORT:-49152}:8000"' in compose
    assert '"${SWAG_MCP_PORT:-8000}:8000"' not in compose
