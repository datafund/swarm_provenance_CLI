#!/usr/bin/env bash
#
# Basic Upload/Download Demo
#
# Demonstrates the core Swarm Provenance workflow:
# 1. Upload a file to Swarm
# 2. Download it back
# 3. Verify data integrity
#
# Usage: ./demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAMPLE_FILE="$SCRIPT_DIR/sample.txt"
DOWNLOAD_DIR="$SCRIPT_DIR/downloads"

echo "======================================"
echo "  Swarm Provenance CLI - Basic Demo"
echo "======================================"
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

# --- Step 2: Upload the sample file ---
echo "--- Step 2: Upload sample file ---"
echo "File: $SAMPLE_FILE"
echo "Size: $(wc -c < "$SAMPLE_FILE") bytes"
echo "SHA256: $(shasum -a 256 "$SAMPLE_FILE" | cut -d' ' -f1)"
echo

echo "Uploading with --usePool (faster stamp acquisition)..."
UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$SAMPLE_FILE" --usePool --json 2>&1)
echo "$UPLOAD_OUTPUT" | python3 -m json.tool 2>/dev/null || echo "$UPLOAD_OUTPUT"

# Extract Swarm reference from JSON output
SWARM_REF=$(echo "$UPLOAD_OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['swarm_hash'])" 2>/dev/null)

if [ -z "$SWARM_REF" ]; then
    echo "ERROR: Could not extract Swarm reference from upload output."
    echo "Raw output: $UPLOAD_OUTPUT"
    exit 1
fi

echo
echo "Swarm Reference: $SWARM_REF"
echo

# --- Step 3: Download the file ---
echo "--- Step 3: Download and verify ---"
rm -rf "$DOWNLOAD_DIR"
mkdir -p "$DOWNLOAD_DIR"

swarm-prov-upload download "$SWARM_REF" --output-dir "$DOWNLOAD_DIR"
echo

# --- Step 4: Verify integrity ---
echo "--- Step 4: Compare SHA-256 hashes ---"
ORIGINAL_HASH=$(shasum -a 256 "$SAMPLE_FILE" | cut -d' ' -f1)
DOWNLOADED_FILE=$(ls "$DOWNLOAD_DIR"/ | head -1)
DOWNLOADED_HASH=$(shasum -a 256 "$DOWNLOAD_DIR/$DOWNLOADED_FILE" | cut -d' ' -f1)

echo "Original:   $ORIGINAL_HASH"
echo "Downloaded: $DOWNLOADED_HASH"
echo

if [ "$ORIGINAL_HASH" = "$DOWNLOADED_HASH" ]; then
    echo "PASS: Data integrity verified - hashes match."
else
    echo "FAIL: Hash mismatch - data may have been tampered with!"
    exit 1
fi

echo
echo "--- Demo complete ---"
echo "Swarm Reference: $SWARM_REF"
echo "Use this hash to retrieve the data from any Swarm gateway."
