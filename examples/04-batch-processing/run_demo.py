#!/usr/bin/env python3
"""
Batch Processing Demo - Python Version

Demonstrates uploading multiple files with stamp reuse:
1. Upload first file with --size medium -v to capture stamp ID
2. Upload remaining files with --stamp-id (reuses stamp, skips purchase)
3. Build a manifest of all uploaded files
4. Download and verify one file

Usage:
    python run_demo.py
    python run_demo.py --files log_entry_001.json log_entry_002.json log_entry_003.json
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

DEFAULT_FILES = [
    "sample_files/log_entry_001.json",
    "sample_files/log_entry_002.json",
    "sample_files/log_entry_003.json",
]


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


def extract_swarm_ref(output: str) -> str:
    """Extract Swarm reference hash from CLI output."""
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if "Swarm Reference Hash:" in line and i + 1 < len(lines):
            ref = lines[i + 1].strip()
            if len(ref) >= 64:
                return ref
    return ""


def extract_stamp_id(output: str) -> str:
    """Extract stamp ID from verbose CLI output."""
    for line in output.splitlines():
        if "Stamp ID Received:" in line:
            parts = line.split("Stamp ID Received:")
            if len(parts) > 1:
                stamp_id = parts[1].strip()
                if len(stamp_id) >= 16:
                    return stamp_id
    return ""


def main():
    parser = argparse.ArgumentParser(description="Batch processing demo")
    parser.add_argument(
        "--files", "-f",
        nargs="+",
        default=DEFAULT_FILES,
        help="Files to upload (default: 3 sample log entries)",
    )
    args = parser.parse_args()

    print("=" * 50)
    print("  Swarm Provenance CLI - Batch Upload (Python)")
    print("=" * 50)

    # --- Step 1: Check health ---
    print("\n--- Step 1: Check gateway health ---")
    result = run_cli("health")
    if result.returncode != 0:
        print(f"Gateway not available: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    # Verify all files exist
    for file_rel in args.files:
        file_path = str(SCRIPT_DIR / file_rel)
        if not os.path.exists(file_path):
            print(f"ERROR: File not found: {file_path}")
            sys.exit(1)

    # --- Step 2: Upload first file with verbose to capture stamp ---
    print("\n--- Step 2: Upload first file with --size medium -v ---")
    first_file = str(SCRIPT_DIR / args.files[0])
    first_name = os.path.basename(args.files[0])
    original_hash = sha256_file(first_file)
    print(f"Uploading: {first_name}")
    print(f"  SHA256: {original_hash}")

    result = run_cli("upload", "--file", first_file, "--size", "medium", "-v", "--usePool")
    if result.returncode != 0:
        print("  Pool not available, falling back to regular stamp purchase...")
        result = run_cli("upload", "--file", first_file, "--size", "medium", "-v")
        if result.returncode != 0:
            print(f"  Upload failed: {result.stderr or result.stdout}")
            sys.exit(1)

    first_ref = extract_swarm_ref(result.stdout)
    if not first_ref:
        print("  Could not extract Swarm reference from output")
        sys.exit(1)

    combined_output = result.stdout + "\n" + result.stderr
    stamp_id = extract_stamp_id(combined_output)
    if stamp_id:
        print(f"  Stamp ID captured: {stamp_id[:16]}...")
    else:
        print("  WARNING: Could not extract stamp ID from verbose output")

    print(f"  Reference: {first_ref}")

    manifest = {first_name: first_ref}

    # --- Step 3: Upload remaining files with stamp reuse ---
    print("\n--- Step 3: Upload remaining files with stamp reuse ---")
    for file_rel in args.files[1:]:
        file_path = str(SCRIPT_DIR / file_rel)
        filename = os.path.basename(file_rel)
        print(f"\nUploading: {filename}")
        print(f"  SHA256: {sha256_file(file_path)}")

        if stamp_id:
            print("  (reusing stamp)")
            result = run_cli("upload", "--file", file_path, "--stamp-id", stamp_id)
        else:
            result = run_cli("upload", "--file", file_path, "--usePool")
            if result.returncode != 0:
                print("  Pool not available, falling back to regular stamp purchase...")
                result = run_cli("upload", "--file", file_path)

        if result.returncode != 0:
            print(f"  Upload failed: {result.stderr or result.stdout}")
            sys.exit(1)

        swarm_ref = extract_swarm_ref(result.stdout)
        if not swarm_ref:
            print("  Could not extract Swarm reference")
            sys.exit(1)

        manifest[filename] = swarm_ref
        print(f"  Reference: {swarm_ref}")

    print(f"\nAll {len(manifest)} files uploaded.")

    # --- Step 4: Build manifest ---
    print("\n--- Step 4: Build manifest ---")
    manifest_path = str(SCRIPT_DIR / "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Manifest saved: {manifest_path}")
    print(json.dumps(manifest, indent=2))

    # --- Step 5: Download and verify first file ---
    print(f"\n--- Step 5: Download and verify {first_name} ---")
    download_dir = str(SCRIPT_DIR / "downloads")
    os.makedirs(download_dir, exist_ok=True)
    for f in os.listdir(download_dir):
        os.remove(os.path.join(download_dir, f))

    result = run_cli("download", first_ref, "--output-dir", download_dir)
    if result.returncode != 0:
        print(f"Download failed: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    # --- Step 6: Verify integrity ---
    print("\n--- Step 6: Verify integrity ---")
    downloaded_files = os.listdir(download_dir)
    if not downloaded_files:
        print("ERROR: No files in download directory")
        sys.exit(1)

    data_files = [f for f in downloaded_files if f.endswith(".data")]
    if data_files:
        downloaded_file = os.path.join(download_dir, data_files[0])
    else:
        downloaded_file = os.path.join(download_dir, downloaded_files[0])

    downloaded_hash = sha256_file(downloaded_file)

    print(f"Original:   {original_hash}")
    print(f"Downloaded: {downloaded_hash}")

    if original_hash == downloaded_hash:
        print("\nPASS: Batch upload integrity verified - hashes match.")
    else:
        print("\nFAIL: Hash mismatch - data integrity compromised!")
        sys.exit(1)

    # --- Summary ---
    print("\n--- Summary ---")
    print(f"Uploaded {len(manifest)} files with stamp reuse.")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
