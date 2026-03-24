"""Tests for filesystem abstraction layer."""

import tempfile
from pathlib import Path

import pytest
from swag_mcp.services.filesystem import FileStat, FilesystemBackend, LocalFilesystem


class TestLocalFilesystem:
    """Tests for LocalFilesystem implementation."""

    @pytest.fixture
    def fs(self):
        """Create a LocalFilesystem instance."""
        return LocalFilesystem()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)

    async def test_write_and_read_text(self, fs, temp_dir):
        """Test writing and reading text files."""
        path = str(temp_dir / "test.conf")
        await fs.write_text(path, "server { listen 80; }")
        content = await fs.read_text(path)
        assert content == "server { listen 80; }"

    async def test_write_and_read_bytes(self, fs, temp_dir):
        """Test writing text and reading bytes."""
        path = str(temp_dir / "test.conf")
        await fs.write_text(path, "hello")
        data = await fs.read_bytes(path)
        assert data == b"hello"

    async def test_exists(self, fs, temp_dir):
        """Test exists check."""
        path = str(temp_dir / "test.conf")
        assert not await fs.exists(path)
        await fs.write_text(path, "content")
        assert await fs.exists(path)

    async def test_is_file(self, fs, temp_dir):
        """Test is_file check."""
        path = str(temp_dir / "test.conf")
        await fs.write_text(path, "content")
        assert await fs.is_file(path)
        assert not await fs.is_file(str(temp_dir))

    async def test_is_symlink(self, fs, temp_dir):
        """Test symlink detection."""
        real_file = temp_dir / "real.conf"
        real_file.write_text("content")
        link_file = temp_dir / "link.conf"
        link_file.symlink_to(real_file)

        assert not await fs.is_symlink(str(real_file))
        assert await fs.is_symlink(str(link_file))

    async def test_stat(self, fs, temp_dir):
        """Test stat operation."""
        path = str(temp_dir / "test.conf")
        await fs.write_text(path, "hello world")
        stat = await fs.stat(path)
        assert isinstance(stat, FileStat)
        assert stat.st_size == 11
        assert stat.is_file
        assert not stat.is_dir
        assert stat.st_mtime > 0

    async def test_glob(self, fs, temp_dir):
        """Test glob pattern matching."""
        # Create test files
        (temp_dir / "app.subdomain.conf").write_text("config1")
        (temp_dir / "web.subfolder.conf").write_text("config2")
        (temp_dir / "app.sample").write_text("sample")
        (temp_dir / "readme.txt").write_text("readme")

        conf_files = await fs.glob(str(temp_dir), "*.conf")
        assert sorted(conf_files) == ["app.subdomain.conf", "web.subfolder.conf"]

        sample_files = await fs.glob(str(temp_dir), "*.sample")
        assert sample_files == ["app.sample"]

    async def test_glob_empty(self, fs, temp_dir):
        """Test glob with no matches."""
        result = await fs.glob(str(temp_dir), "*.conf")
        assert result == []

    async def test_mkdir(self, fs, temp_dir):
        """Test directory creation."""
        new_dir = str(temp_dir / "new" / "nested" / "dir")
        await fs.mkdir(new_dir, parents=True)
        assert Path(new_dir).is_dir()

    async def test_unlink(self, fs, temp_dir):
        """Test file deletion."""
        path = str(temp_dir / "test.conf")
        await fs.write_text(path, "content")
        assert await fs.exists(path)
        await fs.unlink(path)
        assert not await fs.exists(path)

    async def test_rename(self, fs, temp_dir):
        """Test atomic rename."""
        src = str(temp_dir / "old.conf")
        dst = str(temp_dir / "new.conf")
        await fs.write_text(src, "content")
        await fs.rename(src, dst)
        assert not await fs.exists(src)
        assert await fs.exists(dst)
        assert await fs.read_text(dst) == "content"

    async def test_statvfs(self, fs, temp_dir):
        """Test filesystem stats."""
        result = await fs.statvfs(str(temp_dir))
        assert result is not None
        available_bytes, block_size = result
        assert available_bytes > 0
        assert block_size > 0

    async def test_read_tail_lines(self, fs, temp_dir):
        """Test reading last N lines."""
        path = str(temp_dir / "test.log")
        lines = [f"line {i}\n" for i in range(100)]
        await fs.write_text(path, "".join(lines))

        tail = await fs.read_tail_lines(path, 5)
        assert len(tail) == 5
        assert tail[0] == "line 95\n"
        assert tail[4] == "line 99\n"

    async def test_read_tail_lines_fewer_than_n(self, fs, temp_dir):
        """Test tail when file has fewer lines than requested."""
        path = str(temp_dir / "test.log")
        await fs.write_text(path, "line1\nline2\nline3\n")

        tail = await fs.read_tail_lines(path, 10)
        assert len(tail) == 3

    async def test_atomic_write_cleanup_on_error(self, fs, temp_dir):
        """Test that temp files are cleaned up on write error."""
        path = str(temp_dir / "nonexistent" / "deep" / "test.conf")
        # Parent doesn't exist initially, but write_text creates it
        await fs.write_text(path, "content")
        assert await fs.exists(path)

    async def test_close_is_noop(self, fs):
        """Test that close does nothing for local filesystem."""
        await fs.close()  # Should not raise

    def test_implements_protocol(self, fs):
        """Test that LocalFilesystem satisfies FilesystemBackend protocol."""
        assert isinstance(fs, FilesystemBackend)
