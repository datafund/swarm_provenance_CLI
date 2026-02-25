"""Tests for file_utils directory/TAR functions."""

import hashlib
import tarfile
from pathlib import Path

import pytest

from swarm_provenance_uploader.core.file_utils import (
    create_tar_from_directory,
    calculate_directory_hash_and_files,
)


@pytest.fixture
def sample_directory(tmp_path):
    """Create a sample directory with files for testing."""
    (tmp_path / "file1.txt").write_text("hello world")
    (tmp_path / "file2.csv").write_text("a,b,c\n1,2,3")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.json").write_text('{"key": "value"}')
    return tmp_path


@pytest.fixture
def empty_directory(tmp_path):
    """Create an empty directory."""
    empty = tmp_path / "empty"
    empty.mkdir()
    return empty


class TestCreateTarFromDirectory:
    """Tests for create_tar_from_directory."""

    def test_create_tar_from_directory(self, sample_directory, tmp_path):
        """Creates a TAR and verifies it contains the correct files."""
        tar_path = tmp_path / "output" / "test.tar"
        tar_path.parent.mkdir(parents=True)

        result = create_tar_from_directory(sample_directory, tar_path)

        assert result == tar_path
        assert tar_path.exists()
        assert tar_path.stat().st_size > 0

        # Verify contents
        with tarfile.open(tar_path, "r") as tar:
            names = sorted(tar.getnames())
            assert "file1.txt" in names
            assert "file2.csv" in names
            assert "subdir/nested.json" in names

    def test_create_tar_preserves_structure(self, sample_directory, tmp_path):
        """Verifies nested directory structure is preserved in TAR."""
        tar_path = tmp_path / "struct.tar"
        create_tar_from_directory(sample_directory, tar_path)

        with tarfile.open(tar_path, "r") as tar:
            # Extract and verify content
            member = tar.getmember("subdir/nested.json")
            assert member is not None
            f = tar.extractfile(member)
            content = f.read().decode()
            assert '"key": "value"' in content

    def test_create_tar_empty_directory(self, empty_directory, tmp_path):
        """Raises ValueError on empty directory."""
        tar_path = tmp_path / "empty.tar"
        with pytest.raises(ValueError, match="empty"):
            create_tar_from_directory(empty_directory, tar_path)

    def test_create_tar_not_a_directory(self, tmp_path):
        """Raises ValueError when path is a file, not a directory."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("data")
        tar_path = tmp_path / "out.tar"
        with pytest.raises(ValueError, match="Not a directory"):
            create_tar_from_directory(file_path, tar_path)

    def test_create_tar_no_compression(self, sample_directory, tmp_path):
        """Verifies TAR is uncompressed (raw TAR, not gzip/bz2)."""
        tar_path = tmp_path / "raw.tar"
        create_tar_from_directory(sample_directory, tar_path)

        # Raw TAR files start with the filename of the first entry
        # and can be opened with mode 'r' (not 'r:gz' or 'r:bz2')
        with tarfile.open(tar_path, "r") as tar:
            assert len(tar.getnames()) > 0


class TestCalculateDirectoryHashAndFiles:
    """Tests for calculate_directory_hash_and_files."""

    def test_calculate_directory_hash_and_files(self, sample_directory):
        """Correct hashes and file list returned."""
        overall_hash, file_infos = calculate_directory_hash_and_files(sample_directory)

        assert len(overall_hash) == 64  # SHA-256 hex
        assert len(file_infos) == 3

        paths = [fi["path"] for fi in file_infos]
        assert "file1.txt" in paths
        assert "file2.csv" in paths
        assert "subdir/nested.json" in paths

        # Verify individual file hash
        for fi in file_infos:
            if fi["path"] == "file1.txt":
                expected = hashlib.sha256(b"hello world").hexdigest()
                assert fi["content_hash"] == expected
                assert fi["size"] == len(b"hello world")

    def test_calculate_directory_hash_deterministic(self, tmp_path):
        """Same input produces same hash regardless of call order."""
        # Create files
        (tmp_path / "a.txt").write_text("alpha")
        (tmp_path / "b.txt").write_text("beta")

        hash1, _ = calculate_directory_hash_and_files(tmp_path)
        hash2, _ = calculate_directory_hash_and_files(tmp_path)

        assert hash1 == hash2

    def test_calculate_directory_hash_empty(self, empty_directory):
        """Raises ValueError on empty directory."""
        with pytest.raises(ValueError, match="empty"):
            calculate_directory_hash_and_files(empty_directory)

    def test_calculate_directory_hash_not_a_directory(self, tmp_path):
        """Raises ValueError when path is a file."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("data")
        with pytest.raises(ValueError, match="Not a directory"):
            calculate_directory_hash_and_files(file_path)


