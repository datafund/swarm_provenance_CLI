#!/usr/bin/env bash
#
# CI/CD Integration Demo
#
# Demonstrates archiving build artifacts to Swarm:
# 1. Upload build artifacts with --std "CI-ARTIFACT-V1"
# 2. Save receipt manifest with references and hashes
# 3. Download and verify one artifact
#
# Usage: ./demo.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ARTIFACTS_DIR="$SCRIPT_DIR/sample_artifacts"
DOWNLOAD_DIR="$SCRIPT_DIR/downloads"

echo "============================================="
echo "  Swarm Provenance CLI - CI/CD Integration"
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

# --- Step 2: Upload build artifacts ---
echo "--- Step 2: Upload build artifacts with --std CI-ARTIFACT-V1 ---"

ARTIFACTS=("build_info.json" "release_notes.txt")
declare -a REFS=()
declare -a HASHES=()

for artifact in "${ARTIFACTS[@]}"; do
    FILE="$ARTIFACTS_DIR/$artifact"
    HASH=$(shasum -a 256 "$FILE" | cut -d' ' -f1)
    HASHES+=("$HASH")
    echo "Uploading: $artifact"
    echo "  SHA256: $HASH"

    UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$FILE" --std "CI-ARTIFACT-V1" --usePool 2>&1) || {
        echo "  Pool not available, falling back to regular stamp purchase..."
        UPLOAD_OUTPUT=$(swarm-prov-upload upload --file "$FILE" --std "CI-ARTIFACT-V1" 2>&1)
    }

    SWARM_REF=$(echo "$UPLOAD_OUTPUT" | grep -A1 "Swarm Reference Hash:" | tail -1 | tr -d '[:space:]')

    if [ -z "$SWARM_REF" ] || [ ${#SWARM_REF} -lt 64 ]; then
        echo "ERROR: Could not extract Swarm reference for $artifact"
        echo "Raw output: $UPLOAD_OUTPUT"
        exit 1
    fi

    REFS+=("$SWARM_REF")
    echo "  Reference: $SWARM_REF"
    echo
done

echo "All ${#ARTIFACTS[@]} artifacts archived."
echo

# --- Step 3: Save receipt manifest ---
echo "--- Step 3: Save archive receipt ---"
RECEIPT_FILE="$SCRIPT_DIR/archive_receipt.json"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "$RECEIPT_FILE" <<RECEIPT_EOF
{
  "pipeline": "ci-cd-demo",
  "timestamp": "$TIMESTAMP",
  "standard": "CI-ARTIFACT-V1",
  "artifacts": [
    {
      "filename": "${ARTIFACTS[0]}",
      "reference": "${REFS[0]}",
      "content_hash": "${HASHES[0]}"
    },
    {
      "filename": "${ARTIFACTS[1]}",
      "reference": "${REFS[1]}",
      "content_hash": "${HASHES[1]}"
    }
  ]
}
RECEIPT_EOF

echo "Receipt saved: $RECEIPT_FILE"
cat "$RECEIPT_FILE"
echo

# --- Step 4: Download and verify one artifact ---
echo "--- Step 4: Download and verify build_info.json ---"
rm -rf "$DOWNLOAD_DIR"
mkdir -p "$DOWNLOAD_DIR"

VERIFY_REF="${REFS[0]}"
echo "Downloading: $VERIFY_REF"
swarm-prov-upload download "$VERIFY_REF" --output-dir "$DOWNLOAD_DIR"
echo

# --- Step 5: Verify integrity ---
echo "--- Step 5: Compare SHA-256 hashes ---"
ORIGINAL_HASH="${HASHES[0]}"
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
    echo "PASS: Build artifact integrity verified - hashes match."
else
    echo "FAIL: Hash mismatch - artifact may have been tampered with!"
    exit 1
fi

echo
echo "--- Demo complete ---"
echo "Archived ${#ARTIFACTS[@]} build artifacts with CI-ARTIFACT-V1 standard."
echo "Receipt: $RECEIPT_FILE"
