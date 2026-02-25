"""Tests for examples common utilities and demo scripts.

Unit tests verify:
- sample_generator: text, JSON, CSV file generation
- verify: SHA-256 hashing, file comparison, CLI output parsing
- demo workflow: full upload/download/verify cycle with mocked CLI
- 02-audit-trail: multi-record upload with --std AUDIT-LOG-V1
- 03-scientific-data: PROV-O standard with --duration 720
- 05-encrypted-data: encryption workflow with --enc AES-256-GCM
- 06-market-memory: canonical hashing and prediction→observation linking

Integration tests (marked @pytest.mark.gateway) run actual demos
against a live gateway — skipped when gateway is unavailable.
"""

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add examples dir to path so we can import common modules
EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
DEMO_DIR = EXAMPLES_DIR / "01-basic-upload-download"
AUDIT_DIR = EXAMPLES_DIR / "02-audit-trail"
SCIENCE_DIR = EXAMPLES_DIR / "03-scientific-data"
ENCRYPTED_DIR = EXAMPLES_DIR / "05-encrypted-data"
MARKET_DIR = EXAMPLES_DIR / "06-market-memory"
sys.path.insert(0, str(EXAMPLES_DIR))

from common.sample_generator import generate_text_file, generate_json_file, generate_csv_file
from common.verify import compute_sha256, compare_hashes, parse_upload_output


# =============================================================================
# SAMPLE GENERATOR TESTS
# =============================================================================


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


# =============================================================================
# VERIFY UTILITY TESTS
# =============================================================================


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


# =============================================================================
# DEMO WORKFLOW TESTS (mocked CLI)
# =============================================================================

FAKE_HASH = "a" * 64


