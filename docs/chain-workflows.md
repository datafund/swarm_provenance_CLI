# Chain Workflow Diagrams

Visual reference for on-chain provenance operations. For setup instructions, see [chain-setup.md](chain-setup.md).

## Component Architecture

How the chain subsystem is structured internally:

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLI Layer (cli.py)                         │
│                                                                     │
│  chain balance | anchor | verify | get | access | transform         │
│  chain status | transfer | delegate | protect                       │
│  Global flags: --chain, --chain-rpc                                 │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    ChainClient  (core/chain_client.py)              │
│                                                                     │
│  High-level facade — one method per operation                       │
│  Handles: gas estimation, signing, broadcasting, receipt parsing    │
│                                                                     │
│  Write ops:  anchor(), transform(), access(), set_status(),         │
│              transfer_ownership(), set_delegate()                   │
│              batch_anchor(), batch_access(), batch_set_status()     │
│  Read ops:   get(), verify(), balance(), health_check(),            │
│              get_provenance_chain()                                  │
└────────┬──────────────────┬──────────────────┬──────────────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
┌─────────────────┐ ┌──────────────┐ ┌────────────────────────────┐
│  ChainProvider  │ │  ChainWallet │ │  DataProvenanceContract    │
│  (provider.py)  │ │  (wallet.py) │ │  (contract.py)             │
│                 │ │              │ │                            │
│  Web3 conn mgmt │ │  Private key │ │  ABI wrapper               │
│  Chain presets  │ │  TX signing  │ │  build_*_tx() methods      │
│  Explorer URLs  │ │  Balance     │ │  get_data_record()         │
│  Health checks  │ │              │ │  Hash normalization        │
│  Chain ID auto- │ │              │ │                            │
│  detection      │ │              │ │  ABI: abi/DataProvenance   │
└────────┬────────┘ └──────┬───────┘ └────────────┬───────────────┘
         │                 │                       │
         └─────────────────┴───────────────────────┘
                           │
                           ▼
                   ┌───────────────┐
                   │   Base Chain  │
                   │  (via RPC)    │
                   └───────────────┘
```

## End-to-End: Upload + Anchor + Verify

The complete flow from raw data to on-chain provenance:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    Upload + Anchor + Verify Workflow                         │
└──────────────────────────────────────────────────────────────────────────────┘

  User                     CLI                     Swarm               Base Chain
   │                        │                        │                      │
   │  1. Upload data        │                        │                      │
   │  swarm-prov-upload     │                        │                      │
   │  upload --file data.txt│                        │                      │
   │───────────────────────>│                        │                      │
   │                        │  2. Buy stamp + upload │                      │
   │                        │───────────────────────>│                      │
   │                        │                        │                      │
   │                        │  3. Swarm hash         │                      │
   │                        │<───────────────────────│                      │
   │  Swarm Reference:      │                        │                      │
   │  abc123...             │                        │                      │
   │<───────────────────────│                        │                      │
   │                        │                        │                      │
   │  4. Anchor on-chain    │                        │                      │
   │  swarm-prov-upload     │                        │                      │
   │  chain anchor abc123...│                        │                      │
   │───────────────────────>│                        │                      │
   │                        │  5. Sign + send TX     │                      │
   │                        │─────────────────────────────────────────────> │
   │                        │                        │                      │
   │                        │  6. TX receipt         │                      │
   │                        │<─────────────────────────────────────────────│
   │  Anchored! TX: 0xbb... │                        │                      │
   │<───────────────────────│                        │                      │
   │                        │                        │                      │
   │  7. Verify later       │                        │                      │
   │  swarm-prov-upload     │                        │                      │
   │  chain verify abc123...│                        │                      │
   │───────────────────────>│                        │                      │
   │                        │  8. Query contract     │                      │
   │                        │  (free, no gas)        │                      │
   │                        │─────────────────────────────────────────────>│
   │                        │                        │                      │
   │                        │  9. Owner, timestamp   │                      │
   │                        │<─────────────────────────────────────────────│
   │  Verified: anchored    │                        │                      │
   │<───────────────────────│                        │                      │
```

