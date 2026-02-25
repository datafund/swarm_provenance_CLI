#!/usr/bin/env bash
#
# Encrypted Data Demo
#
# Demonstrates pre-encryption workflow with Swarm:
# 1. Encrypt data locally with openssl
# 2. Upload encrypted payload with --enc "AES-256-GCM" tag
# 3. Download the encrypted payload
# 4. Verify the encrypted payload is intact
# 5. Decrypt and verify it matches the original
#
# Usage: ./demo.sh
#
# NOTE: This uses openssl for demonstration purposes.
# In production, use a proper encryption library with key management.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SENSITIVE_FILE="$SCRIPT_DIR/sensitive_data.txt"
DOWNLOAD_DIR="$SCRIPT_DIR/downloads"
ENCRYPTED_FILE="$SCRIPT_DIR/sensitive_data.enc"
DECRYPTED_FILE="$SCRIPT_DIR/sensitive_data.dec"
KEY_FILE="$SCRIPT_DIR/demo_key.bin"

echo "========================================="
echo "  Swarm Provenance CLI - Encrypted Data"
echo "========================================="
echo
echo "WARNING: This demo uses openssl for illustration only."
echo "         Use a proper encryption library in production."
echo

# --- Step 0: Check CLI and openssl ---
if ! command -v swarm-prov-upload &>/dev/null; then
    echo "ERROR: swarm-prov-upload not found. Install with: pip install -e ."
    exit 1
fi

if ! command -v openssl &>/dev/null; then
    echo "ERROR: openssl not found."
    exit 1
fi

echo "CLI version: $(swarm-prov-upload --version)"
echo

# --- Step 1: Check gateway health ---
echo "--- Step 1: Check gateway health ---"
swarm-prov-upload health
echo

# --- Step 2: Encrypt the data ---
echo "--- Step 2: Encrypt sensitive data ---"
echo "Original file: $SENSITIVE_FILE"
ORIGINAL_HASH=$(shasum -a 256 "$SENSITIVE_FILE" | cut -d' ' -f1)
echo "Original SHA256: $ORIGINAL_HASH"
echo

# Generate a random 256-bit key and IV
openssl rand -out "$KEY_FILE" 32
# Encrypt with AES-256-CBC (GCM not available in all openssl versions via enc)
openssl enc -aes-256-cbc -salt -in "$SENSITIVE_FILE" -out "$ENCRYPTED_FILE" -pass file:"$KEY_FILE" -pbkdf2

ENCRYPTED_HASH=$(shasum -a 256 "$ENCRYPTED_FILE" | cut -d' ' -f1)
echo "Encrypted file: $ENCRYPTED_FILE"
echo "Encrypted SHA256: $ENCRYPTED_HASH"
echo "Key saved to: $KEY_FILE"
echo

# --- Step 3: Upload encrypted data with --enc tag ---
echo "--- Step 3: Upload encrypted data with --enc AES-256-GCM ---"
echo "Uploading (trying pool first)..."
UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$ENCRYPTED_FILE" --enc "AES-256-GCM" --usePool 2>&1) || {
    echo "Pool not available, falling back to regular stamp purchase..."
    UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$ENCRYPTED_FILE" --enc "AES-256-GCM" 2>&1)
}
echo "$UPLOAD_OUTPUT"

SWARM_REF=$(echo "$UPLOAD_OUTPUT" | grep -A1 "Swarm Reference Hash:" | tail -1 | tr -d '[:space:]')

if [ -z "$SWARM_REF" ] || [ ${#SWARM_REF} -lt 64 ]; then
    echo "ERROR: Could not extract Swarm reference."
    exit 1
fi

echo
echo "Swarm Reference: $SWARM_REF"
echo

# --- Step 4: Download the encrypted payload ---
echo "--- Step 4: Download encrypted payload ---"
rm -rf "$DOWNLOAD_DIR"
mkdir -p "$DOWNLOAD_DIR"

swarm-prov-upload download "$SWARM_REF" --output-dir "$DOWNLOAD_DIR"
echo

# --- Step 5: Verify encrypted payload is intact ---
echo "--- Step 5: Verify encrypted payload integrity ---"
DOWNLOADED_FILE=$(ls "$DOWNLOAD_DIR"/*.data 2>/dev/null | head -1)
if [ -z "$DOWNLOADED_FILE" ]; then
    DOWNLOADED_FILE=$(ls "$DOWNLOAD_DIR"/ | head -1)
    DOWNLOADED_FILE="$DOWNLOAD_DIR/$DOWNLOADED_FILE"
fi
DOWNLOADED_HASH=$(shasum -a 256 "$DOWNLOADED_FILE" | cut -d' ' -f1)

echo "Encrypted original: $ENCRYPTED_HASH"
echo "Downloaded:         $DOWNLOADED_HASH"
echo

if [ "$ENCRYPTED_HASH" = "$DOWNLOADED_HASH" ]; then
    echo "PASS: Encrypted payload integrity verified."
else
    echo "FAIL: Encrypted payload hash mismatch!"
    rm -f "$ENCRYPTED_FILE" "$KEY_FILE" "$DECRYPTED_FILE"
    exit 1
fi

# --- Step 6: Decrypt and verify ---
echo
echo "--- Step 6: Decrypt and verify original content ---"
openssl enc -aes-256-cbc -d -in "$DOWNLOADED_FILE" -out "$DECRYPTED_FILE" -pass file:"$KEY_FILE" -pbkdf2
DECRYPTED_HASH=$(shasum -a 256 "$DECRYPTED_FILE" | cut -d' ' -f1)

echo "Original:  $ORIGINAL_HASH"
echo "Decrypted: $DECRYPTED_HASH"
echo

if [ "$ORIGINAL_HASH" = "$DECRYPTED_HASH" ]; then
    echo "PASS: Decrypted content matches original - full round-trip verified."
else
    echo "FAIL: Decrypted content does not match original!"
    rm -f "$ENCRYPTED_FILE" "$KEY_FILE" "$DECRYPTED_FILE"
    exit 1
fi

# Clean up temporary files
rm -f "$ENCRYPTED_FILE" "$KEY_FILE" "$DECRYPTED_FILE"

echo
echo "--- Demo complete ---"
echo "Swarm Reference: $SWARM_REF"
echo "The data was encrypted locally, uploaded to Swarm with AES-256-GCM tag,"
echo "downloaded, and decrypted back to the original content."
