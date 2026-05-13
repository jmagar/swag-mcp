"""Tests for plugin setup repair and managed config files."""

from pathlib import Path

from swag_mcp.setup import repair_setup


def test_repair_creates_config_and_env_with_permissions(tmp_path: Path) -> None:
    """Setup repair creates durable config files under the SWAG MCP home."""
    result = repair_setup(
        home_dir=tmp_path,
        option_env={
            "SWAG_MCP_URL": "https://swag.example.com/mcp",
            "SWAG_MCP_TOKEN": "fresh-token",
            "SWAG_MCP_PROXY_CONFS_URI": "swag:/proxy-confs",
        },
    )

    config_path = tmp_path / "config.toml"
    env_path = tmp_path / ".env"

    assert result.config_path == config_path
    assert result.env_path == env_path
    assert config_path.exists()
    assert env_path.exists()
    assert env_path.stat().st_mode & 0o777 == 0o600
    assert "SWAG_MCP_URL=https://swag.example.com/mcp" in env_path.read_text()
    assert "SWAG_MCP_TOKEN=fresh-token" in env_path.read_text()
    assert "SWAG_MCP_PROXY_CONFS_URI=swag:/proxy-confs" in env_path.read_text()


def test_repair_preserves_existing_secret_when_plugin_option_missing(tmp_path: Path) -> None:
    """Missing plugin options should not blank existing local secrets."""
    env_path = tmp_path / ".env"
    env_path.write_text(
        "SWAG_MCP_TOKEN=existing-token\nFASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET=existing-secret\n"
    )

    repair_setup(
        home_dir=tmp_path,
        option_env={
            "SWAG_MCP_URL": "https://swag.example.com/mcp",
        },
    )

    env_text = env_path.read_text()
    assert "SWAG_MCP_TOKEN=existing-token" in env_text
    assert "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET=existing-secret" in env_text
    assert "SWAG_MCP_URL=https://swag.example.com/mcp" in env_text


def test_repair_replaces_token_when_plugin_option_provided(tmp_path: Path) -> None:
    """Injected plugin token should replace an existing token."""
    env_path = tmp_path / ".env"
    env_path.write_text("SWAG_MCP_TOKEN=existing-token\n")

    repair_setup(home_dir=tmp_path, option_env={"SWAG_MCP_TOKEN": "new-token"})

    assert "SWAG_MCP_TOKEN=new-token" in env_path.read_text()


def test_repair_rejects_symlink_env(tmp_path: Path) -> None:
    """Setup repair must not write through symlinked config targets."""
    target = tmp_path / "target.env"
    target.write_text("SWAG_MCP_TOKEN=target\n")
    (tmp_path / ".env").symlink_to(target)

    try:
        repair_setup(home_dir=tmp_path, option_env={"SWAG_MCP_TOKEN": "new-token"})
    except RuntimeError as exc:
        assert "Refusing to write symlink" in str(exc)
    else:
        raise AssertionError("repair_setup should reject symlinked .env")

    assert target.read_text() == "SWAG_MCP_TOKEN=target\n"
