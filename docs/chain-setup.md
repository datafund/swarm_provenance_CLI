# Blockchain Anchoring Setup Guide

This guide walks you through setting up on-chain provenance anchoring for the Swarm Provenance CLI.

## What is Blockchain Anchoring?

Blockchain anchoring registers Swarm hashes on the **DataProvenance smart contract** (Base chain), providing:

- **Immutable proof** that data was registered at a specific time
- **Ownership tracking** tied to an Ethereum address
- **Transformation lineage** linking original data to derived versions
- **Access logging** recording who accessed what data

Once a Swarm hash is anchored on-chain, anyone can independently verify its registration, ownership, and history.

### How It Works

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     Blockchain Anchoring Flow                                │
└──────────────────────────────────────────────────────────────────────────────┘

   Your CLI                      Base Chain                   Block Explorer
      │                              │                              │
      │  1. Anchor hash              │                              │
      │  (sign + send tx)            │                              │
      │─────────────────────────────>│                              │
      │                              │                              │
      │  2. TX mined in block        │                              │
      │<─────────────────────────────│                              │
      │  { tx_hash, block_number }   │                              │
      │                              │                              │
      │  3. Verify on explorer       │                              │
      │──────────────────────────────────────────────────────────-->│
      │                              │                              │
      │  Later: Query provenance     │                              │
      │─────────────────────────────>│                              │
      │                              │                              │
      │  { owner, timestamp,         │                              │
      │    transformations,          │                              │
      │    accessors, status }       │                              │
      │<─────────────────────────────│                              │
```

**Key points:**
- Each anchor operation is a blockchain transaction (requires ETH for gas)
- Read operations (get, verify) are free — no gas required
- Data is NOT stored on-chain; only the hash is registered
- The actual data remains on Swarm; the chain provides proof of registration

## Prerequisites

- Python 3.8+
- An Ethereum wallet (MetaMask, hardware wallet, etc.)
- Base Sepolia ETH (for gas fees on testnet)

## Step 1: Install Blockchain Dependencies

Install the CLI with blockchain support:

```bash
pip install -e .[blockchain]
```

This installs:
- `web3` — Blockchain interaction (RPC calls, transaction sending)
- `eth-account` — Ethereum account management and transaction signing

## Step 2: Create or Export a Wallet

### Option A: Use an existing wallet

Export your private key from MetaMask or another wallet. **Be careful with private keys!**

In MetaMask:
1. Click the three dots menu
2. Go to Account Details
3. Click "Export Private Key"
4. Enter your password
5. Copy the private key (starts with 0x)

### Option B: Create a new wallet

```python
from eth_account import Account
account = Account.create()
print(f"Address: {account.address}")
print(f"Private key: {account.key.hex()}")
```

**Important:** Store your private key securely. Never commit it to version control.

## Step 3: Get Testnet ETH

For development and testing, use Base Sepolia testnet. You need ETH for gas fees.

### Get testnet ETH

1. Go to https://www.alchemy.com/faucets/base-sepolia
2. Enter your wallet address
3. Request test ETH

Alternative faucets:
- https://faucet.quicknode.com/base/sepolia
- https://www.coinbase.com/faucets/base-ethereum-goerli-faucet

**Typical costs:** An anchor transaction uses ~95,000 gas. At current Base gas prices, this costs fractions of a cent.

## Step 4: Configure the CLI

### Environment variables

Add to your `.env` file:

```bash
# Your wallet private key (KEEP SECRET!)
PROVENANCE_WALLET_KEY=0x...your_private_key_here...

# Chain: base-sepolia (testnet) or base (mainnet)
CHAIN_NAME=base-sepolia

# Optional: Enable chain features by default
# CHAIN_ENABLED=true

# Optional: Custom RPC URL (uses preset if not set)
# CHAIN_RPC_URL=https://your-rpc-provider.com

# Optional: Custom contract address (uses preset if not set)
# CHAIN_CONTRACT=0x...

# Optional: Custom block explorer URL (uses preset if not set)
# CHAIN_EXPLORER_URL=https://your-explorer.com
```

### Verify configuration

```bash
# Check wallet balance and chain info
swarm-prov-upload chain balance

# Expected output:
# Chain Wallet:
# ----------------------------------------
#   Address:  0x742d...fE00
#   Balance:  0.01 ETH
#   Chain:    base-sepolia
#   Contract: 0x9a3c...fE64
#
# Get testnet ETH: https://www.alchemy.com/faucets/base-sepolia
```

## Step 5: Anchor Your First Hash

### Basic anchoring

```bash
# Anchor a Swarm hash on-chain
swarm-prov-upload chain anchor <swarm_hash>

# Output:
# Anchored successfully!
#   Hash:    a028d937...
#   Type:    swarm-provenance
#   Tx:      0xbb...
#   Block:   12345679
#   Gas:     95000
#   Explorer: https://sepolia.basescan.org/tx/0xbb...
```

### Verify the anchor

```bash
# Check if a hash is registered (exit code 0=yes, 1=no)
swarm-prov-upload chain verify <swarm_hash>

