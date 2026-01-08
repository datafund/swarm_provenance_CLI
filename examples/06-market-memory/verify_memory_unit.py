#!/usr/bin/env python3
"""
Memory Unit Verification Tool

Downloads a memory unit from Swarm and verifies its canonical hash.

Usage:
    python verify_memory_unit.py <swarm_ref> [--output-dir <dir>]
"""

import subprocess
import sys
import json
import hashlib
import argparse
from pathlib import Path


def run_command(args: list) -> tuple:
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def compute_canonical_hash(data: dict) -> str:
    """Compute SHA256 hash of canonically serialized JSON."""
    data_copy = {k: v for k, v in data.items() if k != "content_hash"}
    canonical = json.dumps(data_copy, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_memory_unit(unit: dict) -> tuple:
    """
    Verify a memory unit's hash.

    Returns:
        Tuple of (is_valid, computed_hash, stored_hash)
    """
    stored_hash = unit.get("content_hash", "")
    computed_hash = compute_canonical_hash(unit)

    is_valid = stored_hash.lower() == computed_hash.lower()

    return is_valid, computed_hash, stored_hash


def main():
    parser = argparse.ArgumentParser(
        description="Verify a memory unit from Swarm"
    )
    parser.add_argument(
        "swarm_ref",
        help="Swarm reference hash"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./verified"),
        help="Output directory"
    )

    args = parser.parse_args()
    args.output_dir.mkdir(exist_ok=True)

    print("=" * 55)
    print("Swarm Provenance CLI - Memory Unit Verification")
    print("=" * 55)
    print()

    # Download
    print("Step 1: Downloading from Swarm")
    print(f"  Reference: {args.swarm_ref}")
    print()

    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "download",
        args.swarm_ref,
        "--output-dir", str(args.output_dir),
    ])

    if returncode != 0:
        print(f"ERROR: Download failed: {stderr}")
        sys.exit(1)

    print(stdout)

    # Load memory unit
    data_file = args.output_dir / f"{args.swarm_ref}.data"
    meta_file = args.output_dir / f"{args.swarm_ref}.meta.json"

    if not data_file.exists():
        print(f"ERROR: Data file not found: {data_file}")
        sys.exit(1)

    print("Step 2: Parsing memory unit")
    print()

    try:
        with open(data_file) as f:
            unit = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}")
        sys.exit(1)

    print(f"  ID: {unit.get('id', 'unknown')}")
    print(f"  Domain: {unit.get('domain', 'unknown')}")
    print(f"  Timestamp: {unit.get('timestamp', 'unknown')}")
    print()

    # Verify hash
    print("Step 3: Verifying canonical hash")
    print()

    is_valid, computed_hash, stored_hash = verify_memory_unit(unit)

    print(f"  Stored hash:   {stored_hash}")
    print(f"  Computed hash: {computed_hash}")
    print()

    if is_valid:
        print("  RESULT: VALID - Hashes match")
    else:
        print("  RESULT: INVALID - Hash mismatch!")
        print("  WARNING: Data may have been tampered with")

    print()

    # Show payload
    print("Step 4: Memory unit payload")
    print()
    print(json.dumps(unit.get("payload", {}), indent=2))
    print()

    # Create verification report
    report = {
        "swarm_ref": args.swarm_ref,
        "unit_id": unit.get("id"),
        "domain": unit.get("domain"),
        "timestamp": unit.get("timestamp"),
        "stored_hash": stored_hash,
        "computed_hash": computed_hash,
        "is_valid": is_valid,
        "payload": unit.get("payload"),
    }

    report_file = args.output_dir / f"{args.swarm_ref}.verification.json"
    report_file.write_text(json.dumps(report, indent=2))

    print("=" * 55)
    print("Verification Complete")
    print("=" * 55)
    print()
    print(f"Status: {'VALID' if is_valid else 'INVALID'}")
    print(f"Report: {report_file}")

    return 0 if is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
