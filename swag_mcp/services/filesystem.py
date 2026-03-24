"""Filesystem abstraction layer for SWAG MCP.

Provides a protocol for filesystem operations that can be backed by
local filesystem or remote SSH/SFTP connections.
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

import aiofiles

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileStat:
    """File metadata."""

    st_size: int
    st_mtime: float
    is_file: bool
    is_dir: bool


@runtime_checkable
class FilesystemBackend(Protocol):
    """Protocol for filesystem operations - both local and remote."""

    async def read_bytes(self, path: str) -> bytes:
        """Read file contents as bytes."""
        ...

    async def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Read file contents as text."""
        ...

    async def write_text(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
    ) -> None:
        """Write text to file atomically (temp file + rename)."""
        ...

    async def exists(self, path: str) -> bool:
        """Check if path exists."""
        ...

    async def is_file(self, path: str) -> bool:
        """Check if path is a regular file."""
        ...

    async def is_symlink(self, path: str) -> bool:
        """Check if path is a symlink."""
        ...

    async def stat(self, path: str) -> FileStat:
        """Get file metadata."""
        ...

    async def glob(self, directory: str, pattern: str) -> list[str]:
        """List filenames matching glob pattern in directory.

        Returns filenames only (not full paths).
        """
        ...

    async def mkdir(self, path: str, parents: bool = False) -> None:
        """Create directory."""
        ...

    async def unlink(self, path: str) -> None:
        """Delete a file."""
        ...

    async def rename(self, src: str, dst: str) -> None:
        """Atomically rename/move a file."""
        ...

    async def statvfs(self, path: str) -> tuple[int, int] | None:
        """Get filesystem stats: (available_bytes, block_size).

        Returns None if unavailable.
        """
        ...

    async def read_tail_lines(self, path: str, n: int) -> list[str]:
        """Read last N lines of a file efficiently."""
        ...

    async def close(self) -> None:
        """Clean up resources (close connections)."""
        ...


class LocalFilesystem:
    """Local filesystem implementation of FilesystemBackend."""

    async def read_bytes(self, path: str) -> bytes:
        """Read file contents as bytes."""
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Read file contents as text."""
        async with aiofiles.open(path, encoding=encoding) as f:
            return await f.read()

    async def write_text(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
    ) -> None:
        """Write text to file atomically via temp file + rename."""
        file_path = Path(path)
        temp_path = file_path.with_suffix(f"{file_path.suffix}.tmp.{os.getpid()}")

        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write to temporary file
            async with aiofiles.open(temp_path, "w", encoding=encoding) as f:
                await f.write(content)
                await f.flush()
                await asyncio.to_thread(os.fsync, f.fileno())

            # Atomic move
            temp_path.replace(file_path)

        except Exception:
            # Clean up temp file on error
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass
            raise

    async def exists(self, path: str) -> bool:
        """Check if path exists."""
        return Path(path).exists()

    async def is_file(self, path: str) -> bool:
        """Check if path is a regular file."""
        return Path(path).is_file()

    async def is_symlink(self, path: str) -> bool:
        """Check if path is a symlink."""
        return Path(path).is_symlink()

    async def stat(self, path: str) -> FileStat:
        """Get file metadata."""
        st = Path(path).stat()
        p = Path(path)
        return FileStat(
            st_size=st.st_size,
            st_mtime=st.st_mtime,
            is_file=p.is_file(),
            is_dir=p.is_dir(),
        )

    async def glob(self, directory: str, pattern: str) -> list[str]:
        """List filenames matching glob pattern in directory."""
        dir_path = Path(directory)
        return sorted(f.name for f in dir_path.glob(pattern) if not fnmatch.fnmatch(f.name, ".*"))

    async def mkdir(self, path: str, parents: bool = False) -> None:
        """Create directory."""
        Path(path).mkdir(parents=parents, exist_ok=True)

    async def unlink(self, path: str) -> None:
        """Delete a file."""
        Path(path).unlink()

    async def rename(self, src: str, dst: str) -> None:
        """Atomically rename/move a file."""
        Path(src).replace(Path(dst))

    async def statvfs(self, path: str) -> tuple[int, int] | None:
        """Get filesystem stats: (available_bytes, block_size)."""
        try:
            st = os.statvfs(path)
            return (st.f_bavail * st.f_frsize, st.f_frsize)
        except (OSError, AttributeError):
            return None

    async def read_tail_lines(self, path: str, n: int) -> list[str]:
        """Read last N lines of a file using memory-efficient streaming."""
        line_buffer: deque[str] = deque(maxlen=n)

        async with aiofiles.open(path, encoding="utf-8", errors="ignore") as f:
            async for line in f:
                line_buffer.append(line)

        return list(line_buffer)

    async def close(self) -> None:
        """No-op for local filesystem."""
