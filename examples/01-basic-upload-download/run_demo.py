#!/usr/bin/env python3
"""
Basic Upload/Download Demo - Python Version

Demonstrates the core Swarm Provenance workflow programmatically:
1. Upload a file to Swarm via the CLI
2. Download it back
3. Verify data integrity by comparing SHA-256 hashes

Usage:
    python run_demo.py
    python run_demo.py --file /path/to/custom/file.txt
"""

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def sha256_file(path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cli(*args) -> subprocess.CompletedProcess:
    """Run a swarm-prov-upload CLI command."""
    cmd = ["swarm-prov-upload"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


def main():
    parser = argparse.ArgumentParser(description="Basic upload/download demo")
    parser.add_argument(
        "--file", "-f",
        default=str(SCRIPT_DIR / "sample.txt"),
        help="File to upload (default: sample.txt)",
    )
    args = parser.parse_args()

    sample_file = args.file
    if not os.path.exists(sample_file):
        print(f"ERROR: File not found: {sample_file}")
        sys.exit(1)

    print("=" * 50)
    print("  Swarm Provenance CLI - Basic Demo (Python)")
    print("=" * 50)

    # --- Step 1: Check health ---
    print("\n--- Step 1: Check gateway health ---")
    result = run_cli("health")
    if result.returncode != 0:
        print(f"Gateway not available: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    # --- Step 2: Upload ---
    print("\n--- Step 2: Upload file ---")
    file_size = os.path.getsize(sample_file)
    original_hash = sha256_file(sample_file)
    print(f"File:   {sample_file}")
    print(f"Size:   {file_size} bytes")
    print(f"SHA256: {original_hash}")

    print("\nUploading with --usePool...")
    result = run_cli("upload", "--file", sample_file, "--usePool")
    if result.returncode != 0:
        print(f"Upload failed: {result.stderr or result.stdout}")
        sys.exit(1)

    output = result.stdout
    print(output.strip())

    # Extract Swarm reference from text output
    # The CLI prints: "Swarm Reference Hash:\n<hash>"
    swarm_ref = ""
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if "Swarm Reference Hash:" in line and i + 1 < len(lines):
            swarm_ref = lines[i + 1].strip()
            break

    if not swarm_ref or len(swarm_ref) < 64:
        print(f"Could not extract Swarm reference from output")
        sys.exit(1)

    print(f"\nSwarm Reference: {swarm_ref}")

    # --- Step 3: Download ---
    print("\n--- Step 3: Download and verify ---")
    download_dir = str(SCRIPT_DIR / "downloads")
    os.makedirs(download_dir, exist_ok=True)

    # Clean previous downloads
    for f in os.listdir(download_dir):
        os.remove(os.path.join(download_dir, f))

    result = run_cli("download", swarm_ref, "--output-dir", download_dir)
    if result.returncode != 0:
        print(f"Download failed: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    # --- Step 4: Verify ---
    print("\n--- Step 4: Verify integrity ---")
    downloaded_files = os.listdir(download_dir)
    if not downloaded_files:
        print("ERROR: No files in download directory")
        sys.exit(1)

    downloaded_file = os.path.join(download_dir, downloaded_files[0])
    downloaded_hash = sha256_file(downloaded_file)

    print(f"Original:   {original_hash}")
    print(f"Downloaded: {downloaded_hash}")

    if original_hash == downloaded_hash:
        print("\nPASS: Data integrity verified - hashes match.")
    else:
        print("\nFAIL: Hash mismatch - data may have been tampered with!")
        sys.exit(1)

    # --- Summary ---
    print("\n--- Summary ---")
    print(f"Swarm Reference: {swarm_ref}")
    print(f"File Size:       {file_size} bytes")
    print(f"SHA-256:         {original_hash}")
    print("Use the Swarm reference to retrieve this data from any Swarm gateway.")


if __name__ == "__main__":
    main()