def _make_completed_process(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess(
        args=["swarm-prov-upload"], stdout=stdout, stderr=stderr, returncode=returncode
    )


def _get_cli_subcommand(cmd):
    """Extract the CLI subcommand (health, upload, download) from a cmd list."""
    # cmd is like ["swarm-prov-upload", "upload", "--file", ...]
    for arg in cmd[1:]:
        if not str(arg).startswith("-"):
            return str(arg)
    return ""


def _upload_success_output(ref_hash=FAKE_HASH):
    return (
        f"Processing file: sample.txt...\n"
        f"Acquiring stamp from pool...\n"
        f"  Stamp acquired from pool (ID: ...abcdef123456)\n"
        f"Uploading data to Swarm...\n"
        f"\n"
        f"SUCCESS! Upload complete.\n"
        f"Swarm Reference Hash:\n"
        f"{ref_hash}\n"
    )


class TestDemoShellScript:
    """Tests for the bash demo script."""

    def test_shell_script_is_valid_bash(self):
        """The demo.sh script should parse without syntax errors."""
        result = subprocess.run(
            ["bash", "-n", str(DEMO_DIR / "demo.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"

    def test_shell_script_is_executable(self):
        """demo.sh should have the executable bit set."""
        assert os.access(str(DEMO_DIR / "demo.sh"), os.X_OK)

    def test_shell_script_has_shebang(self):
        """demo.sh should start with a bash shebang."""
        content = (DEMO_DIR / "demo.sh").read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_shell_script_uses_strict_mode(self):
        """demo.sh should use set -euo pipefail."""
        content = (DEMO_DIR / "demo.sh").read_text()
        assert "set -euo pipefail" in content

    def test_shell_ref_extraction_with_grep(self):
        """Verify the grep command used in demo.sh correctly extracts the hash."""
        upload_output = _upload_success_output()
        result = subprocess.run(
            ["bash", "-c",
             'echo "$1" | grep -A1 "Swarm Reference Hash:" | tail -1 | tr -d "[:space:]"',
             "--", upload_output],
            capture_output=True, text=True,
        )
        assert result.stdout.strip() == FAKE_HASH


class TestDemoPythonScript:
    """Tests for run_demo.py — mocks subprocess.run to simulate CLI calls."""

    def test_sample_file_exists(self):
        """sample.txt should exist in the demo directory."""
        assert (DEMO_DIR / "sample.txt").exists()

    def test_sample_file_is_not_empty(self):
        """sample.txt should have content."""
        content = (DEMO_DIR / "sample.txt").read_text()
        assert len(content) > 0
        assert "Provenance Record" in content

    def test_python_demo_full_workflow(self, tmp_path, monkeypatch):
        """Test the full Python demo workflow with mocked CLI calls."""
        # Create a sample file
        sample_file = tmp_path / "sample.txt"
        sample_content = b"test provenance data for demo"
        sample_file.write_bytes(sample_content)

        call_count = {"n": 0}

        def mock_subprocess_run(cmd, **kwargs):
            call_count["n"] += 1
            subcmd = _get_cli_subcommand(cmd)

            if subcmd == "health":
                return _make_completed_process(
                    stdout="Backend: gateway\nStatus: Healthy\n"
                )
            elif subcmd == "upload":
                return _make_completed_process(
                    stdout=_upload_success_output()
                )
            elif subcmd == "download":
                # The demo creates downloads/ under SCRIPT_DIR (= tmp_path)
                dl_dir = tmp_path / "downloads"
                dl_dir.mkdir(exist_ok=True)
                (dl_dir / f"{FAKE_HASH}.data").write_bytes(sample_content)
                return _make_completed_process(
                    stdout="Downloaded and verified: sample.txt\n"
                )
            return _make_completed_process(returncode=1, stderr="Unknown command")

        # Import the demo module fresh
        demo_module_path = str(DEMO_DIR / "run_demo.py")
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_demo", demo_module_path)
        run_demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run_demo)

        # Patch subprocess.run inside the loaded demo module's own subprocess ref
        monkeypatch.setattr(run_demo.subprocess, "run", mock_subprocess_run)

        # Override SCRIPT_DIR to use our tmp_path and patch sys.argv
        run_demo.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", ["run_demo.py", "--file", str(sample_file)])

        # Run the demo — if it calls sys.exit(1), it will raise SystemExit
        run_demo.main()

        # Verify all 3 CLI calls were made (health, upload, download)
        assert call_count["n"] == 3

    def test_python_demo_pool_fallback(self, tmp_path, monkeypatch):
        """Demo should fall back to regular stamp purchase when pool fails."""
        sample_file = tmp_path / "sample.txt"
        sample_content = b"fallback test data"
        sample_file.write_bytes(sample_content)

        upload_calls = {"n": 0}

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                upload_calls["n"] += 1
                cmd_str = " ".join(str(c) for c in cmd)
                if "--usePool" in cmd_str:
                    # Pool fails
                    return _make_completed_process(
                        returncode=1, stderr="ERROR: No stamps in pool"
                    )
                else:
                    # Regular purchase succeeds
                    return _make_completed_process(stdout=_upload_success_output())
            elif subcmd == "download":
                dl_dir = tmp_path / "downloads"
                dl_dir.mkdir(exist_ok=True)
                (dl_dir / f"{FAKE_HASH}.data").write_bytes(sample_content)
                return _make_completed_process(stdout="Downloaded.\n")
            return _make_completed_process()

        demo_module_path = str(DEMO_DIR / "run_demo.py")
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_demo_fallback", demo_module_path)
        run_demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run_demo)

        monkeypatch.setattr(run_demo.subprocess, "run", mock_subprocess_run)
        run_demo.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", ["run_demo.py", "--file", str(sample_file)])

        run_demo.main()
        # Both pool attempt and fallback should have been called
        assert upload_calls["n"] == 2

    def test_python_demo_upload_failure(self, tmp_path, monkeypatch):
        """Demo should exit when both pool and regular upload fail."""
        sample_file = tmp_path / "sample.txt"
        sample_file.write_text("test data")

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                return _make_completed_process(
                    returncode=1, stderr="ERROR: No stamps available"
                )
            return _make_completed_process()

        demo_module_path = str(DEMO_DIR / "run_demo.py")
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_demo_fail", demo_module_path)
        run_demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run_demo)

        monkeypatch.setattr(run_demo.subprocess, "run", mock_subprocess_run)
        run_demo.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", ["run_demo.py", "--file", str(sample_file)])

        with pytest.raises(SystemExit) as exc_info:
            run_demo.main()
        assert exc_info.value.code == 1

    def test_python_demo_health_failure(self, tmp_path, monkeypatch):
        """Demo should exit if health check fails."""
        sample_file = tmp_path / "sample.txt"
        sample_file.write_text("test data")

        def mock_subprocess_run(cmd, **kwargs):
            return _make_completed_process(
                returncode=1, stderr="Connection refused"
            )

        demo_module_path = str(DEMO_DIR / "run_demo.py")
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_demo_nohealth", demo_module_path)
        run_demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run_demo)

        monkeypatch.setattr(run_demo.subprocess, "run", mock_subprocess_run)
        run_demo.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", ["run_demo.py", "--file", str(sample_file)])

        with pytest.raises(SystemExit) as exc_info:
            run_demo.main()
        assert exc_info.value.code == 1

    def test_python_demo_hash_mismatch(self, tmp_path, monkeypatch):
        """Demo should exit with code 1 when downloaded file doesn't match."""
        sample_file = tmp_path / "sample.txt"
        sample_file.write_bytes(b"original data")

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                return _make_completed_process(stdout=_upload_success_output())
            elif subcmd == "download":
                # Write DIFFERENT content to simulate corruption
                dl_dir = tmp_path / "downloads"
                dl_dir.mkdir(exist_ok=True)
                (dl_dir / f"{FAKE_HASH}.data").write_bytes(b"corrupted data")
                return _make_completed_process(stdout="Downloaded.\n")
            return _make_completed_process()

        demo_module_path = str(DEMO_DIR / "run_demo.py")
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_demo_mismatch", demo_module_path)
        run_demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run_demo)

        monkeypatch.setattr(run_demo.subprocess, "run", mock_subprocess_run)
        run_demo.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", ["run_demo.py", "--file", str(sample_file)])

        with pytest.raises(SystemExit) as exc_info:
            run_demo.main()
        assert exc_info.value.code == 1

    def test_python_demo_missing_file(self, tmp_path, monkeypatch):
        """Demo should exit if the sample file doesn't exist."""
        demo_module_path = str(DEMO_DIR / "run_demo.py")
        import importlib.util
        spec = importlib.util.spec_from_file_location("run_demo_nofile", demo_module_path)
        run_demo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(run_demo)

        run_demo.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py", "--file", str(tmp_path / "nonexistent.txt")
        ])

        with pytest.raises(SystemExit) as exc_info:
            run_demo.main()
        assert exc_info.value.code == 1


# =============================================================================
# EXAMPLE 02: AUDIT TRAIL TESTS
# =============================================================================


