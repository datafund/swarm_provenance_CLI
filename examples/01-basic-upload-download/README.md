# 01 - Basic Upload/Download

The fundamental Swarm Provenance workflow: upload a file, get a Swarm reference, download it back, and verify integrity.

## What This Demonstrates

- Uploading a file with `swarm-prov-upload upload`
- Understanding the metadata JSON envelope (base64 data + SHA-256 hash + stamp ID)
- Downloading with `swarm-prov-upload download`
- Verifying data integrity via SHA-256 hash comparison

## Prerequisites

```bash
pip install -e "."
```

## Quick Start

### Shell demo

```bash
chmod +x demo.sh
./demo.sh
```

### Python demo

```bash
python run_demo.py
```

## Step-by-Step Walkthrough

### 1. Upload a file

```bash
swarm-prov-upload upload --file sample.txt --usePool
```

Output:

```
Uploading file: sample.txt
  File size: 634 bytes
  SHA256: a1b2c3...
Acquiring stamp from pool...
  Stamp ID: abc123...
Uploading to Swarm...
  Swarm Reference: def456...
```

The **Swarm Reference** is the immutable content-addressed hash. Save it — this is how you retrieve the data later.

### 2. Download the data

```bash
swarm-prov-upload download <swarm_reference> --output-dir ./downloads
```

This downloads the metadata envelope, extracts the base64-encoded data, decodes it, and verifies the SHA-256 hash automatically.

### 3. Verify integrity

The CLI verifies integrity on download automatically. You can also compare manually:

```bash
sha256sum sample.txt
sha256sum downloads/sample.txt
```

If the hashes match, the data is intact — no tampering occurred between upload and download.

## JSON Output

For scripting, use the `--json` flag:

```bash
swarm-prov-upload upload --file sample.txt --usePool --json
```

Returns:

```json
{
  "swarm_hash": "def456...",
  "content_hash": "a1b2c3...",
  "stamp_id": "abc123...",
  "file_name": "sample.txt",
  "file_size": 634,
  "provenance_standard": null
}
```

## With Provenance Standard

Tag uploads with a provenance standard identifier:

```bash
swarm-prov-upload upload --file sample.txt --std "PROV-STD-V1" --usePool
```

This adds `"provenance_standard": "PROV-STD-V1"` to the metadata envelope, useful for categorizing data by compliance framework or data standard.

## Metadata Envelope Structure

The CLI wraps your file in a JSON metadata envelope before uploading:

```json
{
  "data": "<base64-encoded file content>",
  "content_hash": "<SHA-256 of original file>",
  "stamp_id": "<postage stamp used>",
  "provenance_standard": "<optional standard tag>",
  "encryption": "<optional encryption details>"
}
```

This envelope is what gets stored on Swarm. On download, the CLI unwraps it and restores the original file.

## Files

| File | Description |
|------|-------------|
| `sample.txt` | Sample data file to upload |
| `demo.sh` | Shell script walkthrough |
| `run_demo.py` | Python script version |
