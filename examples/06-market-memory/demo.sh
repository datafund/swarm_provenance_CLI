#!/usr/bin/env bash
#
# Market Memory Demo
#
# Demonstrates market prediction memory units on Swarm:
# 1. Verify canonical hash of a prediction memory unit
# 2. Upload prediction with --std "MARKET-MEMORY-V1"
# 3. Upload observation that links to the prediction
# 4. Download both and verify canonical hashes
#
# Usage: ./demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PREDICTION_FILE="$SCRIPT_DIR/prediction_001.json"
OBSERVATION_FILE="$SCRIPT_DIR/observation_001.json"
DOWNLOAD_DIR="$SCRIPT_DIR/downloads"

echo "========================================="
echo "  Swarm Provenance CLI - Market Memory"
echo "========================================="
echo

# --- Step 0: Check CLI is installed ---
if ! command -v swarm-prov-upload &>/dev/null; then
    echo "ERROR: swarm-prov-upload not found. Install with: pip install -e ."
    exit 1
fi

echo "CLI version: $(swarm-prov-upload --version)"
echo

# --- Step 1: Verify canonical hash of prediction ---
echo "--- Step 1: Verify prediction canonical hash ---"
echo "Verifying: $PREDICTION_FILE"
python3 "$SCRIPT_DIR/create_memory_unit.py" verify "$PREDICTION_FILE"
echo

# --- Step 2: Check gateway health ---
echo "--- Step 2: Check gateway health ---"
swarm-prov-upload health
echo

# --- Step 3: Upload prediction ---
echo "--- Step 3: Upload prediction with --std MARKET-MEMORY-V1 ---"
echo "File: $PREDICTION_FILE"
echo "SHA256: $(shasum -a 256 "$PREDICTION_FILE" | cut -d' ' -f1)"
echo

echo "Uploading (trying pool first)..."
UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$PREDICTION_FILE" --std "MARKET-MEMORY-V1" --usePool 2>&1) || {
    echo "Pool not available, falling back to regular stamp purchase..."
    UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$PREDICTION_FILE" --std "MARKET-MEMORY-V1" 2>&1)
}
echo "$UPLOAD_OUTPUT"

PRED_REF=$(echo "$UPLOAD_OUTPUT" | grep -A1 "Swarm Reference Hash:" | tail -1 | tr -d '[:space:]')

if [ -z "$PRED_REF" ] || [ ${#PRED_REF} -lt 64 ]; then
    echo "ERROR: Could not extract Swarm reference for prediction."
    exit 1
fi

echo
echo "Prediction Reference: $PRED_REF"
echo

# --- Step 4: Update observation with prediction reference and upload ---
echo "--- Step 4: Upload observation linking to prediction ---"

# Create a temporary observation with the actual prediction Swarm reference
TEMP_OBS=$(mktemp)
python3 -c "
import json, hashlib
with open('$OBSERVATION_FILE') as f:
    obs = json.load(f)
obs['prediction_ref'] = '$PRED_REF'
# Recompute canonical hash
hashable = {k: v for k, v in obs.items() if k != 'content_hash'}
canonical = json.dumps(hashable, sort_keys=True, separators=(',', ':'))
obs['content_hash'] = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
with open('$TEMP_OBS', 'w') as f:
    json.dump(obs, f, indent=2)
    f.write('\n')
"

echo "File: observation (with prediction_ref = $PRED_REF)"
echo "SHA256: $(shasum -a 256 "$TEMP_OBS" | cut -d' ' -f1)"
echo

echo "Uploading (trying pool first)..."
UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$TEMP_OBS" --std "MARKET-MEMORY-V1" --usePool 2>&1) || {
    echo "Pool not available, falling back to regular stamp purchase..."
    UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$TEMP_OBS" --std "MARKET-MEMORY-V1" 2>&1)
}
echo "$UPLOAD_OUTPUT"

OBS_REF=$(echo "$UPLOAD_OUTPUT" | grep -A1 "Swarm Reference Hash:" | tail -1 | tr -d '[:space:]')
rm -f "$TEMP_OBS"

if [ -z "$OBS_REF" ] || [ ${#OBS_REF} -lt 64 ]; then
    echo "ERROR: Could not extract Swarm reference for observation."
    exit 1
fi

echo
echo "Observation Reference: $OBS_REF"
echo

# --- Step 5: Download prediction and verify ---
echo "--- Step 5: Download and verify prediction ---"
rm -rf "$DOWNLOAD_DIR"
mkdir -p "$DOWNLOAD_DIR"

swarm-prov-upload download "$PRED_REF" --output-dir "$DOWNLOAD_DIR"
echo

DOWNLOADED_FILE=$(ls "$DOWNLOAD_DIR"/*.data 2>/dev/null | head -1)
if [ -z "$DOWNLOADED_FILE" ]; then
    DOWNLOADED_FILE=$(ls "$DOWNLOAD_DIR"/ | head -1)
    DOWNLOADED_FILE="$DOWNLOAD_DIR/$DOWNLOADED_FILE"
fi

ORIGINAL_HASH=$(shasum -a 256 "$PREDICTION_FILE" | cut -d' ' -f1)
DOWNLOADED_HASH=$(shasum -a 256 "$DOWNLOADED_FILE" | cut -d' ' -f1)

echo "Original:   $ORIGINAL_HASH"
echo "Downloaded: $DOWNLOADED_HASH"
echo

if [ "$ORIGINAL_HASH" = "$DOWNLOADED_HASH" ]; then
    echo "PASS: Prediction data integrity verified."
else
    echo "FAIL: Prediction hash mismatch!"
    exit 1
fi

# Verify canonical hash of downloaded prediction
echo
echo "Verifying canonical hash of downloaded prediction..."
python3 "$SCRIPT_DIR/create_memory_unit.py" verify "$DOWNLOADED_FILE"

echo
echo "--- Demo complete ---"
echo "Prediction Reference:  $PRED_REF"
echo "Observation Reference: $OBS_REF"
echo "The observation links back to the prediction via prediction_ref."
echo "Both memory units use canonical hashing for content integrity."
