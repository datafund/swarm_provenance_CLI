# Swarm Provenance Uploader

A CLI toolkit to wrap data files within a metadata structure
and upload them to the Swarm decentralized storage network.

**Supports two backends:**
- **Gateway** (default): Uses `provenance-gateway.datafund.io` - no local Bee node required
- **Local**: Direct Bee node communication for development/self-hosted setups

## Quick Start

```bash
# Install
pip install -e .

# Check version
swarm-prov-upload --version

# Check connectivity
swarm-prov-upload health

# Upload data (purchases stamp with 25 hour validity)
swarm-prov-upload upload --file /path/to/data.txt

# Upload using pooled stamp (faster, ~5s vs >1min)
swarm-prov-upload upload --file /path/to/data.txt --usePool

# Upload with custom duration (hours)
swarm-prov-upload upload --file /path/to/data.txt --duration 48

# Upload with size preset (small, medium, large)
swarm-prov-upload upload --file /path/to/data.txt --size medium

# Upload with existing stamp (skip purchase)
swarm-prov-upload upload --file /path/to/data.txt --stamp-id <existing_stamp_id>

# Download and verify
swarm-prov-upload download <swarm_hash> --output-dir ./downloads

# Upload with notary signing (gateway only)
swarm-prov-upload upload --file /path/to/data.txt --sign notary

# Download with signature verification
swarm-prov-upload download <swarm_hash> --output-dir ./downloads --verify
```

## Setup

1. Create and activate a virtual environment.
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   # Or on Windows: .\venv\Scripts\activate
   ```
2. Copy `.env.example` to `.env` and adjust values if needed.
   ```bash
   cp .env.example .env
   ```
3. Install in editable mode, including testing dependencies:
   ```bash
   pip install -e .[testing]
   ```

## Backend Configuration

### Gateway Backend (Default)
No local Bee node required. Uses the Datafund provenance gateway.

```bash
# Uses gateway by default
swarm-prov-upload upload --file data.txt

# Or explicitly
swarm-prov-upload --backend gateway upload --file data.txt

# Custom gateway URL
swarm-prov-upload --gateway-url https://custom.gateway.io upload --file data.txt
```

### Local Backend
For development or self-hosted Swarm nodes.

```bash
# Use local Bee node
swarm-prov-upload --backend local upload --file data.txt

# Custom Bee URL
swarm-prov-upload --backend local upload --file data.txt --bee-url http://localhost:1633
```

### Environment Variables

```bash
PROVENANCE_BACKEND=gateway           # gateway (default) or local
PROVENANCE_GATEWAY_URL=https://provenance-gateway.datafund.io
BEE_GATEWAY_URL=http://localhost:1633
DEFAULT_POSTAGE_DEPTH=17
DEFAULT_POSTAGE_DURATION_HOURS=25    # Stamp validity in hours (gateway only, min 24)
DEFAULT_POSTAGE_AMOUNT=1000000000    # Legacy: for local backend
```

## x402 Payment Mode (Optional)

x402 enables pay-per-request payments using USDC on Base chain. When the gateway requires payment (HTTP 402), the CLI automatically handles the payment flow.

### Quick Start

```bash
# Install with x402 support
pip install -e .[x402]

# Configure wallet (testnet)
export SWARM_X402_PRIVATE_KEY=0x...  # Your wallet private key
export X402_ENABLED=true
export X402_NETWORK=base-sepolia     # Testnet (default)

# Check x402 status
swarm-prov-upload x402 status

# Check USDC balance
swarm-prov-upload x402 balance

# Upload with x402 enabled (prompts for payment confirmation)
swarm-prov-upload --x402 upload --file data.txt

# Upload with auto-pay (no prompts, up to $1.00)
swarm-prov-upload --x402 --auto-pay --max-pay 1.00 upload --file data.txt
```

### x402 Commands

```bash
# Show configuration status
swarm-prov-upload x402 status

# Check wallet USDC balance
swarm-prov-upload x402 balance

