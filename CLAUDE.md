# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

The Swarm Provenance Uploader is a Python CLI toolkit that wraps provenance data files within metadata structures and uploads them to the Swarm decentralized storage network via a Bee gateway. It provides bidirectional operations for secure data storage with integrity verification.

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
pytest
```

### CLI Usage
```bash
# Upload data to Swarm
swarm-prov-upload --file /path/to/data.txt --std "PROV-STD-V1" --verbose

# Download and verify data from Swarm
swarm-prov-upload download <swarm_hash> --output-dir ./downloads --verbose
```

## Architecture

### Core Workflow
The application follows a modular architecture with clear separation of concerns:

1. **CLI Layer** (`cli.py`): Typer-based command interface with upload/download commands
2. **Core Modules** (`core/`): Business logic split across specialized modules
3. **Data Models** (`models.py`): Pydantic v2 schemas for metadata structure
4. **Configuration** (`config.py`): Environment-based configuration management

### Key Components

**ProvenanceMetadata Model**: The central data structure containing:
- `data`: Base64-encoded original file content
- `content_hash`: SHA256 hash for integrity verification
- `stamp_id`: Swarm postage stamp identifier
- `provenance_standard`: Optional provenance standard identifier
- `encryption`: Optional encryption details

**Upload Process**:
1. File reading and SHA256 hashing (`file_utils.py`)
2. Postage stamp purchasing and validation (`swarm_client.py`)
3. Metadata wrapping (`metadata_builder.py`)
4. Upload to Swarm network (`swarm_client.py`)

**Download Process**:
1. Metadata retrieval from Swarm (`swarm_client.py`)
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
- `BEE_GATEWAY_URL`: Swarm Bee gateway endpoint (default: http://localhost:1633)
- `POSTAGE_DEPTH`: Stamp depth parameter (default: 17)
- `POSTAGE_AMOUNT`: Stamp amount parameter (default: 1000000000)

## Testing Approach

The test suite uses pytest with comprehensive mocking:
- Network calls mocked via `requests-mock`
- File I/O operations mocked with `pytest-mock`
- CLI command testing with Typer's testing utilities
- Test data includes realistic Swarm API responses

Tests do not require a live Bee node and run entirely with mocks.

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