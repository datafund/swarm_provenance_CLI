# Example 08: CI/CD Integration

Demonstrates archiving build artifacts to Swarm from CI/CD pipelines.

## What This Demonstrates

- Uploading build artifacts with `--std "CI-ARTIFACT-V1"`
- Saving archive receipts (JSON manifests with references, hashes, timestamps)
- Downloading and verifying archived artifacts
- Sample GitHub Actions and GitLab CI configurations

## Use Case

CI/CD pipelines produce build artifacts that need immutable archival for:

- **Compliance**: Prove exactly what was built and deployed
- **Reproducibility**: Retrieve any historical build artifact by its Swarm reference
- **Audit trails**: Track which artifacts were deployed to production
- **Supply chain security**: Verify artifact integrity before deployment

By archiving artifacts to Swarm with a provenance standard, each build gets a permanent, content-addressed record.

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

### 1. Upload build artifacts

```bash
swarm-prov-upload upload --file sample_artifacts/build_info.json --std "CI-ARTIFACT-V1" --usePool
swarm-prov-upload upload --file sample_artifacts/release_notes.txt --std "CI-ARTIFACT-V1" --usePool
```

### 2. Save archive receipt

The demo saves a JSON receipt with references, content hashes, and timestamps for each artifact.

### 3. Download and verify

```bash
swarm-prov-upload download <swarm_hash> --output-dir ./downloads
```

Compare SHA-256 hashes to verify the artifact is intact.

## CI/CD Configuration Templates

### GitHub Actions

See `github-action.yml` for a sample workflow that archives artifacts after a successful build. Copy to `.github/workflows/` in your repository.

### GitLab CI

See `gitlab-ci.yml` for a sample pipeline configuration. Copy the relevant sections to your `.gitlab-ci.yml`.

Both templates use `swarm-prov-upload` with `--std "CI-ARTIFACT-V1"` and `--usePool` for fast uploads.

## Archive Artifacts Helper

The `archive_artifacts.py` script automates artifact archival:

```bash
python archive_artifacts.py --directory ./dist
python archive_artifacts.py --directory ./dist --std "CI-ARTIFACT-V1"
```

## Sample Artifacts

| File | Description |
|------|-------------|
| `sample_artifacts/build_info.json` | Build metadata (version, commit, test results) |
| `sample_artifacts/release_notes.txt` | Release notes for v2.1.0 |

## Files

| File | Description |
|------|-------------|
| `demo.sh` | Shell demo — archive and verify artifacts |
| `run_demo.py` | Python demo — same workflow with argparse support |
| `archive_artifacts.py` | Standalone artifact archival tool |
| `github-action.yml` | Sample GitHub Actions workflow |
| `gitlab-ci.yml` | Sample GitLab CI configuration |
| `sample_artifacts/` | Directory of sample build artifacts |
