# Example 05: Encrypted Data

Demonstrates pre-encryption workflow for sensitive data on Swarm.

## What This Demonstrates

- Encrypting data locally before upload
- Using `--enc "AES-256-GCM"` to tag the metadata envelope with encryption info
- Downloading and verifying the encrypted payload is intact
- Decrypting and verifying the content matches the original

## Use Case

When storing sensitive data (medical records, financial data, PII) on a decentralized network, the data should be encrypted before upload. The `--enc` flag doesn't perform encryption — it records the encryption method in the metadata envelope so consumers know how to decrypt.

**Workflow:**
1. Encrypt data locally using your preferred encryption library
2. Upload the encrypted payload with `--enc` tag to record the method
3. Store the encryption key separately (key management system, hardware wallet, etc.)
4. To retrieve: download the payload, check the encryption tag, decrypt with the key

## Prerequisites

1. Install the CLI: `pip install -e .`
2. Gateway access (default, no setup needed)
3. For shell demo: `openssl` (pre-installed on macOS/Linux)

## Quick Start

### Shell (uses openssl)

```bash
chmod +x demo.sh
./demo.sh
```

### Python (uses XOR cipher — demo only)

```bash
python run_demo.py
```

## Step-by-Step Walkthrough

### 1. Encrypt the data locally

**Shell (openssl):**
```bash
openssl rand -out key.bin 32
openssl enc -aes-256-cbc -salt -in sensitive_data.txt -out sensitive_data.enc -pass file:key.bin -pbkdf2
```

**Python (demo XOR cipher):**
```python
key = os.urandom(32)
encrypted = xor_encrypt(original_data, key)
```

### 2. Upload encrypted payload with encryption tag

```bash
swarm-prov-upload upload --file sensitive_data.enc --enc "AES-256-GCM" --usePool
```

The `--enc` flag adds an `encryption` field to the metadata envelope, recording that this data is encrypted with AES-256-GCM.

### 3. Download and verify the encrypted payload

```bash
swarm-prov-upload download <swarm_hash> --output-dir ./downloads
shasum -a 256 sensitive_data.enc downloads/*.data
```

### 4. Decrypt and verify

```bash
openssl enc -aes-256-cbc -d -in downloads/*.data -out decrypted.txt -pass file:key.bin -pbkdf2
shasum -a 256 sensitive_data.txt decrypted.txt
```

## Metadata Envelope

When uploaded with `--enc "AES-256-GCM"`, the envelope includes:

```json
{
  "data": "<base64-encoded encrypted payload>",
  "content_hash": "<sha256 of encrypted payload>",
  "stamp_id": "<postage stamp used>",
  "encryption": "AES-256-GCM"
}
```

The `encryption` field tells consumers what algorithm was used, but the key is not stored on Swarm.

## Security Notes

- The demo scripts use simplified encryption (openssl CBC / XOR) for illustration only
- In production, use a proper encryption library with authenticated encryption (e.g., AES-256-GCM via `cryptography` library)
- Never store encryption keys alongside encrypted data
- Use a key management system (KMS) for production key storage
- The `--enc` tag is metadata only — it does not perform encryption

## Files

| File | Description |
|------|-------------|
| `demo.sh` | Shell demo — encrypts with openssl, uploads, downloads, decrypts |
| `run_demo.py` | Python demo — XOR cipher (demo only), same workflow |
| `sensitive_data.txt` | Sample PII data (fictional patient record) |
