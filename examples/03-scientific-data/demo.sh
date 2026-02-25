#!/usr/bin/env bash
#
# Scientific Data Demo
#
# Demonstrates research data archival on Swarm:
# 1. Upload experiment metadata with --std "PROV-O" --duration 720 (30 days)
# 2. Upload experiment results CSV
# 3. Download and verify the CSV data
#
# Usage: ./demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
METADATA_FILE="$SCRIPT_DIR/dataset_metadata.json"
RESULTS_FILE="$SCRIPT_DIR/experiment_results.csv"
DOWNLOAD_DIR="$SCRIPT_DIR/downloads"

echo "========================================="
echo "  Swarm Provenance CLI - Scientific Data"
echo "========================================="
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

# --- Step 2: Upload metadata with PROV-O standard and 30-day retention ---
echo "--- Step 2: Upload experiment metadata (PROV-O, 30-day retention) ---"
echo "File: $METADATA_FILE"
echo "SHA256: $(shasum -a 256 "$METADATA_FILE" | cut -d' ' -f1)"
echo

echo "Uploading with --std PROV-O --duration 720 (trying pool first)..."
UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$METADATA_FILE" --std "PROV-O" --duration 720 --usePool 2>&1) || {
    echo "Pool not available, trying without pool..."
    UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$METADATA_FILE" --std "PROV-O" --duration 720 2>&1) || {
        echo "Long duration not available, falling back to default duration..."
        UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$METADATA_FILE" --std "PROV-O" --usePool 2>&1) || {
            UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$METADATA_FILE" --std "PROV-O" 2>&1)
        }
    }
}
echo "$UPLOAD_OUTPUT"

META_REF=$(echo "$UPLOAD_OUTPUT" | grep -A1 "Swarm Reference Hash:" | tail -1 | tr -d '[:space:]')

if [ -z "$META_REF" ] || [ ${#META_REF} -lt 64 ]; then
    echo "ERROR: Could not extract Swarm reference for metadata."
    exit 1
fi

echo
echo "Metadata Reference: $META_REF"
echo

# --- Step 3: Upload experiment results CSV ---
echo "--- Step 3: Upload experiment results CSV ---"
echo "File: $RESULTS_FILE"
echo "SHA256: $(shasum -a 256 "$RESULTS_FILE" | cut -d' ' -f1)"
echo

echo "Uploading (trying pool first)..."
UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$RESULTS_FILE" --std "PROV-O" --usePool 2>&1) || {
    echo "Pool not available, falling back to regular stamp purchase..."
    UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$RESULTS_FILE" --std "PROV-O" 2>&1)
}
echo "$UPLOAD_OUTPUT"

CSV_REF=$(echo "$UPLOAD_OUTPUT" | grep -A1 "Swarm Reference Hash:" | tail -1 | tr -d '[:space:]')

if [ -z "$CSV_REF" ] || [ ${#CSV_REF} -lt 64 ]; then
    echo "ERROR: Could not extract Swarm reference for results CSV."
    exit 1
fi

echo
echo "Results Reference: $CSV_REF"
echo

# --- Step 4: Download and verify the CSV ---
echo "--- Step 4: Download and verify results CSV ---"
rm -rf "$DOWNLOAD_DIR"
mkdir -p "$DOWNLOAD_DIR"

swarm-prov-upload download "$CSV_REF" --output-dir "$DOWNLOAD_DIR"
echo

echo "--- Step 5: Compare SHA-256 hashes ---"
ORIGINAL_HASH=$(shasum -a 256 "$RESULTS_FILE" | cut -d' ' -f1)
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
    echo "PASS: Experiment data integrity verified - hashes match."
else
    echo "FAIL: Hash mismatch - data may have been corrupted!"
    exit 1
fi

echo
echo "--- Demo complete ---"
echo "Metadata Reference: $META_REF"
echo "Results Reference:  $CSV_REF"
echo "Both datasets are archived on Swarm with PROV-O provenance standard."
