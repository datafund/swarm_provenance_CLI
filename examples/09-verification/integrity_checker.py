#!/usr/bin/env python3
"""
Integrity Checker

Verifies a Swarm reference against an expected content hash.
Downloads the file and compares SHA-256 hashes.

Usage:
    python integrity_checker.py --ref <swarm_hash> --expected-hash <sha256>
    python integrity_checker.py --ref <swarm_hash> --original-file document.txt
"""

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path


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


def verify_reference(swarm_ref: str, expected_hash: str,
                     output_dir: str) -> dict:
    """Download a Swarm reference and verify against expected hash.

    Returns a verification report dict.
    """
    os.makedirs(output_dir, exist_ok=True)
    for f in os.listdir(output_dir):
        os.remove(os.path.join(output_dir, f))

    result = run_cli("download", swarm_ref, "--output-dir", output_dir)
    if result.returncode != 0:
        return {
            "status": "ERROR",
            "message": f"Download failed: {result.stderr or result.stdout}",
        }

    downloaded_files = os.listdir(output_dir)
    if not downloaded_files:
        return {
            "status": "ERROR",
            "message": "No files in download directory",
        }

    data_files = [f for f in downloaded_files if f.endswith(".data")]
    if data_files:
        downloaded_file = os.path.join(output_dir, data_files[0])
    else:
        downloaded_file = os.path.join(output_dir, downloaded_files[0])

    actual_hash = sha256_file(downloaded_file)

    return {
        "status": "PASS" if actual_hash == expected_hash else "FAIL",
        "swarm_reference": swarm_ref,
        "expected_hash": expected_hash,
        "actual_hash": actual_hash,
        "match": actual_hash == expected_hash,
        "downloaded_file": downloaded_file,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Verify Swarm reference integrity"
    )
    parser.add_argument(
        "--ref", "-r",
        required=True,
        help="Swarm reference hash to verify",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--expected-hash", "-e",
        help="Expected SHA-256 hash",
    )
    group.add_argument(
        "--original-file", "-f",
        help="Original file to compare against",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default="./verification_downloads",
        help="Directory for downloaded files",
    )
    args = parser.parse_args()

    if args.original_file:
        if not os.path.exists(args.original_file):
            print(f"ERROR: File not found: {args.original_file}")
            sys.exit(1)
        expected_hash = sha256_file(args.original_file)
    else:
        expected_hash = args.expected_hash

    print(f"Verifying Swarm reference: {args.ref}")
    print(f"Expected hash: {expected_hash}")

    report = verify_reference(args.ref, expected_hash, args.output_dir)

    print(f"\nVerification result: {report['status']}")
    if report["status"] == "ERROR":
        print(f"Error: {report['message']}")
        sys.exit(1)

    print(f"Expected:   {report['expected_hash']}")
    print(f"Downloaded: {report['actual_hash']}")

    if report["match"]:
        print("\nPASS: Integrity verified - hashes match.")
    else:
        print("\nFAIL: Integrity check failed - hashes do not match!")
        sys.exit(1)


if __name__ == "__main__":
    main()
