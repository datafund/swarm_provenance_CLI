#!/usr/bin/env python3
"""
Download and Decrypt Workflow

Downloads encrypted data from Swarm and decrypts it locally.

Usage:
    python decrypt_download.py <swarm_ref> --key-file <key.key> [--output-dir <dir>]
"""

import subprocess
import sys
import json
import argparse
from pathlib import Path

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    print("ERROR: cryptography package required")
    print("Install with: pip install cryptography")
    sys.exit(1)


def run_command(args: list) -> tuple:
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def decrypt_file(encrypted_path: Path, key: bytes, output_path: Path) -> bool:
    """
    Decrypt a file using Fernet.

    Returns:
        True if successful, False otherwise
    """
    try:
        cipher = Fernet(key)

        with open(encrypted_path, "rb") as f:
            ciphertext = f.read()

        plaintext = cipher.decrypt(ciphertext)

        with open(output_path, "wb") as f:
            f.write(plaintext)

        return True

    except InvalidToken:
        print("ERROR: Decryption failed - invalid key or corrupted data")
        return False
    except Exception as e:
        print(f"ERROR: Decryption failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Download from Swarm and decrypt"
    )
    parser.add_argument(
        "swarm_ref",
        help="Swarm reference hash (64 hex characters)"
    )
    parser.add_argument(
        "--key-file",
        type=Path,
        required=True,
        help="Path to the encryption key file"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./decrypted"),
        help="Directory for decrypted output"
    )
    parser.add_argument(
        "--output-name",
        help="Output filename (default: original name from metadata)"
    )

    args = parser.parse_args()

    if not args.key_file.exists():
        print(f"ERROR: Key file not found: {args.key_file}")
        sys.exit(1)

    args.output_dir.mkdir(exist_ok=True)
    download_dir = args.output_dir / "downloaded"
    download_dir.mkdir(exist_ok=True)

    print("=" * 55)
    print("Swarm Provenance CLI - Download & Decrypt")
    print("=" * 55)
    print()

    # Step 1: Download
    print("Step 1: Downloading from Swarm")
    print(f"  Reference: {args.swarm_ref}")
    print()

    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "download",
        args.swarm_ref,
        "--output-dir", str(download_dir),
    ])

    if returncode != 0:
        print(f"ERROR: Download failed: {stderr}")
        sys.exit(1)

    print(stdout)

    # Find downloaded files
    data_file = download_dir / f"{args.swarm_ref}.data"
    meta_file = download_dir / f"{args.swarm_ref}.meta.json"

    if not data_file.exists():
        print(f"ERROR: Downloaded data not found: {data_file}")
        sys.exit(1)

    # Step 2: Check metadata
    print("Step 2: Checking encryption metadata")
    print()

    encryption_info = None
    if meta_file.exists():
        with open(meta_file) as f:
            metadata = json.load(f)
        encryption_info = metadata.get("encryption")
        print(f"  Encryption field: {encryption_info}")
    else:
        print("  WARNING: No metadata file found")
    print()

    # Step 3: Load key
    print("Step 3: Loading encryption key")
    print(f"  Key file: {args.key_file}")

    with open(args.key_file, "rb") as f:
        key = f.read()

    print(f"  Key loaded ({len(key)} bytes)")
    print()

    # Step 4: Decrypt
    print("Step 4: Decrypting data")
    print()

    # Determine output filename
    if args.output_name:
        output_name = args.output_name
    else:
        # Try to get original name from encrypted filename
        output_name = data_file.name.replace(".data", "")
        if output_name.endswith(".enc"):
            output_name = output_name[:-4]
        else:
            output_name = f"decrypted_{args.swarm_ref[:8]}"

    output_path = args.output_dir / output_name

    success = decrypt_file(data_file, key, output_path)

    if not success:
        sys.exit(1)

    print(f"  Decrypted: {output_path}")
    print(f"  Size: {output_path.stat().st_size} bytes")
    print()

    # Show preview
    print("Step 5: Content preview")
    print()

    try:
        content = output_path.read_text()
        lines = content.split("\n")[:10]
        for line in lines:
            print(f"  {line[:80]}")
        if len(content.split("\n")) > 10:
            print("  ...")
    except UnicodeDecodeError:
        print("  (Binary content - cannot preview)")
    print()

    print("=" * 55)
    print("Decryption complete!")
    print("=" * 55)
    print()
    print(f"Output: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
