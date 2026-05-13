"""Setup repair utilities for plugin and local deployments."""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

MANAGED_ENV_KEYS = [
    "SWAG_MCP_PROXY_CONFS_PATH",
    "SWAG_MCP_PROXY_CONFS_URI",
    "SWAG_MCP_SWAG_LOG_BASE_PATH",
    "SWAG_MCP_LOG_DIRECTORY",
    "SWAG_MCP_TOKEN",
    "SWAG_MCP_URL",
    "SWAG_MCP_NO_AUTH",
    "FASTMCP_SERVER_AUTH",
    "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_ID",
    "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET",
    "FASTMCP_SERVER_AUTH_GOOGLE_BASE_URL",
    "FASTMCP_SERVER_AUTH_RESOURCE_BASE_URL",
    "FASTMCP_SERVER_AUTH_GOOGLE_REQUIRED_SCOPES",
    "FASTMCP_SERVER_AUTH_GOOGLE_REDIRECT_PATH",
    "SWAG_MCP_HOST",
    "SWAG_MCP_BIND_ADDRESS",
    "SWAG_MCP_PORT",
    "SWAG_MCP_DEFAULT_WEB_AUTH_METHOD",
    "SWAG_MCP_DEFAULT_QUIC_ENABLED",
    "SWAG_MCP_OAUTH_UPSTREAM",
    "SWAG_MCP_AUTH_SERVER_URL",
    "SWAG_MCP_BACKUP_RETENTION_DAYS",
    "SWAG_MCP_LOG_LEVEL",
    "SWAG_MCP_LOG_FILE_ENABLED",
    "SWAG_MCP_REQUIRE_WRITABLE_LOG_DIRECTORY",
    "SWAG_MCP_LOG_FILE_MAX_BYTES",
    "SWAG_MCP_LOG_FILE_BACKUP_COUNT",
    "SWAG_MCP_ENABLE_STRUCTURED_LOGGING",
    "SWAG_MCP_LOG_PAYLOADS",
    "SWAG_MCP_LOG_PAYLOAD_MAX_LENGTH",
    "SWAG_MCP_SLOW_OPERATION_THRESHOLD_MS",
    "SWAG_MCP_ENABLE_RETRY_MIDDLEWARE",
    "SWAG_MCP_MAX_RETRIES",
    "SWAG_MCP_HEALTH_CHECK_INSECURE",
    "SWAG_MCP_RATE_LIMIT_ENABLED",
    "SWAG_MCP_RATE_LIMIT_RPS",
    "SWAG_MCP_RATE_LIMIT_BURST",
    "SWAG_MCP_TEMPLATE_PATH",
]

SECRET_KEYS = {
    "SWAG_MCP_TOKEN",
    "FASTMCP_SERVER_AUTH_GOOGLE_CLIENT_SECRET",
}

ASSIGNMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


@dataclass(frozen=True)
class RepairResult:
    """Paths repaired by setup repair."""

    home_dir: Path
    config_path: Path
    env_path: Path


