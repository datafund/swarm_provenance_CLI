"""Custom exceptions for blockchain-related operations.

Standalone exception hierarchy for the chain module. These inherit from
the main ProvenanceError base to keep a unified exception tree while
allowing the chain module to be self-contained.
"""

from typing import Optional

from ..exceptions import ProvenanceError
from .redact import redact_url, redact_urls


class ChainError(ProvenanceError):
    """Base exception for blockchain-related errors.

    URLs in the message are redacted (scheme, host and port are kept),
    because chain errors often repeat the RPC URL, which can carry a
    provider API key (#169).
    """

    def __init__(self, message: str = "", *args):
        if isinstance(message, str):
            message = redact_urls(message)
        super().__init__(message, *args)


class ChainConfigurationError(ChainError):
    """Missing dependencies, invalid config, or missing wallet key."""
    pass


class ChainIdMismatchError(ChainConfigurationError):
    """The RPC endpoint is on another chain than the configured preset.

    Raised for the ``base`` and ``base-sepolia`` presets, when the client
    starts or before its first signature. Nothing has been signed or sent.
    ChainProvider.health_check() raises it for any preset when the RPC in
    use reports another chain ID; no fallback is tried then.
    """

    def __init__(
        self,
        message: str,
        chain: str = None,
        expected_chain_id: int = None,
        actual_chain_id: int = None,
    ):
        super().__init__(message)
        self.chain = chain
        self.expected_chain_id = expected_chain_id
        self.actual_chain_id = actual_chain_id


class ContractCodeNotFoundError(ChainConfigurationError):
    """The RPC in use has no contract code at the contract address (#230).

    Raised by the contract version check when a call returns an empty
    result and the address has no code on that RPC. The RPC may not be
    synced, so ChainClient tries the fallback RPCs first; when none has
    the code, the contract address or the chain is wrong. Nothing is
    cached and nothing is sent.
    """

    def __init__(self, message: str, contract_address: str = None):
        super().__init__(message)
        self.contract_address = contract_address


class ChainConnectionError(ChainError):
    """Failed to connect to RPC endpoint.

    ``rpc_url`` is the endpoint with only its scheme, host and port; the
    path, query and credentials are replaced (#169).
    """

    def __init__(self, message: str, rpc_url: str = None):
        super().__init__(message)
        self.rpc_url = redact_url(rpc_url)


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


class InsufficientFundsError(ChainTransactionError):
    """Wallet balance too low to cover gas for a chain transaction.

    Carries structured data so CLI can show actionable guidance
    (wallet address, balance, estimated cost, faucet/bridge link).
    """

    def __init__(
        self,
        message: str,
        wallet_address: str = None,
        balance_wei: int = None,
        estimated_cost_wei: int = None,
        chain_name: str = None,
        tx_hash: str = None,
    ):
        super().__init__(message, tx_hash=tx_hash)
        self.wallet_address = wallet_address
        self.balance_wei = balance_wei
        self.estimated_cost_wei = estimated_cost_wei
        self.chain_name = chain_name


class TransactionUnconfirmedError(ChainTransactionError):
    """Transaction was sent, but the write is not confirmed as recorded.

    Base class for TransactionNotRecordedError and TransactionNotVerifiedError
    (the transaction was mined with status 1),
    TransactionOutcomeUnknownError and its ReceiptTimeoutError subclass (it is
    not known whether it was mined), and TransactionReplacedError (another
    transaction with the same nonce was mined instead).
    Catch the subclass to decide whether a retry is safe.
    """

    def __init__(
        self,
        message: str,
        tx_hash: str = None,
        event_name: str = None,
        expected_count: int = None,
        contract_address: str = None,
        explorer_url: str = None,
    ):
        super().__init__(message, tx_hash=tx_hash)
        self.event_name = event_name
        self.expected_count = expected_count
        self.contract_address = contract_address
        self.explorer_url = explorer_url


class TransactionNotRecordedError(TransactionUnconfirmedError):
    """Transaction succeeded, but the contract did not emit the expected events.

    The write did not happen as asked: for example, the configured address has
    no contract, or a batch recorded fewer items than were sent.
    ``expected_count`` and ``emitted_count`` are always ints.

    Retry: safe for the items that were not recorded, after fixing the cause
    (contract address, chain). The transaction itself cost gas.
    """

    def __init__(
        self,
        message: str,
        tx_hash: str = None,
        event_name: str = None,
        expected_count: int = 0,
        emitted_count: int = 0,
        contract_address: str = None,
        explorer_url: str = None,
    ):
        super().__init__(
            message,
            tx_hash=tx_hash,
            event_name=event_name,
            expected_count=expected_count,
            contract_address=contract_address,
            explorer_url=explorer_url,
        )
        self.emitted_count = emitted_count


