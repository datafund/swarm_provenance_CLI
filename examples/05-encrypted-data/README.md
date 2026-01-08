# Encrypted Data with Metadata Example

This example demonstrates how to handle encrypted data with the Swarm Provenance CLI, including the complete encrypt-upload-download-decrypt workflow.

## Use Cases

- **PII Protection**: Storing personal data securely
- **Client-Side Encryption**: Zero-knowledge data preservation
- **Sensitive Documents**: Legal, medical, financial records
- **Encrypted Backups**: Secure offsite backups

## What You'll Learn

- Pre-encrypting data before upload
- Using the `--enc` flag for encryption metadata
- Complete encrypt/upload/download/decrypt cycle
- Key management best practices

## Prerequisites

```bash
swarm-prov-upload --version
swarm-prov-upload health

# For encryption examples (Python)
pip install cryptography
```

## Quick Start

```bash
chmod +x demo.sh
./demo.sh

# Or Python scripts
python encrypt_upload.py
python decrypt_download.py <swarm_ref>
```

## Encryption Workflow

### 1. Encrypt Data Locally

```python
from cryptography.fernet import Fernet

# Generate key (store securely!)
key = Fernet.generate_key()
cipher = Fernet(key)

# Encrypt data
with open("sensitive.txt", "rb") as f:
    plaintext = f.read()
ciphertext = cipher.encrypt(plaintext)

# Save encrypted file
with open("sensitive.enc", "wb") as f:
    f.write(ciphertext)
```

### 2. Upload with Encryption Metadata

```bash
swarm-prov-upload upload \
  --file sensitive.enc \
  --enc "FERNET-AES128-CBC"
```

The `--enc` flag adds encryption details to the metadata:

```json
{
  "data": "<base64 encrypted content>",
  "content_hash": "sha256...",
  "stamp_id": "...",
  "provenance_standard": null,
  "encryption": "FERNET-AES128-CBC"
}
```

### 3. Download and Decrypt

```bash
# Download
swarm-prov-upload download <swarm_ref> --output-dir ./downloads

# Decrypt (using stored key)
python decrypt_download.py <swarm_ref>
```

## Encryption Metadata Values

| Value | Description |
|-------|-------------|
| `AES-256-GCM` | AES with Galois/Counter Mode |
| `AES-256-CBC` | AES with Cipher Block Chaining |
| `FERNET-AES128-CBC` | Python Fernet (AES-128-CBC + HMAC) |
| `CHACHA20-POLY1305` | ChaCha20 with Poly1305 MAC |
| `RSA-OAEP` | RSA with OAEP padding |
| `custom` | Custom encryption scheme |

## Key Management

The CLI does not manage encryption keys. You must:

1. **Generate keys securely** using a cryptographic library
2. **Store keys separately** from encrypted data (never upload keys!)
3. **Back up keys** using secure methods (HSM, vault, etc.)
4. **Document encryption params** for future decryption

## Sample Scripts

### encrypt_upload.py
- Generates encryption key
- Encrypts input file using Fernet
- Uploads encrypted file with `--enc` metadata
- Saves key to secure location

### decrypt_download.py
- Downloads encrypted data from Swarm
- Reads encryption key from secure location
- Decrypts and outputs original content

## Security Considerations

1. **Key Storage**: Never store keys alongside encrypted data
2. **Key Rotation**: Implement key rotation for long-term storage
3. **Algorithm Choice**: Use modern algorithms (AES-GCM, ChaCha20)
4. **Metadata Exposure**: The encryption field is visible in metadata
5. **Local Encryption**: Always encrypt before upload, never after

## Files in This Example

| File | Description |
|------|-------------|
| `README.md` | This documentation |
| `demo.sh` | Shell script demonstration |
| `encrypt_upload.py` | Encrypt and upload workflow |
| `decrypt_download.py` | Download and decrypt workflow |

## Next Steps

- [02-audit-trail](../02-audit-trail/) - Add audit logging for encrypted data
- [04-batch-processing](../04-batch-processing/) - Encrypt multiple files efficiently
