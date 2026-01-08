# Swarm Provenance CLI Examples

Real-world usage examples for the Swarm Provenance CLI, demonstrating practical scenarios from basic uploads to enterprise compliance workflows.

## Prerequisites

1. **Install the CLI**:
   ```bash
   pip install swarm-provenance-uploader
   # Or for development:
   pip install -e .
   ```

2. **Verify installation**:
   ```bash
   swarm-prov-upload --version
   swarm-prov-upload health
   ```

3. **Gateway access**: Examples use the default gateway (`provenance-gateway.datafund.io`). No local Bee node required.

## Examples Overview

| # | Example | Description | Key Features |
|---|---------|-------------|--------------|
| 01 | [Basic Upload/Download](./01-basic-upload-download/) | Core functionality demo | `upload`, `download`, metadata structure |
| 02 | [Audit Trail](./02-audit-trail/) | Compliance & regulatory records | `--std` flag, batch processing |
| 03 | [Scientific Data](./03-scientific-data/) | Research data preservation | `--duration`, PROV-O standard |
| 04 | [Batch Processing](./04-batch-processing/) | Cost-optimized bulk uploads | `--stamp-id` reuse, manifests |
| 05 | [Encrypted Data](./05-encrypted-data/) | Secure data handling | `--enc` flag, AES-256-GCM |
| 06 | [Market Memory](./06-market-memory/) | Verifiable trading records | Memory units, canonical hashing |
| 07 | [Stamp Management](./07-stamp-management/) | Stamp lifecycle operations | `stamps list/info/extend` |
| 08 | [CI/CD Integration](./08-ci-cd-integration/) | DevOps automation | GitHub Actions, GitLab CI |
| 09 | [Verification](./09-verification/) | Integrity & tamper detection | Hash verification, reports |

## Quick Start

### 1. Basic Upload
```bash
# Upload a file (purchases stamp automatically, 25-hour validity)
swarm-prov-upload upload --file mydata.txt

# Output: Swarm reference hash (64 characters)
# Example: a1b2c3d4e5f6...
```

### 2. Download & Verify
```bash
# Download and verify integrity
swarm-prov-upload download <swarm_hash> --output-dir ./downloads

# Creates:
#   downloads/<hash>.meta.json  - Full metadata
#   downloads/<hash>.data       - Original file content
```

### 3. Check Your Stamps
```bash
# List all your postage stamps
swarm-prov-upload stamps list

# Get details on a specific stamp
swarm-prov-upload stamps info <stamp_id>
```

## Directory Structure

```
examples/
├── README.md                 # This file
├── common/                   # Shared utilities
│   ├── __init__.py
│   ├── sample_generator.py   # Generate sample data files
│   └── verify.py             # Verification helpers
├── 01-basic-upload-download/
├── 02-audit-trail/
├── 03-scientific-data/
├── 04-batch-processing/
├── 05-encrypted-data/
├── 06-market-memory/
├── 07-stamp-management/
├── 08-ci-cd-integration/
└── 09-verification/
```

## Running Examples

Each example directory contains:
- `README.md` - Detailed explanation and context
- `demo.sh` - Shell script you can run directly
- `run_demo.py` - Python script version (programmatic usage)
- Sample data files

### Shell Demo
```bash
cd examples/01-basic-upload-download
chmod +x demo.sh
./demo.sh
```

### Python Demo
```bash
cd examples/01-basic-upload-download
python run_demo.py
```

## Common Utilities

The `common/` directory provides shared utilities:

```python
from examples.common.sample_generator import generate_audit_log, generate_dataset
from examples.common.verify import verify_download, compare_hashes
```

## Environment Configuration

Examples use environment variables from `.env` (optional):

```bash
# Backend selection (default: gateway)
PROVENANCE_BACKEND=gateway

# Gateway URL (default: https://provenance-gateway.datafund.io)
PROVENANCE_GATEWAY_URL=https://provenance-gateway.datafund.io

# Default stamp duration in hours (default: 25, minimum: 24)
DEFAULT_POSTAGE_DURATION_HOURS=25
```

## Cost Considerations

- **Single uploads**: Each upload purchases a new stamp (~25 hours validity)
- **Batch uploads**: Purchase one stamp, reuse with `--stamp-id` for multiple files
- **Size presets**: Use `--size small|medium|large` for optimized pricing
- **Duration**: Use `--duration <hours>` for longer retention (minimum 24 hours)

## Troubleshooting

### Health Check Fails
```bash
swarm-prov-upload health --verbose
```
Check if the gateway is accessible from your network.

### Stamp Not Usable
New stamps need ~20-60 seconds to become usable. The CLI automatically waits and retries.

### Download Verification Fails
If you see `UNVERIFIED` in the output filename, the data hash doesn't match. This indicates potential tampering or corruption.

## Related Resources

- [Main README](../README.md) - Full CLI documentation
- [Gateway API](https://provenance-gateway.datafund.io) - API documentation
- [Swarm Documentation](https://docs.ethswarm.org/) - Swarm network details
