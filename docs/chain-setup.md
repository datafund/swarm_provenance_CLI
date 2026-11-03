# Blockchain anchoring setup guide

This guide walks you through setting up on-chain provenance anchoring for the Swarm Provenance CLI.

## What is blockchain anchoring?

Blockchain anchoring registers Swarm hashes on the **DataProvenance smart contract** (Base chain), providing:

- **Immutable proof** that data was registered at a specific time
- **Ownership tracking** tied to an Ethereum address
- **Transformation lineage** linking original data to derived versions
- **Access logging** recording who accessed what data

Once a Swarm hash is anchored on-chain, anyone can independently verify its registration, ownership, and history.

### How it works

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
- Read operations (`get`, `verify`, `lookup`, and `status` without `--set`) are free and need no wallet key
- Data is NOT stored on-chain; only the hash is registered
- The actual data remains on Swarm; the chain provides proof of registration

## Prerequisites

- Python 3.9+
- An Ethereum wallet (MetaMask, hardware wallet, etc.)
- Base Sepolia ETH (for gas fees on testnet)

## Step 1: Install blockchain dependencies

Install the CLI with blockchain support:

```bash
pip install -e .[blockchain]
```

This installs:
- `web3` — Blockchain interaction (RPC calls, transaction sending)
- `eth-account` — Ethereum account management and transaction signing

## Step 2: Create or export a wallet

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

## Step 3: Get testnet ETH

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

### Private key

The CLI reads the wallet key from the `PROVENANCE_WALLET_KEY` environment variable. Do not type the key into your shell, for example with `export PROVENANCE_WALLET_KEY=0x...`: it stays in your shell history. Instead, read it from your password manager's command-line tool (such as 1Password `op read`, `pass`, or macOS `security`) into the variable for one command:

```bash
PROVENANCE_WALLET_KEY="$(op read 'op://<vault>/<item>/<field>')" swarm-prov-upload chain balance
```

If you must keep the key in a `.env` file, make the file readable only by you (`chmod 600 .env`) and never commit it. Use a dedicated wallet that holds only what anchoring needs.

### Environment variables

Add to your `.env` file:

```bash
# Wallet private key: not stored here, see "Private key" above

# Chain: base-sepolia (testnet) or base (mainnet)
CHAIN_NAME=base-sepolia

# Optional: Custom RPC URL (uses preset if not set)
# CHAIN_RPC_URL=https://your-rpc-provider.com

# Optional: Custom contract address (uses preset if not set)
# CHAIN_CONTRACT=0x...

# Optional: Block the contract was deployed in, where event scans start.
# A custom CHAIN_CONTRACT does not use the preset's deploy block.
# It also turns on the duplicate check of `chain transform` on a v1 contract
# when the chain has more than 50,000 blocks.
# It must not be later than the contract's real deploy block: events before
# it are not read.
# CHAIN_DEPLOY_BLOCK=12345678

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
#   Contract: 0xD4a7...f80a
#
# Get testnet ETH: https://www.alchemy.com/faucets/base-sepolia
```

## Step 5: Anchor your first hash

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
#   Explorer: https://base-sepolia.blockscout.com/tx/0xbb...
```

### Verify the anchor

```bash
# Check if a hash is registered (exit code 0=yes, 1=no).
# The output shows the record's status (ACTIVE, RESTRICTED or DELETED) and owner.
# "Verified:" means ACTIVE. A RESTRICTED or DELETED record prints
# "Anchored on-chain (status: DELETED): ..." and still exits 0.
swarm-prov-upload chain verify <swarm_hash>

# Also require an ACTIVE record and a given owner (exit code 1 if either differs).
# The owner is compared without regard to case or checksum.
swarm-prov-upload chain verify <swarm_hash> --require-active --owner 0xYourAddress

# Get the full provenance record
swarm-prov-upload chain get <swarm_hash>
```

### End-to-end workflow: Upload + anchor + verify

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

## Common operations

### Record a data transformation

When you transform data (filter, anonymize, aggregate), link the original and derived hashes:

```bash
# Original data must be anchored first
swarm-prov-upload chain anchor <original_hash>

