# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## GitHub

- **Always use the `origin` remote**: `datafund/swarm_provenance_CLI`
- Never use `upstream` for issues, PRs, or any GitHub operations
- When running `gh` commands, always specify `--repo datafund/swarm_provenance_CLI`

## Git Commits

- Never mention "Claude" or AI tools in commit messages
- Keep commit messages focused on what changed and why

## Project Overview

The Swarm Provenance Uploader is a Python CLI toolkit that wraps provenance data files within metadata structures and uploads them to the Swarm decentralized storage network. It supports two backends:

- **Gateway** (default): Uses `provenance-gateway.datafund.io` - no local Bee node required
- **Local**: Direct Bee node communication for development/self-hosted setups

## Development Commands

### Setup
```bash
python -m venv .venv
source .venv/bin/activate
cp .env.example .env
pip install -e .[testing]
```

### Testing
```bash
# Run all tests (unit + integration)
pytest

# Run only unit tests (skip integration)
pytest --ignore=tests/test_integration.py

# Run only integration tests (requires real backends)
pytest tests/test_integration.py -v

# Run by marker
pytest -m local_bee    # Local Bee tests only
pytest -m gateway      # Gateway tests only
pytest -m integration  # All integration tests
```

### CLI Usage
```bash
# Check backend health
swarm-prov-upload health

# Upload data (uses gateway by default)
swarm-prov-upload upload --file /path/to/data.txt --std "PROV-STD-V1"

# Upload with local Bee backend
swarm-prov-upload --backend local upload --file /path/to/data.txt

# Download and verify data
swarm-prov-upload download <swarm_hash> --output-dir ./downloads

# Stamp management (gateway only)
swarm-prov-upload stamps list
swarm-prov-upload stamps info <stamp_id>
swarm-prov-upload stamps extend <stamp_id> --amount 1000000

# Wallet info (gateway only)
swarm-prov-upload wallet
swarm-prov-upload chequebook
```

## Architecture

### Core Workflow
The application follows a modular architecture with clear separation of concerns:

1. **CLI Layer** (`cli.py`): Typer-based command interface with commands for upload, download, stamps, wallet, health
2. **Core Modules** (`core/`): Business logic split across specialized modules
   - `gateway_client.py`: Client for provenance-gateway API (default)
   - `swarm_client.py`: Client for local Bee node API
   - `file_utils.py`: File I/O and encoding utilities
   - `metadata_builder.py`: Metadata construction
3. **Data Models** (`models.py`): Pydantic v2 schemas for metadata and API responses
4. **Configuration** (`config.py`): Environment-based configuration management

### Backend Clients

**GatewayClient** (`core/gateway_client.py`):
- Default backend, requires no local infrastructure
- Supports all features: stamps, wallet, chequebook, data upload/download
- Uses provenance-gateway.datafund.io API

**SwarmClient** (`core/swarm_client.py`):
- For local Bee node communication
- Subset of features (no stamp list, no extend, no wallet)
- Used with `--backend local`

### Key Components

**ProvenanceMetadata Model**: The central data structure containing:
- `data`: Base64-encoded original file content
- `content_hash`: SHA256 hash for integrity verification
- `stamp_id`: Swarm postage stamp identifier
- `provenance_standard`: Optional provenance standard identifier
- `encryption`: Optional encryption details

**Gateway API Models**: Response schemas for gateway endpoints:
- `StampDetails`, `StampListResponse`, `StampPurchaseResponse`
- `DataUploadResponse`, `DataDownloadResponse`
- `WalletResponse`, `ChequebookResponse`

**Upload Process**:
1. File reading and SHA256 hashing (`file_utils.py`)
2. Postage stamp purchasing and validation (via selected backend client)
3. Metadata wrapping (`metadata_builder.py`)
4. Upload to Swarm network (via selected backend client)

**Download Process**:
1. Metadata retrieval from Swarm (via selected backend client)
2. Data extraction and Base64 decoding (`file_utils.py`)
3. SHA256 integrity verification
4. File output with metadata preservation

### Error Handling Strategy
The codebase implements comprehensive error handling:
- HTTP request failures with detailed error messages
- Postage stamp validation with retry logic
- File I/O error handling with clear user feedback
- JSON parsing errors with context

### Configuration Management
Uses python-dotenv for environment configuration:

**Backend Selection**:
- `PROVENANCE_BACKEND`: `gateway` (default) or `local`
- `PROVENANCE_GATEWAY_URL`: Gateway URL (default: https://provenance-gateway.datafund.io)
- `BEE_GATEWAY_URL`: Local Bee URL (default: http://localhost:1633)

**Stamp Defaults**:
- `DEFAULT_POSTAGE_DEPTH`: Stamp depth parameter (default: 17)
- `DEFAULT_POSTAGE_AMOUNT`: Stamp amount parameter (default: 1000000000)

## Testing Approach

The test suite has two layers:

### Unit Tests (Mocked)
- `test_cli.py`: CLI command tests with mocked backends
- `test_gateway_client.py`: GatewayClient tests with mocked HTTP
- Network calls mocked via `requests-mock`
- File I/O operations mocked with `pytest-mock`
- Do not require live services

### Integration Tests (Real Backends)
- `test_integration.py`: Tests against real services
- Auto-skip when backends unavailable
- Markers: `@pytest.mark.integration`, `@pytest.mark.local_bee`, `@pytest.mark.gateway`
- Require: Local Bee at `localhost:1633` and/or gateway at `provenance-gateway.datafund.io`

## Development Guidelines

### Documentation Requirements
When adding features or making implementation changes:
- Update README.md with new CLI options or usage patterns
- Add docstrings to new functions and classes following existing patterns
- Update CLI help text for new commands or options (Typer automatically generates help from docstrings)
- Document configuration changes in both README.md and inline comments
- Include example usage for new features
- Update this CLAUDE.md file if architectural changes are made
- Ensure Pydantic model docstrings are updated as they contribute to auto-generated schema documentation
- Update function docstrings as they may be used for API documentation generation
- **IMPORTANT**: Update the architecture diagram section in README.md whenever changes are made that affect the system architecture, data flow, features, or technology stack

### Dependencies
- **Typer**: CLI framework with Click backend
- **Pydantic v2**: Data validation and serialization
- **Requests**: HTTP client for Bee gateway communication
- **Python-dotenv**: Environment configuration management

### Code Patterns
- Type hints throughout the codebase
- Pydantic models for data validation
- Comprehensive logging with verbose mode support
- Modular design with single responsibility principle
- Error handling with user-friendly messages

### File Structure Importance
The `core/` directory contains the business logic modules that should be modified when extending functionality. The CLI layer should remain focused on command interface and delegate to core modules.