#!/usr/bin/env python3
"""
Basic Upload/Download Demo - Python Version

Demonstrates programmatic usage of the Swarm Provenance CLI
for uploading and downloading files.
"""

import subprocess
import sys
import json
import hashlib
from pathlib import Path


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def run_command(args: list, capture: bool = True) -> tuple:
    """Run a CLI command and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        args,
        capture_output=capture,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def main():
    script_dir = Path(__file__).parent
    sample_file = script_dir / "sample.txt"
    output_dir = script_dir / "output"

    print("=" * 50)
    print("Swarm Provenance CLI - Basic Demo (Python)")
    print("=" * 50)
    print()

    # Check CLI availability
    returncode, stdout, stderr = run_command(["swarm-prov-upload", "--version"])
    if returncode != 0:
        print("ERROR: swarm-prov-upload not found")
        print("Install with: pip install swarm-provenance-uploader")
        sys.exit(1)

    print(f"CLI Version: {stdout.strip()}")
    print()

    # Health check
    print("Checking gateway health...")
    returncode, stdout, stderr = run_command(["swarm-prov-upload", "health"])
    if returncode != 0:
        print(f"WARNING: Health check failed: {stderr}")
    else:
        print(stdout)

    # Step 1: Upload
    print("=" * 50)
    print("Step 1: Uploading sample.txt")
    print("=" * 50)
    print()

    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "upload",
        "--file", str(sample_file),
    ])

    if returncode != 0:
        print(f"ERROR: Upload failed: {stderr}")
        sys.exit(1)

    print(stdout)

    # Extract Swarm reference (64 hex characters)
    import re
    match = re.search(r"[a-f0-9]{64}", stdout)
    if not match:
        print("ERROR: Could not extract Swarm reference from output")
        sys.exit(1)

    swarm_ref = match.group(0)
    print(f"Swarm reference: {swarm_ref}")
    print()

    # Step 2: Download
    print("=" * 50)
    print("Step 2: Downloading and verifying")
    print("=" * 50)
    print()

    output_dir.mkdir(exist_ok=True)

    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "download",
        swarm_ref,
        "--output-dir", str(output_dir),
    ])

    if returncode != 0:
        print(f"ERROR: Download failed: {stderr}")
        sys.exit(1)

    print(stdout)
    print()

    # Step 3: Examine results
    print("=" * 50)
    print("Step 3: Examining output files")
    print("=" * 50)
    print()

    meta_file = output_dir / f"{swarm_ref}.meta.json"
    data_file = output_dir / f"{swarm_ref}.data"

    print(f"Output directory: {output_dir}")
    for f in output_dir.iterdir():
        print(f"  - {f.name} ({f.stat().st_size} bytes)")
    print()

    # Show metadata structure
    if meta_file.exists():
        print("Metadata structure:")
        with open(meta_file) as f:
            metadata = json.load(f)
        # Show structure without full data
        display_meta = {
            "data": f"<base64 encoded, {len(metadata.get('data', ''))} chars>",
            "content_hash": metadata.get("content_hash"),
            "stamp_id": metadata.get("stamp_id"),
            "provenance_standard": metadata.get("provenance_standard"),
            "encryption": metadata.get("encryption"),
        }
        print(json.dumps(display_meta, indent=2))
        print()

    # Show downloaded content
    if data_file.exists():
        print("Downloaded content (first 200 chars):")
        content = data_file.read_text()
        print(content[:200])
        if len(content) > 200:
            print("...")
        print()

    # Step 4: Verification
    print("=" * 50)
    print("Step 4: Verification")
    print("=" * 50)
    print()

    original_hash = compute_sha256(sample_file)
    downloaded_hash = compute_sha256(data_file)

    print(f"Original file hash:   {original_hash}")
    print(f"Downloaded file hash: {downloaded_hash}")
    print()

    if original_hash == downloaded_hash:
        print("SUCCESS: Files match! Integrity verified.")
    else:
        print("WARNING: Hash mismatch detected!")

    print()
    print("=" * 50)
    print("Demo complete!")
    print("=" * 50)
    print()
    print(f"Swarm reference for future retrieval: {swarm_ref}")
    print(f"Output directory: {output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
