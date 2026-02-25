# Swarm Provenance CLI - Examples

Real-world usage examples for the Swarm Provenance CLI toolkit.

## Prerequisites

1. **Install the CLI** (with optional extras as needed):
   ```bash
   pip install -e "."                    # Base install
   pip install -e ".[blockchain]"        # With on-chain anchoring
   ```

2. **Gateway access** (default, no setup needed):
   The CLI uses the public provenance gateway by default. No local Bee node required.

3. **Environment** (optional):
   ```bash
   cp .env.example .env
   # Edit .env if you need custom gateway URL or blockchain config
   ```

## Examples

| # | Example | Description |
|---|---------|-------------|
| [01](01-basic-upload-download/) | **Basic Upload/Download** | Upload a file, download it back, verify integrity |

## Directory Structure

```
examples/
  README.md                    # This file
  common/
    __init__.py                # Shared utilities package
    sample_generator.py        # Generate sample data files
    verify.py                  # Verification helpers
  01-basic-upload-download/    # Core upload/download workflow
    README.md
    demo.sh
    sample.txt
    run_demo.py
```

## Common Utilities

The `common/` package provides shared helpers used across examples:

- **`sample_generator.py`** — Generate sample data files (text, JSON, CSV) for demos
- **`verify.py`** — Download and verify data integrity, compare hashes

Import them in Python scripts:

```python
from common.sample_generator import generate_text_file, generate_json_file
from common.verify import verify_download, compare_hashes
```

## Running Examples

Each example directory contains:

- **`README.md`** — Explanation of the use case and step-by-step walkthrough
- **`demo.sh`** — Shell script you can run end-to-end
- **`run_demo.py`** — Python script demonstrating the same flow programmatically
- **Sample data files** — Ready-to-use test data

### Shell demos

```bash
cd examples/01-basic-upload-download
chmod +x demo.sh
./demo.sh
```

### Python demos

```bash
cd examples
python -m 01-basic-upload-download.run_demo
# or
cd examples/01-basic-upload-download
python run_demo.py
```

## Tips

- Use `--usePool` for faster stamp acquisition (~5s vs >1min)
- Use `--json` flag to get machine-readable output for scripting
- Use `--stamp-id` to reuse an existing stamp across multiple uploads
- Use `-v` (verbose) to see detailed request/response information
