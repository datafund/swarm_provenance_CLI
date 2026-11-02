"""Custom exceptions for the Swarm Provenance CLI.

Provides unified error handling across both gateway and local Bee backends.
"""

import requests


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
    """HTTP 402 received but x402 payments not configured or disabled.

    When the gateway's 402 carries its own error code (not the placeholder
    HTTP_402 of an ordinary payment request), `code` and `gateway_message`
    hold it, and `resets_at` the time a spent free allowance resets (#139).
    `free_tier_used` is True when the request was sent on the free tier;
    `gateway_message` then holds the gateway's reason even without a code.
    """

    # Codes for which the free tier is no way forward: the pool allowance is
    # what the free tier draws on, and the others refuse the free tier.
    FREE_TIER_DOES_NOT_HELP = frozenset({
        "DAILY_STAMP_ALLOWANCE_EXHAUSTED",
        "DAILY_STAMP_ALLOWANCE_PER_CLIENT_EXHAUSTED",
        "FREE_TIER_DISABLED",
        "PAYMENT_REQUIRED",
    })

    def __init__(self, message: str, payment_options: list = None, code: str = None,
                 gateway_message: str = None, resets_at: str = None,
                 free_tier_used: bool = False):
        super().__init__(message)
        self.payment_options = payment_options or []
        self.code = code
        self.gateway_message = gateway_message
        self.resets_at = resets_at
        # The request already asked for the free tier and still got a 402
        self.free_tier_used = free_tier_used

    @property
    def free_tier_helps(self) -> bool:
        """False when --free would not get past this 402: it was already used, or the code says so."""
        return not self.free_tier_used and self.code not in self.FREE_TIER_DOES_NOT_HELP


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
    """No longer raised; kept so existing imports keep working (#143).

    It was raised for a success whose X-PAYMENT-RESPONSE receipt said
    the payment failed. The gateway sends that receipt only after a
    successful settlement and never falls back to the free tier, so such
    an answer is now reported as PaymentOutcomeUnknownError.
    """

    def __init__(self, message: str, error_reason: str = None, payer: str = None):
        super().__init__(message)
        self.error_reason = error_reason
        self.payer = payer


class PaymentRequirementsError(X402Error):
    """The gateway's 402 payment request was refused before anything was signed.

    Raised when no offered option is safe to sign: an unsupported scheme, an
    asset that is not USDC on the network, a malformed amount or recipient,
    or a recipient other than the pinned X402_EXPECTED_PAY_TO.
    """

    def __init__(self, message: str, reasons: list = None):
        super().__init__(message)
        self.reasons = reasons or []


class InsecureGatewayWarning(UserWarning):
    """x402 payments are enabled against a plain-http (non-loopback) gateway.

    Anyone on the network path can then rewrite the 402 payment request,
    including the amount and the recipient.
    """


class PaymentOutcomeUnknownError(X402Error):
    """A signed payment was sent, but whether it was collected is not known.

    Raised when a paid request times out, drops, or fails with a server error
    after the X-PAYMENT header went out. The gateway settles before doing the
    work and does not undo it when the client disconnects, so the payment may
    have been taken and the request may even have completed. Re-running the
    command signs a new authorization and can pay a second time.

    The attributes identify the payment so the user can check it on-chain or
    cite it to the operator: `nonce` is the EIP-3009 authorization nonce,
    `transaction` the settlement transaction hash when the gateway sent one,
    and `valid_before` the unix time after which the authorization can no
    longer be collected.
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
        valid_before: int = None,
        idempotency_key: str = None,
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
        self.valid_before = valid_before
        self.idempotency_key = idempotency_key

    # Whether the gateway confirmed the payment was collected.
    settled = False


class PaymentSettledNotDeliveredError(PaymentOutcomeUnknownError):
    """The gateway collected the payment but did not deliver the result.

    The gateway reports this with `X-Payment-Status: settled_not_delivered`
    or the `DELIVERY_FAILED_AFTER_PAYMENT` code. The operator needs the
    `transaction` to deliver the result or refund it.
    """

    settled = True


class PaymentDeliveredNotStoredError(PaymentSettledNotDeliveredError):
    """The first request with this Idempotency-Key succeeded and was paid once.

    The gateway answers a retry with IDEMPOTENCY_KEY_DELIVERED_NOT_STORED when
    the first response was too large to keep. The operation worked; only its
    result cannot be returned again, so it must be looked up through the
    resource itself. This is not a failure.
    """


class IdempotencyKeyError(X402Error):
    """The gateway refused the Idempotency-Key itself; nothing was charged.

    `code` is IDEMPOTENCY_KEY_REUSED (the key was used for a different
    request) or IDEMPOTENCY_KEY_INVALID (malformed key).
    """

    def __init__(self, message: str, code: str = None, idempotency_key: str = None):
        super().__init__(message)
        self.code = code
        self.idempotency_key = idempotency_key


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


class GatewayHTTPError(requests.exceptions.HTTPError):
    """
    An error response from the gateway, with the gateway's own code and message (#139).

    A `requests.exceptions.HTTPError`, so code that catches that (and reads
    `e.response.status_code`) keeps working. `code` is the gateway's error code
    (for example STAMP_OWNERSHIP_DENIED), `gateway_message` its message, and
    `retry_after` the Retry-After header in seconds, when the gateway sent one.
    """

    def __init__(self, message: str, response: requests.Response = None, code: str = None,
                 gateway_message: str = None, retry_after: int = None):
        super().__init__(message, response=response)
        self.status_code = response.status_code if response is not None else None
        self.code = code
        self.gateway_message = gateway_message
        self.retry_after = retry_after


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
# for backward compatibility. The re-export is lazy: chain/exceptions.py
# imports ProvenanceError from this module, so importing it eagerly here
# made `import swarm_provenance_uploader.chain.provider` (or anything that
# reaches chain/exceptions.py first) fail with a circular ImportError.

_CHAIN_EXCEPTIONS = frozenset({
    "ChainError",
    "ChainConfigurationError",
    "ChainConnectionError",
    "ChainTransactionError",
    "ChainValidationError",
    "InsufficientFundsError",
    "TransactionUnconfirmedError",
    "TransactionNotRecordedError",
    "TransactionNotVerifiedError",
    "DataNotRegisteredError",
    "DataAlreadyRegisteredError",
    "TransformationAlreadyExistsError",
})


def __getattr__(name):
    if name in _CHAIN_EXCEPTIONS:
        from .chain import exceptions as _chain_exceptions

        value = getattr(_chain_exceptions, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | _CHAIN_EXCEPTIONS)