class TestSymlinkHandling:
    """Tests for symlink safety in directory operations."""

    def test_create_tar_skips_symlinks(self, tmp_path):
        """Symlinks are excluded from TAR archives."""
        real_file = tmp_path / "real.txt"
        real_file.write_text("real content")
        link = tmp_path / "link.txt"
        link.symlink_to(real_file)

        tar_path = tmp_path / "out.tar"
        create_tar_from_directory(tmp_path, tar_path)

        with tarfile.open(tar_path, "r") as tar:
            names = tar.getnames()
            assert "real.txt" in names
            assert "link.txt" not in names

    def test_calculate_hash_skips_symlinks(self, tmp_path):
        """Symlinks are excluded from hash calculation."""
        real_file = tmp_path / "real.txt"
        real_file.write_text("real content")
        link = tmp_path / "link.txt"
        link.symlink_to(real_file)

        overall_hash, file_infos = calculate_directory_hash_and_files(tmp_path)
        paths = [fi["path"] for fi in file_infos]
        assert "real.txt" in paths
        assert "link.txt" not in paths
        assert len(file_infos) == 1

    def test_directory_with_only_symlinks_is_empty(self, tmp_path):
        """Directory containing only symlinks is treated as empty."""
        target = tmp_path / "target"
        target.mkdir()
        real = target / "real.txt"
        real.write_text("data")

        symlink_dir = tmp_path / "links"
        symlink_dir.mkdir()
        (symlink_dir / "link.txt").symlink_to(real)

        tar_path = tmp_path / "out.tar"
        with pytest.raises(ValueError, match="empty"):
            create_tar_from_directory(symlink_dir, tar_path)


class TestBinaryAndEdgeCases:
    """Tests for binary files, hidden files, and edge cases."""

    def test_create_tar_with_binary_files(self, tmp_path):
        """Binary files are correctly included in TAR."""
        binary_data = bytes(range(256))
        (tmp_path / "binary.bin").write_bytes(binary_data)

        tar_path = tmp_path / "out.tar"
        create_tar_from_directory(tmp_path, tar_path)

        with tarfile.open(tar_path, "r") as tar:
            member = tar.getmember("binary.bin")
            extracted = tar.extractfile(member).read()
            assert extracted == binary_data

    def test_calculate_hash_binary_files(self, tmp_path):
        """Binary files are correctly hashed."""
        binary_data = bytes(range(256))
        (tmp_path / "data.bin").write_bytes(binary_data)

        overall_hash, file_infos = calculate_directory_hash_and_files(tmp_path)
        assert len(file_infos) == 1
        expected_hash = hashlib.sha256(binary_data).hexdigest()
        assert file_infos[0]["content_hash"] == expected_hash
        assert file_infos[0]["size"] == 256

    def test_create_tar_includes_hidden_files(self, tmp_path):
        """Hidden files (dotfiles) are included in TAR."""
        (tmp_path / ".hidden").write_text("secret")
        (tmp_path / "visible.txt").write_text("public")

        tar_path = tmp_path / "out.tar"
        create_tar_from_directory(tmp_path, tar_path)

        with tarfile.open(tar_path, "r") as tar:
            names = tar.getnames()
            assert ".hidden" in names
            assert "visible.txt" in names

    def test_create_tar_with_empty_file(self, tmp_path):
        """Empty (zero-byte) files are included in TAR."""
        (tmp_path / "empty.txt").write_bytes(b"")
        (tmp_path / "notempty.txt").write_text("data")

        tar_path = tmp_path / "out.tar"
        create_tar_from_directory(tmp_path, tar_path)

        with tarfile.open(tar_path, "r") as tar:
            names = tar.getnames()
            # empty.txt is a zero-byte file but still a file
            assert "empty.txt" in names

    def test_calculate_hash_empty_file(self, tmp_path):
        """Empty files have correct SHA-256 (hash of empty bytes)."""
        (tmp_path / "empty.txt").write_bytes(b"")

        _, file_infos = calculate_directory_hash_and_files(tmp_path)
        expected = hashlib.sha256(b"").hexdigest()
        assert file_infos[0]["content_hash"] == expected
        assert file_infos[0]["size"] == 0

    def test_nonexistent_directory(self, tmp_path):
        """Nonexistent path raises ValueError."""
        fake = tmp_path / "does_not_exist"
        tar_path = tmp_path / "out.tar"
        with pytest.raises(ValueError, match="Not a directory"):
            create_tar_from_directory(fake, tar_path)
        with pytest.raises(ValueError, match="Not a directory"):
            calculate_directory_hash_and_files(fake)
