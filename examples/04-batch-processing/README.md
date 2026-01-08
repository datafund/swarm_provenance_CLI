# Batch Processing / Cost Optimization Example

This example demonstrates how to efficiently upload multiple files while minimizing costs through postage stamp reuse.

## Use Cases

- **Log Rotation**: Daily/weekly log file archival
- **IoT Data**: Sensor readings collected over time
- **Document Processing**: Batch document archival
- **Backup Systems**: Incremental backup uploads

## What You'll Learn

- Purchasing stamps with size presets for capacity planning
- Reusing a single stamp across multiple uploads
- Creating upload manifests for tracking
- Cost comparison: individual vs batch uploads

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
python batch_upload.py
```

## Cost Optimization Strategy

### Individual Uploads (Expensive)
Each upload purchases a new stamp:
```bash
swarm-prov-upload upload --file file1.txt  # New stamp
swarm-prov-upload upload --file file2.txt  # New stamp
swarm-prov-upload upload --file file3.txt  # New stamp
# Total: 3 stamps purchased
```

### Batch Upload (Optimized)
Purchase one stamp, reuse for all files:
```bash
# First upload - purchase stamp with capacity
OUTPUT=$(swarm-prov-upload upload --file file1.txt --size medium)
STAMP_ID=$(extract_stamp_id "$OUTPUT")

# Subsequent uploads - reuse stamp
swarm-prov-upload upload --file file2.txt --stamp-id $STAMP_ID
swarm-prov-upload upload --file file3.txt --stamp-id $STAMP_ID
# Total: 1 stamp purchased
```

## Size Presets

| Preset | Capacity | Best For |
|--------|----------|----------|
| `small` | ~10 files | Quick tests, small batches |
| `medium` | ~100 files | Daily logs, moderate batches |
| `large` | ~1000 files | Large archives, bulk processing |

## Batch Upload Script

The `batch_upload.py` script provides:
- Automatic stamp purchasing with appropriate size
- Progress tracking for each file
- Manifest generation with all references
- Error handling and retry logic

Usage:
```bash
python batch_upload.py ./sample_files --size medium --std "BATCH-V1"
```

## Sample Files

The `sample_files/` directory contains example files:
- `log_001.txt` through `log_005.txt`

## Manifest Output

After batch upload, a manifest is created:

```json
{
  "version": "1.0",
  "created_at": "2025-01-08T12:00:00Z",
  "stamp_id": "abc123...",
  "total_files": 5,
  "uploads": [
    {"filename": "log_001.txt", "swarm_ref": "def456...", "size": 1024},
    {"filename": "log_002.txt", "swarm_ref": "ghi789...", "size": 2048}
  ]
}
```

## Monitoring Stamp Usage

Check stamp utilization after batch uploads:
```bash
swarm-prov-upload stamps info <stamp_id>
```

If utilization is high, extend or purchase a new stamp.

## Files in This Example

| File | Description |
|------|-------------|
| `README.md` | This documentation |
| `demo.sh` | Shell script demonstration |
| `batch_upload.py` | Python batch uploader |
| `sample_files/` | Directory with sample files |

## Next Steps

- [07-stamp-management](../07-stamp-management/) - Monitor and extend stamps
- [02-audit-trail](../02-audit-trail/) - Add provenance standards to batches
