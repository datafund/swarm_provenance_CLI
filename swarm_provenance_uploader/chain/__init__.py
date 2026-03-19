"""Chain subpackage for blockchain integration with DataProvenance contract."""

try:
    from .provider import ChainProvider
    from .contract import DataProvenanceContract
    from .wallet import ChainWallet
    from .event_cache import TransformationEventCache, get_cache, clear_registry
    from .exceptions import (
        ChainError,
        ChainConfigurationError,
        ChainConnectionError,
        ChainTransactionError,
        ChainValidationError,
        DataNotRegisteredError,
        DataAlreadyRegisteredError,
        TransformationAlreadyExistsError,
    )

    BLOCKCHAIN_AVAILABLE = True
    __all__ = [
        "ChainProvider",
        "DataProvenanceContract",
        "ChainWallet",
        "TransformationEventCache",
        "get_cache",
        "clear_registry",
        "ChainError",
        "ChainConfigurationError",
        "ChainConnectionError",
        "ChainTransactionError",
        "ChainValidationError",
        "DataNotRegisteredError",
        "DataAlreadyRegisteredError",
        "TransformationAlreadyExistsError",
        "BLOCKCHAIN_AVAILABLE",
    ]
except ImportError:
    BLOCKCHAIN_AVAILABLE = False
    __all__ = ["BLOCKCHAIN_AVAILABLE"]
