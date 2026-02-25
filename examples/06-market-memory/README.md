# Example 06: Market Memory

Demonstrates market prediction memory units with canonical content hashing on Swarm.

## What This Demonstrates

- Canonical JSON hashing for deterministic content fingerprints
- Uploading predictions with `--std "MARKET-MEMORY-V1"`
- Linking observations back to predictions via Swarm references
- Verifying content integrity through canonical hash recomputation

## Use Case

Trading agents produce predictions and later record observations (outcomes). Each memory unit contains a canonical content hash computed from its fields, ensuring any tampering is detectable. Observations link to their predictions via Swarm references, creating an auditable prediction→outcome chain.

**Canonical hashing** ensures the same data always produces the same hash regardless of JSON key ordering:

```python
json.dumps(data, sort_keys=True, separators=(',', ':'))  →  SHA-256
```

The `content_hash` field is excluded from the hash computation to avoid circular dependency.

## Prerequisites

1. Install the CLI: `pip install -e .`
2. Gateway access (default, no setup needed)

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

### 1. Verify canonical hash

Before uploading, verify the prediction's content hash:

```bash
python create_memory_unit.py verify prediction_001.json
```

### 2. Upload prediction

```bash
swarm-prov-upload upload --file prediction_001.json --std "MARKET-MEMORY-V1" --usePool
```

### 3. Upload observation with prediction reference

The observation's `prediction_ref` field is updated with the actual Swarm hash of the uploaded prediction, then its canonical hash is recomputed:

```bash
# The demo scripts handle this automatically
swarm-prov-upload upload --file observation.json --std "MARKET-MEMORY-V1" --usePool
```

### 4. Download and verify

```bash
swarm-prov-upload download <prediction_ref> --output-dir ./downloads
python create_memory_unit.py verify downloads/*.data
```

## Memory Unit Helper

`create_memory_unit.py` generates and verifies memory units:

```bash
# Create a prediction
python create_memory_unit.py prediction --agent agent-alpha --market BTC/USD --direction up

# Create an observation linking to a prediction
python create_memory_unit.py observation --agent agent-alpha --market BTC/USD \
    --prediction-ref <swarm_hash>

# Verify a unit's canonical hash
python create_memory_unit.py verify prediction_001.json
```

## Sample Data

### prediction_001.json

A BTC/USD prediction with:
- Direction: up, 75% confidence, 24h horizon
- Model version, data sources, feature count
- Pre-computed canonical content hash

### observation_001.json

An observation recording the outcome:
- Links to prediction via `prediction_ref`
- Outcome: correct, actual direction: up, 2.3% return
- Pre-computed canonical content hash (with placeholder prediction ref)

## Canonical Hashing

The content hash is computed as:

1. Take all fields except `content_hash`
2. Serialize with `json.dumps(data, sort_keys=True, separators=(',', ':'))`
3. Compute SHA-256 of the UTF-8 encoded string

This makes the hash deterministic regardless of:
- JSON key ordering
- Whitespace formatting
- Platform differences

## Files

| File | Description |
|------|-------------|
| `demo.sh` | Shell demo — verify, upload prediction + observation, download and verify |
| `run_demo.py` | Python demo — same workflow with argparse support |
| `create_memory_unit.py` | Helper: create and verify memory units with canonical hashing |
| `prediction_001.json` | Sample prediction memory unit (BTC/USD, up, 75% confidence) |
| `observation_001.json` | Sample observation (correct outcome, links to prediction) |
