"""SSH/SFTP filesystem backend for remote SWAG server support.

Uses asyncssh for native async SFTP operations. Connects lazily on first
operation and reuses the connection for the lifetime of the instance.
"""

from __future__ import annotations

import asyncio
import contextlib
import fnmatch
import inspect
import logging
import os
import shlex
import uuid
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from swag_mcp.services.filesystem import FileStat

logger = logging.getLogger(__name__)

T = TypeVar("T")


class SSHRunResultProtocol(Protocol):
    """Minimal command result returned by SSH tail execution."""

    stdout: str | bytes | None


class SSHConnectionProtocol(Protocol):
    """Minimal async SSH connection interface used by this backend."""

    def start_sftp_client(self) -> Any:
        """Start an SFTP client."""
        ...

    async def run(self, command: str, check: bool) -> SSHRunResultProtocol:
        """Run a remote command."""
        ...

    def close(self) -> None:
        """Close the SSH connection."""
        ...


class SSHFilesystem:
    """Remote filesystem implementation using SSH/SFTP via asyncssh.

    Connects lazily on first filesystem operation and reuses the connection.
    Automatically recovers from connection failures by reconnecting once.
    """

    MAX_TAIL_LINES = 4096
    MAX_TAIL_FALLBACK_BYTES = 1024 * 1024

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str | None = None,
    ) -> None:
        """Initialize SSH filesystem.

        Args:
            host: Remote hostname or IP address
            port: SSH port (default: 22)
            username: SSH username (default: current user / ssh config)

        """
        self._host = host
        self._port = port
        self._username = username
        self._conn: SSHConnectionProtocol | None = None
        self._sftp: Any = None
        self._lock = asyncio.Lock()  # Protects connection setup

    async def _ensure_connected(self) -> Any:
        """Ensure SSH/SFTP connection is established.

        Returns:
            asyncssh.SFTPClient instance

        Raises:
            ConnectionError: If SSH connection fails
            ImportError: If asyncssh is not installed

        """
        async with self._lock:
            if self._sftp is not None:
                return self._sftp

            try:
                import asyncssh
            except ImportError as e:
                raise ImportError(
                    "asyncssh is required for remote SSH support. Install it with: uv add asyncssh"
                ) from e

            try:
                user_prefix = f"{self._username}@" if self._username else ""
                logger.info(f"Connecting to {user_prefix}{self._host}:{self._port} via SSH")
                connect_kwargs: dict[str, Any] = {
                    "host": self._host,
                    "port": self._port,
                    "known_hosts": (),  # Use system default known_hosts
                }
                # Only pass username if explicitly set — asyncssh reads
                # ~/.ssh/config when omitted but crashes on None (asyncssh 2.22+)
                if self._username is not None:
                    connect_kwargs["username"] = self._username
                conn = cast("SSHConnectionProtocol", await asyncssh.connect(**connect_kwargs))
                self._conn = conn
                self._sftp = await conn.start_sftp_client()
                logger.info(f"SSH connection established to {self._host}")
                return self._sftp
            except Exception as e:
                self._conn = None
                self._sftp = None
                raise ConnectionError(f"Failed to connect to {self._host}:{self._port}: {e}") from e

    async def _get_sftp(self) -> Any:
        """Get SFTP client, reconnecting if needed."""
        if self._sftp is not None:
            return self._sftp
        return await self._ensure_connected()

    async def _with_reconnect(self, operation: Callable[[Any], Awaitable[T]]) -> T:
        """Execute an operation with automatic reconnection on failure.

        Args:
            operation: Async callable that takes an SFTP client

        Returns:
            Result of the operation

        """
        try:
            sftp = await self._get_sftp()
            return await operation(sftp)
        except Exception as e:
            # Check if this is a connection-level error
            error_name = type(e).__name__
            connection_errors = (
                "ConnectionLost",
                "DisconnectError",
                "ChannelClosedError",
            )
            if error_name in connection_errors:
                logger.warning(f"SSH connection lost, reconnecting: {e}")
                self._conn = None
                self._sftp = None
                sftp = await self._ensure_connected()
                return await operation(sftp)
            raise

    async def read_bytes(self, path: str) -> bytes:
        """Read file contents as bytes via SFTP."""

        async def _read_raw(sftp: Any) -> bytes:
            async with sftp.open(path, "rb") as f:
                return await f.read()

        return await self._with_reconnect(_read_raw)

    async def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Read file contents as text via SFTP."""
        raw = await self.read_bytes(path)
        return raw.decode(encoding)

    async def write_text(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
    ) -> None:
        """Write text to file atomically via SFTP."""
        temp_path = f"{path}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
        encoded = content.encode(encoding)

        async def _write(sftp: Any) -> None:
            try:
                # Write to temp file
                async with sftp.open(temp_path, "wb") as f:
                    await f.write(encoded)

                # Atomic rename
                await sftp.rename(temp_path, path)
            except Exception:
                # Clean up temp file on error
                with contextlib.suppress(Exception):
                    await sftp.remove(temp_path)
                raise

        await self._with_reconnect(_write)

    async def exists(self, path: str) -> bool:
        """Check if path exists on remote server."""

        async def _exists(sftp: Any) -> bool:
            return await sftp.exists(path)

        return await self._with_reconnect(_exists)

    async def is_file(self, path: str) -> bool:
        """Check if path is a regular file."""

        async def _is_file(sftp: Any) -> bool:
            return await sftp.isfile(path)

        return await self._with_reconnect(_is_file)

    async def is_symlink(self, path: str) -> bool:
        """Check if path is a symlink."""

        async def _is_symlink(sftp: Any) -> bool:
            try:
                await sftp.readlink(path)
                return True
            except Exception:
                return False

        return await self._with_reconnect(_is_symlink)

    async def stat(self, path: str) -> FileStat:
        """Get file metadata via SFTP."""

        async def _stat(sftp: Any) -> FileStat:
            import stat as stat_module

            attrs = await sftp.stat(path)
            mode = attrs.permissions or 0
            return FileStat(
                st_size=attrs.size or 0,
                st_mtime=attrs.mtime or 0.0,
                is_file=stat_module.S_ISREG(mode),
                is_dir=stat_module.S_ISDIR(mode),
            )

        return await self._with_reconnect(_stat)

    async def glob(self, directory: str, pattern: str) -> list[str]:
        """List filenames matching glob pattern in remote directory.

        Uses a single readdir call + fnmatch filtering.
        Returns filenames only (not full paths).
        """

        async def _glob(sftp: Any) -> list[str]:
            try:
                entries = await sftp.readdir(directory)
            except Exception as e:
                logger.warning(f"Failed to list directory {directory}: {e}")
                return []

            filenames = [entry.filename for entry in entries if entry.filename not in (".", "..")]
            matched = fnmatch.filter(filenames, pattern)
            return sorted(matched)

        return await self._with_reconnect(_glob)

    async def mkdir(self, path: str, parents: bool = False) -> None:
        """Create directory on remote server."""

        async def _mkdir(sftp: Any) -> None:
            if parents:
                await sftp.makedirs(path, exist_ok=True)
            else:
                try:
                    await sftp.mkdir(path)
                except Exception:
                    # Directory may already exist
                    if not await sftp.isdir(path):
                        raise

        await self._with_reconnect(_mkdir)

    async def unlink(self, path: str) -> None:
        """Delete a file on remote server."""

        async def _unlink(sftp: Any) -> None:
            await sftp.remove(path)

        await self._with_reconnect(_unlink)

    async def rename(self, src: str, dst: str) -> None:
        """Atomically rename/move a file on remote server."""

        async def _rename(sftp: Any) -> None:
            await sftp.rename(src, dst)

        await self._with_reconnect(_rename)

    async def statvfs(self, path: str) -> tuple[int, int] | None:
        """Get filesystem stats via SFTP statvfs extension.

        Returns (available_bytes, block_size) or None if unsupported.
        """

        async def _statvfs(
            sftp: Any,
        ) -> tuple[int, int] | None:
            try:
                st = await sftp.statvfs(path)
                return (
                    st.f_bavail * st.f_frsize,
                    st.f_frsize,
                )
            except Exception:
                return None

        return await self._with_reconnect(_statvfs)

    async def read_tail_lines(self, path: str, n: int) -> list[str]:
        """Read last N lines of a remote file.

        Uses SSH command execution (tail) for efficiency on large
        files, falling back to a bounded SFTP read if command execution fails.
        The fallback reads at most MAX_TAIL_FALLBACK_BYTES, so very long final
        lines may return fewer than the requested line count and emit a debug log.
        """
        line_count = max(0, min(int(n), self.MAX_TAIL_LINES))
        if line_count == 0:
            return []

        if self._conn is None:
            await self._get_sftp()

        # Try efficient tail via SSH command first
        if self._conn is not None:
            try:
                result = await self._conn.run(
                    f"tail -n {line_count} {shlex.quote(path)}",
                    check=True,
                )
                stdout = result.stdout or ""
                if isinstance(stdout, bytes):
                    stdout = stdout.decode("utf-8", errors="ignore")
                lines: list[str] = stdout.splitlines(keepends=True)
                return lines
            except Exception:
                logger.debug(f"SSH tail command failed for {path}, falling back to SFTP read")

        try:
            lines = await self._read_tail_lines_bounded(path, line_count)
            if len(lines) < line_count:
                logger.debug(
                    "Bounded SFTP tail for %s returned %d/%d lines; fallback window is %d bytes",
                    path,
                    len(lines),
                    line_count,
                    self.MAX_TAIL_FALLBACK_BYTES,
                )
            return lines
        except Exception as e:
            logger.warning(f"Failed to read tail lines from {path}: {e}")
            return []

    async def _read_tail_lines_bounded(self, path: str, n: int) -> list[str]:
        """Read a bounded byte window from the end of a remote file."""

        async def _read_tail(sftp: Any) -> list[str]:
            attrs = await sftp.stat(path)
            size = max(0, int(attrs.size or 0))
            read_size = min(size, self.MAX_TAIL_FALLBACK_BYTES)
            offset = max(0, size - read_size)

            async with sftp.open(path, "rb") as remote_file:
                if offset:
                    seek_result = remote_file.seek(offset)
                    if inspect.isawaitable(seek_result):
                        await seek_result

                raw = await remote_file.read(read_size)

            if offset and raw:
                newline_index = raw.find(b"\n")
                if newline_index >= 0:
                    raw = raw[newline_index + 1 :]

            lines = raw.decode("utf-8", errors="ignore").splitlines(keepends=True)
            return lines[-n:] if len(lines) > n else lines

        return await self._with_reconnect(_read_tail)

    def requires_remote_nginx_validation(self) -> bool:
        """SSH-backed files must be validated on the remote SWAG host."""
        return True

    async def close(self) -> None:
        """Close SSH and SFTP connections."""
        if self._sftp is not None:
            with contextlib.suppress(Exception):
                self._sftp.exit()
            self._sftp = None

        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None

        logger.info(f"SSH connection to {self._host} closed")
