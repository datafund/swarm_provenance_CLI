import os
from dotenv import find_dotenv, load_dotenv

# Load the .env file of the folder the command runs in (#141). find_dotenv
# searches that folder, then each parent folder, and uses the first .env it
# finds. Without usecwd=True it would search from this package's install
# directory instead. Variables already set in the environment take precedence.
load_dotenv(find_dotenv(usecwd=True))

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

# Environment variable name that contains the private key
# The actual private key should be in this env var, not in config.
# Signing and the status display both resolve the key with
# core.x402_client.resolve_x402_private_key(), which reads this setting.
X402_PRIVATE_KEY_ENV = os.getenv("X402_PRIVATE_KEY_ENV", "X402_PRIVATE_KEY")  # gitleaks:allow (a variable name, not a key)

# Network: "base-sepolia" (testnet, default) or "base" (mainnet)
X402_NETWORK = os.getenv("X402_NETWORK", "base-sepolia")

# Auto-pay without prompting (disabled by default for safety)
X402_AUTO_PAY = os.getenv("X402_AUTO_PAY", "false").lower() == "true"

# Maximum auto-pay amount per request in USD (default: $1.00)
try:
    X402_MAX_AUTO_PAY_USD = float(os.getenv("X402_MAX_AUTO_PAY_USD", "1.00"))
except (ValueError, TypeError):
    X402_MAX_AUTO_PAY_USD = 1.00

# Custom RPC URL for USDC balance and EIP-712 domain checks (optional, uses
# the network preset if not set). X402Client reads it when no rpc_url is given.
X402_RPC_URL = os.getenv("X402_RPC_URL") or None

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

# Custom block explorer URL (optional, overrides preset for selected chain)
CHAIN_EXPLORER_URL = os.getenv("CHAIN_EXPLORER_URL")

# Environment variable name that contains the wallet private key
CHAIN_WALLET_KEY_ENV = os.getenv("CHAIN_WALLET_KEY_ENV", "PROVENANCE_WALLET_KEY")

# Explicit gas limit (optional, overrides estimation when set)
try:
    _chain_gas_limit_str = os.getenv("CHAIN_GAS_LIMIT")
    CHAIN_GAS_LIMIT = int(_chain_gas_limit_str) if _chain_gas_limit_str else None
except (ValueError, TypeError):
    CHAIN_GAS_LIMIT = None