# Show setup instructions
swarm-prov-upload x402 info
```

### x402 Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `X402_ENABLED` | Enable x402 payments | `false` |
| `SWARM_X402_PRIVATE_KEY` | Wallet private key (keep secret!) | - |
| `X402_NETWORK` | `base-sepolia` (testnet) or `base` (mainnet) | `base-sepolia` |
| `X402_AUTO_PAY` | Auto-pay without prompts | `false` |
| `X402_MAX_AUTO_PAY_USD` | Maximum auto-pay amount per request | `1.00` |
| `X402_RPC_URL` | Custom RPC URL (optional) | Uses default |

### Global Flags

| Flag | Description |
|------|-------------|
| `--x402` / `--no-x402` | Enable/disable x402 for this command |
| `--auto-pay` / `--no-auto-pay` | Enable/disable auto-pay |
| `--max-pay FLOAT` | Maximum auto-pay amount in USD |
| `--x402-network TEXT` | Network: `base-sepolia` or `base` |

### Testnet Setup

1. **Get testnet ETH** (for gas): https://www.alchemy.com/faucets/base-sepolia
2. **Get testnet USDC**: https://faucet.circle.com/
3. **Configure wallet**: Set `SWARM_X402_PRIVATE_KEY` with your wallet's private key

See [docs/x402-setup.md](docs/x402-setup.md) for detailed setup instructions.

## Blockchain Anchoring (Optional)

On-chain provenance anchoring registers Swarm hashes on the DataProvenance smart contract (Base chain), providing immutable proof of data registration, ownership, and transformation lineage.

### Quick Start

```bash
# Install with blockchain support
pip install -e .[blockchain]

# Configure wallet
export PROVENANCE_WALLET_KEY=0x...  # Your wallet private key
export CHAIN_NAME=base-sepolia      # Testnet (default)

# Check wallet balance
swarm-prov-upload chain balance

# Anchor a Swarm hash on-chain
swarm-prov-upload chain anchor <swarm_hash>

# Get the on-chain provenance record
swarm-prov-upload chain get <swarm_hash>

# Verify a hash is anchored
swarm-prov-upload chain verify <swarm_hash>
```

### Chain Commands

```bash
# Wallet balance and chain info
swarm-prov-upload chain balance
swarm-prov-upload chain balance --json

# Anchor a Swarm hash on-chain
swarm-prov-upload chain anchor <swarm_hash>
swarm-prov-upload chain anchor <swarm_hash> --type "dataset"
swarm-prov-upload chain anchor <swarm_hash> --owner <address>  # anchor as delegate

# Record data access
swarm-prov-upload chain access <swarm_hash>

# Record a data transformation (original must be anchored first)
swarm-prov-upload chain transform <original_hash> <new_hash> --description "Anonymized PII"
swarm-prov-upload chain transform <orig> <new> --restrict-original  # restrict original after transform

# Get full provenance record
swarm-prov-upload chain get <swarm_hash>
swarm-prov-upload chain get <swarm_hash> --json
swarm-prov-upload chain get <swarm_hash> --follow           # walk transformation chain
swarm-prov-upload chain get <swarm_hash> --follow --depth 3 # limit traversal depth

# Verify a hash is registered on-chain (exit code 0=yes, 1=no)
swarm-prov-upload chain verify <swarm_hash>

# Query or set data status
swarm-prov-upload chain status <swarm_hash>                 # show current status
swarm-prov-upload chain status <swarm_hash> --set restricted  # set status (active|restricted|deleted)

# Transfer ownership
swarm-prov-upload chain transfer <swarm_hash> --to <new_owner_address>

# Authorize or revoke a delegate
swarm-prov-upload chain delegate <address> --authorize
swarm-prov-upload chain delegate <address> --revoke

# Protect: composite workflow (transform + restrict original)
swarm-prov-upload chain protect <original_hash> <new_hash> --description "Removed PII"
swarm-prov-upload chain protect <orig> <new> --anchor-new --description "Redacted"  # anchor new hash first
```

### Global Flags

| Flag | Description |
|------|-------------|
| `--chain TEXT` | Blockchain: `base-sepolia` (testnet) or `base` (mainnet) |
| `--chain-rpc TEXT` | Custom RPC URL for blockchain connection |

### Blockchain Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `CHAIN_ENABLED` | Enable blockchain features | `false` |
| `CHAIN_NAME` | `base-sepolia` (testnet) or `base` (mainnet) | `base-sepolia` |
| `PROVENANCE_WALLET_KEY` | Wallet private key (keep secret!) | - |
| `CHAIN_RPC_URL` | Custom RPC URL (optional) | Uses preset |
| `CHAIN_CONTRACT` | Custom contract address (optional) | Uses preset |
| `CHAIN_EXPLORER_URL` | Custom block explorer URL (optional) | Uses preset |

### Testnet Setup

1. **Get testnet ETH** (for gas): https://www.alchemy.com/faucets/base-sepolia
2. **Get testnet USDC** (if using x402): https://faucet.circle.com/
3. **Configure wallet**: Set `PROVENANCE_WALLET_KEY` with your wallet's private key

See [docs/chain-setup.md](docs/chain-setup.md) for detailed setup instructions and [docs/chain-workflows.md](docs/chain-workflows.md) for workflow diagrams.

### ChainClient Python API

```python
from swarm_provenance_uploader.core.chain_client import ChainClient

