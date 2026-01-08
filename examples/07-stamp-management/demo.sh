#!/bin/bash
# Stamp Management Workflow Demo
# Demonstrates stamp lifecycle operations

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/output"

echo "=============================================="
echo "Swarm Provenance CLI - Stamp Management Demo"
echo "=============================================="
echo ""

if ! command -v swarm-prov-upload &> /dev/null; then
    echo "ERROR: swarm-prov-upload not found"
    exit 1
fi

swarm-prov-upload health
echo ""

mkdir -p "${OUTPUT_DIR}"

# Step 1: List existing stamps
echo "=============================================="
echo "Step 1: List All Stamps"
echo "=============================================="
echo ""

swarm-prov-upload stamps list 2>&1 || echo "No stamps found or listing failed"

echo ""

# Step 2: Create a stamp by uploading
echo "=============================================="
echo "Step 2: Create a New Stamp (via upload)"
echo "=============================================="
echo ""

# Create sample file
SAMPLE_FILE="${OUTPUT_DIR}/stamp_demo.txt"
echo "Sample file for stamp management demo - $(date)" > "$SAMPLE_FILE"

UPLOAD_OUTPUT=$(swarm-prov-upload upload \
    --file "$SAMPLE_FILE" \
    --size small \
    2>&1)

echo "$UPLOAD_OUTPUT"

# Try to extract stamp ID
STAMP_ID=$(echo "$UPLOAD_OUTPUT" | grep -oE 'Stamp purchased: [a-f0-9]+' | cut -d' ' -f3 || \
           echo "$UPLOAD_OUTPUT" | grep -oE 'stamp_id.*[a-f0-9]{64}' | grep -oE '[a-f0-9]{64}' | head -1 || \
           echo "")

echo ""

if [ -z "$STAMP_ID" ]; then
    echo "Could not extract stamp ID from output"
    echo "Attempting to get stamp from listing..."

    # Try to get stamp from list
    STAMP_ID=$(swarm-prov-upload stamps list 2>&1 | grep -oE '[a-f0-9]{64}' | head -1 || echo "")
fi

if [ -z "$STAMP_ID" ]; then
    echo "No stamp ID available for detailed operations"
    echo "Skipping stamp info and extend steps"
else
    echo "Using stamp: ${STAMP_ID:0:16}..."
    echo ""

    # Step 3: Get stamp details
    echo "=============================================="
    echo "Step 3: Get Stamp Details"
    echo "=============================================="
    echo ""

    swarm-prov-upload stamps info "$STAMP_ID" 2>&1 || echo "Could not get stamp info"

    echo ""

    # Step 4: Monitor utilization
    echo "=============================================="
    echo "Step 4: Check Utilization"
    echo "=============================================="
    echo ""

    echo "Uploading additional file to increase utilization..."
    echo "Second upload to same stamp - $(date)" > "${OUTPUT_DIR}/stamp_demo_2.txt"

    swarm-prov-upload upload \
        --file "${OUTPUT_DIR}/stamp_demo_2.txt" \
        --stamp-id "$STAMP_ID" \
        2>&1 || echo "Second upload failed"

    echo ""
    echo "Updated stamp info:"
    swarm-prov-upload stamps info "$STAMP_ID" 2>&1 || echo "Could not get updated stamp info"
fi

echo ""

# Step 5: List stamps again
echo "=============================================="
echo "Step 5: Final Stamp List"
echo "=============================================="
echo ""

swarm-prov-upload stamps list 2>&1 || echo "Could not list stamps"

echo ""
echo "=============================================="
echo "Summary"
echo "=============================================="
echo ""
echo "Stamp management commands:"
echo "  swarm-prov-upload stamps list           - List all stamps"
echo "  swarm-prov-upload stamps info <id>      - Get stamp details"
echo "  swarm-prov-upload stamps extend <id>    - Extend stamp TTL"
echo ""
echo "Best practices:"
echo "  - Reuse stamps with --stamp-id for cost savings"
echo "  - Monitor utilization before large batches"
echo "  - Extend stamps before they expire"
