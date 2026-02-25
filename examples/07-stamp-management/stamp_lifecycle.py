#!/usr/bin/env python3
"""
Stamp Lifecycle Manager

Demonstrates the full postage stamp lifecycle:
1. Check pool availability
2. Upload a file to acquire a stamp
3. List all stamps
4. Inspect stamp details
5. Health-check a stamp
6. Attempt to extend a stamp (may require funded wallet)

Usage:
    python stamp_lifecycle.py
    python stamp_lifecycle.py --file sample_data.txt
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run_cli(*args) -> subprocess.CompletedProcess:
    """Run a swarm-prov-upload CLI command."""
    cmd = ["swarm-prov-upload"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


def extract_stamp_id(output: str) -> str:
    """Extract stamp ID from verbose CLI output.

    Handles format: 'Stamp ID Received: <hex> (Length: 64)'
    """
    for line in output.splitlines():
        if "Stamp ID Received:" in line:
            parts = line.split("Stamp ID Received:")
            if len(parts) > 1:
                # Take first token only (ignore trailing "(Length: 64)" etc.)
                stamp_id = parts[1].strip().split()[0]
                if len(stamp_id) >= 16:
                    return stamp_id
    return ""


def extract_swarm_ref(output: str) -> str:
    """Extract Swarm reference hash from CLI output."""
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if "Swarm Reference Hash:" in line and i + 1 < len(lines):
            ref = lines[i + 1].strip()
            if len(ref) >= 64:
                return ref
    return ""


def pool_status():
    """Check stamp pool availability."""
    result = run_cli("stamps", "pool-status")
    print(result.stdout.strip() if result.stdout else result.stderr.strip())
    return result.returncode == 0


def list_stamps():
    """List all stamps."""
    result = run_cli("stamps", "list")
    print(result.stdout.strip() if result.stdout else result.stderr.strip())
    return result.returncode == 0


def stamp_info(stamp_id: str):
    """Get detailed stamp information."""
    result = run_cli("stamps", "info", stamp_id)
    print(result.stdout.strip() if result.stdout else result.stderr.strip())
    return result.returncode == 0


def stamp_check(stamp_id: str):
    """Health-check a stamp."""
    result = run_cli("stamps", "check", stamp_id)
    print(result.stdout.strip() if result.stdout else result.stderr.strip())
    return result.returncode == 0


def stamp_extend(stamp_id: str, amount: int = 1000000):
    """Attempt to extend a stamp (requires funded wallet)."""
    result = run_cli("stamps", "extend", stamp_id, "--amount", str(amount))
    print(result.stdout.strip() if result.stdout else result.stderr.strip())
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Stamp lifecycle demo")
    parser.add_argument(
        "--file", "-f",
        default=None,
        help="File to upload for stamp acquisition",
    )
    args = parser.parse_args()

    print("=" * 55)
    print("  Stamp Lifecycle Manager")
    print("=" * 55)

    # Step 1: Pool status
    print("\n--- Step 1: Check stamp pool availability ---")
    pool_status()

    # Step 2: Upload to acquire stamp
    if args.file:
        print(f"\n--- Step 2: Upload file to acquire stamp ---")
        if not os.path.exists(args.file):
            print(f"ERROR: File not found: {args.file}")
            sys.exit(1)

        result = run_cli("upload", "--file", args.file, "-v", "--usePool")
        if result.returncode != 0:
            print("Pool not available, falling back to regular stamp purchase...")
            result = run_cli("upload", "--file", args.file, "-v")
            if result.returncode != 0:
                print(f"Upload failed: {result.stderr or result.stdout}")
                sys.exit(1)

        output = result.stdout + "\n" + result.stderr
        stamp_id = extract_stamp_id(output)
        swarm_ref = extract_swarm_ref(result.stdout)

        if not stamp_id:
            print("WARNING: Could not extract stamp ID from verbose output")
            print("Continuing with stamps list to find stamps...")
        else:
            print(f"Stamp acquired: {stamp_id}")

        if swarm_ref:
            print(f"Swarm reference: {swarm_ref}")
    else:
        stamp_id = None
        print("\n--- Step 2: Skipped (no --file provided) ---")

    # Step 3: List stamps
    print("\n--- Step 3: List all stamps ---")
    list_stamps()

    # Step 4: Stamp info (if we have a stamp ID)
    if stamp_id:
        print(f"\n--- Step 4: Stamp details for {stamp_id[:16]}... ---")
        stamp_info(stamp_id)

        # Step 5: Stamp health check
        print(f"\n--- Step 5: Stamp health check ---")
        stamp_check(stamp_id)

        # Step 6: Attempt extend (may fail without funded wallet)
        print(f"\n--- Step 6: Attempt stamp extension ---")
        print("Note: Extension requires a funded wallet with BZZ tokens.")
        ok = stamp_extend(stamp_id)
        if not ok:
            print("Extension failed (expected if wallet is not funded).")
            print("This is normal for demo environments.")
    else:
        print("\n--- Steps 4-6: Skipped (no stamp ID available) ---")
        print("Provide --file to upload and acquire a stamp for full lifecycle demo.")

    print("\n--- Lifecycle demo complete ---")


if __name__ == "__main__":
    main()