client = ChainClient(chain="base-sepolia")
result = client.anchor(swarm_hash="<64-char-hex>", data_type="swarm-provenance")
print(f"TX: {result.explorer_url}")
```

**Write operations** (require wallet + gas):
- `anchor(swarm_hash, data_type)` - Register a hash on-chain
- `anchor_for(swarm_hash, owner, data_type)` - Register on behalf of another owner
- `batch_anchor(swarm_hashes, data_types)` - Batch register multiple hashes
- `transform(original_hash, new_hash, description)` - Record data transformation
- `access(swarm_hash)` - Record data access
- `batch_access(swarm_hashes)` - Batch record access
- `set_status(swarm_hash, status)` - Change data status (ACTIVE/RESTRICTED/DELETED)
- `transfer_ownership(swarm_hash, new_owner)` - Transfer data ownership
- `set_delegate(delegate, authorized)` - Authorize/revoke a delegate

**Read operations** (no gas required):
- `get(swarm_hash)` - Get full provenance record
- `verify(swarm_hash)` - Check if hash is registered
- `get_provenance_chain(swarm_hash)` - Follow transformation lineage
- `balance()` - Get wallet balance and chain info
- `health_check()` - Check RPC connectivity

## Run Tests

### Unit Tests (Mocked)

Unit tests use mocks and do not require a live Bee node or gateway.

```bash
# Run all tests (unit + integration)
pytest

# Run only unit tests (skip integration)
pytest --ignore=tests/test_integration.py
```

### Integration Tests (Real Backends)

Integration tests hit real services. They auto-skip if backends are unavailable.

```bash
# Run only integration tests
pytest tests/test_integration.py -v

# Run only local Bee tests
pytest -m local_bee

# Run only gateway tests
pytest -m gateway

# Run blockchain tests (local Hardhat)
pytest -m blockchain

# Run blockchain tests on Base Sepolia (uses testnet gas)
pytest -m "blockchain and slow"
```

**Requirements:**
- Local Bee: Running at `http://localhost:1633`
- Gateway: Available at `https://provenance-gateway.datafund.io`
- Local Hardhat: Running at `http://localhost:8545` with DataProvenance deployed
- Base Sepolia: `PROVENANCE_WALLET_KEY` set with funded wallet

## Usage

### Data Operations

```bash
# Upload data to Swarm (default: 25 hour stamp validity)
swarm-prov-upload upload --file /path/to/data.txt --std "PROV-STD-V1" --verbose

# Upload with custom duration (hours, min 24)
swarm-prov-upload upload --file /path/to/data.txt --duration 168  # 7 days

# Upload with size preset (small, medium, large)
swarm-prov-upload upload --file /path/to/data.txt --size large

# Upload with existing stamp (cost savings, faster)
swarm-prov-upload upload --file /path/to/data.txt --stamp-id <existing_stamp_id>

# Upload using pooled stamp (instant ~5s vs >1min for purchase)
swarm-prov-upload upload --file /path/to/data.txt --usePool

# Download and verify data
swarm-prov-upload download <swarm_hash> --output-dir ./downloads --verbose
```

**Upload Options:**
| Option | Description |
|--------|-------------|
| `--duration`, `-d` | Stamp validity in hours (min 24, gateway only) |
| `--size` | Size preset: `small`, `medium`, `large` (gateway only) |
| `--depth` | Technical depth parameter (16-32) |
| `--stamp-id`, `-s` | Use existing stamp (skip purchase) |
| `--usePool` | Acquire stamp from pool instead of purchasing (gateway only, faster) |
| `--sign` | Sign document with notary service (value: `notary`, gateway only) |
| `--amount` | Legacy: PLUR amount (local backend) |

### Stamp Management (Gateway only)

```bash
# List all stamps
swarm-prov-upload stamps list

# Get stamp details
swarm-prov-upload stamps info <stamp_id>

# Extend stamp TTL
swarm-prov-upload stamps extend <stamp_id> --amount 1000000

# Check stamp health (can it be used for uploads?)
swarm-prov-upload stamps check <stamp_id>

# View stamp pool status
swarm-prov-upload stamps pool-status
```

