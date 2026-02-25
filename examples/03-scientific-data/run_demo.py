#!/usr/bin/env python3
"""
Scientific Data Demo - Python Version

Demonstrates research data archival on Swarm:
1. Upload experiment metadata with --std "PROV-O" --duration 720 (30 days)
2. Upload experiment results CSV
3. Download and verify the CSV data

Usage:
    python run_demo.py
    python run_demo.py --metadata dataset_metadata.json --results experiment_results.csv
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


def upload_file(file_path: str, std: str, duration: int = None) -> str:
    """Upload a file and return its Swarm reference.

    Tries pool first, then regular stamp purchase.
    If duration is specified, tries with duration first, falls back to default.
    """
    extra_args = ["--std", std]
    if duration:
        extra_args += ["--duration", str(duration)]

    # Try pool first
    result = run_cli("upload", "--file", file_path, *extra_args, "--usePool")
    if result.returncode == 0:
        ref = extract_swarm_ref(result.stdout)
        if ref:
            print(result.stdout.strip())
            return ref

    # Try without pool
    print("  Pool not available, trying without pool...")
    result = run_cli("upload", "--file", file_path, *extra_args)
    if result.returncode == 0:
        ref = extract_swarm_ref(result.stdout)
        if ref:
            print(result.stdout.strip())
            return ref

    # If duration was set, fall back to default duration
    if duration:
        print(f"  Duration {duration}h not available, falling back to default...")
        return upload_file(file_path, std)

    print(f"  Upload failed: {result.stderr or result.stdout}")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Scientific data archival demo")
    parser.add_argument(
        "--metadata", "-m",
        default=str(SCRIPT_DIR / "dataset_metadata.json"),
        help="Metadata JSON file (default: dataset_metadata.json)",
    )
    parser.add_argument(
        "--results", "-r",
        default=str(SCRIPT_DIR / "experiment_results.csv"),
        help="Results CSV file (default: experiment_results.csv)",
    )
    args = parser.parse_args()

    for f in [args.metadata, args.results]:
        if not os.path.exists(f):
            print(f"ERROR: File not found: {f}")
            sys.exit(1)

    print("=" * 55)
    print("  Swarm Provenance CLI - Scientific Data (Python)")
    print("=" * 55)

    # --- Step 1: Check health ---
    print("\n--- Step 1: Check gateway health ---")
    result = run_cli("health")
    if result.returncode != 0:
        print(f"Gateway not available: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    # --- Step 2: Upload metadata with PROV-O and 30-day retention ---
    print("\n--- Step 2: Upload metadata (PROV-O, 30-day retention) ---")
    meta_hash = sha256_file(args.metadata)
    print(f"File:   {args.metadata}")
    print(f"SHA256: {meta_hash}")
    print("\nUploading with --std PROV-O --duration 720...")
    meta_ref = upload_file(args.metadata, "PROV-O", duration=720)
    print(f"\nMetadata Reference: {meta_ref}")

    # --- Step 3: Upload results CSV ---
    print("\n--- Step 3: Upload experiment results CSV ---")
    csv_hash = sha256_file(args.results)
    print(f"File:   {args.results}")
    print(f"SHA256: {csv_hash}")
    print("\nUploading with --std PROV-O...")
    csv_ref = upload_file(args.results, "PROV-O")
    print(f"\nResults Reference: {csv_ref}")

    # --- Step 4: Download and verify CSV ---
    print("\n--- Step 4: Download and verify results CSV ---")
    download_dir = str(SCRIPT_DIR / "downloads")
    os.makedirs(download_dir, exist_ok=True)
    for f in os.listdir(download_dir):
        os.remove(os.path.join(download_dir, f))

    result = run_cli("download", csv_ref, "--output-dir", download_dir)
    if result.returncode != 0:
        print(f"Download failed: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    # --- Step 5: Verify integrity ---
    print("\n--- Step 5: Verify integrity ---")
    downloaded_files = os.listdir(download_dir)
    if not downloaded_files:
        print("ERROR: No files in download directory")
        sys.exit(1)

    data_files = [f for f in downloaded_files if f.endswith(".data")]
    if data_files:
        downloaded_file = os.path.join(download_dir, data_files[0])
    else:
        downloaded_file = os.path.join(download_dir, downloaded_files[0])

    original_hash = sha256_file(args.results)
    downloaded_hash = sha256_file(downloaded_file)

    print(f"Original:   {original_hash}")
    print(f"Downloaded: {downloaded_hash}")

    if original_hash == downloaded_hash:
        print("\nPASS: Experiment data integrity verified - hashes match.")
    else:
        print("\nFAIL: Hash mismatch - data may have been corrupted!")
        sys.exit(1)

    # --- Summary ---
    print("\n--- Summary ---")
    print(f"Metadata Reference: {meta_ref}")
    print(f"Results Reference:  {csv_ref}")
    print("Both datasets archived on Swarm with PROV-O provenance standard.")


if __name__ == "__main__":
    main()
