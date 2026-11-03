import os
from dotenv import find_dotenv, load_dotenv

# Load the .env file of the folder the command runs in (#141). find_dotenv
# searches that folder, then each parent folder, and uses the first .env it
# finds. Without usecwd=True it would search from this package's install
# directory instead. Variables already set in the environment take precedence.
# If the working directory was deleted, os.getcwd() fails: skip .env loading
# then instead of crashing every command.
try:
    _dotenv_path = find_dotenv(usecwd=True)
except OSError:
    _dotenv_path = None
if _dotenv_path:
    load_dotenv(_dotenv_path)

# --- Defaults ---
GATEWAY_DEFAULT_URL = "https://provenance-gateway.datafund.io"
BEE_DEFAULT_URL = "http://localhost:1633"
DEFAULT_DEPTH = 17
DEFAULT_DURATION_HOURS = 25  # Minimum 24 hours required by gateway
DEFAULT_AMOUNT = 1000000000  # Legacy: kept for local Bee backend
DEFAULT_BACKEND = "gateway"  # "gateway" or "local"

# --- Backend Configuration ---
BACKEND = os.getenv("PROVENANCE_BACKEND", DEFAULT_BACKEND)
GATEWAY_URL = os.getenv("PROVENANCE_GATEWAY_URL", GATEWAY_DEFAULT_URL)

# --- Local Bee Configuration (when BACKEND=local) ---
BEE_GATEWAY_URL = os.getenv("BEE_GATEWAY_URL", BEE_DEFAULT_URL)

# --- Stamp Configuration ---
try:
    DEFAULT_POSTAGE_DEPTH = int(os.getenv("DEFAULT_POSTAGE_DEPTH", str(DEFAULT_DEPTH)))
except (ValueError, TypeError):
    DEFAULT_POSTAGE_DEPTH = DEFAULT_DEPTH

try:
    DEFAULT_POSTAGE_DURATION_HOURS = int(os.getenv("DEFAULT_POSTAGE_DURATION_HOURS", str(DEFAULT_DURATION_HOURS)))
except (ValueError, TypeError):
    DEFAULT_POSTAGE_DURATION_HOURS = DEFAULT_DURATION_HOURS

# Legacy: kept for local Bee backend compatibility
try:
    DEFAULT_POSTAGE_AMOUNT = int(os.getenv("DEFAULT_POSTAGE_AMOUNT", str(DEFAULT_AMOUNT)))
except (ValueError, TypeError):
    DEFAULT_POSTAGE_AMOUNT = DEFAULT_AMOUNT

# --- x402 Payment Configuration ---
# Enable x402 pay-per-request mode (disabled by default)
X402_ENABLED = os.getenv("X402_ENABLED", "false").lower() == "true"

# X402_PRIVATE_KEY_ENV and X402_RPC_URL are read when they are used, by
# core.x402_client.resolve_x402_private_key() and X402Client (#141).

# Network: "base-sepolia" (testnet, default) or "base" (mainnet)
X402_NETWORK = os.getenv("X402_NETWORK", "base-sepolia")

# Auto-pay without prompting (disabled by default for safety)
X402_AUTO_PAY = os.getenv("X402_AUTO_PAY", "false").lower() == "true"

# Maximum auto-pay amount per request in USD (default: $1.00). Kept as the
# string written: GatewayClient parses it exactly, and the CLI reports a value
# that is not a finite number of 0 or more (#152). A blank value counts as not set.
X402_MAX_AUTO_PAY_USD = os.getenv("X402_MAX_AUTO_PAY_USD", "")
if not X402_MAX_AUTO_PAY_USD.strip():
    X402_MAX_AUTO_PAY_USD = "1.00"

# Only sign payments to this address (optional). Pin it to the gateway
# operator's published pay-to address so a misconfigured or hostile gateway
# cannot redirect payments.
X402_EXPECTED_PAY_TO = os.getenv("X402_EXPECTED_PAY_TO") or None

# --- Free Tier Mode ---
# Sends X-Payment-Mode: free header (rate-limited to 3 req/min)
FREE_TIER = os.getenv("FREE_TIER", "false").lower() == "true"

# --- Chain / Blockchain Configuration ---
# Chain name: "base-sepolia" (testnet, default) or "base" (mainnet)
CHAIN_NAME = os.getenv("CHAIN_NAME", "base-sepolia")

# Custom RPC URL (optional, overrides preset for selected chain)
CHAIN_RPC_URL = os.getenv("CHAIN_RPC_URL")


def _split_urls(value):
    """Split a comma-separated URL list; None when it names no URL."""
    urls = [url.strip() for url in (value or "").split(",") if url.strip()]
    return urls or None


# Fallback RPC URLs, comma-separated (optional). They replace the preset
# fallbacks and are tried in order after CHAIN_RPC_URL (or the preset RPC).
CHAIN_RPC_URLS = _split_urls(os.getenv("CHAIN_RPC_URLS"))

# Custom contract address (optional, overrides preset for selected chain)
CHAIN_CONTRACT = os.getenv("CHAIN_CONTRACT")

# Block the contract was deployed in (optional), where event scans start.
# Kept as written: ChainProvider checks it when a chain client is built, so
# a bad value does not stop commands that do not use the chain.
CHAIN_DEPLOY_BLOCK = os.getenv("CHAIN_DEPLOY_BLOCK")

# Custom block explorer URL (optional, overrides preset for selected chain)
CHAIN_EXPLORER_URL = os.getenv("CHAIN_EXPLORER_URL")

# Environment variable name that contains the wallet private key
CHAIN_WALLET_KEY_ENV = os.getenv("CHAIN_WALLET_KEY_ENV", "PROVENANCE_WALLET_KEY")

# Smallest gas limit accepted for --gas and CHAIN_GAS_LIMIT (#226). Defined
# in constants.py, so the library can use it without loading .env.
from .constants import MIN_GAS_LIMIT  # noqa: E402

# Explicit gas limit (optional, overrides estimation when set). A value that
# is not a whole number of at least MIN_GAS_LIMIT is not used: the error is
# kept in CHAIN_GAS_LIMIT_ERROR, and the CLI reports it when a chain write
# would use the setting, so other commands still work (#226).
CHAIN_GAS_LIMIT = None
CHAIN_GAS_LIMIT_ERROR = None
_chain_gas_limit_str = (os.getenv("CHAIN_GAS_LIMIT") or "").strip()
if _chain_gas_limit_str:
    # Only ASCII digits: int() would also take "50_000", "+50000" and
    # non-ASCII digits such as full-width ones
    if _chain_gas_limit_str.isascii() and _chain_gas_limit_str.isdigit():
        CHAIN_GAS_LIMIT = int(_chain_gas_limit_str)
    if CHAIN_GAS_LIMIT is None or CHAIN_GAS_LIMIT < MIN_GAS_LIMIT:
        CHAIN_GAS_LIMIT = None
        CHAIN_GAS_LIMIT_ERROR = (
            f"CHAIN_GAS_LIMIT is not a whole number of at least {MIN_GAS_LIMIT}: "
            f"{_chain_gas_limit_str!r}"
        )
