#!/usr/bin/env python3
"""
Memory Unit Generator

Creates SemantiCord-inspired memory units with canonical hashing
and uploads them to Swarm.

Usage:
    python create_memory_unit.py --domain market-forecast --asset ETH/USD --value 2500
"""

import subprocess
import sys
import json
import re
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timezone


def run_command(args: list) -> tuple:
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def extract_ref(output: str) -> str:
    match = re.search(r"[a-f0-9]{64}", output)
    return match.group(0) if match else ""


def compute_canonical_hash(data: dict) -> str:
    """Compute SHA256 hash of canonically serialized JSON."""
    # Remove content_hash field if present
    data_copy = {k: v for k, v in data.items() if k != "content_hash"}

    # Canonical serialization: sorted keys, minimal separators
    canonical = json.dumps(data_copy, sort_keys=True, separators=(",", ":"))

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_memory_unit(
    domain: str,
    payload: dict,
    unit_id: str = None,
    related_units: list = None,
) -> dict:
    """
    Create a memory unit with canonical hash.

    Args:
        domain: Domain classification
        payload: Domain-specific payload
        unit_id: Custom unit ID (auto-generated if None)
        related_units: List of related unit references

    Returns:
        Memory unit dictionary with computed hash
    """
    timestamp = datetime.now(timezone.utc)

    if unit_id is None:
        unit_id = f"mu-{timestamp.strftime('%Y%m%d%H%M%S')}"

    unit = {
        "id": unit_id,
        "version": "1.0",
        "domain": domain,
        "timestamp": timestamp.isoformat(),
        "payload": payload,
        "metadata": {
            "created_by": "swarm-provenance-cli",
            "schema": f"{domain}-v1",
        },
        "related_units": related_units or [],
    }

    # Compute and add canonical hash
    unit["content_hash"] = compute_canonical_hash(unit)

    return unit


def main():
    parser = argparse.ArgumentParser(
        description="Create and upload a memory unit to Swarm"
    )
    parser.add_argument(
        "--domain",
        default="market-forecast",
        help="Domain classification (default: market-forecast)"
    )
    parser.add_argument(
        "--asset",
        default="ETH/USD",
        help="Asset identifier (default: ETH/USD)"
    )
    parser.add_argument(
        "--value",
        type=float,
        default=2500.00,
        help="Prediction/observation value (default: 2500.00)"
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.85,
        help="Confidence level 0-1 (default: 0.85)"
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
    print("Swarm Provenance CLI - Memory Unit Generator")
    print("=" * 55)
    print()

    # Check CLI
    returncode, stdout, _ = run_command(["swarm-prov-upload", "--version"])
    if returncode != 0:
        print("ERROR: swarm-prov-upload not found")
        sys.exit(1)

    # Create payload based on domain
    if args.domain == "market-forecast":
        payload = {
            "event": "price_prediction",
            "asset": args.asset,
            "prediction": {"value": args.value, "currency": "USD"},
            "confidence": args.confidence,
            "timeframe": "24h",
        }
    elif args.domain == "price-observation":
        payload = {
            "event": "price_snapshot",
            "asset": args.asset,
            "price": args.value,
            "source": "aggregated",
        }
    else:
        payload = {
            "event": "custom",
            "value": args.value,
        }

    # Create memory unit
    print("Step 1: Creating memory unit")
    print()

    unit = create_memory_unit(args.domain, payload)

    print(f"  ID: {unit['id']}")
    print(f"  Domain: {unit['domain']}")
    print(f"  Hash: {unit['content_hash']}")
    print()

    # Save to file
    unit_file = args.output_dir / f"{unit['id']}.json"
    unit_file.write_text(json.dumps(unit, indent=2))
    print(f"  Saved: {unit_file}")
    print()

    # Upload to Swarm
    print("Step 2: Uploading to Swarm")
    print()

    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "upload",
        "--file", str(unit_file),
        "--std", "MEMORY-UNIT-V1",
    ])

    if returncode != 0:
        print(f"ERROR: Upload failed: {stderr}")
        sys.exit(1)

    print(stdout)

    swarm_ref = extract_ref(stdout)

    # Update unit with Swarm reference
    unit["swarm_ref"] = swarm_ref

    # Save updated manifest
    manifest_file = args.output_dir / f"{unit['id']}.manifest.json"
    manifest_file.write_text(json.dumps(unit, indent=2))

    print()
    print("=" * 55)
    print("Memory Unit Created")
    print("=" * 55)
    print()
    print(f"Unit ID:    {unit['id']}")
    print(f"Domain:     {unit['domain']}")
    print(f"Swarm Ref:  {swarm_ref}")
    print(f"Hash:       {unit['content_hash']}")
    print()
    print(f"Unit file:     {unit_file}")
    print(f"Manifest:      {manifest_file}")
    print()
    print("To verify:")
    print(f"  python verify_memory_unit.py {swarm_ref}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
