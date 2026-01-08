# Data Verification & Integrity Check Example

This example demonstrates comprehensive verification workflows for tamper detection, integrity checking, and building verification reports.

## Use Cases

- **Tamper Detection**: Verify data hasn't been modified
- **Audit Verification**: Prove record authenticity
- **Chain of Custody**: Verify data lineage
- **Compliance Reporting**: Generate verification reports

## What You'll Learn

- Downloading and verifying data integrity
- Detecting tampered files (hash mismatch)
- Building verification reports
- Chain-of-custody verification patterns

## Prerequisites

```bash
swarm-prov-upload --version
swarm-prov-upload health
```

## Quick Start

```bash
chmod +x demo.sh
./demo.sh

# Or Python scripts
python integrity_checker.py <swarm_ref>
python tamper_detection.py <swarm_ref>
```

## Verification Workflow

```
┌─────────────────────┐
│ Download from Swarm │
│  (metadata + data)  │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Extract metadata   │
│  (content_hash)     │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│  Compute SHA256     │
│  of downloaded data │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   Compare hashes    │
└─────────┬───────────┘
          │
    ┌─────┴─────┐
    │           │
    ▼           ▼
┌───────┐  ┌──────────┐
│ VALID │  │ INVALID  │
│       │  │ (Tamper) │
└───────┘  └──────────┘
```

## CLI Verification

The download command automatically verifies integrity:

```bash
swarm-prov-upload download <swarm_ref> --output-dir ./verify
```

**Successful verification:**
```
Downloaded: abc123.meta.json (verified)
Downloaded: abc123.data (SHA256 verified)
```

**Failed verification:**
```
WARNING: Hash mismatch detected
Downloaded: abc123.UNVERIFIED.data
```

## Integrity Checker

The `integrity_checker.py` script provides detailed verification:

```bash
python integrity_checker.py <swarm_ref>
```

Output includes:
- Download status
- Expected vs actual hash
- Verification result
- Metadata analysis

## Tamper Detection

The `tamper_detection.py` script simulates tamper detection:

```bash
python tamper_detection.py <swarm_ref>
```

Demonstrates:
- Original data verification (should pass)
- Modified data detection (should fail)
- Report generation

## Verification Report

Generated reports include:

```json
{
  "verification_id": "ver-20250108-001",
  "timestamp": "2025-01-08T12:00:00Z",
  "swarm_ref": "abc123...",
  "results": {
    "download_success": true,
    "hash_verified": true,
    "expected_hash": "sha256...",
    "actual_hash": "sha256...",
    "metadata_valid": true
  },
  "conclusion": "VERIFIED",
  "details": {
    "provenance_standard": "AUDIT-LOG-V1",
    "stamp_id": "stamp...",
    "encryption": null
  }
}
```

## Chain of Custody

For chain-of-custody verification:

1. **Upload original** with provenance standard
2. **Store reference** in custody log
3. **At each transfer**, verify and re-upload
4. **Final verification** checks entire chain

```python
chain = [
    {"actor": "Alice", "action": "created", "ref": "abc123..."},
    {"actor": "Bob", "action": "received", "ref": "def456..."},
    {"actor": "Carol", "action": "verified", "ref": "ghi789..."},
]

# Verify each link
for link in chain:
    verify(link["ref"])
```

## Files in This Example

| File | Description |
|------|-------------|
| `README.md` | This documentation |
| `demo.sh` | Shell script demonstration |
| `integrity_checker.py` | Verification tool |
| `tamper_detection.py` | Tamper detection demo |

## Best Practices

1. **Always Verify**: Check integrity on every download
2. **Store References**: Keep Swarm refs with verification timestamps
3. **Document Chain**: Record who verified what and when
4. **Report Failures**: Alert on any verification failure
5. **Independent Verification**: Allow third parties to verify

## Next Steps

- [02-audit-trail](../02-audit-trail/) - Auditable verification records
- [06-market-memory](../06-market-memory/) - Canonical hash verification
