#!/usr/bin/env python3
"""
Audit Trail Demo - Python Version

Demonstrates immutable compliance audit records on Swarm:
1. Upload multiple audit records with --std "AUDIT-LOG-V1"
2. Download and verify one record
3. Prove data integrity via SHA-256

Usage:
    python run_demo.py
    python run_demo.py --records audit_record_001.json audit_record_002.json
"""

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

DEFAULT_RECORDS = [
    "audit_record_001.json",
    "audit_record_002.json",
    "audit_record_003.json",
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


def main():
    parser = argparse.ArgumentParser(description="Audit trail demo")
    parser.add_argument(
        "--records", "-r",
        nargs="+",
        default=DEFAULT_RECORDS,
        help="Audit record files to upload (default: all 3 sample records)",
    )
    args = parser.parse_args()

    print("=" * 50)
    print("  Swarm Provenance CLI - Audit Trail (Python)")
    print("=" * 50)

    # --- Step 1: Check health ---
    print("\n--- Step 1: Check gateway health ---")
    result = run_cli("health")
    if result.returncode != 0:
        print(f"Gateway not available: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    # --- Step 2: Upload audit records ---
    print("\n--- Step 2: Upload audit records with --std AUDIT-LOG-V1 ---")
    refs = {}

    for record_name in args.records:
        record_path = str(SCRIPT_DIR / record_name)
        if not os.path.exists(record_path):
            print(f"ERROR: File not found: {record_path}")
            sys.exit(1)

        original_hash = sha256_file(record_path)
        print(f"\nUploading: {record_name}")
        print(f"  SHA256: {original_hash}")

        result = run_cli("upload", "--file", record_path, "--std", "AUDIT-LOG-V1", "--usePool")
        if result.returncode != 0:
            print("  Pool not available, falling back to regular stamp purchase...")
            result = run_cli("upload", "--file", record_path, "--std", "AUDIT-LOG-V1")
            if result.returncode != 0:
                print(f"  Upload failed: {result.stderr or result.stdout}")
                sys.exit(1)

        swarm_ref = extract_swarm_ref(result.stdout)
        if not swarm_ref:
            print(f"  Could not extract Swarm reference from output")
            sys.exit(1)

        refs[record_name] = swarm_ref
        print(f"  Reference: {swarm_ref}")

    print(f"\nAll {len(refs)} audit records uploaded.")

    # --- Step 3: Download and verify first record ---
    first_record = args.records[0]
    first_ref = refs[first_record]

    print(f"\n--- Step 3: Download and verify {first_record} ---")
    download_dir = str(SCRIPT_DIR / "downloads")
    os.makedirs(download_dir, exist_ok=True)
    for f in os.listdir(download_dir):
        os.remove(os.path.join(download_dir, f))

    result = run_cli("download", first_ref, "--output-dir", download_dir)
    if result.returncode != 0:
        print(f"Download failed: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    # --- Step 4: Verify integrity ---
    print("\n--- Step 4: Verify integrity ---")
    downloaded_files = os.listdir(download_dir)
    if not downloaded_files:
        print("ERROR: No files in download directory")
        sys.exit(1)

    data_files = [f for f in downloaded_files if f.endswith(".data")]
    if data_files:
        downloaded_file = os.path.join(download_dir, data_files[0])
    else:
        downloaded_file = os.path.join(download_dir, downloaded_files[0])

    original_hash = sha256_file(str(SCRIPT_DIR / first_record))
    downloaded_hash = sha256_file(downloaded_file)

    print(f"Original:   {original_hash}")
    print(f"Downloaded: {downloaded_hash}")

    if original_hash == downloaded_hash:
        print("\nPASS: Audit record integrity verified - hashes match.")
    else:
        print("\nFAIL: Hash mismatch - audit record may have been tampered with!")
        sys.exit(1)

    # --- Summary ---
    print("\n--- Summary ---")
    print(f"Uploaded {len(refs)} audit records with AUDIT-LOG-V1 standard.")
    print("Swarm References:")
    for name, ref in refs.items():
        print(f"  {name}: {ref}")
    print("These immutable records can be retrieved from any Swarm gateway.")


if __name__ == "__main__":
    main()
