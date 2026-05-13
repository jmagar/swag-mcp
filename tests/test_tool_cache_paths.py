"""Regression tests for tool cache and plugin data paths."""

import json
import os
import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_pytest_tool_caches_route_to_cache() -> None:
    """Pytest-integrated tools should not write their state to the repo root."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    pytest_options = pyproject["tool"]["pytest"]["ini_options"]
    addopts = pytest_options.get("addopts", [])

    assert pytest_options["cache_dir"] == ".cache/pytest"
    assert "--benchmark-storage=.cache/benchmarks" in addopts

    conftest = (REPO_ROOT / "tests" / "conftest.py").read_text()
    assert 'HYPOTHESIS_STORAGE_DIRECTORY", ".cache/hypothesis"' in conftest


def test_mcp_config_uses_native_http_transport() -> None:
    """Plugin MCP config should use the server's native HTTP transport."""
    assert not (REPO_ROOT / ".mcp.json").exists()
    assert not (REPO_ROOT / ".app.json").exists()

    plugin_mcp_path = REPO_ROOT / "plugins" / "swag-mcp" / ".mcp.json"
    mcp_config = json.loads(plugin_mcp_path.read_text())
    servers = mcp_config["mcpServers"]
    swag_server = servers["swag-mcp"]

    assert list(servers) == ["swag-mcp"]
    assert swag_server == {
        "type": "http",
        "url": "${user_config.swag_mcp_url}",
        "headers": {
            "Authorization": "Bearer ${user_config.swag_mcp_token}",
        },
    }


def test_plugin_manifests_point_at_plugin_assets() -> None:
    """Plugin assets should live outside project-root MCP discovery paths."""
    claude_config = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    codex_config = json.loads((REPO_ROOT / ".codex-plugin" / "plugin.json").read_text())

    assert claude_config["mcpServers"] == "./plugins/swag-mcp/.mcp.json"
    assert claude_config["hooks"] == "./plugins/swag-mcp/hooks/hooks.json"
    assert codex_config["skills"] == "./plugins/swag-mcp/skills/"
    assert codex_config["mcpServers"] == "./plugins/swag-mcp/.mcp.json"
    assert codex_config["apps"] == "./plugins/swag-mcp/.app.json"


def test_claude_plugin_declares_http_user_config() -> None:
    """Claude plugin config should provide fields used by .mcp.json."""
    plugin_config = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    user_config = plugin_config["userConfig"]

    assert "swag_mcp_proxy_confs_uri" in user_config
    assert "swag_mcp_host" in user_config
    assert "swag_mcp_port" in user_config
    assert "swag_mcp_token" in user_config
    assert "swag_mcp_url" in user_config
    assert "swag_mcp_default_web_auth_method" in user_config
    assert user_config["swag_mcp_token"]["sensitive"] is True


def test_default_web_auth_method_env_name(monkeypatch) -> None:
    """Generated web endpoint auth should use the explicit env var name."""
    from swag_mcp.core.config import SwagConfig

    monkeypatch.setenv("SWAG_MCP_DEFAULT_WEB_AUTH_METHOD", "authentik")
    monkeypatch.delenv("SWAG_MCP_DEFAULT_AUTH_METHOD", raising=False)

    config = SwagConfig(_env_file=None)

    assert config.default_auth_method == "authentik"


def test_sync_uv_uses_cache_when_plugin_data_is_placeholder(tmp_path: Path) -> None:
    """The install hook should treat literal placeholders like missing env vars."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    output_path = tmp_path / "uv-env.txt"
    fake_uv = fake_bin / "uv"
    fake_uv.write_text(
        '#!/usr/bin/env bash\nprintf "%s\\n" "$UV_PROJECT_ENVIRONMENT" "$*" > "$UV_ENV_OUTPUT"\n'
    )
    fake_uv.chmod(0o755)

    env = {
        **os.environ,
        "CLAUDE_PLUGIN_ROOT": str(REPO_ROOT),
        "CLAUDE_PLUGIN_DATA": "${CLAUDE_PLUGIN_DATA}",
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "UV_ENV_OUTPUT": str(output_path),
    }

    subprocess.run(
        ["bash", str(REPO_ROOT / "bin" / "sync-uv.sh")],
        check=True,
        cwd=REPO_ROOT,
        env=env,
    )

    lines = output_path.read_text().splitlines()
    assert lines[0] == str(REPO_ROOT / ".cache" / "claude-plugin-data" / ".venv")
    assert lines[1] == f"sync --project {REPO_ROOT}"
