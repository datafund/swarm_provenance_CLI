#!/usr/bin/env python3
"""
CI/CD Integration Demo - Python Version

Demonstrates archiving build artifacts to Swarm:
1. Upload build artifacts with --std "CI-ARTIFACT-V1"
2. Save receipt manifest with references and hashes
3. Download and verify one artifact

Usage:
    python run_demo.py
    python run_demo.py --artifacts build_info.json release_notes.txt
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

DEFAULT_ARTIFACTS = [
    "sample_artifacts/build_info.json",
    "sample_artifacts/release_notes.txt",
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
    parser = argparse.ArgumentParser(description="CI/CD integration demo")
    parser.add_argument(
        "--artifacts", "-a",
        nargs="+",
        default=DEFAULT_ARTIFACTS,
        help="Artifact files to archive (default: sample build artifacts)",
    )
    args = parser.parse_args()

    print("=" * 55)
    print("  Swarm Provenance CLI - CI/CD Integration (Python)")
    print("=" * 55)

    # --- Step 1: Check health ---
    print("\n--- Step 1: Check gateway health ---")
    result = run_cli("health")
    if result.returncode != 0:
        print(f"Gateway not available: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    # --- Step 2: Upload artifacts ---
    print('\n--- Step 2: Upload artifacts with --std "CI-ARTIFACT-V1" ---')
    receipt = {
        "pipeline": "ci-cd-demo",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "standard": "CI-ARTIFACT-V1",
        "artifacts": [],
    }

    for artifact_rel in args.artifacts:
        artifact_path = str(SCRIPT_DIR / artifact_rel)
        artifact_name = os.path.basename(artifact_rel)

        if not os.path.exists(artifact_path):
            print(f"ERROR: File not found: {artifact_path}")
            sys.exit(1)

        content_hash = sha256_file(artifact_path)
        print(f"\nUploading: {artifact_name}")
        print(f"  SHA256: {content_hash}")

        result = run_cli("upload", "--file", artifact_path, "--std", "CI-ARTIFACT-V1", "--usePool")
        if result.returncode != 0:
            print("  Pool not available, falling back to regular stamp purchase...")
            result = run_cli("upload", "--file", artifact_path, "--std", "CI-ARTIFACT-V1")
            if result.returncode != 0:
                print(f"  Upload failed: {result.stderr or result.stdout}")
                sys.exit(1)

        swarm_ref = extract_swarm_ref(result.stdout)
        if not swarm_ref:
            print("  Could not extract Swarm reference from output")
            sys.exit(1)

        receipt["artifacts"].append({
            "filename": artifact_name,
            "reference": swarm_ref,
            "content_hash": content_hash,
        })
        print(f"  Reference: {swarm_ref}")

    print(f"\nAll {len(receipt['artifacts'])} artifacts archived.")

    # --- Step 3: Save receipt ---
    print("\n--- Step 3: Save archive receipt ---")
    receipt_path = str(SCRIPT_DIR / "archive_receipt.json")
    with open(receipt_path, "w") as f:
        json.dump(receipt, f, indent=2)
    print(f"Receipt saved: {receipt_path}")

    # --- Step 4: Download and verify first artifact ---
    first = receipt["artifacts"][0]
    print(f"\n--- Step 4: Download and verify {first['filename']} ---")
    download_dir = str(SCRIPT_DIR / "downloads")
    os.makedirs(download_dir, exist_ok=True)
    for f in os.listdir(download_dir):
        os.remove(os.path.join(download_dir, f))

    result = run_cli("download", first["reference"], "--output-dir", download_dir)
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

    downloaded_hash = sha256_file(downloaded_file)
    original_hash = first["content_hash"]

    print(f"Original:   {original_hash}")
    print(f"Downloaded: {downloaded_hash}")

    if original_hash == downloaded_hash:
        print("\nPASS: Build artifact integrity verified - hashes match.")
    else:
        print("\nFAIL: Hash mismatch - artifact may have been tampered with!")
        sys.exit(1)

    # --- Summary ---
    print("\n--- Summary ---")
    print(f"Archived {len(receipt['artifacts'])} build artifacts with CI-ARTIFACT-V1 standard.")
    print(f"Receipt: {receipt_path}")


if __name__ == "__main__":
    main()
