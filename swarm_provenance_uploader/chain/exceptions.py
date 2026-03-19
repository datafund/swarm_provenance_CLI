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
