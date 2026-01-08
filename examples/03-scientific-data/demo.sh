#!/bin/bash
# Scientific Data Preservation Demo
# Demonstrates long-term research data archival with PROV-O standard

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/output"

echo "=============================================="
echo "Swarm Provenance CLI - Scientific Data Demo"
echo "=============================================="
echo ""

# Check CLI
if ! command -v swarm-prov-upload &> /dev/null; then
    echo "ERROR: swarm-prov-upload not found"
    exit 1
fi

swarm-prov-upload health
echo ""

# Step 1: Upload metadata with PROV-O standard
echo "=============================================="
echo "Step 1: Upload Dataset Metadata (PROV-O)"
echo "=============================================="
echo ""

META_OUTPUT=$(swarm-prov-upload upload \
    --file "${SCRIPT_DIR}/dataset_metadata.json" \
    --std "PROV-O" \
    --duration 720 \
    --size medium \
    2>&1)

echo "$META_OUTPUT"

META_REF=$(echo "$META_OUTPUT" | grep -oE '[a-f0-9]{64}' | tail -1)
STAMP_ID=$(echo "$META_OUTPUT" | grep -oE 'Stamp purchased: [a-f0-9]+' | cut -d' ' -f3 || true)

echo ""
echo "Metadata reference: ${META_REF}"
echo "Duration: 30 days (720 hours)"
echo ""

# Step 2: Upload raw data
echo "=============================================="
echo "Step 2: Upload Experiment Data (CSV)"
echo "=============================================="
echo ""

if [ -n "$STAMP_ID" ]; then
    DATA_OUTPUT=$(swarm-prov-upload upload \
        --file "${SCRIPT_DIR}/experiment_results.csv" \
        --std "PROV-O" \
        --stamp-id "$STAMP_ID" \
        2>&1)
else
    DATA_OUTPUT=$(swarm-prov-upload upload \
        --file "${SCRIPT_DIR}/experiment_results.csv" \
        --std "PROV-O" \
        --duration 720 \
        2>&1)
fi

echo "$DATA_OUTPUT"

DATA_REF=$(echo "$DATA_OUTPUT" | grep -oE '[a-f0-9]{64}' | tail -1)

echo ""
echo "Data reference: ${DATA_REF}"
echo ""

# Step 3: Create research artifact manifest
echo "=============================================="
echo "Step 3: Create Research Artifact Manifest"
echo "=============================================="
echo ""

mkdir -p "${OUTPUT_DIR}"
MANIFEST_FILE="${OUTPUT_DIR}/research_manifest.json"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "$MANIFEST_FILE" << MANIFEST
{
  "manifest_version": "1.0",
  "created_at": "${TIMESTAMP}",
  "dataset_title": "Urban Climate Monitoring Dataset - Ljubljana Q1 2025",
  "doi": "10.5281/example.20250108",
  "provenance_standard": "PROV-O",
  "retention_days": 30,
  "artifacts": [
    {
      "type": "metadata",
      "description": "DataCite-compliant dataset metadata",
      "filename": "dataset_metadata.json",
      "swarm_ref": "${META_REF}"
    },
    {
      "type": "data",
      "description": "Raw experiment results (CSV)",
      "filename": "experiment_results.csv",
      "swarm_ref": "${DATA_REF}"
    }
  ],
  "citation": "Smith, J., & Novak, P. (2025). Urban Climate Monitoring Dataset - Ljubljana Q1 2025 [Data set]. Swarm Network. https://swarm.example/${META_REF}"
}
MANIFEST

echo "Manifest created:"
cat "$MANIFEST_FILE"
echo ""

# Step 4: Verify download
echo "=============================================="
echo "Step 4: Verify Data Retrieval"
echo "=============================================="
echo ""

swarm-prov-upload download "${DATA_REF}" --output-dir "${OUTPUT_DIR}"

DATA_FILE="${OUTPUT_DIR}/${DATA_REF}.data"
if [ -f "$DATA_FILE" ]; then
    echo ""
    echo "Downloaded data preview (first 5 lines):"
    head -5 "$DATA_FILE"
fi

echo ""
echo "=============================================="
echo "Summary"
echo "=============================================="
echo ""
echo "Research artifacts preserved on Swarm:"
echo "  Metadata: ${META_REF}"
echo "  Data:     ${DATA_REF}"
echo ""
echo "Retention: 30 days"
echo "Standard:  PROV-O"
echo ""
echo "Output: ${OUTPUT_DIR}"
