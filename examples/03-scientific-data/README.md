# Scientific Data Preservation Example

This example demonstrates how to use the Swarm Provenance CLI for preserving research data with long-term retention and W3C PROV-O standard compliance.

## Use Cases

- **Academic Research**: Dataset publication, experiment reproducibility
- **Clinical Trials**: Patient data, trial results, protocol versions
- **Environmental Monitoring**: Sensor data, climate records
- **Government/Public Data**: Census data, public records

## What You'll Learn

- Using `--duration` for extended retention periods
- Applying the W3C PROV-O provenance standard
- Preserving metadata alongside raw data
- Creating verifiable research artifacts

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
python run_demo.py
```

## Key Features

### Long-Term Retention

Use `--duration` to specify retention in hours:

```bash
# 30 days retention
swarm-prov-upload upload --file dataset.csv --duration 720

# 1 year retention
swarm-prov-upload upload --file dataset.csv --duration 8760
```

### PROV-O Standard

The W3C PROV-O standard provides a vocabulary for provenance:

```bash
swarm-prov-upload upload \
  --file experiment_results.csv \
  --std "PROV-O"
```

### Metadata Structure

Research datasets benefit from rich metadata:

```json
{
  "identifier": {"type": "DOI", "value": "10.5281/example.123"},
  "title": "Climate Sensor Readings Q1 2025",
  "creators": [{"name": "Dr. Jane Smith"}],
  "description": "Hourly temperature and humidity readings",
  "subjects": [{"term": "climate"}, {"term": "sensors"}],
  "provenance": {
    "standard": "PROV-O",
    "generated_at": "2025-01-08T12:00:00Z"
  }
}
```

## Sample Files

- `dataset_metadata.json` - DataCite-inspired metadata
- `experiment_results.csv` - Sample sensor data

## Workflow

1. **Prepare metadata** describing your dataset
2. **Upload metadata** with PROV-O standard tagging
3. **Upload raw data** referencing the metadata
4. **Create manifest** linking all artifacts
5. **Store references** for future citation/retrieval

## Best Practices

1. **Use DOIs**: Include persistent identifiers in metadata
2. **Document provenance**: Record how data was collected/processed
3. **Include licenses**: Specify data usage rights (CC-BY-4.0, etc.)
4. **Version control**: Track dataset versions with timestamps
5. **Long retention**: Match duration to grant/project timeline

## Files in This Example

| File | Description |
|------|-------------|
| `README.md` | This documentation |
| `demo.sh` | Shell script demonstration |
| `dataset_metadata.json` | Sample research metadata |
| `experiment_results.csv` | Sample CSV dataset |
| `run_demo.py` | Python version |

## Next Steps

- [04-batch-processing](../04-batch-processing/) - Upload large datasets in chunks
- [05-encrypted-data](../05-encrypted-data/) - Protect sensitive research data
