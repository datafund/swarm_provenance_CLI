# Example 07: Stamp Management

Demonstrates the full postage stamp lifecycle using the stamps subcommands.

## What This Demonstrates

- Checking stamp pool availability (`stamps pool-status`)
- Uploading a file with verbose output to capture a stamp ID
- Listing all stamps (`stamps list`)
- Inspecting stamp details (`stamps info <id>`)
- Health-checking a stamp (`stamps check <id>`)
- Extending a stamp (`stamps extend <id>` — requires funded wallet)

## Use Case

Postage stamps are the payment mechanism for Swarm storage. Understanding how to manage stamps is essential for production deployments:

- **Pool stamps** are pre-purchased and shared, offering fast (~5s) uploads
- **Individual stamps** give you full control over capacity and duration
- **Monitoring** stamp utilization prevents unexpected expiration
- **Extending** stamps keeps your data available longer

## Prerequisites

1. Install the CLI: `pip install -e .`
2. Gateway access (default, no setup needed)
3. For `stamps extend`: a funded wallet with BZZ tokens (optional)

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

### 1. Check pool availability

```bash
swarm-prov-upload stamps pool-status
```

Shows whether the stamp pool is enabled and how many stamps are available.

### 2. Upload to acquire a stamp

```bash
swarm-prov-upload upload --file sample_data.txt -v --usePool
```

The `-v` flag shows the stamp ID in the output.

### 3. List all stamps

```bash
swarm-prov-upload stamps list
```

### 4. Inspect stamp details

```bash
swarm-prov-upload stamps info <stamp_id>
```

Shows depth, amount, utilization, and TTL.

### 5. Health-check a stamp

```bash
swarm-prov-upload stamps check <stamp_id>
```

### 6. Extend a stamp (optional)

```bash
swarm-prov-upload stamps extend <stamp_id> --amount 1000000
```

Requires a funded wallet. This tops up the stamp to extend its lifetime.

## Stamp Lifecycle Helper

The `stamp_lifecycle.py` script runs the full lifecycle:

```bash
python stamp_lifecycle.py --file sample_data.txt
```

## Files

| File | Description |
|------|-------------|
| `demo.sh` | Shell demo — full stamp lifecycle |
| `run_demo.py` | Python demo — same workflow with argparse support |
| `stamp_lifecycle.py` | Standalone stamp lifecycle management tool |
| `sample_data.txt` | Sample file for triggering stamp creation |
