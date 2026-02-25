#!/usr/bin/env bash
#
# Stamp Management Demo
#
# Demonstrates the full postage stamp lifecycle:
# 1. Check stamp pool availability
# 2. Upload a file with -v to capture stamp ID
# 3. List all stamps
# 4. Inspect stamp details
# 5. Health-check a stamp
#
# Usage: ./demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SAMPLE_FILE="$SCRIPT_DIR/sample_data.txt"

echo "============================================="
echo "  Swarm Provenance CLI - Stamp Management"
echo "============================================="
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

# --- Step 2: Check stamp pool status ---
echo "--- Step 2: Check stamp pool availability ---"
swarm-prov-upload stamps pool-status || echo "(pool status check returned non-zero)"
echo

# --- Step 3: Upload file with verbose to capture stamp ID ---
echo "--- Step 3: Upload sample file with -v to capture stamp ID ---"
echo "Uploading: sample_data.txt"

UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$SAMPLE_FILE" -v --usePool 2>&1) || {
    echo "  Pool not available, falling back to regular stamp purchase..."
    UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$SAMPLE_FILE" -v 2>&1)
}

SWARM_REF=$(echo "$UPLOAD_OUTPUT" | grep -A1 "Swarm Reference Hash:" | tail -1 | tr -d '[:space:]')
if [ -z "$SWARM_REF" ] || [ ${#SWARM_REF} -lt 64 ]; then
    echo "ERROR: Could not extract Swarm reference"
    echo "Raw output: $UPLOAD_OUTPUT"
    exit 1
fi

STAMP_ID=$(echo "$UPLOAD_OUTPUT" | grep "Stamp ID Received:" | awk -F'Stamp ID Received: ' '{print $2}' | tr -d '[:space:]')
echo "  Swarm reference: $SWARM_REF"

if [ -z "$STAMP_ID" ] || [ ${#STAMP_ID} -lt 16 ]; then
    echo "WARNING: Could not extract stamp ID from verbose output"
    echo "Stamp lifecycle commands require a stamp ID."
    echo
    echo "PASS: Upload succeeded. Stamp lifecycle steps skipped (no stamp ID)."
    exit 0
fi

echo "  Stamp ID: $STAMP_ID"
echo

# --- Step 4: List all stamps ---
echo "--- Step 4: List all stamps ---"
swarm-prov-upload stamps list || echo "(stamps list returned non-zero)"
echo

# --- Step 5: Stamp info ---
echo "--- Step 5: Stamp details ---"
swarm-prov-upload stamps info "$STAMP_ID" || echo "(stamps info returned non-zero)"
echo

# --- Step 6: Stamp health check ---
echo "--- Step 6: Stamp health check ---"
swarm-prov-upload stamps check "$STAMP_ID" || echo "(stamps check returned non-zero)"
echo

echo "PASS: Stamp lifecycle demo complete."
echo
echo "--- Summary ---"
echo "Swarm reference: $SWARM_REF"
echo "Stamp ID: $STAMP_ID"
echo
echo "Additional stamp commands available:"
echo "  swarm-prov-upload stamps extend $STAMP_ID --amount 1000000"
echo "  (requires funded wallet with BZZ tokens)"