class TestAuditTrailShellScript:
    """Tests for the 02-audit-trail bash demo script."""

    def test_shell_script_is_valid_bash(self):
        result = subprocess.run(
            ["bash", "-n", str(AUDIT_DIR / "demo.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"

    def test_shell_script_is_executable(self):
        assert os.access(str(AUDIT_DIR / "demo.sh"), os.X_OK)

    def test_shell_script_has_shebang(self):
        content = (AUDIT_DIR / "demo.sh").read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_shell_script_uses_strict_mode(self):
        content = (AUDIT_DIR / "demo.sh").read_text()
        assert "set -euo pipefail" in content

    def test_shell_script_uses_audit_std(self):
        content = (AUDIT_DIR / "demo.sh").read_text()
        assert '--std "AUDIT-LOG-V1"' in content


class TestAuditTrailSampleFiles:
    """Tests for audit trail sample JSON files."""

    @pytest.mark.parametrize("filename", [
        "audit_record_001.json",
        "audit_record_002.json",
        "audit_record_003.json",
    ])
    def test_audit_record_exists(self, filename):
        assert (AUDIT_DIR / filename).exists()

    @pytest.mark.parametrize("filename", [
        "audit_record_001.json",
        "audit_record_002.json",
        "audit_record_003.json",
    ])
    def test_audit_record_is_valid_json(self, filename):
        data = json.loads((AUDIT_DIR / filename).read_text())
        assert "event_type" in data
        assert "event_id" in data
        assert "timestamp" in data
        assert "actor" in data
        assert "action" in data
        assert "compliance" in data

    def test_audit_records_have_distinct_event_types(self):
        event_types = set()
        for filename in ["audit_record_001.json", "audit_record_002.json", "audit_record_003.json"]:
            data = json.loads((AUDIT_DIR / filename).read_text())
            event_types.add(data["event_type"])
        assert len(event_types) == 3


class TestAuditTrailPythonDemo:
    """Tests for 02-audit-trail/run_demo.py with mocked CLI."""

    def _load_demo(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "audit_demo", str(AUDIT_DIR / "run_demo.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_full_workflow(self, tmp_path, monkeypatch):
        """Test uploading 3 audit records, downloading and verifying one."""
        # Copy sample files to tmp_path
        for f in ["audit_record_001.json", "audit_record_002.json", "audit_record_003.json"]:
            content = (AUDIT_DIR / f).read_bytes()
            (tmp_path / f).write_bytes(content)

        upload_count = {"n": 0}

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                upload_count["n"] += 1
                # Verify --std flag is present
                cmd_str = " ".join(str(c) for c in cmd)
                assert "AUDIT-LOG-V1" in cmd_str
                return _make_completed_process(stdout=_upload_success_output())
            elif subcmd == "download":
                dl_dir = tmp_path / "downloads"
                dl_dir.mkdir(exist_ok=True)
                # Copy the first audit record as downloaded content
                content = (tmp_path / "audit_record_001.json").read_bytes()
                (dl_dir / f"{FAKE_HASH}.data").write_bytes(content)
                return _make_completed_process(stdout="Downloaded.\n")
            return _make_completed_process()

        mod = self._load_demo()
        monkeypatch.setattr(mod.subprocess, "run", mock_subprocess_run)
        mod.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py", "--records",
            "audit_record_001.json", "audit_record_002.json", "audit_record_003.json"
        ])
        mod.main()
        # Should upload 3 records (pool succeeds)
        assert upload_count["n"] == 3

    def test_pool_fallback(self, tmp_path, monkeypatch):
        """Test fallback when pool is unavailable."""
        (tmp_path / "audit_record_001.json").write_bytes(
            (AUDIT_DIR / "audit_record_001.json").read_bytes()
        )

        upload_calls = {"n": 0}

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                upload_calls["n"] += 1
                cmd_str = " ".join(str(c) for c in cmd)
                if "--usePool" in cmd_str:
                    return _make_completed_process(returncode=1, stderr="No pool")
                return _make_completed_process(stdout=_upload_success_output())
            elif subcmd == "download":
                dl_dir = tmp_path / "downloads"
                dl_dir.mkdir(exist_ok=True)
                (dl_dir / f"{FAKE_HASH}.data").write_bytes(
                    (tmp_path / "audit_record_001.json").read_bytes()
                )
                return _make_completed_process(stdout="Downloaded.\n")
            return _make_completed_process()

        mod = self._load_demo()
        monkeypatch.setattr(mod.subprocess, "run", mock_subprocess_run)
        mod.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py", "--records", "audit_record_001.json"
        ])
        mod.main()
        # Pool fail + fallback = 2 upload calls
        assert upload_calls["n"] == 2

    def test_upload_failure_exits(self, tmp_path, monkeypatch):
        """Test that total upload failure exits with code 1."""
        (tmp_path / "audit_record_001.json").write_text('{"test": true}')

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                return _make_completed_process(returncode=1, stderr="Failed")
            return _make_completed_process()

        mod = self._load_demo()
        monkeypatch.setattr(mod.subprocess, "run", mock_subprocess_run)
        mod.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py", "--records", "audit_record_001.json"
        ])
        with pytest.raises(SystemExit) as exc_info:
            mod.main()
        assert exc_info.value.code == 1

    def test_hash_mismatch_exits(self, tmp_path, monkeypatch):
        """Test that hash mismatch on download exits with code 1."""
        (tmp_path / "audit_record_001.json").write_bytes(b"original content")

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                return _make_completed_process(stdout=_upload_success_output())
            elif subcmd == "download":
                dl_dir = tmp_path / "downloads"
                dl_dir.mkdir(exist_ok=True)
                (dl_dir / f"{FAKE_HASH}.data").write_bytes(b"different content")
                return _make_completed_process(stdout="Downloaded.\n")
            return _make_completed_process()

        mod = self._load_demo()
        monkeypatch.setattr(mod.subprocess, "run", mock_subprocess_run)
        mod.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py", "--records", "audit_record_001.json"
        ])
        with pytest.raises(SystemExit) as exc_info:
            mod.main()
        assert exc_info.value.code == 1


