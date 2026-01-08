#!/usr/bin/env python3
"""
Tamper Detection Demonstration

Downloads data from Swarm and demonstrates how tampering is detected.

Usage:
    python tamper_detection.py <swarm_ref> [--output-dir <dir>]
"""

import subprocess
import sys
import json
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timezone


def run_command(args: list) -> tuple:
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_sha256_file(file_path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def main():
    parser = argparse.ArgumentParser(
        description="Demonstrate tamper detection"
    )
    parser.add_argument(
        "swarm_ref",
        help="Swarm reference hash"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./tamper_test"),
        help="Output directory"
    )

    args = parser.parse_args()
    args.output_dir.mkdir(exist_ok=True)

    print("=" * 55)
    print("Swarm Provenance CLI - Tamper Detection Demo")
    print("=" * 55)
    print()

    # Download original
    print("Step 1: Download original data")
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

    # Load files
    data_file = args.output_dir / f"{args.swarm_ref}.data"
    meta_file = args.output_dir / f"{args.swarm_ref}.meta.json"

    if not data_file.exists():
        print("ERROR: Data file not found")
        sys.exit(1)

    original_data = data_file.read_bytes()
    original_hash = compute_sha256(original_data)

    # Load expected hash
    expected_hash = None
    if meta_file.exists():
        with open(meta_file) as f:
            metadata = json.load(f)
        expected_hash = metadata.get("content_hash")

    print("Step 2: Verify original data")
    print(f"  Expected hash: {expected_hash}")
    print(f"  Computed hash: {original_hash}")

    if expected_hash and original_hash.lower() == expected_hash.lower():
        print("  RESULT: VERIFIED - Original data is intact")
    else:
        print("  RESULT: MISMATCH - Even original data doesn't match!")
    print()

    # Simulate tampering
    print("Step 3: Simulate tampering")
    print()

    # Create tampered versions
    tamper_tests = [
        {
            "name": "Append data",
            "modify": lambda d: d + b"\n[TAMPERED]",
        },
        {
            "name": "Prepend data",
            "modify": lambda d: b"[MODIFIED]\n" + d,
        },
        {
            "name": "Change single byte",
            "modify": lambda d: d[:10] + bytes([d[10] ^ 0xFF]) + d[11:] if len(d) > 11 else d + b"X",
        },
        {
            "name": "Replace word",
            "modify": lambda d: d.replace(b"data", b"DATA") if b"data" in d else d + b"x",
        },
    ]

    results = []

    for i, test in enumerate(tamper_tests, 1):
        tampered_data = test["modify"](original_data)
        tampered_hash = compute_sha256(tampered_data)

        is_detected = tampered_hash.lower() != expected_hash.lower() if expected_hash else True

        result = {
            "test": test["name"],
            "tampered_hash": tampered_hash,
            "detected": is_detected,
        }
        results.append(result)

        print(f"  Test {i}: {test['name']}")
        print(f"    Tampered hash: {tampered_hash[:32]}...")
        print(f"    Detection: {'DETECTED' if is_detected else 'MISSED'}")
        print()

    # Summary
    print("=" * 55)
    print("Tamper Detection Summary")
    print("=" * 55)
    print()

    detected_count = sum(1 for r in results if r["detected"])
    total_tests = len(results)

    print(f"Tests performed: {total_tests}")
    print(f"Tampering detected: {detected_count}/{total_tests}")
    print()

    if detected_count == total_tests:
        print("RESULT: All tampering attempts were detected")
        print()
        print("The SHA256 hash in the Swarm metadata provides")
        print("strong protection against data modification.")
    else:
        print("WARNING: Some tampering was not detected!")

    print()

    # Save report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "swarm_ref": args.swarm_ref,
        "original_hash": original_hash,
        "expected_hash": expected_hash,
        "original_verified": original_hash.lower() == (expected_hash or "").lower(),
        "tamper_tests": results,
        "detection_rate": f"{detected_count}/{total_tests}",
    }

    report_file = args.output_dir / "tamper_detection_report.json"
    report_file.write_text(json.dumps(report, indent=2))

    print(f"Report saved: {report_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
