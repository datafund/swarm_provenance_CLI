#!/bin/bash
# Batch Processing / Cost Optimization Demo
# Demonstrates efficient multi-file uploads with stamp reuse

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/output"
SAMPLE_DIR="${SCRIPT_DIR}/sample_files"

echo "=============================================="
echo "Swarm Provenance CLI - Batch Processing Demo"
echo "=============================================="
echo ""

# Check CLI
if ! command -v swarm-prov-upload &> /dev/null; then
    echo "ERROR: swarm-prov-upload not found"
    exit 1
fi

swarm-prov-upload health
echo ""

mkdir -p "${OUTPUT_DIR}"

# Count files
FILE_COUNT=$(ls -1 "${SAMPLE_DIR}"/*.txt 2>/dev/null | wc -l | tr -d ' ')
echo "Found ${FILE_COUNT} files to upload in ${SAMPLE_DIR}"
echo ""

# Step 1: Upload first file and get stamp
echo "=============================================="
echo "Step 1: Upload First File (Purchase Stamp)"
echo "=============================================="
echo ""

FIRST_FILE=$(ls "${SAMPLE_DIR}"/*.txt | head -1)
echo "Uploading: $(basename "$FIRST_FILE")"
echo "Using --size medium for batch capacity"
echo ""

FIRST_OUTPUT=$(swarm-prov-upload upload \
    --file "$FIRST_FILE" \
    --std "BATCH-LOG-V1" \
    --size medium \
    2>&1)

echo "$FIRST_OUTPUT"

# Extract stamp ID
STAMP_ID=$(echo "$FIRST_OUTPUT" | grep -oE 'Stamp purchased: [a-f0-9]+' | cut -d' ' -f3 || \
           echo "$FIRST_OUTPUT" | grep -oE 'stamp.*[a-f0-9]{64}' | grep -oE '[a-f0-9]{64}' | head -1)

FIRST_REF=$(echo "$FIRST_OUTPUT" | grep -oE '[a-f0-9]{64}' | tail -1)

echo ""
echo "Stamp ID: ${STAMP_ID:0:32}..."
echo "Reference: ${FIRST_REF}"
echo ""

# Initialize manifest
MANIFEST_FILE="${OUTPUT_DIR}/batch_manifest.json"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Start manifest with first upload
UPLOADS="[{\"filename\": \"$(basename "$FIRST_FILE")\", \"swarm_ref\": \"${FIRST_REF}\", \"size\": $(stat -f%z "$FIRST_FILE" 2>/dev/null || stat -c%s "$FIRST_FILE")}]"

# Step 2: Upload remaining files with stamp reuse
echo "=============================================="
echo "Step 2: Upload Remaining Files (Stamp Reuse)"
echo "=============================================="
echo ""

UPLOAD_COUNT=1

for FILE in "${SAMPLE_DIR}"/*.txt; do
    # Skip first file (already uploaded)
    if [ "$FILE" = "$FIRST_FILE" ]; then
        continue
    fi

    FILENAME=$(basename "$FILE")
    UPLOAD_COUNT=$((UPLOAD_COUNT + 1))

    echo "[${UPLOAD_COUNT}/${FILE_COUNT}] Uploading: ${FILENAME}"

    if [ -n "$STAMP_ID" ]; then
        FILE_OUTPUT=$(swarm-prov-upload upload \
            --file "$FILE" \
            --std "BATCH-LOG-V1" \
            --stamp-id "$STAMP_ID" \
            2>&1)
    else
        FILE_OUTPUT=$(swarm-prov-upload upload \
            --file "$FILE" \
            --std "BATCH-LOG-V1" \
            2>&1)
    fi

    FILE_REF=$(echo "$FILE_OUTPUT" | grep -oE '[a-f0-9]{64}' | tail -1)
    FILE_SIZE=$(stat -f%z "$FILE" 2>/dev/null || stat -c%s "$FILE")

    echo "  Reference: ${FILE_REF}"

    # Add to manifest (simple append)
    UPLOADS="${UPLOADS%]}, {\"filename\": \"${FILENAME}\", \"swarm_ref\": \"${FILE_REF}\", \"size\": ${FILE_SIZE}}]"
done

echo ""

# Step 3: Generate manifest
echo "=============================================="
echo "Step 3: Generate Batch Manifest"
echo "=============================================="
echo ""

cat > "$MANIFEST_FILE" << MANIFEST
{
  "version": "1.0",
  "created_at": "${TIMESTAMP}",
  "stamp_id": "${STAMP_ID}",
  "provenance_standard": "BATCH-LOG-V1",
  "total_files": ${FILE_COUNT},
  "uploads": ${UPLOADS}
}
MANIFEST

echo "Manifest created: ${MANIFEST_FILE}"
echo ""
cat "$MANIFEST_FILE"
echo ""

# Step 4: Check stamp utilization
echo "=============================================="
echo "Step 4: Check Stamp Utilization"
echo "=============================================="
echo ""

if [ -n "$STAMP_ID" ]; then
    swarm-prov-upload stamps info "$STAMP_ID" 2>&1 || echo "Could not retrieve stamp info"
fi

echo ""
echo "=============================================="
echo "Summary"
echo "=============================================="
echo ""
echo "Batch upload complete!"
echo "  Files uploaded: ${FILE_COUNT}"
echo "  Stamps used: 1 (cost optimized)"
echo "  Manifest: ${MANIFEST_FILE}"
echo ""
echo "Cost savings: Used 1 stamp instead of ${FILE_COUNT} stamps"
