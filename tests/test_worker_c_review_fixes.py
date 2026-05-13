"""Focused tests for Worker C review finding fixes."""

import asyncio
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from swag_mcp.models.config import (
    SwagConfigResult,
    SwagEditRequest,
    SwagHealthCheckRequest,
)
from swag_mcp.models.enums import SwagAction
from swag_mcp.services.filesystem import FileStat
from swag_mcp.services.swag_manager import SwagManagerService
from swag_mcp.services.template_manager import TemplateManager
from swag_mcp.tools.handlers.configs import _handle_create_action, _handle_update_action
from swag_mcp.utils.mcp_cache import MCPCache, get_cache
from swag_mcp.utils.token_efficient_formatter import TokenEfficientFormatter


class _ContextStub:
    async def info(self, message: str) -> None:
        """Accept progress messages from handlers under test."""
        _ = message


class _CountingFilesystem:
    def __init__(self) -> None:
        self.read_bytes_calls = 0
        self.glob_calls = 0

    async def read_bytes(self, path: str) -> bytes:
        self.read_bytes_calls += 1
        return Path(path).read_bytes()

    async def read_text(self, path: str, encoding: str = "utf-8") -> str:
        return Path(path).read_text(encoding=encoding)

    async def write_text(self, path: str, content: str, encoding: str = "utf-8") -> None:
        Path(path).write_text(content, encoding=encoding)

    async def exists(self, path: str) -> bool:
        return Path(path).exists()

    async def is_file(self, path: str) -> bool:
        return Path(path).is_file()

    async def is_symlink(self, path: str) -> bool:
        return Path(path).is_symlink()

    async def stat(self, path: str) -> FileStat:
        file_path = Path(path)
        stat_result = file_path.stat()
        return FileStat(
            st_size=stat_result.st_size,
            st_mtime=stat_result.st_mtime,
            is_file=file_path.is_file(),
            is_dir=file_path.is_dir(),
        )

    async def glob(self, directory: str, pattern: str) -> list[str]:
        self.glob_calls += 1
        return sorted(path.name for path in Path(directory).glob(pattern))

    async def mkdir(self, path: str, parents: bool = False) -> None:
        Path(path).mkdir(parents=parents, exist_ok=True)

    async def unlink(self, path: str) -> None:
        Path(path).unlink()

    async def rename(self, src: str, dst: str) -> None:
        Path(src).replace(Path(dst))

    async def statvfs(self, path: str) -> tuple[int, int] | None:
        return None

    async def read_tail_lines(self, path: str, n: int) -> list[str]:
        return []

    async def close(self) -> None:
        return None


def _safe_write_from_process(file_path: str, config_path: str, content: str) -> str:
    async def _write() -> str:
        from swag_mcp.services.file_operations import FileOperations

        file_ops = FileOperations(config_path=Path(config_path))
        await file_ops.safe_write_file(Path(file_path), content, "process write")
        return content

    return asyncio.run(_write())


@pytest.mark.asyncio
async def test_mcp_cache_computes_misses_without_global_lock() -> None:
    """Independent cache misses can compute concurrently."""
    cache = MCPCache(default_ttl=60, max_size=10)
    started: list[str] = []
    both_started = asyncio.Event()

    async def factory(name: str) -> str:
        started.append(name)
        if len(started) == 2:
            both_started.set()
        await both_started.wait()
        return name

    results = await asyncio.wait_for(
        asyncio.gather(
            cache.get_or_set("first", lambda: factory("first")),
            cache.get_or_set("second", lambda: factory("second")),
        ),
        timeout=0.25,
    )

    assert results == ["first", "second"]


@pytest.mark.asyncio
async def test_mcp_cache_caches_none_values() -> None:
    """Cached None values are hits, not repeated misses."""
    cache = MCPCache(default_ttl=60, max_size=10)
    calls = 0

    async def factory() -> None:
        nonlocal calls
        calls += 1
        return None

    assert await cache.get_or_set("none-value", factory) is None
    assert await cache.get_or_set("none-value", factory) is None
    assert calls == 1