# Record the transformation
swarm-prov-upload chain transform <original_hash> <new_hash> --description "Anonymized PII fields"
```

### Merge multiple datasets

When you combine multiple data sources into one, record it as a merge transformation:

```bash
# All source hashes must be anchored first
swarm-prov-upload chain anchor <hash_a>
swarm-prov-upload chain anchor <hash_b>

# Record the merge (2-50 sources supported)
swarm-prov-upload chain merge <hash_a> <hash_b> <merged_hash> --description "Combined datasets"

# With a custom data type for the merged result
swarm-prov-upload chain merge <hash_a> <hash_b> <merged_hash> --type "combined-dataset" -d "Merged A+B"
```

### Walk the provenance chain

Trace data lineage back through transformations:

```bash
# Get full provenance record
swarm-prov-upload chain get <hash>

# Walk the full transformation chain (follows links to root)
swarm-prov-upload chain get <hash> --follow

# Limit traversal depth (1-50, default 10)
swarm-prov-upload chain get <hash> --follow --depth 2

# JSON output for scripting
swarm-prov-upload chain get <hash> --follow --json
```

On a v2 contract, the walk reads the transformation links from the contract state. On a v1 contract, it scans the contract's events from its deploy block. The preset's deploy block is used only for the preset's own contract. With a custom `CHAIN_CONTRACT`, set `CHAIN_DEPLOY_BLOCK` to the block the contract was deployed in. The value must not be later than that block, because events before it are not read. A value above the latest block of the chain, for example one left over after a change of `CHAIN_NAME`, stops the command with an error. Without a deploy block, only the last 50,000 blocks can be scanned. If the chain is longer, the lineage may be incomplete, so the command stops with an error that asks you to set `CHAIN_DEPLOY_BLOCK`, and exits with code 1. `CHAIN_DEPLOY_BLOCK` also turns on the duplicate transformation check of `chain transform` and `chain protect` on a v1 contract. Without it, the check reads the events of the original hash when the chain has at most 50,000 blocks, and is skipped with a warning on a longer chain.

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

All chain commands except `chain verify` support `--json` for machine-readable output:

```bash
swarm-prov-upload chain get <hash> --json
swarm-prov-upload chain balance --json
swarm-prov-upload chain anchor <hash> --json
```

With `--json`, stdout carries exactly one JSON document, for a success or an error, so you can pipe it to `jq`. Everything else (progress, warnings, hints, `-v` debug lines and the text of an error) goes to stderr. The exit codes are the same as without `--json`. Errors in the global options and usage errors (exit 2) are JSON too, when the command you run has `--json` and it is set. `--help` and `--version` print text, not JSON.

An error document has an `error` code and a `message`, and some codes add fields:

| Code | Meaning | Extra fields |
|------|---------|--------------|
| `invalid_input` | A command-line value is not valid, including usage errors (exit 2) | |
| `configuration_error` | The chain settings are not valid, for example an unsupported `CHAIN_NAME`, an invalid `CHAIN_CONTRACT` or `CHAIN_DEPLOY_BLOCK`, a deploy block later than the chain head, or no contract code at the contract address on any RPC | |
| `invalid_gas_limit` | A chain write would use a `CHAIN_GAS_LIMIT` that is not a whole number of at least 21000 | |
| `missing_dependencies` | The blockchain extras are not installed | `install` |
| `connection_failed` | No RPC can be reached | `rpc_url` (redacted) |
| `not_registered` | The hash (or storage reference) has no on-chain record | `data_hash` or `storage_ref` |
| `already_registered` | `chain anchor`: the hash is already anchored | `data_hash`, `owner`, `timestamp`, `data_type` |
| `transaction_failed` | The transaction reverted or could not be sent | `tx_hash` |
| `insufficient_funds` | The wallet cannot pay the gas | `wallet_address`, `balance_eth`, `estimated_cost_eth`, `chain` |
| `receipt_timeout`, `outcome_unknown` | The transaction may still be mined (exit 3) | `tx_hash`, `wait_command` |
| `replaced`, `not_recorded`, `not_verified` | The transaction is not confirmed as recorded | `tx_hash`, `explorer_url` |
| `not_found` | `chain wait`: the RPC does not know the transaction | `tx_hash` |
| `chain_error` | Any other chain error | |
| `interrupted` | The command was stopped with Ctrl+C (exit 130) | |
| `aborted` | A prompt was aborted (exit 1) | |

`chain protect` and `chain transform --restrict-original` report a failed step in their step format, with `failed_step` and an `error` or `unconfirmed` object (see [chain-workflows.md](chain-workflows.md)).

### Use a different chain or RPC

```bash
# Use a specific chain
swarm-prov-upload --chain base chain balance

