#!/usr/bin/env python3
"""
Encrypt and Upload Workflow

Demonstrates encrypting data locally before uploading to Swarm.
Uses Fernet (AES-128-CBC with HMAC) for symmetric encryption.

Usage:
    python encrypt_upload.py <input_file> [--output-dir <dir>]
"""

import subprocess
import sys
import json
import re
import argparse
from pathlib import Path
from datetime import datetime, timezone

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("ERROR: cryptography package required")
    print("Install with: pip install cryptography")
    sys.exit(1)


def run_command(args: list) -> tuple:
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def extract_ref(output: str) -> str:
    match = re.search(r"[a-f0-9]{64}", output)
    return match.group(0) if match else ""


def encrypt_file(input_path: Path, output_dir: Path) -> tuple:
    """
    Encrypt a file using Fernet.

    Returns:
        Tuple of (encrypted_file_path, key_file_path, key_bytes)
    """
    # Generate key
    key = Fernet.generate_key()
    cipher = Fernet(key)

    # Read and encrypt
    with open(input_path, "rb") as f:
        plaintext = f.read()

    ciphertext = cipher.encrypt(plaintext)

    # Save encrypted file
    encrypted_path = output_dir / f"{input_path.name}.enc"
    with open(encrypted_path, "wb") as f:
        f.write(ciphertext)

    # Save key (in production, use secure key storage!)
    key_path = output_dir / f"{input_path.name}.key"
    with open(key_path, "wb") as f:
        f.write(key)

    return encrypted_path, key_path, key


def main():
    parser = argparse.ArgumentParser(
        description="Encrypt a file and upload to Swarm"
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="File to encrypt and upload"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./output"),
        help="Directory for encrypted files and keys"
    )

    args = parser.parse_args()

    if not args.input_file.exists():
        print(f"ERROR: File not found: {args.input_file}")
        sys.exit(1)

    args.output_dir.mkdir(exist_ok=True)

    print("=" * 55)
    print("Swarm Provenance CLI - Encrypt & Upload")
    print("=" * 55)
    print()

    # Check CLI
    returncode, stdout, _ = run_command(["swarm-prov-upload", "--version"])
    if returncode != 0:
        print("ERROR: swarm-prov-upload not found")
        sys.exit(1)

    # Step 1: Encrypt
    print("Step 1: Encrypting file")
    print(f"  Input: {args.input_file}")

    encrypted_path, key_path, key = encrypt_file(args.input_file, args.output_dir)

    print(f"  Encrypted: {encrypted_path}")
    print(f"  Key saved: {key_path}")
    print()
    print("  WARNING: Store the key securely! Without it, data cannot be decrypted.")
    print()

    # Step 2: Upload
    print("Step 2: Uploading encrypted file")
    print()

    returncode, stdout, stderr = run_command([
        "swarm-prov-upload", "upload",
        "--file", str(encrypted_path),
        "--enc", "FERNET-AES128-CBC",
    ])

    if returncode != 0:
        print(f"ERROR: Upload failed: {stderr}")
        sys.exit(1)

    print(stdout)

    swarm_ref = extract_ref(stdout)
    print(f"Swarm reference: {swarm_ref}")
    print()

    # Step 3: Save manifest
    print("Step 3: Creating encryption manifest")
    print()

    manifest = {
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "original_filename": args.input_file.name,
        "encrypted_filename": encrypted_path.name,
        "encryption": {
            "algorithm": "FERNET-AES128-CBC",
            "key_file": key_path.name,
            "note": "Key stored separately - never upload key to Swarm!"
        },
        "swarm_ref": swarm_ref,
        "decryption_instructions": (
            f"python decrypt_download.py {swarm_ref} "
            f"--key-file {key_path} --output-dir ./decrypted"
        )
    }

    manifest_path = args.output_dir / f"{args.input_file.name}.manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"Manifest saved: {manifest_path}")
    print()
    print(json.dumps(manifest, indent=2))
    print()

    print("=" * 55)
    print("Upload complete!")
    print("=" * 55)
    print()
    print("To decrypt later:")
    print(f"  python decrypt_download.py {swarm_ref} \\")
    print(f"    --key-file {key_path} \\")
    print(f"    --output-dir ./decrypted")

    return 0


if __name__ == "__main__":
    sys.exit(main())
