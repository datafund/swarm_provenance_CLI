#!/usr/bin/env python3
"""
Verification & Integrity Demo - Python Version

Demonstrates data verification and tamper detection:
1. Upload original document
2. Download and verify integrity (hash match)
3. Tamper test: compare original vs tampered file hashes
4. Download with --verify flag (notary verification)
5. Print verification report

Usage:
    python run_demo.py
    python run_demo.py --file sample_document.txt --tampered sample_document_tampered.txt
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
    parser = argparse.ArgumentParser(description="Verification & integrity demo")
    parser.add_argument(
        "--file", "-f",
        default="sample_document.txt",
        help="Original document to upload and verify (default: sample_document.txt)",
    )
    parser.add_argument(
        "--tampered", "-t",
        default="sample_document_tampered.txt",
        help="Tampered document for comparison (default: sample_document_tampered.txt)",
    )
    args = parser.parse_args()

    print("=" * 55)
    print("  Swarm Provenance CLI - Verification (Python)")
    print("=" * 55)

    # --- Step 1: Check health ---
    print("\n--- Step 1: Check gateway health ---")
    result = run_cli("health")
    if result.returncode != 0:
        print(f"Gateway not available: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    # Verify files exist
    original_path = str(SCRIPT_DIR / args.file)
    tampered_path = str(SCRIPT_DIR / args.tampered)

    if not os.path.exists(original_path):
        print(f"ERROR: Original file not found: {original_path}")
        sys.exit(1)
    if not os.path.exists(tampered_path):
        print(f"ERROR: Tampered file not found: {tampered_path}")
        sys.exit(1)

    # --- Step 2: Upload original document ---
    print("\n--- Step 2: Upload original document ---")
    original_hash = sha256_file(original_path)
    print(f"Uploading: {args.file}")
    print(f"  SHA256: {original_hash}")

    result = run_cli("upload", "--file", original_path, "--usePool")
    if result.returncode != 0:
        print("  Pool not available, falling back to regular stamp purchase...")
        result = run_cli("upload", "--file", original_path)
        if result.returncode != 0:
            print(f"  Upload failed: {result.stderr or result.stdout}")
            sys.exit(1)

    swarm_ref = extract_swarm_ref(result.stdout)
    if not swarm_ref:
        print("  Could not extract Swarm reference from output")
        sys.exit(1)

    print(f"  Reference: {swarm_ref}")

    # --- Step 3: Download and verify ---
    print("\n--- Step 3: Download and verify integrity ---")
    download_dir = str(SCRIPT_DIR / "downloads")
    os.makedirs(download_dir, exist_ok=True)
    for f in os.listdir(download_dir):
        os.remove(os.path.join(download_dir, f))

    result = run_cli("download", swarm_ref, "--output-dir", download_dir)
    if result.returncode != 0:
        print(f"Download failed: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

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
        print("\nPASS: Document integrity verified - hashes match.")
    else:
        print("\nFAIL: Hash mismatch - document may have been tampered with!")
        sys.exit(1)

    # --- Step 4: Tamper detection test ---
    print("\n--- Step 4: Tamper detection test ---")
    tampered_hash = sha256_file(tampered_path)
    print(f"Original document hash:  {original_hash}")
    print(f"Tampered document hash:  {tampered_hash}")

    if original_hash != tampered_hash:
        print("\nPASS: Tamper detection works - hashes differ.")
        print("Even a small change produces a completely different SHA-256 hash.")
    else:
        print("\nFAIL: Hashes should differ for different content!")
        sys.exit(1)

    # --- Step 5: Download with --verify ---
    print("\n--- Step 5: Download with --verify (notary verification) ---")
    for f in os.listdir(download_dir):
        os.remove(os.path.join(download_dir, f))

    result = run_cli("download", swarm_ref, "--output-dir", download_dir, "--verify")
    print(result.stdout.strip() if result.stdout else "")
    if result.stderr:
        print(result.stderr.strip())
    print("Note: --verify checks for notary signatures. If none exist,")
    print("the download still succeeds but reports no signatures found.")

    # --- Step 6: Verification report ---
    print("\n--- Step 6: Verification Report ---")
    print("=" * 55)
    print(f"  Document: {args.file}")
    print(f"  Swarm Reference: {swarm_ref}")
    print(f"  SHA-256 Hash: {original_hash}")
    print(f"  Integrity: VERIFIED")
    print(f"  Tamper Detection: WORKING")
    print("=" * 55)
    print("\nPASS: All verification checks passed.")


if __name__ == "__main__":
    main()
