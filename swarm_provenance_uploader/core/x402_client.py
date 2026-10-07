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
import re
import secrets
import time
from typing import Optional, Tuple

from ..exceptions import (
    InsufficientBalanceError,
    PaymentRejectedError,
    PaymentRequiredError,
    PaymentRequirementsError,
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

# Used with fullmatch(): "$" alone would also accept a trailing newline.
_ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}")
_AMOUNT_RE = re.compile(r"[0-9]+")
_ZERO_ADDRESS = "0x" + "0" * 40

# Chain IDs for supported networks
CHAIN_IDS = {
    "base-sepolia": 84532,
    "base": 8453,
}


def compute_domain_separator(name: str, version: str, chain_id: int, contract_address: str) -> bytes:
    """
    Compute the EIP-712 DOMAIN_SEPARATOR for verification.

    This allows us to validate that our configured domain matches
    what the contract actually uses.

    Args:
        name: Token name (e.g., "USDC" or "USD Coin")
        version: Contract version (e.g., "2")
        chain_id: Chain ID (e.g., 84532 for Base Sepolia)
        contract_address: Token contract address

    Returns:
        The computed DOMAIN_SEPARATOR as bytes32
    """
    _, Web3 = _import_x402_deps()
    from eth_abi import encode

    # EIP-712 domain type hash
    type_hash = Web3.keccak(
        text="EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
    )

    # Hash name and version strings
    name_hash = Web3.keccak(text=name)
    version_hash = Web3.keccak(text=version)

    # Encode and hash to get DOMAIN_SEPARATOR
    domain_data = encode(
        ["bytes32", "bytes32", "bytes32", "uint256", "address"],
        [type_hash, name_hash, version_hash, chain_id, contract_address]
    )
    return Web3.keccak(domain_data)


def fetch_contract_domain_separator(web3_instance, contract_address: str) -> bytes:
    """
    Fetch the actual DOMAIN_SEPARATOR from a USDC contract.

    Args:
        web3_instance: Web3 instance connected to the right network
        contract_address: Token contract address

    Returns:
        The contract's DOMAIN_SEPARATOR as bytes32
    """
    abi = [{"constant": True, "inputs": [], "name": "DOMAIN_SEPARATOR",
            "outputs": [{"name": "", "type": "bytes32"}], "type": "function"}]
    contract = web3_instance.eth.contract(
        address=web3_instance.to_checksum_address(contract_address),
        abi=abi
    )
    return contract.functions.DOMAIN_SEPARATOR().call()


def validate_domain_config(
    network: str,
    name: str,
    version: str,
    web3_instance=None,
) -> bool:
    """
    Validate that a domain configuration matches the on-chain contract.

    This prevents signing with incorrect EIP-712 domains, which would
    result in invalid signatures that fail on-chain.

    Args:
        network: Network identifier (e.g., "base-sepolia")
        name: Token name to validate
        version: Token version to validate
        web3_instance: Optional Web3 instance (created if not provided)

    Returns:
        True if domain matches contract

    Raises:
        X402ConfigurationError: If domain doesn't match contract
    """
    _, Web3 = _import_x402_deps()

    contract_address = USDC_CONTRACTS.get(network)
    chain_id = CHAIN_IDS.get(network)

    if not contract_address or not chain_id:
        raise X402ConfigurationError(f"Unknown network: {network}")

    # Create web3 instance if not provided
    if web3_instance is None:
        rpc_url = RPC_ENDPOINTS.get(network)
        web3_instance = Web3(Web3.HTTPProvider(rpc_url))

    # Compute what we think DOMAIN_SEPARATOR should be
    computed = compute_domain_separator(name, version, chain_id, contract_address)

    # Fetch actual DOMAIN_SEPARATOR from contract
    try:
        actual = fetch_contract_domain_separator(web3_instance, contract_address)
    except Exception as e:
        raise X402ConfigurationError(
            f"Failed to fetch DOMAIN_SEPARATOR from contract on {network}: {e}"
        ) from e

    if computed != actual:
        raise X402ConfigurationError(
            f"EIP-712 domain mismatch on {network}! "
            f"Configured name='{name}', version='{version}' produces "
            f"DOMAIN_SEPARATOR {computed.hex()}, but contract has {actual.hex()}. "
            f"Payments will fail on-chain. Check the token's actual domain name."
        )

    return True


