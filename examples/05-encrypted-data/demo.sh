#!/bin/bash
# Encrypted Data Demo
# Demonstrates encrypt-upload-download-decrypt workflow

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/output"

echo "=============================================="
echo "Swarm Provenance CLI - Encrypted Data Demo"
echo "=============================================="
echo ""

# Check for Python cryptography module
if ! python3 -c "import cryptography" 2>/dev/null; then
    echo "ERROR: Python cryptography module required"
    echo "Install with: pip install cryptography"
    exit 1
fi

# Check CLI
if ! command -v swarm-prov-upload &> /dev/null; then
    echo "ERROR: swarm-prov-upload not found"
    exit 1
fi

mkdir -p "${OUTPUT_DIR}"

# Create sample sensitive file
SAMPLE_FILE="${OUTPUT_DIR}/sensitive_data.txt"
cat > "$SAMPLE_FILE" << 'SENSITIVE'
CONFIDENTIAL - Sample Sensitive Data

User: John Doe
SSN: XXX-XX-1234
Account: ****5678

This file contains sensitive information that should
be encrypted before storage on any public network.

The encryption ensures that even if someone retrieves
this data from Swarm, they cannot read it without
the encryption key.
SENSITIVE

echo "Created sample sensitive file: ${SAMPLE_FILE}"
echo ""

# Step 1: Encrypt and Upload
echo "=============================================="
echo "Step 1: Encrypt and Upload"
echo "=============================================="
echo ""

cd "${SCRIPT_DIR}"
python3 encrypt_upload.py "${SAMPLE_FILE}" --output-dir "${OUTPUT_DIR}"

echo ""

# Get the swarm ref from manifest
MANIFEST="${OUTPUT_DIR}/sensitive_data.txt.manifest.json"
if [ -f "$MANIFEST" ]; then
    SWARM_REF=$(python3 -c "import json; print(json.load(open('${MANIFEST}'))['swarm_ref'])")
    KEY_FILE="${OUTPUT_DIR}/sensitive_data.txt.key"
else
    echo "ERROR: Manifest not found"
    exit 1
fi

# Step 2: Download and Decrypt
echo ""
echo "=============================================="
echo "Step 2: Download and Decrypt"
echo "=============================================="
echo ""

DECRYPT_DIR="${OUTPUT_DIR}/decrypted"
mkdir -p "${DECRYPT_DIR}"

python3 decrypt_download.py "${SWARM_REF}" \
    --key-file "${KEY_FILE}" \
    --output-dir "${DECRYPT_DIR}" \
    --output-name "recovered_sensitive_data.txt"

echo ""

# Step 3: Verify content matches
echo "=============================================="
echo "Step 3: Verify Content Match"
echo "=============================================="
echo ""

ORIGINAL_HASH=$(shasum -a 256 "$SAMPLE_FILE" | cut -d' ' -f1)
RECOVERED_FILE="${DECRYPT_DIR}/recovered_sensitive_data.txt"
RECOVERED_HASH=$(shasum -a 256 "$RECOVERED_FILE" | cut -d' ' -f1)

echo "Original hash:  ${ORIGINAL_HASH}"
echo "Recovered hash: ${RECOVERED_HASH}"
echo ""

if [ "$ORIGINAL_HASH" = "$RECOVERED_HASH" ]; then
    echo "SUCCESS: Files match! Encryption cycle complete."
else
    echo "ERROR: Hash mismatch!"
fi

echo ""
echo "=============================================="
echo "Summary"
echo "=============================================="
echo ""
echo "Files created:"
echo "  Encrypted: ${OUTPUT_DIR}/sensitive_data.txt.enc"
echo "  Key:       ${KEY_FILE}"
echo "  Manifest:  ${MANIFEST}"
echo "  Recovered: ${RECOVERED_FILE}"
echo ""
echo "Swarm reference: ${SWARM_REF}"
echo ""
echo "SECURITY REMINDER:"
echo "  - Store encryption keys separately from encrypted data"
echo "  - Never upload encryption keys to Swarm"
echo "  - Use secure key management in production"
