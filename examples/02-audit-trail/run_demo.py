#!/usr/bin/env python3
"""
Audit Trail / Compliance Records Demo - Python Version

Demonstrates creating immutable audit trails with provenance standards.
"""

import subprocess
import sys
import json
import re
from pathlib import Path
from datetime import datetime, timezone


def run_command(args: list) -> tuple:
    """Run a CLI command and return (returncode, stdout, stderr)."""
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def extract_swarm_ref(output: str) -> str:
    """Extract 64-character Swarm reference from output."""
    match = re.search(r"[a-f0-9]{64}", output)
    return match.group(0) if match else ""


def extract_stamp_id(output: str) -> str:
    """Extract stamp ID from upload output."""
    # Try to find "Stamp purchased: <id>" pattern
    match = re.search(r"Stamp purchased: ([a-f0-9]+)", output)
    if match:
        return match.group(1)
    # Try to find stamp_id in verbose output
    match = re.search(r"stamp_id.*?([a-f0-9]{64})", output)
    return match.group(1) if match else ""


def main():
    script_dir = Path(__file__).parent
    output_dir = script_dir / "output"
    output_dir.mkdir(exist_ok=True)

    print("=" * 50)
    print("Swarm Provenance CLI - Audit Trail Demo (Python)")
    print("=" * 50)
    print()

    # Check CLI
    returncode, stdout, stderr = run_command(["swarm-prov-upload", "--version"])
    if returncode != 0:
        print("ERROR: swarm-prov-upload not found")
        sys.exit(1)
    print(f"CLI Version: {stdout.strip()}")
    print()

    # Health check
    print("Checking gateway health...")
    run_command(["swarm-prov-upload", "health"])
    print()

    # Track all uploaded records
    audit_trail = []
    stamp_id = None

    # Step 1: Upload audit log
    print("=" * 50)
    print("Step 1: Upload Audit Log")
    print("=" * 50)
    print()

    audit_file = script_dir / "audit_log.json"
    print(f"Uploading {audit_file.name} with --std AUDIT-LOG-V1")
    print()

    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "upload",
        "--file", str(audit_file),
        "--std", "AUDIT-LOG-V1",
        "--size", "medium",
    ])

    if returncode != 0:
        print(f"ERROR: Upload failed: {stderr}")
        sys.exit(1)

    print(stdout)
    audit_ref = extract_swarm_ref(stdout)
    stamp_id = extract_stamp_id(stdout)

    print(f"Audit log reference: {audit_ref}")
    print()

    audit_trail.append({
        "type": "audit_log",
        "standard": "AUDIT-LOG-V1",
        "swarm_ref": audit_ref,
        "filename": "audit_log.json",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    })

    # Step 2: Upload compliance record (reusing stamp)
    print("=" * 50)
    print("Step 2: Upload Compliance Record (Stamp Reuse)")
    print("=" * 50)
    print()

    compliance_file = script_dir / "compliance_record.json"

    if stamp_id:
        print(f"Reusing stamp: {stamp_id[:16]}...")
        returncode, stdout, stderr = run_command([
            "swarm-prov-upload", "upload",
            "--file", str(compliance_file),
            "--std", "COMPLIANCE-SOC2-V1",
            "--stamp-id", stamp_id,
        ])
    else:
        print("No stamp ID found, purchasing new stamp...")
        returncode, stdout, stderr = run_command([
            "swarm-prov-upload", "upload",
            "--file", str(compliance_file),
            "--std", "COMPLIANCE-SOC2-V1",
        ])

    if returncode != 0:
        print(f"ERROR: Upload failed: {stderr}")
        sys.exit(1)

    print(stdout)
    compliance_ref = extract_swarm_ref(stdout)
    print(f"Compliance record reference: {compliance_ref}")
    print()

    audit_trail.append({
        "type": "compliance_assessment",
        "standard": "COMPLIANCE-SOC2-V1",
        "swarm_ref": compliance_ref,
        "filename": "compliance_record.json",
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    })

    # Step 3: Create and upload manifest
    print("=" * 50)
    print("Step 3: Create Audit Trail Manifest")
    print("=" * 50)
    print()

    manifest = {
        "manifest_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "organization": "Example Corporation",
        "period": "2025-Q1",
        "records": audit_trail,
        "total_records": len(audit_trail),
        "verification_instructions": (
            "Download each record using 'swarm-prov-upload download <swarm_ref>' "
            "and verify the SHA256 hash matches the content_hash in metadata."
        ),
    }

    manifest_file = output_dir / "audit_trail_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2))

    print(f"Manifest created: {manifest_file}")
    print(json.dumps(manifest, indent=2))
    print()

    print("Uploading manifest to create complete audit trail...")
    print()

    cmd = [
        "swarm-prov-upload", "upload",
        "--file", str(manifest_file),
        "--std", "AUDIT-MANIFEST-V1",
    ]
    if stamp_id:
        cmd.extend(["--stamp-id", stamp_id])

    returncode, stdout, stderr = run_command(cmd)

    if returncode != 0:
        print(f"ERROR: Manifest upload failed: {stderr}")
        sys.exit(1)

    print(stdout)
    manifest_ref = extract_swarm_ref(stdout)
    print(f"Manifest reference: {manifest_ref}")
    print()

    # Step 4: Verify one record
    print("=" * 50)
    print("Step 4: Verify Audit Record")
    print("=" * 50)
    print()

    print("Downloading and verifying audit log...")
    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "download",
        audit_ref,
        "--output-dir", str(output_dir),
    ])

    if returncode != 0:
        print(f"WARNING: Download failed: {stderr}")
    else:
        print(stdout)

        # Check metadata
        meta_file = output_dir / f"{audit_ref}.meta.json"
        if meta_file.exists():
            with open(meta_file) as f:
                metadata = json.load(f)
            print("Metadata verification:")
            print(f"  provenance_standard: {metadata.get('provenance_standard')}")
            print(f"  content_hash: {metadata.get('content_hash', '')[:32]}...")
            print(f"  stamp_id: {metadata.get('stamp_id', '')[:32]}...")
    print()

    # Summary
    print("=" * 50)
    print("Audit Trail Summary")
    print("=" * 50)
    print()
    print("Records uploaded to immutable storage:")
    print()
    print("1. Audit Log")
    print("   Standard: AUDIT-LOG-V1")
    print(f"   Reference: {audit_ref}")
    print()
    print("2. Compliance Record")
    print("   Standard: COMPLIANCE-SOC2-V1")
    print(f"   Reference: {compliance_ref}")
    print()
    print("3. Audit Trail Manifest")
    print("   Standard: AUDIT-MANIFEST-V1")
    print(f"   Reference: {manifest_ref}")
    print()
    print(f"Output directory: {output_dir}")
    print()
    print("To verify any record:")
    print("  swarm-prov-upload download <reference> --output-dir ./verify")
    print()
    print("=" * 50)
    print("Demo complete!")
    print("=" * 50)

    return 0


if __name__ == "__main__":
    sys.exit(main())
