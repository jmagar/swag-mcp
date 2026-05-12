"""Focused regression tests for filesystem and MCP service review findings."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from swag_mcp.core.config import SwagConfig
from swag_mcp.services.filesystem import LocalFilesystem
from swag_mcp.services.ssh_filesystem import SSHFilesystem
from swag_mcp.services.swag_manager import SwagManagerService


class RemoteValidationLocalFilesystem(LocalFilesystem):
    """Local test backend that advertises remote nginx validation semantics."""

    def requires_remote_nginx_validation(self) -> bool:
        """Report that local nginx validation should be skipped."""
        return True


class FailingTailConnection:
    """SSH connection stub whose command execution path is unavailable."""

    async def run(self, command: str, check: bool) -> object:
        """Capture command execution attempts and force SFTP fallback."""
        raise OSError("remote shell unavailable")


class CapturingTailConnection:
    """SSH connection stub that captures the command used for tail."""

    def __init__(self) -> None:
        """Initialize capture state."""
        self.command: str | None = None

    async def run(self, command: str, check: bool) -> SimpleNamespace:
        """Capture the command and return a successful tail result."""
        self.command = command
        return SimpleNamespace(stdout="tail output\n")


class BoundedReadFile:
    """Async file object that records bounded fallback reads."""

    def __init__(self, content: bytes) -> None:
        """Initialize file content and read accounting."""
        self.content = content
        self.offset = 0
        self.max_read_length = 0

    async def __aenter__(self) -> "BoundedReadFile":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Exit async context manager."""
        return None

    def seek(self, offset: int) -> None:
        """Move the current read offset."""
        self.offset = offset

    async def read(self, length: int = -1) -> bytes:
        """Read at most the requested number of bytes."""
        self.max_read_length = max(self.max_read_length, length)
        if length < 0:
            return self.content[self.offset :]
        return self.content[self.offset : self.offset + length]


class BoundedTailSFTP:
    """SFTP stub used to verify fallback tail reads are bounded."""

    def __init__(self, content: bytes) -> None:
        """Initialize with remote file content."""
        self.content = content
        self.file = BoundedReadFile(content)

    async def stat(self, path: str) -> SimpleNamespace:
        """Return remote file metadata."""
        return SimpleNamespace(size=len(self.content))

    def open(self, path: str, mode: str) -> BoundedReadFile:
        """Open the remote file for bounded reads."""
        return self.file


@pytest.fixture
def temp_paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create isolated config, template, and log paths."""
    config_path = tmp_path / "proxy-confs"
    template_path = tmp_path / "templates"
    log_path = tmp_path / "logs"
    config_path.mkdir()
    template_path.mkdir()
    log_path.mkdir()
    return config_path, template_path, log_path


async def test_transaction_attaches_structured_rollback_errors(temp_paths):
    """Original exceptions expose rollback failures without changing exception type."""
    config_path, template_path, _ = temp_paths
    service = SwagManagerService(config_path=config_path, template_path=template_path)
    created_file = config_path / "created.conf"

    with (
        patch.object(service.file_ops.fs, "unlink", AsyncMock(side_effect=PermissionError("nope"))),
        pytest.raises(ValueError) as exc_info,
    ):
        async with service.begin_transaction("rollback-visibility") as transaction:
            await transaction.track_file_creation(created_file)
            created_file.write_text("temporary")
            raise ValueError("primary failure")

    rollback_errors = getattr(exc_info.value, "rollback_errors", None)
    assert rollback_errors is not None
    assert len(rollback_errors) == 1
    assert rollback_errors[0].operation == "remove_created"
    assert rollback_errors[0].path == created_file
    assert "PermissionError" in rollback_errors[0].error_type


async def test_mcp_location_uses_filesystem_validation_capability(temp_paths):
    """MCP writes skip local nginx validation based on backend capability, not SSH type."""
    config_path, template_path, _ = temp_paths
    config_file = config_path / "remote.subdomain.conf"
    config_file.write_text(
        """
server {
    listen 443 ssl;
    server_name remote.example.com;

    set $upstream_app "remote-app";
    set $upstream_port "8080";
    set $upstream_proto "http";

    location / {
        proxy_pass http://remote-app:8080;
    }
}
        """.strip()
    )

    service = SwagManagerService(
        config_path=config_path,
        template_path=template_path,
        fs=RemoteValidationLocalFilesystem(),
    )
    service.validation_service.validate_nginx_syntax = AsyncMock(
        side_effect=AssertionError("local nginx validation should be skipped")
    )

    result = await service.add_mcp_location("remote.subdomain.conf", "/mcp")

    assert "location /mcp" in result.content
    service.validation_service.validate_nginx_syntax.assert_not_awaited()


def test_swag_manager_exposes_mcp_config_reader_explicitly(temp_paths):
    """SwagManager wires MCP config reading through an explicit public dependency."""
    config_path, template_path, _ = temp_paths

    service = SwagManagerService(config_path=config_path, template_path=template_path)

    assert service.mcp_operations.config_reader is service.config_operations


def test_swag_manager_accepts_explicit_runtime_config(temp_paths):
    """SwagManager can be configured per instance without reading global runtime config."""
    config_path, template_path, log_path = temp_paths
    runtime_config = SwagConfig(
        proxy_confs_path=config_path,
        log_directory=log_path,
        swag_log_base_path=str(log_path),
        template_path=template_path,
    )

    service = SwagManagerService(settings=runtime_config)

    assert service.config_path == config_path
    assert service.template_path == template_path
    assert service.health_monitor.swag_log_base_path == str(log_path)


async def test_ssh_tail_command_quotes_path_and_caps_line_count():
    """SSH tail command path and line count are sanitized before remote execution."""
    fs = SSHFilesystem("example.test")
    connection = CapturingTailConnection()
    fs._conn = connection

    lines = await fs.read_tail_lines("/var/log/nginx/error.log; touch /tmp/pwn", 999_999)

    assert lines == ["tail output\n"]
    assert connection.command is not None
    assert connection.command.startswith("tail -n 4096 ")
    assert "'/var/log/nginx/error.log; touch /tmp/pwn'" in connection.command


async def test_ssh_tail_fallback_reads_bounded_window():
    """SSH tail fallback reads a bounded byte window instead of the whole remote file."""
    line_count = 8_000
    content = "".join(f"line {index}\n" for index in range(line_count)).encode()
    fs = SSHFilesystem("example.test")
    sftp = BoundedTailSFTP(content)
    fs._conn = FailingTailConnection()
    fs._sftp = sftp

    lines = await fs.read_tail_lines("/var/log/nginx/error.log", 5)

    assert lines == [f"line {index}\n" for index in range(line_count - 5, line_count)]
    assert 0 < sftp.file.max_read_length <= SSHFilesystem.MAX_TAIL_FALLBACK_BYTES