class TransactionNotVerifiedError(TransactionUnconfirmedError):
    """Transaction was mined, but its events could not be decoded.

    It is not known whether the write was recorded. ``reason`` is the decode
    error.

    Retry: NOT safe without checking first. The write may have happened, so
    sending it again may record it twice. Check the transaction in the block
    explorer, or read the record back, before you send it again.
    """

    def __init__(
        self,
        message: str,
        tx_hash: str = None,
        event_name: str = None,
        expected_count: int = None,
        contract_address: str = None,
        explorer_url: str = None,
        reason: str = None,
    ):
        super().__init__(
            message,
            tx_hash=tx_hash,
            event_name=event_name,
            expected_count=expected_count,
            contract_address=contract_address,
            explorer_url=explorer_url,
        )
        self.reason = redact_urls(reason)


class TransactionOutcomeUnknownError(TransactionUnconfirmedError):
    """The connection to the RPC failed after the transaction was sent.

    The transaction may have been broadcast, and may be mined later, so it is
    not known whether the write happened. ``tx_hash`` is the hash of the
    signed transaction. ``reason`` is the transport error.

    Retry: NOT safe without checking first. Look up ``tx_hash`` in the block
    explorer, or read the record back, before you send it again.
    """

    def __init__(
        self,
        message: str,
        tx_hash: str = None,
        event_name: str = None,
        expected_count: int = None,
        contract_address: str = None,
        explorer_url: str = None,
        reason: str = None,
    ):
        super().__init__(
            message,
            tx_hash=tx_hash,
            event_name=event_name,
            expected_count=expected_count,
            contract_address=contract_address,
            explorer_url=explorer_url,
        )
        self.reason = redact_urls(reason)


class ReceiptTimeoutError(TransactionOutcomeUnknownError):
    """No receipt arrived for a sent transaction within ``timeout`` seconds (#167).

    The transaction may still be mined, so the write may still happen.
    ``timeout`` is the wait in seconds. ``reason`` is web3's timeout message.

    Retry: NOT safe. Wait for the transaction with
    ``ChainClient.wait_for_transaction(tx_hash, event_name, expected_count)``
    (CLI: ``chain wait <tx_hash> --event <event_name>``) instead of sending
    the write again.
    """

    def __init__(
        self,
        message: str,
        tx_hash: str = None,
        event_name: str = None,
        expected_count: int = None,
        contract_address: str = None,
        explorer_url: str = None,
        reason: str = None,
        timeout: float = None,
    ):
        super().__init__(
            message,
            tx_hash=tx_hash,
            event_name=event_name,
            expected_count=expected_count,
            contract_address=contract_address,
            explorer_url=explorer_url,
            reason=reason,
        )
        self.timeout = timeout


class TransactionReplacedError(TransactionUnconfirmedError):
    """Another transaction with the same nonce was mined instead (#167).

    The receipt wait timed out, the account's mined nonce is above the
    transaction's ``nonce``, and the transaction has no receipt, so it will
    never be mined. The replacement can be the same write, sent from
    elsewhere with the same key.

    Retry: NOT safe without checking first. Read the record back
    (CLI: ``chain get``) before you send the write again.
    """

    def __init__(
        self,
        message: str,
        tx_hash: str = None,
        event_name: str = None,
        expected_count: int = None,
        contract_address: str = None,
        explorer_url: str = None,
        nonce: int = None,
    ):
        super().__init__(
            message,
            tx_hash=tx_hash,
            event_name=event_name,
            expected_count=expected_count,
            contract_address=contract_address,
            explorer_url=explorer_url,
        )
        self.nonce = nonce


# Events of writes that create or change a data record, which `chain get`
# reads back. Other events (DelegateAuthorized) have no data record (#167).
DATA_RECORD_EVENTS = frozenset({
    "DataRegistered",
    "StorageRefLinked",
    "DataTransformed",
    "DataMerged",
    "DataAccessed",
    "DataStatusChanged",
    "DataOwnershipTransferred",
})


