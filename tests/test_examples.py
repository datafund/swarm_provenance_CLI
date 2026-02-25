"""Tests for examples common utilities (sample_generator, verify)."""

import csv
import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

# Add examples dir to path so we can import common modules
EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
sys.path.insert(0, str(EXAMPLES_DIR))

from common.sample_generator import generate_text_file, generate_json_file, generate_csv_file
from common.verify import compute_sha256, compare_hashes, parse_upload_output


# --- sample_generator tests ---


class TestGenerateTextFile:
    def test_default_content(self, tmp_path):
        path = str(tmp_path / "test.txt")
        result = generate_text_file(path)
        assert os.path.exists(result)
        content = Path(result).read_text()
        assert "Provenance Record" in content
        assert "Swarm Provenance CLI Example" in content

    def test_custom_content(self, tmp_path):
        path = str(tmp_path / "test.txt")
        result = generate_text_file(path, content="custom data")
        assert Path(result).read_text() == "custom data"

    def test_creates_parent_dirs(self, tmp_path):
        path = str(tmp_path / "sub" / "deep" / "test.txt")
        result = generate_text_file(path)
        assert os.path.exists(result)

    def test_returns_absolute_path(self, tmp_path):
        path = str(tmp_path / "test.txt")
        result = generate_text_file(path)
        assert os.path.isabs(result)


class TestGenerateJsonFile:
    def test_default_data(self, tmp_path):
        path = str(tmp_path / "test.json")
        result = generate_json_file(path)
        assert os.path.exists(result)
        data = json.loads(Path(result).read_text())
        assert data["type"] == "provenance-record"
        assert data["version"] == "1.0"
        assert "payload" in data

    def test_custom_data(self, tmp_path):
        path = str(tmp_path / "test.json")
        custom = {"key": "value", "number": 42}
        result = generate_json_file(path, data=custom)
        data = json.loads(Path(result).read_text())
        assert data == custom

    def test_creates_parent_dirs(self, tmp_path):
        path = str(tmp_path / "sub" / "test.json")
        result = generate_json_file(path)
        assert os.path.exists(result)


class TestGenerateCsvFile:
    def test_default_data(self, tmp_path):
        path = str(tmp_path / "test.csv")
        result = generate_csv_file(path)
        assert os.path.exists(result)
        with open(result) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 3
        assert rows[0]["label"] == "sensor-A"

    def test_custom_rows(self, tmp_path):
        path = str(tmp_path / "test.csv")
        rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        result = generate_csv_file(path, rows=rows)
        with open(result) as f:
            reader = csv.DictReader(f)
            data = list(reader)
        assert len(data) == 2
        assert data[0]["a"] == "1"

    def test_custom_headers(self, tmp_path):
        path = str(tmp_path / "test.csv")
        rows = [{"x": 1, "y": 2}]
        result = generate_csv_file(path, rows=rows, headers=["x", "y"])
        with open(result) as f:
            header_line = f.readline().strip()
        assert header_line == "x,y"


# --- verify tests ---


class TestComputeSha256:
    def test_known_hash(self):
        data = b"hello world"
        expected = hashlib.sha256(data).hexdigest()
        assert compute_sha256(data) == expected

    def test_empty_data(self):
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_sha256(b"") == expected


class TestCompareHashes:
    def test_matching_files(self, tmp_path):
        content = b"identical content"
        f1 = tmp_path / "file1.txt"
        f2 = tmp_path / "file2.txt"
        f1.write_bytes(content)
        f2.write_bytes(content)
        assert compare_hashes(str(f1), str(f2)) is True

    def test_different_files(self, tmp_path):
        f1 = tmp_path / "file1.txt"
        f2 = tmp_path / "file2.txt"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")
        assert compare_hashes(str(f1), str(f2)) is False


class TestParseUploadOutput:
    def test_parse_text_output(self):
        output = (
            "Processing file: sample.txt...\n"
            "Acquiring stamp from pool...\n"
            "\n"
            "SUCCESS! Upload complete.\n"
            "Swarm Reference Hash:\n"
            "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2\n"
        )
        result = parse_upload_output(output)
        assert result["reference"] == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"

    def test_parse_json_output(self):
        output = json.dumps({
            "swarm_hash": "abc123def456abc123def456abc123def456abc123def456abc123def456abc123de",
            "content_hash": "xyz789",
            "stamp_id": "stamp001",
        })
        result = parse_upload_output(output)
        assert result["reference"] == "abc123def456abc123def456abc123def456abc123def456abc123def456abc123de"
        assert result["swarm_hash"] == result["reference"]
        assert result["stamp_id"] == "stamp001"

    def test_parse_empty_output(self):
        result = parse_upload_output("")
        assert result == {}

    def test_parse_no_reference(self):
        output = "Some random output\nwithout any reference hash\n"
        result = parse_upload_output(output)
        assert "reference" not in result

    def test_parse_text_with_stamp_id(self):
        output = (
            "Processing file: sample.txt...\n"
            "  Stamp ID: abc123def456\n"
            "\n"
            "SUCCESS! Upload complete.\n"
            "Swarm Reference Hash:\n"
            "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2\n"
        )
        result = parse_upload_output(output)
        assert result["reference"] == "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        assert "abc123def456" in result.get("stamp_id", "")

    def test_ignores_short_lines_after_header(self):
        """Lines shorter than 64 chars after 'Swarm Reference Hash:' should not be picked up."""
        output = (
            "Swarm Reference Hash:\n"
            "short\n"
        )
        result = parse_upload_output(output)
        assert "reference" not in result