# =============================================================================
# EXAMPLE 03: SCIENTIFIC DATA TESTS
# =============================================================================


class TestScientificDataShellScript:
    """Tests for the 03-scientific-data bash demo script."""

    def test_shell_script_is_valid_bash(self):
        result = subprocess.run(
            ["bash", "-n", str(SCIENCE_DIR / "demo.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"

    def test_shell_script_is_executable(self):
        assert os.access(str(SCIENCE_DIR / "demo.sh"), os.X_OK)

    def test_shell_script_has_shebang(self):
        content = (SCIENCE_DIR / "demo.sh").read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_shell_script_uses_strict_mode(self):
        content = (SCIENCE_DIR / "demo.sh").read_text()
        assert "set -euo pipefail" in content

    def test_shell_script_uses_prov_o_std(self):
        content = (SCIENCE_DIR / "demo.sh").read_text()
        assert '--std "PROV-O"' in content

    def test_shell_script_uses_duration_720(self):
        content = (SCIENCE_DIR / "demo.sh").read_text()
        assert "--duration 720" in content


class TestScientificDataSampleFiles:
    """Tests for scientific data sample files."""

    def test_metadata_exists(self):
        assert (SCIENCE_DIR / "dataset_metadata.json").exists()

    def test_metadata_is_valid_json(self):
        data = json.loads((SCIENCE_DIR / "dataset_metadata.json").read_text())
        assert "title" in data
        assert "experiment" in data
        assert "methodology" in data
        assert data["prov_standard"] == "PROV-O"

    def test_csv_exists(self):
        assert (SCIENCE_DIR / "experiment_results.csv").exists()

    def test_csv_has_correct_structure(self):
        with open(str(SCIENCE_DIR / "experiment_results.csv")) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 8
        expected_cols = {"timestamp", "station_id", "temperature_c", "humidity_pct", "status"}
        assert set(rows[0].keys()) == expected_cols

    def test_csv_has_valid_data(self):
        with open(str(SCIENCE_DIR / "experiment_results.csv")) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        for row in rows:
            float(row["temperature_c"])  # Should not raise
            float(row["humidity_pct"])
            assert row["status"] in ("normal", "warning")


class TestScientificDataPythonDemo:
    """Tests for 03-scientific-data/run_demo.py with mocked CLI."""

    def _load_demo(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "science_demo", str(SCIENCE_DIR / "run_demo.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_full_workflow(self, tmp_path, monkeypatch):
        """Test uploading metadata and CSV, downloading and verifying CSV."""
        # Copy sample files
        for f in ["dataset_metadata.json", "experiment_results.csv"]:
            (tmp_path / f).write_bytes((SCIENCE_DIR / f).read_bytes())

        upload_count = {"n": 0}

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                upload_count["n"] += 1
                cmd_str = " ".join(str(c) for c in cmd)
                assert "PROV-O" in cmd_str
                return _make_completed_process(stdout=_upload_success_output())
            elif subcmd == "download":
                dl_dir = tmp_path / "downloads"
                dl_dir.mkdir(exist_ok=True)
                (dl_dir / f"{FAKE_HASH}.data").write_bytes(
                    (tmp_path / "experiment_results.csv").read_bytes()
                )
                return _make_completed_process(stdout="Downloaded.\n")
            return _make_completed_process()

        mod = self._load_demo()
        monkeypatch.setattr(mod.subprocess, "run", mock_subprocess_run)
        mod.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py",
            "--metadata", str(tmp_path / "dataset_metadata.json"),
            "--results", str(tmp_path / "experiment_results.csv"),
        ])
        mod.main()
        # metadata upload + CSV upload = 2 uploads (pool succeeds both times)
        assert upload_count["n"] == 2

    def test_duration_fallback(self, tmp_path, monkeypatch):
        """Test that upload falls back when duration 720 is not available."""
        for f in ["dataset_metadata.json", "experiment_results.csv"]:
            (tmp_path / f).write_bytes((SCIENCE_DIR / f).read_bytes())

        upload_attempts = {"n": 0}

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                upload_attempts["n"] += 1
                cmd_str = " ".join(str(c) for c in cmd)
                if "--duration" in cmd_str:
                    return _make_completed_process(returncode=1, stderr="Duration not available")
                return _make_completed_process(stdout=_upload_success_output())
            elif subcmd == "download":
                dl_dir = tmp_path / "downloads"
                dl_dir.mkdir(exist_ok=True)
                (dl_dir / f"{FAKE_HASH}.data").write_bytes(
                    (tmp_path / "experiment_results.csv").read_bytes()
                )
                return _make_completed_process(stdout="Downloaded.\n")
            return _make_completed_process()

        mod = self._load_demo()
        monkeypatch.setattr(mod.subprocess, "run", mock_subprocess_run)
        mod.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py",
            "--metadata", str(tmp_path / "dataset_metadata.json"),
            "--results", str(tmp_path / "experiment_results.csv"),
        ])
        mod.main()
        # Duration attempts fail (pool + no-pool), then fallback without duration succeeds
        assert upload_attempts["n"] >= 3

    def test_missing_file_exits(self, tmp_path, monkeypatch):
        """Test exit when metadata file doesn't exist."""
        mod = self._load_demo()
        mod.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py",
            "--metadata", str(tmp_path / "nonexistent.json"),
            "--results", str(tmp_path / "also_missing.csv"),
        ])
        with pytest.raises(SystemExit) as exc_info:
            mod.main()
        assert exc_info.value.code == 1


# =============================================================================
# EXAMPLE 05: ENCRYPTED DATA TESTS
# =============================================================================


