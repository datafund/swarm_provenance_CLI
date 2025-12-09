import os
from dotenv import load_dotenv

load_dotenv()  # Load variables from .env file

# --- Defaults ---
GATEWAY_DEFAULT_URL = "https://provenance-gateway.datafund.io"
BEE_DEFAULT_URL = "http://localhost:1633"
DEFAULT_DEPTH = 17
DEFAULT_AMOUNT = 1000000000
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
    DEFAULT_POSTAGE_AMOUNT = int(os.getenv("DEFAULT_POSTAGE_AMOUNT", str(DEFAULT_AMOUNT)))
except (ValueError, TypeError):
    DEFAULT_POSTAGE_AMOUNT = DEFAULT_AMOUNT
