#!/usr/bin/env python3
"""
Encrypted Data Demo - Python Version

Demonstrates pre-encryption workflow with Swarm:
1. Encrypt data locally (XOR cipher for demo purposes)
2. Upload encrypted payload with --enc "AES-256-GCM" tag
3. Download the encrypted payload
4. Verify the encrypted payload is intact
5. Decrypt and verify it matches the original

Usage:
    python run_demo.py
    python run_demo.py --file /path/to/sensitive.txt

WARNING: This demo uses XOR cipher for illustration only.
         NOT PRODUCTION-SAFE — use a real encryption library (e.g., cryptography)
         with proper key management for actual sensitive data.
"""

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


def sha256_file(path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """Compute SHA-256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()


def run_cli(*args) -> subprocess.CompletedProcess:
    """Run a swarm-prov-upload CLI command."""
    cmd = ["swarm-prov-upload"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


def extract_swarm_ref(output: str) -> str:
    """Extract Swarm reference hash from CLI output."""
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if "Swarm Reference Hash:" in line and i + 1 < len(lines):
            ref = lines[i + 1].strip()
            if len(ref) >= 64:
                return ref
    return ""


def xor_encrypt(data: bytes, key: bytes) -> bytes:
    """XOR cipher — symmetric, same function encrypts and decrypts.

    WARNING: NOT PRODUCTION-SAFE. This is a demo cipher only.
    Use a real encryption library (e.g., cryptography, PyCryptodome) in production.
    """
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))


def main():
    parser = argparse.ArgumentParser(description="Encrypted data upload demo")
    parser.add_argument(
        "--file", "-f",
        default=str(SCRIPT_DIR / "sensitive_data.txt"),
        help="File to encrypt and upload (default: sensitive_data.txt)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.file):
        print(f"ERROR: File not found: {args.file}")
        sys.exit(1)

    print("=" * 55)
    print("  Swarm Provenance CLI - Encrypted Data (Python)")
    print("=" * 55)
    print()
    print("WARNING: This demo uses XOR cipher for illustration only.")
    print("         Use a real encryption library in production.")

    # --- Step 1: Check health ---
    print("\n--- Step 1: Check gateway health ---")
    result = run_cli("health")
    if result.returncode != 0:
        print(f"Gateway not available: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    # --- Step 2: Encrypt the data ---
    print("\n--- Step 2: Encrypt sensitive data ---")
    with open(args.file, "rb") as f:
        original_data = f.read()

    original_hash = sha256_bytes(original_data)
    print(f"Original file:   {args.file}")
    print(f"Original SHA256: {original_hash}")

    # Generate random key and encrypt
    key = os.urandom(32)
    encrypted_data = xor_encrypt(original_data, key)
    encrypted_hash = sha256_bytes(encrypted_data)

    # Write encrypted file
    encrypted_path = str(SCRIPT_DIR / "sensitive_data.enc")
    with open(encrypted_path, "wb") as f:
        f.write(encrypted_data)

    print(f"Encrypted SHA256: {encrypted_hash}")
    print(f"Key length: {len(key)} bytes (kept in memory)")

    # --- Step 3: Upload encrypted data ---
    print("\n--- Step 3: Upload encrypted data with --enc AES-256-GCM ---")
    print("Uploading (trying pool first)...")
    result = run_cli("upload", "--file", encrypted_path, "--enc", "AES-256-GCM", "--usePool")
    if result.returncode != 0:
        print("Pool not available, falling back to regular stamp purchase...")
        result = run_cli("upload", "--file", encrypted_path, "--enc", "AES-256-GCM")
        if result.returncode != 0:
            print(f"Upload failed: {result.stderr or result.stdout}")
            os.remove(encrypted_path)
            sys.exit(1)

    print(result.stdout.strip())

    swarm_ref = extract_swarm_ref(result.stdout)
    if not swarm_ref:
        print("Could not extract Swarm reference from output")
        os.remove(encrypted_path)
        sys.exit(1)

    print(f"\nSwarm Reference: {swarm_ref}")

    # --- Step 4: Download encrypted payload ---
    print("\n--- Step 4: Download encrypted payload ---")
    download_dir = str(SCRIPT_DIR / "downloads")
    os.makedirs(download_dir, exist_ok=True)
    for f in os.listdir(download_dir):
        os.remove(os.path.join(download_dir, f))

    result = run_cli("download", swarm_ref, "--output-dir", download_dir)
    if result.returncode != 0:
        print(f"Download failed: {result.stderr or result.stdout}")
        os.remove(encrypted_path)
        sys.exit(1)
    print(result.stdout.strip())

    # --- Step 5: Verify encrypted payload integrity ---
    print("\n--- Step 5: Verify encrypted payload integrity ---")
    downloaded_files = os.listdir(download_dir)
    if not downloaded_files:
        print("ERROR: No files in download directory")
        os.remove(encrypted_path)
        sys.exit(1)

    data_files = [f for f in downloaded_files if f.endswith(".data")]
    if data_files:
        downloaded_file = os.path.join(download_dir, data_files[0])
    else:
        downloaded_file = os.path.join(download_dir, downloaded_files[0])

    downloaded_hash = sha256_file(downloaded_file)
    print(f"Encrypted original: {encrypted_hash}")
    print(f"Downloaded:         {downloaded_hash}")

    if encrypted_hash != downloaded_hash:
        print("\nFAIL: Encrypted payload hash mismatch!")
        os.remove(encrypted_path)
        sys.exit(1)
    print("\nPASS: Encrypted payload integrity verified.")

    # --- Step 6: Decrypt and verify ---
    print("\n--- Step 6: Decrypt and verify original content ---")
    with open(downloaded_file, "rb") as f:
        downloaded_encrypted = f.read()

    decrypted_data = xor_encrypt(downloaded_encrypted, key)
    decrypted_hash = sha256_bytes(decrypted_data)

    print(f"Original:  {original_hash}")
    print(f"Decrypted: {decrypted_hash}")

    if original_hash == decrypted_hash:
        print("\nPASS: Decrypted content matches original - full round-trip verified.")
    else:
        print("\nFAIL: Decrypted content does not match original!")
        os.remove(encrypted_path)
        sys.exit(1)

    # Clean up
    os.remove(encrypted_path)

    # --- Summary ---
    print("\n--- Summary ---")
    print(f"Swarm Reference: {swarm_ref}")
    print("Data was encrypted locally, uploaded with AES-256-GCM metadata tag,")
    print("downloaded, and decrypted back to the original content.")


if __name__ == "__main__":
    main()
