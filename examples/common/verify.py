"""
Verification utilities for Swarm Provenance CLI examples.

Provides helpers for integrity checking and verification workflows.
"""

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple


def compute_sha256(file_path: Path) -> str:
    """
    Compute SHA256 hash of a file.

    Args:
        file_path: Path to the file

    Returns:
        Hexadecimal SHA256 hash string
    """
    file_path = Path(file_path)
    sha256_hash = hashlib.sha256()

    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)

    return sha256_hash.hexdigest()


def compute_sha256_bytes(data: bytes) -> str:
    """
    Compute SHA256 hash of bytes.

    Args:
        data: Bytes to hash

    Returns:
        Hexadecimal SHA256 hash string
    """
    return hashlib.sha256(data).hexdigest()


def compare_hashes(hash1: str, hash2: str) -> bool:
    """
    Compare two hash strings (case-insensitive).

    Args:
        hash1: First hash string
        hash2: Second hash string

    Returns:
        True if hashes match, False otherwise
    """
    return hash1.lower() == hash2.lower()


def verify_download(
    metadata_path: Path,
    data_path: Path,
) -> Tuple[bool, dict]:
    """
    Verify a downloaded file against its metadata.

    Args:
        metadata_path: Path to the .meta.json file
        data_path: Path to the .data file

    Returns:
        Tuple of (is_valid, details_dict)
    """
    metadata_path = Path(metadata_path)
    data_path = Path(data_path)

    result = {
        "verified": False,
        "metadata_path": str(metadata_path),
        "data_path": str(data_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "errors": [],
        "details": {},
    }

    # Check files exist
    if not metadata_path.exists():
        result["errors"].append(f"Metadata file not found: {metadata_path}")
        return False, result

    if not data_path.exists():
        result["errors"].append(f"Data file not found: {data_path}")
        return False, result

    # Load metadata
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except json.JSONDecodeError as e:
        result["errors"].append(f"Invalid JSON in metadata: {e}")
        return False, result

    # Extract expected hash
    expected_hash = metadata.get("content_hash")
    if not expected_hash:
        result["errors"].append("No content_hash found in metadata")
        return False, result

    result["details"]["expected_hash"] = expected_hash

    # Compute actual hash
    actual_hash = compute_sha256(data_path)
    result["details"]["actual_hash"] = actual_hash

    # Compare
    is_valid = compare_hashes(expected_hash, actual_hash)
    result["verified"] = is_valid
    result["details"]["stamp_id"] = metadata.get("stamp_id", "unknown")
    result["details"]["provenance_standard"] = metadata.get("provenance_standard")
    result["details"]["encryption"] = metadata.get("encryption")

    if not is_valid:
        result["errors"].append(
            f"Hash mismatch: expected {expected_hash}, got {actual_hash}"
        )

    return is_valid, result


def verify_memory_unit(memory_unit: dict) -> Tuple[bool, str]:
    """
    Verify a memory unit's content hash.

    The hash is computed over the unit WITHOUT the content_hash field,
    using canonical JSON (sorted keys, no whitespace).

    Args:
        memory_unit: Memory unit dictionary

    Returns:
        Tuple of (is_valid, computed_hash)
    """
    # Create a copy without the hash
    unit_copy = {k: v for k, v in memory_unit.items() if k != "content_hash"}

    # Compute canonical hash
    canonical = json.dumps(unit_copy, sort_keys=True, separators=(",", ":"))
    computed_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # Compare with stored hash
    stored_hash = memory_unit.get("content_hash", "")
    is_valid = compare_hashes(computed_hash, stored_hash)

    return is_valid, computed_hash


def format_verification_report(
    results: list,
    title: str = "Verification Report",
) -> str:
    """
    Format multiple verification results into a readable report.

    Args:
        results: List of (is_valid, details) tuples from verify_download
        title: Report title

    Returns:
        Formatted report string
    """
    lines = [
        title,
        "=" * len(title),
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Total files: {len(results)}",
        "",
    ]

    passed = sum(1 for valid, _ in results if valid)
    failed = len(results) - passed

    lines.append(f"Passed: {passed}")
    lines.append(f"Failed: {failed}")
    lines.append("")
    lines.append("-" * 50)
    lines.append("")

    for i, (is_valid, details) in enumerate(results, 1):
        status = "PASS" if is_valid else "FAIL"
        lines.append(f"[{i}] {status}: {details.get('data_path', 'unknown')}")

        if details.get("details"):
            d = details["details"]
            if d.get("expected_hash"):
                lines.append(f"    Expected: {d['expected_hash'][:16]}...")
            if d.get("actual_hash"):
                lines.append(f"    Actual:   {d['actual_hash'][:16]}...")
            if d.get("stamp_id"):
                lines.append(f"    Stamp:    {d['stamp_id'][:16]}...")

        if details.get("errors"):
            for error in details["errors"]:
                lines.append(f"    ERROR: {error}")

        lines.append("")

    lines.append("-" * 50)
    summary = "ALL PASSED" if failed == 0 else f"{failed} FAILED"
    lines.append(f"Summary: {summary}")

    return "\n".join(lines)


def create_verification_manifest(
    uploads: list,
    output_path: Path,
) -> Path:
    """
    Create a JSON manifest of uploaded files for later verification.

    Args:
        uploads: List of dicts with 'file_path', 'swarm_ref', 'content_hash'
        output_path: Path to write the manifest

    Returns:
        Path to the created manifest
    """
    manifest = {
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "total_files": len(uploads),
        "uploads": uploads,
    }

    output_path = Path(output_path)
    output_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return output_path
