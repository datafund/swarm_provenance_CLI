import os
from dotenv import load_dotenv

load_dotenv()  # Load variables from .env file

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
# The actual private key should be in this env var, not in config
X402_PRIVATE_KEY_ENV = os.getenv("X402_PRIVATE_KEY_ENV", "SWARM_X402_PRIVATE_KEY")

# Network: "base-sepolia" (testnet, default) or "base" (mainnet)
X402_NETWORK = os.getenv("X402_NETWORK", "base-sepolia")

# Auto-pay without prompting (disabled by default for safety)
X402_AUTO_PAY = os.getenv("X402_AUTO_PAY", "false").lower() == "true"

# Maximum auto-pay amount per request in USD (default: $1.00)
try:
    X402_MAX_AUTO_PAY_USD = float(os.getenv("X402_MAX_AUTO_PAY_USD", "1.00"))
except (ValueError, TypeError):
    X402_MAX_AUTO_PAY_USD = 1.00

# Custom RPC URL (optional, uses default if not set)
X402_RPC_URL = os.getenv("X402_RPC_URL")
