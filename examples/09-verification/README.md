# Example 09: Verification & Integrity

Demonstrates data verification, tamper detection, and integrity reporting.

## What This Demonstrates

- Uploading a document and verifying download integrity via SHA-256
- Tamper detection: comparing original vs modified file hashes
- Using `--verify` flag for notary signature verification
- Generating a verification report

## Use Case

Content-addressed storage provides built-in integrity guarantees: any change to the data produces a different hash. This example shows how to:

- **Verify downloads**: Confirm that a downloaded file matches the original
- **Detect tampering**: Show that even a small change (e.g., changing "24 months" to "36 months" in a contract) produces a completely different hash
- **Notary verification**: Use the `--verify` flag to check for notary signatures on downloaded data
- **Build trust reports**: Generate verification reports for compliance or audit purposes

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

### 1. Upload original document

```bash
swarm-prov-upload upload --file sample_document.txt --usePool
```

### 2. Download and verify

```bash
swarm-prov-upload download <swarm_hash> --output-dir ./downloads
shasum -a 256 sample_document.txt downloads/*.data
```

Hashes must match — proving the document is intact.

### 3. Tamper detection

Compare the original and tampered files:

```bash
shasum -a 256 sample_document.txt sample_document_tampered.txt
```

The tampered file has "24 months" changed to "36 months" — a single word change that produces a completely different hash.

### 4. Notary verification

```bash
swarm-prov-upload download <swarm_hash> --output-dir ./downloads --verify
```

The `--verify` flag checks for notary signatures. If no signatures exist, the download still succeeds.

## Helper Tools

### Integrity Checker

Verify a Swarm reference against an expected hash:

```bash
python integrity_checker.py --ref <swarm_hash> --original-file sample_document.txt
python integrity_checker.py --ref <swarm_hash> --expected-hash <sha256>
```

### Tamper Detection

Compare two files and show differences:

```bash
python tamper_detection.py --original sample_document.txt --tampered sample_document_tampered.txt
```

## Sample Documents

| File | Description |
|------|-------------|
| `sample_document.txt` | Original data processing agreement (24-month retention) |
| `sample_document_tampered.txt` | Tampered version (36-month retention — one word changed) |

## Files

| File | Description |
|------|-------------|
| `demo.sh` | Shell demo — upload, verify, tamper test, notary check |
| `run_demo.py` | Python demo — same workflow with argparse support |
| `integrity_checker.py` | Standalone integrity verification tool |
| `tamper_detection.py` | Standalone tamper detection tool |
| `sample_document.txt` | Original document |
| `sample_document_tampered.txt` | Tampered document for comparison |
