#!/bin/bash
# Basic Upload/Download Demo
# Demonstrates core Swarm Provenance CLI functionality

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/output"

echo "=================================="
echo "Swarm Provenance CLI - Basic Demo"
echo "=================================="
echo ""

# Check CLI is available
if ! command -v swarm-prov-upload &> /dev/null; then
    echo "ERROR: swarm-prov-upload not found in PATH"
    echo "Install with: pip install swarm-provenance-uploader"
    exit 1
fi

# Show version
echo "CLI Version:"
swarm-prov-upload --version
echo ""

# Health check
echo "Checking gateway health..."
swarm-prov-upload health
echo ""

# Step 1: Upload
echo "=================================="
echo "Step 1: Uploading sample.txt"
echo "=================================="
echo ""

UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "${SCRIPT_DIR}/sample.txt" 2>&1)
echo "$UPLOAD_OUTPUT"

# Extract Swarm reference from output
SWARM_REF=$(echo "$UPLOAD_OUTPUT" | grep -oE '[a-f0-9]{64}' | tail -1)

if [ -z "$SWARM_REF" ]; then
    echo "ERROR: Could not extract Swarm reference from output"
    exit 1
fi

echo ""
echo "Swarm reference: ${SWARM_REF}"
echo ""

# Step 2: Download
echo "=================================="
echo "Step 2: Downloading and verifying"
echo "=================================="
echo ""

mkdir -p "${OUTPUT_DIR}"
swarm-prov-upload download "${SWARM_REF}" --output-dir "${OUTPUT_DIR}"

echo ""

# Step 3: Examine results
echo "=================================="
echo "Step 3: Examining output files"
echo "=================================="
echo ""

echo "Files created in ${OUTPUT_DIR}:"
ls -la "${OUTPUT_DIR}"
echo ""

# Show metadata
META_FILE="${OUTPUT_DIR}/${SWARM_REF}.meta.json"
if [ -f "$META_FILE" ]; then
    echo "Metadata content (first 500 chars):"
    head -c 500 "$META_FILE"
    echo ""
    echo "..."
    echo ""
fi

# Show data content
DATA_FILE="${OUTPUT_DIR}/${SWARM_REF}.data"
if [ -f "$DATA_FILE" ]; then
    echo "Downloaded data content:"
    cat "$DATA_FILE"
    echo ""
fi

# Compare original and downloaded
echo "=================================="
echo "Step 4: Verification"
echo "=================================="
echo ""

ORIG_HASH=$(shasum -a 256 "${SCRIPT_DIR}/sample.txt" | cut -d' ' -f1)
DOWN_HASH=$(shasum -a 256 "$DATA_FILE" | cut -d' ' -f1)

echo "Original file hash:   ${ORIG_HASH}"
echo "Downloaded file hash: ${DOWN_HASH}"
echo ""

if [ "$ORIG_HASH" = "$DOWN_HASH" ]; then
    echo "SUCCESS: Files match! Integrity verified."
else
    echo "WARNING: Hash mismatch detected!"
fi

echo ""
echo "=================================="
echo "Demo complete!"
echo "=================================="
echo ""
echo "Swarm reference for future retrieval: ${SWARM_REF}"
echo "Output directory: ${OUTPUT_DIR}"
