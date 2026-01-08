# Market Memory / Trading Records Example

This example demonstrates SemantiCord-inspired market record keeping, creating verifiable "memory units" that link predictions to outcomes and build trusted market narratives.

## Concepts

**Memory Units** are self-contained JSON records with:
- Unique identifier
- Domain classification
- Timestamp
- Payload (domain-specific data)
- Canonical hash for verification

## Use Cases

- **Forecast Tracking**: Link predictions to actual outcomes
- **Trading Records**: Immutable trade execution records
- **Price Observations**: Timestamped market data snapshots
- **Settlement Records**: Auction clearing prices, RFQ outcomes

## What You'll Learn

- Creating memory unit structures
- Canonical JSON hashing for verification
- Building verifiable market narratives
- Linking related records

## Quick Start

```bash
chmod +x demo.sh
./demo.sh

# Or Python scripts
python create_memory_unit.py
python verify_memory_unit.py <swarm_ref>
```

## Memory Unit Structure

```json
{
  "id": "mu-20250108120000",
  "version": "1.0",
  "domain": "market-forecast",
  "timestamp": "2025-01-08T12:00:00Z",
  "payload": {
    "event": "price_prediction",
    "asset": "ETH/USD",
    "prediction": 2500.00,
    "confidence": 0.85,
    "timeframe": "24h"
  },
  "metadata": {
    "created_by": "forecast-system",
    "schema": "market-forecast-v1"
  },
  "content_hash": "sha256..."
}
```

## Canonical Hashing

For deterministic verification:
1. Serialize JSON with sorted keys
2. Use minimal separators (no whitespace)
3. Exclude the hash field itself from computation

```python
import json
import hashlib

# Create unit without hash
unit = {"id": "...", "payload": {...}}

# Canonical serialization
canonical = json.dumps(unit, sort_keys=True, separators=(",", ":"))

# Compute hash
content_hash = hashlib.sha256(canonical.encode()).hexdigest()
```

## Verification Workflow

1. Download memory unit from Swarm
2. Extract `content_hash` from the record
3. Recompute hash from remaining fields
4. Compare hashes to verify integrity

## Domain Examples

### Price Observation
```json
{
  "domain": "price-observation",
  "payload": {
    "asset": "BTC/USD",
    "price": 45000.00,
    "volume_24h": 28500000000,
    "source": "aggregated"
  }
}
```

### Forecast Result
```json
{
  "domain": "forecast-result",
  "payload": {
    "forecast_id": "fc-001",
    "predicted": 2500.00,
    "actual": 2487.50,
    "accuracy": 0.995,
    "timeframe": "24h"
  }
}
```

### Settlement Record
```json
{
  "domain": "settlement",
  "payload": {
    "auction_id": "auc-001",
    "clearing_price": 1.42,
    "unit": "EUR/kg",
    "participants": 15,
    "total_volume": 5000
  }
}
```

## Files in This Example

| File | Description |
|------|-------------|
| `README.md` | This documentation |
| `demo.sh` | Shell script demonstration |
| `memory_unit.json` | Sample memory unit |
| `create_memory_unit.py` | Memory unit generator |
| `verify_memory_unit.py` | Verification tool |

## Next Steps

- [09-verification](../09-verification/) - Advanced verification workflows
- [02-audit-trail](../02-audit-trail/) - Combine with audit standards
