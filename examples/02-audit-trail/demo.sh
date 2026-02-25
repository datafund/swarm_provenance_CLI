#!/usr/bin/env bash
#
# Audit Trail Demo
#
# Demonstrates immutable compliance audit records on Swarm:
# 1. Upload multiple audit records with --std "AUDIT-LOG-V1"
# 2. Download and verify one record
# 3. Prove data integrity via SHA-256
#
# Usage: ./demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOWNLOAD_DIR="$SCRIPT_DIR/downloads"

echo "======================================"
echo "  Swarm Provenance CLI - Audit Trail"
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

# --- Step 2: Upload audit records ---
echo "--- Step 2: Upload audit records with --std AUDIT-LOG-V1 ---"

RECORDS=("audit_record_001.json" "audit_record_002.json" "audit_record_003.json")
declare -a REFS=()

for record in "${RECORDS[@]}"; do
    FILE="$SCRIPT_DIR/$record"
    echo "Uploading: $record"
    echo "  SHA256: $(shasum -a 256 "$FILE" | cut -d' ' -f1)"

    UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$FILE" --std "AUDIT-LOG-V1" --usePool 2>&1) || {
        echo "  Pool not available, falling back to regular stamp purchase..."
        UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$FILE" --std "AUDIT-LOG-V1" 2>&1)
    }

    SWARM_REF=$(echo "$UPLOAD_OUTPUT" | grep -A1 "Swarm Reference Hash:" | tail -1 | tr -d '[:space:]')

    if [ -z "$SWARM_REF" ] || [ ${#SWARM_REF} -lt 64 ]; then
        echo "ERROR: Could not extract Swarm reference for $record"
        echo "Raw output: $UPLOAD_OUTPUT"
        exit 1
    fi

    REFS+=("$SWARM_REF")
    echo "  Reference: $SWARM_REF"
    echo
done

echo "All ${#RECORDS[@]} audit records uploaded."
echo

# --- Step 3: Download and verify one record ---
echo "--- Step 3: Download and verify first record ---"
rm -rf "$DOWNLOAD_DIR"
mkdir -p "$DOWNLOAD_DIR"

VERIFY_REF="${REFS[0]}"
echo "Downloading: $VERIFY_REF"
swarm-prov-upload download "$VERIFY_REF" --output-dir "$DOWNLOAD_DIR"
echo

# --- Step 4: Verify integrity ---
echo "--- Step 4: Compare SHA-256 hashes ---"
ORIGINAL_HASH=$(shasum -a 256 "$SCRIPT_DIR/audit_record_001.json" | cut -d' ' -f1)
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
    echo "PASS: Audit record integrity verified - hashes match."
else
    echo "FAIL: Hash mismatch - audit record may have been tampered with!"
    exit 1
fi

echo
echo "--- Demo complete ---"
echo "Uploaded ${#RECORDS[@]} audit records with AUDIT-LOG-V1 standard."
echo "Swarm References:"
for i in "${!RECORDS[@]}"; do
    echo "  ${RECORDS[$i]}: ${REFS[$i]}"
done
echo "These immutable records can be retrieved from any Swarm gateway."
