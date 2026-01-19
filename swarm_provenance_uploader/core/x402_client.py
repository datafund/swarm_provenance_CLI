"""
x402 Payment Client for pay-per-request API access.

This module handles x402 protocol payments using USDC on Base chain.
It parses 402 responses, signs payment authorizations using EIP-712,
and constructs the X-PAYMENT header for retrying requests.

Requires optional dependencies: pip install swarm-provenance-uploader[x402]
"""

import base64
import json
import os
import secrets
import time
from typing import Optional, Tuple

from ..exceptions import (
    InsufficientBalanceError,
    PaymentRejectedError,
    PaymentRequiredError,
    X402ConfigurationError,
    X402NetworkError,
)
from ..models import (
    X402PaymentOption,
    X402PaymentPayload,
    X402PaymentRequirements,
)

# Lazy imports for optional x402 dependencies
_eth_account = None
_web3 = None


def _import_x402_deps():
    """Lazily import x402 dependencies to avoid import errors when not installed."""
    global _eth_account, _web3
    if _eth_account is None:
        try:
            from eth_account import Account as _eth_account_module
            from web3 import Web3 as _web3_module
            _eth_account = _eth_account_module
            _web3 = _web3_module
        except ImportError as e:
            raise X402ConfigurationError(
                "x402 dependencies not installed. Run: pip install swarm-provenance-uploader[x402]"
            ) from e
    return _eth_account, _web3


# USDC contract addresses by network
USDC_CONTRACTS = {
    "base-sepolia": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
}

# Default RPC endpoints
RPC_ENDPOINTS = {
    "base-sepolia": "https://sepolia.base.org",
    "base": "https://mainnet.base.org",
}

# EIP-712 domain for USDC permit
USDC_PERMIT_DOMAIN = {
    "base-sepolia": {
        "name": "USD Coin",
        "version": "2",
        "chainId": 84532,
        "verifyingContract": USDC_CONTRACTS["base-sepolia"],
    },
    "base": {
        "name": "USD Coin",
        "version": "2",
        "chainId": 8453,
        "verifyingContract": USDC_CONTRACTS["base"],
    },
}