# EIP-712 domain for USDC permit
# IMPORTANT: The domain name MUST match what the USDC contract uses for EIP-712 signing.
# The two networks differ: the Base Sepolia contract's name() is "USDC", the Base
# mainnet contract's name() is "USD Coin". Both values were read from the contracts
# and checked against their on-chain DOMAIN_SEPARATOR (pinned in tests).
# Use validate_domain_config() to verify at runtime before signing payments.
USDC_PERMIT_DOMAIN = {
    "base-sepolia": {
        "name": "USDC",  # Verified 2026-10-07: DOMAIN_SEPARATOR 0x71f17a3b...94c9818
        "version": "2",
        "chainId": 84532,
        "verifyingContract": USDC_CONTRACTS["base-sepolia"],
    },
    "base": {
        "name": "USD Coin",  # Verified 2026-10-07: DOMAIN_SEPARATOR 0x02fa7265...2c7834f
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
        skip_domain_validation: bool = False,
        expected_pay_to: Optional[str] = None,
    ):
        """
        Initialize the x402 payment client.

        Args:
            private_key: Ethereum private key for signing payments.
                         If None, reads from X402_PRIVATE_KEY env var.
            network: Network to use ('base-sepolia' or 'base').
            rpc_url: Custom RPC URL. If None, uses default for network.
            skip_domain_validation: Skip runtime domain validation (for testing only).
                                    WARNING: Do not use in production as it disables
                                    protection against signing with wrong EIP-712 domain.
            expected_pay_to: Only sign payments to this address. If None, reads
                             the X402_EXPECTED_PAY_TO env var; unset means any
                             well-formed recipient the gateway names.

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
                "x402 private key not configured. Set X402_PRIVATE_KEY environment variable."
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

        # Optional pinned recipient
        if expected_pay_to is None:
            expected_pay_to = os.getenv("X402_EXPECTED_PAY_TO")
        self.expected_pay_to = (expected_pay_to or "").strip() or None  # "" turns the pin off
        if self.expected_pay_to and not _ADDRESS_RE.fullmatch(self.expected_pay_to):
            raise X402ConfigurationError(
                f"X402_EXPECTED_PAY_TO is not an address: {self.expected_pay_to!r}"
            )

        # Domain validation state (lazy validation on first payment)
        # If skip_domain_validation=True, mark as already validated (for testing)
        self._skip_domain_validation = skip_domain_validation
        self._domain_validated = skip_domain_validation

    @property
    def wallet_address(self) -> str:
        """Get the wallet address derived from the private key."""
        return self.address

    def validate_domain(self, force: bool = False) -> bool:
        """
        Validate that our EIP-712 domain configuration matches the on-chain contract.

        This is called automatically before signing payments to ensure signatures
        will be valid on-chain. Call with force=True to re-validate.

        Args:
            force: Re-validate even if already validated

        Returns:
            True if domain is valid

        Raises:
            X402ConfigurationError: If domain doesn't match contract
        """
        if self._domain_validated and not force:
            return True

        domain = USDC_PERMIT_DOMAIN.get(self.network)
        if not domain:
            raise X402ConfigurationError(f"No domain config for network: {self.network}")

        validate_domain_config(
            network=self.network,
            name=domain["name"],
            version=domain["version"],
            web3_instance=self._web3,
        )

        self._domain_validated = True
        return True

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
            # New gateway wraps payload in {"detail": {...}}
            payload = response_body
            if "detail" in response_body and "accepts" in response_body.get("detail", {}):
                payload = response_body["detail"]
            return X402PaymentRequirements.model_validate(payload)
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

        Only options for the configured network that are safe to sign are
        considered: see refusal_reason().

        Args:
            requirements: Payment requirements from 402 response.

        Returns:
            The selected payment option.

        Raises:
            X402NetworkError: If no option is for the configured network.
            PaymentRequirementsError: If every option for the network is refused.
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

        refusals = []
        for opt in compatible:
            reason = self.refusal_reason(opt)
            if reason is None:
                return opt
            refusals.append(reason)

        raise PaymentRequirementsError(
            "Refused the gateway's payment request; nothing was signed: "
            + "; ".join(dict.fromkeys(refusals)),
            reasons=refusals,
        )

    def refusal_reason(self, option: X402PaymentOption) -> Optional[str]:
        """
        Why a payment option must not be signed, or None if it is acceptable.

        The signer only implements EIP-3009 transfers of USDC (the 'exact'
        scheme), so anything else the gateway asks for is refused rather than
        signed as if it were that.
        """
        # Gateway values in these messages are repr()'d: the CLI prints them, and
        # repr escapes control and formatting characters (terminal escapes).
        if option.network != self.network:
            return f"network {option.network!r} is not the configured '{self.network}'"
        if option.scheme != "exact":
            return f"scheme {option.scheme!r} is not supported (only 'exact')"
        if option.asset and option.asset.lower() != self._usdc_address.lower():
            return f"asset {option.asset!r} is not USDC on {self.network} ({self._usdc_address})"
        if not _AMOUNT_RE.fullmatch(option.maxAmountRequired or ""):
            return f"amount {option.maxAmountRequired!r} is not a whole number of USDC units"
        if not _ADDRESS_RE.fullmatch(option.payTo or ""):
            return f"payTo {option.payTo!r} is not an address"
        if option.payTo == _ZERO_ADDRESS:
            return "payTo is the zero address (the gateway has no pay-to address configured)"
        if self.expected_pay_to and option.payTo.lower() != self.expected_pay_to.lower():
            return (f"payTo {option.payTo} is not the expected recipient "
                    f"{self.expected_pay_to} (X402_EXPECTED_PAY_TO)")
        return None

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

    def _check_advertised_domain(self, payment_option: X402PaymentOption) -> None:
        """
        Compare the EIP-712 domain advertised in the 402 `extra` with ours.

        Facilitators build the verification domain from `extra`, so a gateway
        advertising a different name or version would reject a signature made
        against the contract's real domain. Fail before signing with a message
        that names the mismatch instead of a generic rejection after it.

        Raises:
            X402ConfigurationError: If `extra` names a different domain.
        """
        extra = payment_option.extra or {}
        domain = USDC_PERMIT_DOMAIN.get(self.network, {})
        for field in ("name", "version"):
            advertised = extra.get(field)
            # EIP-712 name and version are strings; a gateway sending version 2
            # as a number means the same domain.
            if advertised is not None and str(advertised) != domain.get(field):
                raise X402ConfigurationError(
                    f"Gateway advertises EIP-712 {field} '{advertised}' for {self.network}, "
                    f"but the USDC contract uses '{domain.get(field)}'. The payment would be "
                    "rejected at verification; nothing was signed. The gateway's x402 "
                    "configuration needs updating."
                )

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
            X402ConfigurationError: If EIP-712 domain doesn't match contract.
        """
        # Validate domain configuration against on-chain contract BEFORE signing
        # This prevents signing with an incorrect domain that would fail on-chain
        # Local checks run first: a refused request or a domain mismatch is
        # reported as such rather than hidden behind an RPC round-trip or error.
        reason = self.refusal_reason(payment_option)
        if reason:
            raise PaymentRequirementsError(
                f"Refused the gateway's payment request; nothing was signed: {reason}",
                reasons=[reason],
            )
        self._check_advertised_domain(payment_option)
        self.validate_domain()

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
            Formatted string with all 6 decimals, like "$0.050000". Rounding to
            cents would show a $0.004 payment as "$0.00".
        """
        raw = int(amount)
        return f"${raw // 1_000_000}.{raw % 1_000_000:06d}"
