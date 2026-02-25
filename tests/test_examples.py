"""Tests for examples common utilities and demo scripts.

Unit tests verify:
- sample_generator: text, JSON, CSV file generation
- verify: SHA-256 hashing, file comparison, CLI output parsing
- demo workflow: full upload/download/verify cycle with mocked CLI

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
                (dl_dir / "sample.txt").write_bytes(sample_content)
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

    def test_python_demo_upload_failure(self, tmp_path, monkeypatch):
        """Demo should exit on upload failure."""
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
                (dl_dir / "sample.txt").write_bytes(b"corrupted data")
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
