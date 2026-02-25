"""
Verification helpers for example scripts.

Provides functions to download data from Swarm, verify integrity via
SHA-256 hash comparison, and print verification reports.

Usage:
    from common.verify import verify_download, compare_hashes
"""

import base64
import hashlib
import json
import subprocess
import sys


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def compare_hashes(original_file: str, downloaded_file: str) -> bool:
    """
    Compare SHA-256 hashes of two files.

    Args:
        original_file: Path to the original file.
        downloaded_file: Path to the downloaded file.

    Returns:
        True if hashes match.
    """
    with open(original_file, "rb") as f:
        original_hash = compute_sha256(f.read())
    with open(downloaded_file, "rb") as f:
        downloaded_hash = compute_sha256(f.read())

    match = original_hash == downloaded_hash
    print(f"Original SHA-256:   {original_hash}")
    print(f"Downloaded SHA-256: {downloaded_hash}")
    print(f"Match: {'YES' if match else 'NO - DATA INTEGRITY FAILURE'}")
    return match


def verify_download(swarm_ref: str, original_file: str, output_dir: str = None) -> bool:
    """
    Download data from Swarm and verify against the original file.

    Uses the CLI to download, then compares SHA-256 hashes.

    Args:
        swarm_ref: Swarm reference hash from upload.
        original_file: Path to the original file for comparison.
        output_dir: Directory to save downloaded file. Defaults to './downloads'.

    Returns:
        True if verification passes.
    """
    if output_dir is None:
        output_dir = "./downloads"

    print(f"\nDownloading {swarm_ref[:16]}...")
    result = subprocess.run(
        ["swarm-prov-upload", "download", swarm_ref, "--output-dir", output_dir],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Download failed: {result.stderr or result.stdout}")
        return False

    print(result.stdout)

    # Find the downloaded file (CLI saves to output_dir/<filename>)
    import os
    downloaded_files = os.listdir(output_dir)
    if not downloaded_files:
        print("No files found in download directory")
        return False

    # Use the most recently modified file
    downloaded_path = os.path.join(
        output_dir,
        max(downloaded_files, key=lambda f: os.path.getmtime(os.path.join(output_dir, f))),
    )

    print(f"\nVerifying integrity...")
    return compare_hashes(original_file, downloaded_path)


def parse_upload_output(output: str) -> dict:
    """
    Parse CLI upload output to extract the Swarm reference and metadata.

    Handles both JSON (--json flag) and text output formats.

    Args:
        output: Raw CLI stdout from an upload command.

    Returns:
        Dict with 'reference' key (and other fields if JSON).
    """
    # Try JSON first
    try:
        return json.loads(output)
    except (json.JSONDecodeError, ValueError):
        pass

    # Parse text output — look for "Swarm Reference:" or "Reference:" lines
    result = {}
    for line in output.splitlines():
        line = line.strip()
        if "reference" in line.lower() and ":" in line:
            result["reference"] = line.split(":", 1)[1].strip()
        elif "hash" in line.lower() and ":" in line and "reference" not in result:
            result["reference"] = line.split(":", 1)[1].strip()
        elif "stamp" in line.lower() and "id" in line.lower() and ":" in line:
            result["stamp_id"] = line.split(":", 1)[1].strip()

    return result
