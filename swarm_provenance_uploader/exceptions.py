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
