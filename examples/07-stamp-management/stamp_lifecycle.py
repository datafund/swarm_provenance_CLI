#!/usr/bin/env python3
"""
Stamp Lifecycle Management

Demonstrates stamp operations: list, info, and monitoring.

Usage:
    python stamp_lifecycle.py [--stamp-id <id>]
"""

import subprocess
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime, timezone


def run_command(args: list) -> tuple:
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def extract_ref(output: str) -> str:
    match = re.search(r"[a-f0-9]{64}", output)
    return match.group(0) if match else ""


def list_stamps() -> str:
    """List all stamps and return output."""
    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "stamps", "list"
    ])
    return stdout if returncode == 0 else stderr


def get_stamp_info(stamp_id: str) -> str:
    """Get detailed stamp information."""
    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "stamps", "info", stamp_id
    ])
    return stdout if returncode == 0 else stderr


def create_stamp_via_upload(output_dir: Path) -> str:
    """Create a new stamp by uploading a file."""
    sample_file = output_dir / "stamp_test.txt"
    sample_file.write_text(
        f"Stamp management test - {datetime.now(timezone.utc).isoformat()}"
    )

    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "upload",
        "--file", str(sample_file),
        "--size", "small",
    ])

    if returncode != 0:
        return ""

    # Extract stamp ID
    match = re.search(r"Stamp purchased: ([a-f0-9]+)", stdout)
    if match:
        return match.group(1)

    # Try to find any 64-char hex
    match = re.search(r"stamp.*?([a-f0-9]{64})", stdout, re.IGNORECASE)
    return match.group(1) if match else ""


def main():
    parser = argparse.ArgumentParser(
        description="Stamp lifecycle management"
    )
    parser.add_argument(
        "--stamp-id",
        help="Specific stamp ID to inspect"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./output"),
        help="Output directory"
    )

    args = parser.parse_args()
    args.output_dir.mkdir(exist_ok=True)

    print("=" * 55)
    print("Swarm Provenance CLI - Stamp Lifecycle Management")
    print("=" * 55)
    print()

    # Check CLI
    returncode, stdout, _ = run_command(["swarm-prov-upload", "--version"])
    if returncode != 0:
        print("ERROR: swarm-prov-upload not found")
        sys.exit(1)
    print(f"CLI Version: {stdout.strip()}")
    print()

    # Step 1: List stamps
    print("=" * 55)
    print("Step 1: List All Stamps")
    print("=" * 55)
    print()

    stamps_output = list_stamps()
    print(stamps_output)
    print()

    # Step 2: Get or create a stamp
    stamp_id = args.stamp_id

    if not stamp_id:
        print("=" * 55)
        print("Step 2: Create New Stamp (via upload)")
        print("=" * 55)
        print()

        stamp_id = create_stamp_via_upload(args.output_dir)
        if stamp_id:
            print(f"Created stamp: {stamp_id[:32]}...")
        else:
            print("Could not create/extract stamp ID")

            # Try to get from list
            match = re.search(r"[a-f0-9]{64}", stamps_output)
            if match:
                stamp_id = match.group(0)
                print(f"Using existing stamp: {stamp_id[:32]}...")
        print()

    # Step 3: Get stamp details
    if stamp_id:
        print("=" * 55)
        print("Step 3: Stamp Details")
        print("=" * 55)
        print()

        info_output = get_stamp_info(stamp_id)
        print(info_output)
        print()

        # Parse key metrics
        print("Key Metrics:")
        if "usable" in info_output.lower():
            usable = "Yes" in info_output or "true" in info_output.lower()
            print(f"  Usable: {'Yes' if usable else 'No'}")

        # Extract TTL
        ttl_match = re.search(r"TTL[:\s]+([^\n]+)", info_output, re.IGNORECASE)
        if ttl_match:
            print(f"  TTL: {ttl_match.group(1).strip()}")

        # Extract utilization
        util_match = re.search(r"[Uu]tilization[:\s]+(\d+)", info_output)
        if util_match:
            print(f"  Utilization: {util_match.group(1)}%")
        print()

    # Summary
    print("=" * 55)
    print("Stamp Management Summary")
    print("=" * 55)
    print()
    print("Commands:")
    print("  swarm-prov-upload stamps list        - List all stamps")
    print("  swarm-prov-upload stamps info <id>   - Stamp details")
    print("  swarm-prov-upload stamps extend <id> - Extend TTL")
    print()
    print("Tips:")
    print("  - Use --size small/medium/large for appropriate capacity")
    print("  - Reuse stamps with --stamp-id for cost savings")
    print("  - Monitor utilization before large batch uploads")
    print("  - Extend stamps before TTL expires")

    return 0


if __name__ == "__main__":
    sys.exit(main())
