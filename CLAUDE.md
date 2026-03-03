# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## GitHub

- **Always use the `origin` remote**: `datafund/swarm_provenance_CLI`
- Never use `upstream` for issues, PRs, or any GitHub operations
- When running `gh` commands, always specify `--repo datafund/swarm_provenance_CLI`

## Git Workflow

**IMPORTANT**: Always create a feature branch before making changes. Never commit directly to `main`.

### x402 Feature Development (Active)

**DO NOT MERGE `feature/x402-support` TO `main` UNTIL EXPLICITLY AGREED WITH USER.**

The x402 implementation uses a branching strategy:
- `feature/x402-support` - Main x402 feature branch (DO NOT MERGE TO MAIN)
- `feature/x402-core-module` - Issue #37: Core payment module
- `feature/x402-gateway-integration` - Issue #38: GatewayClient integration
- `feature/x402-cli-commands` - Issue #39: CLI commands and config
- `feature/x402-testing-docs` - Issue #40: Testing and documentation

All sub-branches merge into `feature/x402-support`, which only merges to `main` after explicit approval.

### Branch Naming
- `fix/` - Bug fixes (e.g., `fix/stamp-usability-check`)
- `feature/` - New features (e.g., `feature/add-stamp-purchase-command`)
- `docs/` - Documentation only (e.g., `docs/update-readme`)

### Commit Messages

**CRITICAL: NEVER mention "Claude", "AI", "Generated with", "Co-Authored-By: Claude", or any AI attribution in commits, PRs, or issues. This is a strict requirement - no exceptions.**

- Keep commit messages focused on what changed and why
- Use conventional commit style when appropriate

## Version Management

**IMPORTANT**: Increment the version number with each change that modifies functionality.

### Version Location
- Primary: `swarm_provenance_uploader/__init__.py` (`__version__`)
- Mirror: `pyproject.toml` (`version` field)

Both files MUST be kept in sync.

### Version Format
Uses semantic versioning with optional git hash: `MAJOR.MINOR.PATCH[+git.SHORT_HASH]`

- **Release versions**: `0.1.0`, `1.0.0` (clean semver for PyPI releases)
- **Development versions**: `0.1.1+git.abc1234` (includes git hash for traceability)

### When to Increment
- **PATCH** (0.0.X): Bug fixes, documentation updates, minor improvements
- **MINOR** (0.X.0): New features, new CLI commands, new API endpoints
- **MAJOR** (X.0.0): Breaking changes, incompatible API changes

### How to Update Version
1. Update `__version__` in `swarm_provenance_uploader/__init__.py`
2. Update `version` in `pyproject.toml`
3. The git hash suffix is added automatically at runtime (see below)

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
# Check version
swarm-prov-upload --version

# Check backend health
swarm-prov-upload health

# Upload data (uses gateway by default, 25 hour stamp validity)
swarm-prov-upload upload --file /path/to/data.txt --std "PROV-STD-V1"

# Upload with custom duration (hours, min 24)
swarm-prov-upload upload --file /path/to/data.txt --duration 168  # 7 days

# Upload with size preset
swarm-prov-upload upload --file /path/to/data.txt --size medium

# Upload with existing stamp (skips purchase)
swarm-prov-upload upload --file /path/to/data.txt --stamp-id <existing_stamp_id>

# Upload using pooled stamp (faster, ~5s vs >1min)
swarm-prov-upload upload --file /path/to/data.txt --usePool

# Upload with local Bee backend (uses legacy amount)
swarm-prov-upload --backend local upload --file /path/to/data.txt --amount 1000000000

# Download and verify data
swarm-prov-upload download <swarm_hash> --output-dir ./downloads

# Stamp management (gateway only)
swarm-prov-upload stamps list
swarm-prov-upload stamps info <stamp_id>
swarm-prov-upload stamps extend <stamp_id> --amount 1000000
swarm-prov-upload stamps check <stamp_id>     # Health check
swarm-prov-upload stamps pool-status          # Pool availability

# Wallet info (gateway only)
swarm-prov-upload wallet
swarm-prov-upload chequebook

# x402 payment commands (optional)
swarm-prov-upload x402 status
swarm-prov-upload x402 balance
swarm-prov-upload x402 info

# Upload with free tier (rate-limited, no wallet needed)
swarm-prov-upload --free upload --file /path/to/data.txt

# Upload with x402 enabled
swarm-prov-upload --x402 upload --file /path/to/data.txt

# Upload with auto-pay
swarm-prov-upload --x402 --auto-pay --max-pay 1.00 upload --file /path/to/data.txt

# Notary signing (gateway only)
swarm-prov-upload notary info                           # Check notary service status
swarm-prov-upload notary status                         # Quick status check
swarm-prov-upload notary verify --file signed.json      # Verify local file signature
swarm-prov-upload upload --file data.txt --sign notary  # Upload with notary signing
swarm-prov-upload download <hash> --verify              # Download with signature verification

