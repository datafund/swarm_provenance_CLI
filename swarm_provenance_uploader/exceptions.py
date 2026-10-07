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


class PaymentOutcomeUnknownError(X402Error):
    """A signed payment was sent, but whether it was collected is not known.

    Raised when a paid request times out, drops, or fails with a server error
    after the X-PAYMENT header went out. The gateway settles before doing the
    work and does not undo it when the client disconnects, so the payment may
    have been taken and the request may even have completed. Re-running the
    command signs a new authorization and can pay a second time.

    The attributes identify the payment so the user can check it on-chain or
    cite it to the operator: `nonce` is the EIP-3009 authorization nonce,
    `transaction` the settlement transaction hash when the gateway sent one.
    """

    def __init__(
        self,
        message: str,
        payer: str = None,
        nonce: str = None,
        amount: str = None,
        amount_usd: str = None,
        pay_to: str = None,
        network: str = None,
        transaction: str = None,
        status_code: int = None,
        code: str = None,
    ):
        super().__init__(message)
        self.payer = payer
        self.nonce = nonce
        self.amount = amount
        self.amount_usd = amount_usd
        self.pay_to = pay_to
        self.network = network
        self.transaction = transaction
        self.status_code = status_code
        self.code = code

    # Whether the gateway confirmed the payment was collected.
    settled = False


class PaymentSettledNotDeliveredError(PaymentOutcomeUnknownError):
    """The gateway collected the payment but did not deliver the result.

    The gateway reports this with `X-Payment-Status: settled_not_delivered`
    or the `DELIVERY_FAILED_AFTER_PAYMENT` code. The operator needs the
    `transaction` to deliver the result or refund it.
    """

    settled = True


class StampPurchasePendingError(PaymentSettledNotDeliveredError):
    """A paid stamp purchase was accepted but not yet confirmed (HTTP 202).

    The payment has settled; the gateway registers the batch to the payer's
    wallet once the Bee node reports it. Buying again would pay twice.
    """

    def __init__(self, message: str, label: str = None, depth: int = None,
                 lookup: str = None, **kwargs):
        super().__init__(message, **kwargs)
        self.label = label
        self.depth = depth
        self.lookup = lookup


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
# Canonical definitions live in chain/exceptions.py; re-exported here
# for backward compatibility.

from .chain.exceptions import (  # noqa: F401, E402
    ChainError,
    ChainConfigurationError,
    ChainConnectionError,
    ChainTransactionError,
    ChainValidationError,
    InsufficientFundsError,
    DataNotRegisteredError,
    DataAlreadyRegisteredError,
    TransformationAlreadyExistsError,
)