@pytest.mark.asyncio
async def test_read_and_list_configs_use_cache(tmp_path: Path) -> None:
    """Repeated safe reads and lists avoid duplicate filesystem scans."""
    await get_cache().invalidate()
    fs = _CountingFilesystem()
    config_path = tmp_path / "proxy-confs"
    config_path.mkdir()
    (config_path / "cached.subdomain.conf").write_text("server_name cached.example.com;")

    service = SwagManagerService(config_path=config_path, template_path=Path("templates"), fs=fs)

    first_read = await service.read_config("cached.subdomain.conf")
    second_read = await service.read_config("cached.subdomain.conf")
    first_list = await service.list_configs("all")
    second_list = await service.list_configs("all")

    assert first_read == second_read == "server_name cached.example.com;"
    assert first_list.configs == second_list.configs == ["cached.subdomain.conf"]
    assert fs.read_bytes_calls == 1
    assert fs.glob_calls == 2
    await get_cache().invalidate()


def test_template_hooks_are_not_public_api() -> None:
    """Test-only template hooks stay out of the production-facing API."""
    manager = TemplateManager(Path("templates"))

    assert not hasattr(manager, "set_template_hooks")
    assert not hasattr(manager, "clear_template_hooks")
    assert not hasattr(manager, "get_template_path")


@pytest.mark.asyncio
async def test_backup_cleanup_scan_and_delete_units_skip_locked_file(tmp_path: Path) -> None:
    """Backup cleanup exposes small scan/delete units with lock-aware behavior."""
    config_path = tmp_path / "proxy-confs"
    config_path.mkdir()
    old_backup = config_path / "old.subdomain.conf.backup.20200101_120000_123456_deadbeef"
    old_backup.write_text("old backup")
    directory_backup = config_path / "dir.backup.20200101_120000_123456_deadbeef"
    directory_backup.mkdir()

    service = SwagManagerService(config_path=config_path, template_path=Path("templates"))
    candidates = await service.backup_manager._scan_backup_candidates()

    assert [candidate.filename for candidate in candidates] == [old_backup.name]

    file_lock = await service.file_ops.get_file_lock(old_backup)
    await file_lock.acquire()
    try:
        deleted = await service.backup_manager._delete_backup_candidate(
            candidates[0],
            cutoff_time=time.time() + 1,
        )
    finally:
        file_lock.release()

    assert deleted is False
    assert old_backup.exists()


@pytest.mark.asyncio
async def test_health_check_short_circuits_after_first_success() -> None:
    """Health checks do not wait for later endpoints after a success."""
    service = SwagManagerService(config_path=Path("/tmp"), template_path=Path("templates"))
    requested: list[str] = []

    class Response:
        def __init__(self, endpoint: str) -> None:
            self.endpoint = endpoint
            self.status = 406 if endpoint == "/mcp" else 404

        async def text(self) -> str:
            return self.endpoint

    class ResponseContext:
        def __init__(self, endpoint: str) -> None:
            self.endpoint = endpoint

        async def __aenter__(self) -> Response:
            requested.append(self.endpoint)
            if self.endpoint == "/":
                await asyncio.sleep(1)
            return Response(self.endpoint)

        async def __aexit__(self, *args: Any) -> None:
            return None

    class Session:
        def get(self, url: str, **kwargs: Any) -> ResponseContext:
            _ = kwargs
            endpoint = "/" + url.split("/", 3)[-1] if url.count("/") >= 3 else "/"
            if endpoint == "/":
                return ResponseContext("/")
            return ResponseContext(endpoint)

    async def get_session() -> Session:
        return Session()

    service.health_monitor.get_session = get_session  # type: ignore[method-assign]
    service.health_monitor._validate_health_check_host = AsyncMock(return_value=None)
    request = SwagHealthCheckRequest(
        action=SwagAction.HEALTH_CHECK,
        domain="parallel.example.com",
        timeout=10,
    )

    result = await asyncio.wait_for(service.health_check(request), timeout=0.25)

    assert result.success is True
    assert requested == ["/health", "/mcp"]


@pytest.mark.asyncio
async def test_health_check_rejects_localhost_targets() -> None:
    """Health checks reject localhost targets before any outbound request."""
    service = SwagManagerService(config_path=Path("/tmp"), template_path=Path("templates"))
    session = AsyncMock()
    service.health_monitor.get_session = AsyncMock(return_value=session)  # type: ignore[method-assign]
    request = SwagHealthCheckRequest(
        action=SwagAction.HEALTH_CHECK,
        domain="localhost",
        timeout=10,
    )

    result = await service.health_check(request)

    assert result.success is False
    assert "localhost" in (result.error or "")
    session.get.assert_not_called()