def replaced_check_kind(event_name: Optional[str]) -> str:
    """What to check before a replaced write is sent again, by its event (#167).

    The one place that decides it; the library message and the CLI text
    both use it. Returns "record" for a write with a data record (read it
    back with ``chain get``), "delegate" for a delegate write (no data
    record: check the delegate state or the transaction in the block
    explorer), and "unknown" without an event or for another event.
    """
    if event_name in DATA_RECORD_EVENTS:
        return "record"
    if event_name == "DelegateAuthorized":
        return "delegate"
    return "unknown"


def replaced_check_advice(event_name: Optional[str]) -> str:
    """The library wording of replaced_check_kind's advice."""
    kind = replaced_check_kind(event_name)
    if kind == "record":
        return "read the record back (chain get <data hash>)"
    if kind == "delegate":
        return (
            "check the delegate state (the contract's isAuthorizedDelegate) or the "
            "transaction in the block explorer"
        )
    return "check the transaction in the block explorer, or read the record back (chain get <data hash>)"


class TransactionNotFoundError(ChainTransactionError):
    """The RPC does not know the transaction, and no receipt arrived (#167).

    Raised by ChainClient.wait_for_transaction() for a hash that the RPC
    does not return after the wait. ``explorer_url`` is the explorer link
    for the hash, if the chain has an explorer.
    """

    def __init__(self, message: str, tx_hash: str = None, explorer_url: str = None):
        super().__init__(message, tx_hash=tx_hash)
        self.explorer_url = explorer_url


class TransformationAlreadyExistsError(ChainError):
    """Transformation (original -> new) pair is already recorded on-chain."""

    def __init__(
        self,
        message: str,
        original_hash: str = None,
        new_hash: str = None,
        existing_description: str = None,
    ):
        super().__init__(message)
        self.original_hash = original_hash
        self.new_hash = new_hash
        self.existing_description = existing_description


class RedactedException(Exception):
    """A redacted copy of an exception linked to a ChainError (#187).

    :func:`redact_exception_chain` puts it in place of a raw exception, such
    as a ``requests`` or web3 error, in a ChainError's ``__cause__`` or
    ``__context__``, because the raw text can repeat the RPC URL with its
    API key. The message is ``"<module>.<class>: <redacted text>"``, and
    ``__traceback__`` is the original's, so a printed traceback still shows
    where the error happened. ``original_type`` is the qualified class name.
    """

    def __init__(self, message: str, original_type: Optional[str] = None):
        super().__init__(message)
        self.original_type = original_type


def _redacted_copy(error: BaseException) -> RedactedException:
    cls = type(error)
    original_type = f"{cls.__module__}.{cls.__qualname__}"
    try:
        text = redact_urls(str(error))
    except Exception:  # an exception whose __str__ fails
        text = ""
    message = f"{original_type}: {text}" if text else original_type
    return RedactedException(message, original_type=original_type).with_traceback(
        error.__traceback__
    )


def redact_exception_chain(error: BaseException) -> BaseException:
    """
    Replace the raw exceptions linked to ``error`` with redacted copies.

    Walks ``__cause__`` and ``__context__``, also of the linked exceptions.
    Each linked exception that is not a ChainError is replaced by a
    :class:`RedactedException`; a ChainError is kept, because its message is
    redacted when it is created, and its own links are walked. The original
    exceptions are not changed. ``__suppress_context__`` keeps its value, so
    ``traceback.format_exception()`` shows the same links as before. Safe to
    call more than once and on chains with cycles.

    Frame local variables of the kept tracebacks are not changed: a tool
    that prints them (``TracebackException(capture_locals=True)``, a
    debugger) can still show the RPC URL.

    Args:
        error: The exception to clean, usually a ChainError.

    Returns:
        ``error`` itself.
    """
    replaced = {}

    def visit(exc):
        if exc is None:
            return None
        if id(exc) in replaced:
            return replaced[id(exc)]
        if isinstance(exc, (ChainError, RedactedException)) or exc is error:
            result = exc
        else:
            result = _redacted_copy(exc)
        replaced[id(exc)] = result
        # Assigning __cause__ sets __suppress_context__: restore it after
        suppress = exc.__suppress_context__
        cause, context = visit(exc.__cause__), visit(exc.__context__)
        if result.__cause__ is not cause:
            result.__cause__ = cause
        if result.__context__ is not context:
            result.__context__ = context
        result.__suppress_context__ = suppress
        return result

    visit(error)
    return error
