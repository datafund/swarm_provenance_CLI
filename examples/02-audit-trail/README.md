# Audit Trail / Compliance Records Example

This example demonstrates how to use the Swarm Provenance CLI for regulatory compliance and audit logging. By storing audit records on Swarm, you create an immutable, tamper-evident trail that can be independently verified.

## Use Cases

- **Financial Services**: Transaction logs, trade records, compliance reports
- **Healthcare**: HIPAA audit trails, patient access logs
- **Supply Chain**: Chain-of-custody records, quality control logs
- **Legal**: Evidence preservation, contract execution records

## What You'll Learn

- Using the `--std` flag for provenance standard tagging
- Creating timestamped, immutable audit records
- Batch processing multiple audit logs with stamp reuse
- Building a verifiable audit trail

## Prerequisites

```bash
swarm-prov-upload --version
swarm-prov-upload health
```

## Quick Start

```bash
# Shell demo
chmod +x demo.sh
./demo.sh

# Python demo
python run_demo.py
```

## Step-by-Step Guide

### 1. Single Audit Record Upload

Upload an audit log with provenance standard tagging:

```bash
swarm-prov-upload upload \
  --file audit_log.json \
  --std "AUDIT-LOG-V1"
```

The `--std` flag adds a `provenance_standard` field to the metadata, making it easy to identify the record type.

### 2. Batch Audit Records (Cost-Optimized)

For multiple audit records, purchase one stamp and reuse it:

```bash
# Purchase a stamp with sufficient capacity
swarm-prov-upload upload \
  --file audit_log.json \
  --std "AUDIT-LOG-V1" \
  --size medium

# Note the stamp_id from output, then reuse it:
swarm-prov-upload upload \
  --file compliance_record.json \
  --std "COMPLIANCE-V1" \
  --stamp-id <stamp_id_from_above>
```

### 3. Building an Audit Trail

Create a manifest linking all audit records:

```python
audit_trail = {
    "organization": "Example Corp",
    "period": "2025-Q1",
    "records": [
        {"type": "audit_log", "swarm_ref": "abc123...", "timestamp": "..."},
        {"type": "compliance", "swarm_ref": "def456...", "timestamp": "..."},
    ]
}
```

Upload the manifest itself for a complete, verifiable chain.

## Sample Files

### audit_log.json

```json
{
  "schema_version": "1.0",
  "source_system": "compliance-audit-service",
  "entries": [
    {
      "id": "audit-20250108-0001",
      "timestamp": "2025-01-08T10:30:00Z",
      "event_type": "DATA_ACCESS",
      "user_id": "user-001",
      "resource": "/api/data/records",
      "action": "READ",
      "status": "SUCCESS"
    }
  ]
}
```

### compliance_record.json

```json
{
  "schema_version": "1.0",
  "compliance_framework": "SOC2",
  "assessment_date": "2025-01-08",
  "controls": [
    {
      "control_id": "CC6.1",
      "status": "IMPLEMENTED",
      "evidence": ["doc-001", "doc-002"]
    }
  ]
}
```

## Metadata Structure

When uploaded with `--std "AUDIT-LOG-V1"`, the metadata becomes:

```json
{
  "data": "<base64 encoded audit log>",
  "content_hash": "sha256...",
  "stamp_id": "stamp...",
  "provenance_standard": "AUDIT-LOG-V1",
  "encryption": null
}
```

## Common Provenance Standards

| Standard | Use Case |
|----------|----------|
| `AUDIT-LOG-V1` | General audit logging |
| `COMPLIANCE-V1` | Compliance assessments |
| `HIPAA-AUDIT` | Healthcare access logs |
| `SOX-AUDIT` | Financial reporting |
| `GDPR-CONSENT` | Consent records |
| `CHAIN-OF-CUSTODY` | Evidence handling |

## Verification Workflow

1. **Store the Swarm reference** alongside your internal records
2. **Retrieve and verify** when needed:
   ```bash
   swarm-prov-upload download <swarm_ref> --output-dir ./audit_verify
   ```
3. **Compare hashes** to prove the record hasn't been modified
4. **Present the immutable record** for audits or legal proceedings

## Best Practices

1. **Consistent Standards**: Use consistent `--std` values across your organization
2. **Timestamp Everything**: Include ISO 8601 timestamps in your audit data
3. **Batch by Period**: Group audit logs by day/week/month for efficient storage
4. **Maintain Manifests**: Create index files linking related audit records
5. **Long Duration**: Use `--duration 8760` (1 year) for compliance records
6. **Encrypt Sensitive Data**: Use `--enc` flag for PII (see encrypted-data example)

## Files in This Example

| File | Description |
|------|-------------|
| `README.md` | This documentation |
| `demo.sh` | Shell script demonstrating audit trail creation |
| `audit_log.json` | Sample audit log record |
| `compliance_record.json` | Sample compliance assessment |
| `run_demo.py` | Python script version |

## Next Steps

- [05-encrypted-data](../05-encrypted-data/) - Encrypt sensitive audit records
- [04-batch-processing](../04-batch-processing/) - Process large volumes of audit logs
- [09-verification](../09-verification/) - Build comprehensive verification reports