#### Stamp Health Check

The `stamps check` command performs a detailed health check on a stamp:

```bash
swarm-prov-upload stamps check <stamp_id>
```

**Output example:**
```
Stamp Health Check:
--------------------------------------------------
  Stamp ID:   13be53a5...fc0d3c80
  Can upload: Yes

  Warnings:
    [LOW_TTL] TTL is below 24 hours
```

**Possible issues:**

| Code | Type | Meaning |
|------|------|---------|
| `EXPIRED` | Error | Stamp has expired, cannot upload |
| `NOT_USABLE` | Error | Stamp exists but is not usable |
| `NOT_FOUND` | Error | Stamp does not exist |
| `LOW_TTL` | Warning | TTL below 24 hours, consider extending |
| `HIGH_UTILIZATION` | Warning | Stamp is nearly full |

Use `-v` (verbose) for detailed metrics including TTL, utilization percentage, and expiration date.

### Stamp Pool (Gateway only)

#### What is a Stamp Pool?

Normally, purchasing a postage stamp on Swarm takes >1 minute because the transaction must be confirmed on-chain and the stamp must sync across the network. The gateway maintains a **pool of pre-purchased stamps** that can be acquired instantly (~5 seconds).

#### When to Use `--usePool`

| Scenario | Recommendation |
|----------|----------------|
| Quick uploads, testing, demos | Use `--usePool` |
| Production with predictable volume | Use `--usePool` |
| Pool is empty (check with `stamps pool-status`) | Use regular purchase (omit `--usePool`) |
| Need specific stamp configuration | Use regular purchase with `--duration`/`--depth` |

#### Size Presets

Stamps come in three sizes based on storage capacity:

| Size | Depth | Typical Use |
|------|-------|-------------|
| `small` (default) | 17 | Small files (<1MB) |
| `medium` | 20 | Medium files (1-100MB) |
| `large` | 22 | Large files (>100MB) |

#### Usage Examples

```bash
# Upload using a pooled stamp (uses 'small' size by default)
swarm-prov-upload upload --file data.txt --usePool

# Upload with specific size from pool
swarm-prov-upload upload --file data.txt --usePool --size medium

# Check pool availability before uploading
swarm-prov-upload stamps pool-status
```

#### Pool Status Output

```
Stamp Pool Status:
--------------------------------------------------
  Status:       Enabled
  Total stamps: 3

  Availability by size:
    small    (depth 17): 1 available / 1 total (target: 1)
    medium   (depth 20): 2 available / 2 total (target: 1)
```

- **Enabled/Disabled**: Whether the pool feature is active on this gateway
- **Available**: Stamps ready for immediate acquisition
- **Total**: All stamps in pool (including recently acquired ones being replenished)
- **Target**: The gateway's target reserve level for each size

#### Error Handling

If the pool is empty or unavailable, the CLI provides helpful guidance:

```
ERROR: No stamps available in pool for requested size/depth.
Try again later, use a different size, or use regular purchase (without --usePool).
```

**Fallback behavior**: If your requested size isn't available but a larger size is, the pool will automatically substitute a larger stamp and notify you.

#### Benefits

- **Speed**: ~5 seconds vs >1 minute for regular purchase
- **No waiting**: Pooled stamps are already usable (no sync delay)
- **Automatic fallback**: Larger stamps substituted if exact size unavailable
- **Same pricing**: x402 costs are identical to regular purchases

### Notary Signing (Gateway only)

The notary service adds cryptographic signatures to uploaded data, providing proof of authenticity and integrity.

#### How It Works

When you upload with `--sign notary`, the gateway's notary service:
1. Receives your data payload
2. Signs a hash of the data + timestamp using EIP-191 (Ethereum signed messages)
3. Adds the signature to a `signatures` array in the document
4. Returns the signed document stored on Swarm

The signature can be verified locally using standard Ethereum signature recovery.

#### Usage

```bash
# Upload with notary signing
swarm-prov-upload upload --file data.txt --sign notary

# Check notary service status
swarm-prov-upload notary info

# Quick status check
swarm-prov-upload notary status

# Verify a signed document file
swarm-prov-upload notary verify --file signed_document.json
```

#### Verification on Download

