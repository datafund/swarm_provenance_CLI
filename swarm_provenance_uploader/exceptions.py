"""Custom exceptions for the Swarm Provenance CLI.

Provides unified error handling across both gateway and local Bee backends.
"""


class ProvenanceError(Exception):
    """Base exception for all provenance CLI errors."""
    pass


class ConnectionError(ProvenanceError):
    """Failed to connect to backend (gateway or local Bee)."""
    pass


class StampNotFoundError(ProvenanceError):
    """Stamp does not exist."""
    pass


class StampNotUsableError(ProvenanceError):
    """Stamp exists but is not usable for uploads."""
    pass


class StampPurchaseError(ProvenanceError):
    """Failed to purchase a new stamp."""
    pass


class UploadError(ProvenanceError):
    """Failed to upload data to Swarm."""
    pass


class DownloadError(ProvenanceError):
    """Failed to download data from Swarm."""
    pass


class DataNotFoundError(ProvenanceError):
    """Requested data not found on Swarm."""
    pass


class ValidationError(ProvenanceError):
    """Data validation failed (e.g., hash mismatch, invalid format)."""
    pass


class AuthenticationError(ProvenanceError):
    """Authentication failed (for future API key support)."""
    pass


# --- x402 Payment Exceptions ---

class X402Error(ProvenanceError):
    """Base exception for x402 payment errors."""
    pass


class PaymentRequiredError(X402Error):
    """HTTP 402 received but x402 payments not configured or disabled."""

    def __init__(self, message: str, payment_options: list = None):
        super().__init__(message)
        self.payment_options = payment_options or []


class InsufficientBalanceError(X402Error):
    """Wallet USDC balance too low for required payment."""

    def __init__(self, message: str, required: str = None, available: str = None):
        super().__init__(message)
        self.required = required
        self.available = available


class PaymentRejectedError(X402Error):
    """Payment signature or amount rejected by x402 facilitator."""

    def __init__(self, message: str, reason: str = None):
        super().__init__(message)
        self.reason = reason


class X402ConfigurationError(X402Error):
    """x402 configuration is invalid or incomplete."""
    pass


class X402NetworkError(X402Error):
    """Network mismatch or unsupported network."""

    def __init__(self, message: str, expected: str = None, actual: str = None):
        super().__init__(message)
        self.expected = expected
        self.actual = actual


class PaymentTransactionFailedError(X402Error):
    """Payment was signed but the on-chain transaction failed.

    This occurs when the x402 facilitator could not execute the
    TransferWithAuthorization on-chain. The gateway may have fallen
    back to free tier.
    """

    def __init__(self, message: str, error_reason: str = None, payer: str = None):
        super().__init__(message)
        self.error_reason = error_reason
        self.payer = payer


# --- Stamp Pool Exceptions ---

class PoolError(ProvenanceError):
    """Base exception for stamp pool errors."""
    pass


class PoolNotEnabledError(PoolError):
    """Stamp pool is not enabled on this gateway."""
    pass


class PoolEmptyError(PoolError):
    """No stamps available in the pool for the requested size/depth."""

    def __init__(self, message: str, size: str = None, depth: int = None):
        super().__init__(message)
        self.size = size
        self.depth = depth


class PoolAcquisitionError(PoolError):
    """Failed to acquire stamp from pool despite availability.

    This can happen due to race conditions when multiple clients
    try to acquire the same stamp simultaneously.
    """

    def __init__(self, message: str, available_count: int = 0):
        super().__init__(message)
        self.available_count = available_count


# --- Notary Signing Exceptions ---

class NotaryError(ProvenanceError):
    """Base exception for notary signing errors."""
    pass


class NotaryNotEnabledError(NotaryError):
    """Notary signing is not enabled on this gateway."""
    pass


class NotaryNotConfiguredError(NotaryError):
    """Notary is enabled but private key not configured on gateway."""
    pass


class InvalidDocumentFormatError(NotaryError):
    """Document is not valid JSON or missing required 'data' field."""
    pass


class SignatureVerificationError(NotaryError):
    """Signature verification failed.

    This can occur when:
    - Data hash doesn't match
    - Signer address doesn't match expected
    - Signature is invalid or corrupted
    """

    def __init__(self, message: str, reason: str = None):
        super().__init__(message)
        self.reason = reason


# --- Chain / Blockchain Exceptions ---

class ChainError(ProvenanceError):
    """Base exception for blockchain-related errors."""
    pass


class ChainConfigurationError(ChainError):
    """Missing dependencies, invalid config, or missing wallet key."""
    pass


class ChainConnectionError(ChainError):
    """Failed to connect to RPC endpoint."""

    def __init__(self, message: str, rpc_url: str = None):
        super().__init__(message)
        self.rpc_url = rpc_url


class ChainTransactionError(ChainError):
    """Transaction reverted, ran out of gas, or otherwise failed."""

    def __init__(self, message: str, tx_hash: str = None):
        super().__init__(message)
        self.tx_hash = tx_hash


class ChainValidationError(ChainError):
    """Input validation failed (hash format, string lengths, batch limits)."""
    pass


class DataNotRegisteredError(ChainError):
    """Data hash not found on-chain."""

    def __init__(self, message: str, data_hash: str = None):
        super().__init__(message)
        self.data_hash = data_hash


class DataAlreadyRegisteredError(ChainError):
    """Data hash is already registered on-chain."""

    def __init__(
        self,
        message: str,
        data_hash: str = None,
        owner: str = None,
        timestamp: int = None,
        data_type: str = None,
    ):
        super().__init__(message)
        self.data_hash = data_hash
        self.owner = owner
        self.timestamp = timestamp
        self.data_type = data_type
