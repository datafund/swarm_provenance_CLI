# Stamp Management Workflow Example

This example demonstrates the complete postage stamp lifecycle: listing, inspecting, extending, and best practices for efficient stamp usage.

## What You'll Learn

- Listing all your postage stamps
- Getting detailed stamp information
- Extending stamp TTL (Time-To-Live)
- Monitoring stamp utilization
- Best practices for stamp reuse

## Prerequisites

```bash
swarm-prov-upload --version
swarm-prov-upload health
```

## Quick Start

```bash
chmod +x demo.sh
./demo.sh

# Or Python version
python stamp_lifecycle.py
```

## Stamp Commands

### List All Stamps

```bash
swarm-prov-upload stamps list
```

Output shows:
- Batch ID (shortened)
- Usable status (Yes/No)
- TTL (time remaining)
- Depth
- Utilization %

### Get Stamp Details

```bash
swarm-prov-upload stamps info <stamp_id>
```

Detailed output includes:
- Full batch ID
- Usable/Exists status
- TTL in human-readable format
- Depth, Amount, Utilization
- Block number, Owner (if available)

### Extend Stamp TTL

```bash
swarm-prov-upload stamps extend <stamp_id> --amount <bzz_amount>
```

Adds BZZ tokens to extend the stamp's validity period.

## Stamp Lifecycle

```
┌─────────────────┐
│  Purchase Stamp │ --size medium
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Use Stamp     │ --stamp-id <id>
│   (Uploads)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Monitor Usage   │ stamps info <id>
│ (Utilization)   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌───────────┐
│ Expire │ │  Extend   │
└───────┘ │   TTL     │
          └───────────┘
```

## Understanding Stamp Properties

| Property | Description |
|----------|-------------|
| `batchID` | Unique identifier (64 hex chars) |
| `usable` | Can be used for uploads |
| `batchTTL` | Seconds until expiration |
| `depth` | Capacity parameter (17 = ~128KB) |
| `utilization` | Percentage of capacity used |
| `amount` | BZZ tokens allocated |

## Best Practices

### 1. Size Selection
```bash
# Small batches (testing, few files)
swarm-prov-upload upload --file data.txt --size small

# Regular usage
swarm-prov-upload upload --file data.txt --size medium

# Large archives
swarm-prov-upload upload --file archive.tar.gz --size large
```

### 2. Stamp Reuse
```bash
# Get stamp ID from first upload
OUTPUT=$(swarm-prov-upload upload --file first.txt --size medium)
STAMP_ID=<extract from output>

# Reuse for subsequent uploads
swarm-prov-upload upload --file second.txt --stamp-id $STAMP_ID
swarm-prov-upload upload --file third.txt --stamp-id $STAMP_ID
```

### 3. Monitoring
```bash
# Regular checks
swarm-prov-upload stamps list

# Before large batch
swarm-prov-upload stamps info <stamp_id>
# Check utilization % and TTL
```

### 4. Extension Strategy
```bash
# Extend before expiration
swarm-prov-upload stamps extend <stamp_id> --amount 1000000

# Monitor after extension
swarm-prov-upload stamps info <stamp_id>
```

## Files in This Example

| File | Description |
|------|-------------|
| `README.md` | This documentation |
| `demo.sh` | Shell script demonstration |
| `stamp_lifecycle.py` | Python stamp management |

## Next Steps

- [04-batch-processing](../04-batch-processing/) - Efficient stamp reuse
- [02-audit-trail](../02-audit-trail/) - Long-term stamp planning
