#!/usr/bin/env bash
#
# Verification & Integrity Demo
#
# Demonstrates data verification and tamper detection:
# 1. Upload original document
# 2. Download and verify integrity (hash match)
# 3. Tamper test: compare original vs tampered file hashes
# 4. Download with --verify flag (notary verification)
# 5. Print verification report
#
# Usage: ./demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ORIGINAL_FILE="$SCRIPT_DIR/sample_document.txt"
TAMPERED_FILE="$SCRIPT_DIR/sample_document_tampered.txt"
DOWNLOAD_DIR="$SCRIPT_DIR/downloads"

echo "================================================="
echo "  Swarm Provenance CLI - Verification & Integrity"
echo "================================================="
echo

# --- Step 0: Check CLI is installed ---
if ! command -v swarm-prov-upload &>/dev/null; then
    echo "ERROR: swarm-prov-upload not found. Install with: pip install -e ."
    exit 1
fi

echo "CLI version: $(swarm-prov-upload --version)"
echo

# --- Step 1: Check gateway health ---
echo "--- Step 1: Check gateway health ---"
swarm-prov-upload health
echo

# --- Step 2: Upload original document ---
echo "--- Step 2: Upload original document ---"
ORIGINAL_HASH=$(shasum -a 256 "$ORIGINAL_FILE" | cut -d' ' -f1)
echo "Uploading: sample_document.txt"
echo "  SHA256: $ORIGINAL_HASH"

UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$ORIGINAL_FILE" --usePool 2>&1) || {
    echo "  Pool not available, falling back to regular stamp purchase..."
    UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$ORIGINAL_FILE" 2>&1)
}

SWARM_REF=$(echo "$UPLOAD_OUTPUT" | grep -A1 "Swarm Reference Hash:" | tail -1 | tr -d '[:space:]')

if [ -z "$SWARM_REF" ] || [ ${#SWARM_REF} -lt 64 ]; then
    echo "ERROR: Could not extract Swarm reference"
    echo "Raw output: $UPLOAD_OUTPUT"
    exit 1
fi

echo "  Reference: $SWARM_REF"
echo

# --- Step 3: Download and verify integrity ---
echo "--- Step 3: Download and verify integrity ---"
rm -rf "$DOWNLOAD_DIR"
mkdir -p "$DOWNLOAD_DIR"

echo "Downloading: $SWARM_REF"
swarm-prov-upload download "$SWARM_REF" --output-dir "$DOWNLOAD_DIR"
echo

DOWNLOADED_FILE=$(ls "$DOWNLOAD_DIR"/*.data 2>/dev/null | head -1)
if [ -z "$DOWNLOADED_FILE" ]; then
    DOWNLOADED_FILE=$(ls "$DOWNLOAD_DIR"/ | head -1)
    DOWNLOADED_FILE="$DOWNLOAD_DIR/$DOWNLOADED_FILE"
fi
DOWNLOADED_HASH=$(shasum -a 256 "$DOWNLOADED_FILE" | cut -d' ' -f1)

echo "Original:   $ORIGINAL_HASH"
echo "Downloaded: $DOWNLOADED_HASH"
echo

if [ "$ORIGINAL_HASH" = "$DOWNLOADED_HASH" ]; then
    echo "PASS: Document integrity verified - hashes match."
else
    echo "FAIL: Hash mismatch - document may have been tampered with!"
    exit 1
fi
echo

# --- Step 4: Tamper detection test ---
echo "--- Step 4: Tamper detection test ---"
TAMPERED_HASH=$(shasum -a 256 "$TAMPERED_FILE" | cut -d' ' -f1)
echo "Original document hash:  $ORIGINAL_HASH"
echo "Tampered document hash:  $TAMPERED_HASH"
echo

if [ "$ORIGINAL_HASH" != "$TAMPERED_HASH" ]; then
    echo "PASS: Tamper detection works - hashes differ."
    echo "Even a small change (e.g., '24 months' -> '36 months') produces"
    echo "a completely different SHA-256 hash, making tampering detectable."
else
    echo "FAIL: Hashes should differ for different content!"
    exit 1
fi
echo

# --- Step 5: Download with --verify (notary) ---
echo "--- Step 5: Download with --verify (notary verification) ---"
rm -rf "$DOWNLOAD_DIR"
mkdir -p "$DOWNLOAD_DIR"

echo "Downloading with signature verification..."
VERIFY_OUTPUT=$(swarm-prov-upload download "$SWARM_REF" --output-dir "$DOWNLOAD_DIR" --verify 2>&1) || true
echo "$VERIFY_OUTPUT"
echo
echo "Note: --verify checks for notary signatures. If no signatures exist,"
echo "the download still succeeds but reports 'no signatures found'."
echo

# --- Step 6: Verification report ---
echo "--- Step 6: Verification Report ---"
echo "================================================="
echo "  Document: sample_document.txt"
echo "  Swarm Reference: $SWARM_REF"
echo "  SHA-256 Hash: $ORIGINAL_HASH"
echo "  Integrity: VERIFIED"
echo "  Tamper Detection: WORKING"
echo "================================================="
echo
echo "PASS: All verification checks passed."
