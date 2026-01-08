# CI/CD Integration Example

This example demonstrates how to integrate the Swarm Provenance CLI into automated CI/CD pipelines for build artifact archival and release provenance tracking.

## Use Cases

- **Build Artifact Archival**: Store compiled binaries, packages
- **Release Provenance**: Track deployment receipts
- **Audit Trail Automation**: Automated compliance record creation
- **Backup Automation**: Scheduled data preservation

## What You'll Learn

- GitHub Actions workflow integration
- GitLab CI configuration
- Environment variable setup
- Automated artifact archival
- Release receipt generation

## Prerequisites

```bash
# Verify CLI is available
swarm-prov-upload --version
swarm-prov-upload health
```

## Environment Variables

Configure these secrets/variables in your CI/CD platform:

| Variable | Description | Required |
|----------|-------------|----------|
| `PROVENANCE_BACKEND` | Backend type (`gateway` or `local`) | No (default: gateway) |
| `PROVENANCE_GATEWAY_URL` | Gateway URL | No (uses default) |
| `SWARM_STAMP_SIZE` | Stamp size preset | No (default: medium) |

## GitHub Actions

### Basic Workflow

```yaml
name: Archive Build Artifacts

on:
  release:
    types: [published]
  workflow_dispatch:

jobs:
  archive:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Swarm CLI
        run: pip install swarm-provenance-uploader

      - name: Build project
        run: |
          # Your build commands here
          echo "Build artifacts ready"

      - name: Archive to Swarm
        run: |
          swarm-prov-upload upload \
            --file ./dist/app.tar.gz \
            --std "RELEASE-V1" \
            --size medium
```

### With Release Receipt

See `github-action.yml` for a complete example that:
- Uploads build artifacts
- Creates a release manifest
- Stores the Swarm reference as a release asset

## GitLab CI

### Basic Configuration

```yaml
archive_artifacts:
  stage: deploy
  image: python:3.11
  script:
    - pip install swarm-provenance-uploader
    - swarm-prov-upload health
    - swarm-prov-upload upload --file ./dist/*.tar.gz --std "BUILD-V1"
  only:
    - tags
```

See `gitlab-ci.yml` for a complete multi-stage example.

## Archive Script

The `archive_artifacts.py` script provides:
- Automatic file discovery
- Manifest generation
- Error handling and retries
- Structured output for CI logs

Usage:
```bash
python archive_artifacts.py ./dist --std "RELEASE-V1" --size medium
```

## Release Manifest

Generated manifests include:

```json
{
  "version": "1.0",
  "created_at": "2025-01-08T12:00:00Z",
  "ci_environment": {
    "platform": "github-actions",
    "run_id": "12345",
    "commit_sha": "abc123...",
    "ref": "refs/tags/v1.0.0"
  },
  "artifacts": [
    {
      "filename": "app-v1.0.0.tar.gz",
      "swarm_ref": "def456...",
      "size": 1234567,
      "sha256": "sha256..."
    }
  ]
}
```

## Files in This Example

| File | Description |
|------|-------------|
| `README.md` | This documentation |
| `github-action.yml` | GitHub Actions workflow |
| `gitlab-ci.yml` | GitLab CI configuration |
| `archive_artifacts.py` | Python archive script |

## Best Practices

1. **Use Tags/Releases**: Trigger archival on release events
2. **Store References**: Save Swarm refs as release assets/notes
3. **Include Metadata**: Add commit SHA, build number to manifests
4. **Size Appropriately**: Use `--size large` for big artifacts
5. **Handle Failures**: Implement retry logic for network issues

## Next Steps

- [04-batch-processing](../04-batch-processing/) - Archive multiple artifacts
- [02-audit-trail](../02-audit-trail/) - Add compliance standards
