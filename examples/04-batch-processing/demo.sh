#!/usr/bin/env bash
#
# Batch Processing Demo
#
# Demonstrates uploading multiple files with stamp reuse:
# 1. Upload first file with --size medium -v to capture stamp ID
# 2. Upload remaining files with --stamp-id (reuses stamp, skips purchase)
# 3. Build a manifest of all uploaded files
# 4. Download and verify one file
#
# Usage: ./demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAMPLE_DIR="$SCRIPT_DIR/sample_files"
DOWNLOAD_DIR="$SCRIPT_DIR/downloads"

echo "======================================"
echo "  Swarm Provenance CLI - Batch Upload"
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

# --- Step 2: Upload first file with verbose to capture stamp ID ---
echo "--- Step 2: Upload first file with --size medium -v ---"
FIRST_FILE="$SAMPLE_DIR/log_entry_001.json"
echo "Uploading: log_entry_001.json"
echo "  SHA256: $(shasum -a 256 "$FIRST_FILE" | cut -d' ' -f1)"

UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$FIRST_FILE" --size medium -v --usePool 2>&1) || {
    echo "  Pool not available, falling back to regular stamp purchase..."
    UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$FIRST_FILE" --size medium -v 2>&1)
}

FIRST_REF=$(echo "$UPLOAD_OUTPUT" | grep -A1 "Swarm Reference Hash:" | tail -1 | tr -d '[:space:]')
if [ -z "$FIRST_REF" ] || [ ${#FIRST_REF} -lt 64 ]; then
    echo "ERROR: Could not extract Swarm reference"
    echo "Raw output: $UPLOAD_OUTPUT"
    exit 1
fi

# Extract stamp ID from verbose output
STAMP_ID=$(echo "$UPLOAD_OUTPUT" | grep "Stamp ID Received:" | awk -F'Stamp ID Received: ' '{print $2}' | awk '{print $1}' | tr -d '[:space:]')
if [ -z "$STAMP_ID" ] || [ ${#STAMP_ID} -lt 16 ]; then
    echo "WARNING: Could not extract stamp ID from verbose output"
    echo "Subsequent uploads will purchase new stamps"
    USE_STAMP=""
else
    echo "  Stamp ID captured: ${STAMP_ID:0:16}..."
    USE_STAMP="--stamp-id $STAMP_ID"
fi

echo "  Reference: $FIRST_REF"
echo

# --- Step 3: Upload remaining files with stamp reuse ---
echo "--- Step 3: Upload remaining files with stamp reuse ---"
declare -A MANIFEST
MANIFEST["log_entry_001.json"]="$FIRST_REF"

REMAINING=("log_entry_002.json" "log_entry_003.json")
for entry in "${REMAINING[@]}"; do
    FILE="$SAMPLE_DIR/$entry"
    echo "Uploading: $entry (reusing stamp)"
    echo "  SHA256: $(shasum -a 256 "$FILE" | cut -d' ' -f1)"

    if [ -n "$USE_STAMP" ]; then
        # shellcheck disable=SC2086
        UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$FILE" $USE_STAMP 2>&1)
    else
        UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$FILE" --usePool 2>&1) || {
            echo "  Pool not available, falling back to regular stamp purchase..."
            UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$FILE" 2>&1)
        }
    fi

    SWARM_REF=$(echo "$UPLOAD_OUTPUT" | grep -A1 "Swarm Reference Hash:" | tail -1 | tr -d '[:space:]')

    if [ -z "$SWARM_REF" ] || [ ${#SWARM_REF} -lt 64 ]; then
        echo "ERROR: Could not extract Swarm reference for $entry"
        echo "Raw output: $UPLOAD_OUTPUT"
        exit 1
    fi

    MANIFEST["$entry"]="$SWARM_REF"
    echo "  Reference: $SWARM_REF"
    echo
done

echo "All ${#MANIFEST[@]} files uploaded."
echo

# --- Step 4: Build manifest ---
echo "--- Step 4: Build manifest ---"
MANIFEST_FILE="$SCRIPT_DIR/manifest.json"
echo "{" > "$MANIFEST_FILE"
FIRST_ENTRY=true
for key in $(echo "${!MANIFEST[@]}" | tr ' ' '\n' | sort); do
    if [ "$FIRST_ENTRY" = true ]; then
        FIRST_ENTRY=false
    else
        echo "," >> "$MANIFEST_FILE"
    fi
    printf '  "%s": "%s"' "$key" "${MANIFEST[$key]}" >> "$MANIFEST_FILE"
done
echo "" >> "$MANIFEST_FILE"
echo "}" >> "$MANIFEST_FILE"
echo "Manifest saved: $MANIFEST_FILE"
cat "$MANIFEST_FILE"
echo

# --- Step 5: Download and verify one file ---
echo "--- Step 5: Download and verify log_entry_001.json ---"
rm -rf "$DOWNLOAD_DIR"
mkdir -p "$DOWNLOAD_DIR"

echo "Downloading: $FIRST_REF"
swarm-prov-upload download "$FIRST_REF" --output-dir "$DOWNLOAD_DIR"
echo

# --- Step 6: Verify integrity ---
echo "--- Step 6: Compare SHA-256 hashes ---"
ORIGINAL_HASH=$(shasum -a 256 "$FIRST_FILE" | cut -d' ' -f1)
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
    echo "PASS: Batch upload integrity verified - hashes match."
else
    echo "FAIL: Hash mismatch - data integrity compromised!"
    exit 1
fi

echo
echo "--- Demo complete ---"
echo "Uploaded ${#MANIFEST[@]} files with stamp reuse."
echo "Manifest: $MANIFEST_FILE"
