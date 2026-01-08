#!/usr/bin/env python3
"""
Batch Upload Script

Efficiently uploads multiple files using a single postage stamp.
Generates a manifest tracking all uploaded references.

Usage:
    python batch_upload.py ./sample_files --size medium --std "BATCH-V1"
"""

import subprocess
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime, timezone


def run_command(args: list) -> tuple:
    """Run CLI command and return (returncode, stdout, stderr)."""
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def extract_ref(output: str) -> str:
    """Extract Swarm reference from output."""
    match = re.search(r"[a-f0-9]{64}", output)
    return match.group(0) if match else ""


def extract_stamp_id(output: str) -> str:
    """Extract stamp ID from upload output."""
    match = re.search(r"Stamp purchased: ([a-f0-9]+)", output)
    if match:
        return match.group(1)
    match = re.search(r"stamp.*?([a-f0-9]{64})", output, re.IGNORECASE)
    return match.group(1) if match else ""


def batch_upload(
    directory: Path,
    size: str = "medium",
    std: str = None,
    output_dir: Path = None,
    pattern: str = "*",
) -> dict:
    """
    Upload all files in directory using a single stamp.

    Args:
        directory: Directory containing files to upload
        size: Stamp size preset (small, medium, large)
        std: Provenance standard identifier
        output_dir: Directory for manifest output
        pattern: Glob pattern for file matching

    Returns:
        Manifest dictionary with all upload references
    """
    directory = Path(directory)
    if output_dir is None:
        output_dir = directory.parent / "output"
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)

    # Find files
    files = sorted(directory.glob(pattern))
    if not files:
        print(f"No files found matching {pattern} in {directory}")
        return {}

    print(f"Found {len(files)} files to upload")
    print()

    uploads = []
    stamp_id = None

    for i, file_path in enumerate(files):
        print(f"[{i+1}/{len(files)}] Uploading: {file_path.name}")

        # Build command
        cmd = [
            "swarm-prov-upload", "upload",
            "--file", str(file_path),
        ]

        if std:
            cmd.extend(["--std", std])

        # First file: purchase stamp with size
        if i == 0:
            cmd.extend(["--size", size])
        # Subsequent files: reuse stamp
        elif stamp_id:
            cmd.extend(["--stamp-id", stamp_id])

        returncode, stdout, stderr = run_command(cmd)

        if returncode != 0:
            print(f"  ERROR: {stderr}")
            continue

        swarm_ref = extract_ref(stdout)

        # Extract stamp ID from first upload
        if i == 0:
            stamp_id = extract_stamp_id(stdout)
            if stamp_id:
                print(f"  Stamp: {stamp_id[:32]}...")

        print(f"  Reference: {swarm_ref}")

        uploads.append({
            "filename": file_path.name,
            "swarm_ref": swarm_ref,
            "size": file_path.stat().st_size,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        })

    # Create manifest
    manifest = {
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "stamp_id": stamp_id,
        "provenance_standard": std,
        "source_directory": str(directory),
        "total_files": len(uploads),
        "total_size": sum(u["size"] for u in uploads),
        "uploads": uploads,
    }

    # Save manifest
    manifest_file = output_dir / "batch_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2))
    print()
    print(f"Manifest saved: {manifest_file}")

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Batch upload files to Swarm with stamp reuse"
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory containing files to upload"
    )
    parser.add_argument(
        "--size",
        choices=["small", "medium", "large"],
        default="medium",
        help="Stamp size preset (default: medium)"
    )
    parser.add_argument(
        "--std",
        default="BATCH-V1",
        help="Provenance standard identifier"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for manifest output"
    )
    parser.add_argument(
        "--pattern",
        default="*",
        help="Glob pattern for file matching (default: *)"
    )

    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"ERROR: {args.directory} is not a directory")
        sys.exit(1)

    print("=" * 50)
    print("Swarm Provenance CLI - Batch Upload")
    print("=" * 50)
    print()

    # Check CLI
    returncode, stdout, _ = run_command(["swarm-prov-upload", "--version"])
    if returncode != 0:
        print("ERROR: swarm-prov-upload not found")
        sys.exit(1)
    print(f"CLI Version: {stdout.strip()}")
    print()

    manifest = batch_upload(
        args.directory,
        size=args.size,
        std=args.std,
        output_dir=args.output_dir,
        pattern=args.pattern,
    )

    print()
    print("=" * 50)
    print("Summary")
    print("=" * 50)
    print()
    print(f"Files uploaded: {manifest.get('total_files', 0)}")
    print(f"Total size: {manifest.get('total_size', 0)} bytes")
    print(f"Stamps used: 1")
    print(f"Cost savings: {manifest.get('total_files', 1) - 1} stamps saved")

    return 0


if __name__ == "__main__":
    sys.exit(main())
