"""Focused regression tests for filesystem and MCP service review findings."""

import os
import time
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


class CapturingWriteFile:
    """Async write file stub that records bytes written."""

    def __init__(self, sftp: "CapturingWriteSFTP", path: str) -> None:
        """Initialize capture target."""
        self.sftp = sftp
        self.path = path

    async def __aenter__(self) -> "CapturingWriteFile":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Exit async context manager."""
        return None

    async def write(self, data: bytes) -> None:
        """Record written data."""
        self.sftp.writes[self.path] = data


class CapturingWriteSFTP:
    """SFTP stub that captures write and rename paths."""

    def __init__(self) -> None:
        """Initialize capture state."""
        self.writes: dict[str, bytes] = {}
        self.renames: list[tuple[str, str]] = []
        self.removes: list[str] = []

    def open(self, path: str, mode: str) -> CapturingWriteFile:
        """Open a remote temp file for writing."""
        _ = mode
        return CapturingWriteFile(self, path)

    async def rename(self, src: str, dst: str) -> None:
        """Capture atomic rename operation."""
        self.renames.append((src, dst))

    async def remove(self, path: str) -> None:
        """Capture cleanup operation."""
        self.removes.append(path)


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
    """MCP writes fail closed when authoritative remote validation is unavailable."""
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
    service.validation_service.validate_nginx_syntax = AsyncMock()

    with pytest.raises(ValueError, match="authoritative remote nginx validation"):
        await service.add_mcp_location("remote.subdomain.conf", "/mcp")

    assert "location /mcp" not in config_file.read_text()
    assert not list(config_path.glob("*.backup.*"))
    service.validation_service.validate_nginx_syntax.assert_not_awaited()


async def test_backup_cleanup_detects_uuid_temp_write_files(temp_paths):
    """Backup cleanup skips files with active UUID-suffixed atomic temp writes."""
    config_path, template_path, _ = temp_paths
    backup_file = config_path / "active.subdomain.conf.backup.20200101_120000_123456_deadbeef"
    temp_file = config_path / f"{backup_file.name}.tmp.{os.getpid()}.abcdef123456"
    backup_file.write_text("backup")
    temp_file.write_text("partial")
    old_time = time.time() - (3 * 24 * 60 * 60)
    os.utime(backup_file, (old_time, old_time))

    service = SwagManagerService(config_path=config_path, template_path=template_path)

    cleaned_count = await service.cleanup_old_backups(retention_days=1)

    assert cleaned_count == 0
    assert backup_file.exists()


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


async def test_ssh_write_uses_uuid_suffixed_temp_path():
    """SSH writes use unique temp paths for concurrent requests in one process."""
    fs = SSHFilesystem("example.test")
    sftp = CapturingWriteSFTP()
    fs._sftp = sftp

    await fs.write_text("/remote/app.subdomain.conf", "content")

    assert len(sftp.renames) == 1
    temp_path, destination_path = sftp.renames[0]
    assert destination_path == "/remote/app.subdomain.conf"
    assert temp_path.startswith(f"/remote/app.subdomain.conf.tmp.{os.getpid()}.")
    assert temp_path != f"/remote/app.subdomain.conf.tmp.{os.getpid()}"