```bash
# Download and automatically verify signature
swarm-prov-upload download <swarm_hash> --output-dir ./downloads --verify

# If verification fails, you'll see an error with details
```

#### Signature Structure

The notary adds a signature entry in the following format:

```json
{
  "data": { ... },
  "signatures": [
    {
      "type": "notary",
      "signer": "0x...",
      "timestamp": "2026-01-21T16:30:00+00:00",
      "data_hash": "sha256...",
      "signature": "0x...",
      "hashed_fields": ["data"],
      "signed_message_format": "{data_hash}|{timestamp}"
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `type` | Always `notary` |
| `signer` | Ethereum address of the notary |
| `timestamp` | ISO 8601 timestamp when signed (gateway's witness time) |
| `data_hash` | SHA256 hash of canonical JSON of `data` field |
| `signature` | EIP-191 signature of `{data_hash}|{timestamp}` |
| `hashed_fields` | Fields whose values were hashed (typically `["data"]`) |
| `signed_message_format` | Format pattern of the signed message |

#### Verifying Signatures Manually

The signature can be verified with any Ethereum library:

1. Compute canonical JSON of `data` field (sorted keys, no whitespace)
2. Hash with SHA256
3. Construct message: `{data_hash}|{timestamp}`
4. Verify EIP-191 signature recovers to expected address

```python
# Example using eth-account
from eth_account import Account
from eth_account.messages import encode_defunct
import json, hashlib

data_json = json.dumps(document["data"], sort_keys=True, separators=(",", ":"))
data_hash = hashlib.sha256(data_json.encode()).hexdigest()
message = f"{data_hash}|{signature['timestamp']}"
signable = encode_defunct(text=message)
recovered = Account.recover_message(signable, signature=signature["signature"])
assert recovered.lower() == expected_address.lower()
```

### Information Commands

```bash
# Check backend health
swarm-prov-upload health

# Wallet info (gateway only)
swarm-prov-upload wallet

