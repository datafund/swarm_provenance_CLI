#!/usr/bin/env python3
"""
Scientific Data Preservation Demo - Python Version

Demonstrates long-term research data archival with PROV-O standard.
"""

import subprocess
import sys
import json
import re
from pathlib import Path
from datetime import datetime, timezone


def run_command(args: list) -> tuple:
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def extract_ref(output: str) -> str:
    match = re.search(r"[a-f0-9]{64}", output)
    return match.group(0) if match else ""


def main():
    script_dir = Path(__file__).parent
    output_dir = script_dir / "output"
    output_dir.mkdir(exist_ok=True)

    print("=" * 55)
    print("Swarm Provenance CLI - Scientific Data Demo (Python)")
    print("=" * 55)
    print()

    # Check CLI
    returncode, stdout, _ = run_command(["swarm-prov-upload", "--version"])
    if returncode != 0:
        print("ERROR: swarm-prov-upload not found")
        sys.exit(1)
    print(f"CLI Version: {stdout.strip()}")

    # Health check
    run_command(["swarm-prov-upload", "health"])
    print()

    # Step 1: Upload metadata
    print("=" * 55)
    print("Step 1: Upload Dataset Metadata (PROV-O)")
    print("=" * 55)
    print()

    meta_file = script_dir / "dataset_metadata.json"
    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "upload",
        "--file", str(meta_file),
        "--std", "PROV-O",
        "--duration", "720",
        "--size", "medium",
    ])

    if returncode != 0:
        print(f"ERROR: {stderr}")
        sys.exit(1)

    print(stdout)
    meta_ref = extract_ref(stdout)
    print(f"Metadata reference: {meta_ref}")
    print()

    # Step 2: Upload raw data
    print("=" * 55)
    print("Step 2: Upload Experiment Data (CSV)")
    print("=" * 55)
    print()

    data_file = script_dir / "experiment_results.csv"
    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "upload",
        "--file", str(data_file),
        "--std", "PROV-O",
        "--duration", "720",
    ])

    if returncode != 0:
        print(f"ERROR: {stderr}")
        sys.exit(1)

    print(stdout)
    data_ref = extract_ref(stdout)
    print(f"Data reference: {data_ref}")
    print()

    # Step 3: Create manifest
    print("=" * 55)
    print("Step 3: Create Research Artifact Manifest")
    print("=" * 55)
    print()

    manifest = {
        "manifest_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_title": "Urban Climate Monitoring Dataset - Ljubljana Q1 2025",
        "doi": "10.5281/example.20250108",
        "provenance_standard": "PROV-O",
        "retention_days": 30,
        "artifacts": [
            {
                "type": "metadata",
                "description": "DataCite-compliant dataset metadata",
                "filename": "dataset_metadata.json",
                "swarm_ref": meta_ref,
            },
            {
                "type": "data",
                "description": "Raw experiment results (CSV)",
                "filename": "experiment_results.csv",
                "swarm_ref": data_ref,
            },
        ],
    }

    manifest_file = output_dir / "research_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2))
    print(f"Manifest created: {manifest_file}")
    print(json.dumps(manifest, indent=2))
    print()

    # Step 4: Verify
    print("=" * 55)
    print("Step 4: Verify Data Retrieval")
    print("=" * 55)
    print()

    run_command([
        "swarm-prov-upload", "download",
        data_ref,
        "--output-dir", str(output_dir),
    ])

    downloaded = output_dir / f"{data_ref}.data"
    if downloaded.exists():
        print("Downloaded data preview:")
        lines = downloaded.read_text().split("\n")[:5]
        for line in lines:
            print(f"  {line}")
    print()

    print("=" * 55)
    print("Summary")
    print("=" * 55)
    print()
    print(f"Metadata: {meta_ref}")
    print(f"Data:     {data_ref}")
    print(f"Output:   {output_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
