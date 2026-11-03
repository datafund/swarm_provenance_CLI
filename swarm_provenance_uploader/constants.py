"""Constants shared by the CLI and the library.

This module has no side effects: importing it does not read the
environment or a .env file, unlike config.py.
"""

# Smallest gas limit accepted for --gas, CHAIN_GAS_LIMIT and
# ChainClient(gas_limit=...): the gas that every transaction uses (#226)
MIN_GAS_LIMIT = 21000