class TestEncryptedDataShellScript:
    """Tests for the 05-encrypted-data bash demo script."""

    def test_shell_script_is_valid_bash(self):
        result = subprocess.run(
            ["bash", "-n", str(ENCRYPTED_DIR / "demo.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"

    def test_shell_script_is_executable(self):
        assert os.access(str(ENCRYPTED_DIR / "demo.sh"), os.X_OK)

    def test_shell_script_has_shebang(self):
        content = (ENCRYPTED_DIR / "demo.sh").read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_shell_script_uses_strict_mode(self):
        content = (ENCRYPTED_DIR / "demo.sh").read_text()
        assert "set -euo pipefail" in content

    def test_shell_script_uses_enc_flag(self):
        content = (ENCRYPTED_DIR / "demo.sh").read_text()
        assert '--enc "AES-256-GCM"' in content


class TestEncryptedDataSampleFiles:
    """Tests for encrypted data sample files."""

    def test_sensitive_data_exists(self):
        assert (ENCRYPTED_DIR / "sensitive_data.txt").exists()

    def test_sensitive_data_has_content(self):
        content = (ENCRYPTED_DIR / "sensitive_data.txt").read_text()
        assert len(content) > 0
        assert "Patient" in content or "CONFIDENTIAL" in content


class TestEncryptedDataPythonDemo:
    """Tests for 05-encrypted-data/run_demo.py with mocked CLI."""

    def _load_demo(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "encrypted_demo", str(ENCRYPTED_DIR / "run_demo.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_xor_encrypt_decrypt_roundtrip(self):
        """XOR cipher should be symmetric."""
        mod = self._load_demo()
        original = b"Hello, this is sensitive data!"
        key = os.urandom(32)
        encrypted = mod.xor_encrypt(original, key)
        assert encrypted != original
        decrypted = mod.xor_encrypt(encrypted, key)
        assert decrypted == original

    def test_xor_encrypt_different_with_different_key(self):
        """Different keys should produce different ciphertext."""
        mod = self._load_demo()
        original = b"Same plaintext"
        encrypted1 = mod.xor_encrypt(original, b"key1" * 8)
        encrypted2 = mod.xor_encrypt(original, b"key2" * 8)
        assert encrypted1 != encrypted2

    def test_full_workflow(self, tmp_path, monkeypatch):
        """Test encrypt, upload, download, verify, decrypt workflow."""
        sample_content = b"Sensitive patient record data"
        sample_file = tmp_path / "sensitive_data.txt"
        sample_file.write_bytes(sample_content)

        # Track what encrypted content was uploaded
        uploaded_content = {}

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                cmd_str = " ".join(str(c) for c in cmd)
                assert "AES-256-GCM" in cmd_str
                # Read the encrypted file that was uploaded
                for i, c in enumerate(cmd):
                    if str(c) == "--file" and i + 1 < len(cmd):
                        uploaded_content["data"] = Path(cmd[i + 1]).read_bytes()
                return _make_completed_process(stdout=_upload_success_output())
            elif subcmd == "download":
                dl_dir = tmp_path / "downloads"
                dl_dir.mkdir(exist_ok=True)
                # Return the encrypted content
                (dl_dir / f"{FAKE_HASH}.data").write_bytes(
                    uploaded_content.get("data", b"")
                )
                return _make_completed_process(stdout="Downloaded.\n")
            return _make_completed_process()

        mod = self._load_demo()
        monkeypatch.setattr(mod.subprocess, "run", mock_subprocess_run)
        mod.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py", "--file", str(sample_file)
        ])
        mod.main()

    def test_upload_failure_exits(self, tmp_path, monkeypatch):
        """Test exit when upload fails."""
        sample_file = tmp_path / "sensitive_data.txt"
        sample_file.write_bytes(b"test data")

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                return _make_completed_process(returncode=1, stderr="Failed")
            return _make_completed_process()

        mod = self._load_demo()
        monkeypatch.setattr(mod.subprocess, "run", mock_subprocess_run)
        mod.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py", "--file", str(sample_file)
        ])
        with pytest.raises(SystemExit) as exc_info:
            mod.main()
        assert exc_info.value.code == 1

    def test_encrypted_payload_mismatch_exits(self, tmp_path, monkeypatch):
        """Test exit when downloaded encrypted payload doesn't match."""
        sample_file = tmp_path / "sensitive_data.txt"
        sample_file.write_bytes(b"test data")

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                return _make_completed_process(stdout=_upload_success_output())
            elif subcmd == "download":
                dl_dir = tmp_path / "downloads"
                dl_dir.mkdir(exist_ok=True)
                (dl_dir / f"{FAKE_HASH}.data").write_bytes(b"corrupted data")
                return _make_completed_process(stdout="Downloaded.\n")
            return _make_completed_process()

        mod = self._load_demo()
        monkeypatch.setattr(mod.subprocess, "run", mock_subprocess_run)
        mod.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py", "--file", str(sample_file)
        ])
        with pytest.raises(SystemExit) as exc_info:
            mod.main()
        assert exc_info.value.code == 1

    def test_missing_file_exits(self, tmp_path, monkeypatch):
        """Test exit when input file doesn't exist."""
        mod = self._load_demo()
        mod.SCRIPT_DIR = tmp_path
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py", "--file", str(tmp_path / "nonexistent.txt")
        ])
        with pytest.raises(SystemExit) as exc_info:
            mod.main()
        assert exc_info.value.code == 1


# =============================================================================
# EXAMPLE 06: MARKET MEMORY TESTS
# =============================================================================


