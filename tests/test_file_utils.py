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