class X402Client:
    """
    Client for handling x402 pay-per-request payments.

    This client:
    - Parses HTTP 402 responses to extract payment requirements
    - Signs payment authorizations using EIP-712 typed data
    - Constructs the X-PAYMENT header for authenticated requests
    - Checks wallet USDC balance
    """

    SUPPORTED_NETWORKS = ["base-sepolia", "base"]

    def __init__(
        self,
        private_key: Optional[str] = None,
        network: str = "base-sepolia",
        rpc_url: Optional[str] = None,
    ):
        """
        Initialize the x402 payment client.

        Args:
            private_key: Ethereum private key for signing payments.
                         If None, reads from X402_PRIVATE_KEY env var.
            network: Network to use ('base-sepolia' or 'base').
            rpc_url: Custom RPC URL. If None, uses default for network.

        Raises:
            X402ConfigurationError: If private key is missing or invalid.
            X402NetworkError: If network is not supported.
        """
        # Import dependencies
        Account, Web3 = _import_x402_deps()

        # Validate network
        if network not in self.SUPPORTED_NETWORKS:
            raise X402NetworkError(
                f"Unsupported network: {network}. Supported: {self.SUPPORTED_NETWORKS}",
                expected=", ".join(self.SUPPORTED_NETWORKS),
                actual=network,
            )
        self.network = network

        # Get private key
        self._private_key = private_key or os.getenv("X402_PRIVATE_KEY") or os.getenv("SWARM_X402_PRIVATE_KEY")
        if not self._private_key:
            raise X402ConfigurationError(
                "x402 private key not configured. Set X402_PRIVATE_KEY or SWARM_X402_PRIVATE_KEY environment variable."
            )

        # Validate and derive address
        try:
            if not self._private_key.startswith("0x"):
                self._private_key = "0x" + self._private_key
            self._account = Account.from_key(self._private_key)
            self.address = self._account.address
        except Exception as e:
            raise X402ConfigurationError(f"Invalid private key: {e}") from e

        # Setup Web3 connection
        self._rpc_url = rpc_url or RPC_ENDPOINTS.get(network)
        self._web3 = Web3(Web3.HTTPProvider(self._rpc_url))

        # USDC contract address for this network
        self._usdc_address = USDC_CONTRACTS.get(network)

    @property
    def wallet_address(self) -> str:
        """Get the wallet address derived from the private key."""
        return self.address

    def parse_402_response(self, response_body: dict) -> X402PaymentRequirements:
        """
        Parse an HTTP 402 response body to extract payment requirements.

        Args:
            response_body: The JSON body from a 402 response.

        Returns:
            X402PaymentRequirements with accepted payment options.

        Raises:
            PaymentRequiredError: If response format is invalid.
        """
        try:
            return X402PaymentRequirements.model_validate(response_body)
        except Exception as e:
            raise PaymentRequiredError(
                f"Failed to parse 402 response: {e}",
                payment_options=[],
            ) from e

    def select_payment_option(
        self, requirements: X402PaymentRequirements
    ) -> X402PaymentOption:
        """
        Select a compatible payment option from requirements.

        Prefers options matching the configured network.

        Args:
            requirements: Payment requirements from 402 response.

        Returns:
            The selected payment option.

        Raises:
            PaymentRequiredError: If no compatible option found.
        """
        # Filter for matching network
        compatible = [
            opt for opt in requirements.accepts
            if opt.network == self.network
        ]

        if not compatible:
            available_networks = [opt.network for opt in requirements.accepts]
            raise X402NetworkError(
                f"No payment options for network '{self.network}'. "
                f"Available: {available_networks}",
                expected=self.network,
                actual=", ".join(available_networks),
            )

        # Prefer 'exact' scheme if available
        exact_options = [opt for opt in compatible if opt.scheme == "exact"]
        if exact_options:
            return exact_options[0]

        return compatible[0]

    def get_usdc_balance(self) -> Tuple[int, float]:
        """
        Get USDC balance for the configured wallet.

        Returns:
            Tuple of (raw_balance_smallest_units, balance_in_usdc).

        Raises:
            X402ConfigurationError: If balance check fails.
        """
        # USDC ERC-20 balanceOf ABI
        balance_of_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            }
        ]

        try:
            contract = self._web3.eth.contract(
                address=self._web3.to_checksum_address(self._usdc_address),
                abi=balance_of_abi,
            )
            raw_balance = contract.functions.balanceOf(self.address).call()
            usdc_balance = raw_balance / 1_000_000  # USDC has 6 decimals
            return raw_balance, usdc_balance
        except Exception as e:
            raise X402ConfigurationError(f"Failed to check USDC balance: {e}") from e

    def check_balance_sufficient(self, required_amount: str) -> bool:
        """
        Check if wallet has sufficient USDC for payment.

        Args:
            required_amount: Required amount in smallest units (string).

        Returns:
            True if balance is sufficient.

        Raises:
            InsufficientBalanceError: If balance is insufficient.
        """
        raw_balance, usdc_balance = self.get_usdc_balance()
        required_int = int(required_amount)

        if raw_balance < required_int:
            required_usdc = required_int / 1_000_000
            raise InsufficientBalanceError(
                f"Insufficient USDC balance. Required: ${required_usdc:.6f}, "
                f"Available: ${usdc_balance:.6f}",
                required=str(required_int),
                available=str(raw_balance),
            )
        return True

    def _generate_nonce(self) -> bytes:
        """Generate a random 32-byte nonce for payment authorization."""
        return secrets.token_bytes(32)

    def sign_payment(
        self,
        payment_option: X402PaymentOption,
        timeout_seconds: int = 300,
    ) -> str:
        """
        Sign a payment authorization using EIP-712.

        Args:
            payment_option: The selected payment option.
            timeout_seconds: Payment validity window in seconds.

        Returns:
            Base64-encoded X-PAYMENT header value.

        Raises:
            PaymentRejectedError: If signing fails.
        """
        try:
            # Generate authorization data
            valid_after = int(time.time()) - 60  # 60 seconds before now
            valid_before = int(time.time()) + timeout_seconds
            nonce_bytes = self._generate_nonce()
            nonce_hex = "0x" + nonce_bytes.hex()
            amount = payment_option.maxAmountRequired

            # Build EIP-712 typed data for USDC TransferWithAuthorization
            domain = USDC_PERMIT_DOMAIN.get(self.network)
            if not domain:
                raise X402NetworkError(f"No EIP-712 domain for network: {self.network}")

            # Use sign_typed_data which handles EIP-712 properly
            message_types = {
                "TransferWithAuthorization": [
                    {"name": "from", "type": "address"},
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"},
                    {"name": "validAfter", "type": "uint256"},
                    {"name": "validBefore", "type": "uint256"},
                    {"name": "nonce", "type": "bytes32"},
                ],
            }

            message_data = {
                "from": self.address,
                "to": payment_option.payTo,
                "value": int(amount),
                "validAfter": valid_after,
                "validBefore": valid_before,
                "nonce": nonce_bytes,  # Pass as bytes for signing
            }

            # Sign using sign_typed_data (the correct API)
            signed = self._account.sign_typed_data(
                domain_data=domain,
                message_types=message_types,
                message_data=message_data,
            )
            signature = "0x" + signed.signature.hex()

            # Build the payment payload with string values for timestamps
            payload = X402PaymentPayload(
                x402Version=1,
                scheme=payment_option.scheme,
                network=self.network,
                payload={
                    "signature": signature,
                    "authorization": {
                        "from": self.address,
                        "to": payment_option.payTo,
                        "value": amount,
                        "validAfter": str(valid_after),
                        "validBefore": str(valid_before),
                        "nonce": nonce_hex,  # Hex string in payload
                    },
                },
            )

            # Encode as base64 for X-PAYMENT header
            payload_json = payload.model_dump_json()
            return base64.b64encode(payload_json.encode()).decode()

        except Exception as e:
            raise PaymentRejectedError(
                f"Failed to sign payment: {e}",
                reason=str(e),
            ) from e

    def create_payment_header(
        self,
        response_body: dict,
        timeout_seconds: int = 300,
        check_balance: bool = True,
    ) -> str:
        """
        Create X-PAYMENT header from a 402 response.

        This is the main entry point for handling 402 responses.
        It parses requirements, selects an option, optionally checks
        balance, and signs the payment.

        Args:
            response_body: The JSON body from a 402 response.
            timeout_seconds: Payment validity window.
            check_balance: Whether to verify USDC balance first.

        Returns:
            Base64-encoded value for X-PAYMENT header.

        Raises:
            PaymentRequiredError: If 402 response is invalid.
            X402NetworkError: If no compatible network option.
            InsufficientBalanceError: If balance check fails.
            PaymentRejectedError: If signing fails.
        """
        # Parse the 402 response
        requirements = self.parse_402_response(response_body)

        # Select a compatible payment option
        option = self.select_payment_option(requirements)

        # Optionally check balance
        if check_balance:
            self.check_balance_sufficient(option.maxAmountRequired)

        # Sign and return the payment header
        return self.sign_payment(option, timeout_seconds)

    def format_amount_usd(self, amount: str) -> str:
        """
        Format a USDC amount (in smallest units) as USD string.

        Args:
            amount: Amount in smallest units (6 decimals).

        Returns:
            Formatted string like "$0.05".
        """
        usdc = int(amount) / 1_000_000
        return f"${usdc:.2f}"