def default_home_dir() -> Path:
    """Return the SWAG MCP home directory."""
    configured = os.getenv("SWAG_MCP_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".swag-mcp"


def repair_setup(
    *,
    home_dir: Path | None = None,
    option_env: dict[str, str] | None = None,
) -> RepairResult:
    """Create or repair durable SWAG MCP config files.

    Existing values are preserved unless a non-empty option value is supplied.
    Writes reject symlinked targets and use an atomic replace for `.env`.
    """
    resolved_home = (home_dir or default_home_dir()).expanduser()
    resolved_home.mkdir(parents=True, exist_ok=True)
    if resolved_home.is_symlink():
        raise RuntimeError(f"Refusing to write symlinked home directory: {resolved_home}")

    config_path = resolved_home / "config.toml"
    env_path = resolved_home / ".env"

    _ensure_config(config_path)
    _repair_env(env_path, option_env or _collect_process_env())

    return RepairResult(home_dir=resolved_home, config_path=config_path, env_path=env_path)


def _ensure_config(config_path: Path) -> None:
    """Create config.toml from bundled defaults if missing."""
    _reject_symlink(config_path)
    if config_path.exists():
        return

    template_path = Path(__file__).resolve().parents[1] / "config.example.toml"
    content = template_path.read_text()
    _atomic_write(config_path, content, mode=0o600)


def _repair_env(env_path: Path, option_env: dict[str, str]) -> None:
    """Merge managed env keys into env_path while preserving user values."""
    _reject_symlink(env_path)
    existing_text = env_path.read_text() if env_path.exists() else ""
    existing_values = _parse_env_values(existing_text)
    defaults = _parse_env_values((Path(__file__).resolve().parents[1] / ".env.example").read_text())

    merged = dict(existing_values)
    if (
        "SWAG_MCP_DEFAULT_AUTH_METHOD" in merged
        and "SWAG_MCP_DEFAULT_WEB_AUTH_METHOD" not in merged
    ):
        merged["SWAG_MCP_DEFAULT_WEB_AUTH_METHOD"] = merged["SWAG_MCP_DEFAULT_AUTH_METHOD"]

    normalized_options = _normalize_options(option_env)
    for key in MANAGED_ENV_KEYS:
        option_value = normalized_options.get(key)
        if option_value:
            merged[key] = option_value
            continue

        if key in SECRET_KEYS and merged.get(key):
            continue

        if key not in merged:
            merged[key] = defaults.get(key, "")

    rendered = _render_env(existing_text, merged, defaults)
    _atomic_write(env_path, rendered, mode=0o600)


def _normalize_options(option_env: dict[str, str]) -> dict[str, str]:
    """Normalize plugin option names to real runtime env var names."""
    normalized: dict[str, str] = {}
    for raw_key, value in option_env.items():
        if value is None:
            continue
        key = raw_key.removeprefix("CLAUDE_PLUGIN_OPTION_")
        if key == "SWAG_MCP_DEFAULT_AUTH_METHOD":
            key = "SWAG_MCP_DEFAULT_WEB_AUTH_METHOD"
        normalized[key] = value
    return normalized


def _collect_process_env() -> dict[str, str]:
    """Collect managed values from process env and Claude plugin option env."""
    collected: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in MANAGED_ENV_KEYS or key.startswith("CLAUDE_PLUGIN_OPTION_"):
            collected[key] = value
    return collected


def _parse_env_values(text: str) -> dict[str, str]:
    """Parse simple KEY=value lines from an env file."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = ASSIGNMENT_RE.match(line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def _render_env(existing_text: str, values: dict[str, str], defaults: dict[str, str]) -> str:
    """Render env content preserving existing comments and key order where possible."""
    output: list[str] = []
    seen: set[str] = set()

    for line in existing_text.splitlines():
        match = ASSIGNMENT_RE.match(line)
        if not match:
            output.append(line)
            continue

        key = match.group(1)
        if key == "SWAG_MCP_DEFAULT_AUTH_METHOD":
            continue
        if key in seen:
            continue
        if key in MANAGED_ENV_KEYS:
            output.append(f"{key}={values.get(key, '')}")
            seen.add(key)
        else:
            output.append(line)
            seen.add(key)

    for key in MANAGED_ENV_KEYS:
        if key in seen:
            continue
        default_value = defaults.get(key, "")
        output.append(f"{key}={values.get(key, default_value)}")
        seen.add(key)

    return "\n".join(output).rstrip() + "\n"


def _reject_symlink(path: Path) -> None:
    """Reject symlinked write targets."""
    if path.is_symlink():
        raise RuntimeError(f"Refusing to write symlink: {path}")


def _atomic_write(path: Path, content: str, *, mode: int) -> None:
    """Atomically write content with locked-down permissions."""
    temp_path = path.with_name(f".{path.name}.tmp")
    _reject_symlink(temp_path)
    temp_path.write_text(content)
    temp_path.chmod(mode)
    temp_path.replace(path)
    path.chmod(mode)
    current_mode = stat.S_IMODE(path.stat().st_mode)
    if current_mode != mode:
        raise RuntimeError(f"Failed to set {path} permissions to {oct(mode)}")
