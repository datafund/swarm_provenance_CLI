#!/usr/bin/env python3
"""
Batch Upload Tool

Uploads all files in a directory to Swarm with stamp reuse.
The first file triggers a stamp purchase; subsequent files reuse that stamp.

Usage:
    python batch_upload.py --directory ./sample_files
    python batch_upload.py --directory ./sample_files --std "PROV-STD-V1"
"""

import argparse
import hashlib
import json
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
    """Extract stamp ID from verbose CLI output.

    Handles format: 'Stamp ID Received: <hex> (Length: 64)'
    """
    for line in output.splitlines():
        if "Stamp ID Received:" in line:
            parts = line.split("Stamp ID Received:")
            if len(parts) > 1:
                # Take first token only (ignore trailing "(Length: 64)" etc.)
                stamp_id = parts[1].strip().split()[0]
                if len(stamp_id) >= 16:
                    return stamp_id
    return ""


def upload_file(file_path: str, std: str = None, stamp_id: str = None,
                verbose: bool = False) -> dict:
    """Upload a single file, optionally reusing a stamp.

    Returns dict with 'reference', 'stamp_id', and 'hash' keys.
    """
    args = ["upload", "--file", file_path]
    if std:
        args.extend(["--std", std])
    if stamp_id:
        args.extend(["--stamp-id", stamp_id])
    if verbose:
        args.append("-v")

    if not stamp_id:
        # Try pool first
        result = run_cli(*(args + ["--usePool"]))
        if result.returncode != 0:
            result = run_cli(*args)
    else:
        result = run_cli(*args)

    if result.returncode != 0:
        return {"error": result.stderr or result.stdout}

    output = result.stdout + "\n" + result.stderr
    ref = extract_swarm_ref(result.stdout)
    sid = extract_stamp_id(output)

    return {
        "reference": ref,
        "stamp_id": sid,
        "hash": sha256_file(file_path),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Batch upload files to Swarm with stamp reuse"
    )
    parser.add_argument(
        "--directory", "-d",
        required=True,
        help="Directory containing files to upload",
    )
    parser.add_argument(
        "--std", "-s",
        default=None,
        help="Provenance standard to apply (e.g., PROV-STD-V1)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output manifest file (default: <directory>/manifest.json)",
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

    print(f"Batch uploading {len(files)} files from {args.directory}")
    if args.std:
        print(f"Provenance standard: {args.std}")

    manifest = {}
    stamp_id = None

    for i, filename in enumerate(files):
        file_path = os.path.join(args.directory, filename)
        print(f"\n[{i + 1}/{len(files)}] Uploading: {filename}")

        # First upload uses verbose to capture stamp ID
        verbose = (i == 0 and stamp_id is None)
        result = upload_file(file_path, std=args.std, stamp_id=stamp_id,
                             verbose=verbose)

        if "error" in result:
            print(f"  ERROR: {result['error']}")
            sys.exit(1)

        if not result["reference"]:
            print("  ERROR: Could not extract Swarm reference")
            sys.exit(1)

        # Capture stamp ID from first upload for reuse
        if stamp_id is None and result.get("stamp_id"):
            stamp_id = result["stamp_id"]
            print(f"  Stamp ID captured: {stamp_id[:16]}...")

        manifest[filename] = {
            "reference": result["reference"],
            "content_hash": result["hash"],
        }
        print(f"  Reference: {result['reference']}")

    # Save manifest
    output_path = args.output or os.path.join(args.directory, "manifest.json")
    with open(output_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest saved: {output_path}")
    print(f"Total files uploaded: {len(manifest)}")


if __name__ == "__main__":
    main()
