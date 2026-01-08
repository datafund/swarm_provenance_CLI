# Basic Upload/Download Example

This example demonstrates the core functionality of the Swarm Provenance CLI: uploading a file to the Swarm network and downloading it back with integrity verification.

## What You'll Learn

- How to upload a file to Swarm
- Understanding the metadata wrapper structure
- How to download and verify file integrity
- Interpreting the Swarm reference hash

## Prerequisites

```bash
# Verify CLI is installed
swarm-prov-upload --version

# Check gateway health
swarm-prov-upload health
```

## Quick Start

### Option 1: Shell Script
```bash
chmod +x demo.sh
./demo.sh
```

### Option 2: Python Script
```bash
python run_demo.py
```

## Step-by-Step Walkthrough

### 1. Upload a File

```bash
swarm-prov-upload upload --file sample.txt
```

**What happens:**
1. The CLI reads `sample.txt` and computes its SHA256 hash
2. A new postage stamp is purchased (25-hour validity by default)
3. The file content is Base64-encoded and wrapped in metadata
4. The wrapped metadata is uploaded to Swarm
5. A 64-character Swarm reference hash is returned

**Example output:**
```
Purchasing new stamp (duration: 25 hours)...
Stamp purchased: abc123...
Waiting for stamp to become usable...
Uploading data...
Success! Swarm reference: 7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069
```

### 2. Download and Verify

```bash
swarm-prov-upload download <swarm_hash> --output-dir ./output
```

**What happens:**
1. The metadata JSON is fetched from Swarm
2. The Base64 data is extracted and decoded
3. SHA256 hash is computed and compared to stored hash
4. If hashes match, files are saved; otherwise marked as UNVERIFIED

**Output files:**
- `<hash>.meta.json` - Full metadata including Base64 data
- `<hash>.data` - Decoded original file content

### 3. Examine the Metadata

The metadata JSON structure:

```json
{
  "data": "VGhpcyBpcyBzYW1wbGUgZGF0YS4uLg==",
  "content_hash": "7f83b165...",
  "stamp_id": "abc123def456...",
  "provenance_standard": null,
  "encryption": null
}
```

| Field | Description |
|-------|-------------|
| `data` | Base64-encoded original file content |
| `content_hash` | SHA256 hash of the raw (not encoded) file |
| `stamp_id` | Postage stamp used for this upload |
| `provenance_standard` | Optional standard identifier (e.g., "PROV-O") |
| `encryption` | Optional encryption details |

## Files in This Example

| File | Description |
|------|-------------|
| `README.md` | This documentation |
| `demo.sh` | Shell script demonstrating upload/download |
| `sample.txt` | Sample data file to upload |
| `run_demo.py` | Python script version of the demo |

## Understanding the Swarm Reference

The Swarm reference hash (64 hex characters) is:
- **Content-addressed**: The hash is derived from the content
- **Permanent**: As long as the stamp is valid, the data is retrievable
- **Unique**: Different content produces different hashes
- **Verifiable**: Anyone with the hash can retrieve and verify the data

## Verbose Mode

For debugging, use the `--verbose` flag:

```bash
swarm-prov-upload upload --file sample.txt --verbose
```

This shows:
- HTTP requests and responses
- Stamp purchase details
- Upload progress
- Full metadata structure

## Common Issues

### "Stamp not usable yet"
New stamps take 20-60 seconds to become usable. The CLI automatically retries.

### "Gateway health check failed"
Ensure you have internet connectivity and the gateway is accessible:
```bash
swarm-prov-upload health --verbose
```

### Hash mismatch on download
If the downloaded file is named `*.UNVERIFIED.data`, the integrity check failed. This could indicate:
- Data corruption during transfer
- Tampered content
- Wrong Swarm reference

## Next Steps

- [02-audit-trail](../02-audit-trail/) - Add provenance standard tagging
- [04-batch-processing](../04-batch-processing/) - Upload multiple files efficiently
- [09-verification](../09-verification/) - Advanced verification workflows
