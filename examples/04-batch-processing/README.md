# Example 04: Batch Processing

Demonstrates uploading multiple files efficiently by reusing a single postage stamp.

## What This Demonstrates

- Uploading multiple files with stamp reuse (`--stamp-id`)
- Using `--size medium` for appropriate stamp sizing
- Extracting stamp ID from verbose (`-v`) output
- Building a manifest (JSON) mapping filenames to Swarm references
- Downloading and verifying one file from the batch

## Use Case

When archiving multiple log files, dataset partitions, or document collections, purchasing a new stamp for each file is wasteful and slow. By capturing the stamp ID from the first upload and reusing it for subsequent uploads, you skip the stamp purchase step entirely — reducing upload time from ~60 seconds to ~5 seconds per file.

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

### 1. Upload first file with verbose output

The first upload uses `--size medium -v` to get detailed output including the stamp ID:

```bash
swarm-prov-upload upload --file sample_files/log_entry_001.json --size medium -v --usePool
```

Extract the stamp ID from the verbose output line: `Stamp ID Received: <64-char-hex>`

### 2. Upload remaining files with stamp reuse

Subsequent uploads skip stamp purchase by providing the captured stamp ID:

```bash
swarm-prov-upload upload --file sample_files/log_entry_002.json --stamp-id <stamp_id>
swarm-prov-upload upload --file sample_files/log_entry_003.json --stamp-id <stamp_id>
```

### 3. Build manifest

Create a JSON file mapping each filename to its Swarm reference for later retrieval.

### 4. Download and verify

```bash
swarm-prov-upload download <swarm_hash> --output-dir ./downloads
```

Compare SHA-256 hashes to verify integrity.

## Batch Upload Helper

The `batch_upload.py` script automates the full batch workflow:

```bash
python batch_upload.py --directory ./sample_files
python batch_upload.py --directory ./sample_files --std "PROV-STD-V1"
```

It handles stamp capture, reuse, and manifest generation automatically.

## Sample Files

| File | Description |
|------|-------------|
| `sample_files/log_entry_001.json` | INFO: User login event |
| `sample_files/log_entry_002.json` | WARNING: Rate limit approached |
| `sample_files/log_entry_003.json` | ERROR: Transaction failure |

## Files

| File | Description |
|------|-------------|
| `demo.sh` | Shell demo — batch upload with stamp reuse |
| `run_demo.py` | Python demo — same workflow with argparse support |
| `batch_upload.py` | Standalone batch upload tool with manifest generation |
| `sample_files/` | Directory of sample log entries |
