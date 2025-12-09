# Swarm Provenance Uploader

A CLI toolkit to wrap data files within a metadata structure
and upload them to the Swarm decentralized storage network.

**Supports two backends:**
- **Gateway** (default): Uses `provenance-gateway.datafund.io` - no local Bee node required
- **Local**: Direct Bee node communication for development/self-hosted setups

## Quick Start

```bash
# Install
pip install -e .

# Check version
swarm-prov-upload --version

# Check connectivity
swarm-prov-upload health

# Upload data
swarm-prov-upload upload --file /path/to/data.txt

# Upload with existing stamp (skip purchase)
swarm-prov-upload upload --file /path/to/data.txt --stamp-id <existing_stamp_id>

# Download and verify
swarm-prov-upload download <swarm_hash> --output-dir ./downloads
```

## Setup

1. Create and activate a virtual environment.
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   # Or on Windows: .\venv\Scripts\activate
   ```
2. Copy `.env.example` to `.env` and adjust values if needed.
   ```bash
   cp .env.example .env
   ```
3. Install in editable mode, including testing dependencies:
   ```bash
   pip install -e .[testing]
   ```

## Backend Configuration

### Gateway Backend (Default)
No local Bee node required. Uses the Datafund provenance gateway.

```bash
# Uses gateway by default
swarm-prov-upload upload --file data.txt

# Or explicitly
swarm-prov-upload --backend gateway upload --file data.txt

# Custom gateway URL
swarm-prov-upload --gateway-url https://custom.gateway.io upload --file data.txt
```

### Local Backend
For development or self-hosted Swarm nodes.

```bash
# Use local Bee node
swarm-prov-upload --backend local upload --file data.txt

# Custom Bee URL
swarm-prov-upload --backend local upload --file data.txt --bee-url http://localhost:1633
```

### Environment Variables

```bash
PROVENANCE_BACKEND=gateway           # gateway (default) or local
PROVENANCE_GATEWAY_URL=https://provenance-gateway.datafund.io
BEE_GATEWAY_URL=http://localhost:1633
DEFAULT_POSTAGE_DEPTH=17
DEFAULT_POSTAGE_AMOUNT=1000000000
```

## Run Tests

### Unit Tests (Mocked)

Unit tests use mocks and do not require a live Bee node or gateway.

```bash
# Run all tests (unit + integration)
pytest

# Run only unit tests (skip integration)
pytest --ignore=tests/test_integration.py
```

### Integration Tests (Real Backends)

Integration tests hit real services. They auto-skip if backends are unavailable.

```bash
# Run only integration tests
pytest tests/test_integration.py -v

# Run only local Bee tests
pytest -m local_bee

# Run only gateway tests
pytest -m gateway
```

**Requirements:**
- Local Bee: Running at `http://localhost:1633`
- Gateway: Available at `https://provenance-gateway.datafund.io`

## Usage

### Data Operations

```bash
# Upload data to Swarm
swarm-prov-upload upload --file /path/to/data.txt --std "PROV-STD-V1" --verbose

# Upload with existing stamp (cost savings, faster)
swarm-prov-upload upload --file /path/to/data.txt --stamp-id <existing_stamp_id>

# Download and verify data
swarm-prov-upload download <swarm_hash> --output-dir ./downloads --verbose
```

### Stamp Management (Gateway only)

```bash
# List all stamps
swarm-prov-upload stamps list

# Get stamp details
swarm-prov-upload stamps info <stamp_id>

# Extend stamp TTL
swarm-prov-upload stamps extend <stamp_id> --amount 1000000
```

### Information Commands

```bash
# Check backend health
swarm-prov-upload health

# Wallet info (gateway only)
swarm-prov-upload wallet

# Chequebook info (gateway only)
swarm-prov-upload chequebook
```

Use `swarm-prov-upload --help` for all options.