@pytest.mark.asyncio
async def test_create_handler_schedules_health_check_without_blocking() -> None:
    """Create returns after the write; health verification runs out of band."""
    health_started = asyncio.Event()
    health_release = asyncio.Event()
    health_done = asyncio.Event()

    class Service:
        async def create_config(self, request: Any) -> SwagConfigResult:
            return SwagConfigResult(filename=request.config_name, content="server {}")

        async def health_check(self, request: Any) -> Any:
            health_started.set()
            await health_release.wait()
            health_done.set()
            return None

    result = await _handle_create_action(
        _ContextStub(),  # type: ignore[arg-type]
        Service(),  # type: ignore[arg-type]
        TokenEfficientFormatter(),
        "fast.subdomain.conf",
        "fast.example.com",
        "app",
        8080,
        "http",
        "none",
        False,
    )

    assert result.structured_content is not None
    assert result.structured_content["filename"] == "fast.subdomain.conf"
    await asyncio.wait_for(health_started.wait(), timeout=1.0)
    health_release.set()
    await asyncio.wait_for(health_done.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_update_handler_schedules_health_check_without_blocking() -> None:
    """Update returns after the write; post-update health verification is out of band."""
    health_started = asyncio.Event()
    health_release = asyncio.Event()
    health_done = asyncio.Event()

    class Service:
        async def update_config_field(self, request: Any) -> SwagConfigResult:
            return SwagConfigResult(filename=request.config_name, content="server {}")

        async def read_config(self, config_name: str) -> str:
            _ = config_name
            return "server_name updated.example.com;"

        async def health_check(self, request: Any) -> Any:
            health_started.set()
            await health_release.wait()
            health_done.set()
            return None

    result = await _handle_update_action(
        _ContextStub(),  # type: ignore[arg-type]
        Service(),  # type: ignore[arg-type]
        TokenEfficientFormatter(),
        "fast.subdomain.conf",
        "port",
        "9090",
        False,
    )

    assert result.structured_content is not None
    assert result.structured_content["filename"] == "fast.subdomain.conf"
    await asyncio.wait_for(health_started.wait(), timeout=1.0)
    health_release.set()
    await asyncio.wait_for(health_done.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_cached_read_is_invalidated_after_edit(tmp_path: Path) -> None:
    """Write operations invalidate cached file content."""
    await get_cache().invalidate()
    config_path = tmp_path / "proxy-confs"
    config_path.mkdir()
    config_file = config_path / "edit.subdomain.conf"
    config_file.write_text("server_name old.example.com;")
    service = SwagManagerService(config_path=config_path, template_path=Path("templates"))

    assert await service.read_config("edit.subdomain.conf") == "server_name old.example.com;"

    await service.update_config(
        SwagEditRequest(
            action=SwagAction.EDIT,
            config_name="edit.subdomain.conf",
            new_content="server_name new.example.com;",
            create_backup=False,
        )
    )

    assert await service.read_config("edit.subdomain.conf") == "server_name new.example.com;"
    await get_cache().invalidate()


def test_mcp_nginx_routes_have_request_body_limit() -> None:
    """Generated and shared MCP nginx routes set bounded body limits."""
    template = Path("templates/mcp.subdomain.conf.j2").read_text()
    include = Path("config/nginx/mcp-location.conf").read_text()

    assert "client_max_body_size 0;" not in template
    assert "client_max_body_size 16m;" in include
    assert "client_body_timeout 30s;" in include


def test_safe_write_file_is_atomic_across_processes(tmp_path: Path) -> None:
    """Multi-process writes leave one complete payload and no temp files."""
    config_path = tmp_path / "proxy-confs"
    config_path.mkdir()
    target = config_path / "shared.subdomain.conf"
    payloads = [f"payload-{index}-" + ("x" * 4096) for index in range(6)]

    with ProcessPoolExecutor(max_workers=3) as executor:
        written = list(
            executor.map(
                _safe_write_from_process,
                [str(target)] * len(payloads),
                [str(config_path)] * len(payloads),
                payloads,
            )
        )

    final_content = target.read_text()
    assert written == payloads
    assert final_content in payloads
    assert not list(config_path.glob("*.tmp.*"))