# Chain commands (optional, requires blockchain dependencies)
swarm-prov-upload chain balance                                              # Wallet balance and chain info
swarm-prov-upload chain anchor <hash>                                        # Anchor a Swarm hash on-chain
swarm-prov-upload chain anchor <hash> --type "dataset"                       # Anchor with custom data type
swarm-prov-upload chain anchor <hash> --owner <address>                      # Anchor as delegate for owner
swarm-prov-upload chain get <hash>                                           # Get on-chain provenance record
swarm-prov-upload chain get <hash> --follow                                  # Walk transformation chain
swarm-prov-upload chain get <hash> --follow --depth 3                        # Limit chain walk depth
swarm-prov-upload chain verify <hash>                                        # Verify hash is anchored
swarm-prov-upload chain access <hash>                                        # Record data access
swarm-prov-upload chain status <hash>                                        # Query current status
swarm-prov-upload chain status <hash> --set restricted                       # Set status (active|restricted|deleted)
swarm-prov-upload chain transfer <hash> --to <address>                       # Transfer ownership
swarm-prov-upload chain delegate <address> --authorize                       # Authorize a delegate
swarm-prov-upload chain delegate <address> --revoke                          # Revoke a delegate
swarm-prov-upload chain transform <orig> <new> --description "..."           # Record transformation
swarm-prov-upload chain transform <orig> <new> --restrict-original           # Transform + restrict original
swarm-prov-upload chain protect <orig> <new> --description "..."             # Composite: transform + restrict
swarm-prov-upload chain protect <orig> <new> --anchor-new                    # Protect with auto-anchor

