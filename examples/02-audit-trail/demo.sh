#!/bin/bash
# Audit Trail / Compliance Records Demo
# Demonstrates immutable audit logging with provenance standards

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/output"

echo "==========================================="
echo "Swarm Provenance CLI - Audit Trail Demo"
echo "==========================================="
echo ""

# Check CLI
if ! command -v swarm-prov-upload &> /dev/null; then
    echo "ERROR: swarm-prov-upload not found"
    exit 1
fi

# Health check
echo "Checking gateway health..."
swarm-prov-upload health
echo ""

# Step 1: Upload audit log with provenance standard
echo "==========================================="
echo "Step 1: Upload Audit Log"
echo "==========================================="
echo ""
echo "Uploading audit_log.json with --std AUDIT-LOG-V1"
echo ""

AUDIT_OUTPUT=$(swarm-prov-upload upload \
    --file "${SCRIPT_DIR}/audit_log.json" \
    --std "AUDIT-LOG-V1" \
    --size medium \
    2>&1)

echo "$AUDIT_OUTPUT"

# Extract Swarm ref and stamp ID
AUDIT_REF=$(echo "$AUDIT_OUTPUT" | grep -oE '[a-f0-9]{64}' | tail -1)
STAMP_ID=$(echo "$AUDIT_OUTPUT" | grep -oE 'Stamp purchased: [a-f0-9]+' | cut -d' ' -f3 || \
           echo "$AUDIT_OUTPUT" | grep -oE 'stamp_id.*[a-f0-9]{64}' | grep -oE '[a-f0-9]{64}')

echo ""
echo "Audit log reference: ${AUDIT_REF}"
echo ""

# Step 2: Upload compliance record (reusing stamp)
echo "==========================================="
echo "Step 2: Upload Compliance Record (Stamp Reuse)"
echo "==========================================="
echo ""

if [ -n "$STAMP_ID" ]; then
    echo "Reusing stamp from previous upload: ${STAMP_ID:0:16}..."
    COMPLIANCE_OUTPUT=$(swarm-prov-upload upload \
        --file "${SCRIPT_DIR}/compliance_record.json" \
        --std "COMPLIANCE-SOC2-V1" \
        --stamp-id "$STAMP_ID" \
        2>&1)
else
    echo "No stamp ID found, purchasing new stamp..."
    COMPLIANCE_OUTPUT=$(swarm-prov-upload upload \
        --file "${SCRIPT_DIR}/compliance_record.json" \
        --std "COMPLIANCE-SOC2-V1" \
        2>&1)
fi

echo "$COMPLIANCE_OUTPUT"

COMPLIANCE_REF=$(echo "$COMPLIANCE_OUTPUT" | grep -oE '[a-f0-9]{64}' | tail -1)
echo ""
echo "Compliance record reference: ${COMPLIANCE_REF}"
echo ""

# Step 3: Create audit trail manifest
echo "==========================================="
echo "Step 3: Create Audit Trail Manifest"
echo "==========================================="
echo ""

MANIFEST_FILE="${OUTPUT_DIR}/audit_trail_manifest.json"
mkdir -p "${OUTPUT_DIR}"

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "$MANIFEST_FILE" << MANIFEST
{
  "manifest_version": "1.0",
  "created_at": "${TIMESTAMP}",
  "organization": "Example Corporation",
  "period": "2025-Q1",
  "records": [
    {
      "type": "audit_log",
      "standard": "AUDIT-LOG-V1",
      "swarm_ref": "${AUDIT_REF}",
      "filename": "audit_log.json",
      "uploaded_at": "${TIMESTAMP}"
    },
    {
      "type": "compliance_assessment",
      "standard": "COMPLIANCE-SOC2-V1",
      "swarm_ref": "${COMPLIANCE_REF}",
      "filename": "compliance_record.json",
      "uploaded_at": "${TIMESTAMP}"
    }
  ],
  "total_records": 2,
  "verification_instructions": "Download each record using swarm-prov-upload download <swarm_ref> and verify the SHA256 hash matches the content_hash in metadata."
}
MANIFEST

echo "Manifest created: ${MANIFEST_FILE}"
cat "$MANIFEST_FILE"
echo ""

# Upload the manifest itself
echo "Uploading manifest to create complete audit trail..."
echo ""

if [ -n "$STAMP_ID" ]; then
    MANIFEST_OUTPUT=$(swarm-prov-upload upload \
        --file "$MANIFEST_FILE" \
        --std "AUDIT-MANIFEST-V1" \
        --stamp-id "$STAMP_ID" \
        2>&1)
else
    MANIFEST_OUTPUT=$(swarm-prov-upload upload \
        --file "$MANIFEST_FILE" \
        --std "AUDIT-MANIFEST-V1" \
        2>&1)
fi

echo "$MANIFEST_OUTPUT"

MANIFEST_REF=$(echo "$MANIFEST_OUTPUT" | grep -oE '[a-f0-9]{64}' | tail -1)
echo ""

# Step 4: Verify one record
echo "==========================================="
echo "Step 4: Verify Audit Record"
echo "==========================================="
echo ""

echo "Downloading and verifying audit log..."
swarm-prov-upload download "${AUDIT_REF}" --output-dir "${OUTPUT_DIR}"
echo ""

# Check provenance standard in metadata
META_FILE="${OUTPUT_DIR}/${AUDIT_REF}.meta.json"
if [ -f "$META_FILE" ]; then
    echo "Metadata provenance_standard:"
    grep -o '"provenance_standard"[^,}]*' "$META_FILE" || echo "Not found"
    echo ""
fi

# Summary
echo "==========================================="
echo "Audit Trail Summary"
echo "==========================================="
echo ""
echo "Records uploaded to immutable storage:"
echo ""
echo "1. Audit Log"
echo "   Standard: AUDIT-LOG-V1"
echo "   Reference: ${AUDIT_REF}"
echo ""
echo "2. Compliance Record"
echo "   Standard: COMPLIANCE-SOC2-V1"
echo "   Reference: ${COMPLIANCE_REF}"
echo ""
echo "3. Audit Trail Manifest"
echo "   Standard: AUDIT-MANIFEST-V1"
echo "   Reference: ${MANIFEST_REF}"
echo ""
echo "Output directory: ${OUTPUT_DIR}"
echo ""
echo "To verify any record:"
echo "  swarm-prov-upload download <reference> --output-dir ./verify"
echo ""
echo "==========================================="
echo "Demo complete!"
echo "==========================================="
