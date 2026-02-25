#!/usr/bin/env python3
"""
Tamper Detection Tool

Demonstrates how content-addressed storage detects tampering.
Compares original and modified files to show that any change
produces a completely different hash.

Usage:
    python tamper_detection.py --original document.txt --tampered document_tampered.txt
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path


def sha256_file(path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def find_differences(original_path: str, tampered_path: str) -> list:
    """Find line-level differences between two text files."""
    with open(original_path, "r") as f:
        original_lines = f.readlines()
    with open(tampered_path, "r") as f:
        tampered_lines = f.readlines()

    diffs = []
    max_lines = max(len(original_lines), len(tampered_lines))
    for i in range(max_lines):
        orig = original_lines[i] if i < len(original_lines) else "<missing>"
        tamp = tampered_lines[i] if i < len(tampered_lines) else "<missing>"
        if orig != tamp:
            diffs.append({
                "line": i + 1,
                "original": orig.rstrip("\n"),
                "tampered": tamp.rstrip("\n"),
            })
    return diffs


def main():
    parser = argparse.ArgumentParser(
        description="Detect tampering via hash comparison"
    )
    parser.add_argument(
        "--original", "-o",
        required=True,
        help="Path to original file",
    )
    parser.add_argument(
        "--tampered", "-t",
        required=True,
        help="Path to potentially tampered file",
    )
    args = parser.parse_args()

    if not os.path.exists(args.original):
        print(f"ERROR: Original file not found: {args.original}")
        sys.exit(1)
    if not os.path.exists(args.tampered):
        print(f"ERROR: Tampered file not found: {args.tampered}")
        sys.exit(1)

    print("=" * 55)
    print("  Tamper Detection Report")
    print("=" * 55)

    original_hash = sha256_file(args.original)
    tampered_hash = sha256_file(args.tampered)

    print(f"\nOriginal file:  {args.original}")
    print(f"  SHA-256: {original_hash}")
    print(f"\nCompared file:  {args.tampered}")
    print(f"  SHA-256: {tampered_hash}")

    if original_hash == tampered_hash:
        print("\nRESULT: Files are IDENTICAL (hashes match)")
        print("No tampering detected.")
    else:
        print("\nRESULT: Files are DIFFERENT (hashes do not match)")
        print("TAMPERING DETECTED!")

        # Show differences
        diffs = find_differences(args.original, args.tampered)
        if diffs:
            print(f"\nDifferences found ({len(diffs)} lines changed):")
            for diff in diffs[:5]:  # Show first 5 differences
                print(f"  Line {diff['line']}:")
                print(f"    Original: {diff['original']}")
                print(f"    Tampered: {diff['tampered']}")
            if len(diffs) > 5:
                print(f"  ... and {len(diffs) - 5} more differences")

    return original_hash != tampered_hash


if __name__ == "__main__":
    tampered = main()
    sys.exit(0)