# Chequebook info (gateway only)
swarm-prov-upload chequebook
```

Use `swarm-prov-upload --help` for all options.

## Architecture & Features

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           SWARM PROVENANCE UPLOADER                            │
│                              Architecture Diagram                               │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                                CLI INTERFACE                                    │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────────────────┐ │
│  │ GLOBAL OPTIONS  │  │ DATA COMMANDS    │  │ INFO COMMANDS                   │ │
│  │                 │  │                  │  │                                 │ │
│  │ --backend       │  │ upload           │  │ health                          │ │
│  │   gateway|local │  │ download         │  │ wallet (gateway)                │ │
│  │ --gateway-url   │  │                  │  │ chequebook (gateway)            │ │
│  │ --x402          │  ├──────────────────┤  │                                 │ │
│  │ --auto-pay      │  │ STAMPS COMMANDS  │  ├─────────────────────────────────┤ │
│  │ --max-pay       │  │ (gateway only)   │  │ NOTARY COMMANDS (gateway only)  │ │
│  │ --chain         │  │ stamps list      │  │ notary info                     │ │
│  │ --chain-rpc     │  │ stamps info      │  │ notary status                   │ │
│  │ --usePool       │  │ stamps extend    │  │ notary verify                   │ │
│  │ --sign          │  │ stamps check     │  │                                 │ │
│  │ --verify        │  │ stamps pool-stat │  ├─────────────────────────────────┤ │
│  │                 │  │                  │  │ x402 status                     │ │
│  │ Built with:     │  ├──────────────────┤  │ x402 balance                    │ │
│  │ • Rich output   │  │ CHAIN COMMANDS   │  │ x402 info                       │ │
│  │                 │  │ (optional)       │  │                                 │ │
│  │                 │  │ chain balance    │  │                                 │ │
│  │                 │  │ chain anchor     │  │                                 │ │
│  │                 │  │ chain get        │  │                                 │ │
│  │                 │  │ chain verify     │  │                                 │ │
│  │                 │  │ chain access     │  │                                 │ │
│  │                 │  │ chain transform  │  │                                 │ │
│  │                 │  │ chain status     │  │                                 │ │
│  │                 │  │ chain transfer   │  │                                 │ │
│  │                 │  │ chain delegate   │  │                                 │ │
│  │                 │  │ chain protect    │  │                                 │ │
│  └─────────────────┘  └──────────────────┘  └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CORE BUSINESS LOGIC                               │
│  ┌───────────────────┐  ┌─────────────────┐  ┌──────────────────────────────┐  │
│  │ FILE_UTILS.PY     │  │ METADATA_       │  │ BACKEND CLIENTS              │  │
│  │                   │  │ BUILDER.PY      │  │                              │  │
│  │ • File I/O        │  │                 │  │ gateway_client.py (default)  │  │
│  │ • SHA256 hashing  │  │ • Pydantic      │  │ • Gateway API wrapper        │  │
│  │ • Base64 encode   │  │   validation    │  │ • Full feature support       │  │
│  │ • Base64 decode   │  │ • JSON          │  │ • x402 payment integration   │  │
│  │ • Size calculation│  │   serialization │  │                              │  │
│  │ • Error handling  │  │ • Metadata      │  │ swarm_client.py (local)      │  │
│  │                   │  │   wrapping      │  │ • Direct Bee API             │  │
│  ├───────────────────┤  │                 │  │ • Local/self-hosted          │  │
│  │ X402_CLIENT.PY    │  │                 │  │                              │  │
│  │ (optional)        │  │                 │  │ chain_client.py (optional)   │  │
│  │ • EIP-712 signing │  │                 │  │ • On-chain anchoring         │  │
│  │ • USDC on Base    │  │                 │  │ • DataProvenance contract    │  │
│  │ • 402 handling    │  │                 │  │ • Provenance chain tracking  │  │
│  └───────────────────┘  └─────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                             DATA MODELS & CONFIG                               │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │ MODELS.PY                       │  │ CONFIG.PY                           │  │
│  │                                 │  │                                     │  │
│  │ ProvenanceMetadata (Pydantic):  │  │ Environment Configuration:          │  │
│  │ ┌─────────────────────────────┐ │  │ • PROVENANCE_BACKEND               │  │
│  │ │ • data: str (Base64)        │ │  │ • PROVENANCE_GATEWAY_URL           │  │
│  │ │ • content_hash: str (SHA256)│ │  │ • BEE_GATEWAY_URL                  │  │
│  │ │ • stamp_id: str (64 hex)    │ │  │ • DEFAULT_POSTAGE_DEPTH            │  │
│  │ │ • provenance_standard: str? │ │  │ • DEFAULT_POSTAGE_AMOUNT           │  │
│  │ │ • encryption: str?          │ │  │ • .env file support                │  │
│  │ └─────────────────────────────┘ │  │                                     │  │
│  │                                 │  │ x402 Configuration:                 │  │
│  │ x402 Payment Models:            │  │ • X402_ENABLED                      │  │
│  │ • X402PaymentOption             │  │ • SWARM_X402_PRIVATE_KEY            │  │
│  │ • X402PaymentRequirements       │  │ • X402_NETWORK                      │  │
│  │ • X402PaymentPayload            │  │ • X402_AUTO_PAY                     │  │
│  │                                 │  │ • X402_MAX_AUTO_PAY_USD             │  │
│  │ Chain Models:                   │  │                                     │  │
│  │ • ChainProvenanceRecord         │  │ Chain Configuration:                │  │
│  │ • AnchorResult                  │  │ • CHAIN_ENABLED                     │  │
│  │ • TransformResult               │  │ • CHAIN_NAME                        │  │
│  │ • AccessResult                  │  │ • PROVENANCE_WALLET_KEY             │  │
│  │ • ChainWalletInfo               │  │ • CHAIN_RPC_URL                     │  │
│  │                                 │  │ • CHAIN_EXPLORER_URL                │  │
│  └─────────────────────────────────┘  └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                UPLOAD WORKFLOW                                 │
│                                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ 1. READ     │───▶│ 2. HASH &   │───▶│ 3. PURCHASE │───▶│ 4. WRAP &   │     │
│  │    FILE     │    │    ENCODE   │    │    STAMP    │    │    UPLOAD   │     │
│  │             │    │             │    │             │    │             │     │
│  │ • File I/O  │    │ • SHA256    │    │ • HTTP POST │    │ • Metadata  │     │
│  │ • Validate  │    │ • Base64    │    │ • Wait loop │    │ • JSON wrap │     │
│  │ • Read raw  │    │ • Size calc │    │ • Retry     │    │ • HTTP POST │     │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                                                 │
│                              ┌─────────────────┐                               │
│                              │ 5. RETURN HASH  │                               │
│                              │                 │                               │
│                              │ • Swarm ref     │                               │
│                              │ • 64-char hex   │                               │
│                              │ • Success msg   │                               │
│                              └─────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                             x402 PAYMENT FLOW (Optional)                        │
│                                                                                 │
│  When gateway returns HTTP 402 Payment Required:                               │
│                                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ 1. RECEIVE  │───▶│ 2. PARSE    │───▶│ 3. CONFIRM  │───▶│ 4. SIGN &   │     │
│  │    402      │    │    OPTIONS  │    │    PAYMENT  │    │    RETRY    │     │
│  │             │    │             │    │             │    │             │     │
│  │ • HTTP 402  │    │ • Extract   │    │ • Auto-pay  │    │ • EIP-712   │     │
│  │ • JSON body │    │   accepts[] │    │   or prompt │    │ • X-PAYMENT │     │
│  │ • x402 hdr  │    │ • Match net │    │ • Check bal │    │ • Retry req │     │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                                                 │
│  Networks: Base Sepolia (testnet) | Base (mainnet)                             │
│  Payment: USDC stablecoin via x402 facilitator (https://x402.org)              │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                               DOWNLOAD WORKFLOW                                │
│                                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ 1. FETCH    │───▶│ 2. PARSE &  │───▶│ 3. DECODE & │───▶│ 4. VERIFY & │     │
│  │    METADATA │    │    VALIDATE │    │    EXTRACT  │    │    SAVE     │     │
│  │             │    │             │    │             │    │             │     │
│  │ • HTTP GET  │    │ • JSON      │    │ • Base64    │    │ • SHA256    │     │
│  │ • Error     │    │ • Pydantic  │    │ • Extract   │    │ • Compare   │     │
│  │   handling  │    │ • Schema    │    │ • Raw bytes │    │ • Save both │     │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                                                 │
│                              ┌─────────────────┐                               │
│                              │ 5. SUCCESS      │                               │
│                              │                 │                               │
│                              │ • .data file    │                               │
│                              │ • .meta.json    │                               │
│                              │ • Verification  │                               │
│                              └─────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                              SWARM NETWORK LAYER                               │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │ GATEWAY (DEFAULT)               │  │ SWARM NETWORK                       │  │
│  │                                 │  │                                     │  │
│  │ provenance-gateway.datafund.io  │  │ • Decentralized storage             │  │
│  │ API Endpoints:                  │  │ • Content-addressable               │  │
│  │ • /api/v1/stamps/ - CRUD        │  │ • Redundant & persistent            │  │
│  │ • /api/v1/data/ - Upload/DL     │  │ • Cryptographic integrity           │  │
│  │ • /api/v1/wallet - Balance      │  │ • Economic incentives               │  │
│  │ • /api/v1/chequebook            │  │ • Censorship resistant              │  │
│  │                                 │  │                                     │  │
│  │ No local node required!         │  │                                     │  │
│  ├─────────────────────────────────┤  │                                     │  │
│  │ LOCAL BEE (--backend local)     │  │                                     │  │
│  │ Direct /bzz, /stamps endpoints  │  │                                     │  │
│  │ Requires running Bee node       │  │                                     │  │
│  └─────────────────────────────────┘  └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                                KEY FEATURES                                    │
│                                                                                 │
│  🔒 SECURITY & INTEGRITY           📦 DATA PROCESSING                          │
│  • SHA256 content verification    • Base64 encoding/decoding                  │
│  • Cryptographic hashing          • JSON metadata wrapping                    │
│  • Immutable storage              • Pydantic data validation                  │
│  • Tamper detection               • Type-safe operations                      │
│                                                                                 │
│  🌐 DECENTRALIZED STORAGE          ⚙️  OPERATIONAL                             │
│  • Swarm network integration      • Verbose/concise modes                     │
│  • Content-addressable            • Comprehensive error handling              │
│  • Censorship resistant           • Retry logic with backoff                  │
│  • Persistent & redundant         • Environment configuration                 │
│                                                                                 │
│  🏷️  PROVENANCE METADATA           🧪 TESTING & RELIABILITY                   │
│  • Standard identifier support    • Mock-based test suite                     │
│  • Optional encryption details    • No live node required for tests           │
│  • Bidirectional operations       • Comprehensive CLI testing                 │
│  • Metadata preservation          • CI/CD ready                               │
│                                                                                 │
│  🔗 POSTAGE STAMP SYSTEM           📊 MONITORING & DEBUGGING                   │
│  • Economic spam prevention       • Detailed verbose output                   │
│  • TTL-based data persistence     • HTTP request/response logging             │
│  • Automatic stamp validation     • Progress indicators                       │
│  • Configurable parameters        • Error context & suggestions               │
│                                                                                 │
│  🔀 DUAL BACKEND SUPPORT           🚀 GATEWAY FEATURES                         │
│  • Gateway backend (default)      • stamps list - View all stamps             │
│  • Local Bee backend option       • stamps extend - Add TTL                   │
│  • Seamless switching             • wallet - View BZZ balance                 │
│  • Same CLI for both              • chequebook - View chequebook              │
│                                                                                 │
│  💳 x402 PAYMENTS (Optional)       🔏 NOTARY SIGNING (Gateway only)            │
│  • USDC on Base chain             • EIP-191 message signatures                │
│  • Auto-pay mode                  • Cryptographic proof of authenticity       │
│  • Payment confirmation           • Verifiable timestamps                     │
│  • Lazy dependency loading        • Local signature verification              │
│  • Balance checking               • Ethereum address recovery                 │
│                                                                                 │
│  ⛓️  BLOCKCHAIN ANCHORING (Optional)                                           │
│  • DataProvenance smart contract  • On-chain data registration                │
│  • Transformation lineage         • Access tracking                           │
│  • Ownership transfer             • Delegate authorization                    │
│  • Base Sepolia / Base mainnet    • Lazy dependency loading                   │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                               TECHNOLOGY STACK                                 │
│                                                                                 │
│  🐍 CORE TECHNOLOGIES              📚 KEY LIBRARIES                            │
│  • Python 3.8+                    • Typer - CLI framework                     │
│  • Modular architecture           • Pydantic v2 - Data validation             │
│  • Type hints throughout          • Requests - HTTP client                    │
│  • Async-ready design             • Python-dotenv - Config management         │
│                                   • eth-account - Ethereum signing (optional) │
│                                   • web3 - Blockchain interaction (optional)  │
│                                                                                 │
│  🔧 DEVELOPMENT TOOLS              🧪 TESTING FRAMEWORK                        │
│  • Virtual environment            • Pytest - Test runner                      │
│  • Editable installation          • Pytest-mock - Mocking utilities           │
│  • Environment configuration      • Requests-mock - HTTP mocking              │
│  • Rich CLI output                • No external dependencies for tests        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

This architecture diagram shows the **Swarm Provenance Uploader** as a layered system that:

1. **CLI Layer**: Provides user-friendly commands with rich help and validation
2. **Core Logic**: Handles file processing, metadata creation, and Swarm communication
3. **Data Models**: Ensures type safety and validation with Pydantic schemas
4. **Network Layer**: Interfaces with Bee nodes and the Swarm decentralized network

**Key Strengths**:
- ✅ **Dual backend support** (gateway default, local Bee optional)
- ✅ **Bidirectional operations** (upload/download)
- ✅ **Integrity verification** (SHA256 hashing)
- ✅ **Metadata preservation** (provenance standards)
- ✅ **Decentralized storage** (Swarm network)
- ✅ **Production ready** (error handling, retries, logging)

## Project Directory Structure

```
swarm_provenance_uploader/
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── docs/
│   └── x402-setup.md            # x402 payment setup guide
├── swarm_provenance_uploader/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── exceptions.py            # Custom exception classes
│   ├── models.py
│   ├── chain/                   # Blockchain subpackage (optional)
│   │   ├── __init__.py
│   │   ├── provider.py          # Web3 connection management
│   │   ├── wallet.py            # Transaction signing
│   │   ├── contract.py          # DataProvenance contract wrapper
│   │   └── abi/
│   │       └── DataProvenance.json  # Contract ABI
│   └── core/
│       ├── __init__.py
│       ├── chain_client.py      # High-level chain facade (optional)
│       ├── file_utils.py
│       ├── gateway_client.py    # Gateway API client (default)
│       ├── metadata_builder.py
│       ├── notary_utils.py      # Notary signature verification
│       ├── swarm_client.py      # Local Bee API client
│       └── x402_client.py       # x402 payment client (optional)
└── tests/
    ├── __init__.py
    ├── test_chain_client.py     # Chain client unit tests (mocked)
    ├── test_cli.py              # CLI unit tests (mocked)
    ├── test_gateway_client.py   # GatewayClient unit tests (mocked)
    ├── test_integration.py      # Integration tests (real backends)
    ├── test_notary_utils.py     # Notary utils unit tests (mocked)
    └── test_x402_client.py      # x402 unit tests (mocked)
```

