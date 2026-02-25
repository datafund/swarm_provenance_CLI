#!/usr/bin/env python3
"""
CI/CD Artifact Archiver

Archives build artifacts to Swarm with provenance metadata.
Designed for use in CI/CD pipelines (GitHub Actions, GitLab CI, etc.).

Usage:
    python archive_artifacts.py --directory ./sample_artifacts
    python archive_artifacts.py --directory ./dist --std "CI-ARTIFACT-V1"
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
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


def extract_swarm_ref(output: str) -> str:
    """Extract Swarm reference hash from CLI output."""
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if "Swarm Reference Hash:" in line and i + 1 < len(lines):
            ref = lines[i + 1].strip()
            if len(ref) >= 64:
                return ref
    return ""


def archive_file(file_path: str, std: str = None) -> dict:
    """Upload a single artifact and return its receipt.

    Returns dict with reference, hash, filename, and timestamp.
    """
    args = ["upload", "--file", file_path]
    if std:
        args.extend(["--std", std])

    result = run_cli(*(args + ["--usePool"]))
    if result.returncode != 0:
        print(f"  Pool not available, falling back to regular stamp purchase...")
        result = run_cli(*args)

    if result.returncode != 0:
        return {"error": result.stderr or result.stdout}

    ref = extract_swarm_ref(result.stdout)
    return {
        "filename": os.path.basename(file_path),
        "reference": ref,
        "content_hash": sha256_file(file_path),
        "size_bytes": os.path.getsize(file_path),
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Archive build artifacts to Swarm"
    )
    parser.add_argument(
        "--directory", "-d",
        required=True,
        help="Directory containing artifacts to archive",
    )
    parser.add_argument(
        "--std", "-s",
        default="CI-ARTIFACT-V1",
        help="Provenance standard (default: CI-ARTIFACT-V1)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output receipt file (default: <directory>/archive_receipt.json)",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"ERROR: Directory not found: {args.directory}")
        sys.exit(1)

    files = sorted([
        f for f in os.listdir(args.directory)
        if os.path.isfile(os.path.join(args.directory, f))
    ])

    if not files:
        print(f"ERROR: No files found in {args.directory}")
        sys.exit(1)

    print(f"Archiving {len(files)} artifacts from {args.directory}")
    print(f"Provenance standard: {args.std}")

    receipt = {
        "pipeline": "ci-cd-archive",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "standard": args.std,
        "artifacts": [],
    }

    for i, filename in enumerate(files):
        file_path = os.path.join(args.directory, filename)
        print(f"\n[{i + 1}/{len(files)}] Archiving: {filename}")

        result = archive_file(file_path, std=args.std)

        if "error" in result:
            print(f"  ERROR: {result['error']}")
            sys.exit(1)

        if not result["reference"]:
            print("  ERROR: Could not extract Swarm reference")
            sys.exit(1)

        receipt["artifacts"].append(result)
        print(f"  Reference: {result['reference']}")
        print(f"  Hash: {result['content_hash']}")

    # Save receipt
    output_path = args.output or os.path.join(args.directory, "archive_receipt.json")
    with open(output_path, "w") as f:
        json.dump(receipt, f, indent=2)
    print(f"\nArchive receipt saved: {output_path}")
    print(f"Total artifacts archived: {len(receipt['artifacts'])}")


if __name__ == "__main__":
    main()