**CLI commands:**
```bash
# 1. Upload to Swarm
swarm-prov-upload upload --file data.txt
# Output: Swarm Reference Hash: abc123...

# 2. Anchor the hash on-chain
swarm-prov-upload chain anchor abc123...

# 3. Verify anytime later
swarm-prov-upload chain verify abc123...

# 4. Get full provenance record
swarm-prov-upload chain get abc123... --json
```

## Transformation Lineage

Track how data evolves through transformations. Each transformation links an original hash to a derived hash with a description.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        Transformation Lineage Flow                          │
└──────────────────────────────────────────────────────────────────────────────┘

  On-chain records:

  ┌─────────────────────┐     transform()      ┌─────────────────────┐
  │  Original Dataset   │─────────────────────>│  Anonymized Dataset │
  │  hash: aaa...       │  "Removed PII"       │  hash: bbb...       │
  │  type: dataset      │                      │  type: dataset      │
  │  owner: 0x742d...   │                      │  owner: 0x742d...   │
  │  status: ACTIVE     │                      │  status: ACTIVE     │
  │                     │                      │                     │
  │  transformations:   │                      │  transformations:   │
  │   -> bbb... Removed │                      │   -> ccc... Aggre-  │
  │      PII            │                      │      gated by region│
  └─────────────────────┘                      └──────────┬──────────┘
                                                          │
                                                          │  transform()
                                                          │  "Aggregated by region"
                                                          ▼
                                               ┌─────────────────────┐
                                               │  Aggregated Report  │
                                               │  hash: ccc...       │
                                               │  type: report       │
                                               │  owner: 0x742d...   │
                                               │  status: ACTIVE     │
                                               │                     │
                                               │  transformations:   │
                                               │   (none)            │
                                               └─────────────────────┘

  Walking the chain with get_provenance_chain("aaa..."):
  Returns: [record_aaa, record_bbb, record_ccc]
```

**CLI commands:**
```bash
# 1. Anchor original dataset
swarm-prov-upload chain anchor aaa... --type dataset

# 2. Process data, upload result, then record the transformation
swarm-prov-upload chain transform aaa... bbb... --description "Removed PII"

# 3. Further transform and record
swarm-prov-upload chain anchor bbb... --type dataset
swarm-prov-upload chain transform bbb... ccc... --description "Aggregated by region"

# 4. View the full lineage
swarm-prov-upload chain get aaa...
# Shows: transformations -> bbb... "Removed PII"

# 5. Walk the full transformation chain
swarm-prov-upload chain get aaa... --follow
# Shows all records: aaa -> bbb -> ccc

# 6. Limit walk depth
swarm-prov-upload chain get aaa... --follow --depth 1
# Shows only: aaa -> bbb (stops at depth 1)
```

**Python API for chain walking:**
```python
from swarm_provenance_uploader.core.chain_client import ChainClient

client = ChainClient()
chain = client.get_provenance_chain("aaa...")
# Returns [record_aaa, record_bbb, record_ccc]

for record in chain:
    print(f"{record.data_hash[:12]}... ({record.data_type})")
    for t in record.transformations:
        print(f"  -> {t.new_data_hash[:12]}... {t.description}")
