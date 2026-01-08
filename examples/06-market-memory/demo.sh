#!/bin/bash
# Market Memory Demo
# Creates and verifies SemantiCord-inspired memory units

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/output"

echo "=============================================="
echo "Swarm Provenance CLI - Market Memory Demo"
echo "=============================================="
echo ""

if ! command -v swarm-prov-upload &> /dev/null; then
    echo "ERROR: swarm-prov-upload not found"
    exit 1
fi

mkdir -p "${OUTPUT_DIR}"

# Step 1: Create a market forecast memory unit
echo "=============================================="
echo "Step 1: Create Market Forecast"
echo "=============================================="
echo ""

cd "${SCRIPT_DIR}"
python3 create_memory_unit.py \
    --domain market-forecast \
    --asset ETH/USD \
    --value 2500.00 \
    --confidence 0.85 \
    --output-dir "${OUTPUT_DIR}"

# Get swarm ref
UNIT_FILE=$(ls -t "${OUTPUT_DIR}"/mu-*.manifest.json 2>/dev/null | head -1)
if [ -f "$UNIT_FILE" ]; then
    SWARM_REF=$(python3 -c "import json; print(json.load(open('${UNIT_FILE}'))['swarm_ref'])")
else
    echo "ERROR: No manifest found"
    exit 1
fi

echo ""

# Step 2: Verify the memory unit
echo "=============================================="
echo "Step 2: Verify Memory Unit"
echo "=============================================="
echo ""

python3 verify_memory_unit.py "${SWARM_REF}" --output-dir "${OUTPUT_DIR}/verified"

echo ""

# Step 3: Create a price observation
echo "=============================================="
echo "Step 3: Create Price Observation"
echo "=============================================="
echo ""

python3 create_memory_unit.py \
    --domain price-observation \
    --asset BTC/USD \
    --value 45000.00 \
    --output-dir "${OUTPUT_DIR}"

echo ""
echo "=============================================="
echo "Summary"
echo "=============================================="
echo ""
echo "Memory units created in: ${OUTPUT_DIR}"
ls -la "${OUTPUT_DIR}"/*.json 2>/dev/null || echo "No JSON files found"
echo ""
echo "Each memory unit contains:"
echo "  - Unique ID"
echo "  - Domain classification"
echo "  - Timestamped payload"
echo "  - Canonical hash for verification"
echo "  - Swarm reference for retrieval"
