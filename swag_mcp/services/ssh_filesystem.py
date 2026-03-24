"""SSH/SFTP filesystem backend for remote SWAG server support.

Uses asyncssh for native async SFTP operations. Connects lazily on first
operation and reuses the connection for the lifetime of the instance.
"""

from __future__ import annotations

import asyncio
import contextlib
import fnmatch
import logging
import os
from typing import Any

from swag_mcp.services.filesystem import FileStat

logger = logging.getLogger(__name__)


class SSHFilesystem:
    """Remote filesystem implementation using SSH/SFTP via asyncssh.

    Connects lazily on first filesystem operation and reuses the connection.
    Automatically recovers from connection failures by reconnecting once.
    """

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
        self._conn: Any = None  # asyncssh.SSHClientConnection
        self._sftp: Any = None  # asyncssh.SFTPClient
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
                import asyncssh  # type: ignore[import-not-found]
            except ImportError as e:
                raise ImportError(
                    "asyncssh is required for remote SSH support. "
                    "Install it with: uv add asyncssh"
                ) from e

            try:
                logger.info(
                    f"Connecting to "
                    f"{self._username + '@' if self._username else ''}"
                    f"{self._host}:{self._port} via SSH"
                )
                self._conn = await asyncssh.connect(
                    self._host,
                    port=self._port,
                    username=self._username,
                    known_hosts=None,  # Use system known_hosts
                )
                self._sftp = await self._conn.start_sftp_client()
                logger.info(f"SSH connection established to {self._host}")
                return self._sftp
            except Exception as e:
                self._conn = None
                self._sftp = None
                raise ConnectionError(
                    f"Failed to connect to " f"{self._host}:{self._port}: {e}"
                ) from e

    async def _get_sftp(self) -> Any:
        """Get SFTP client, reconnecting if needed."""
        if self._sftp is not None:
            return self._sftp
        return await self._ensure_connected()

    async def _with_reconnect(self, operation: Any) -> Any:
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

        async def _read(sftp: Any) -> bytes:
            return await sftp.getl(path)  # type: ignore[no-any-return]

        # Use raw SFTP read
        async def _read_raw(sftp: Any) -> bytes:
            async with sftp.open(path, "rb") as f:
                return await f.read()  # type: ignore[no-any-return]

        return await self._with_reconnect(_read_raw)  # type: ignore[no-any-return]

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
        temp_path = f"{path}.tmp.{os.getpid()}"
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
            return await sftp.exists(path)  # type: ignore[no-any-return]

        return await self._with_reconnect(_exists)  # type: ignore[no-any-return]

    async def is_file(self, path: str) -> bool:
        """Check if path is a regular file."""

        async def _is_file(sftp: Any) -> bool:
            return await sftp.isfile(path)  # type: ignore[no-any-return]

        return await self._with_reconnect(_is_file)  # type: ignore[no-any-return]

    async def is_symlink(self, path: str) -> bool:
        """Check if path is a symlink."""

        async def _is_symlink(sftp: Any) -> bool:
            try:
                await sftp.readlink(path)
                return True
            except Exception:
                return False

        return await self._with_reconnect(_is_symlink)  # type: ignore[no-any-return]

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

        return await self._with_reconnect(_stat)  # type: ignore[no-any-return]

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

        return await self._with_reconnect(_glob)  # type: ignore[no-any-return]

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

        return await self._with_reconnect(_statvfs)  # type: ignore[no-any-return]

    async def read_tail_lines(self, path: str, n: int) -> list[str]:
        """Read last N lines of a remote file.

        Uses SSH command execution (tail) for efficiency on large
        files, falling back to SFTP read if command execution fails.
        """
        # Try efficient tail via SSH command first
        if self._conn is not None:
            try:
                result = await self._conn.run(
                    f"tail -n {n} {path}",
                    check=True,
                )
                lines: list[str] = result.stdout.splitlines(keepends=True)
                return lines
            except Exception:
                logger.debug(f"SSH tail command failed for {path}, " "falling back to SFTP read")

        # Fallback: read entire file via SFTP and take last N lines
        try:
            content = await self.read_text(path, encoding="utf-8")
            all_lines = content.splitlines(keepends=True)
            return all_lines[-n:] if len(all_lines) > n else all_lines
        except Exception as e:
            logger.warning(f"Failed to read tail lines from {path}: {e}")
            return []

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