```

## Access Logging

Record and audit who accessed what data. Each access call is a transaction, creating an immutable audit trail.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Access Logging Flow                                │
└──────────────────────────────────────────────────────────────────────────────┘

  Data Consumer A                CLI                         Base Chain
       │                          │                              │
       │  Download data           │                              │
       │  from Swarm              │                              │
       │                          │                              │
       │  Record access           │                              │
       │  chain access abc123...  │                              │
       │─────────────────────────>│                              │
       │                          │  recordAccess(abc123, 0xA)   │
       │                          │  (sign + send tx)            │
       │                          │─────────────────────────────>│
       │                          │                              │  Stored:
       │                          │  TX receipt                  │  accessors += [0xA]
       │                          │<─────────────────────────────│
       │  Access recorded!        │                              │
       │<─────────────────────────│                              │

  Data Consumer B                 │                              │
       │                          │                              │
       │  chain access abc123...  │                              │
       │─────────────────────────>│                              │
       │                          │  recordAccess(abc123, 0xB)   │
       │                          │─────────────────────────────>│
       │                          │                              │  Stored:
       │                          │  TX receipt                  │  accessors += [0xB]
       │                          │<─────────────────────────────│
       │  Access recorded!        │                              │
       │<─────────────────────────│                              │

  Data Owner                      │                              │
       │                          │                              │
       │  Audit: who accessed?    │                              │
       │  chain get abc123...     │                              │
       │─────────────────────────>│                              │
       │                          │  getDataRecord(abc123)       │
       │                          │  (free read, no gas)         │
       │                          │─────────────────────────────>│
       │                          │                              │
       │                          │  { accessors: [0xA, 0xB] }  │
       │                          │<─────────────────────────────│
       │  Accessors (2):          │                              │
       │   - 0xA (Consumer A)     │                              │
       │   - 0xB (Consumer B)     │                              │
       │<─────────────────────────│                              │
```

**Key properties:**
- Access logging is **idempotent** — recording the same accessor twice is safe
- Write operations (recording access) require gas
- Read operations (auditing who accessed) are free
- The accessor address is the wallet that signed the transaction

**CLI commands:**
```bash
# Record that you accessed data
swarm-prov-upload chain access abc123...

# Audit: see who accessed the data
swarm-prov-upload chain get abc123...
# Output includes:
#   Accessors (2):
#     - 0x742d...fE00
#     - 0x8bC3...a1B2
```

## Data Lifecycle (Status Management)

Data goes through lifecycle states. Status changes are recorded on-chain.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Data Lifecycle States                               │
└──────────────────────────────────────────────────────────────────────────────┘

                    anchor()
                 ┌────────────┐
                 ▼            │
          ┌─────────────┐     │
          │   ACTIVE     │ ◄──┘
          │   (status=0) │
          │              │
          │  Data is live│
          │  and access- │
          │  ible        │
          └──────┬───────┘
                 │
        set_status(1)     set_status(2)
        ┌────────┘             └─────────┐
        ▼                                ▼
 ┌─────────────┐                  ┌─────────────┐
 │  RESTRICTED  │                  │   DELETED    │
 │  (status=1) │                  │  (status=2) │
 │              │                  │              │
 │  Access is   │                  │  Logically   │
 │  restricted  │                  │  deleted     │
 └──────┬───────┘                  └──────┬───────┘
        │                                 │
        │  set_status(0)                  │  set_status(0)
        └─────────┐              ┌────────┘
                  ▼              ▼
           ┌─────────────┐
           │   ACTIVE     │
           │   (status=0) │
           └─────────────┘

  All transitions are bidirectional.
  Only the data owner (or authorized delegate) can change status.
  Status changes are recorded on-chain and auditable.
```

**CLI commands:**
```bash
# Query current status
swarm-prov-upload chain status abc123...

# Set status
swarm-prov-upload chain status abc123... --set restricted
swarm-prov-upload chain status abc123... --set deleted
swarm-prov-upload chain status abc123... --set active
```

**Python API:**
```python
from swarm_provenance_uploader.core.chain_client import ChainClient

client = ChainClient()

# Restrict access
client.set_status("abc123...", status=1)  # RESTRICTED

# Logically delete
client.set_status("abc123...", status=2)  # DELETED