# Get the full provenance record
swarm-prov-upload chain get <swarm_hash>
```

### End-to-end workflow: Upload + Anchor + Verify

```bash
# 1. Upload data to Swarm
swarm-prov-upload upload --file data.txt
# Output: Swarm Reference Hash: abc123...

# 2. Anchor the Swarm hash on-chain
swarm-prov-upload chain anchor abc123...

# 3. Later: verify the data is anchored
swarm-prov-upload chain verify abc123...

# 4. Get full provenance record
swarm-prov-upload chain get abc123... --json
```

## Common Operations

### Record a data transformation

When you transform data (filter, anonymize, aggregate), link the original and derived hashes:

```bash
# Original data must be anchored first
swarm-prov-upload chain anchor <original_hash>

# Record the transformation
swarm-prov-upload chain transform <original_hash> <new_hash> --description "Anonymized PII fields"
```

### Record data access

Log that data was accessed (idempotent — safe to record multiple times):

```bash
swarm-prov-upload chain access <swarm_hash>
```

### Anchor with a custom type

```bash
swarm-prov-upload chain anchor <hash> --type "dataset"
swarm-prov-upload chain anchor <hash> --type "model-weights"
```

### JSON output for scripting

All chain commands support `--json` for machine-readable output:

```bash
swarm-prov-upload chain get <hash> --json
swarm-prov-upload chain balance --json
swarm-prov-upload chain anchor <hash> --json
```

### Use a different chain or RPC

```bash
# Use a specific chain
swarm-prov-upload --chain base chain balance

# Use a custom RPC endpoint
swarm-prov-upload --chain-rpc https://your-rpc.io chain balance
```

## Data Status Values

On-chain records have a status field:

| Status | Value | Meaning |
|--------|-------|---------|
| `ACTIVE` | 0 | Data is live and accessible (default) |
| `RESTRICTED` | 1 | Data access is restricted |
| `DELETED` | 2 | Data has been logically deleted |

Status changes are recorded on-chain and can be audited.

## Switching to Mainnet

When ready for production:

1. Get real ETH on Base mainnet
2. Update your `.env`:

```bash
CHAIN_NAME=base
```

Or use the CLI flag:

```bash
swarm-prov-upload --chain base chain anchor <hash>
```

**Warning:** Mainnet uses real funds. Start with small amounts and test thoroughly.

## Troubleshooting

### "Blockchain dependencies not installed"

Install the blockchain extras:
```bash
pip install -e .[blockchain]
```

### "No wallet private key configured"

Set the `PROVENANCE_WALLET_KEY` environment variable:
```bash
export PROVENANCE_WALLET_KEY=0x...
```

Or add it to your `.env` file.

### "Cannot connect to chain"

Check your RPC endpoint. The default Base Sepolia RPC (`https://sepolia.base.org`) is public and rate-limited. For production, use a dedicated RPC provider:
- [Alchemy](https://www.alchemy.com/)
- [Infura](https://www.infura.io/)
- [QuickNode](https://www.quicknode.com/)

```bash
export CHAIN_RPC_URL=https://base-sepolia.g.alchemy.com/v2/YOUR_KEY
```

### "Transaction reverted"

Common causes:
- **Insufficient gas** — Get more testnet ETH from the faucet
- **Hash already registered** — A hash can only be anchored once
- **Not the owner** — Only the data owner can modify records (unless using delegates)
- **Invalid hash format** — Must be 64 hex characters

### "Chain ID mismatch"

Your RPC URL doesn't match the selected chain. Ensure `CHAIN_NAME` and `CHAIN_RPC_URL` are consistent:
- `base-sepolia` expects chain ID 84532
- `base` expects chain ID 8453

### "No contract address configured"

Base mainnet contract is not yet deployed. Use `base-sepolia` for testing, or provide a custom address:
```bash
export CHAIN_CONTRACT=0x...your_contract_address...
```

## Security Best Practices

1. **Never commit private keys** to version control
2. **Use a dedicated wallet** for anchoring, not your main wallet
3. **Start with testnet** before using real funds
4. **Use environment files** (`.env`) instead of command line arguments for secrets
5. **Monitor gas costs** — anchor transactions are cheap but add up at scale
6. **Use batch operations** (`batch_anchor`, `batch_access` via Python API) for efficiency

## Network Details

### Base Sepolia (Testnet)

| Property | Value |
|----------|-------|
| Chain ID | 84532 |
| RPC URL | https://sepolia.base.org |
| Block Explorer | https://sepolia.basescan.org |
| DataProvenance Contract | `0x9a3c6F47B69211F05891CCb7aD33596290b9fE64` |

### Base (Mainnet)

| Property | Value |
|----------|-------|
| Chain ID | 8453 |
| RPC URL | https://mainnet.base.org |
| Block Explorer | https://basescan.org |
| DataProvenance Contract | Not yet deployed |

## Additional Resources

- [Base Documentation](https://docs.base.org)
- [Etherscan Base Sepolia](https://sepolia.basescan.org)
- [Alchemy Base Sepolia Faucet](https://www.alchemy.com/faucets/base-sepolia)