class TestMarketMemoryShellScript:
    """Tests for the 06-market-memory bash demo script."""

    def test_shell_script_is_valid_bash(self):
        result = subprocess.run(
            ["bash", "-n", str(MARKET_DIR / "demo.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Bash syntax error: {result.stderr}"

    def test_shell_script_is_executable(self):
        assert os.access(str(MARKET_DIR / "demo.sh"), os.X_OK)

    def test_shell_script_has_shebang(self):
        content = (MARKET_DIR / "demo.sh").read_text()
        assert content.startswith("#!/usr/bin/env bash")

    def test_shell_script_uses_strict_mode(self):
        content = (MARKET_DIR / "demo.sh").read_text()
        assert "set -euo pipefail" in content

    def test_shell_script_uses_market_memory_std(self):
        content = (MARKET_DIR / "demo.sh").read_text()
        assert '--std "MARKET-MEMORY-V1"' in content


class TestMarketMemorySampleFiles:
    """Tests for market memory sample JSON files."""

    def test_prediction_exists(self):
        assert (MARKET_DIR / "prediction_001.json").exists()

    def test_observation_exists(self):
        assert (MARKET_DIR / "observation_001.json").exists()

    def test_create_memory_unit_exists(self):
        assert (MARKET_DIR / "create_memory_unit.py").exists()

    def test_prediction_is_valid_json(self):
        data = json.loads((MARKET_DIR / "prediction_001.json").read_text())
        assert data["type"] == "prediction"
        assert data["version"] == "1.0"
        assert "agent_id" in data
        assert "market" in data
        assert "prediction" in data
        assert "content_hash" in data

    def test_observation_is_valid_json(self):
        data = json.loads((MARKET_DIR / "observation_001.json").read_text())
        assert data["type"] == "observation"
        assert data["version"] == "1.0"
        assert "prediction_ref" in data
        assert "observation" in data
        assert "content_hash" in data

    def test_prediction_has_valid_canonical_hash(self):
        """The pre-computed content_hash should match the canonical hash."""
        data = json.loads((MARKET_DIR / "prediction_001.json").read_text())
        hashable = {k: v for k, v in data.items() if k != "content_hash"}
        canonical = json.dumps(hashable, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert data["content_hash"] == expected

    def test_observation_has_valid_canonical_hash(self):
        """The pre-computed content_hash should match the canonical hash."""
        data = json.loads((MARKET_DIR / "observation_001.json").read_text())
        hashable = {k: v for k, v in data.items() if k != "content_hash"}
        canonical = json.dumps(hashable, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        assert data["content_hash"] == expected


class TestMarketMemoryCreateUnit:
    """Tests for create_memory_unit.py canonical hashing functions."""

    def _load_module(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "create_memory_unit", str(MARKET_DIR / "create_memory_unit.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_canonical_hash_deterministic(self):
        """Same data should always produce the same hash."""
        mod = self._load_module()
        data = {"b": 2, "a": 1, "c": 3}
        assert mod.canonical_hash(data) == mod.canonical_hash(data)

    def test_canonical_hash_ignores_key_order(self):
        """Hash should be the same regardless of dict key order."""
        mod = self._load_module()
        data1 = {"a": 1, "b": 2}
        data2 = {"b": 2, "a": 1}
        assert mod.canonical_hash(data1) == mod.canonical_hash(data2)

    def test_canonical_hash_excludes_content_hash(self):
        """content_hash field should be excluded from hash computation."""
        mod = self._load_module()
        data_without = {"a": 1, "b": 2}
        data_with = {"a": 1, "b": 2, "content_hash": "should_be_excluded"}
        assert mod.canonical_hash(data_without) == mod.canonical_hash(data_with)

    def test_verify_hash_valid(self):
        """verify_hash should return True for correctly hashed data."""
        mod = self._load_module()
        data = {"type": "test", "value": 42}
        data["content_hash"] = mod.canonical_hash(data)
        assert mod.verify_hash(data) is True

    def test_verify_hash_invalid(self):
        """verify_hash should return False for tampered data."""
        mod = self._load_module()
        data = {"type": "test", "value": 42}
        data["content_hash"] = "0000000000000000000000000000000000000000000000000000000000000000"
        assert mod.verify_hash(data) is False

    def test_create_prediction(self):
        """create_prediction should return a valid unit with content_hash."""
        mod = self._load_module()
        pred = mod.create_prediction("agent-test", "ETH/USD", "down", 0.80, 12)
        assert pred["type"] == "prediction"
        assert pred["agent_id"] == "agent-test"
        assert pred["market"] == "ETH/USD"
        assert pred["prediction"]["direction"] == "down"
        assert "content_hash" in pred
        assert mod.verify_hash(pred) is True

    def test_create_observation(self):
        """create_observation should return a valid unit linking to prediction."""
        mod = self._load_module()
        obs = mod.create_observation(
            "agent-test", "ETH/USD", "abc123" * 11,
            "incorrect", "down", -1.5
        )
        assert obs["type"] == "observation"
        assert obs["prediction_ref"] == "abc123" * 11
        assert obs["observation"]["outcome"] == "incorrect"
        assert "content_hash" in obs
        assert mod.verify_hash(obs) is True

    def test_verify_sample_prediction(self):
        """Verify the shipped prediction_001.json with the module."""
        mod = self._load_module()
        data = json.loads((MARKET_DIR / "prediction_001.json").read_text())
        assert mod.verify_hash(data) is True

    def test_verify_sample_observation(self):
        """Verify the shipped observation_001.json with the module."""
        mod = self._load_module()
        data = json.loads((MARKET_DIR / "observation_001.json").read_text())
        assert mod.verify_hash(data) is True


class TestMarketMemoryPythonDemo:
    """Tests for 06-market-memory/run_demo.py with mocked CLI."""

    def _load_demo(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "market_demo", str(MARKET_DIR / "run_demo.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_full_workflow(self, tmp_path, monkeypatch):
        """Test prediction upload, observation upload, download and verify."""
        # Copy sample files
        for f in ["prediction_001.json", "observation_001.json", "create_memory_unit.py"]:
            (tmp_path / f).write_bytes((MARKET_DIR / f).read_bytes())

        upload_count = {"n": 0}

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                upload_count["n"] += 1
                cmd_str = " ".join(str(c) for c in cmd)
                assert "MARKET-MEMORY-V1" in cmd_str
                return _make_completed_process(stdout=_upload_success_output())
            elif subcmd == "download":
                dl_dir = tmp_path / "downloads"
                dl_dir.mkdir(exist_ok=True)
                (dl_dir / f"{FAKE_HASH}.data").write_bytes(
                    (tmp_path / "prediction_001.json").read_bytes()
                )
                return _make_completed_process(stdout="Downloaded.\n")
            return _make_completed_process()

        mod = self._load_demo()
        monkeypatch.setattr(mod.subprocess, "run", mock_subprocess_run)
        mod.SCRIPT_DIR = tmp_path
        # Also patch sys.path so the import of create_memory_unit works from tmp_path
        monkeypatch.syspath_prepend(str(tmp_path))
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py", "--prediction", str(tmp_path / "prediction_001.json")
        ])
        mod.main()
        # prediction + observation = 2 uploads
        assert upload_count["n"] == 2

    def test_upload_failure_exits(self, tmp_path, monkeypatch):
        """Test exit when prediction upload fails."""
        for f in ["prediction_001.json", "observation_001.json", "create_memory_unit.py"]:
            (tmp_path / f).write_bytes((MARKET_DIR / f).read_bytes())

        def mock_subprocess_run(cmd, **kwargs):
            subcmd = _get_cli_subcommand(cmd)
            if subcmd == "health":
                return _make_completed_process(stdout="Healthy\n")
            elif subcmd == "upload":
                return _make_completed_process(returncode=1, stderr="Failed")
            return _make_completed_process()

        mod = self._load_demo()
        monkeypatch.setattr(mod.subprocess, "run", mock_subprocess_run)
        mod.SCRIPT_DIR = tmp_path
        monkeypatch.syspath_prepend(str(tmp_path))
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py", "--prediction", str(tmp_path / "prediction_001.json")
        ])
        with pytest.raises(SystemExit) as exc_info:
            mod.main()
        assert exc_info.value.code == 1

    def test_missing_prediction_file_exits(self, tmp_path, monkeypatch):
        """Test exit when prediction file doesn't exist."""
        # Copy create_memory_unit.py so import works
        (tmp_path / "create_memory_unit.py").write_bytes(
            (MARKET_DIR / "create_memory_unit.py").read_bytes()
        )
        mod = self._load_demo()
        mod.SCRIPT_DIR = tmp_path
        monkeypatch.syspath_prepend(str(tmp_path))
        monkeypatch.setattr(sys, "argv", [
            "run_demo.py", "--prediction", str(tmp_path / "nonexistent.json")
        ])
        with pytest.raises(SystemExit) as exc_info:
            mod.main()
        assert exc_info.value.code == 1


# =============================================================================
# GATEWAY INTEGRATION TESTS — run actual demos
# =============================================================================

def _can_upload_to_gateway():
    """Check if we can actually upload via the gateway.

    Verifies:
    1. Gateway is reachable
    2. Stamp pool has available stamps (so upload will work)
    3. The venv CLI is installed with --usePool support
    """
    try:
        import requests
        url = os.getenv("PROVENANCE_GATEWAY_URL", "https://provenance-gateway.datafund.io")
        resp = requests.get(f"{url}/", timeout=5)
        if resp.status_code != 200:
            return False

        # Check stamp pool availability via the gateway API
        pool_resp = requests.get(f"{url}/api/v1/stamps/pool/status", timeout=5)
        if pool_resp.status_code != 200:
            return False
        pool_data = pool_resp.json()
        if not pool_data.get("enabled") or pool_data.get("available", 0) < 1:
            return False

        # Verify the CLI has --usePool
        cli = _venv_cli_path()
        if not cli:
            return False
        result = subprocess.run(
            [cli, "upload", "--help"], capture_output=True, text=True, timeout=10
        )
        return "--usePool" in result.stdout
    except Exception:
        return False


def _venv_cli_path():
    """Return path to the venv CLI binary, or None if not found."""
    venv_cli = Path(__file__).parent.parent / ".venv" / "bin" / "swarm-prov-upload"
    if venv_cli.exists():
        return str(venv_cli)
    # Fall back to system PATH
    cli = shutil.which("swarm-prov-upload")
    return cli


skip_if_no_gateway_upload = pytest.mark.skipif(
    not _can_upload_to_gateway(),
    reason="Gateway not available or CLI not installed with --usePool support"
)


@pytest.mark.integration
@pytest.mark.gateway
class TestDemoIntegration:
    """Integration tests that run the actual demos against a live gateway.

    These require:
    - Running gateway with stamp pool or x402 configured
    - The venv CLI installed (with --usePool support)

    Skipped automatically when prerequisites aren't met.
    """

    @skip_if_no_gateway_upload
    def test_python_demo_e2e(self):
        """Run run_demo.py end-to-end against the live gateway."""
        cli_path = _venv_cli_path()
        venv_python = str(Path(__file__).parent.parent / ".venv" / "bin" / "python3")
        env = os.environ.copy()
        # Ensure the venv CLI is first on PATH
        env["PATH"] = str(Path(cli_path).parent) + ":" + env.get("PATH", "")

        result = subprocess.run(
            [venv_python, str(DEMO_DIR / "run_demo.py")],
            capture_output=True, text=True,
            timeout=300,
            env=env,
        )
        assert result.returncode == 0, (
            f"Python demo failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout

    @skip_if_no_gateway_upload
    def test_shell_demo_e2e(self):
        """Run demo.sh end-to-end against the live gateway."""
        cli_path = _venv_cli_path()
        env = os.environ.copy()
        env["PATH"] = str(Path(cli_path).parent) + ":" + env.get("PATH", "")

        result = subprocess.run(
            ["bash", str(DEMO_DIR / "demo.sh")],
            capture_output=True, text=True,
            timeout=300,
            env=env,
        )
        assert result.returncode == 0, (
            f"Shell demo failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout


@pytest.mark.integration
@pytest.mark.gateway
class TestAuditTrailIntegration:
    """Integration tests for 02-audit-trail demos."""

    @skip_if_no_gateway_upload
    def test_python_demo_e2e(self):
        cli_path = _venv_cli_path()
        venv_python = str(Path(__file__).parent.parent / ".venv" / "bin" / "python3")
        env = os.environ.copy()
        env["PATH"] = str(Path(cli_path).parent) + ":" + env.get("PATH", "")

        result = subprocess.run(
            [venv_python, str(AUDIT_DIR / "run_demo.py")],
            capture_output=True, text=True,
            timeout=300,
            env=env,
        )
        assert result.returncode == 0, (
            f"Audit trail demo failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout

    @skip_if_no_gateway_upload
    def test_shell_demo_e2e(self):
        cli_path = _venv_cli_path()
        env = os.environ.copy()
        env["PATH"] = str(Path(cli_path).parent) + ":" + env.get("PATH", "")

        result = subprocess.run(
            ["bash", str(AUDIT_DIR / "demo.sh")],
            capture_output=True, text=True,
            timeout=300,
            env=env,
        )
        assert result.returncode == 0, (
            f"Audit trail shell demo failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout


@pytest.mark.integration
@pytest.mark.gateway
class TestScientificDataIntegration:
    """Integration tests for 03-scientific-data demos."""

    @skip_if_no_gateway_upload
    def test_python_demo_e2e(self):
        cli_path = _venv_cli_path()
        venv_python = str(Path(__file__).parent.parent / ".venv" / "bin" / "python3")
        env = os.environ.copy()
        env["PATH"] = str(Path(cli_path).parent) + ":" + env.get("PATH", "")

        result = subprocess.run(
            [venv_python, str(SCIENCE_DIR / "run_demo.py")],
            capture_output=True, text=True,
            timeout=300,
            env=env,
        )
        assert result.returncode == 0, (
            f"Scientific data demo failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout

    @skip_if_no_gateway_upload
    def test_shell_demo_e2e(self):
        cli_path = _venv_cli_path()
        env = os.environ.copy()
        env["PATH"] = str(Path(cli_path).parent) + ":" + env.get("PATH", "")

        result = subprocess.run(
            ["bash", str(SCIENCE_DIR / "demo.sh")],
            capture_output=True, text=True,
            timeout=300,
            env=env,
        )
        assert result.returncode == 0, (
            f"Scientific data shell demo failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout


@pytest.mark.integration
@pytest.mark.gateway
class TestEncryptedDataIntegration:
    """Integration tests for 05-encrypted-data demos."""

    @skip_if_no_gateway_upload
    def test_python_demo_e2e(self):
        cli_path = _venv_cli_path()
        venv_python = str(Path(__file__).parent.parent / ".venv" / "bin" / "python3")
        env = os.environ.copy()
        env["PATH"] = str(Path(cli_path).parent) + ":" + env.get("PATH", "")

        result = subprocess.run(
            [venv_python, str(ENCRYPTED_DIR / "run_demo.py")],
            capture_output=True, text=True,
            timeout=300,
            env=env,
        )
        assert result.returncode == 0, (
            f"Encrypted data demo failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout

    @skip_if_no_gateway_upload
    def test_shell_demo_e2e(self):
        cli_path = _venv_cli_path()
        env = os.environ.copy()
        env["PATH"] = str(Path(cli_path).parent) + ":" + env.get("PATH", "")

        result = subprocess.run(
            ["bash", str(ENCRYPTED_DIR / "demo.sh")],
            capture_output=True, text=True,
            timeout=300,
            env=env,
        )
        assert result.returncode == 0, (
            f"Encrypted data shell demo failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout


@pytest.mark.integration
@pytest.mark.gateway
class TestMarketMemoryIntegration:
    """Integration tests for 06-market-memory demos."""

    @skip_if_no_gateway_upload
    def test_python_demo_e2e(self):
        cli_path = _venv_cli_path()
        venv_python = str(Path(__file__).parent.parent / ".venv" / "bin" / "python3")
        env = os.environ.copy()
        env["PATH"] = str(Path(cli_path).parent) + ":" + env.get("PATH", "")

        result = subprocess.run(
            [venv_python, str(MARKET_DIR / "run_demo.py")],
            capture_output=True, text=True,
            timeout=300,
            env=env,
        )
        assert result.returncode == 0, (
            f"Market memory demo failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout

    @skip_if_no_gateway_upload
    def test_shell_demo_e2e(self):
        cli_path = _venv_cli_path()
        env = os.environ.copy()
        env["PATH"] = str(Path(cli_path).parent) + ":" + env.get("PATH", "")

        result = subprocess.run(
            ["bash", str(MARKET_DIR / "demo.sh")],
            capture_output=True, text=True,
            timeout=300,
            env=env,
        )
        assert result.returncode == 0, (
            f"Market memory shell demo failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "PASS" in result.stdout
