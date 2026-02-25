#!/usr/bin/env python3
"""
Stamp Management Demo - Python Version

Demonstrates the full postage stamp lifecycle:
1. Check stamp pool availability
2. Upload a file with -v to capture stamp ID
3. List all stamps
4. Inspect stamp details
5. Health-check a stamp

Usage:
    python run_demo.py
    python run_demo.py --file sample_data.txt
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
    parser = argparse.ArgumentParser(description="Stamp management demo")
    parser.add_argument(
        "--file", "-f",
        default="sample_data.txt",
        help="File to upload for stamp acquisition (default: sample_data.txt)",
    )
    args = parser.parse_args()

    print("=" * 55)
    print("  Swarm Provenance CLI - Stamp Management (Python)")
    print("=" * 55)

    # --- Step 1: Check health ---
    print("\n--- Step 1: Check gateway health ---")
    result = run_cli("health")
    if result.returncode != 0:
        print(f"Gateway not available: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    # --- Step 2: Check stamp pool ---
    print("\n--- Step 2: Check stamp pool availability ---")
    result = run_cli("stamps", "pool-status")
    print(result.stdout.strip() if result.stdout else result.stderr.strip())

    # --- Step 3: Upload file with verbose ---
    print("\n--- Step 3: Upload file with -v to capture stamp ID ---")
    file_path = str(SCRIPT_DIR / args.file)
    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    print(f"Uploading: {args.file}")
    result = run_cli("upload", "--file", file_path, "-v", "--usePool")
    if result.returncode != 0:
        print("  Pool not available, falling back to regular stamp purchase...")
        result = run_cli("upload", "--file", file_path, "-v")
        if result.returncode != 0:
            print(f"  Upload failed: {result.stderr or result.stdout}")
            sys.exit(1)

    swarm_ref = extract_swarm_ref(result.stdout)
    if not swarm_ref:
        print("  Could not extract Swarm reference")
        sys.exit(1)

    combined_output = result.stdout + "\n" + result.stderr
    stamp_id = extract_stamp_id(combined_output)

    print(f"  Swarm reference: {swarm_ref}")

    if not stamp_id:
        print("  WARNING: Could not extract stamp ID from verbose output")
        print("  Stamp lifecycle commands require a stamp ID.")
        print("\nPASS: Upload succeeded. Stamp lifecycle steps skipped.")
        return

    print(f"  Stamp ID: {stamp_id}")

    # --- Step 4: List stamps ---
    print("\n--- Step 4: List all stamps ---")
    result = run_cli("stamps", "list")
    print(result.stdout.strip() if result.stdout else result.stderr.strip())

    # --- Step 5: Stamp info ---
    print(f"\n--- Step 5: Stamp details for {stamp_id[:16]}... ---")
    result = run_cli("stamps", "info", stamp_id)
    print(result.stdout.strip() if result.stdout else result.stderr.strip())

    # --- Step 6: Stamp health check ---
    print("\n--- Step 6: Stamp health check ---")
    result = run_cli("stamps", "check", stamp_id)
    print(result.stdout.strip() if result.stdout else result.stderr.strip())

    print("\nPASS: Stamp lifecycle demo complete.")
    print(f"\n--- Summary ---")
    print(f"Swarm reference: {swarm_ref}")
    print(f"Stamp ID: {stamp_id}")


if __name__ == "__main__":
    main()
