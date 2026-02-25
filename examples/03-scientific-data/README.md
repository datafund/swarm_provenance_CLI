# Example 03: Scientific Data

Demonstrates research data archival on Swarm with extended retention.

## What This Demonstrates

- Uploading experiment metadata with `--std "PROV-O"` provenance standard
- Using `--duration 720` for 30-day data retention
- Archiving both metadata and raw data files
- Downloading and verifying research data integrity

## Use Case

Research institutions need to archive experiment data with clear provenance tracking. The PROV-O standard (W3C provenance ontology) tags data with its scientific context, while extended duration ensures the data remains accessible for the retention period required by the research protocol.

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

### 1. Upload experiment metadata

The metadata JSON describes the experiment (PI, methodology, sensors) and is uploaded with PROV-O standard and 30-day retention:

```bash
swarm-prov-upload upload \
    --file dataset_metadata.json \
    --std "PROV-O" \
    --duration 720 \
    --usePool
```

The `--duration 720` flag requests a postage stamp valid for 720 hours (30 days). If this duration is not available (e.g., due to gateway limitations or cost), the demo falls back to the default duration.

### 2. Upload experiment results

The CSV file with sensor readings is uploaded separately:

```bash
swarm-prov-upload upload \
    --file experiment_results.csv \
    --std "PROV-O" \
    --usePool
```

### 3. Download and verify

```bash
swarm-prov-upload download <csv_reference> --output-dir ./downloads
shasum -a 256 experiment_results.csv downloads/*.data
```

## Sample Data

### dataset_metadata.json

Experiment metadata following the PROV-O model:
- Experiment ID, principal investigator, institution
- Methodology: sensor type, sampling interval, calibration
- Data file references and column descriptions

### experiment_results.csv

8 sensor readings with columns:
- `timestamp` — ISO 8601 UTC
- `station_id` — Monitoring station identifier
- `temperature_c` — Temperature in Celsius
- `humidity_pct` — Relative humidity percentage
- `status` — Reading status (normal/warning)

## Files

| File | Description |
|------|-------------|
| `demo.sh` | Shell demo — uploads metadata and CSV, downloads and verifies |
| `run_demo.py` | Python demo — same workflow with argparse support |
| `dataset_metadata.json` | Experiment metadata (PROV-O format) |
| `experiment_results.csv` | Sensor readings (8 rows) |
