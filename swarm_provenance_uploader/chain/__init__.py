"""Chain subpackage for blockchain integration with DataProvenance contract."""

try:
    from .provider import ChainProvider
    from .contract import DataProvenanceContract
    from .wallet import ChainWallet

    BLOCKCHAIN_AVAILABLE = True
    __all__ = ["ChainProvider", "DataProvenanceContract", "ChainWallet", "BLOCKCHAIN_AVAILABLE"]
except ImportError:
    BLOCKCHAIN_AVAILABLE = False
    __all__ = ["BLOCKCHAIN_AVAILABLE"]