# Use a custom RPC endpoint
swarm-prov-upload --chain-rpc https://your-rpc.io chain balance
```

## Data status values

On-chain records have a status field:

| Status | Value | Meaning |
|--------|-------|---------|
| `ACTIVE` | 0 | Data is live and accessible (default) |
| `RESTRICTED` | 1 | Data access is restricted |
| `DELETED` | 2 | Data has been logically deleted |

Status changes are recorded on-chain and can be audited.

## Switching to mainnet

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

Commands that write to the chain, and `chain balance`, need a wallet key. Read-only commands (`chain get`, `verify`, `lookup`, and `status` without `--set`) do not.

Set the `PROVENANCE_WALLET_KEY` environment variable for the command, as described in [Private key](#private-key):
```bash
PROVENANCE_WALLET_KEY="$(op read 'op://<vault>/<item>/<field>')" swarm-prov-upload chain balance
```

### "Cannot connect to chain"

Check your RPC endpoint. The default Base Sepolia RPC (`https://sepolia.base.org`) is public and rate-limited. The CLI automatically tries fallback RPCs (`base-sepolia-rpc.publicnode.com`, `base-sepolia.drpc.org`) if the primary cannot be reached, for reads and for the steps of a write before the transaction is sent (see [Which operations use the fallback RPCs](#which-operations-use-the-fallback-rpcs)). For production, use a dedicated RPC provider:
- [Alchemy](https://www.alchemy.com/)
- [Infura](https://www.infura.io/)
- [QuickNode](https://www.quicknode.com/)

```bash
export CHAIN_RPC_URL=https://base-sepolia.g.alchemy.com/v2/YOUR_KEY

# Or set multiple fallback URLs (comma-separated)
export CHAIN_RPC_URLS=https://fallback1.io,https://fallback2.io
```

Like `CHAIN_RPC_URL`, `CHAIN_RPC_URLS` applies whatever chain is selected (`CHAIN_NAME` or `--chain`). If you switch chains, change the URLs too.

#### Which operations use the fallback RPCs

The CLI moves to the next fallback RPC when the RPC in use cannot be reached, times out, or answers with something that is not JSON-RPC (for example an HTML error page). Before a fallback is used, the CLI checks that it reports the chain ID in use. A fallback on another chain is skipped. Each RPC is tried at most once per chain client call: one read, or one write with all its steps. A command that makes several calls, such as `chain protect`, can try an RPC again in a later call. If no RPC is left, the command prints "Cannot connect to chain".

- **Reads** use the fallbacks: `chain get` (also with `--follow`), `chain verify`, `chain lookup`, `chain status` without `--set`, `chain balance`, and the "already registered" check before an anchor.
- **Writes** use the fallbacks only for the steps before the transaction is sent: the chain ID and contract code checks, the "already registered" and duplicate transformation checks, the gas estimate, the nonce, the gas price and the balance check. These steps send nothing, so running them again on another RPC is safe. The duplicate transformation check of `chain transform` reads the contract state on a v2 contract, or scans the transformation events (`eth_getLogs`) on a v1 contract; both reads use the fallbacks. If the check cannot reach any RPC, the command stops with "Cannot connect to chain" before anything is sent. If the RPC answers the check with a JSON-RPC error, or the check fails for another reason, the command stops before anything is sent too, and exits with code 1.
- **Sending the transaction** never moves to a fallback, and the CLI never repeats the request that sends it (web3's own retry is turned off for `eth_sendRawTransaction`). If the connection fails while the transaction is sent, the CLI prints "Outcome unknown" (see below) and does not send it again.
- **Waiting for the receipt** can move to a fallback, for the same transaction hash. Nothing is sent again. If the wait moved to a fallback and that RPC does not return the receipt in time, the CLI prints "Outcome unknown", because the transaction may still be mined.

The CLI does not move to a fallback when the RPC answers with a JSON-RPC error (for example "transaction underpriced" or a rate-limit error in JSON-RPC form), when the contract reverts, or when the RPC in use reports another chain ID. Another RPC would give the same answer, or must not be used. There is one exception: if the RPC answers the chain ID check (`eth_chainId`) before a write, or in `ChainProvider.health_check()`, with a JSON-RPC error, the CLI counts this as a connection failure and moves to a fallback. Nothing has been sent at that point, and the fallback's chain ID is checked before it is used. In `ChainProvider.health_check()`, the connection probe (`web3_clientVersion`, through web3's `is_connected()`) also cannot tell a JSON-RPC error answer from a connection failure, so such an answer there moves to a fallback too. A JSON-RPC error answer to the block number read (`eth_blockNumber`) does not. A wrong chain ID is reported as "Chain ID mismatch" (`ChainIdMismatchError`), also by `ChainProvider.health_check()`.

The nonce of a write comes from the RPC in use. After a fallback, that RPC may not yet know about transactions from the same wallet that are still waiting at the RPC used before. If you send several writes quickly from one wallet while the primary RPC fails, check the earlier transactions in the explorer.

### "Outcome unknown"

The transaction may have been sent, and the CLI does not know whether it was mined. The transaction may still be mined. This happens when:

- the connection to the RPC fails while or after the transaction is sent;
- the RPC answers the send with "already known", "Known transaction" or "nonce too low". A node gives these answers when it already has the transaction or a transaction with its nonce is mined, for example when a proxy sent the same request twice;
- after the send, the RPC answers the receipt lookup with a JSON-RPC error, such as a rate limit (-32005), or the wait for the receipt fails in another way. This also applies to `chain wait`.

After "nonce too low", the transaction was often not sent: the CLI does not repeat the send, so this answer usually means that another transaction from the same wallet used the nonce first. `chain wait` then waits for the full timeout and reports the transaction as not found (`not_found`, exit 1).

The "Reason" line shows the RPC's answer or the connection error. The CLI prints the transaction hash, the explorer link and the `chain wait` command that resumes the wait (with `--json`, `{"error": "outcome_unknown", "tx_hash": ..., "wait_command": ...}`) and exits 3. Running that `chain wait` command is safe: it sends nothing. Look up the transaction in the explorer, or read the record back with `chain get <data hash>` (the Swarm hash you wrote, not the transaction hash), before you run the command again: running it again can send the write twice and pay gas twice.

If the connection fails before the transaction is sent, the CLI prints "Cannot connect to chain" instead. Nothing was sent in that case.

### "Not confirmed yet"

The transaction was sent, but no receipt arrived within 120 seconds. The transaction may still be mined, so do not run the write again. The CLI prints the transaction hash, the explorer link and the command that waits for the transaction, and exits 3. With `--json`, it prints `{"error": "receipt_timeout", "tx_hash": ..., "event": ..., "expected_count": ..., "timeout": 120, "wait_command": "swarm-prov-upload chain wait 0x... --event ...", ...}`. To wait again, run the printed command, for example:

```bash
swarm-prov-upload chain wait 0x<tx hash> --event DataRegistered
```

`chain wait` sends nothing and needs no wallet key, so running it again after its own timeout is safe. Use `--count N` for a batch write, and `--timeout SECONDS` to wait longer than 120 seconds. It exits 0 when the transaction is confirmed (with `--event`, when the contract emitted the events), 1 when it reverted, was not recorded, was replaced or is not found, and 3 when it is still pending (`receipt_timeout`), when the RPC answered the receipt lookup with an error (`outcome_unknown`), or when no RPC can be reached (with `--json`, `{"error": "connection_failed", ...}`).

### "Replaced"

The receipt wait timed out, and another transaction with the same nonce from the same address was mined instead, so this transaction will never be mined. This can happen when the same wallet key is used elsewhere at the same time. The other transaction may have made the same write. Check the record with `chain get <data hash>` before you run the command again. For `chain delegate`, which has no data record, check the delegate state or the transaction in the explorer. With `--json`, the error is `"replaced"`, and the command exits 1.

"Replaced" can be a false positive behind a load-balanced RPC: the mined nonce and the receipt lookup may be answered by different backend nodes, and a node that is behind may not have the receipt yet. This is why the advice is to check before you run the write again.

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

With `base` or `base-sepolia`, a custom RPC that reports another chain ID is a configuration error. This stops a testnet configuration from signing mainnet transactions. The check runs when the client starts: if the RPC answers then on another chain, the command fails before it reads or signs anything. The chain ID is checked again once before the first transaction is signed. If the RPC could not be reached when the command started, signing is still blocked until the chain ID matches, but reads may be served once the RPC comes up. A fallback RPC that reports another chain ID is skipped.

For a local development node (Hardhat, Anvil), set `CHAIN_NAME=localhost` and `CHAIN_RPC_URL` to the node's URL. The `localhost` preset uses the chain ID that the node reports. The global `--chain` option accepts only `base-sepolia` and `base`, so use the environment variable:

```bash
export CHAIN_NAME=localhost
export CHAIN_RPC_URL=http://127.0.0.1:8545
```

### "No contract address configured"

Base mainnet contract is not yet deployed. Use `base-sepolia` for testing, or provide a custom address:
```bash
export CHAIN_CONTRACT=0x...your_contract_address...
```

## Security best practices

1. **Never commit private keys** to version control
2. **Use a dedicated wallet** for anchoring, not your main wallet
3. **Start with testnet** before using real funds
4. **Keep the key out of your shell history and plaintext files**: read it from a password manager for each command; if you use a `.env` file, `chmod 600` it and never commit it
5. **Monitor gas costs** — anchor transactions are cheap but add up at scale
6. **Use batch operations** (`batch_anchor`, `batch_access` via Python API) for efficiency

## Network details

### Base Sepolia (testnet)

| Property | Value |
|----------|-------|
| Chain ID | 84532 |
| RPC URL | https://sepolia.base.org |
| Fallback RPCs | base-sepolia-rpc.publicnode.com, base-sepolia.drpc.org |
| Block Explorer | https://base-sepolia.blockscout.com |
| DataProvenance Contract | `0x3945aDfd5Df9ab2F5cB4Ca0eb3D4384CC3650322` |
| Contract creation block | 39,898,628 |
| Preset deploy block (event scans start) | 39,905,249 |

The preset's deploy block is the block of the contract's first data event, not the block it was created in. This is safe: the creation block holds only the constructor's `RoleGranted` log, and the contract emits no other events before block 39,905,249, so a scan that starts there reads every data event. A `CHAIN_DEPLOY_BLOCK` you set yourself must still not be later than the first event the contract emits; the contract's creation block is always a safe choice.

### Base (mainnet)

| Property | Value |
|----------|-------|
| Chain ID | 8453 |
| RPC URL | https://mainnet.base.org |
| Fallback RPCs | base-rpc.publicnode.com, base.drpc.org |
| Block Explorer | https://basescan.org |
| DataProvenance Contract | Not yet deployed |

### Localhost (development)

| Property | Value |
|----------|-------|
| Chain ID | 31337 |
| RPC URL | http://127.0.0.1:8545 |
| DataProvenance Contract | `0xCf7Ed3AccA5a467e9e704C703E8D87F634fB0Fc9` |

Set `CHAIN_NAME=localhost` (and `CHAIN_RPC_URL`, if the node is not at `http://127.0.0.1:8545`) for local Hardhat development. The `--chain` option does not accept `localhost`.

## Additional resources

- [Base Documentation](https://docs.base.org)
- [Base Sepolia Block Explorer](https://base-sepolia.blockscout.com)
- [Alchemy Base Sepolia Faucet](https://www.alchemy.com/faucets/base-sepolia)