# Collection/manifest upload (directory as Swarm manifest, gateway only)
swarm-prov-upload upload-collection /path/to/directory                       # Upload directory
swarm-prov-upload upload-collection /path/to/directory --std "PROV-STD-V1"   # With provenance standard
swarm-prov-upload upload-collection /path/to/directory --duration 168        # Custom stamp duration
swarm-prov-upload upload-collection /path/to/directory --usePool             # Use pooled stamp
swarm-prov-upload upload-collection /path/to/directory --stamp-id <id>       # Reuse existing stamp
swarm-prov-upload upload-collection /path/to/directory --json                # JSON output
swarm-prov-upload upload-collection /path/to/directory --deferred            # Deferred upload
swarm-prov-upload upload-collection /path/to/directory --redundancy          # With redundancy
```

## Architecture

### Core Workflow
The application follows a modular architecture with clear separation of concerns:

1. **CLI Layer** (`cli.py`): Typer-based command interface with commands for upload, download, stamps, wallet, health, x402
2. **Core Modules** (`core/`): Business logic split across specialized modules
   - `gateway_client.py`: Client for provenance-gateway API (default)
   - `swarm_client.py`: Client for local Bee node API
   - `x402_client.py`: Client for x402 payment handling (optional)
   - `chain_client.py`: High-level facade for on-chain operations (optional)
   - `notary_utils.py`: Notary signature verification utilities
   - `file_utils.py`: File I/O and encoding utilities
   - `metadata_builder.py`: Metadata construction
3. **Chain Subpackage** (`chain/`): Low-level blockchain components
   - `provider.py`: Web3 connection management with chain presets
   - `wallet.py`: Private key handling and transaction signing
   - `contract.py`: DataProvenance contract wrapper with build_*_tx pattern
   - `abi/DataProvenance.json`: Embedded contract ABI
4. **Data Models** (`models.py`): Pydantic v2 schemas for metadata and API responses
5. **Exceptions** (`exceptions.py`): Custom exception hierarchy for unified error handling
6. **Configuration** (`config.py`): Environment-based configuration management

### Backend Clients

**GatewayClient** (`core/gateway_client.py`):
- Default backend, requires no local infrastructure
- Supports all features: stamps, wallet, chequebook, data upload/download
- Uses provenance-gateway.datafund.io API
- Integrated x402 payment handling when enabled

**SwarmClient** (`core/swarm_client.py`):
- For local Bee node communication
- Subset of features (no stamp list, no extend, no wallet)
- Used with `--backend local`

**X402Client** (`core/x402_client.py`):
- Optional client for x402 payment handling
- Lazy-loads eth-account and web3 dependencies
- Handles HTTP 402 Payment Required responses
- EIP-712 message signing for USDC payments on Base chain
- Supports Base Sepolia (testnet) and Base (mainnet)

**ChainClient** (`core/chain_client.py`):
- High-level facade for on-chain provenance operations
- Wraps ChainProvider + ChainWallet + DataProvenanceContract
- Write methods: `anchor()`, `anchor_for()`, `batch_anchor()`, `transform()`, `access()`, `batch_access()`, `set_status()`, `transfer_ownership()`, `set_delegate()`
- Read methods: `get()`, `verify()`, `get_provenance_chain()`, `balance()`, `health_check()`
- Lazy-loads web3 and eth-account via `blockchain` optional dependency group
- Targets DataProvenance contract on Base Sepolia (`0x9a3c6F47B69211F05891CCb7aD33596290b9fE64`)

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

**x402 Payment Models**: Schemas for x402 payment handling:
- `X402PaymentOption`: Individual payment option from 402 response
- `X402PaymentRequirements`: Parsed 402 response body with accepts array
- `X402PaymentPayload`: Signed payment payload for X-PAYMENT header

**Notary Models**: Schemas for notary signing:
- `NotaryInfoResponse`: Status and configuration from /api/v1/notary/info
- `NotaryStatusResponse`: Simplified health check from /api/v1/notary/status
- `NotarySignature`: Signature entry in a signed document

**Chain Models**: Schemas for on-chain provenance:
- `DataStatusEnum`: On-chain data status (ACTIVE, RESTRICTED, DELETED)
- `ChainProvenanceRecord`: Full on-chain provenance record
- `AnchorResult`: Transaction result from anchoring a hash
- `TransformResult`: Transaction result from recording a transformation
- `AccessResult`: Transaction result from recording data access
- `ChainWalletInfo`: Wallet balance and chain configuration info
- `SignedDocumentResponse`: Response from upload with sign=notary

**Collection Models**: Schemas for collection/manifest uploads:
- `ManifestUploadTiming`: Optional timing breakdown from manifest upload
- `ManifestUploadResponse`: Response with reference, file_count, timing
- `CollectionFileInfo`: Per-file info (path, size, content_hash)
- `CollectionProvenanceMetadata`: Full provenance metadata for a collection upload

**Upload Process**:
1. File reading and SHA256 hashing (`file_utils.py`)
2. Postage stamp purchasing and validation (via selected backend client)
3. Metadata wrapping (`metadata_builder.py`)
4. Upload to Swarm network (via selected backend client)

**Collection Upload Process** (gateway only):
1. Directory scanning and per-file SHA-256 hashing (`file_utils.py`)
2. TAR archive creation (uncompressed, `file_utils.py`)
3. Postage stamp acquisition (purchase, pool, or existing)
4. Upload TAR as Swarm manifest via `gateway_client.upload_manifest()`
5. Files accessible at `bzz/<reference>/path/to/file`

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
- `DEFAULT_POSTAGE_DURATION_HOURS`: Stamp validity in hours (gateway only, default: 25)
- `DEFAULT_POSTAGE_AMOUNT`: Legacy PLUR amount for local backend (default: 1000000000)

**Free Tier Mode**:
- `FREE_TIER`: Use gateway free tier with `X-Payment-Mode: free` header (default: false, rate-limited to 3 req/min)

**x402 Payment Configuration**:
- `X402_ENABLED`: Enable x402 payment support (default: false)
- `X402_PRIVATE_KEY`: Wallet private key for signing payments
- `X402_NETWORK`: `base-sepolia` (testnet) or `base` (mainnet)
- `X402_AUTO_PAY`: Enable auto-pay without prompts (default: false)
- `X402_MAX_AUTO_PAY_USD`: Maximum auto-pay amount per request (default: 1.00)

**Chain / Blockchain Configuration**:
- `CHAIN_ENABLED`: Enable on-chain anchoring (default: false)
- `CHAIN_NAME`: `base-sepolia` (testnet, default) or `base` (mainnet)
- `CHAIN_RPC_URL`: Custom RPC URL (optional, overrides preset)
- `CHAIN_CONTRACT`: Custom contract address (optional, overrides preset)
- `CHAIN_EXPLORER_URL`: Custom block explorer URL (optional, overrides preset)
- `CHAIN_GAS_LIMIT`: Explicit gas limit (optional, skips RPC estimation when set)
- `PROVENANCE_WALLET_KEY`: Wallet private key for signing transactions

## Testing Approach

The test suite has two layers:

### Unit Tests (Mocked)
- `test_cli.py`: CLI command tests with mocked backends
- `test_gateway_client.py`: GatewayClient tests with mocked HTTP
- `test_file_utils.py`: TAR creation and directory hashing tests
- `test_notary_utils.py`: Notary signature verification tests with mocked crypto
- `test_x402_client.py`: X402Client tests with mocked eth-account/web3
- `test_chain_client.py`: ChainClient tests with mocked web3/eth-account
- Network calls mocked via `requests-mock`
- File I/O operations mocked with `pytest-mock`
- Do not require live services

### Integration Tests (Real Backends)
- `test_integration.py`: Tests against real services
- Auto-skip when backends unavailable
- Markers: `@pytest.mark.integration`, `@pytest.mark.local_bee`, `@pytest.mark.gateway`, `@pytest.mark.blockchain`
- Require: Local Bee at `localhost:1633` and/or gateway at `provenance-gateway.datafund.io`
- Blockchain: Local Hardhat at `localhost:8545` with DataProvenance deployed, or Base Sepolia with funded wallet

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