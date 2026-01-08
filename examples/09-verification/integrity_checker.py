#!/usr/bin/env python3
"""
Integrity Checker

Downloads data from Swarm and performs comprehensive integrity verification.

Usage:
    python integrity_checker.py <swarm_ref> [--output-dir <dir>]
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


def compute_sha256(file_path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def verify_integrity(swarm_ref: str, output_dir: Path) -> dict:
    """
    Download and verify data integrity.

    Returns:
        Verification report dictionary
    """
    report = {
        "verification_id": f"ver-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "swarm_ref": swarm_ref,
        "results": {
            "download_success": False,
            "hash_verified": False,
            "expected_hash": None,
            "actual_hash": None,
            "metadata_valid": False,
        },
        "conclusion": "UNKNOWN",
        "details": {},
        "errors": [],
    }

    # Download
    print(f"Downloading: {swarm_ref}")
    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "download",
        swarm_ref,
        "--output-dir", str(output_dir),
    ])

    if returncode != 0:
        report["errors"].append(f"Download failed: {stderr}")
        report["conclusion"] = "DOWNLOAD_FAILED"
        return report

    report["results"]["download_success"] = True
    print("Download complete")

    # Find files
    data_file = output_dir / f"{swarm_ref}.data"
    meta_file = output_dir / f"{swarm_ref}.meta.json"

    # Check for unverified file (indicates CLI detected mismatch)
    unverified_file = output_dir / f"{swarm_ref}.UNVERIFIED.data"
    if unverified_file.exists():
        report["errors"].append("CLI flagged data as UNVERIFIED")
        data_file = unverified_file

    if not data_file.exists():
        report["errors"].append(f"Data file not found: {data_file}")
        report["conclusion"] = "DATA_MISSING"
        return report

    # Load metadata
    if meta_file.exists():
        try:
            with open(meta_file) as f:
                metadata = json.load(f)
            report["results"]["metadata_valid"] = True
            report["results"]["expected_hash"] = metadata.get("content_hash")
            report["details"] = {
                "provenance_standard": metadata.get("provenance_standard"),
                "stamp_id": metadata.get("stamp_id"),
                "encryption": metadata.get("encryption"),
            }
        except json.JSONDecodeError as e:
            report["errors"].append(f"Invalid metadata JSON: {e}")
    else:
        report["errors"].append("Metadata file not found")

    # Compute actual hash
    actual_hash = compute_sha256(data_file)
    report["results"]["actual_hash"] = actual_hash
    print(f"Computed hash: {actual_hash}")

    # Compare
    expected_hash = report["results"]["expected_hash"]
    if expected_hash:
        print(f"Expected hash: {expected_hash}")
        if actual_hash.lower() == expected_hash.lower():
            report["results"]["hash_verified"] = True
            report["conclusion"] = "VERIFIED"
        else:
            report["conclusion"] = "HASH_MISMATCH"
            report["errors"].append("Hash mismatch - data may be tampered")
    else:
        report["conclusion"] = "NO_EXPECTED_HASH"
        report["errors"].append("No expected hash in metadata")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Verify data integrity from Swarm"
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
    print("Swarm Provenance CLI - Integrity Checker")
    print("=" * 55)
    print()

    # Check CLI
    returncode, _, _ = run_command(["swarm-prov-upload", "--version"])
    if returncode != 0:
        print("ERROR: swarm-prov-upload not found")
        sys.exit(1)

    # Verify
    report = verify_integrity(args.swarm_ref, args.output_dir)

    print()
    print("=" * 55)
    print("Verification Report")
    print("=" * 55)
    print()

    # Display results
    results = report["results"]
    print(f"Download:     {'SUCCESS' if results['download_success'] else 'FAILED'}")
    print(f"Metadata:     {'VALID' if results['metadata_valid'] else 'INVALID'}")
    print(f"Hash Match:   {'YES' if results['hash_verified'] else 'NO'}")
    print()

    if results["expected_hash"]:
        print(f"Expected: {results['expected_hash']}")
    if results["actual_hash"]:
        print(f"Actual:   {results['actual_hash']}")
    print()

    # Conclusion
    conclusion = report["conclusion"]
    if conclusion == "VERIFIED":
        print("RESULT: VERIFIED - Data integrity confirmed")
    elif conclusion == "HASH_MISMATCH":
        print("RESULT: FAILED - Hash mismatch detected")
        print("WARNING: Data may have been tampered with!")
    else:
        print(f"RESULT: {conclusion}")

    # Errors
    if report["errors"]:
        print()
        print("Errors:")
        for error in report["errors"]:
            print(f"  - {error}")

    # Save report
    report_file = args.output_dir / f"{args.swarm_ref}.verification.json"
    report_file.write_text(json.dumps(report, indent=2))
    print()
    print(f"Report saved: {report_file}")

    return 0 if conclusion == "VERIFIED" else 1


if __name__ == "__main__":
    sys.exit(main())
