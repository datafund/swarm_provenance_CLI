# Example 02: Audit Trail

Demonstrates using Swarm as an immutable audit log for compliance records.

## What This Demonstrates

- Uploading multiple audit records with a provenance standard (`--std "AUDIT-LOG-V1"`)
- Immutable storage of compliance-critical events
- Downloading and verifying record integrity via SHA-256

## Use Case

Organizations subject to SOX, GDPR, or ISO 27001 need tamper-proof audit trails. By uploading audit events to Swarm with a provenance standard tag, each record gets:

- An immutable content-addressed reference (Swarm hash)
- A SHA-256 integrity fingerprint
- A metadata envelope recording the provenance standard

No one — not even the data owner — can alter a record after upload without changing its hash.

## Prerequisites

1. Install the CLI: `pip install -e .`
2. Gateway access (default, no setup needed)

## Quick Start

### Shell

```bash
chmod +x demo.sh
./demo.sh
```

### Python

```bash
python run_demo.py
```

## Step-by-Step Walkthrough

### 1. Upload audit records

Each record is uploaded with the `AUDIT-LOG-V1` provenance standard:

```bash
swarm-prov-upload upload --file audit_record_001.json --std "AUDIT-LOG-V1" --usePool
swarm-prov-upload upload --file audit_record_002.json --std "AUDIT-LOG-V1" --usePool
swarm-prov-upload upload --file audit_record_003.json --std "AUDIT-LOG-V1" --usePool
```

The `--std` flag tags the metadata envelope with the provenance standard, identifying these as audit log entries.

### 2. Download and verify

```bash
swarm-prov-upload download <swarm_hash> --output-dir ./downloads
```

### 3. Verify integrity

Compare SHA-256 hashes of the original and downloaded files:

```bash
shasum -a 256 audit_record_001.json
shasum -a 256 downloads/*.data
```

If the hashes match, the record is intact.

## Sample Records

| File | Event Type | Description |
|------|-----------|-------------|
| `audit_record_001.json` | Transaction approval | Finance manager approves Q2 payment |
| `audit_record_002.json` | Data access | Analyst queries EU customer dataset |
| `audit_record_003.json` | Config change | Sysadmin modifies firewall rules |

## Metadata Envelope

When uploaded with `--std "AUDIT-LOG-V1"`, the metadata envelope includes:

```json
{
  "data": "<base64-encoded audit record>",
  "content_hash": "<sha256 of original file>",
  "stamp_id": "<postage stamp used>",
  "provenance_standard": "AUDIT-LOG-V1"
}
```

## Files

| File | Description |
|------|-------------|
| `demo.sh` | Shell demo — uploads 3 records, downloads and verifies one |
| `run_demo.py` | Python demo — same workflow with argparse support |
| `audit_record_001.json` | Sample: transaction approval event |
| `audit_record_002.json` | Sample: data access event |
| `audit_record_003.json` | Sample: configuration change event |
