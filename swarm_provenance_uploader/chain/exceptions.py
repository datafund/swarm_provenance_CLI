"""Custom exceptions for blockchain-related operations.

Standalone exception hierarchy for the chain module. These inherit from
the main ProvenanceError base to keep a unified exception tree while
allowing the chain module to be self-contained.
"""

from ..exceptions import ProvenanceError


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
    """Transaction was mined (status 1), but the write is not confirmed as recorded.

    Base class for TransactionNotRecordedError and TransactionNotVerifiedError.
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
        self.reason = reason


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
