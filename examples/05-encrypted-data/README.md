# Example 05: Encrypted data

Demonstrates pre-encryption workflow for sensitive data on Swarm.

## What this demonstrates

- Encrypting data locally before upload
- Using `--enc` to tag the metadata envelope with the cipher actually used: `"AES-256-CBC-PBKDF2"` in `demo.sh` (openssl AES-256-CBC with a PBKDF2-derived key), `"XOR-DEMO"` in `run_demo.py`
- Downloading and verifying the encrypted payload is intact
- Decrypting and verifying the content matches the original

## Use case

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

## Quick start

### Shell (uses openssl)

```bash
chmod +x demo.sh
./demo.sh
```

### Python (toy XOR cipher: not encryption to rely on)

```bash
python run_demo.py
```

## Step-by-step walkthrough

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
swarm-prov-upload upload --file sensitive_data.enc --enc "AES-256-CBC-PBKDF2" --usePool
```

The `--enc` flag adds an `encryption` field to the metadata envelope, recording that this data is encrypted with AES-256-CBC and a PBKDF2-derived key (the openssl command above). Use the label of the cipher you actually used. `run_demo.py` tags its uploads `"XOR-DEMO"`: its repeating-key XOR is a toy for the demo, not encryption to rely on.

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

## Metadata envelope

When uploaded with `--enc "AES-256-CBC-PBKDF2"`, the envelope includes:

```json
{
  "data": "<base64-encoded encrypted payload>",
  "content_hash": "<sha256 of encrypted payload>",
  "stamp_id": "<postage stamp used>",
  "encryption": "AES-256-CBC-PBKDF2"
}
```

The `encryption` field tells consumers what algorithm was used, but the key is not stored on Swarm.

## Security notes

- The demo scripts use simplified encryption (openssl CBC / XOR) for illustration only
- In production, use a proper encryption library with authenticated encryption (e.g., AES-256-GCM via `cryptography` library)
- Never store encryption keys alongside encrypted data
- Use a key management system (KMS) for production key storage
- The `--enc` tag is metadata only — it does not perform encryption

## Files

| File | Description |
|------|-------------|
| `demo.sh` | Shell demo — encrypts with openssl, uploads, downloads, decrypts |
| `run_demo.py` | Python demo — toy XOR cipher (not encryption to rely on), same workflow |
| `sensitive_data.txt` | Sample PII data (fictional patient record) |