## Architecture & Features

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           SWARM PROVENANCE UPLOADER                            │
│                              Architecture Diagram                               │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                                CLI INTERFACE                                    │
│  ┌─────────────────┐  ┌──────────────────┐  ┌─────────────────────────────────┐ │
│  │ GLOBAL OPTIONS  │  │ DATA COMMANDS    │  │ INFO COMMANDS                   │ │
│  │                 │  │                  │  │                                 │ │
│  │ --backend       │  │ upload           │  │ health                          │ │
│  │   gateway|local │  │ download         │  │ wallet (gateway)                │ │
│  │ --gateway-url   │  │                  │  │ chequebook (gateway)            │ │
│  │                 │  ├──────────────────┤  │                                 │ │
│  │ Built with:     │  │ STAMPS COMMANDS  │  │                                 │ │
│  │ • Typer CLI     │  │ (gateway only)   │  │                                 │ │
│  │ • Rich output   │  │ stamps list      │  │                                 │ │
│  │ • Auto help     │  │ stamps info      │  │                                 │ │
│  │                 │  │ stamps extend    │  │                                 │ │
│  └─────────────────┘  └──────────────────┘  └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              CORE BUSINESS LOGIC                               │
│  ┌───────────────────┐  ┌─────────────────┐  ┌──────────────────────────────┐  │
│  │ FILE_UTILS.PY     │  │ METADATA_       │  │ BACKEND CLIENTS              │  │
│  │                   │  │ BUILDER.PY      │  │                              │  │
│  │ • File I/O        │  │                 │  │ gateway_client.py (default)  │  │
│  │ • SHA256 hashing  │  │ • Pydantic      │  │ • Gateway API wrapper        │  │
│  │ • Base64 encode   │  │   validation    │  │ • Full feature support       │  │
│  │ • Base64 decode   │  │ • JSON          │  │ • No local node needed       │  │
│  │ • Size calculation│  │   serialization │  │                              │  │
│  │ • Error handling  │  │ • Metadata      │  │ swarm_client.py (local)      │  │
│  │                   │  │   wrapping      │  │ • Direct Bee API             │  │
│  │                   │  │                 │  │ • Local/self-hosted          │  │
│  └───────────────────┘  └─────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                             DATA MODELS & CONFIG                               │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │ MODELS.PY                       │  │ CONFIG.PY                           │  │
│  │                                 │  │                                     │  │
│  │ ProvenanceMetadata (Pydantic):  │  │ Environment Configuration:          │  │
│  │ ┌─────────────────────────────┐ │  │ • PROVENANCE_BACKEND               │  │
│  │ │ • data: str (Base64)        │ │  │ • PROVENANCE_GATEWAY_URL           │  │
│  │ │ • content_hash: str (SHA256)│ │  │ • BEE_GATEWAY_URL                  │  │
│  │ │ • stamp_id: str (64 hex)    │ │  │ • DEFAULT_POSTAGE_DEPTH            │  │
│  │ │ • provenance_standard: str? │ │  │ • DEFAULT_POSTAGE_AMOUNT           │  │
│  │ │ • encryption: str?          │ │  │ • .env file support                │  │
│  │ └─────────────────────────────┘ │  │                                     │  │
│  │                                 │  │                                     │  │
│  │ • JSON schema validation        │  │                                     │  │
│  │ • Auto serialization            │  │                                     │  │
│  │ • Type hints throughout         │  │                                     │  │
│  └─────────────────────────────────┘  └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                UPLOAD WORKFLOW                                 │
│                                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ 1. READ     │───▶│ 2. HASH &   │───▶│ 3. PURCHASE │───▶│ 4. WRAP &   │     │
│  │    FILE     │    │    ENCODE   │    │    STAMP    │    │    UPLOAD   │     │
│  │             │    │             │    │             │    │             │     │
│  │ • File I/O  │    │ • SHA256    │    │ • HTTP POST │    │ • Metadata  │     │
│  │ • Validate  │    │ • Base64    │    │ • Wait loop │    │ • JSON wrap │     │
│  │ • Read raw  │    │ • Size calc │    │ • Retry     │    │ • HTTP POST │     │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                                                 │
│                              ┌─────────────────┐                               │
│                              │ 5. RETURN HASH  │                               │
│                              │                 │                               │
│                              │ • Swarm ref     │                               │
│                              │ • 64-char hex   │                               │
│                              │ • Success msg   │                               │
│                              └─────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                               DOWNLOAD WORKFLOW                                │
│                                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ 1. FETCH    │───▶│ 2. PARSE &  │───▶│ 3. DECODE & │───▶│ 4. VERIFY & │     │
│  │    METADATA │    │    VALIDATE │    │    EXTRACT  │    │    SAVE     │     │
│  │             │    │             │    │             │    │             │     │
│  │ • HTTP GET  │    │ • JSON      │    │ • Base64    │    │ • SHA256    │     │
│  │ • Error     │    │ • Pydantic  │    │ • Extract   │    │ • Compare   │     │
│  │   handling  │    │ • Schema    │    │ • Raw bytes │    │ • Save both │     │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                                                 │
│                              ┌─────────────────┐                               │
│                              │ 5. SUCCESS      │                               │
│                              │                 │                               │
│                              │ • .data file    │                               │
│                              │ • .meta.json    │                               │
│                              │ • Verification  │                               │
│                              └─────────────────┘                               │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                              SWARM NETWORK LAYER                               │
│  ┌─────────────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │ GATEWAY (DEFAULT)               │  │ SWARM NETWORK                       │  │
│  │                                 │  │                                     │  │
│  │ provenance-gateway.datafund.io  │  │ • Decentralized storage             │  │
│  │ API Endpoints:                  │  │ • Content-addressable               │  │
│  │ • /api/v1/stamps/ - CRUD        │  │ • Redundant & persistent            │  │
│  │ • /api/v1/data/ - Upload/DL     │  │ • Cryptographic integrity           │  │
│  │ • /api/v1/wallet - Balance      │  │ • Economic incentives               │  │
│  │ • /api/v1/chequebook            │  │ • Censorship resistant              │  │
│  │                                 │  │                                     │  │
│  │ No local node required!         │  │                                     │  │
│  ├─────────────────────────────────┤  │                                     │  │
│  │ LOCAL BEE (--backend local)     │  │                                     │  │
│  │ Direct /bzz, /stamps endpoints  │  │                                     │  │
│  │ Requires running Bee node       │  │                                     │  │
│  └─────────────────────────────────┘  └─────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                                KEY FEATURES                                    │
│                                                                                 │
│  🔒 SECURITY & INTEGRITY           📦 DATA PROCESSING                          │
│  • SHA256 content verification    • Base64 encoding/decoding                  │
│  • Cryptographic hashing          • JSON metadata wrapping                    │
│  • Immutable storage              • Pydantic data validation                  │
│  • Tamper detection               • Type-safe operations                      │
│                                                                                 │
│  🌐 DECENTRALIZED STORAGE          ⚙️  OPERATIONAL                             │
│  • Swarm network integration      • Verbose/concise modes                     │
│  • Content-addressable            • Comprehensive error handling              │
│  • Censorship resistant           • Retry logic with backoff                  │
│  • Persistent & redundant         • Environment configuration                 │
│                                                                                 │
│  🏷️  PROVENANCE METADATA           🧪 TESTING & RELIABILITY                   │
│  • Standard identifier support    • Mock-based test suite                     │
│  • Optional encryption details    • No live node required for tests           │
│  • Bidirectional operations       • Comprehensive CLI testing                 │
│  • Metadata preservation          • CI/CD ready                               │
│                                                                                 │
│  🔗 POSTAGE STAMP SYSTEM           📊 MONITORING & DEBUGGING                   │
│  • Economic spam prevention       • Detailed verbose output                   │
│  • TTL-based data persistence     • HTTP request/response logging             │
│  • Automatic stamp validation     • Progress indicators                       │
│  • Configurable parameters        • Error context & suggestions               │
│                                                                                 │
│  🔀 DUAL BACKEND SUPPORT           🚀 GATEWAY FEATURES (NEW)                   │
│  • Gateway backend (default)      • stamps list - View all stamps             │
│  • Local Bee backend option       • stamps extend - Add TTL                   │
│  • Seamless switching             • wallet - View BZZ balance                 │
│  • Same CLI for both              • chequebook - View chequebook              │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────────┐
│                               TECHNOLOGY STACK                                 │
│                                                                                 │
│  🐍 CORE TECHNOLOGIES              📚 KEY LIBRARIES                            │
│  • Python 3.8+                    • Typer - CLI framework                     │
│  • Modular architecture           • Pydantic v2 - Data validation             │
│  • Type hints throughout          • Requests - HTTP client                    │
│  • Async-ready design             • Python-dotenv - Config management         │
│                                                                                 │
│  🔧 DEVELOPMENT TOOLS              🧪 TESTING FRAMEWORK                        │
│  • Virtual environment            • Pytest - Test runner                      │
│  • Editable installation          • Pytest-mock - Mocking utilities           │
│  • Environment configuration      • Requests-mock - HTTP mocking              │
│  • Rich CLI output                • No external dependencies for tests        │
└─────────────────────────────────────────────────────────────────────────────────┘
```

This architecture diagram shows the **Swarm Provenance Uploader** as a layered system that:

1. **CLI Layer**: Provides user-friendly commands with rich help and validation
2. **Core Logic**: Handles file processing, metadata creation, and Swarm communication
3. **Data Models**: Ensures type safety and validation with Pydantic schemas
4. **Network Layer**: Interfaces with Bee nodes and the Swarm decentralized network

**Key Strengths**:
- ✅ **Dual backend support** (gateway default, local Bee optional)
- ✅ **Bidirectional operations** (upload/download)
- ✅ **Integrity verification** (SHA256 hashing)
- ✅ **Metadata preservation** (provenance standards)
- ✅ **Decentralized storage** (Swarm network)
- ✅ **Production ready** (error handling, retries, logging)

## Project Directory Structure

```
swarm_provenance_uploader/
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── swarm_provenance_uploader/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   └── core/
│       ├── __init__.py
│       ├── file_utils.py
│       ├── gateway_client.py    # Gateway API client (default)
│       ├── metadata_builder.py
│       └── swarm_client.py      # Local Bee API client
└── tests/
    ├── __init__.py
    ├── test_cli.py              # CLI unit tests (mocked)
    ├── test_gateway_client.py   # GatewayClient unit tests (mocked)
    └── test_integration.py      # Integration tests (real backends)
```