# Reactivate
client.set_status("abc123...", status=0)  # ACTIVE
```

## Ownership and Delegation

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     Ownership & Delegation Model                            │
└──────────────────────────────────────────────────────────────────────────────┘

  Owner (0xAlice)                                    Delegate (0xBob)
       │                                                   │
       │  1. Authorize Bob as delegate                     │
       │  set_delegate(0xBob, authorized=True)             │
       │─────────────────────────────────────────────────> │
       │                                                   │
       │                                                   │  2. Bob can now anchor
       │                                                   │  on behalf of Alice
       │                                                   │  anchor_for(hash, 0xAlice)
       │                              ┌────────────────────│
       │                              │                    │
       │                              ▼                    │
       │                    ┌─────────────────┐            │
       │                    │  On-chain record │            │
       │                    │  owner: 0xAlice  │            │
       │                    │  (not 0xBob)     │            │
       │                    └─────────────────┘            │
       │                                                   │
       │  3. Transfer ownership to Carol                   │
       │  transfer_ownership(hash, 0xCarol)                │
       │───────────────────────┐                           │
       │                       ▼                           │
       │             ┌─────────────────┐                   │
       │             │  On-chain record │                   │
       │             │  owner: 0xCarol  │                   │
       │             └─────────────────┘                   │
       │                                                   │
       │  4. Revoke Bob's delegation                       │
       │  set_delegate(0xBob, authorized=False)            │
       │─────────────────────────────────────────────────> │
       │                                                   │  Bob can no longer
       │                                                   │  act on Alice's behalf
```

**CLI commands:**
```bash
# Authorize Bob as delegate
swarm-prov-upload chain delegate 0xBob... --authorize

# Bob anchors on behalf of Alice
swarm-prov-upload chain anchor abc123... --owner 0xAlice...

# Transfer ownership to Carol
swarm-prov-upload chain transfer abc123... --to 0xCarol...

# Revoke Bob's delegation
swarm-prov-upload chain delegate 0xBob... --revoke
```

**Python API:**
```python
from swarm_provenance_uploader.core.chain_client import ChainClient

# Alice's client
alice_client = ChainClient()

# Authorize Bob as delegate
alice_client.set_delegate("0xBob...", authorized=True)

# Bob anchors on behalf of Alice
bob_client = ChainClient(private_key="0xBob_key...")
bob_client.anchor_for("abc123...", owner="0xAlice...")
# Record shows owner = 0xAlice, not 0xBob

# Transfer ownership to Carol
alice_client.transfer_ownership("abc123...", new_owner="0xCarol...")

# Revoke Bob's delegation
alice_client.set_delegate("0xBob...", authorized=False)
```

## Transaction Cost Summary

| Operation | Type | Gas Cost | Notes |
|-----------|------|----------|-------|
| `anchor` | Write | ~95,000 | One-time registration |
| `transform` | Write | ~80,000 | Links original to derived |
| `access` | Write | ~65,000 | Idempotent per accessor |
| `set_status` | Write | ~45,000 | Status change |
| `transfer_ownership` | Write | ~50,000 | Owner change |
| `set_delegate` | Write | ~45,000 | Authorize/revoke |
| `batch_anchor` | Write | ~95k + ~60k/item | Up to 50 per batch |
| `batch_access` | Write | ~65k + ~45k/item | Up to 100 per batch |
| `verify` | Read | Free | No gas |
| `get` | Read | Free | No gas |
| `balance` | Read | Free | No gas |
| `get_provenance_chain` | Read | Free | Follows transformation links |

Gas costs are estimates on Base chain. At typical gas prices (~0.001 gwei), each write operation costs fractions of a cent.

## Data Protection Pattern

The `chain protect` command combines multiple steps into a single atomic-intent workflow: replace sensitive data with a clean version and restrict the original.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        Data Protection Workflow                             │
└──────────────────────────────────────────────────────────────────────────────┘

  Manual steps (4 commands):            chain protect (1 command):

  1. chain anchor <new>                 chain protect <orig> <new> \
  2. chain transform <orig> <new> \       --anchor-new \
       --description "..."                --description "Removed PII"
  3. chain status <orig> --set restricted
  4. chain verify <orig>                Does all 4 steps automatically:
                                        1. Verify original is ACTIVE
                                        2. Anchor new hash (--anchor-new)
                                        3. Record transformation
                                        4. Restrict original
