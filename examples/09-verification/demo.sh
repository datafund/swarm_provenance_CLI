#!/bin/bash
# Data Verification & Integrity Check Demo
# Demonstrates verification workflows and tamper detection

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/output"

echo "=============================================="
echo "Swarm Provenance CLI - Verification Demo"
echo "=============================================="
echo ""

if ! command -v swarm-prov-upload &> /dev/null; then
    echo "ERROR: swarm-prov-upload not found"
    exit 1
fi

mkdir -p "${OUTPUT_DIR}"

# Step 1: Create and upload test data
echo "=============================================="
echo "Step 1: Upload Test Data"
echo "=============================================="
echo ""

TEST_FILE="${OUTPUT_DIR}/verification_test.txt"
cat > "$TEST_FILE" << 'TESTDATA'
Verification Test Data
======================
This file will be uploaded to Swarm and then verified.

The verification process:
1. Download the data
2. Compute SHA256 hash
3. Compare with stored content_hash
4. Report success or failure

Timestamp: TIMESTAMP_PLACEHOLDER
TESTDATA

# Add actual timestamp
sed -i.bak "s/TIMESTAMP_PLACEHOLDER/$(date -u +%Y-%m-%dT%H:%M:%SZ)/" "$TEST_FILE" 2>/dev/null || \
    sed -i '' "s/TIMESTAMP_PLACEHOLDER/$(date -u +%Y-%m-%dT%H:%M:%SZ)/" "$TEST_FILE"

echo "Created test file: $TEST_FILE"
ORIGINAL_HASH=$(shasum -a 256 "$TEST_FILE" | cut -d' ' -f1)
echo "Original SHA256: $ORIGINAL_HASH"
echo ""

UPLOAD_OUTPUT=$(swarm-prov-upload upload \
    --file "$TEST_FILE" \
    --std "VERIFICATION-TEST" \
    2>&1)

echo "$UPLOAD_OUTPUT"

SWARM_REF=$(echo "$UPLOAD_OUTPUT" | grep -oE '[a-f0-9]{64}' | tail -1)
echo ""
echo "Swarm reference: $SWARM_REF"
echo ""

# Step 2: Verify integrity (should pass)
echo "=============================================="
echo "Step 2: Verify Integrity (Should Pass)"
echo "=============================================="
echo ""

VERIFY_DIR="${OUTPUT_DIR}/verified"
mkdir -p "$VERIFY_DIR"

swarm-prov-upload download "$SWARM_REF" --output-dir "$VERIFY_DIR"

DATA_FILE="${VERIFY_DIR}/${SWARM_REF}.data"
META_FILE="${VERIFY_DIR}/${SWARM_REF}.meta.json"

echo ""
echo "Downloaded files:"
ls -la "$VERIFY_DIR"

echo ""
echo "Verification:"

if [ -f "$DATA_FILE" ]; then
    DOWNLOADED_HASH=$(shasum -a 256 "$DATA_FILE" | cut -d' ' -f1)
    echo "  Downloaded hash: $DOWNLOADED_HASH"
    echo "  Original hash:   $ORIGINAL_HASH"

    if [ "$DOWNLOADED_HASH" = "$ORIGINAL_HASH" ]; then
        echo "  Result: VERIFIED - Hashes match"
    else
        echo "  Result: FAILED - Hash mismatch!"
    fi
else
    echo "  ERROR: Data file not found"
fi

echo ""

# Step 3: Check metadata
echo "=============================================="
echo "Step 3: Examine Metadata"
echo "=============================================="
echo ""

if [ -f "$META_FILE" ]; then
    echo "Metadata content:"
    # Show key fields (without full base64 data)
    python3 -c "
import json
with open('$META_FILE') as f:
    meta = json.load(f)
print(f'  content_hash: {meta.get(\"content_hash\", \"N/A\")}')
print(f'  stamp_id: {meta.get(\"stamp_id\", \"N/A\")[:32]}...')
print(f'  provenance_standard: {meta.get(\"provenance_standard\", \"N/A\")}')
print(f'  encryption: {meta.get(\"encryption\", \"N/A\")}')
print(f'  data length: {len(meta.get(\"data\", \"\"))} chars (base64)')
" 2>/dev/null || cat "$META_FILE" | head -20
fi

echo ""

# Step 4: Simulate tamper detection
echo "=============================================="
echo "Step 4: Tamper Detection Simulation"
echo "=============================================="
echo ""

TAMPERED_FILE="${OUTPUT_DIR}/tampered.data"
cp "$DATA_FILE" "$TAMPERED_FILE"
echo "TAMPERED CONTENT" >> "$TAMPERED_FILE"

TAMPERED_HASH=$(shasum -a 256 "$TAMPERED_FILE" | cut -d' ' -f1)
EXPECTED_HASH=$(python3 -c "import json; print(json.load(open('$META_FILE'))['content_hash'])" 2>/dev/null || echo "")

echo "Expected hash:  $EXPECTED_HASH"
echo "Tampered hash:  $TAMPERED_HASH"
echo ""

if [ "$TAMPERED_HASH" != "$EXPECTED_HASH" ]; then
    echo "Result: TAMPER DETECTED - Hashes do not match"
    echo "        The data has been modified since upload"
else
    echo "Result: No tampering detected"
fi

echo ""

# Summary
echo "=============================================="
echo "Summary"
echo "=============================================="
echo ""
echo "Test data uploaded and verified successfully."
echo ""
echo "Swarm reference: $SWARM_REF"
echo "Original hash:   $ORIGINAL_HASH"
echo ""
echo "Verification commands:"
echo "  swarm-prov-upload download $SWARM_REF --output-dir ./verify"
echo "  python integrity_checker.py $SWARM_REF"
echo ""
echo "Output directory: $OUTPUT_DIR"