```

**CLI commands:**
```bash
# Full protect workflow (new hash already anchored)
swarm-prov-upload chain protect aaa... bbb... --description "Removed PII"

# Protect with auto-anchor of new hash
swarm-prov-upload chain protect aaa... bbb... --anchor-new --description "Redacted"

# Protect with custom data type for the new hash
swarm-prov-upload chain protect aaa... bbb... --anchor-new --type dataset -d "Anonymized"

# JSON output includes all sub-operation results
swarm-prov-upload chain protect aaa... bbb... --json
```

**Equivalent manual steps:**
```bash
# 1. Upload the clean version
swarm-prov-upload upload --file clean-data.txt
# Output: bbb...

# 2. Anchor it
swarm-prov-upload chain anchor bbb... --type dataset

# 3. Record the transformation link
swarm-prov-upload chain transform aaa... bbb... --description "Removed PII"

# 4. Restrict the original
swarm-prov-upload chain status aaa... --set restricted

# Alternatively, steps 3+4 in one command:
swarm-prov-upload chain transform aaa... bbb... --restrict-original -d "Removed PII"
```

## Depth-Limited Chain Traversal

The `--follow` flag on `chain get` walks the full transformation chain using breadth-first search. Use `--depth` to limit how deep it goes.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        Depth-Limited Traversal                              │
└──────────────────────────────────────────────────────────────────────────────┘

  Chain: A ──> B ──> C ──> D

  --follow              Returns: [A, B, C, D]     (all records)
  --follow --depth 2    Returns: [A, B, C]         (stops at depth 2)
  --follow --depth 1    Returns: [A, B]            (stops at depth 1)
  --follow --depth 0    Returns: [A]               (root only)
  (no --follow)         Returns: A                 (single record, no chain)
```

**Default behavior:**
- Without `--depth`: traverses up to 50 levels (safety cap)
- `--depth` without `--follow`: warns and is ignored
- Cycles are detected and skipped (visited set prevents infinite loops)

**CLI commands:**
```bash
# Walk full chain
swarm-prov-upload chain get aaa... --follow

# Limit to 2 levels
swarm-prov-upload chain get aaa... --follow --depth 2

# JSON output includes chain array, depth count, and root hash
swarm-prov-upload chain get aaa... --follow --json
# Output: {"chain": [...], "depth": 4, "root": "aaa..."}
```

## Error Recovery

### Partial Failures in Protect

The `chain protect` command runs multiple operations sequentially. If a later step fails, earlier steps have already been committed on-chain.

| Step Failed | What Happened | Recovery |
|------------|---------------|----------|
| Step 1 (verify) | Nothing committed | Fix preconditions and retry |
| Step 2 (anchor new) | Nothing committed | Fix anchor issue and retry |
| Step 3 (transform) | New hash may be anchored | Record transform manually |
| Step 4 (restrict) | Transform recorded, original still ACTIVE | Restrict manually |

**If restrict fails after transform:**
```bash
# The CLI shows a WARNING with the manual command:
# WARNING: Transform succeeded but failed to restrict original: ...
#   Restrict manually: swarm-prov-upload chain status <hash> --set restricted

# Run the suggested command:
swarm-prov-upload chain status aaa... --set restricted
```

**JSON output for partial failures:**
```json
{
  "transform": { "tx_hash": "0x...", ... },
  "restrict": null,
  "partial_failure": true
}
```

### Common Error Scenarios

| Error | Cause | Fix |
|-------|-------|-----|
| `not registered on-chain` | Hash not anchored | `chain anchor <hash>` first |
| `expected ACTIVE` | Original is RESTRICTED/DELETED | Set to ACTIVE first or use different hash |
| `Transaction failed: reverted` | Not the owner or not authorized | Check owner with `chain get <hash>` |
| `Cannot connect to chain` | RPC node unreachable | Check `CHAIN_RPC_URL` or network config |

### Exit Codes

| Exit Code | Meaning |
|-----------|---------|
| 0 | Success (also for protect with partial restrict failure) |
| 1 | Error: hash not found, transaction failed, connection error |
