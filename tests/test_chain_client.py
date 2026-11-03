"""Tests for the chain client module and chain subpackage."""

import json
import os
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from swarm_provenance_uploader.exceptions import (
    ChainConfigurationError,
    ChainConnectionError,
    ChainTransactionError,
    ChainValidationError,
    InsufficientFundsError,
    DataAlreadyRegisteredError,
    DataNotRegisteredError,
    TransformationAlreadyExistsError,
)
from swarm_provenance_uploader.models import (
    AnchorResult,
    AccessResult,
    ChainProvenanceRecord,
    ChainWalletInfo,
    DataStatusEnum,
    MergeTransformResult,
    TransformResult,
)


# Test constants
DUMMY_PRIVATE_KEY = "0x" + "a" * 64
DUMMY_ADDRESS = "0x742d35Cc6634C0532925a3b844Bc9e7595f8fE00"
DUMMY_HASH = "a" * 64
DUMMY_HASH_BYTES = bytes.fromhex(DUMMY_HASH)
DUMMY_CONTRACT = "0x3945aDfd5Df9ab2F5cB4Ca0eb3D4384CC3650322"
DUMMY_TX_HASH_BYTES = bytes.fromhex("bb" * 32)
ZERO_ADDRESS = "0x" + "0" * 40
OTHER_ADDRESS = "0x" + "1" * 40
DUMMY_CODE = bytes.fromhex("6080604052")

# Events each write expects (from chain/abi/DataProvenance.json)
WRITE_EVENTS = [
    "DataRegistered",
    "StorageRefLinked",
    "DataTransformed",
    "DataMerged",
    "DataAccessed",
    "DataStatusChanged",
    "DataOwnershipTransferred",
    "DelegateAuthorized",
]


def _log(event, address=DUMMY_CONTRACT):
    """A receipt log entry, already decoded, for the process_receipt mock."""
    return {"event": event, "address": address}


def _process_receipt_mock(event_name):
    """Stand-in for web3 process_receipt: decodes by event, not by address."""
    def process_receipt(receipt, errors=None):
        return tuple(
            log for log in receipt.get("logs", []) if log["event"] == event_name
        )
    return process_receipt


@pytest.fixture
def mock_chain_deps():
    """Mock web3 and eth-account dependencies for chain tests."""
    with patch.dict(os.environ, {"PROVENANCE_WALLET_KEY": DUMMY_PRIVATE_KEY}):
        # Mock eth_account
        mock_account = MagicMock()
        mock_account.address = DUMMY_ADDRESS
        mock_account.sign_transaction.return_value = MagicMock(
            raw_transaction=b"\x00" * 32
        )

        mock_account_class = MagicMock()
        mock_account_class.from_key.return_value = mock_account

        # Mock web3 instance
        mock_web3_instance = MagicMock()
        mock_web3_instance.to_checksum_address = lambda x: x
        mock_web3_instance.eth.chain_id = 84532
        mock_web3_instance.eth.block_number = 12345678
        mock_web3_instance.eth.get_balance.return_value = 1_000_000_000_000_000_000  # 1 ETH
        mock_web3_instance.eth.gas_price = 1_000_000_000  # 1 gwei
        mock_web3_instance.eth.get_transaction_count.return_value = 0
        mock_web3_instance.eth.estimate_gas.return_value = 100_000
        mock_web3_instance.eth.send_raw_transaction.return_value = DUMMY_TX_HASH_BYTES
        mock_web3_instance.eth.wait_for_transaction_receipt.return_value = {
            "status": 1,
            "transactionHash": DUMMY_TX_HASH_BYTES,
            "blockNumber": 12345679,
            "gasUsed": 95_000,
            # One event of each kind from the contract: enough for single writes
            "logs": [_log(name) for name in WRITE_EVENTS],
        }
        mock_web3_instance.eth.get_code.return_value = DUMMY_CODE
        mock_web3_instance.is_connected.return_value = True

        # Mock contract
        mock_contract = MagicMock()
        mock_web3_instance.eth.contract.return_value = mock_contract
        for name in WRITE_EVENTS:
            getattr(mock_contract.events, name).return_value.process_receipt.side_effect = (
                _process_receipt_mock(name)
            )

        # Mock build_transaction for all contract functions
        mock_contract.functions.registerData.return_value.build_transaction.return_value = {
            "from": DUMMY_ADDRESS,
            "to": DUMMY_CONTRACT,
            "data": "0x",
        }
        mock_contract.functions.registerDataFor.return_value.build_transaction.return_value = {
            "from": DUMMY_ADDRESS,
            "to": DUMMY_CONTRACT,
            "data": "0x",
        }
        mock_contract.functions.batchRegisterData.return_value.build_transaction.return_value = {
            "from": DUMMY_ADDRESS,
            "to": DUMMY_CONTRACT,
            "data": "0x",
        }
        mock_contract.functions.recordTransformation.return_value.build_transaction.return_value = {
            "from": DUMMY_ADDRESS,
            "to": DUMMY_CONTRACT,
            "data": "0x",
        }
        mock_contract.functions.recordAccess.return_value.build_transaction.return_value = {
            "from": DUMMY_ADDRESS,
            "to": DUMMY_CONTRACT,
            "data": "0x",
        }
        mock_contract.functions.batchRecordAccess.return_value.build_transaction.return_value = {
            "from": DUMMY_ADDRESS,
            "to": DUMMY_CONTRACT,
            "data": "0x",
        }
        mock_contract.functions.setDataStatus.return_value.build_transaction.return_value = {
            "from": DUMMY_ADDRESS,
            "to": DUMMY_CONTRACT,
            "data": "0x",
        }
        mock_contract.functions.transferDataOwnership.return_value.build_transaction.return_value = {
            "from": DUMMY_ADDRESS,
            "to": DUMMY_CONTRACT,
            "data": "0x",
        }
        mock_contract.functions.setDelegate.return_value.build_transaction.return_value = {
            "from": DUMMY_ADDRESS,
            "to": DUMMY_CONTRACT,
            "data": "0x",
        }
        mock_contract.functions.batchSetDataStatus.return_value.build_transaction.return_value = {
            "from": DUMMY_ADDRESS,
            "to": DUMMY_CONTRACT,
            "data": "0x",
        }

        mock_contract.functions.setStorageRef.return_value.build_transaction.return_value = {
            "from": DUMMY_ADDRESS,
            "to": DUMMY_CONTRACT,
            "data": "0x",
        }

        # Mock read functions
        mock_contract.functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES,  # dataHash
            DUMMY_ADDRESS,     # owner
            1700000000,        # timestamp
            "swarm-provenance",  # dataType
            b"\x00" * 32,     # storageRef (not set)
            [],                # transformationLinks
            [],                # accessors
            0,                 # status (ACTIVE)
        )
        mock_contract.functions.getDataHashByStorageRef.return_value.call.return_value = b"\x00" * 32
        mock_contract.functions.getUserDataRecords.return_value.call.return_value = [
            DUMMY_HASH_BYTES,
        ]
        mock_contract.functions.getUserDataRecordsCount.return_value.call.return_value = 1
        mock_contract.functions.getUserDataRecordsPaginated.return_value.call.return_value = [
            DUMMY_HASH_BYTES,
        ]
        mock_contract.functions.hasAddressAccessed.return_value.call.return_value = True
        mock_contract.functions.isAuthorizedDelegate.return_value.call.return_value = False

        # Mock Web3 class
        mock_web3_class = MagicMock(return_value=mock_web3_instance)
        mock_web3_class.HTTPProvider = MagicMock()
        mock_web3_class.from_wei = lambda val, unit: str(val / 10**18)

        with patch.dict(
            "sys.modules",
            {
                "eth_account": MagicMock(Account=mock_account_class),
                "web3": MagicMock(Web3=mock_web3_class),
                "web3.logs": MagicMock(DISCARD="discard"),
            },
        ):
            # Reset lazy import globals so they pick up the mocked modules
            import swarm_provenance_uploader.chain.provider as provider_module
            import swarm_provenance_uploader.chain.wallet as wallet_module
            provider_module._Web3 = None
            wallet_module._Account = None

            yield {
                "account": mock_account,
                "account_class": mock_account_class,
                "web3_instance": mock_web3_instance,
                "web3_class": mock_web3_class,
                "contract": mock_contract,
            }

            # Reset lazy import globals so real modules are re-imported next time
            provider_module._Web3 = None
            wallet_module._Account = None


# --- Contract validation tests ---

class TestContractValidation:
    """Tests for contract-level validation helpers."""

    def test_normalize_hash_valid_hex(self):
        """Tests normalizing a valid 64-char hex hash."""
        from swarm_provenance_uploader.chain.contract import _normalize_hash

        result = _normalize_hash(DUMMY_HASH)
        assert result == DUMMY_HASH_BYTES
        assert len(result) == 32

    def test_normalize_hash_with_0x_prefix(self):
        """Tests normalizing a hash with 0x prefix."""
        from swarm_provenance_uploader.chain.contract import _normalize_hash

        result = _normalize_hash("0x" + DUMMY_HASH)
        assert result == DUMMY_HASH_BYTES

    def test_normalize_hash_invalid_length(self):
        """Tests that short hash raises validation error."""
        from swarm_provenance_uploader.chain.contract import _normalize_hash

        with pytest.raises(ChainValidationError) as exc_info:
            _normalize_hash("abcdef")
        assert "64 hex characters" in str(exc_info.value)

    def test_normalize_hash_invalid_hex(self):
        """Tests that non-hex characters raise validation error."""
        from swarm_provenance_uploader.chain.contract import _normalize_hash

        with pytest.raises(ChainValidationError) as exc_info:
            _normalize_hash("g" * 64)
        assert "Invalid hex" in str(exc_info.value)

    def test_normalize_hash_raw_bytes(self):
        """Tests normalizing raw 32-byte input."""
        from swarm_provenance_uploader.chain.contract import _normalize_hash

        result = _normalize_hash(DUMMY_HASH_BYTES)
        assert result == DUMMY_HASH_BYTES

    def test_normalize_hash_wrong_bytes_length(self):
        """Tests that wrong byte length raises error."""
        from swarm_provenance_uploader.chain.contract import _normalize_hash

        with pytest.raises(ChainValidationError) as exc_info:
            _normalize_hash(b"\x00" * 16)
        assert "32 bytes" in str(exc_info.value)

    def test_validate_data_type_valid(self):
        """Tests valid data type string."""
        from swarm_provenance_uploader.chain.contract import _validate_data_type

        result = _validate_data_type("swarm-provenance")
        assert result == "swarm-provenance"

    def test_validate_data_type_too_long(self):
        """Tests that data type exceeding max length raises error."""
        from swarm_provenance_uploader.chain.contract import _validate_data_type

        with pytest.raises(ChainValidationError) as exc_info:
            _validate_data_type("x" * 65)
        assert "64" in str(exc_info.value)

    def test_validate_transformation_valid(self):
        """Tests valid transformation description."""
        from swarm_provenance_uploader.chain.contract import _validate_transformation

        result = _validate_transformation("Filtered and anonymized")
        assert result == "Filtered and anonymized"

    def test_validate_transformation_too_long(self):
        """Tests that transformation exceeding max length raises error."""
        from swarm_provenance_uploader.chain.contract import _validate_transformation

        with pytest.raises(ChainValidationError) as exc_info:
            _validate_transformation("x" * 257)
        assert "256" in str(exc_info.value)


class TestContractBatchValidation:
    """Tests for batch operation validation."""

    def test_batch_register_mismatched_lengths(self, mock_chain_deps):
        """Tests that mismatched array lengths raise error."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )

        with pytest.raises(ChainValidationError) as exc_info:
            contract.build_batch_register_data_tx(
                data_hashes=[DUMMY_HASH],
                data_types=["type1", "type2"],  # mismatched
                sender=DUMMY_ADDRESS,
            )
        assert "same length" in str(exc_info.value)

    def test_batch_register_exceeds_limit(self, mock_chain_deps):
        """Tests that exceeding batch limit raises error."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract, MAX_BATCH_REGISTER

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )

        with pytest.raises(ChainValidationError) as exc_info:
            contract.build_batch_register_data_tx(
                data_hashes=[DUMMY_HASH] * (MAX_BATCH_REGISTER + 1),
                data_types=["type"] * (MAX_BATCH_REGISTER + 1),
                sender=DUMMY_ADDRESS,
            )
        assert "maximum" in str(exc_info.value).lower()

    def test_batch_access_exceeds_limit(self, mock_chain_deps):
        """Tests that exceeding batch access limit raises error."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract, MAX_BATCH_ACCESS

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )

        with pytest.raises(ChainValidationError) as exc_info:
            contract.build_batch_record_access_tx(
                data_hashes=[DUMMY_HASH] * (MAX_BATCH_ACCESS + 1),
                sender=DUMMY_ADDRESS,
            )
        assert "maximum" in str(exc_info.value).lower()


class TestABILoading:
    """Tests for ABI file loading."""

    def test_load_abi_success(self):
        """Tests that the bundled ABI loads correctly."""
        from swarm_provenance_uploader.chain.contract import _load_abi

        abi = _load_abi()
        assert isinstance(abi, list)
        assert len(abi) > 0

        # Should contain registerData function
        func_names = [e["name"] for e in abi if e.get("type") == "function"]
        assert "registerData" in func_names
        assert "getDataRecord" in func_names
        assert "recordAccess" in func_names

    def test_load_abi_missing_file(self):
        """Tests that missing ABI file raises config error."""
        from swarm_provenance_uploader.chain.contract import _load_abi
        from pathlib import Path

        with patch.object(Path, "parent", new_callable=PropertyMock) as mock_parent:
            mock_parent.return_value = Path("/nonexistent")
            # Need to patch at the open level
            with patch("builtins.open", side_effect=FileNotFoundError("no such file")):
                with pytest.raises(ChainConfigurationError) as exc_info:
                    _load_abi()
                assert "Failed to load" in str(exc_info.value)


# --- Provider tests ---

class TestChainProvider:
    """Tests for ChainProvider initialization and methods."""

    def test_unsupported_chain_raises_error(self, mock_chain_deps):
        """Tests that unsupported chain name raises error."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        with pytest.raises(ChainConfigurationError) as exc_info:
            ChainProvider(chain="ethereum-mainnet")
        assert "Unsupported chain" in str(exc_info.value)

    def test_valid_init_base_sepolia(self, mock_chain_deps):
        """Tests successful initialization for base-sepolia."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia")

        assert provider.chain == "base-sepolia"
        assert provider.chain_id == 84532
        assert provider.contract_address == "0x3945aDfd5Df9ab2F5cB4Ca0eb3D4384CC3650322"

    def test_custom_rpc_url(self, mock_chain_deps):
        """Tests that custom RPC URL is used."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(
            chain="base-sepolia",
            rpc_url="https://custom.rpc.io",
        )
        assert provider.rpc_url == "https://custom.rpc.io"

    def test_custom_contract_address(self, mock_chain_deps):
        """Tests that custom contract address is used."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        custom_addr = "0x1234567890abcdef1234567890abcdef12345678"
        provider = ChainProvider(
            chain="base-sepolia",
            contract_address=custom_addr,
        )
        assert provider.contract_address == custom_addr

    def test_custom_explorer_url(self, mock_chain_deps):
        """Tests that custom explorer URL overrides the preset."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(
            chain="base-sepolia",
            explorer_url="https://custom-explorer.io",
        )
        assert provider.explorer_url == "https://custom-explorer.io"

    def test_default_explorer_url(self, mock_chain_deps):
        """Tests that preset explorer URL is used when no override given."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia")
        assert provider.explorer_url == "https://base-sepolia.blockscout.com"

    def test_custom_explorer_url_in_tx_url(self, mock_chain_deps):
        """Tests that custom explorer URL is used in generated TX URLs."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(
            chain="base-sepolia",
            explorer_url="https://custom-explorer.io",
        )
        url = provider.get_explorer_tx_url("0xabc123")
        assert url == "https://custom-explorer.io/tx/0xabc123"

    def test_base_mainnet_no_contract_raises_error(self, mock_chain_deps):
        """Tests that base mainnet without contract raises error."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        with pytest.raises(ChainConfigurationError) as exc_info:
            ChainProvider(chain="base")
        assert "No contract address" in str(exc_info.value)

    def test_health_check_success(self, mock_chain_deps):
        """Tests successful health check."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia")
        assert provider.health_check() is True

    def test_health_check_not_connected(self, mock_chain_deps):
        """Tests health check when not connected."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        mock_chain_deps["web3_instance"].is_connected.return_value = False
        provider = ChainProvider(chain="base-sepolia")

        with pytest.raises(ChainConnectionError) as exc_info:
            provider.health_check()
        assert "Cannot connect" in str(exc_info.value)

    def test_health_check_chain_id_mismatch(self, mock_chain_deps):
        """Tests health check with wrong chain ID."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        from swarm_provenance_uploader.chain.exceptions import ChainIdMismatchError

        mock_chain_deps["web3_instance"].eth.chain_id = 9999
        provider = ChainProvider(chain="base-sepolia")

        # A wrong-chain RPC is a configuration error, as in reads and writes (#168 review)
        with pytest.raises(ChainIdMismatchError) as exc_info:
            provider.health_check()
        assert "Chain ID mismatch" in str(exc_info.value)

    def test_get_block_number(self, mock_chain_deps):
        """Tests getting block number."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia")
        assert provider.get_block_number() == 12345678

    def test_explorer_tx_url(self, mock_chain_deps):
        """Tests generating transaction explorer URL."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia")
        url = provider.get_explorer_tx_url("0xabc123")
        assert url == "https://base-sepolia.blockscout.com/tx/0xabc123"

    def test_explorer_tx_url_without_prefix(self, mock_chain_deps):
        """Tests explorer URL auto-adds 0x prefix."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia")
        url = provider.get_explorer_tx_url("abc123")
        assert url == "https://base-sepolia.blockscout.com/tx/0xabc123"

    def test_explorer_address_url(self, mock_chain_deps):
        """Tests generating address explorer URL."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia")
        url = provider.get_explorer_address_url(DUMMY_ADDRESS)
        assert "base-sepolia.blockscout.com/address/" in url


# --- Wallet tests ---

class TestChainWallet:
    """Tests for ChainWallet initialization and methods."""

    def test_missing_key_raises_error(self, mock_chain_deps):
        """Tests that missing private key raises error."""
        with patch.dict(os.environ, {}, clear=True):
            from swarm_provenance_uploader.chain.wallet import ChainWallet

            with pytest.raises(ChainConfigurationError) as exc_info:
                ChainWallet()
            assert "No wallet private key" in str(exc_info.value)

    def test_valid_init_with_env_key(self, mock_chain_deps):
        """Tests successful init from environment variable."""
        from swarm_provenance_uploader.chain.wallet import ChainWallet

        wallet = ChainWallet()
        assert wallet.address == DUMMY_ADDRESS

    def test_valid_init_with_direct_key(self, mock_chain_deps):
        """Tests successful init with direct private key."""
        from swarm_provenance_uploader.chain.wallet import ChainWallet

        wallet = ChainWallet(private_key=DUMMY_PRIVATE_KEY)
        assert wallet.address == DUMMY_ADDRESS

    def test_key_without_0x_prefix(self, mock_chain_deps):
        """Tests that key without 0x prefix gets normalized."""
        from swarm_provenance_uploader.chain.wallet import ChainWallet

        wallet = ChainWallet(private_key="a" * 64)
        assert wallet._private_key == DUMMY_PRIVATE_KEY

    def test_sign_transaction(self, mock_chain_deps):
        """Tests transaction signing."""
        from swarm_provenance_uploader.chain.wallet import ChainWallet

        wallet = ChainWallet()
        raw = wallet.sign_transaction({"to": DUMMY_CONTRACT, "value": 0})
        assert isinstance(raw, bytes)

    def test_get_balance(self, mock_chain_deps):
        """Tests balance retrieval."""
        from swarm_provenance_uploader.chain.wallet import ChainWallet

        wallet = ChainWallet()
        balance = wallet.get_balance(mock_chain_deps["web3_instance"])
        assert balance == 1_000_000_000_000_000_000


# --- ChainClient tests ---

class TestChainClientInit:
    """Tests for ChainClient initialization."""

    def test_valid_init(self, mock_chain_deps):
        """Tests successful initialization."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")

        assert client.address == DUMMY_ADDRESS
        assert client.chain == "base-sepolia"
        assert client.contract_address == DUMMY_CONTRACT

    def test_explorer_url_passthrough(self, mock_chain_deps):
        """Tests that explorer_url is passed through to ChainProvider."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Pre-check expects unregistered hash
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        client = ChainClient(
            chain="base-sepolia",
            explorer_url="https://custom-explorer.io",
        )
        assert client._provider.explorer_url == "https://custom-explorer.io"

        # Verify explorer URL is used in anchor results
        result = client.anchor(swarm_hash=DUMMY_HASH)
        assert "custom-explorer.io" in result.explorer_url

    def test_missing_deps_shows_helpful_message(self):
        """Tests that missing blockchain deps give clear error."""
        with patch.dict(os.environ, {"PROVENANCE_WALLET_KEY": DUMMY_PRIVATE_KEY}):
            with patch.dict("sys.modules", {"web3": None}):
                import swarm_provenance_uploader.chain.provider as pmod
                pmod._Web3 = None

                with pytest.raises((ChainConfigurationError, ImportError)):
                    from swarm_provenance_uploader.core.chain_client import ChainClient
                    ChainClient()


class TestChainClientAnchor:
    """Tests for anchor (register data) operations."""

    def test_anchor_success(self, mock_chain_deps):
        """Tests successful data anchoring."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Pre-check expects unregistered hash (zero-address owner)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        client = ChainClient(chain="base-sepolia")
        result = client.anchor(swarm_hash=DUMMY_HASH, data_type="test-data")

        assert isinstance(result, AnchorResult)
        assert result.swarm_hash == DUMMY_HASH
        assert result.data_type == "test-data"
        assert result.owner == DUMMY_ADDRESS
        assert result.block_number == 12345679
        assert result.gas_used == 95_000
        assert "base-sepolia.blockscout.com" in result.explorer_url

    def test_anchor_default_data_type(self, mock_chain_deps):
        """Tests anchor uses default data type."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Pre-check expects unregistered hash
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        client = ChainClient(chain="base-sepolia")
        result = client.anchor(swarm_hash=DUMMY_HASH)

        assert result.data_type == "swarm-provenance"

    def test_anchor_for_success(self, mock_chain_deps):
        """Tests anchoring on behalf of another owner."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Pre-check expects unregistered hash
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        other_owner = "0x1111111111111111111111111111111111111111"
        client = ChainClient(chain="base-sepolia")
        result = client.anchor_for(
            swarm_hash=DUMMY_HASH,
            owner=other_owner,
        )

        assert isinstance(result, AnchorResult)
        assert result.owner == other_owner

    def test_batch_anchor_success(self, mock_chain_deps):
        """Tests batch anchoring."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        hash2 = "b" * 64
        receipt = mock_chain_deps["web3_instance"].eth.wait_for_transaction_receipt.return_value
        receipt["logs"] = [_log("DataRegistered"), _log("DataRegistered")]
        client = ChainClient(chain="base-sepolia")
        result = client.batch_anchor(
            swarm_hashes=[DUMMY_HASH, hash2],
            data_types=["type1", "type2"],
        )

        assert isinstance(result, AnchorResult)
        assert result.swarm_hash == DUMMY_HASH

    def test_anchor_with_storage_ref(self, mock_chain_deps):
        """Tests anchoring with a storage reference."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Pre-check expects unregistered hash
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        storage_ref = "cc" * 32
        client = ChainClient(chain="base-sepolia")
        result = client.anchor(swarm_hash=DUMMY_HASH, storage_ref=storage_ref)

        assert isinstance(result, AnchorResult)
        assert result.storage_ref == storage_ref
        assert result.swarm_hash == DUMMY_HASH

    def test_anchor_without_storage_ref(self, mock_chain_deps):
        """Tests that anchor without storage_ref returns None for that field."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Pre-check expects unregistered hash
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        client = ChainClient(chain="base-sepolia")
        result = client.anchor(swarm_hash=DUMMY_HASH)

        assert result.storage_ref is None

    def test_anchor_invalid_hash(self, mock_chain_deps):
        """Tests that invalid hash raises validation error."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(ChainValidationError):
            client.anchor(swarm_hash="tooshort")


class TestChainClientStorageRef:
    """Tests for storage reference operations."""

    def test_set_storage_ref_success(self, mock_chain_deps):
        """Tests setting a storage reference on an existing record."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        storage_ref = "dd" * 32
        client = ChainClient(chain="base-sepolia")
        result = client.set_storage_ref(data_hash=DUMMY_HASH, storage_ref=storage_ref)

        assert isinstance(result, AnchorResult)
        assert result.storage_ref == storage_ref
        assert result.swarm_hash == DUMMY_HASH

    def test_get_by_storage_ref_success(self, mock_chain_deps):
        """Tests looking up a record by storage reference."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        storage_ref = "ee" * 32
        # Reverse lookup returns data hash
        mock_chain_deps["contract"].functions.getDataHashByStorageRef.return_value.call.return_value = DUMMY_HASH_BYTES

        # getDataRecord returns record with the storage ref
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, DUMMY_ADDRESS, 1700000000, "swarm-provenance",
            bytes.fromhex(storage_ref), [], [], 0,
        )

        client = ChainClient(chain="base-sepolia")
        record = client.get_by_storage_ref(storage_ref)

        assert isinstance(record, ChainProvenanceRecord)
        assert record.data_hash == DUMMY_HASH
        assert record.storage_ref == storage_ref

    def test_get_by_storage_ref_not_found(self, mock_chain_deps):
        """Tests that unknown storage ref raises DataNotRegisteredError."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Reverse lookup returns zero hash (not found)
        mock_chain_deps["contract"].functions.getDataHashByStorageRef.return_value.call.return_value = b"\x00" * 32

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(DataNotRegisteredError):
            client.get_by_storage_ref("ff" * 32)


class TestChainClientAlreadyRegistered:
    """Tests for already-registered hash pre-check in anchor/anchor_for."""

    def test_anchor_raises_already_registered(self, mock_chain_deps):
        """Tests that anchoring an already-registered hash raises DataAlreadyRegisteredError."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Default mock returns a registered record (owner=DUMMY_ADDRESS)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, DUMMY_ADDRESS, 1700000000, "swarm-provenance", b"\x00" * 32, [], [], 0,
        )

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(DataAlreadyRegisteredError) as exc_info:
            client.anchor(swarm_hash=DUMMY_HASH)
        assert exc_info.value.data_hash == DUMMY_HASH
        assert exc_info.value.owner == DUMMY_ADDRESS
        assert exc_info.value.timestamp == 1700000000
        assert exc_info.value.data_type == "swarm-provenance"

    def test_anchor_for_raises_already_registered(self, mock_chain_deps):
        """Tests that anchor_for on already-registered hash raises DataAlreadyRegisteredError."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, DUMMY_ADDRESS, 1700000000, "swarm-provenance", b"\x00" * 32, [], [], 0,
        )

        other_owner = "0x1111111111111111111111111111111111111111"
        client = ChainClient(chain="base-sepolia")
        with pytest.raises(DataAlreadyRegisteredError) as exc_info:
            client.anchor_for(swarm_hash=DUMMY_HASH, owner=other_owner)
        assert exc_info.value.data_hash == DUMMY_HASH

    def test_anchor_succeeds_when_not_registered(self, mock_chain_deps):
        """Tests that anchor succeeds when hash is not yet registered."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Return zero-address owner = not registered
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        client = ChainClient(chain="base-sepolia")
        result = client.anchor(swarm_hash=DUMMY_HASH)
        assert isinstance(result, AnchorResult)
        assert result.swarm_hash == DUMMY_HASH


class TestChainClientTransform:
    """Tests for transform operations."""

    def test_transform_success(self, mock_chain_deps):
        """Tests successful transformation recording."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        new_hash = "b" * 64
        client = ChainClient(chain="base-sepolia")
        result = client.transform(
            original_hash=DUMMY_HASH,
            new_hash=new_hash,
            description="Filtered PII",
        )

        assert isinstance(result, TransformResult)
        assert result.original_hash == DUMMY_HASH
        assert result.new_hash == new_hash
        assert result.description == "Filtered PII"


class TestChainClientAccess:
    """Tests for access recording operations."""

    def test_access_success(self, mock_chain_deps):
        """Tests successful access recording."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")
        result = client.access(swarm_hash=DUMMY_HASH)

        assert isinstance(result, AccessResult)
        assert result.swarm_hash == DUMMY_HASH
        assert result.accessor == DUMMY_ADDRESS

    def test_batch_access_success(self, mock_chain_deps):
        """Tests batch access recording."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        hash2 = "b" * 64
        receipt = mock_chain_deps["web3_instance"].eth.wait_for_transaction_receipt.return_value
        receipt["logs"] = [_log("DataAccessed"), _log("DataAccessed")]
        client = ChainClient(chain="base-sepolia")
        result = client.batch_access(swarm_hashes=[DUMMY_HASH, hash2])

        assert isinstance(result, AccessResult)
        assert result.swarm_hash == DUMMY_HASH


class TestChainClientStatus:
    """Tests for status and ownership operations."""

    def test_set_status_success(self, mock_chain_deps):
        """Tests setting data status."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")
        result = client.set_status(swarm_hash=DUMMY_HASH, status=1)  # RESTRICTED

        assert isinstance(result, AnchorResult)
        assert result.swarm_hash == DUMMY_HASH

    def test_transfer_ownership_success(self, mock_chain_deps):
        """Tests transferring data ownership."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        new_owner = "0x1111111111111111111111111111111111111111"
        client = ChainClient(chain="base-sepolia")
        result = client.transfer_ownership(
            swarm_hash=DUMMY_HASH,
            new_owner=new_owner,
        )

        assert isinstance(result, AnchorResult)
        assert result.owner == new_owner

    def test_set_delegate_success(self, mock_chain_deps):
        """Tests authorizing a delegate."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        delegate = "0x2222222222222222222222222222222222222222"
        client = ChainClient(chain="base-sepolia")
        result = client.set_delegate(delegate=delegate, authorized=True)

        assert isinstance(result, AnchorResult)


class TestChainClientRead:
    """Tests for read operations."""

    def test_get_record_success(self, mock_chain_deps):
        """Tests getting an on-chain record."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")
        record = client.get(swarm_hash=DUMMY_HASH)

        assert isinstance(record, ChainProvenanceRecord)
        assert record.owner == DUMMY_ADDRESS
        assert record.data_type == "swarm-provenance"
        assert record.status == DataStatusEnum.ACTIVE

    def test_get_unregistered_hash_raises_error(self, mock_chain_deps):
        """Tests that unregistered hash raises DataNotRegisteredError."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Make the contract return zero address (not registered)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES,
            ZERO_ADDRESS,
            0,
            "",
            b"\x00" * 32,
            [],
            [],
            0,
        )

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(DataNotRegisteredError) as exc_info:
            client.get(swarm_hash=DUMMY_HASH)
        assert exc_info.value.data_hash == DUMMY_HASH

    def test_verify_registered(self, mock_chain_deps):
        """Tests verifying a registered hash."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")
        assert client.verify(swarm_hash=DUMMY_HASH) is True

    def test_verify_unregistered(self, mock_chain_deps):
        """Tests verifying an unregistered hash."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES,
            ZERO_ADDRESS,
            0,
            "",
            b"\x00" * 32,
            [],
            [],
            0,
        )

        client = ChainClient(chain="base-sepolia")
        assert client.verify(swarm_hash=DUMMY_HASH) is False

    def test_get_record_with_storage_ref(self, mock_chain_deps):
        """Tests that storage_ref is parsed from on-chain record."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        storage_ref = bytes.fromhex("bb" * 32)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES,
            DUMMY_ADDRESS,
            1700000000,
            "swarm-provenance",
            storage_ref,
            [],
            [],
            0,
        )

        client = ChainClient(chain="base-sepolia")
        record = client.get(swarm_hash=DUMMY_HASH)

        assert record.storage_ref == "bb" * 32

    def test_get_record_without_storage_ref(self, mock_chain_deps):
        """Tests that zero storage_ref is returned as None."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")
        record = client.get(swarm_hash=DUMMY_HASH)

        assert record.storage_ref is None

    def test_balance_info(self, mock_chain_deps):
        """Tests getting wallet balance info."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")
        info = client.balance()

        assert isinstance(info, ChainWalletInfo)
        assert info.address == DUMMY_ADDRESS
        assert info.balance_wei == 1_000_000_000_000_000_000
        assert info.chain == "base-sepolia"
        assert info.contract_address == DUMMY_CONTRACT

    def test_health_check(self, mock_chain_deps):
        """Tests chain health check via client."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")
        assert client.health_check() is True


class TestChainClientTransaction:
    """Tests for transaction sending edge cases."""

    def test_transaction_reverted(self, mock_chain_deps):
        """Tests that reverted transaction raises error."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Pre-check expects unregistered hash
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        # Make receipt indicate failure
        mock_chain_deps["web3_instance"].eth.wait_for_transaction_receipt.return_value = {
            "status": 0,
            "transactionHash": DUMMY_TX_HASH_BYTES,
            "blockNumber": 12345679,
            "gasUsed": 100_000,
        }

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(ChainTransactionError) as exc_info:
            client.anchor(swarm_hash=DUMMY_HASH)
        assert "reverted" in str(exc_info.value).lower()

    def test_gas_limit_multiplier(self, mock_chain_deps):
        """Tests that gas limit multiplier is applied."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Pre-check expects unregistered hash
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        client = ChainClient(chain="base-sepolia", gas_limit_multiplier=1.5)
        client.anchor(swarm_hash=DUMMY_HASH)

        # Verify gas was multiplied: 100000 * 1.5 = 150000
        # Check the tx dict that was passed to sign_transaction
        call_args = mock_chain_deps["account"].sign_transaction.call_args
        tx = call_args[0][0]
        assert tx["gas"] == 150_000


class TestChainClientGasLimit:
    """Tests for explicit gas limit support."""

    def test_explicit_gas_limit_skips_estimation(self, mock_chain_deps):
        """Tests that explicit gas limit skips estimate_gas call."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Pre-check expects unregistered hash
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        client = ChainClient(chain="base-sepolia", gas_limit=500_000)
        client.anchor(swarm_hash=DUMMY_HASH)

        # estimate_gas should NOT have been called
        mock_chain_deps["web3_instance"].eth.estimate_gas.assert_not_called()

        # tx should use explicit gas value
        call_args = mock_chain_deps["account"].sign_transaction.call_args
        tx = call_args[0][0]
        assert tx["gas"] == 500_000

    def test_explicit_gas_limit_no_multiplier(self, mock_chain_deps):
        """Tests that explicit gas limit ignores multiplier."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Pre-check expects unregistered hash
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        # Even with 2x multiplier, explicit value should be used as-is
        client = ChainClient(chain="base-sepolia", gas_limit=500_000, gas_limit_multiplier=2.0)
        client.anchor(swarm_hash=DUMMY_HASH)

        call_args = mock_chain_deps["account"].sign_transaction.call_args
        tx = call_args[0][0]
        assert tx["gas"] == 500_000

    def test_gas_limit_none_uses_estimation(self, mock_chain_deps):
        """Tests that gas_limit=None falls back to estimation."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Pre-check expects unregistered hash
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        client = ChainClient(chain="base-sepolia", gas_limit=None)
        client.anchor(swarm_hash=DUMMY_HASH)

        # estimate_gas should have been called
        mock_chain_deps["web3_instance"].eth.estimate_gas.assert_called_once()


class TestChainClientProvenanceChain:
    """Tests for provenance chain traversal."""

    def test_single_record_chain(self, mock_chain_deps):
        """Tests getting a chain with a single record."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")
        chain = client.get_provenance_chain(swarm_hash=DUMMY_HASH)

        assert len(chain) == 1
        assert chain[0].data_hash == DUMMY_HASH

    def test_unregistered_returns_empty(self, mock_chain_deps):
        """Tests that unregistered hash returns empty chain."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES,
            ZERO_ADDRESS,
            0,
            "",
            b"\x00" * 32,
            [],
            [],
            0,
        )

        client = ChainClient(chain="base-sepolia")
        chain = client.get_provenance_chain(swarm_hash=DUMMY_HASH)

        assert len(chain) == 0

    def test_chain_with_transformations(self, mock_chain_deps):
        """Tests chain returns record with transformation descriptions."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        hash_a = DUMMY_HASH
        hash_a_bytes = bytes.fromhex(hash_a)

        # Contract returns transformations as string[] (descriptions only)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            hash_a_bytes, DUMMY_ADDRESS, 1700000000, "swarm-provenance",
            b"\x00" * 32, ["filtered PII", "anonymized"],
            [], 0,
        )

        client = ChainClient(chain="base-sepolia")
        chain = client.get_provenance_chain(swarm_hash=hash_a)

        # Only the queried record is returned (no new_data_hash links to follow)
        assert len(chain) == 1
        assert chain[0].data_hash == hash_a
        assert len(chain[0].transformations) == 2
        assert chain[0].transformations[0].description == "filtered PII"
        assert chain[0].transformations[1].description == "anonymized"

    def test_get_provenance_chain_with_depth(self, mock_chain_deps):
        """Tests that max_depth=0 returns only the root record."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")

        # max_depth=0 should return only the root record
        chain = client.get_provenance_chain(swarm_hash=DUMMY_HASH, max_depth=0)

        assert len(chain) == 1
        assert chain[0].data_hash == DUMMY_HASH

    def test_get_provenance_chain_with_depth_zero(self, mock_chain_deps):
        """Tests that max_depth=0 returns only the root record."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        hash_a = DUMMY_HASH
        hash_a_bytes = bytes.fromhex(hash_a)

        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            hash_a_bytes, DUMMY_ADDRESS, 1700000000, "swarm-provenance",
            b"\x00" * 32, ["filtered"],
            [], 0,
        )

        client = ChainClient(chain="base-sepolia")
        chain = client.get_provenance_chain(swarm_hash=hash_a, max_depth=0)

        assert len(chain) == 1
        assert chain[0].data_hash == hash_a

    def test_get_provenance_chain_default_depth(self, mock_chain_deps):
        """Tests that max_depth=None uses the default depth (10, #170)."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        hash_a = DUMMY_HASH
        hash_a_bytes = bytes.fromhex(hash_a)

        # Single record with no transformations - just verify the call works
        # and that None defaults are handled
        def mock_get_data_record(data_hash):
            mock_call = MagicMock()
            if data_hash == hash_a_bytes:
                mock_call.call.return_value = (
                    hash_a_bytes, DUMMY_ADDRESS, 1700000000, "swarm-provenance",
                    b"\x00" * 32, [], [], 0,
                )
            else:
                mock_call.call.return_value = (
                    data_hash, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
                )
            return mock_call

        mock_chain_deps["contract"].functions.getDataRecord = mock_get_data_record

        client = ChainClient(chain="base-sepolia")

        # max_depth=None should use the default depth, not error
        chain = client.get_provenance_chain(swarm_hash=hash_a, max_depth=None)
        assert len(chain) == 1

    def test_get_provenance_chain_negative_depth(self, mock_chain_deps):
        """Tests that negative max_depth is rejected, not an empty chain (#170)."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        hash_a = DUMMY_HASH
        hash_a_bytes = bytes.fromhex(hash_a)

        def mock_get_data_record(data_hash):
            mock_call = MagicMock()
            mock_call.call.return_value = (
                hash_a_bytes, DUMMY_ADDRESS, 1700000000, "swarm-provenance",
                b"\x00" * 32, [], [], 0,
            )
            return mock_call

        mock_chain_deps["contract"].functions.getDataRecord = mock_get_data_record

        client = ChainClient(chain="base-sepolia")

        # A negative depth used to return [], which the CLI printed as
        # "not registered on-chain"
        with pytest.raises(ChainValidationError):
            client.get_provenance_chain(swarm_hash=hash_a, max_depth=-1)


# --- Models tests ---

class TestChainModels:
    """Tests for chain Pydantic models."""

    def test_data_status_enum_values(self):
        """Tests DataStatusEnum values."""
        assert DataStatusEnum.ACTIVE == 0
        assert DataStatusEnum.RESTRICTED == 1
        assert DataStatusEnum.DELETED == 2

    def test_anchor_result_serialization(self):
        """Tests AnchorResult model creation."""
        result = AnchorResult(
            tx_hash="0x" + "ab" * 32,
            block_number=100,
            gas_used=50000,
            explorer_url="https://example.com/tx/0xab",
            swarm_hash=DUMMY_HASH,
            data_type="test",
            owner=DUMMY_ADDRESS,
        )
        data = result.model_dump()
        assert data["tx_hash"] == "0x" + "ab" * 32
        assert data["block_number"] == 100

    def test_chain_provenance_record(self):
        """Tests ChainProvenanceRecord model."""
        record = ChainProvenanceRecord(
            data_hash=DUMMY_HASH,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
        )
        assert record.status == DataStatusEnum.ACTIVE
        assert record.accessors == []
        assert record.transformations == []

    def test_chain_wallet_info(self):
        """Tests ChainWalletInfo model."""
        info = ChainWalletInfo(
            address=DUMMY_ADDRESS,
            balance_wei=1000000000000000000,
            balance_eth="1.0",
            chain="base-sepolia",
            contract_address=DUMMY_CONTRACT,
        )
        assert info.balance_wei == 1000000000000000000


# --- Exceptions tests ---

class TestChainExceptions:
    """Tests for chain exception hierarchy."""

    def test_chain_error_is_provenance_error(self):
        """Tests that ChainError inherits from ProvenanceError."""
        from swarm_provenance_uploader.exceptions import ProvenanceError

        with pytest.raises(ProvenanceError):
            raise ChainConfigurationError("test")

    def test_chain_connection_error_stores_rpc_url(self):
        """Tests that ChainConnectionError stores rpc_url."""
        err = ChainConnectionError("failed", rpc_url="https://rpc.example.com")
        assert err.rpc_url == "https://rpc.example.com"

    def test_chain_transaction_error_stores_tx_hash(self):
        """Tests that ChainTransactionError stores tx_hash."""
        err = ChainTransactionError("reverted", tx_hash="0xabc")
        assert err.tx_hash == "0xabc"

    def test_data_not_registered_error_stores_hash(self):
        """Tests that DataNotRegisteredError stores data_hash."""
        err = DataNotRegisteredError("not found", data_hash=DUMMY_HASH)
        assert err.data_hash == DUMMY_HASH


# --- Transformation parsing tests ---

class TestTransformationParsing:
    """Tests for correct parsing of TransformationRecord structs from getDataRecord."""

    def test_get_with_transformations(self, mock_chain_deps):
        """Tests that transformations are parsed as (bytes32, string) tuples."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        new_hash_bytes = bytes.fromhex("bb" * 32)
        # Contract returns transformations as string[] (descriptions only)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES,
            DUMMY_ADDRESS,
            1700000000,
            "swarm-provenance",
            b"\x00" * 32,
            ["encrypted: AES-256-GCM"],
            [DUMMY_ADDRESS],
            0,
        )

        client = ChainClient(chain="base-sepolia")
        record = client.get(swarm_hash=DUMMY_HASH)

        assert len(record.transformations) == 1
        assert record.transformations[0].new_data_hash is None
        assert record.transformations[0].description == "encrypted: AES-256-GCM"

    def test_get_with_multiple_transformations(self, mock_chain_deps):
        """Tests parsing multiple transformation records."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES,
            DUMMY_ADDRESS,
            1700000000,
            "swarm-provenance",
            b"\x00" * 32,
            ["filtered PII", "anonymized"],
            [],
            0,
        )

        client = ChainClient(chain="base-sepolia")
        record = client.get(swarm_hash=DUMMY_HASH)

        assert len(record.transformations) == 2
        assert record.transformations[0].description == "filtered PII"
        assert record.transformations[1].description == "anonymized"

    def test_get_with_accessors(self, mock_chain_deps):
        """Tests that accessors list is parsed correctly."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        accessor_addr = "0x1111111111111111111111111111111111111111"
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES,
            DUMMY_ADDRESS,
            1700000000,
            "swarm-provenance",
            b"\x00" * 32,
            [],
            [DUMMY_ADDRESS, accessor_addr],
            0,
        )

        client = ChainClient(chain="base-sepolia")
        record = client.get(swarm_hash=DUMMY_HASH)

        assert len(record.accessors) == 2
        assert accessor_addr in record.accessors


# --- Batch status tests ---

class TestBatchSetDataStatus:
    """Tests for batch set data status operations."""

    def test_batch_set_status_mismatched_lengths(self, mock_chain_deps):
        """Tests that mismatched array lengths raise error."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )

        with pytest.raises(ChainValidationError) as exc_info:
            contract.build_batch_set_data_status_tx(
                data_hashes=[DUMMY_HASH],
                statuses=[0, 1],  # mismatched
                sender=DUMMY_ADDRESS,
            )
        assert "same length" in str(exc_info.value)

    def test_batch_set_status_exceeds_limit(self, mock_chain_deps):
        """Tests that exceeding batch limit raises error."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract, MAX_BATCH_REGISTER

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )

        with pytest.raises(ChainValidationError) as exc_info:
            contract.build_batch_set_data_status_tx(
                data_hashes=[DUMMY_HASH] * (MAX_BATCH_REGISTER + 1),
                statuses=[0] * (MAX_BATCH_REGISTER + 1),
                sender=DUMMY_ADDRESS,
            )
        assert "maximum" in str(exc_info.value).lower()

    def test_batch_set_status_client_success(self, mock_chain_deps):
        """Tests batch_set_status through ChainClient."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        hash2 = "b" * 64
        receipt = mock_chain_deps["web3_instance"].eth.wait_for_transaction_receipt.return_value
        receipt["logs"] = [_log("DataStatusChanged"), _log("DataStatusChanged")]
        client = ChainClient(chain="base-sepolia")
        result = client.batch_set_status(
            swarm_hashes=[DUMMY_HASH, hash2],
            statuses=[1, 2],  # RESTRICTED, DELETED
        )

        assert isinstance(result, AnchorResult)
        assert result.swarm_hash == DUMMY_HASH


# ============================================================
# V2 Contract Feature Tests
# ============================================================


class TestV2ContractDetection:
    """Tests for v2 contract auto-detection via supports_transformation_links."""

    def test_detects_v2_contract(self, mock_chain_deps):
        """Tests that v2 contract is detected when getTransformationLinks succeeds."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.return_value = []

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )
        assert contract.supports_transformation_links() is True

    def test_detects_v1_contract(self, real_web3_exceptions, mock_chain_deps):
        """Tests that v1 contract is detected when getTransformationLinks reverts."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.side_effect = (
            real_web3_exceptions.ContractLogicError("execution reverted")
        )

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )
        assert contract.supports_transformation_links() is False

    def test_v2_detection_cached(self, mock_chain_deps):
        """Tests that v2 detection result is cached after first call."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.return_value = []

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )
        contract.supports_transformation_links()
        contract.supports_transformation_links()

        # Should only have been called once (cached after first call)
        assert mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.call_count == 1


class TestV2ViewMethods:
    """Tests for v2 state-based view methods."""

    def test_get_transformation_links(self, mock_chain_deps):
        """Tests get_transformation_links returns parsed tuples."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        new_hash_bytes = bytes.fromhex("bb" * 32)
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.return_value = [
            (new_hash_bytes, "filtered PII"),
        ]

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )
        links = contract.get_transformation_links(DUMMY_HASH)

        assert len(links) == 1
        assert links[0][0] == new_hash_bytes
        assert links[0][1] == "filtered PII"

    def test_get_child_hashes(self, mock_chain_deps):
        """Tests get_child_hashes returns list of bytes."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        child1 = bytes.fromhex("bb" * 32)
        child2 = bytes.fromhex("cc" * 32)
        mock_chain_deps["contract"].functions.getChildHashes.return_value.call.return_value = [child1, child2]

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )
        children = contract.get_child_hashes(DUMMY_HASH)

        assert len(children) == 2
        assert children[0] == child1
        assert children[1] == child2

    def test_get_transformation_parents(self, mock_chain_deps):
        """Tests get_transformation_parents returns list of bytes."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        parent = bytes.fromhex("cc" * 32)
        mock_chain_deps["contract"].functions.getTransformationParents.return_value.call.return_value = [parent]

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )
        parents = contract.get_transformation_parents(DUMMY_HASH)

        assert len(parents) == 1
        assert parents[0] == parent


class TestMergeTransformValidation:
    """Tests for merge transformation validation."""

    def test_merge_too_few_sources(self, mock_chain_deps):
        """Tests that fewer than MIN_MERGE_SOURCES raises validation error."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )

        with pytest.raises(ChainValidationError) as exc_info:
            contract.build_record_merge_transformation_tx(
                source_hashes=[DUMMY_HASH],  # only 1, need at least 2
                new_hash="b" * 64,
                description="merge",
                new_data_type="merged",
                sender=DUMMY_ADDRESS,
            )
        assert "at least" in str(exc_info.value).lower()

    def test_merge_too_many_sources(self, mock_chain_deps):
        """Tests that exceeding MAX_MERGE_SOURCES raises validation error."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract, MAX_MERGE_SOURCES

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )

        with pytest.raises(ChainValidationError) as exc_info:
            contract.build_record_merge_transformation_tx(
                source_hashes=[DUMMY_HASH] * (MAX_MERGE_SOURCES + 1),
                new_hash="b" * 64,
                description="merge",
                new_data_type="merged",
                sender=DUMMY_ADDRESS,
            )
        assert "maximum" in str(exc_info.value).lower()

    def test_merge_valid_build(self, mock_chain_deps):
        """Tests successful merge tx build with valid inputs."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        mock_chain_deps["contract"].functions.recordMergeTransformation.return_value.build_transaction.return_value = {
            "from": DUMMY_ADDRESS,
            "to": DUMMY_CONTRACT,
            "data": "0x",
        }

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )
        tx = contract.build_record_merge_transformation_tx(
            source_hashes=[DUMMY_HASH, "b" * 64],
            new_hash="c" * 64,
            description="merged two datasets",
            new_data_type="merged",
            sender=DUMMY_ADDRESS,
        )
        assert tx["from"] == DUMMY_ADDRESS


class TestMergeTransformClient:
    """Tests for ChainClient.merge_transform method."""

    def test_merge_transform_success(self, mock_chain_deps):
        """Tests successful merge transform via ChainClient."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        mock_chain_deps["contract"].functions.recordMergeTransformation.return_value.build_transaction.return_value = {
            "from": DUMMY_ADDRESS,
            "to": DUMMY_CONTRACT,
            "data": "0x",
        }

        client = ChainClient(chain="base-sepolia")
        result = client.merge_transform(
            source_hashes=[DUMMY_HASH, "b" * 64],
            new_hash="c" * 64,
            description="merged",
            new_data_type="combined",
        )

        assert isinstance(result, MergeTransformResult)
        assert result.source_hashes == [DUMMY_HASH, "b" * 64]
        assert result.new_hash == "c" * 64
        assert result.description == "merged"
        assert result.new_data_type == "combined"
        assert result.block_number == 12345679
        assert result.gas_used == 95_000


class TestDuplicateTransformPreCheck:
    """Tests for duplicate transformation pre-checks in ChainClient.transform."""

    def test_v2_duplicate_raises_error(self, mock_chain_deps):
        """Tests that v2 state-based duplicate check raises TransformationAlreadyExistsError."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        new_hash = "b" * 64
        new_hash_bytes = bytes.fromhex(new_hash)

        # V2 detection: getTransformationLinks succeeds
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.return_value = [
            (new_hash_bytes, "already done"),
        ]

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(TransformationAlreadyExistsError) as exc_info:
            client.transform(
                original_hash=DUMMY_HASH,
                new_hash=new_hash,
                description="filter again",
            )
        assert exc_info.value.original_hash == DUMMY_HASH
        assert exc_info.value.new_hash == new_hash
        assert exc_info.value.existing_description == "already done"

    def test_v2_no_duplicate_proceeds(self, mock_chain_deps):
        """Tests that v2 duplicate check passes when no match."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # V2 detection: succeeds but returns empty list
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.return_value = []

        client = ChainClient(chain="base-sepolia")
        result = client.transform(
            original_hash=DUMMY_HASH,
            new_hash="b" * 64,
            description="new transform",
        )
        assert isinstance(result, TransformResult)

    def test_v1_event_cache_duplicate_raises_error(self, mock_chain_deps):
        """Tests that v1 event-cache-based duplicate check raises error."""
        from swarm_provenance_uploader.core.chain_client import ChainClient
        from swarm_provenance_uploader.chain.event_cache import clear_registry

        # Clear any cached state from prior tests
        clear_registry()

        new_hash = "b" * 64

        # Mock the event cache
        mock_cache = MagicMock()
        forward_map = {DUMMY_HASH: [(new_hash, "existing desc")]}
        mock_cache.get_maps.return_value = (forward_map, {})

        with patch("swarm_provenance_uploader.chain.event_cache.get_cache", return_value=mock_cache):
            client = ChainClient(chain="base-sepolia")
            # Force v1 mode — bypass auto-detection which depends on mock state
            client._contract._supports_v2 = False
            with pytest.raises(TransformationAlreadyExistsError) as exc_info:
                client.transform(
                    original_hash=DUMMY_HASH,
                    new_hash=new_hash,
                    description="try again",
                )
            assert exc_info.value.existing_description == "existing desc"


class TestAnchorRevertDetection:
    """Tests for detecting 'already registered' reverts in anchor."""

    def test_anchor_revert_already_registered(self, mock_chain_deps):
        """Tests that 'already registered' revert is caught and re-raised."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Pre-check: not registered (zero-address owner)
        call_count = [0]
        def mock_get_data_record(data_hash):
            call_count[0] += 1
            mock_call = MagicMock()
            if call_count[0] == 1:
                # First call (pre-check): not registered
                mock_call.call.return_value = (
                    DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
                )
            else:
                # Second call (after revert): now registered
                mock_call.call.return_value = (
                    DUMMY_HASH_BYTES, DUMMY_ADDRESS, 1700000000, "swarm-provenance", b"\x00" * 32, [], [], 0,
                )
            return mock_call

        mock_chain_deps["contract"].functions.getDataRecord = mock_get_data_record

        # Transaction fails with "already registered" revert
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.side_effect = Exception(
            "execution reverted: Data already registered"
        )

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(DataAlreadyRegisteredError) as exc_info:
            client.anchor(swarm_hash=DUMMY_HASH)
        assert exc_info.value.data_hash == DUMMY_HASH
        assert exc_info.value.owner == DUMMY_ADDRESS


class TestV2TransformationParsing:
    """Tests for parsing v2 TransformationLink tuples in ChainClient.get()."""

    def test_get_with_v2_transformation_links(self, mock_chain_deps):
        """Tests that v2 TransformationLink tuples are parsed correctly."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        new_hash_bytes = bytes.fromhex("bb" * 32)
        # Contract returns TransformationLink[] (list of (bytes32, string) tuples)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES,
            DUMMY_ADDRESS,
            1700000000,
            "swarm-provenance",
            b"\x00" * 32,
            [(new_hash_bytes, "filtered PII")],  # v2 tuple format
            [],
            0,
        )

        client = ChainClient(chain="base-sepolia")
        record = client.get(swarm_hash=DUMMY_HASH)

        assert len(record.transformations) == 1
        assert record.transformations[0].description == "filtered PII"
        assert record.transformations[0].new_data_hash == "bb" * 32

    def test_get_with_mixed_v1_strings(self, mock_chain_deps):
        """Tests that v1 string descriptions are parsed correctly."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES,
            DUMMY_ADDRESS,
            1700000000,
            "swarm-provenance",
            b"\x00" * 32,
            ["plain string description"],  # v1 format
            [],
            0,
        )

        client = ChainClient(chain="base-sepolia")
        record = client.get(swarm_hash=DUMMY_HASH)

        assert len(record.transformations) == 1
        assert record.transformations[0].description == "plain string description"
        assert record.transformations[0].new_data_hash is None


class TestV1Fallback:
    """Tests for v1 fallback when getDataRecord decode fails."""

    def test_get_data_record_v1_fallback(self, real_web3_exceptions, mock_chain_deps):
        """Tests fallback to dataRecords() when v4 ABI decode fails on v1."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        # getDataRecord fails (v4 ABI decode error on v1 contract)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.side_effect = OverflowError("decode")
        # getTransformationLinks also fails (v1 contract)
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.side_effect = (
            real_web3_exceptions.ContractLogicError("execution reverted")
        )
        # dataRecords returns scalar-only tuple (v1: 5 fields, no storageRef)
        mock_chain_deps["contract"].functions.dataRecords.return_value.call.return_value = (
            DUMMY_HASH_BYTES, DUMMY_ADDRESS, 1700000000, "swarm-provenance", 0
        )

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )
        record = contract.get_data_record(DUMMY_HASH)

        # Should return 8-element tuple with zero storageRef and empty arrays
        assert record[0] == DUMMY_HASH_BYTES
        assert record[1] == DUMMY_ADDRESS
        assert record[4] == b"\x00" * 32  # storageRef (zero)
        assert record[5] == []  # transformations (empty)
        assert record[6] == []  # accessors (empty)

    def test_get_data_record_v4_fallback_with_storage_ref(self, real_web3_exceptions, mock_chain_deps):
        """Tests fallback to dataRecords() on v4 contract (6-field tuple with storageRef)."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        storage_ref = bytes.fromhex("bb" * 32)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.side_effect = OverflowError("decode")
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.side_effect = (
            real_web3_exceptions.ContractLogicError("execution reverted")
        )
        # dataRecords on v4 returns 6 fields including storageRef
        mock_chain_deps["contract"].functions.dataRecords.return_value.call.return_value = (
            DUMMY_HASH_BYTES, DUMMY_ADDRESS, 1700000000, "swarm-provenance", storage_ref, 0
        )

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )
        record = contract.get_data_record(DUMMY_HASH)

        assert record[4] == storage_ref  # storageRef preserved
        assert record[5] == []  # transformations (empty)
        assert record[6] == []  # accessors (empty)


class TestEventCache:
    """Tests for TransformationEventCache singleton and scanning."""

    def setup_method(self):
        """Clear event cache registry before each test."""
        from swarm_provenance_uploader.chain.event_cache import clear_registry
        clear_registry()

    def test_singleton_pattern(self):
        """Tests that get_cache returns the same instance for same key."""
        from swarm_provenance_uploader.chain.event_cache import get_cache

        cache1 = get_cache("base-sepolia", DUMMY_CONTRACT, 0)
        cache2 = get_cache("base-sepolia", DUMMY_CONTRACT, 0)
        assert cache1 is cache2

    def test_different_keys_different_instances(self):
        """Tests that different chain/contract combos get different caches."""
        from swarm_provenance_uploader.chain.event_cache import get_cache

        cache1 = get_cache("base-sepolia", DUMMY_CONTRACT, 0)
        cache2 = get_cache("base", "0x" + "11" * 20, 0)
        assert cache1 is not cache2

    def test_different_deploy_blocks_different_instances(self):
        """A cache built from one deploy block is not reused for another (#231 review)."""
        from swarm_provenance_uploader.chain.event_cache import get_cache

        assert get_cache("base-sepolia", DUMMY_CONTRACT, 1_000) is not get_cache("base-sepolia", DUMMY_CONTRACT, 0)

    def test_case_insensitive_address(self):
        """Tests that contract address lookup is case-insensitive."""
        from swarm_provenance_uploader.chain.event_cache import get_cache

        cache1 = get_cache("base-sepolia", "0xABCDEF", 0)
        cache2 = get_cache("base-sepolia", "0xabcdef", 0)
        assert cache1 is cache2

    def test_full_scan_populates_maps(self):
        """Tests that first get_maps call does full scan."""
        from swarm_provenance_uploader.chain.event_cache import TransformationEventCache

        cache = TransformationEventCache()
        mock_contract = MagicMock()

        orig = bytes.fromhex("aa" * 32)
        new = bytes.fromhex("bb" * 32)
        mock_contract.get_all_transformations.return_value = [
            (orig, new, "filtered"),
        ]
        mock_contract.get_all_merge_events.return_value = []

        forward, reverse = cache.get_maps(mock_contract, deploy_block=0, current_block=1000)

        assert orig.hex() in forward
        assert new.hex() in reverse
        assert forward[orig.hex()] == [(new.hex(), "filtered")]
        assert reverse[new.hex()] == [(orig.hex(), "filtered")]

    def test_incremental_scan(self):
        """Tests that subsequent get_maps call scans only new blocks."""
        from swarm_provenance_uploader.chain.event_cache import TransformationEventCache

        cache = TransformationEventCache()
        mock_contract = MagicMock()
        mock_contract.get_all_transformations.return_value = []
        mock_contract.get_all_merge_events.return_value = []

        # First scan: blocks 0-1000
        cache.get_maps(mock_contract, deploy_block=0, current_block=1000)
        mock_contract.get_all_transformations.assert_called_with(from_block=0, to_block=1000)

        # Second scan: should start from 1001
        mock_contract.get_all_transformations.reset_mock()
        cache.get_maps(mock_contract, deploy_block=0, current_block=2000)
        mock_contract.get_all_transformations.assert_called_with(from_block=1001, to_block=2000)

    def test_no_rescan_when_current(self):
        """Tests that get_maps skips scan when already at current block."""
        from swarm_provenance_uploader.chain.event_cache import TransformationEventCache

        cache = TransformationEventCache()
        mock_contract = MagicMock()
        mock_contract.get_all_transformations.return_value = []
        mock_contract.get_all_merge_events.return_value = []

        cache.get_maps(mock_contract, deploy_block=0, current_block=1000)
        mock_contract.get_all_transformations.reset_mock()

        # Same current_block — should not scan again
        cache.get_maps(mock_contract, deploy_block=0, current_block=1000)
        mock_contract.get_all_transformations.assert_not_called()

    def test_merge_events_populate_maps(self):
        """Tests that DataMerged events populate forward and reverse maps."""
        from swarm_provenance_uploader.chain.event_cache import TransformationEventCache

        cache = TransformationEventCache()
        mock_contract = MagicMock()
        mock_contract.get_all_transformations.return_value = []

        src1 = bytes.fromhex("aa" * 32)
        src2 = bytes.fromhex("bb" * 32)
        new = bytes.fromhex("cc" * 32)

        merge_event = MagicMock()
        merge_event.args.newDataHash = new
        merge_event.args.sourceDataHashes = [src1, src2]
        merge_event.args.transformation = "merged"
        mock_contract.get_all_merge_events.return_value = [merge_event]

        forward, reverse = cache.get_maps(mock_contract, deploy_block=0, current_block=1000)

        # Both sources should map forward to new
        assert (new.hex(), "merged") in forward[src1.hex()]
        assert (new.hex(), "merged") in forward[src2.hex()]
        # Reverse: new should map back to both sources
        reverse_srcs = [src for src, _ in reverse[new.hex()]]
        assert src1.hex() in reverse_srcs
        assert src2.hex() in reverse_srcs

    def test_merge_events_empty_on_v1(self):
        """A v1 contract emits no DataMerged events: the merge scan finds none."""
        from swarm_provenance_uploader.chain.event_cache import TransformationEventCache

        cache = TransformationEventCache()
        mock_contract = MagicMock()
        mock_contract.get_all_transformations.return_value = []
        mock_contract.get_all_merge_events.return_value = []

        forward, reverse = cache.get_maps(mock_contract, deploy_block=0, current_block=1000)
        assert forward == {}
        assert reverse == {}

    def test_merge_scan_failure_raises_and_scans_the_range_again(self):
        """A failed DataMerged scan raises and changes nothing, so no merge is lost (#230).

        It was logged and skipped while the scan marker still moved on, so
        the merges in that block range were never read again.
        """
        from swarm_provenance_uploader.chain.event_cache import TransformationEventCache

        orig = bytes.fromhex("aa" * 32)
        new = bytes.fromhex("bb" * 32)
        merged = bytes.fromhex("cc" * 32)
        merge_event = MagicMock()
        merge_event.args.newDataHash = merged
        merge_event.args.sourceDataHashes = [orig, new]
        merge_event.args.transformation = "merged"

        cache = TransformationEventCache()
        mock_contract = MagicMock()
        mock_contract.get_all_transformations.return_value = [(orig, new, "step")]
        mock_contract.get_all_merge_events.side_effect = [OSError("timed out"), [merge_event]]

        with pytest.raises(OSError):
            cache.get_maps(mock_contract, deploy_block=0, current_block=1000)
        assert cache._last_scanned_block is None
        assert cache._forward == {}
        assert cache._reverse == {}

        forward, reverse = cache.get_maps(mock_contract, deploy_block=0, current_block=1000)
        assert forward[orig.hex()] == [(new.hex(), "step"), (merged.hex(), "merged")]
        assert reverse[new.hex()] == [(orig.hex(), "step")]
        assert sorted(src for src, _ in reverse[merged.hex()]) == [orig.hex(), new.hex()]
        assert mock_contract.get_all_merge_events.call_args.kwargs == {"from_block": 0, "to_block": 1000}

    def test_get_all_merge_events_raises_rpc_errors(self, mock_chain_deps):
        """get_all_merge_events no longer turns an RPC error into an empty list (#230)."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        mock_chain_deps["contract"].events.DataMerged.get_logs.side_effect = OSError("timed out")
        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"], contract_address=DUMMY_CONTRACT,
        )
        with pytest.raises(OSError):
            contract.get_all_merge_events(from_block=0, to_block=100)


class TestChunkedEventQueries:
    """Tests for chunked event log queries."""

    def test_chunked_query_splits_range(self, mock_chain_deps):
        """Tests that large ranges are split into chunks."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )

        mock_event = MagicMock()
        mock_event.get_logs.return_value = []

        # Query a range larger than _EVENT_CHUNK_SIZE
        contract._get_logs_chunked(mock_event, None, 0, 25_000)

        # Should have been called 3 times: 0-9999, 10000-19999, 20000-25000
        assert mock_event.get_logs.call_count == 3

    def test_chunked_query_retries_on_413(self, mock_chain_deps):
        """Tests that 413 error triggers chunk halving."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )

        mock_event = MagicMock()
        # First call fails with 413, halved retries succeed
        call_count = [0]
        def side_effect(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("413 Payload Too Large")
            return []

        mock_event.get_logs.side_effect = side_effect

        # Small range that fits in one chunk normally
        result = contract._get_logs_chunked(mock_event, None, 0, 100)
        assert result == []
        # Should have retried with halved chunks after 413
        assert call_count[0] == 3  # 1 failed + 2 halved


class TestRPCFallback:
    """Tests for RPC failover in ChainProvider."""

    def test_fallback_on_health_check(self, mock_chain_deps):
        """Tests that health_check tries fallback on failure."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        # First connection fails, reconnect with fallback succeeds
        call_count = [0]
        def is_connected_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return False  # Primary fails
            return True  # Fallback succeeds

        mock_chain_deps["web3_instance"].is_connected.side_effect = is_connected_side_effect

        provider = ChainProvider(chain="base-sepolia")
        # The fallback logic creates new Web3 instances, so we need to mock that
        # Since _try_fallback creates new Web3 instances, and the mock_web3_class
        # returns mock_web3_instance for all calls, the fallback should work
        result = provider.health_check()
        assert result is True

    def test_health_check_terminates_when_every_endpoint_fails_the_check(self, mock_chain_deps):
        """Endpoints that connect but report the wrong chain used to be switched between forever (#132).

        Since the #168 review, a wrong chain ID is ChainIdMismatchError at
        once: no fallback is probed.
        """
        from swarm_provenance_uploader.chain.provider import ChainProvider
        from swarm_provenance_uploader.chain.exceptions import ChainIdMismatchError

        web3 = mock_chain_deps["web3_instance"]
        web3.is_connected.side_effect = None
        web3.is_connected.return_value = True
        web3.eth.chain_id = 1  # not Base Sepolia, on every endpoint

        provider = ChainProvider(chain="base-sepolia")
        with pytest.raises(ChainIdMismatchError, match="Chain ID mismatch"):
            provider.health_check()
        assert web3.is_connected.call_count == 1

    def test_dead_fallback_probed_once_per_call(self, mock_chain_deps):
        """A fallback that does not connect is not probed again in the same call."""
        from swarm_provenance_uploader.chain.provider import ChainProvider
        from swarm_provenance_uploader.chain.exceptions import ChainConnectionError

        web3 = mock_chain_deps["web3_instance"]
        web3.is_connected.side_effect = None
        web3.is_connected.return_value = False  # every endpoint is down
        provider = ChainProvider(chain="base-sepolia")
        with pytest.raises(ChainConnectionError):
            provider.health_check()
        # once for the primary check, once per fallback probe
        assert web3.is_connected.call_count == len(provider._rpc_urls)

    def test_get_block_number_terminates_when_every_endpoint_fails(self, mock_chain_deps):
        from unittest.mock import PropertyMock
        from swarm_provenance_uploader.chain.provider import ChainProvider
        from swarm_provenance_uploader.chain.exceptions import ChainConnectionError

        web3 = mock_chain_deps["web3_instance"]
        web3.is_connected.side_effect = None
        web3.is_connected.return_value = True
        calls = PropertyMock(side_effect=RuntimeError("rpc down"))
        type(web3.eth).block_number = calls

        provider = ChainProvider(chain="base-sepolia")
        with pytest.raises(ChainConnectionError, match="Failed to get block number"):
            provider.get_block_number()
        assert calls.call_count == len(provider._rpc_urls)

    def test_fallback_urls_from_preset(self, mock_chain_deps):
        """Tests that preset fallback URLs are populated."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia")
        # Should have primary + 2 fallbacks from preset
        assert len(provider._rpc_urls) == 3
        assert provider._rpc_urls[0] == "https://sepolia.base.org"

    def test_custom_rpc_no_fallbacks(self, mock_chain_deps):
        """Tests that custom RPC with no explicit fallbacks has only primary."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(
            chain="base-sepolia",
            rpc_url="https://custom.rpc.io",
        )
        assert len(provider._rpc_urls) == 1

    def test_explicit_fallbacks_override_preset(self, mock_chain_deps):
        """Tests that explicit rpc_fallbacks overrides preset."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(
            chain="base-sepolia",
            rpc_fallbacks=["https://fb1.io", "https://fb2.io"],
        )
        assert len(provider._rpc_urls) == 3
        assert provider._rpc_urls[1] == "https://fb1.io"


class TestProviderEnhancements:
    """Tests for new provider features: localhost, deploy_block, Optional explorer."""

    def test_localhost_preset(self, mock_chain_deps):
        """Tests localhost preset initialization."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        # Localhost auto-detects chain ID from node
        mock_chain_deps["web3_instance"].eth.chain_id = 31337
        provider = ChainProvider(
            chain="localhost",
            rpc_url="http://127.0.0.1:8545",
        )
        assert provider.chain == "localhost"
        assert provider.contract_address == "0xCf7Ed3AccA5a467e9e704C703E8D87F634fB0Fc9"
        assert provider.deploy_block == 0

    def test_explorer_url_none_for_localhost(self, mock_chain_deps):
        """Tests that localhost has no explorer URL."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        mock_chain_deps["web3_instance"].eth.chain_id = 31337
        provider = ChainProvider(
            chain="localhost",
            rpc_url="http://127.0.0.1:8545",
        )
        assert provider.explorer_url is None
        assert provider.get_explorer_tx_url("0xabc") is None
        assert provider.get_explorer_address_url("0xabc") is None

    def test_deploy_block_populated(self, mock_chain_deps):
        """Tests that deploy_block is set from preset."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia")
        assert provider.deploy_block == 39_905_249


def _web3_per_url(mock_chain_deps, chain_ids, down=()):
    """Make Web3(HTTPProvider(url)) return a separate mock node for each URL.

    chain_ids maps URL -> the chain ID that node reports. URLs in ``down``
    do not connect and fail every call.

    Each Web3 object answers as the node of its current ``provider``, so a
    fallback switch that replaces the provider of the existing Web3 object
    (#200) reaches the fallback's node, as with the real web3.
    """
    nodes = {}
    for url, chain_id in chain_ids.items():
        node = MagicMock()
        node.to_checksum_address = lambda x: x
        if url in down:
            node.is_connected.return_value = False
            type(node.eth).chain_id = PropertyMock(side_effect=ConnectionError("down"))
            type(node.eth).block_number = PropertyMock(side_effect=ConnectionError("down"))
        else:
            node.is_connected.return_value = True
            node.eth.chain_id = chain_id
            node.eth.block_number = 100 + chain_id
        nodes[url] = node

    class _Web3:
        def __init__(self, provider):
            self.provider = provider

        def __getattr__(self, name):
            return getattr(nodes[self.provider], name)

    web3_class = mock_chain_deps["web3_class"]
    web3_class.HTTPProvider.side_effect = lambda url, **kw: url
    web3_class.side_effect = _Web3
    return nodes


class TestChainIdPresetMismatch:
    """A named preset with an RPC on another chain is an error before anything is read or signed (#142)."""

    @pytest.mark.parametrize("chain,preset_id,node_id", [
        ("base-sepolia", 84532, 8453),
        ("base", 8453, 84532),
    ])
    def test_custom_rpc_on_another_chain_is_an_error(self, mock_chain_deps, chain, preset_id, node_id):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        mock_chain_deps["web3_instance"].eth.chain_id = node_id
        with pytest.raises(ChainConfigurationError) as exc_info:
            ChainProvider(chain=chain, rpc_url="https://custom.rpc.io", contract_address=DUMMY_CONTRACT)
        message = str(exc_info.value)
        assert str(preset_id) in message
        assert str(node_id) in message
        assert chain in message
        assert "CHAIN_NAME=localhost" in message
        assert "--chain localhost" not in message

    def test_custom_rpc_on_the_preset_chain_is_accepted(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        mock_chain_deps["web3_instance"].eth.chain_id = 84532
        provider = ChainProvider(chain="base-sepolia", rpc_url="https://custom.rpc.io")
        assert provider.chain_id == 84532

    def test_localhost_preset_still_auto_detects(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        mock_chain_deps["web3_instance"].eth.chain_id = 1337
        provider = ChainProvider(chain="localhost", rpc_url="http://127.0.0.1:8546")
        assert provider.chain_id == 1337

    def test_detection_failure_keeps_the_preset_id(self, mock_chain_deps):
        """Unchanged: an unreachable custom RPC is reported later by health_check, not at init."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        type(mock_chain_deps["web3_instance"].eth).chain_id = PropertyMock(side_effect=ConnectionError("down"))
        provider = ChainProvider(chain="base-sepolia", rpc_url="https://custom.rpc.io")
        assert provider.chain_id == 84532

    def test_client_reads_fail_on_mismatch(self, mock_chain_deps):
        """Reads fail too: the client is never created."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        mock_chain_deps["web3_instance"].eth.chain_id = 8453
        with pytest.raises(ChainConfigurationError, match="84532"):
            ChainClient(chain="base-sepolia", rpc_url="https://custom.rpc.io")
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.assert_not_called()
        mock_chain_deps["account"].sign_transaction.assert_not_called()
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()

    def test_get_block_number_does_not_switch_to_a_fallback_on_another_chain(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.provider import ChainProvider
        from swarm_provenance_uploader.chain.exceptions import ChainConnectionError

        primary, wrong = "https://primary.rpc.io", "https://wrong-chain.rpc.io"
        _web3_per_url(mock_chain_deps, {primary: 84532, wrong: 8453}, down=(primary,))
        provider = ChainProvider(chain="base-sepolia", rpc_url=primary, rpc_fallbacks=[wrong])
        with pytest.raises(ChainConnectionError):
            provider.get_block_number()
        assert provider.rpc_url == primary

    def test_fallback_on_the_preset_chain_is_still_used(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        primary, wrong, good = "https://primary.rpc.io", "https://wrong-chain.rpc.io", "https://good.rpc.io"
        _web3_per_url(mock_chain_deps, {primary: 84532, wrong: 8453, good: 84532}, down=(primary,))
        provider = ChainProvider(chain="base-sepolia", rpc_url=primary, rpc_fallbacks=[wrong, good])
        assert provider.get_block_number() == 100 + 84532
        assert provider.rpc_url == good

    def test_preset_fallbacks_are_checked_too(self, mock_chain_deps):
        """No custom RPC, explicit fallbacks: a fallback on another chain is skipped by health_check."""
        from swarm_provenance_uploader.chain.provider import ChainProvider, CHAIN_PRESETS
        from swarm_provenance_uploader.chain.exceptions import ChainConnectionError

        primary = CHAIN_PRESETS["base-sepolia"]["rpc_url"]
        wrong = "https://wrong-chain.rpc.io"
        _web3_per_url(mock_chain_deps, {primary: 84532, wrong: 8453}, down=(primary,))
        provider = ChainProvider(chain="base-sepolia", rpc_fallbacks=[wrong])
        with pytest.raises(ChainConnectionError):
            provider.health_check()
        assert provider.rpc_url == primary


class TestChainIdCheckedBeforeFirstSignature:
    """The chain ID is checked again before the first signature (#142 review).

    If the custom RPC is unreachable when the client starts, the init check
    cannot run. A node on another chain that comes up later must not get a
    signed transaction.
    """

    def _unregistered(self, mock_chain_deps):
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

    def _nothing_signed(self, mock_chain_deps):
        mock_chain_deps["account"].sign_transaction.assert_not_called()
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()

    def test_node_on_another_chain_after_start_is_refused(self, mock_chain_deps):
        from swarm_provenance_uploader.core.chain_client import ChainClient
        from swarm_provenance_uploader.chain.exceptions import ChainIdMismatchError

        self._unregistered(mock_chain_deps)
        eth = mock_chain_deps["web3_instance"].eth
        # Down when the client starts ...
        type(eth).chain_id = PropertyMock(side_effect=ConnectionError("down"))
        client = ChainClient(chain="base-sepolia", rpc_url="http://127.0.0.1:8546", gas_limit=200_000)
        # ... then a mainnet node comes up at the same URL
        type(eth).chain_id = PropertyMock(return_value=8453)

        with pytest.raises(ChainIdMismatchError) as exc_info:
            client.anchor(swarm_hash=DUMMY_HASH)
        assert isinstance(exc_info.value, ChainConfigurationError)
        assert "84532" in str(exc_info.value) and "8453" in str(exc_info.value)
        assert exc_info.value.expected_chain_id == 84532
        assert exc_info.value.actual_chain_id == 8453
        self._nothing_signed(mock_chain_deps)

    def test_still_unreachable_fails_the_write(self, mock_chain_deps):
        from swarm_provenance_uploader.core.chain_client import ChainClient

        self._unregistered(mock_chain_deps)
        eth = mock_chain_deps["web3_instance"].eth
        type(eth).chain_id = PropertyMock(side_effect=ConnectionError("down"))
        client = ChainClient(chain="base-sepolia", rpc_url="http://127.0.0.1:8546", gas_limit=200_000)

        with pytest.raises(ChainConnectionError):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)
        self._nothing_signed(mock_chain_deps)

    def test_preset_rpc_on_another_chain_is_refused(self, mock_chain_deps):
        """No custom RPC: the preset RPC is not queried at start, so the check runs before the write."""
        from swarm_provenance_uploader.core.chain_client import ChainClient
        from swarm_provenance_uploader.chain.exceptions import ChainIdMismatchError

        self._unregistered(mock_chain_deps)
        mock_chain_deps["web3_instance"].eth.chain_id = 8453
        client = ChainClient(chain="base-sepolia")
        with pytest.raises(ChainIdMismatchError):
            client.anchor(swarm_hash=DUMMY_HASH)
        self._nothing_signed(mock_chain_deps)

    def test_checked_once_per_client(self, mock_chain_deps):
        from swarm_provenance_uploader.core.chain_client import ChainClient

        self._unregistered(mock_chain_deps)
        calls = PropertyMock(return_value=84532)
        type(mock_chain_deps["web3_instance"].eth).chain_id = calls
        client = ChainClient(chain="base-sepolia")
        client.set_status(swarm_hash=DUMMY_HASH, status=1)
        client.set_status(swarm_hash=DUMMY_HASH, status=0)
        assert calls.call_count == 1
        assert mock_chain_deps["account"].sign_transaction.call_count == 2

    def test_init_mismatch_is_chain_id_mismatch_error(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.provider import ChainProvider
        from swarm_provenance_uploader.chain.exceptions import ChainIdMismatchError

        mock_chain_deps["web3_instance"].eth.chain_id = 8453
        with pytest.raises(ChainIdMismatchError) as exc_info:
            ChainProvider(chain="base-sepolia", rpc_url="https://custom.rpc.io")
        assert exc_info.value.chain == "base-sepolia"

    def test_exported_from_package_exceptions(self):
        from swarm_provenance_uploader import exceptions
        from swarm_provenance_uploader.chain.exceptions import ChainIdMismatchError

        assert exceptions.ChainIdMismatchError is ChainIdMismatchError

class TestPendingNonce:
    """The nonce counts pending transactions, so a second write does not reuse it (#142)."""

    def test_send_transaction_uses_pending_nonce(self, mock_chain_deps):
        from swarm_provenance_uploader.core.chain_client import ChainClient

        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )
        mock_chain_deps["web3_instance"].eth.get_transaction_count.return_value = 7

        client = ChainClient(chain="base-sepolia")
        client.anchor(swarm_hash=DUMMY_HASH)

        mock_chain_deps["web3_instance"].eth.get_transaction_count.assert_called_with(DUMMY_ADDRESS, "pending")
        tx = mock_chain_deps["account"].sign_transaction.call_args[0][0]
        assert tx["nonce"] == 7


class TestProvenanceChainV2StateReads:
    """Tests for provenance chain traversal using v2 state reads."""

    def test_v2_state_traversal(self, mock_chain_deps):
        """Tests provenance chain traversal using v2 getTransformationLinks."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        hash_a = DUMMY_HASH
        hash_b = "b" * 64
        hash_a_bytes = bytes.fromhex(hash_a)
        hash_b_bytes = bytes.fromhex(hash_b)

        # V2 detection: succeeds
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.return_value = []

        # getDataRecord returns different records for hash_a and hash_b
        def mock_get_data_record(data_hash):
            mock_call = MagicMock()
            if data_hash == hash_a_bytes:
                mock_call.call.return_value = (
                    hash_a_bytes, DUMMY_ADDRESS, 1700000000, "swarm-provenance",
                    b"\x00" * 32, [], [], 0,
                )
            elif data_hash == hash_b_bytes:
                mock_call.call.return_value = (
                    hash_b_bytes, DUMMY_ADDRESS, 1700000001, "swarm-provenance",
                    b"\x00" * 32, [], [], 0,
                )
            else:
                mock_call.call.return_value = (data_hash, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0)
            return mock_call

        mock_chain_deps["contract"].functions.getDataRecord = mock_get_data_record

        # getTransformationLinks for hash_a returns link to hash_b
        def mock_get_links(data_hash):
            mock_call = MagicMock()
            if data_hash == hash_a_bytes:
                mock_call.call.return_value = [(hash_b_bytes, "filtered")]
            else:
                mock_call.call.return_value = []
            return mock_call

        mock_chain_deps["contract"].functions.getTransformationLinks = mock_get_links

        # getTransformationParents
        def mock_get_parents(data_hash):
            mock_call = MagicMock()
            if data_hash == hash_b_bytes:
                mock_call.call.return_value = [hash_a_bytes]
            else:
                mock_call.call.return_value = []
            return mock_call

        mock_chain_deps["contract"].functions.getTransformationParents = mock_get_parents

        client = ChainClient(chain="base-sepolia")
        chain = client.get_provenance_chain(swarm_hash=hash_a)

        assert len(chain) == 2
        chain_hashes = [r.data_hash for r in chain]
        assert hash_a in chain_hashes
        assert hash_b in chain_hashes

    def test_v2_cycle_detection(self, mock_chain_deps):
        """Tests that provenance chain traversal detects cycles."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        hash_a = DUMMY_HASH
        hash_b = "b" * 64
        hash_a_bytes = bytes.fromhex(hash_a)
        hash_b_bytes = bytes.fromhex(hash_b)

        # V2 detection: succeeds
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.return_value = []

        def mock_get_data_record(data_hash):
            mock_call = MagicMock()
            if data_hash == hash_a_bytes:
                mock_call.call.return_value = (hash_a_bytes, DUMMY_ADDRESS, 1700000000, "type", b"\x00" * 32, [], [], 0)
            elif data_hash == hash_b_bytes:
                mock_call.call.return_value = (hash_b_bytes, DUMMY_ADDRESS, 1700000001, "type", b"\x00" * 32, [], [], 0)
            else:
                mock_call.call.return_value = (data_hash, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0)
            return mock_call

        mock_chain_deps["contract"].functions.getDataRecord = mock_get_data_record

        # Create a cycle: A -> B -> A
        def mock_get_links(data_hash):
            mock_call = MagicMock()
            if data_hash == hash_a_bytes:
                mock_call.call.return_value = [(hash_b_bytes, "step1")]
            elif data_hash == hash_b_bytes:
                mock_call.call.return_value = [(hash_a_bytes, "step2")]
            else:
                mock_call.call.return_value = []
            return mock_call

        mock_chain_deps["contract"].functions.getTransformationLinks = mock_get_links
        mock_chain_deps["contract"].functions.getTransformationParents.return_value.call.return_value = []

        client = ChainClient(chain="base-sepolia")
        chain = client.get_provenance_chain(swarm_hash=hash_a)

        # Should visit each node exactly once despite cycle
        assert len(chain) == 2


class TestTransformationAlreadyExistsExceptionFields:
    """Tests for TransformationAlreadyExistsError exception fields."""

    def test_stores_all_fields(self):
        """Tests that all fields are stored on the exception."""
        err = TransformationAlreadyExistsError(
            "duplicate",
            original_hash="aa" * 32,
            new_hash="bb" * 32,
            existing_description="already done",
        )
        assert err.original_hash == "aa" * 32
        assert err.new_hash == "bb" * 32
        assert err.existing_description == "already done"
        assert "duplicate" in str(err)

    def test_inherits_from_chain_error(self):
        """Tests that TransformationAlreadyExistsError is a ChainError."""
        from swarm_provenance_uploader.exceptions import ChainError, ProvenanceError

        err = TransformationAlreadyExistsError("test")
        assert isinstance(err, ChainError)
        assert isinstance(err, ProvenanceError)

    def test_fields_default_to_none(self):
        """Tests that optional fields default to None."""
        err = TransformationAlreadyExistsError("test")
        assert err.original_hash is None
        assert err.new_hash is None
        assert err.existing_description is None


class TestMergeTransformResultModel:
    """Tests for MergeTransformResult Pydantic model."""

    def test_creation_and_serialization(self):
        """Tests model creation and dump."""
        result = MergeTransformResult(
            tx_hash="0x" + "ab" * 32,
            block_number=100,
            gas_used=50000,
            explorer_url="https://example.com/tx/0xab",
            source_hashes=[DUMMY_HASH, "b" * 64],
            new_hash="c" * 64,
            description="merged datasets",
            new_data_type="combined",
        )
        data = result.model_dump()
        assert data["tx_hash"] == "0x" + "ab" * 32
        assert data["source_hashes"] == [DUMMY_HASH, "b" * 64]
        assert data["new_hash"] == "c" * 64
        assert data["description"] == "merged datasets"
        assert data["new_data_type"] == "combined"

    def test_explorer_url_optional(self):
        """Tests that explorer_url can be None."""
        result = MergeTransformResult(
            tx_hash="0x" + "ab" * 32,
            block_number=100,
            gas_used=50000,
            explorer_url=None,
            source_hashes=[DUMMY_HASH, "b" * 64],
            new_hash="c" * 64,
            description="merged",
            new_data_type="merged",
        )
        assert result.explorer_url is None


def _hex_hash(n):
    """A distinct 64-char hex hash for node n."""
    return f"{n:064x}"


def _mock_v2_graph(mock_chain_deps, children, registered=None, fail=None):
    """Mock a v2 contract whose transformation graph is ``children``.

    ``children`` maps a hash to its child hashes; parents are derived from it.
    ``registered`` is the set of registered hashes (default: every hash in
    the graph). ``fail`` maps (function name, hash) to the exception that
    function raises for that hash.
    """
    fail = fail or {}
    parents = {}
    for parent, kids in children.items():
        for kid in kids:
            parents.setdefault(kid, []).append(parent)
    nodes = set(children) | set(parents)
    registered = nodes if registered is None else set(registered)
    functions = mock_chain_deps["contract"].functions

    def _call(name, data_hash, value):
        mock_call = MagicMock()
        error = fail.get((name, data_hash.hex()))
        if error is not None:
            mock_call.call.side_effect = error
        else:
            mock_call.call.return_value = value
        return mock_call

    def get_data_record(data_hash):
        h = data_hash.hex()
        owner = DUMMY_ADDRESS if h in registered else ZERO_ADDRESS
        return _call(
            "getDataRecord", data_hash,
            (data_hash, owner, 1700000000, "swarm-provenance", b"\x00" * 32,
             [(bytes.fromhex(k), "step") for k in children.get(h, [])], [], 0),
        )

    def get_links(data_hash):
        h = data_hash.hex()
        return _call(
            "getTransformationLinks", data_hash,
            [(bytes.fromhex(k), "step") for k in children.get(h, [])],
        )

    def get_parents(data_hash):
        h = data_hash.hex()
        return _call(
            "getTransformationParents", data_hash,
            [bytes.fromhex(p) for p in parents.get(h, [])],
        )

    functions.getDataRecord = get_data_record
    functions.getTransformationLinks = get_links
    functions.getTransformationParents = get_parents


class TestProvenanceChainFailClosed:
    """A read error during traversal fails the whole walk (#170)."""

    def _chain(self, mock_chain_deps, children, start, **kwargs):
        from swarm_provenance_uploader.core.chain_client import ChainClient

        _mock_v2_graph(mock_chain_deps, children, registered=kwargs.pop("registered", None),
                       fail=kwargs.pop("fail", None))
        client = ChainClient(chain="base-sepolia")
        return client.get_provenance_chain(swarm_hash=start, **kwargs)

    def test_parents_read_error_fails_closed(self, mock_chain_deps):
        """An RPC error reading a child's parents raises; no partial chain."""
        import requests

        a, b, c = _hex_hash(1), _hex_hash(2), _hex_hash(3)
        with pytest.raises(ChainConnectionError) as exc_info:
            self._chain(
                mock_chain_deps, {a: [b], b: [c]}, a,
                fail={("getTransformationParents", b):
                      requests.exceptions.ConnectionError("connection refused")},
            )
        message = str(exc_info.value)
        assert b in message
        assert "depth 1" in message
        assert "connection refused" in message

    def test_links_read_error_fails_closed(self, mock_chain_deps):
        """An RPC error reading a node's transformation links raises."""
        import requests

        a, b = _hex_hash(1), _hex_hash(2)
        with pytest.raises(ChainConnectionError) as exc_info:
            self._chain(
                mock_chain_deps, {a: [b]}, a,
                fail={("getTransformationLinks", a): requests.exceptions.Timeout("read timed out")},
            )
        assert a in str(exc_info.value)
        assert "depth 0" in str(exc_info.value)

    def test_linked_record_read_error_fails_closed(self, mock_chain_deps):
        """An RPC error reading a linked node's record raises."""
        a, b = _hex_hash(1), _hex_hash(2)
        with pytest.raises(ChainConnectionError) as exc_info:
            self._chain(
                mock_chain_deps, {a: [b]}, a,
                fail={("getDataRecord", b): OSError("network unreachable")},
            )
        assert b in str(exc_info.value)

    def test_non_rpc_error_fails_closed_as_chain_error(self, mock_chain_deps):
        """A failure that is not an RPC failure raises ChainError, not a raw exception."""
        from swarm_provenance_uploader.exceptions import ChainError

        a, b = _hex_hash(1), _hex_hash(2)
        with pytest.raises(ChainError) as exc_info:
            self._chain(
                mock_chain_deps, {a: [b]}, a,
                fail={("getTransformationParents", b): ValueError("could not decode")},
            )
        assert not isinstance(exc_info.value, ChainConnectionError)
        assert "could not decode" in str(exc_info.value)

    def test_error_message_redacts_rpc_url(self, mock_chain_deps):
        """A key in an RPC URL repeated by the error is not in the message."""
        a, b = _hex_hash(1), _hex_hash(2)
        with pytest.raises(ChainConnectionError) as exc_info:
            self._chain(
                mock_chain_deps, {a: [b]}, a,
                fail={("getTransformationParents", b): OSError(
                    "failed: https://rpc.example.org/v2/SECRETKEY123")},
            )
        assert "SECRETKEY123" not in str(exc_info.value)
        # The original stays as a redacted cause (#187): the key is not in
        # any linked exception
        from swarm_provenance_uploader.chain.exceptions import RedactedException

        assert isinstance(exc_info.value.__cause__, RedactedException)
        for text in _chain_texts(exc_info.value):
            assert "SECRETKEY123" not in text, text

    def test_linked_hash_not_registered_fails_closed(self, mock_chain_deps):
        """A linked hash that reads as not registered is an inconsistent read."""
        from swarm_provenance_uploader.exceptions import ChainError

        a, b = _hex_hash(1), _hex_hash(2)
        with pytest.raises(ChainError) as exc_info:
            self._chain(mock_chain_deps, {a: [b]}, a, registered={a})
        assert not isinstance(exc_info.value, DataNotRegisteredError)
        assert b in str(exc_info.value)
        assert "not registered" in str(exc_info.value)

    def test_unregistered_start_hash_returns_empty(self, mock_chain_deps):
        """Only the start hash may be unregistered: the walk returns []."""
        a = _hex_hash(1)
        assert self._chain(mock_chain_deps, {a: []}, a, registered=set()) == []

    def test_parents_filled_on_expanded_nodes(self, mock_chain_deps):
        """Each expanded node carries its parent hashes."""
        a, b, c = _hex_hash(1), _hex_hash(2), _hex_hash(3)
        # a and b are both merged into c
        chain = self._chain(mock_chain_deps, {a: [c], b: [c]}, c)
        by_hash = {r.data_hash: r for r in chain}
        assert set(by_hash) == {a, b, c}
        assert sorted(by_hash[c].parents) == sorted([a, b])
        assert by_hash[a].parents == []
        assert by_hash[b].parents == []

    def test_node_at_depth_limit_has_no_parents(self, mock_chain_deps):
        """A node at max_depth is returned but not expanded: parents is None."""
        a, b, c = _hex_hash(1), _hex_hash(2), _hex_hash(3)
        chain = self._chain(mock_chain_deps, {a: [b], b: [c]}, a, max_depth=1)
        assert [r.data_hash for r in chain] == [a, b]
        assert chain[0].parents == []
        assert chain[1].parents is None

    def test_node_at_depth_limit_does_not_read_parents(self, mock_chain_deps):
        """An error on a node beyond the limit's expansion does not matter."""
        a, b = _hex_hash(1), _hex_hash(2)
        chain = self._chain(
            mock_chain_deps, {a: [b]}, a, max_depth=1,
            fail={("getTransformationParents", b): OSError("not read")},
        )
        assert [r.data_hash for r in chain] == [a, b]

    def test_prefixed_upper_case_start_hash_visited_once(self, mock_chain_deps):
        """A 0x-prefixed upper-case start hash is the same node as its child's parent."""
        a, b = "ab" * 32, "cd" * 32
        chain = self._chain(mock_chain_deps, {a: [b]}, "0x" + a.upper())
        assert [r.data_hash for r in chain] == [a, b]
        assert chain[0].parents == []
        assert chain[1].parents == [a]

    def test_default_depth_is_10(self, mock_chain_deps):
        """max_depth=None walks 10 levels: 11 nodes of a 13-node line."""
        nodes = [_hex_hash(n) for n in range(1, 14)]
        children = {nodes[i]: [nodes[i + 1]] for i in range(len(nodes) - 1)}
        chain = self._chain(mock_chain_deps, children, nodes[0], max_depth=None)
        assert [r.data_hash for r in chain] == nodes[:11]

    def test_depth_50_is_accepted(self, mock_chain_deps):
        """max_depth=50 is the largest accepted value."""
        a = _hex_hash(1)
        assert len(self._chain(mock_chain_deps, {a: []}, a, max_depth=50)) == 1

    @pytest.mark.parametrize("depth", [-1, 51, 1000])
    def test_depth_out_of_range_rejected(self, mock_chain_deps, depth):
        """max_depth below 0 or above 50 raises ChainValidationError, before any read."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")
        client._contract.get_data_record = MagicMock()
        with pytest.raises(ChainValidationError):
            client.get_provenance_chain(swarm_hash=DUMMY_HASH, max_depth=depth)
        client._contract.get_data_record.assert_not_called()


class TestProvenanceChainFailClosedEventPaths:
    """The v1 event paths fail closed too (#170)."""

    def _v1_client(self, mock_chain_deps, deploy_block):
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")
        client._contract._supports_v2 = False
        client._provider.deploy_block = deploy_block
        # A short chain: the per-node window reaches block 0 (#231)
        mock_chain_deps["web3_instance"].eth.block_number = 1_000
        return client

    def test_per_node_forward_query_error_fails_closed(self, mock_chain_deps):
        """Per-node scan: a failed DataTransformed query from a node raises."""
        client = self._v1_client(mock_chain_deps, None)
        client._contract.get_transformations_from = MagicMock(side_effect=OSError("timeout"))
        client._contract.get_transformations_to = MagicMock(return_value=[])
        with pytest.raises(ChainConnectionError):
            client.get_provenance_chain(swarm_hash=DUMMY_HASH)

    def test_per_node_reverse_query_error_fails_closed(self, mock_chain_deps):
        """Per-node scan: a failed reverse DataTransformed query raises."""
        client = self._v1_client(mock_chain_deps, None)
        client._contract.get_transformations_from = MagicMock(return_value=[])
        client._contract.get_transformations_to = MagicMock(side_effect=OSError("timeout"))
        with pytest.raises(ChainConnectionError):
            client.get_provenance_chain(swarm_hash=DUMMY_HASH)

    def test_per_node_parents_filled(self, mock_chain_deps):
        """Per-node scan: parents come from the reverse query."""
        parent = "c" * 64
        client = self._v1_client(mock_chain_deps, None)
        client._contract.get_transformations_from = MagicMock(return_value=[])
        client._contract.get_transformations_to = MagicMock(
            side_effect=lambda h, **kw: [(bytes.fromhex(parent), bytes.fromhex(h), "step")]
            if h == DUMMY_HASH else []
        )
        chain = client.get_provenance_chain(swarm_hash=DUMMY_HASH, max_depth=1)
        assert chain[0].parents == [parent]

    def test_local_index_parents_filled(self, mock_chain_deps):
        """Event index: parents come from the reverse map."""
        from swarm_provenance_uploader.chain.event_cache import clear_registry

        clear_registry()
        parent = "c" * 64
        mock_cache = MagicMock()
        mock_cache.get_maps.return_value = ({}, {DUMMY_HASH: [(parent, "step")]})
        with patch("swarm_provenance_uploader.chain.event_cache.get_cache", return_value=mock_cache):
            client = self._v1_client(mock_chain_deps, 0)
            chain = client.get_provenance_chain(swarm_hash=DUMMY_HASH, max_depth=1)
        assert chain[0].data_hash == DUMMY_HASH
        assert chain[0].parents == [parent]


    def test_local_index_prefixed_upper_case_start_hash(self, mock_chain_deps):
        """Event index: a 0x-prefixed upper-case start hash finds its edges, once."""
        from swarm_provenance_uploader.chain.event_cache import clear_registry

        clear_registry()
        a, b = "ab" * 32, "cd" * 32

        def get_data_record(data_hash):
            mock_call = MagicMock()
            mock_call.call.return_value = (
                data_hash, DUMMY_ADDRESS, 1700000000, "swarm-provenance",
                b"\x00" * 32, [], [], 0,
            )
            return mock_call

        mock_chain_deps["contract"].functions.getDataRecord = get_data_record
        mock_cache = MagicMock()
        mock_cache.get_maps.return_value = ({a: [(b, "step")]}, {b: [(a, "step")]})
        with patch("swarm_provenance_uploader.chain.event_cache.get_cache", return_value=mock_cache):
            client = self._v1_client(mock_chain_deps, 0)
            chain = client.get_provenance_chain(swarm_hash="0x" + a.upper())
        assert [r.data_hash for r in chain] == [a, b]
        assert chain[0].parents == []
        assert chain[1].parents == [a]


class TestTraversalErrorWithWeb3:
    """How real web3 errors are classified when a walk fails (#170).

    Runs without mock_chain_deps, which replaces web3 with a MagicMock.
    """

    def test_rpc_errors_become_connection_errors(self):
        web3_exceptions = pytest.importorskip("web3.exceptions")
        from swarm_provenance_uploader.core.chain_client import _traversal_error

        for error in (
            web3_exceptions.RequestTimedOut("timed out"),
            web3_exceptions.ProviderConnectionError("down"),
            web3_exceptions.TimeExhausted("slow"),
            web3_exceptions.BadResponseFormat("not JSON-RPC"),
        ):
            result = _traversal_error(DUMMY_HASH, 2, error)
            assert isinstance(result, ChainConnectionError), type(error)
            assert DUMMY_HASH in str(result)
            assert "depth 2" in str(result)

    def test_json_rpc_rejection_becomes_configuration_error(self):
        """The node answered and refused: not a connection failure, so no fallback (#168 review 4)."""
        web3_exceptions = pytest.importorskip("web3.exceptions")
        from swarm_provenance_uploader.core.chain_client import _traversal_error

        result = _traversal_error(DUMMY_HASH, 2, web3_exceptions.Web3RPCError("limit exceeded"))
        assert isinstance(result, ChainConfigurationError)
        assert not isinstance(result, ChainConnectionError)
        assert DUMMY_HASH in str(result)
        assert "depth 2" in str(result)
        assert "limit exceeded" in str(result)

    def test_revert_becomes_chain_error(self):
        web3_exceptions = pytest.importorskip("web3.exceptions")
        from swarm_provenance_uploader.core.chain_client import _traversal_error
        from swarm_provenance_uploader.exceptions import ChainError

        result = _traversal_error(
            DUMMY_HASH, 0, web3_exceptions.ContractLogicError("execution reverted")
        )
        assert isinstance(result, ChainError)
        assert not isinstance(result, ChainConnectionError)
        assert "execution reverted" in str(result)


class TestABIV2Functions:
    """Tests that the bundled ABI includes v2 functions."""

    def test_abi_has_v2_functions(self):
        """Tests that the ABI includes v2-specific functions."""
        from swarm_provenance_uploader.chain.contract import _load_abi

        abi = _load_abi()
        func_names = [e["name"] for e in abi if e.get("type") == "function"]

        assert "getTransformationLinks" in func_names
        assert "getTransformationParents" in func_names
        assert "getChildHashes" in func_names
        assert "recordMergeTransformation" in func_names

    def test_abi_has_data_merged_event(self):
        """Tests that the ABI includes the DataMerged event."""
        from swarm_provenance_uploader.chain.contract import _load_abi

        abi = _load_abi()
        event_names = [e["name"] for e in abi if e.get("type") == "event"]

        assert "DataMerged" in event_names


class TestInsufficientFundsError:
    """Tests for the InsufficientFundsError exception class."""

    def test_inherits_from_chain_transaction_error(self):
        """Tests that InsufficientFundsError is a subclass of ChainTransactionError."""
        err = InsufficientFundsError("low funds")
        assert isinstance(err, ChainTransactionError)
        assert isinstance(err, InsufficientFundsError)

    def test_carries_structured_data(self):
        """Tests that exception carries wallet, balance, cost, and chain info."""
        err = InsufficientFundsError(
            "low funds",
            wallet_address=DUMMY_ADDRESS,
            balance_wei=500,
            estimated_cost_wei=1000,
            chain_name="base-sepolia",
        )
        assert err.wallet_address == DUMMY_ADDRESS
        assert err.balance_wei == 500
        assert err.estimated_cost_wei == 1000
        assert err.chain_name == "base-sepolia"
        assert err.tx_hash is None

    def test_caught_by_chain_transaction_error_handler(self):
        """Tests backward compatibility — caught by existing ChainTransactionError handlers."""
        with pytest.raises(ChainTransactionError):
            raise InsufficientFundsError("low funds")


class TestPreflightBalanceCheck:
    """Tests for the pre-flight balance check in ChainClient."""

    def test_zero_balance_raises(self, mock_chain_deps):
        """Tests that zero balance raises InsufficientFundsError."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        mock_chain_deps["web3_instance"].eth.get_balance.return_value = 0

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(InsufficientFundsError) as exc_info:
            client._check_balance(estimated_cost_wei=100_000_000_000_000)
        assert exc_info.value.wallet_address == DUMMY_ADDRESS
        assert exc_info.value.balance_wei == 0
        assert exc_info.value.chain_name == "base-sepolia"

    def test_below_cost_raises(self, mock_chain_deps):
        """Tests that balance below estimated cost raises InsufficientFundsError."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Balance is 0.0001 ETH, cost is 0.001 ETH
        mock_chain_deps["web3_instance"].eth.get_balance.return_value = 100_000_000_000_000

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(InsufficientFundsError) as exc_info:
            client._check_balance(estimated_cost_wei=1_000_000_000_000_000)
        assert exc_info.value.estimated_cost_wei == 1_000_000_000_000_000

    def test_above_cost_passes(self, mock_chain_deps):
        """Tests that sufficient balance does not raise."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Balance is 1 ETH (default in fixture)
        client = ChainClient(chain="base-sepolia")
        # Should not raise
        client._check_balance(estimated_cost_wei=100_000_000_000_000)

    def test_low_balance_warns(self, mock_chain_deps, capsys):
        """Tests that balance above cost but below LOW_BALANCE_WEI logs a warning."""
        from swarm_provenance_uploader.core.chain_client import ChainClient, LOW_BALANCE_WEI

        # Balance is 0.0005 ETH — above MIN but below LOW
        mock_chain_deps["web3_instance"].eth.get_balance.return_value = 500_000_000_000_000

        client = ChainClient(chain="base-sepolia")
        # Should not raise, but should warn
        client._check_balance(estimated_cost_wei=100_000_000_000_000)
        captured = capsys.readouterr()
        assert "WARNING" in captured.err or "Low balance" in captured.err

    def test_send_transaction_preflight_raises(self, mock_chain_deps):
        """Tests that _send_transaction raises InsufficientFundsError on low balance."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Set balance to 0
        mock_chain_deps["web3_instance"].eth.get_balance.return_value = 0

        # Pre-check: hash not registered (so anchor proceeds to _send_transaction)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(InsufficientFundsError) as exc_info:
            client.anchor(swarm_hash=DUMMY_HASH)
        assert exc_info.value.wallet_address == DUMMY_ADDRESS

    def test_send_transaction_detects_insufficient_funds_string(self, mock_chain_deps):
        """Tests that RPC 'insufficient funds' errors are converted to InsufficientFundsError."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Balance is enough for pre-flight check
        mock_chain_deps["web3_instance"].eth.get_balance.return_value = 1_000_000_000_000_000_000

        # Pre-check: hash not registered
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
        )

        # Make send_raw_transaction raise with "insufficient funds" message
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.side_effect = Exception(
            "insufficient funds for gas * price + value"
        )

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(InsufficientFundsError) as exc_info:
            client.anchor(swarm_hash=DUMMY_HASH)
        assert exc_info.value.wallet_address == DUMMY_ADDRESS
        assert exc_info.value.chain_name == "base-sepolia"


class TestChainPresetFundUrls:
    """Tests that CHAIN_PRESETS include faucet/bridge URLs."""

    def test_base_sepolia_has_faucet(self):
        """Tests that base-sepolia preset has a faucet URL."""
        from swarm_provenance_uploader.chain.provider import CHAIN_PRESETS

        preset = CHAIN_PRESETS["base-sepolia"]
        assert preset["faucet_url"] is not None
        assert "faucet" in preset["faucet_url"] or "sepolia" in preset["faucet_url"]
        assert preset["bridge_url"] is None

    def test_base_has_bridge(self):
        """Tests that base mainnet preset has a bridge URL."""
        from swarm_provenance_uploader.chain.provider import CHAIN_PRESETS

        preset = CHAIN_PRESETS["base"]
        assert preset["bridge_url"] is not None
        assert "bridge" in preset["bridge_url"]
        assert preset["faucet_url"] is None

    def test_localhost_has_neither(self):
        """Tests that localhost preset has no faucet or bridge URL."""
        from swarm_provenance_uploader.chain.provider import CHAIN_PRESETS

        preset = CHAIN_PRESETS["localhost"]
        assert preset["faucet_url"] is None
        assert preset["bridge_url"] is None


# ============================================================
# Write confirmation: contract code and emitted events (#166)
# ============================================================

# (method, kwargs, expected event) for every write the client sends
WRITES = [
    ("anchor", {"swarm_hash": DUMMY_HASH}, "DataRegistered"),
    ("anchor_for", {"swarm_hash": DUMMY_HASH, "owner": DUMMY_ADDRESS}, "DataRegistered"),
    ("batch_anchor", {"swarm_hashes": [DUMMY_HASH], "data_types": ["t"]}, "DataRegistered"),
    ("set_storage_ref", {"data_hash": DUMMY_HASH, "storage_ref": "b" * 64}, "StorageRefLinked"),
    ("transform", {"original_hash": DUMMY_HASH, "new_hash": "b" * 64, "description": "d"}, "DataTransformed"),
    ("access", {"swarm_hash": DUMMY_HASH}, "DataAccessed"),
    ("batch_access", {"swarm_hashes": [DUMMY_HASH]}, "DataAccessed"),
    ("set_status", {"swarm_hash": DUMMY_HASH, "status": 1}, "DataStatusChanged"),
    ("batch_set_status", {"swarm_hashes": [DUMMY_HASH], "statuses": [1]}, "DataStatusChanged"),
    ("transfer_ownership", {"swarm_hash": DUMMY_HASH, "new_owner": OTHER_ADDRESS}, "DataOwnershipTransferred"),
    ("set_delegate", {"delegate": OTHER_ADDRESS}, "DelegateAuthorized"),
    ("merge_transform", {"source_hashes": [DUMMY_HASH, "c" * 64], "new_hash": "b" * 64, "description": "d"}, "DataMerged"),
]


def _write_client(mock_chain_deps, logs):
    """A client whose next receipt has status 1 and the given logs."""
    from swarm_provenance_uploader.core.chain_client import ChainClient

    # anchor/anchor_for pre-read: hash not registered yet
    mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
        DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
    )
    mock_chain_deps["contract"].functions.recordMergeTransformation.return_value.build_transaction.return_value = {
        "from": DUMMY_ADDRESS,
        "to": DUMMY_CONTRACT,
        "data": "0x",
    }
    receipt = mock_chain_deps["web3_instance"].eth.wait_for_transaction_receipt.return_value
    receipt["logs"] = logs
    return ChainClient(chain="base-sepolia")


class TestWriteConfirmation:
    """A status-1 receipt only counts when the contract emitted the expected events."""

    @pytest.mark.parametrize("method,kwargs,event", WRITES, ids=[w[0] for w in WRITES])
    def test_expected_event_succeeds(self, mock_chain_deps, method, kwargs, event):
        """Each write succeeds when the contract emits its own event."""
        client = _write_client(mock_chain_deps, [_log(event)])
        result = getattr(client, method)(**kwargs)
        assert result.tx_hash == DUMMY_TX_HASH_BYTES.hex()

    @pytest.mark.parametrize("method,kwargs,event", WRITES, ids=[w[0] for w in WRITES])
    def test_no_logs_not_recorded(self, mock_chain_deps, method, kwargs, event):
        """Status 1 with no logs is reported as not recorded, with the tx hash."""
        from swarm_provenance_uploader.exceptions import TransactionNotRecordedError

        client = _write_client(mock_chain_deps, [])
        with pytest.raises(TransactionNotRecordedError) as exc_info:
            getattr(client, method)(**kwargs)

        err = exc_info.value
        assert err.tx_hash == DUMMY_TX_HASH_BYTES.hex()
        assert err.event_name == event
        assert err.expected_count == 1
        assert err.emitted_count == 0
        assert err.contract_address == DUMMY_CONTRACT
        assert DUMMY_TX_HASH_BYTES.hex() in err.explorer_url
        assert "not recorded" in str(err).lower()

    @pytest.mark.parametrize("method,kwargs,event", WRITES, ids=[w[0] for w in WRITES])
    def test_other_events_not_recorded(self, mock_chain_deps, method, kwargs, event):
        """Events of other kinds from the contract do not count."""
        from swarm_provenance_uploader.exceptions import TransactionNotRecordedError

        others = [_log(name) for name in WRITE_EVENTS if name != event]
        client = _write_client(mock_chain_deps, others)
        with pytest.raises(TransactionNotRecordedError):
            getattr(client, method)(**kwargs)

    @pytest.mark.parametrize("method,kwargs,event", WRITES, ids=[w[0] for w in WRITES])
    def test_event_from_other_address_not_recorded(self, mock_chain_deps, method, kwargs, event):
        """The right event emitted by another address does not count."""
        from swarm_provenance_uploader.exceptions import TransactionNotRecordedError

        client = _write_client(mock_chain_deps, [_log(event, address=OTHER_ADDRESS)])
        with pytest.raises(TransactionNotRecordedError) as exc_info:
            getattr(client, method)(**kwargs)
        assert exc_info.value.emitted_count == 0

    @pytest.mark.parametrize(
        "method,kwargs,event",
        [
            ("batch_anchor", {"swarm_hashes": [DUMMY_HASH, "b" * 64, "c" * 64], "data_types": ["t"] * 3}, "DataRegistered"),
            ("batch_access", {"swarm_hashes": [DUMMY_HASH, "b" * 64, "c" * 64]}, "DataAccessed"),
            ("batch_set_status", {"swarm_hashes": [DUMMY_HASH, "b" * 64, "c" * 64], "statuses": [1, 1, 2]}, "DataStatusChanged"),
        ],
        ids=["batch_anchor", "batch_access", "batch_set_status"],
    )
    def test_short_batch_not_recorded(self, mock_chain_deps, method, kwargs, event):
        """A batch with fewer events than items is reported as not recorded."""
        from swarm_provenance_uploader.exceptions import TransactionNotRecordedError

        client = _write_client(mock_chain_deps, [_log(event), _log(event)])
        with pytest.raises(TransactionNotRecordedError) as exc_info:
            getattr(client, method)(**kwargs)
        assert exc_info.value.expected_count == 3
        assert exc_info.value.emitted_count == 2

    @pytest.mark.parametrize(
        "error",
        [Exception("could not decode log"), AttributeError("no event DataAccessed in the ABI")],
        ids=["decode_error", "event_missing_from_abi"],
    )
    def test_events_not_verifiable(self, mock_chain_deps, error):
        """If the events cannot be decoded, the mined tx is not reported as failed."""
        from swarm_provenance_uploader.exceptions import (
            TransactionNotRecordedError,
            TransactionNotVerifiedError,
        )

        client = _write_client(mock_chain_deps, [_log("DataAccessed")])
        mock_chain_deps["contract"].events.DataAccessed.return_value.process_receipt.side_effect = error

        with pytest.raises(TransactionNotVerifiedError) as exc_info:
            client.access(swarm_hash=DUMMY_HASH)

        err = exc_info.value
        assert not isinstance(err, TransactionNotRecordedError)
        assert not hasattr(err, "emitted_count")
        assert err.reason == str(error)
        assert err.tx_hash == DUMMY_TX_HASH_BYTES.hex()
        assert DUMMY_TX_HASH_BYTES.hex() in err.explorer_url
        assert err.expected_count == 1
        assert "was mined" in str(err)
        assert "could not be verified" in str(err)
        assert "Transaction failed" not in str(err)

    def test_full_batch_succeeds(self, mock_chain_deps):
        """A batch with one event per item succeeds."""
        hashes = [DUMMY_HASH, "b" * 64, "c" * 64]
        client = _write_client(mock_chain_deps, [_log("DataAccessed")] * 3)
        result = client.batch_access(swarm_hashes=hashes)
        assert result.tx_hash == DUMMY_TX_HASH_BYTES.hex()

    def test_not_recorded_is_a_transaction_error(self):
        """Callers that catch ChainTransactionError still treat it as a failure."""
        from swarm_provenance_uploader.exceptions import TransactionNotRecordedError

        err = TransactionNotRecordedError("Not recorded", tx_hash="0xab")
        assert isinstance(err, ChainTransactionError)
        assert err.tx_hash == "0xab"
        assert isinstance(err.emitted_count, int)
        assert isinstance(err.expected_count, int)

    def test_unconfirmed_hierarchy(self):
        """Not recorded and not verified share a base class but are told apart by type."""
        from swarm_provenance_uploader import chain
        from swarm_provenance_uploader.exceptions import (
            TransactionNotRecordedError,
            TransactionNotVerifiedError,
            TransactionUnconfirmedError,
        )

        assert issubclass(TransactionUnconfirmedError, ChainTransactionError)
        assert issubclass(TransactionNotRecordedError, TransactionUnconfirmedError)
        assert issubclass(TransactionNotVerifiedError, TransactionUnconfirmedError)
        assert not issubclass(TransactionNotVerifiedError, TransactionNotRecordedError)
        assert not issubclass(TransactionNotRecordedError, TransactionNotVerifiedError)
        for name in (
            "TransactionUnconfirmedError",
            "TransactionNotRecordedError",
            "TransactionNotVerifiedError",
        ):
            assert name in chain.__all__ or not chain.BLOCKCHAIN_AVAILABLE

    @pytest.mark.parametrize("empty_code", [b"", bytes()])
    def test_empty_bytecode_refused_before_signing(self, mock_chain_deps, empty_code):
        """A write to an address without code is refused before anything is signed."""
        web3 = mock_chain_deps["web3_instance"]
        web3.eth.get_code.return_value = empty_code
        client = _write_client(mock_chain_deps, [_log("DataAccessed")])

        with pytest.raises(ChainConfigurationError) as exc_info:
            client.access(swarm_hash=DUMMY_HASH)

        assert "no contract code" in str(exc_info.value).lower()
        web3.eth.get_code.assert_called_once_with(DUMMY_CONTRACT)
        mock_chain_deps["account"].sign_transaction.assert_not_called()
        web3.eth.send_raw_transaction.assert_not_called()

    @pytest.mark.parametrize(
        "method,kwargs",
        [
            ("anchor", {"swarm_hash": DUMMY_HASH}),
            ("anchor_for", {"swarm_hash": DUMMY_HASH, "owner": DUMMY_ADDRESS}),
        ],
        ids=["anchor", "anchor_for"],
    )
    def test_anchor_empty_bytecode_reported_before_pre_read(self, mock_chain_deps, method, kwargs):
        """anchor's duplicate pre-read does not hide the "No contract code" error."""
        web3 = mock_chain_deps["web3_instance"]
        web3.eth.get_code.return_value = b""
        client = _write_client(mock_chain_deps, [])
        # What a read from an address without code does: nothing to decode
        functions = mock_chain_deps["contract"].functions
        functions.getDataRecord.return_value.call.side_effect = Exception(
            "Could not decode contract function call to getDataRecord with return data: b''"
        )
        functions.getTransformationLinks.return_value.call.side_effect = Exception("no code")
        functions.dataRecords.return_value.call.side_effect = Exception("no code")

        with pytest.raises(ChainConfigurationError) as exc_info:
            getattr(client, method)(**kwargs)

        assert "no contract code" in str(exc_info.value).lower()
        functions.getDataRecord.return_value.call.assert_not_called()
        mock_chain_deps["account"].sign_transaction.assert_not_called()

    def test_code_check_runs_once_per_client(self, mock_chain_deps):
        """The contract code is read once, before the first write only."""
        client = _write_client(mock_chain_deps, [_log("DataAccessed")])
        client.access(swarm_hash=DUMMY_HASH)
        client.access(swarm_hash=DUMMY_HASH)
        assert mock_chain_deps["web3_instance"].eth.get_code.call_count == 1

    def test_code_check_rpc_failure_is_connection_error(self, mock_chain_deps):
        """An RPC failure while reading the code is a connection error, not a send."""
        web3 = mock_chain_deps["web3_instance"]
        web3.eth.get_code.side_effect = ConnectionError("rpc down")
        client = _write_client(mock_chain_deps, [_log("DataAccessed")])

        with pytest.raises(ChainConnectionError) as exc_info:
            client.access(swarm_hash=DUMMY_HASH)
        assert exc_info.value.rpc_url == client._provider.rpc_url
        assert exc_info.value.rpc_url
        web3.eth.send_raw_transaction.assert_not_called()

    def test_code_check_non_json_response_is_connection_error(self, mock_chain_deps):
        """An HTTP 200 page that is not JSON-RPC is blamed on the RPC, not the contract."""
        import json as json_module

        web3 = mock_chain_deps["web3_instance"]
        web3.eth.get_code.side_effect = json_module.JSONDecodeError(
            "Expecting value", "<html>Bad gateway</html>", 0
        )
        client = _write_client(mock_chain_deps, [_log("DataAccessed")])

        with pytest.raises(ChainConnectionError) as exc_info:
            client.access(swarm_hash=DUMMY_HASH)
        assert exc_info.value.rpc_url == client._provider.rpc_url
        assert "RPC endpoint" in str(exc_info.value)
        web3.eth.send_raw_transaction.assert_not_called()

    def test_code_check_input_error_is_not_connection_error(self, mock_chain_deps):
        """An error that is not an RPC failure is not reported as a connection error."""
        web3 = mock_chain_deps["web3_instance"]
        web3.eth.get_code.side_effect = ValueError("invalid address")
        client = _write_client(mock_chain_deps, [_log("DataAccessed")])

        with pytest.raises(ChainConfigurationError) as exc_info:
            client.access(swarm_hash=DUMMY_HASH)
        assert not isinstance(exc_info.value, ChainConnectionError)
        web3.eth.send_raw_transaction.assert_not_called()

    def test_code_check_uses_checksummed_address(self, mock_chain_deps):
        """A lowercase contract address is checked, and matched, in checksum form."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        web3 = mock_chain_deps["web3_instance"]
        web3.to_checksum_address = (
            lambda x: DUMMY_CONTRACT if x.lower() == DUMMY_CONTRACT.lower() else x
        )
        receipt = web3.eth.wait_for_transaction_receipt.return_value
        receipt["logs"] = [_log("DataAccessed")]

        client = ChainClient(chain="base-sepolia", contract_address=DUMMY_CONTRACT.lower())
        result = client.access(swarm_hash=DUMMY_HASH)

        web3.eth.get_code.assert_called_once_with(DUMMY_CONTRACT)
        assert result.tx_hash == DUMMY_TX_HASH_BYTES.hex()

    def test_rpc_failure_classification_with_web3(self):
        """web3's RPC errors count as RPC failures; InvalidAddress does not."""
        web3_exceptions = pytest.importorskip("web3.exceptions")
        from swarm_provenance_uploader.core.chain_client import _is_rpc_failure

        assert _is_rpc_failure(web3_exceptions.Web3RPCError("boom"))
        assert _is_rpc_failure(web3_exceptions.ProviderConnectionError("down"))
        assert _is_rpc_failure(web3_exceptions.BadResponseFormat("not JSON-RPC"))
        assert _is_rpc_failure(ConnectionError("refused"))
        assert not _is_rpc_failure(web3_exceptions.InvalidAddress("bad"))
        assert not _is_rpc_failure(ValueError("bad"))


class TestCountReceiptEventsWithWeb3:
    """count_receipt_events decodes real logs with web3 (blockchain extra only)."""

    def _access_log(self, web3, address, log_index=0):
        from hexbytes import HexBytes

        topic = web3.keccak(text="DataAccessed(bytes32,address)")
        accessor = HexBytes(b"\x00" * 12 + bytes.fromhex(DUMMY_ADDRESS[2:]))
        return {
            "address": address,
            "topics": [topic, HexBytes(DUMMY_HASH_BYTES), accessor],
            "data": HexBytes(b""),
            "logIndex": log_index,
            "transactionIndex": 0,
            "transactionHash": HexBytes(DUMMY_TX_HASH_BYTES),
            "blockHash": HexBytes(b"\x01" * 32),
            "blockNumber": 1,
        }

    def test_counts_only_this_contract(self):
        """Logs from another address and logs of other events are not counted."""
        web3_module = pytest.importorskip("web3")
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        web3 = web3_module.Web3()
        contract = DataProvenanceContract(web3, DUMMY_CONTRACT)
        ours = web3.to_checksum_address(DUMMY_CONTRACT)
        other = web3.to_checksum_address(OTHER_ADDRESS)
        unrelated = dict(self._access_log(web3, ours, 3))
        unrelated["topics"] = [web3.keccak(text="Unrelated()")]

        receipt = {"logs": [
            self._access_log(web3, ours, 0),
            self._access_log(web3, other, 1),
            self._access_log(web3, ours, 2),
            unrelated,
        ]}

        assert contract.count_receipt_events("DataAccessed", receipt) == 2
        assert contract.count_receipt_events("DataRegistered", receipt) == 0


# Contract functions that build write transactions (build_transaction runs eth_estimateGas)
WRITE_FUNCTIONS = [
    "registerData", "registerDataFor", "batchRegisterData", "setStorageRef",
    "recordTransformation", "recordAccess", "batchRecordAccess", "setDataStatus",
    "batchSetDataStatus", "transferDataOwnership", "setDelegate",
    "recordMergeTransformation",
]


class _RecordingProvider:
    """Build a real web3 provider that records each JSON-RPC method it gets.

    It answers only the calls build_transaction makes, so the test runs the
    real web3 code that decides whether to run eth_estimateGas.
    """

    @staticmethod
    def make(web3_module):
        from web3.providers.base import BaseProvider

        answers = {
            "eth_chainId": hex(84532),
            "eth_gasPrice": hex(1_000_000_000),
            "eth_maxPriorityFeePerGas": hex(1_000_000_000),
            "eth_estimateGas": hex(100_000),
            "eth_getBlockByNumber": {
                "number": "0x1",
                "hash": "0x" + "11" * 32,
                "parentHash": "0x" + "22" * 32,
                "baseFeePerGas": "0x7",
                "gasLimit": hex(30_000_000),
                "gasUsed": "0x0",
                "timestamp": "0x1",
                "transactions": [],
            },
        }

        class RecordingProvider(BaseProvider):
            def __init__(self):
                super().__init__()
                self.methods = []

            def make_request(self, method, params):
                self.methods.append(method)
                return {"jsonrpc": "2.0", "id": 1, "result": answers[method]}

            def is_connected(self, show_traceback=False):
                return True

        return RecordingProvider()


# Each build_*_tx method of DataProvenanceContract, with arguments
BUILDERS = [
    ("build_register_data_tx", {"data_hash": DUMMY_HASH, "data_type": "t"}),
    ("build_register_data_for_tx", {"data_hash": DUMMY_HASH, "data_type": "t", "actual_owner": OTHER_ADDRESS}),
    ("build_batch_register_data_tx", {"data_hashes": [DUMMY_HASH], "data_types": ["t"]}),
    ("build_set_storage_ref_tx", {"data_hash": DUMMY_HASH, "storage_ref": "b" * 64}),
    ("build_record_transformation_tx", {"original_hash": DUMMY_HASH, "new_hash": "b" * 64, "description": "d"}),
    ("build_record_access_tx", {"data_hash": DUMMY_HASH}),
    ("build_batch_record_access_tx", {"data_hashes": [DUMMY_HASH]}),
    ("build_set_data_status_tx", {"data_hash": DUMMY_HASH, "status": 1}),
    ("build_batch_set_data_status_tx", {"data_hashes": [DUMMY_HASH], "statuses": [1]}),
    ("build_transfer_ownership_tx", {"data_hash": DUMMY_HASH, "new_owner": OTHER_ADDRESS}),
    ("build_set_delegate_tx", {"delegate": OTHER_ADDRESS, "authorized": True}),
    ("build_record_merge_transformation_tx", {"source_hashes": [DUMMY_HASH, "c" * 64], "new_hash": "b" * 64, "description": "d", "new_data_type": "t"}),
]


class TestBuildWithExplicitGas:
    """An explicit gas limit means web3 does not run eth_estimateGas (#180)."""

    def _contract(self):
        web3_module = pytest.importorskip("web3")
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        provider = _RecordingProvider.make(web3_module)
        web3 = web3_module.Web3(provider)
        return DataProvenanceContract(web3, DUMMY_CONTRACT), provider

    @pytest.mark.parametrize("builder,kwargs", BUILDERS, ids=[b[0] for b in BUILDERS])
    def test_explicit_gas_skips_estimate(self, builder, kwargs):
        contract, provider = self._contract()

        tx = getattr(contract, builder)(sender=DUMMY_ADDRESS, gas=500_000, **kwargs)

        assert tx["gas"] == 500_000
        assert "eth_estimateGas" not in provider.methods
        # web3 still fills in the fee fields
        assert "maxFeePerGas" in tx

    @pytest.mark.parametrize("builder,kwargs", BUILDERS, ids=[b[0] for b in BUILDERS])
    def test_without_gas_estimates(self, builder, kwargs):
        """Control: without a gas limit, web3 runs eth_estimateGas."""
        contract, provider = self._contract()

        tx = getattr(contract, builder)(sender=DUMMY_ADDRESS, **kwargs)

        assert tx["gas"] == 100_000
        assert "eth_estimateGas" in provider.methods


class TestClientPassesGasLimit:
    """ChainClient(gas_limit=N) gives N to build_transaction for every write (#180)."""

    @pytest.mark.parametrize(
        "write,function", list(zip(WRITES, WRITE_FUNCTIONS)), ids=[w[0] for w in WRITES]
    )
    def test_gas_limit_reaches_build_transaction(self, mock_chain_deps, write, function):
        from swarm_provenance_uploader.core.chain_client import ChainClient

        method, kwargs, event = write
        _write_client(mock_chain_deps, [_log(event)])
        client = ChainClient(chain="base-sepolia", gas_limit=500_000)

        getattr(client, method)(**kwargs)

        build = getattr(mock_chain_deps["contract"].functions, function).return_value.build_transaction
        assert build.call_args[0][0]["gas"] == 500_000
        tx = mock_chain_deps["account"].sign_transaction.call_args[0][0]
        assert tx["gas"] == 500_000
        mock_chain_deps["web3_instance"].eth.estimate_gas.assert_not_called()

    @pytest.mark.parametrize(
        "write,function", list(zip(WRITES, WRITE_FUNCTIONS)), ids=[w[0] for w in WRITES]
    )
    def test_no_gas_limit_leaves_gas_to_web3(self, mock_chain_deps, write, function):
        method, kwargs, event = write
        client = _write_client(mock_chain_deps, [_log(event)])

        getattr(client, method)(**kwargs)

        build = getattr(mock_chain_deps["contract"].functions, function).return_value.build_transaction
        assert "gas" not in build.call_args[0][0]


class ContractLogicError(Exception):
    """Stand-in for web3.exceptions.ContractLogicError (web3 is mocked here).

    Like web3's, str() is the (message, data) tuple and .message the reason.
    """

    def __init__(self, message, data="0x08c379a0" + "00" * 100):
        super().__init__(message, data)
        self.message = message
        self.data = data


class Web3RPCError(Exception):
    """Stand-in for web3.exceptions.Web3RPCError: the node answered with an error."""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class TestBuildTransactionErrors:
    """Errors while building a write (gas estimation) become chain errors (#175)."""

    def _fail_build(self, mock_chain_deps, error):
        client = _write_client(mock_chain_deps, [])
        for name in WRITE_FUNCTIONS:
            getattr(mock_chain_deps["contract"].functions, name).return_value.build_transaction.side_effect = error
        return client

    @pytest.mark.parametrize("method,kwargs,event", WRITES, ids=[w[0] for w in WRITES])
    def test_revert_in_gas_estimation(self, mock_chain_deps, method, kwargs, event):
        client = self._fail_build(
            mock_chain_deps, ContractLogicError("execution reverted: Not owner")
        )

        with pytest.raises(ChainTransactionError) as exc_info:
            getattr(client, method)(**kwargs)

        assert type(exc_info.value) is ChainTransactionError
        assert exc_info.value.tx_hash is None
        assert str(exc_info.value) == "Transaction reverted: execution reverted: Not owner"
        assert "0x08c379a0" not in str(exc_info.value)
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()

    @pytest.mark.parametrize("method,kwargs,event", WRITES, ids=[w[0] for w in WRITES])
    def test_rpc_failure_in_gas_estimation(self, mock_chain_deps, method, kwargs, event):
        import requests

        client = self._fail_build(
            mock_chain_deps, requests.exceptions.ConnectionError("connection refused")
        )

        with pytest.raises(ChainConnectionError) as exc_info:
            getattr(client, method)(**kwargs)

        assert "connection refused" in str(exc_info.value)
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()

    @pytest.mark.parametrize("method,kwargs,event", WRITES, ids=[w[0] for w in WRITES])
    def test_rpc_rejection_in_gas_estimation(self, mock_chain_deps, method, kwargs, event):
        """A JSON-RPC error answer is a rejected transaction, not a connection failure."""
        client = self._fail_build(mock_chain_deps, Web3RPCError("nonce too low"))

        with pytest.raises(ChainTransactionError) as exc_info:
            getattr(client, method)(**kwargs)

        assert type(exc_info.value) is ChainTransactionError
        assert exc_info.value.tx_hash is None
        assert str(exc_info.value) == "The RPC rejected the transaction: nonce too low"
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()

    def test_insufficient_funds_in_gas_estimation(self, mock_chain_deps):
        client = self._fail_build(
            mock_chain_deps, Exception("insufficient funds for gas * price + value")
        )

        with pytest.raises(InsufficientFundsError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert exc_info.value.wallet_address == DUMMY_ADDRESS
        assert exc_info.value.tx_hash is None

    def test_other_error_in_build(self, mock_chain_deps):
        """Any other error becomes ChainTransactionError, without a doubled prefix."""
        client = self._fail_build(mock_chain_deps, TypeError("unexpected argument"))

        with pytest.raises(ChainTransactionError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert str(exc_info.value) == "Could not build the transaction: unexpected argument"
        assert exc_info.value.tx_hash is None

    def test_validation_error_unchanged(self, mock_chain_deps):
        """A chain error raised while building passes through as it is."""
        client = _write_client(mock_chain_deps, [])

        with pytest.raises(ChainValidationError):
            client.set_status(swarm_hash="not-a-hash", status=1)

    def test_anchor_already_registered_in_gas_estimation(self, mock_chain_deps):
        """An "already registered" revert during gas estimation is still detected."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        records = iter([
            (DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0),
            (DUMMY_HASH_BYTES, DUMMY_ADDRESS, 1700000000, "swarm-provenance", b"\x00" * 32, [], [], 0),
        ])

        def get_data_record(data_hash):
            call = MagicMock()
            call.call.return_value = next(records)
            return call

        mock_chain_deps["contract"].functions.getDataRecord = get_data_record
        mock_chain_deps["contract"].functions.registerData.return_value.build_transaction.side_effect = (
            ContractLogicError("execution reverted: Data already registered")
        )

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(DataAlreadyRegisteredError) as exc_info:
            client.anchor(swarm_hash=DUMMY_HASH)
        assert exc_info.value.owner == DUMMY_ADDRESS


def test_is_contract_revert_with_web3_classes():
    """The real web3 revert classes are recognized, and other errors are not."""
    web3_exceptions = pytest.importorskip("web3.exceptions")
    from swarm_provenance_uploader.core.chain_client import _is_contract_revert

    assert _is_contract_revert(web3_exceptions.ContractLogicError("execution reverted"))
    assert _is_contract_revert(web3_exceptions.ContractCustomError("0x1234"))
    assert _is_contract_revert(web3_exceptions.ContractPanicError("panic"))
    assert not _is_contract_revert(ValueError("execution reverted"))


def test_build_tx_revert_reason_with_web3_class():
    """The real ContractLogicError reports its reason, not the (message, data) tuple."""
    web3_exceptions = pytest.importorskip("web3.exceptions")
    from swarm_provenance_uploader.core.chain_client import ChainClient

    def build():
        raise web3_exceptions.ContractLogicError(
            "execution reverted: Not owner", data="0x08c379a0" + "00" * 100
        )

    with pytest.raises(ChainTransactionError) as exc_info:
        ChainClient._build_tx(MagicMock(_gas_limit=None), build)

    assert "Not owner" in str(exc_info.value)
    assert "0x08c379a0" not in str(exc_info.value)


def test_build_tx_rpc_errors_with_web3_classes():
    """With the real web3 classes, a JSON-RPC error is a rejection and a transport error is not."""
    web3_exceptions = pytest.importorskip("web3.exceptions")
    from swarm_provenance_uploader.core.chain_client import ChainClient

    def failing(error):
        def build():
            raise error
        return build

    rejection = web3_exceptions.Web3RPCError(
        "nonce too low", rpc_response={"error": {"code": -32000, "message": "nonce too low"}}
    )
    with pytest.raises(ChainTransactionError) as exc_info:
        ChainClient._build_tx(MagicMock(_gas_limit=None), failing(rejection))
    assert type(exc_info.value) is ChainTransactionError
    assert "The RPC rejected the transaction: nonce too low" in str(exc_info.value)

    for transport in (
        web3_exceptions.ProviderConnectionError("refused"),
        web3_exceptions.TimeExhausted("timeout"),
        web3_exceptions.BadResponseFormat("bad"),
        json.JSONDecodeError("Expecting value", "<html>", 0),
    ):
        with pytest.raises(ChainConnectionError):
            ChainClient._build_tx(MagicMock(_gas_limit=None), failing(transport))


class TestSendTransactionRevertReason:
    """A revert in _send_transaction's own gas estimation shows the reason (#175)."""

    def test_estimate_gas_revert_reason(self, mock_chain_deps):
        client = _write_client(mock_chain_deps, [])
        mock_chain_deps["web3_instance"].eth.estimate_gas.side_effect = ContractLogicError(
            "execution reverted: Not owner"
        )

        with pytest.raises(ChainTransactionError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        # No "Transaction failed:" prefix: the CLI adds it
        assert str(exc_info.value) == "execution reverted: Not owner"
        assert "0x08c379a0" not in str(exc_info.value)

    def test_revert_mentioning_insufficient_funds_stays_a_revert(self, mock_chain_deps):
        client = _write_client(mock_chain_deps, [])
        mock_chain_deps["web3_instance"].eth.estimate_gas.side_effect = ContractLogicError(
            "execution reverted: insufficient funds in vault"
        )

        with pytest.raises(ChainTransactionError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert not isinstance(exc_info.value, InsufficientFundsError)
        assert str(exc_info.value) == "execution reverted: insufficient funds in vault"

    def test_insufficient_funds_message_has_no_tuple(self, mock_chain_deps):
        client = _write_client(mock_chain_deps, [])
        mock_chain_deps["web3_instance"].eth.estimate_gas.side_effect = Web3RPCError(
            "{'code': -32000, 'message': 'insufficient funds for gas * price + value'}"
        )

        with pytest.raises(InsufficientFundsError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert str(exc_info.value) == "Insufficient funds for gas: insufficient funds for gas * price + value"

    def test_send_error_without_arguments(self, mock_chain_deps):
        """An exception with no arguments is named, not reported as an empty message."""
        class Boom(Exception):
            pass

        client = _write_client(mock_chain_deps, [])
        mock_chain_deps["web3_instance"].eth.estimate_gas.side_effect = Boom()

        with pytest.raises(ChainTransactionError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert str(exc_info.value) == "Boom"

    def test_build_error_without_arguments(self, mock_chain_deps):
        class Boom(Exception):
            pass

        client = _write_client(mock_chain_deps, [])
        mock_chain_deps["contract"].functions.setDataStatus.return_value.build_transaction.side_effect = Boom()

        with pytest.raises(ChainTransactionError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert str(exc_info.value) == "Could not build the transaction: Boom"

    def test_other_send_error_has_no_prefix(self, mock_chain_deps):
        client = _write_client(mock_chain_deps, [])
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.side_effect = Exception("nonce too low")

        with pytest.raises(ChainTransactionError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert str(exc_info.value) == "nonce too low"

    def test_estimate_gas_already_registered(self, mock_chain_deps):
        """anchor still detects an "already registered" revert from estimate_gas."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        records = iter([
            (DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0),
            (DUMMY_HASH_BYTES, DUMMY_ADDRESS, 1700000000, "swarm-provenance", b"\x00" * 32, [], [], 0),
        ])

        def get_data_record(data_hash):
            call = MagicMock()
            call.call.return_value = next(records)
            return call

        mock_chain_deps["contract"].functions.getDataRecord = get_data_record
        mock_chain_deps["web3_instance"].eth.estimate_gas.side_effect = ContractLogicError(
            "execution reverted: Data already registered"
        )

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(DataAlreadyRegisteredError):
            client.anchor(swarm_hash=DUMMY_HASH)


def test_error_reason_with_web3_classes():
    """_error_reason returns the message of web3's revert and JSON-RPC errors."""
    web3_exceptions = pytest.importorskip("web3.exceptions")
    from swarm_provenance_uploader.core.chain_client import _error_reason

    revert = web3_exceptions.ContractLogicError(
        "execution reverted: Not owner", data="0x08c379a0" + "00" * 100
    )
    assert _error_reason(revert) == "execution reverted: Not owner"

    # As web3 raises it: the message is the repr of the JSON-RPC error object
    error = {"code": -32000, "message": "nonce too low"}
    with_response = web3_exceptions.Web3RPCError(str(error), rpc_response={"error": error})
    assert _error_reason(with_response) == "nonce too low"
    without_response = web3_exceptions.Web3RPCError(str(error))
    assert _error_reason(without_response) == "nonce too low"

    assert _error_reason(ValueError("plain")) == "plain"


def test_build_tx_rejection_text_and_timeout_with_web3_classes():
    """A rejection shows only the node's message; RequestTimedOut is a connection problem."""
    web3_exceptions = pytest.importorskip("web3.exceptions")
    from swarm_provenance_uploader.core.chain_client import ChainClient

    def failing(error):
        def build():
            raise error
        return build

    error = {"code": -32000, "message": "nonce too low"}
    rejection = web3_exceptions.Web3RPCError(str(error), rpc_response={"error": error})
    with pytest.raises(ChainTransactionError) as exc_info:
        ChainClient._build_tx(MagicMock(_gas_limit=None), failing(rejection))
    assert str(exc_info.value) == "The RPC rejected the transaction: nonce too low"

    timeout = web3_exceptions.RequestTimedOut("request timed out")
    with pytest.raises(ChainConnectionError):
        ChainClient._build_tx(MagicMock(_gas_limit=None), failing(timeout))


class _WithMessage(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


@pytest.mark.parametrize(
    "message",
    ["{[1]: 2}", "{'message': " + "-" * 100_000 + "1}"],
    ids=["unhashable key", "long minus chain"],
)
def test_error_reason_bounded(message):
    """A hostile message is returned as a string, quickly, without raising."""
    import time
    from swarm_provenance_uploader.core.chain_client import _error_reason

    start = time.monotonic()
    reason = _error_reason(_WithMessage(message))
    assert isinstance(reason, str)
    assert time.monotonic() - start < 1


def test_build_tx_timeout_reason_with_web3_classes():
    """A node timeout reads as the node's message, not the dict repr."""
    web3_exceptions = pytest.importorskip("web3.exceptions")
    from swarm_provenance_uploader.core.chain_client import ChainClient

    error = {"code": -32000, "message": "request timed out"}
    timeout = web3_exceptions.RequestTimedOut(str(error), rpc_response={"error": error})

    def build():
        raise timeout

    with pytest.raises(ChainConnectionError) as exc_info:
        ChainClient._build_tx(MagicMock(_gas_limit=None), build)
    assert str(exc_info.value).endswith(": request timed out")
    assert "{" not in str(exc_info.value)


# RPC URL redaction (#169)

RPC_KEY = "SECRETKEYSECRETKEY"
RPC_URLS_WITH_KEY = [
    f"https://base-sepolia.g.alchemy.com/v2/{RPC_KEY}",
    f"https://rpc.example.org/base?apikey={RPC_KEY}",
    f"https://rpcuser:{RPC_KEY}@rpc.example.org",
]
RPC_URL_IDS = ["path", "query", "basic-auth"]


class TestRpcUrlRedaction:
    """No chain error shows the path, query or credentials of the RPC URL."""

    @pytest.mark.parametrize("rpc_url", RPC_URLS_WITH_KEY, ids=RPC_URL_IDS)
    def test_code_check_http_error(self, mock_chain_deps, rpc_url):
        """The #166 code check: requests' HTTPError repeats the full URL."""
        import requests
        from swarm_provenance_uploader.core.chain_client import ChainClient

        web3 = mock_chain_deps["web3_instance"]
        web3.eth.get_code.side_effect = requests.exceptions.HTTPError(
            f"401 Client Error: Unauthorized for url: {rpc_url}"
        )
        client = ChainClient(chain="base-sepolia", rpc_url=rpc_url)

        with pytest.raises(ChainConnectionError) as exc_info:
            client.access(swarm_hash=DUMMY_HASH)
        message = str(exc_info.value)
        assert RPC_KEY not in message
        assert RPC_KEY not in exc_info.value.rpc_url
        assert "401 Client Error: Unauthorized" in message
        assert "rpc.example.org" in message or "base-sepolia.g.alchemy.com" in message
        assert exc_info.value.rpc_url.startswith("https://")
        web3.eth.send_raw_transaction.assert_not_called()

    def test_code_check_connection_error_path_only(self, mock_chain_deps):
        """urllib3 repeats only the path and query: "Max retries exceeded with url: /v2/<key>"."""
        import requests
        from swarm_provenance_uploader.core.chain_client import ChainClient

        web3 = mock_chain_deps["web3_instance"]
        web3.eth.get_code.side_effect = requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='base-sepolia.g.alchemy.com', port=443): Max retries "
            f"exceeded with url: /v2/{RPC_KEY}?apikey={RPC_KEY} (Caused by NewConnectionError('refused'))"
        )
        client = ChainClient(chain="base-sepolia", rpc_url=RPC_URLS_WITH_KEY[0])

        with pytest.raises(ChainConnectionError) as exc_info:
            client.access(swarm_hash=DUMMY_HASH)
        assert RPC_KEY not in str(exc_info.value)
        assert "base-sepolia.g.alchemy.com" in str(exc_info.value)

    @pytest.mark.parametrize("rpc_url", RPC_URLS_WITH_KEY, ids=RPC_URL_IDS)
    def test_health_check_cannot_connect(self, mock_chain_deps, rpc_url):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia", rpc_url=rpc_url)
        mock_chain_deps["web3_instance"].is_connected.return_value = False

        with pytest.raises(ChainConnectionError) as exc_info:
            provider.health_check()
        assert "Cannot connect to RPC endpoint" in str(exc_info.value)
        assert RPC_KEY not in str(exc_info.value)
        assert RPC_KEY not in exc_info.value.rpc_url

    def test_get_block_number_error(self, mock_chain_deps):
        import requests
        from swarm_provenance_uploader.chain.provider import ChainProvider

        rpc_url = RPC_URLS_WITH_KEY[0]
        provider = ChainProvider(chain="base-sepolia", rpc_url=rpc_url)
        type(mock_chain_deps["web3_instance"].eth).block_number = PropertyMock(
            side_effect=requests.exceptions.HTTPError(f"429 Client Error: Too Many Requests for url: {rpc_url}")
        )
        try:
            with pytest.raises(ChainConnectionError) as exc_info:
                provider.get_block_number()
        finally:
            del type(mock_chain_deps["web3_instance"].eth).block_number
        assert RPC_KEY not in str(exc_info.value)
        assert "429 Client Error: Too Many Requests" in str(exc_info.value)

    def test_fallback_log(self, mock_chain_deps, caplog):
        """The "RPC fallback: switched from ... to ..." log line."""
        import logging
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(
            chain="base-sepolia",
            rpc_url=RPC_URLS_WITH_KEY[0],
            rpc_fallbacks=[RPC_URLS_WITH_KEY[1]],
        )
        web3 = mock_chain_deps["web3_instance"]
        web3.is_connected.side_effect = [False, True, True]

        with caplog.at_level(logging.INFO, logger="swarm_provenance_uploader.chain.provider"):
            assert provider.health_check() is True
        assert "RPC fallback" in caplog.text
        assert RPC_KEY not in caplog.text


class TestChainClientWithoutWallet:
    """Read-only operations work with no wallet key; writes still need it (#140, #201)."""

    UNSET_KEY_ENV = "PROVENANCE_WALLET_KEY_UNSET_FOR_TEST"

    def _client(self, **kwargs):
        from swarm_provenance_uploader.core.chain_client import ChainClient

        os.environ.pop(self.UNSET_KEY_ENV, None)
        return ChainClient(
            chain="base-sepolia", private_key_env=self.UNSET_KEY_ENV,
            require_wallet=False, **kwargs,
        )

    def test_reads_work_without_key(self, mock_chain_deps):
        """get, verify, get_by_storage_ref and get_provenance_chain need no key."""
        contract = mock_chain_deps["contract"]
        contract.functions.getDataHashByStorageRef.return_value.call.return_value = DUMMY_HASH_BYTES
        client = self._client()

        assert client.get(DUMMY_HASH).data_hash == DUMMY_HASH
        assert client.verify(DUMMY_HASH) is True
        assert client.get_by_storage_ref("ee" * 32).data_hash == DUMMY_HASH
        assert [r.data_hash for r in client.get_provenance_chain(DUMMY_HASH)] == [DUMMY_HASH]
        mock_chain_deps["account_class"].from_key.assert_not_called()

    def test_reads_ignore_an_invalid_key(self, mock_chain_deps):
        """The key is not read for reads, so a malformed key does not block them."""
        mock_chain_deps["account_class"].from_key.side_effect = ValueError("bad key")
        with patch.dict(os.environ, {"PROVENANCE_WALLET_KEY": "not-a-key"}):
            from swarm_provenance_uploader.core.chain_client import ChainClient

            client = ChainClient(chain="base-sepolia", require_wallet=False)
            assert client.verify(DUMMY_HASH) is True

    @pytest.mark.parametrize("write", [
        lambda c: c.anchor(swarm_hash=DUMMY_HASH),
        lambda c: c.transform(original_hash=DUMMY_HASH, new_hash="c" * 64, description="d"),
        lambda c: c.access(swarm_hash=DUMMY_HASH),
        lambda c: c.set_status(swarm_hash=DUMMY_HASH, status=1),
    ], ids=["anchor", "transform", "access", "set_status"])
    def test_writes_fail_before_sending(self, mock_chain_deps, write, request):
        """A write without a key raises the missing-key error and sends nothing."""
        web3 = mock_chain_deps["web3_instance"]
        if request.node.callspec.id == "anchor":
            # anchor first checks that the hash is not registered yet
            mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
                DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0,
            )
        client = self._client()

        with pytest.raises(ChainConfigurationError, match="No wallet private key"):
            write(client)
        web3.eth.send_raw_transaction.assert_not_called()
        web3.eth.get_transaction_count.assert_not_called()

    def test_balance_and_address_need_key(self, mock_chain_deps):
        """balance() reports the key's own address, so it needs the key."""
        client = self._client()

        with pytest.raises(ChainConfigurationError, match="No wallet private key"):
            client.balance()
        with pytest.raises(ChainConfigurationError, match="No wallet private key"):
            client.address

    def test_wallet_built_once(self, mock_chain_deps):
        """The wallet is built on first use and then reused."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia", require_wallet=False)
        mock_chain_deps["account_class"].from_key.assert_not_called()
        assert client.address == DUMMY_ADDRESS
        assert client.address == DUMMY_ADDRESS
        mock_chain_deps["account_class"].from_key.assert_called_once()

    def test_default_still_requires_key_at_construction(self, mock_chain_deps):
        """Without require_wallet=False, a missing key fails in the constructor as before."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        os.environ.pop(self.UNSET_KEY_ENV, None)
        with pytest.raises(ChainConfigurationError, match="No wallet private key"):
            ChainClient(chain="base-sepolia", private_key_env=self.UNSET_KEY_ENV)


# Transport failures in the send step (#181)


class TimeExhausted(Exception):
    """Stand-in for web3.exceptions.TimeExhausted: the receipt wait timed out."""


def _format_hash(digest):
    """A hash as the installed web3 formats the one send_raw_transaction returns."""
    try:
        from hexbytes import HexBytes
    except ImportError:
        return digest.hex()
    return HexBytes(digest).hex()


class TestSendTransactionTransportFailures:
    """A transport failure before the send is a connection error; after it, the outcome is unknown."""

    SIGNED = b"\x00" * 32  # what the mocked wallet signs

    def _signed_hash(self):
        from swarm_provenance_uploader.core.swarm_verify import keccak256

        return _format_hash(keccak256(self.SIGNED))

    @pytest.mark.parametrize(
        "step",
        ["get_transaction_count", "estimate_gas", "gas_price"],
    )
    @pytest.mark.parametrize(
        "error_name",
        ["connection_refused", "read_timeout", "not_json_rpc"],
    )
    def test_failure_before_send_is_connection_error(self, mock_chain_deps, step, error_name):
        import json as json_module
        import requests

        error = {
            "connection_refused": requests.exceptions.ConnectionError("connection refused"),
            "read_timeout": requests.exceptions.ReadTimeout("read timed out"),
            "not_json_rpc": json_module.JSONDecodeError("Expecting value", "<html>Bad gateway</html>", 0),
        }[error_name]
        web3 = mock_chain_deps["web3_instance"]
        client = _write_client(mock_chain_deps, [_log("DataStatusChanged")])
        if step == "gas_price":
            type(web3.eth).gas_price = PropertyMock(side_effect=error)
        else:
            getattr(web3.eth, step).side_effect = error
        try:
            with pytest.raises(ChainConnectionError) as exc_info:
                client.set_status(swarm_hash=DUMMY_HASH, status=1)
        finally:
            if step == "gas_price":
                del type(web3.eth).gas_price

        assert not isinstance(exc_info.value, ChainTransactionError)
        assert "before the transaction was sent" in str(exc_info.value)
        assert exc_info.value.rpc_url == client._provider.rpc_url
        web3.eth.send_raw_transaction.assert_not_called()

    def test_balance_check_failure_is_connection_error(self, mock_chain_deps):
        """The pre-flight balance read (wallet.get_balance) failing is a failure before the send."""
        import requests

        web3 = mock_chain_deps["web3_instance"]
        client = _write_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.get_balance.side_effect = requests.exceptions.ConnectionError("connection refused")

        with pytest.raises(ChainConnectionError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert not isinstance(exc_info.value, ChainTransactionError)
        assert "before the transaction was sent" in str(exc_info.value)
        web3.eth.get_balance.assert_called()
        web3.eth.send_raw_transaction.assert_not_called()

    def test_signed_hash_format_matches_send_result(self):
        """The computed hash has the format of web3's HexBytes.hex(), like the returned hash."""
        hexbytes = pytest.importorskip("hexbytes")
        from swarm_provenance_uploader.core.chain_client import _signed_tx_hash
        from swarm_provenance_uploader.core.swarm_verify import keccak256

        raw = bytes.fromhex("02f8") + b"\x01" * 40
        assert _signed_tx_hash(raw) == hexbytes.HexBytes(keccak256(raw)).hex()

    def test_signed_hash_format_with_0x_prefix(self, monkeypatch):
        """With a hexbytes whose hex() adds 0x (older versions), the computed hash has it too."""
        pytest.importorskip("hexbytes")
        import hexbytes
        from swarm_provenance_uploader.core.chain_client import _signed_tx_hash
        from swarm_provenance_uploader.core.swarm_verify import keccak256

        class PrefixedHexBytes(bytes):
            def hex(self):
                return "0x" + bytes(self).hex()

        monkeypatch.setattr(hexbytes, "HexBytes", PrefixedHexBytes)
        raw = b"\x02" * 10
        assert _signed_tx_hash(raw) == "0x" + keccak256(raw).hex()

    def test_failure_in_send_raw_transaction_outcome_unknown(self, mock_chain_deps):
        import requests
        from swarm_provenance_uploader.exceptions import (
            TransactionOutcomeUnknownError,
            TransactionUnconfirmedError,
        )

        web3 = mock_chain_deps["web3_instance"]
        client = _write_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.send_raw_transaction.side_effect = requests.exceptions.ConnectionError(
            "connection reset"
        )

        with pytest.raises(TransactionOutcomeUnknownError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        err = exc_info.value
        assert isinstance(err, TransactionUnconfirmedError)
        assert not isinstance(err, ChainConnectionError)
        # The hash of the signed bytes: known although the send did not return it
        assert err.tx_hash == self._signed_hash()
        assert self._signed_hash() in err.explorer_url
        assert err.contract_address == DUMMY_CONTRACT
        assert err.event_name == "DataStatusChanged"
        assert err.reason == "connection reset"
        assert "Transaction failed" not in str(err)
        assert "outcome is unknown" in str(err)
        assert self._signed_hash() in str(err)
        # Never sent twice
        web3.eth.send_raw_transaction.assert_called_once()

    def test_failure_in_receipt_wait_outcome_unknown(self, mock_chain_deps):
        import requests
        from swarm_provenance_uploader.exceptions import TransactionOutcomeUnknownError

        web3 = mock_chain_deps["web3_instance"]
        client = _write_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.wait_for_transaction_receipt.side_effect = requests.exceptions.ConnectionError(
            "connection refused"
        )

        with pytest.raises(TransactionOutcomeUnknownError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        err = exc_info.value
        assert err.tx_hash == DUMMY_TX_HASH_BYTES.hex()
        assert DUMMY_TX_HASH_BYTES.hex() in err.explorer_url
        assert err.reason == "connection refused"
        web3.eth.send_raw_transaction.assert_called_once()

    def test_rejection_by_send_is_not_outcome_unknown(self, mock_chain_deps):
        """The node answered and refused the transaction: it is not a transport failure."""
        from swarm_provenance_uploader.exceptions import TransactionUnconfirmedError

        web3 = mock_chain_deps["web3_instance"]
        client = _write_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.send_raw_transaction.side_effect = Web3RPCError("nonce too low")

        with pytest.raises(ChainTransactionError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert not isinstance(exc_info.value, TransactionUnconfirmedError)
        assert str(exc_info.value) == "nonce too low"

    def test_rejection_by_send_carries_signed_hash(self, mock_chain_deps):
        """A rejection raised by send_raw_transaction shows the hash of the signed transaction."""
        from swarm_provenance_uploader.exceptions import TransactionUnconfirmedError

        web3 = mock_chain_deps["web3_instance"]
        client = _write_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.send_raw_transaction.side_effect = Web3RPCError("nonce too low")

        with pytest.raises(ChainTransactionError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert type(exc_info.value) is ChainTransactionError
        assert not isinstance(exc_info.value, TransactionUnconfirmedError)
        assert exc_info.value.tx_hash == self._signed_hash()
        web3.eth.send_raw_transaction.assert_called_once()

    def test_failure_before_send_has_no_hash(self, mock_chain_deps):
        """Nothing was signed and sent: an error before the send carries no hash."""
        web3 = mock_chain_deps["web3_instance"]
        client = _write_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.estimate_gas.side_effect = Web3RPCError("execution reverted")

        with pytest.raises(ChainTransactionError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert exc_info.value.tx_hash is None
        web3.eth.send_raw_transaction.assert_not_called()

    def test_receipt_timeout_is_not_a_failure(self, mock_chain_deps):
        """A receipt-wait timeout is ReceiptTimeoutError with the hash, not a failed transaction (#167)."""
        from swarm_provenance_uploader.exceptions import (
            ReceiptTimeoutError,
            TransactionOutcomeUnknownError,
        )

        web3 = mock_chain_deps["web3_instance"]
        client = _write_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.wait_for_transaction_receipt.side_effect = TimeExhausted("not in chain after 120 s")

        with pytest.raises(ReceiptTimeoutError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert isinstance(exc_info.value, TransactionOutcomeUnknownError)
        assert not isinstance(exc_info.value, ChainConnectionError)
        assert exc_info.value.tx_hash == DUMMY_TX_HASH_BYTES.hex()

    @pytest.mark.parametrize("rpc_url", RPC_URLS_WITH_KEY, ids=RPC_URL_IDS)
    def test_rpc_key_redacted(self, mock_chain_deps, rpc_url):
        import requests
        from swarm_provenance_uploader.core.chain_client import ChainClient
        from swarm_provenance_uploader.exceptions import TransactionOutcomeUnknownError

        web3 = mock_chain_deps["web3_instance"]
        _write_client(mock_chain_deps, [_log("DataStatusChanged")])
        client = ChainClient(chain="base-sepolia", rpc_url=rpc_url)
        failure = requests.exceptions.ConnectionError(f"Max retries exceeded for {rpc_url}")

        web3.eth.get_transaction_count.side_effect = failure
        with pytest.raises(ChainConnectionError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)
        assert RPC_KEY not in str(exc_info.value)
        assert RPC_KEY not in exc_info.value.rpc_url

        web3.eth.get_transaction_count.side_effect = None
        web3.eth.send_raw_transaction.side_effect = failure
        with pytest.raises(TransactionOutcomeUnknownError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)
        assert RPC_KEY not in str(exc_info.value)
        assert RPC_KEY not in exc_info.value.reason

    def test_outcome_unknown_exported(self):
        from swarm_provenance_uploader import chain
        from swarm_provenance_uploader.exceptions import (
            TransactionOutcomeUnknownError,
            TransactionUnconfirmedError,
        )

        assert issubclass(TransactionOutcomeUnknownError, TransactionUnconfirmedError)
        assert issubclass(TransactionOutcomeUnknownError, ChainTransactionError)
        assert "TransactionOutcomeUnknownError" in chain.__all__ or not chain.BLOCKCHAIN_AVAILABLE


# The send step with the real web3 exception classes (#181). No sys.modules
# patch: _is_rpc_failure, _is_rpc_rejection and _is_receipt_timeout see the
# installed web3, so the classification itself is tested.

SEND_RAW = b"\x02" * 40
SEND_RETURNED_HASH = bytes.fromhex("cd" * 32)


def _send_client(failing_call, error):
    """A stand-in client whose web3 call `failing_call` raises `error`."""
    web3 = MagicMock()
    web3.eth.get_transaction_count.return_value = 0
    web3.eth.estimate_gas.return_value = 100_000
    web3.eth.gas_price = 1_000_000_000
    web3.eth.send_raw_transaction.return_value = SEND_RETURNED_HASH
    getattr(web3.eth, failing_call).side_effect = error
    client = MagicMock(_gas_limit=None, _gas_limit_multiplier=1.2)
    client._provider.web3 = web3
    client._provider.chain_id = 84532
    client._provider.rpc_url = "https://rpc.example.org"
    client._provider.get_explorer_tx_url = lambda h: "https://explorer.example.org/tx/" + h
    client._wallet.sign_transaction.return_value = SEND_RAW
    client._contract.address = DUMMY_CONTRACT
    # The real receipt helpers, which _send_transaction calls on self (#167)
    from swarm_provenance_uploader.core.chain_client import ChainClient
    for name in ("_await_receipt", "_receipt_after_timeout", "_check_receipt"):
        setattr(client, name, getattr(ChainClient, name).__get__(client))
    return client, web3


def _send(client):
    from swarm_provenance_uploader.core.chain_client import ChainClient

    return ChainClient._send_transaction(client, {"to": DUMMY_CONTRACT, "data": "0x"}, "DataStatusChanged")


def _web3_error(name):
    web3_exceptions = pytest.importorskip("web3.exceptions")
    if name == "Web3RPCError":
        return web3_exceptions.Web3RPCError(
            "nonce too low", rpc_response={"error": {"code": -32000, "message": "nonce too low"}}
        )
    return getattr(web3_exceptions, name)("timed out" if "Time" in name else "refused")


def _expected_hash(failing_call):
    from swarm_provenance_uploader.core.chain_client import _signed_tx_hash

    if failing_call == "send_raw_transaction":
        return _signed_tx_hash(SEND_RAW)
    return _format_hash(SEND_RETURNED_HASH)


AFTER_SEND_CALLS = ["send_raw_transaction", "wait_for_transaction_receipt"]
TRANSPORT_ERRORS = ["ProviderConnectionError", "BadResponseFormat", "RequestTimedOut"]


@pytest.mark.parametrize("failing_call", AFTER_SEND_CALLS)
def test_send_rejection_with_web3_classes(failing_call):
    """A JSON-RPC rejection stays ChainTransactionError, with the hash."""
    error = _web3_error("Web3RPCError")
    client, web3 = _send_client(failing_call, error)

    with pytest.raises(ChainTransactionError) as exc_info:
        _send(client)

    assert type(exc_info.value) is ChainTransactionError
    assert exc_info.value.tx_hash == _expected_hash(failing_call)
    web3.eth.send_raw_transaction.assert_called_once()


def test_send_receipt_timeout_with_web3_classes():
    """The real web3 TimeExhausted from the receipt wait is ReceiptTimeoutError, with the hash (#167)."""
    from swarm_provenance_uploader.exceptions import ReceiptTimeoutError

    error = _web3_error("TimeExhausted")
    client, web3 = _send_client("wait_for_transaction_receipt", error)

    with pytest.raises(ReceiptTimeoutError) as exc_info:
        _send(client)

    assert exc_info.value.tx_hash == _expected_hash("wait_for_transaction_receipt")
    assert exc_info.value.explorer_url.endswith(exc_info.value.tx_hash)
    web3.eth.send_raw_transaction.assert_called_once()


def test_send_timeout_exhausted_from_send_is_not_receipt_timeout():
    """TimeExhausted is classified only in the receipt wait: from the send it stays ChainTransactionError."""
    from swarm_provenance_uploader.exceptions import TransactionUnconfirmedError

    error = _web3_error("TimeExhausted")
    client, web3 = _send_client("send_raw_transaction", error)

    with pytest.raises(ChainTransactionError) as exc_info:
        _send(client)

    assert not isinstance(exc_info.value, TransactionUnconfirmedError)
    assert exc_info.value.tx_hash == _expected_hash("send_raw_transaction")


@pytest.mark.parametrize("name", TRANSPORT_ERRORS)
def test_send_transport_failure_before_send_with_web3_classes(name):
    error = _web3_error(name)
    client, web3 = _send_client("get_transaction_count", error)

    with pytest.raises(ChainConnectionError) as exc_info:
        _send(client)

    assert "before the transaction was sent" in str(exc_info.value)
    web3.eth.send_raw_transaction.assert_not_called()


@pytest.mark.parametrize("failing_call", AFTER_SEND_CALLS)
@pytest.mark.parametrize("name", TRANSPORT_ERRORS)
def test_send_transport_failure_after_send_with_web3_classes(failing_call, name):
    from swarm_provenance_uploader.exceptions import TransactionOutcomeUnknownError

    error = _web3_error(name)
    client, web3 = _send_client(failing_call, error)

    with pytest.raises(TransactionOutcomeUnknownError) as exc_info:
        _send(client)

    assert exc_info.value.tx_hash == _expected_hash(failing_call)
    assert exc_info.value.explorer_url.endswith(_expected_hash(failing_call))
    web3.eth.send_raw_transaction.assert_called_once()


# --- #187: errors that ChainClient raises to library callers ---


def _chain_texts(error):
    """Text of error and of every exception linked through __cause__ and __context__."""
    seen, texts, todo = set(), [], [error]
    while todo:
        exc = todo.pop(0)
        if exc is None or id(exc) in seen:
            continue
        seen.add(id(exc))
        texts.append(f"{type(exc).__name__}: {exc} {exc.args!r} {vars(exc)!r}")
        todo.extend([exc.__cause__, exc.__context__])
    return texts


def _assert_no_key(error, key=RPC_KEY):
    import traceback

    from swarm_provenance_uploader.exceptions import ChainError

    assert isinstance(error, ChainError), repr(error)
    trace = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    assert key not in trace, trace
    for text in _chain_texts(error):
        assert key not in text, text


_READ_CALLS = {
    "get": lambda client: client.get(DUMMY_HASH),
    "verify": lambda client: client.verify(DUMMY_HASH),
    "get_by_storage_ref": lambda client: client.get_by_storage_ref(DUMMY_HASH),
    "balance": lambda client: client.balance(),
    "get_provenance_chain": lambda client: client.get_provenance_chain(DUMMY_HASH),
}

_READ_CASES = (
    [(mode, m) for mode in ("http401", "jsonrpc", "refused") for m in _READ_CALLS]
    + [("html", m) for m in ("get", "balance")]
)


class TestReadErrorsRealWeb3:
    """Read methods with the real web3 and requests against failing local RPCs (#187).

    No mock_chain_deps: it replaces web3 with a MagicMock. Only reads are
    made, only to 127.0.0.1, with the dummy test key.
    """

    @pytest.mark.parametrize("path", [f"/v2/{RPC_KEY}", f"/?apikey={RPC_KEY}"], ids=["path", "query"])
    @pytest.mark.parametrize("mode,method", _READ_CASES, ids=[f"{m}-{n}" for m, n in _READ_CASES])
    def test_read_raises_redacted_chain_error(
        self, monkeypatch, failing_rpc_server, closed_port, no_web3_retry_sleep, mode, method, path
    ):
        pytest.importorskip("web3")
        from swarm_provenance_uploader.core.chain_client import ChainClient

        monkeypatch.setenv("PROVENANCE_WALLET_KEY", DUMMY_PRIVATE_KEY)
        failing_rpc_server.mode = mode
        port = closed_port if mode == "refused" else failing_rpc_server.server_port
        client = ChainClient(
            chain="base-sepolia", rpc_url=f"http://127.0.0.1:{port}{path}", rpc_fallbacks=[]
        )

        expected = ChainConfigurationError if mode == "jsonrpc" else ChainConnectionError
        with pytest.raises(expected) as exc_info:
            _READ_CALLS[method](client)

        error = exc_info.value
        _assert_no_key(error)
        if mode == "jsonrpc":
            assert str(error).startswith("The RPC rejected the request: invalid api key in /")
            assert error.__cause__.original_type == "web3.exceptions.Web3RPCError"
        else:
            assert error.rpc_url == f"http://127.0.0.1:{port}/…"
            expected_text = {
                "http401": "401 Client Error",
                "refused": "Connection refused",
                "html": "",
            }[mode]
            assert expected_text in str(error)
            # The redacted original stays as the cause, so tracebacks show where it failed
            assert error.__cause__.original_type.startswith(("requests.", "json.", "web3."))

    @pytest.mark.parametrize("mode", ["jsonrpc", "refused"])
    def test_health_check_chain_is_redacted(self, monkeypatch, failing_rpc_server, closed_port, no_web3_retry_sleep, mode):
        """health_check already raises ChainConnectionError; its cause must be redacted too."""
        pytest.importorskip("web3")
        from swarm_provenance_uploader.core.chain_client import ChainClient

        monkeypatch.setenv("PROVENANCE_WALLET_KEY", DUMMY_PRIVATE_KEY)
        failing_rpc_server.mode = mode
        port = closed_port if mode == "refused" else failing_rpc_server.server_port
        client = ChainClient(
            chain="base-sepolia", rpc_url=f"http://127.0.0.1:{port}/v2/{RPC_KEY}", rpc_fallbacks=[]
        )
        # is_connected() swallows the failure; the chain id request raises
        monkeypatch.setattr(client._provider._web3, "is_connected", lambda *a, **k: True)

        with pytest.raises(ChainConnectionError) as exc_info:
            client.health_check()

        _assert_no_key(exc_info.value)
        assert exc_info.value.__cause__ is not None


class TestChainErrorCauseRedaction:
    """Every ChainError that ChainClient raises has a redacted chain (#187)."""

    @pytest.mark.parametrize("rpc_url", RPC_URLS_WITH_KEY, ids=RPC_URL_IDS)
    def test_code_check_cause(self, mock_chain_deps, rpc_url):
        import requests
        from swarm_provenance_uploader.core.chain_client import ChainClient

        web3 = mock_chain_deps["web3_instance"]
        web3.eth.get_code.side_effect = requests.exceptions.HTTPError(
            f"401 Client Error: Unauthorized for url: {rpc_url} (key {RPC_KEY})"
        )
        client = ChainClient(chain="base-sepolia", rpc_url=rpc_url)

        with pytest.raises(ChainConnectionError) as exc_info:
            client.access(swarm_hash=DUMMY_HASH)

        _assert_no_key(exc_info.value)
        cause = exc_info.value.__cause__
        assert cause.original_type == "requests.exceptions.HTTPError"
        assert "401 Client Error: Unauthorized" in str(cause)

    def test_build_tx_cause(self, mock_chain_deps):
        import requests
        from swarm_provenance_uploader.core.chain_client import ChainClient

        web3 = mock_chain_deps["web3_instance"]
        web3.eth.get_code.return_value = DUMMY_CODE
        client = ChainClient(chain="base-sepolia", rpc_url=RPC_URLS_WITH_KEY[0])
        client._contract.build_record_access_tx = MagicMock(
            side_effect=requests.exceptions.ConnectionError(
                f"Max retries exceeded with url: /v2/{RPC_KEY} ({RPC_URLS_WITH_KEY[0]})"
            )
        )

        with pytest.raises(ChainConnectionError) as exc_info:
            client.access(swarm_hash=DUMMY_HASH)

        _assert_no_key(exc_info.value)

    def test_write_method_passes_raw_errors_through(self, mock_chain_deps):
        """Write paths keep their own classification: a raw error is not mapped here."""
        import requests
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia", rpc_url=RPC_URLS_WITH_KEY[0])
        raw = requests.exceptions.ConnectionError("refused")
        client._check_contract_code = MagicMock(side_effect=raw)

        with pytest.raises(requests.exceptions.ConnectionError) as exc_info:
            client.access(swarm_hash=DUMMY_HASH)
        assert exc_info.value is raw


# RPC fallbacks for reads and for writes before the send (#168), and the
# contract following a fallback switch (#200)

BASE_SEPOLIA_CHAIN_ID_HEX = hex(84532)
BASE_MAINNET_CHAIN_ID_HEX = hex(8453)


def _encoded_data_record(owner=OTHER_ADDRESS):
    """The eth_call result of getDataRecord for a registered DUMMY_HASH, ABI-encoded."""
    import eth_abi
    from eth_utils.abi import get_abi_output_types
    from swarm_provenance_uploader.chain.contract import _load_abi

    function = next(item for item in _load_abi() if item.get("name") == "getDataRecord")
    (record_type,) = get_abi_output_types(function)
    record = (DUMMY_HASH_BYTES, owner, 1_700_000_000, "swarm-provenance", b"\x00" * 32, [], [], 0)
    return "0x" + eth_abi.encode([record_type], [record]).hex()


def _working_rpc(server, chain_id_hex=BASE_SEPOLIA_CHAIN_ID_HEX):
    """Make the failing_rpc_server stub answer as a node on the given chain."""
    server.answers.update({
        "web3_clientVersion": "stub/1.0",
        "eth_chainId": chain_id_hex,
        "eth_call": _encoded_data_record(),
    })
    return f"http://127.0.0.1:{server.server_port}"


class TestReadFallbackRealWeb3:
    """A dead primary RPC: reads go to the fallback, with the real web3 (#168, #200).

    No mock_chain_deps: it replaces web3 with a MagicMock, and the point is
    that the real contract object sends its eth_call to the new endpoint.
    Only reads are made, only to 127.0.0.1, without a wallet key.
    """

    def test_contract_read_succeeds_through_the_fallback(
        self, failing_rpc_server, closed_port, no_web3_retry_sleep
    ):
        pytest.importorskip("web3")
        from swarm_provenance_uploader.core.chain_client import ChainClient

        primary = f"http://127.0.0.1:{closed_port}"
        fallback = _working_rpc(failing_rpc_server)
        client = ChainClient(
            chain="base-sepolia", rpc_url=primary, rpc_fallbacks=[fallback], require_wallet=False
        )
        contract = client._contract

        record = client.get(DUMMY_HASH)

        assert record.owner.lower() == OTHER_ADDRESS
        assert record.data_type == "swarm-provenance"
        assert "eth_call" in failing_rpc_server.methods
        assert client._provider.rpc_url == fallback
        # #200: the same contract object, bound to the provider's active web3
        assert client._contract is contract
        assert contract._contract.w3 is client._provider.web3

    def test_fallback_on_another_chain_is_not_used(
        self, failing_rpc_server, closed_port, no_web3_retry_sleep
    ):
        pytest.importorskip("web3")
        from swarm_provenance_uploader.core.chain_client import ChainClient

        primary = f"http://127.0.0.1:{closed_port}"
        fallback = _working_rpc(failing_rpc_server, chain_id_hex=BASE_MAINNET_CHAIN_ID_HEX)
        client = ChainClient(
            chain="base-sepolia", rpc_url=primary, rpc_fallbacks=[fallback], require_wallet=False
        )

        with pytest.raises(ChainConnectionError):
            client.get(DUMMY_HASH)

        assert "eth_chainId" in failing_rpc_server.methods
        assert "eth_call" not in failing_rpc_server.methods
        assert client._provider.rpc_url == primary

    def test_switch_keeps_the_web3_object(self, failing_rpc_server, closed_port, no_web3_retry_sleep):
        """_try_fallback changes the provider of the existing Web3 object (#200)."""
        pytest.importorskip("web3")
        from swarm_provenance_uploader.chain.provider import ChainProvider

        primary = f"http://127.0.0.1:{closed_port}"
        fallback = _working_rpc(failing_rpc_server)
        provider = ChainProvider(chain="base-sepolia", rpc_url=primary, rpc_fallbacks=[fallback])
        web3 = provider.web3

        assert provider._try_fallback() is True

        assert provider.web3 is web3
        assert web3.provider.endpoint_uri == fallback
        assert provider.rpc_url == fallback

    def test_every_endpoint_dead_is_a_redacted_connection_error(
        self, failing_rpc_server, closed_port, no_web3_retry_sleep, caplog
    ):
        import logging

        pytest.importorskip("web3")
        from swarm_provenance_uploader.core.chain_client import ChainClient

        failing_rpc_server.mode = "http401"
        primary = f"http://127.0.0.1:{closed_port}/v2/{RPC_KEY}"
        # Connects (answers is_connected and the chain ID), then fails the read
        failing_rpc_server.answers.update({
            "web3_clientVersion": "stub/1.0", "eth_chainId": BASE_SEPOLIA_CHAIN_ID_HEX,
        })
        fallback = f"http://127.0.0.1:{failing_rpc_server.server_port}/v2/{RPC_KEY}"
        client = ChainClient(
            chain="base-sepolia", rpc_url=primary, rpc_fallbacks=[fallback], require_wallet=False
        )

        with caplog.at_level(logging.DEBUG, logger="swarm_provenance_uploader"):
            with pytest.raises(ChainConnectionError) as exc_info:
                client.get(DUMMY_HASH)

        _assert_no_key(exc_info.value)
        assert "RPC fallback" in caplog.text
        assert RPC_KEY not in caplog.text


def _fallback_client(mock_chain_deps, logs=()):
    """A write client whose _try_fallback switches once, then has no endpoint left."""
    client = _write_client(mock_chain_deps, list(logs))
    mock_chain_deps["web3_instance"].eth.get_code.return_value = DUMMY_CODE
    client._provider._try_fallback = MagicMock(side_effect=[True, False, False, False])
    return client


class TestWriteFallbackBeforeSend:
    """A transport failure before the send falls back; the transaction is sent once (#168)."""

    @pytest.mark.parametrize("step", ["get_transaction_count", "estimate_gas", "get_balance", "get_code"])
    def test_step_falls_back_and_sends_once(self, mock_chain_deps, step):
        import requests

        web3 = mock_chain_deps["web3_instance"]
        client = _fallback_client(mock_chain_deps, [_log("DataStatusChanged")])
        method = getattr(web3.eth, step)
        ok = method.return_value
        method.side_effect = [requests.exceptions.ConnectionError("connection refused"), ok, ok, ok]

        client.set_status(swarm_hash=DUMMY_HASH, status=1)

        client._provider._try_fallback.assert_called_once()
        web3.eth.send_raw_transaction.assert_called_once()
        mock_chain_deps["account"].sign_transaction.assert_called_once()

    def test_gas_estimate_in_build_falls_back(self, mock_chain_deps):
        import requests

        web3 = mock_chain_deps["web3_instance"]
        client = _fallback_client(mock_chain_deps, [_log("DataAccessed")])
        build = mock_chain_deps["contract"].functions.recordAccess.return_value.build_transaction
        tx = {"from": DUMMY_ADDRESS, "to": DUMMY_CONTRACT, "data": "0x"}
        build.side_effect = [requests.exceptions.ConnectionError("connection refused"), tx]

        client.access(swarm_hash=DUMMY_HASH)

        assert build.call_count == 2
        client._provider._try_fallback.assert_called_once()
        web3.eth.send_raw_transaction.assert_called_once()

    def test_no_endpoint_left_is_connection_error_and_nothing_is_sent(self, mock_chain_deps):
        import requests

        web3 = mock_chain_deps["web3_instance"]
        client = _fallback_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.get_transaction_count.side_effect = requests.exceptions.ConnectionError("refused")

        with pytest.raises(ChainConnectionError, match="before the transaction was sent"):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert client._provider._try_fallback.call_count == 2
        web3.eth.send_raw_transaction.assert_not_called()
        mock_chain_deps["account"].sign_transaction.assert_not_called()

    def test_wrong_chain_primary_does_not_fall_back(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.exceptions import ChainIdMismatchError

        web3 = mock_chain_deps["web3_instance"]
        client = _fallback_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.chain_id = 8453  # the primary answers on mainnet

        with pytest.raises(ChainIdMismatchError):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        client._provider._try_fallback.assert_not_called()
        mock_chain_deps["account"].sign_transaction.assert_not_called()

    def test_json_rpc_rejection_does_not_fall_back(self, mock_chain_deps):
        """A node that answers with a JSON-RPC error is not a transport failure."""
        web3_exceptions = pytest.importorskip("web3.exceptions")

        web3 = mock_chain_deps["web3_instance"]
        client = _fallback_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.get_transaction_count.side_effect = web3_exceptions.Web3RPCError("nonce too low")

        with pytest.raises(ChainTransactionError):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        client._provider._try_fallback.assert_not_called()
        web3.eth.send_raw_transaction.assert_not_called()

    def test_contract_revert_in_build_does_not_fall_back(self, mock_chain_deps):
        web3_exceptions = pytest.importorskip("web3.exceptions")

        client = _fallback_client(mock_chain_deps, [_log("DataAccessed")])
        build = mock_chain_deps["contract"].functions.recordAccess.return_value.build_transaction
        build.side_effect = web3_exceptions.ContractLogicError("execution reverted: no")

        with pytest.raises(ChainTransactionError, match="reverted"):
            client.access(swarm_hash=DUMMY_HASH)

        client._provider._try_fallback.assert_not_called()


class TestWriteNoFallbackAfterSend:
    """After send_raw_transaction is called, nothing is sent again (#168, #181)."""

    def test_send_failure_is_outcome_unknown_without_fallback(self, mock_chain_deps):
        import requests
        from swarm_provenance_uploader.chain.exceptions import TransactionOutcomeUnknownError

        web3 = mock_chain_deps["web3_instance"]
        client = _fallback_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.send_raw_transaction.side_effect = requests.exceptions.ConnectionError("reset")

        with pytest.raises(TransactionOutcomeUnknownError):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        web3.eth.send_raw_transaction.assert_called_once()
        mock_chain_deps["account"].sign_transaction.assert_called_once()
        client._provider._try_fallback.assert_not_called()

    def test_receipt_wait_falls_back_for_the_same_hash(self, mock_chain_deps):
        import requests

        web3 = mock_chain_deps["web3_instance"]
        client = _fallback_client(mock_chain_deps, [_log("DataStatusChanged")])
        receipt = web3.eth.wait_for_transaction_receipt.return_value
        web3.eth.wait_for_transaction_receipt.side_effect = [
            requests.exceptions.ConnectionError("reset"), receipt,
        ]

        client.set_status(swarm_hash=DUMMY_HASH, status=1)

        web3.eth.send_raw_transaction.assert_called_once()
        client._provider._try_fallback.assert_called_once()
        hashes = [c.args[0] for c in web3.eth.wait_for_transaction_receipt.call_args_list]
        assert hashes == [DUMMY_TX_HASH_BYTES, DUMMY_TX_HASH_BYTES]

    def test_receipt_wait_with_no_endpoint_left_is_outcome_unknown(self, mock_chain_deps):
        import requests
        from swarm_provenance_uploader.chain.exceptions import TransactionOutcomeUnknownError

        web3 = mock_chain_deps["web3_instance"]
        client = _fallback_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.wait_for_transaction_receipt.side_effect = requests.exceptions.ConnectionError("reset")

        with pytest.raises(TransactionOutcomeUnknownError):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        web3.eth.send_raw_transaction.assert_called_once()

    def test_receipt_timeout_does_not_fall_back(self, mock_chain_deps):
        web3_exceptions = pytest.importorskip("web3.exceptions")

        web3 = mock_chain_deps["web3_instance"]
        client = _fallback_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.wait_for_transaction_receipt.side_effect = web3_exceptions.TimeExhausted("timeout")

        with pytest.raises(ChainTransactionError):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        client._provider._try_fallback.assert_not_called()
        web3.eth.send_raw_transaction.assert_called_once()


class TestReadFallbackMocked:
    """Read methods retry on the fallback after a transport failure (#168)."""

    def _client(self, mock_chain_deps):
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia", require_wallet=False)
        client._provider._try_fallback = MagicMock(side_effect=[True, False, False, False])
        return client

    def test_link_read_in_provenance_chain_falls_back(self, mock_chain_deps):
        import requests

        contract = mock_chain_deps["contract"]
        contract.functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, OTHER_ADDRESS, 1, "t", b"\x00" * 32, [], [], 0,
        )
        links = contract.functions.getTransformationLinks.return_value.call
        links.side_effect = [[], requests.exceptions.ConnectionError("reset"), [], []]
        contract.functions.getTransformationParents.return_value.call.return_value = []
        client = self._client(mock_chain_deps)

        chain = client.get_provenance_chain(DUMMY_HASH)

        assert [r.data_hash for r in chain] == [DUMMY_HASH]
        client._provider._try_fallback.assert_called_once()

    def test_json_rpc_rejection_in_a_read_does_not_fall_back(self, mock_chain_deps):
        web3_exceptions = pytest.importorskip("web3.exceptions")

        mock_chain_deps["web3_instance"].eth.get_balance.side_effect = web3_exceptions.Web3RPCError(
            "rate limited"
        )
        client = self._client(mock_chain_deps)
        client._wallet  # the test key from mock_chain_deps

        with pytest.raises(ChainConfigurationError):
            client.balance()

        client._provider._try_fallback.assert_not_called()


class TestNestedReadsTryEachEndpointOnce:
    """A public read that calls get() tries each RPC endpoint at most once (#168 review).

    verify(), get_by_storage_ref() and get_provenance_chain() call get().
    Only the outermost read runs the fallback loop, so the inner one does
    not probe every endpoint again.
    """

    def _dead_client(self, mock_chain_deps):
        import requests
        from swarm_provenance_uploader.core.chain_client import ChainClient

        web3 = mock_chain_deps["web3_instance"]
        web3.is_connected.side_effect = None
        web3.is_connected.return_value = False  # no fallback connects
        contract = mock_chain_deps["contract"]
        contract.functions.getDataRecord.return_value.call.side_effect = (
            requests.exceptions.ConnectionError("refused")
        )
        client = ChainClient(chain="base-sepolia", require_wallet=False)
        return client, web3

    @pytest.mark.parametrize("method", ["get", "verify", "get_by_storage_ref", "get_provenance_chain"])
    def test_every_endpoint_dead_probes_each_fallback_once(self, mock_chain_deps, method):
        client, web3 = self._dead_client(mock_chain_deps)
        contract = mock_chain_deps["contract"]
        contract.functions.getDataHashByStorageRef.return_value.call.return_value = DUMMY_HASH_BYTES
        fallbacks = len(client._provider._rpc_urls) - 1
        assert fallbacks == 2

        with pytest.raises(ChainConnectionError):
            getattr(client, method)(DUMMY_HASH)

        assert web3.is_connected.call_count == fallbacks
        assert contract.functions.getDataRecord.return_value.call.call_count == 1

    def test_verify_real_web3_reads_each_endpoint_once(
        self, failing_rpc_server, closed_port, no_web3_retry_sleep
    ):
        """Real web3: two fallbacks that connect but fail the read get one eth_call each."""
        pytest.importorskip("web3")
        from swarm_provenance_uploader.core.chain_client import ChainClient

        failing_rpc_server.mode = "http401"
        failing_rpc_server.answers.update({
            "web3_clientVersion": "stub/1.0", "eth_chainId": BASE_SEPOLIA_CHAIN_ID_HEX,
        })
        base = f"http://127.0.0.1:{failing_rpc_server.server_port}"
        client = ChainClient(
            chain="base-sepolia",
            rpc_url=f"http://127.0.0.1:{closed_port}",
            rpc_fallbacks=[f"{base}/a", f"{base}/b"],
            require_wallet=False,
        )

        with pytest.raises(ChainConnectionError):
            client.verify(DUMMY_HASH)

        # One probe per fallback, and /a is never read again once /b is in use
        # (web3 itself repeats a failed HTTP request, so the counts per
        # endpoint are larger than one)
        assert failing_rpc_server.methods.count("web3_clientVersion") == 2
        reads = [path for path, method in failing_rpc_server.requests if method == "eth_call"]
        assert reads, failing_rpc_server.requests
        first_b = reads.index("/b")
        assert set(reads[:first_b]) == {"/a"}
        assert set(reads[first_b:]) == {"/b"}


class TestReceiptWaitTimeoutAfterSwitch:
    """A receipt wait that moved to a fallback and then timed out is "outcome unknown" (#168 review).

    The primary failed during the wait, so the transaction was sent and
    may be mined. Reporting it as a failed transaction could lead to
    sending the write again. Without a switch, the timeout handling is
    unchanged (#167).
    """

    def test_timeout_after_switch_is_outcome_unknown(self, mock_chain_deps):
        import requests
        web3_exceptions = pytest.importorskip("web3.exceptions")
        from swarm_provenance_uploader.chain.exceptions import TransactionOutcomeUnknownError

        web3 = mock_chain_deps["web3_instance"]
        client = _fallback_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.wait_for_transaction_receipt.side_effect = [
            requests.exceptions.ConnectionError("reset"),
            web3_exceptions.TimeExhausted("not in chain after 120 seconds"),
        ]

        with pytest.raises(TransactionOutcomeUnknownError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert exc_info.value.tx_hash == DUMMY_TX_HASH_BYTES.hex()
        assert exc_info.value.tx_hash in str(exc_info.value)
        assert "Outcome unknown" in str(exc_info.value)
        web3.eth.send_raw_transaction.assert_called_once()
        client._provider._try_fallback.assert_called_once()
        # #167 keeps this case as outcome unknown, without the nonce check
        from swarm_provenance_uploader.chain.exceptions import ReceiptTimeoutError
        assert not isinstance(exc_info.value, ReceiptTimeoutError)
        assert not any(c.args[1:] == ("latest",) for c in web3.eth.get_transaction_count.call_args_list)

    def test_timeout_without_switch_is_receipt_timeout(self, mock_chain_deps):
        """Without a switch, a timeout is ReceiptTimeoutError, with the nonce check (#167)."""
        web3_exceptions = pytest.importorskip("web3.exceptions")
        from swarm_provenance_uploader.chain.exceptions import ReceiptTimeoutError

        web3 = mock_chain_deps["web3_instance"]
        client = _fallback_client(mock_chain_deps, [_log("DataStatusChanged")])
        web3.eth.wait_for_transaction_receipt.side_effect = web3_exceptions.TimeExhausted("timeout")

        with pytest.raises(ReceiptTimeoutError):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        client._provider._try_fallback.assert_not_called()


class TestHealthCheckWrongChainDoesNotFallBack:
    """health_check() on an RPC on another chain is ChainIdMismatchError, with no fallback (#168 review)."""

    def test_wrong_chain_is_mismatch_error_without_fallback(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.exceptions import ChainIdMismatchError
        from swarm_provenance_uploader.chain.provider import ChainProvider

        primary, good = "https://primary.rpc.io", "https://good.rpc.io"
        _web3_per_url(mock_chain_deps, {primary: 8453, good: 84532})
        # A custom primary on another chain already fails in __init__. Build
        # with the preset primary, which is not checked at start-up, and
        # point it at the wrong-chain node
        provider = ChainProvider(chain="base-sepolia", rpc_fallbacks=[good])
        provider._web3.provider = primary
        provider.rpc_url = primary

        with pytest.raises(ChainIdMismatchError) as exc_info:
            provider.health_check()

        assert exc_info.value.expected_chain_id == 84532
        assert exc_info.value.actual_chain_id == 8453
        assert provider.rpc_url == primary


class TestWrongChainPrimaryRealWeb3:
    """A primary RPC on another chain is an error on the read path; no fallback is used (#168 review)."""

    def test_wrong_chain_primary_at_start_does_not_fall_back(
        self, monkeypatch, failing_rpc_server, closed_port, no_web3_retry_sleep
    ):
        pytest.importorskip("web3")
        from swarm_provenance_uploader.chain.exceptions import ChainIdMismatchError
        from swarm_provenance_uploader.chain.provider import ChainProvider
        from swarm_provenance_uploader.core.chain_client import ChainClient

        calls = []
        real = ChainProvider._try_fallback
        monkeypatch.setattr(
            ChainProvider, "_try_fallback", lambda self, tried=None: calls.append(1) or real(self, tried)
        )
        primary = _working_rpc(failing_rpc_server, chain_id_hex=BASE_MAINNET_CHAIN_ID_HEX)

        with pytest.raises(ChainIdMismatchError):
            ChainClient(
                chain="base-sepolia", rpc_url=primary,
                rpc_fallbacks=[f"http://127.0.0.1:{closed_port}"], require_wallet=False,
            )

        assert calls == []
        assert "eth_call" not in failing_rpc_server.methods

    def test_primary_moved_to_another_chain_fails_health_check_without_fallback(
        self, monkeypatch, failing_rpc_server, closed_port, no_web3_retry_sleep
    ):
        pytest.importorskip("web3")
        from swarm_provenance_uploader.chain.exceptions import ChainIdMismatchError
        from swarm_provenance_uploader.chain.provider import ChainProvider
        from swarm_provenance_uploader.core.chain_client import ChainClient

        primary = _working_rpc(failing_rpc_server)
        client = ChainClient(
            chain="base-sepolia", rpc_url=primary,
            rpc_fallbacks=[f"http://127.0.0.1:{closed_port}"], require_wallet=False,
        )
        calls = []
        real = ChainProvider._try_fallback
        monkeypatch.setattr(
            ChainProvider, "_try_fallback", lambda self, tried=None: calls.append(1) or real(self, tried)
        )
        # The node at the same URL now reports mainnet
        failing_rpc_server.answers["eth_chainId"] = BASE_MAINNET_CHAIN_ID_HEX
        # web3 caches eth_chainId per provider: use a fresh one at the same URL
        from web3 import Web3
        client._provider.web3.provider = Web3.HTTPProvider(primary)

        with pytest.raises(ChainIdMismatchError):
            client.health_check()

        assert calls == []
        assert client._provider.rpc_url == primary


class TestOneTriedSetPerWriteCall:
    """One write call tries each RPC endpoint at most once, across all its steps (#168 review 2)."""

    def test_anchor_never_returns_to_the_primary_real_web3(
        self, monkeypatch, failing_rpc_server, no_web3_retry_sleep
    ):
        """Real web3. The primary fails the code check, fallback /a fails the
        "already registered" read, fallback /b fails building the transaction.
        After the switch to /a, the primary gets no request again."""
        pytest.importorskip("web3")
        from swarm_provenance_uploader.core.chain_client import ChainClient

        monkeypatch.setenv("PROVENANCE_WALLET_KEY", DUMMY_PRIVATE_KEY)
        failing_rpc_server.mode = "http401"
        node = {"web3_clientVersion": "stub/1.0", "eth_chainId": BASE_SEPOLIA_CHAIN_ID_HEX}
        code = {"eth_getCode": "0x" + DUMMY_CODE.hex()}
        failing_rpc_server.path_answers = {
            "/p": dict(node),
            "/a": {**node, **code},
            "/b": {**node, **code, "eth_call": _encoded_data_record(owner=ZERO_ADDRESS)},
        }
        base = f"http://127.0.0.1:{failing_rpc_server.server_port}"
        client = ChainClient(
            chain="base-sepolia", rpc_url=f"{base}/p", rpc_fallbacks=[f"{base}/a", f"{base}/b"]
        )

        with pytest.raises(ChainConnectionError):
            client.anchor(swarm_hash=DUMMY_HASH)

        paths = [path for path, _ in failing_rpc_server.requests]
        assert "/a" in paths and "/b" in paths, failing_rpc_server.requests
        assert "/p" not in paths[paths.index("/a"):], failing_rpc_server.requests
        assert "/a" not in paths[paths.index("/b"):], failing_rpc_server.requests
        assert "eth_sendRawTransaction" not in failing_rpc_server.methods

    def test_steps_share_the_tried_set(self, mock_chain_deps):
        """Mocked: each endpoint is probed at most once in one write call."""
        import requests

        probes = []
        web3_class = mock_chain_deps["web3_class"]
        web3_class.HTTPProvider.side_effect = lambda url, **kw: probes.append(url) or url
        web3 = mock_chain_deps["web3_instance"]
        client = _write_client(mock_chain_deps, [_log("DataRegistered")])
        primary, fb1, fb2 = client._provider._rpc_urls
        probes.clear()
        web3.eth.get_code.side_effect = [requests.exceptions.ConnectionError("down"), DUMMY_CODE]
        record = mock_chain_deps["contract"].functions.getDataRecord.return_value.call
        record.side_effect = [
            requests.exceptions.ConnectionError("down"),
            (DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", b"\x00" * 32, [], [], 0),
        ]

        client.anchor(swarm_hash=DUMMY_HASH)

        assert probes == [fb1, fb2]
        web3.eth.send_raw_transaction.assert_called_once()


class TestIsTransportFailureRealWeb3Classes:
    """_is_transport_failure with the real web3 exception classes (#168 review 2).

    No mock_chain_deps: it replaces web3 with a MagicMock, so the classes
    _is_rpc_failure looks up would not be the real ones.
    """

    @pytest.mark.parametrize("name,expected", [
        ("Web3RPCError", False),
        ("TimeExhausted", False),
        ("ContractLogicError", False),
        ("RequestTimedOut", True),
        ("BadResponseFormat", True),
        ("ProviderConnectionError", True),
    ])
    def test_web3_classes(self, name, expected):
        web3_exceptions = pytest.importorskip("web3.exceptions")
        from swarm_provenance_uploader.core.chain_client import _is_transport_failure

        error = getattr(web3_exceptions, name)("message")
        assert _is_transport_failure(error) is expected

    def test_requests_connection_error(self):
        import requests
        from swarm_provenance_uploader.core.chain_client import _is_transport_failure

        assert _is_transport_failure(requests.exceptions.ConnectionError("refused")) is True
        assert _is_transport_failure(requests.exceptions.ReadTimeout("timed out")) is True

    def test_chain_errors(self):
        from swarm_provenance_uploader.chain.exceptions import ChainIdMismatchError
        from swarm_provenance_uploader.core.chain_client import _is_transport_failure

        assert _is_transport_failure(ChainConnectionError("down")) is True
        assert _is_transport_failure(ChainIdMismatchError("wrong chain")) is False
        assert _is_transport_failure(ValueError("bad input")) is False


class TestProviderLoopsLeaveFallbackToActiveLoop:
    """While ChainClient's fallback loop runs, the provider's own loops do not fall back (#168 review 2)."""

    def test_health_check(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        web3 = mock_chain_deps["web3_instance"]
        web3.is_connected.side_effect = None
        web3.is_connected.return_value = False
        provider = ChainProvider(chain="base-sepolia")
        # Switches a few times, then has no endpoint left: without the guard
        # the test fails instead of looping
        provider._try_fallback = MagicMock(side_effect=[True, True, False])
        provider._fallback_active = True

        with pytest.raises(ChainConnectionError):
            provider.health_check()
        provider._try_fallback.assert_not_called()

    def test_get_block_number(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        web3 = mock_chain_deps["web3_instance"]
        provider = ChainProvider(chain="base-sepolia")
        # Switches a few times, then has no endpoint left: without the guard
        # the test fails instead of looping
        provider._try_fallback = MagicMock(side_effect=[True, True, False])
        provider._fallback_active = True
        type(web3.eth).block_number = PropertyMock(side_effect=ConnectionError("down"))
        try:
            with pytest.raises(ChainConnectionError):
                provider.get_block_number()
        finally:
            del type(web3.eth).block_number
        provider._try_fallback.assert_not_called()

    def test_without_an_active_loop_they_still_fall_back(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        web3 = mock_chain_deps["web3_instance"]
        web3.is_connected.side_effect = [False, True]
        provider = ChainProvider(chain="base-sepolia")
        provider._try_fallback = MagicMock(return_value=True)

        assert provider.health_check() is True
        provider._try_fallback.assert_called_once()


class TestTransformPreCheckUsesFallbacks:
    """transform()'s v2 duplicate check reads through the fallbacks (#168 review 2)."""

    def _client(self, mock_chain_deps):
        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._contract.supports_transformation_links = MagicMock(return_value=True)
        return client

    def test_duplicate_found_on_the_fallback(self, mock_chain_deps):
        import requests

        client = self._client(mock_chain_deps)
        new_hash = "b" * 64
        client._contract.get_transformation_links = MagicMock(side_effect=[
            requests.exceptions.ConnectionError("down"),
            [(bytes.fromhex(new_hash), "existing")],
        ])

        with pytest.raises(TransformationAlreadyExistsError):
            client.transform(original_hash=DUMMY_HASH, new_hash=new_hash, description="d")

        client._provider._try_fallback.assert_called_once()
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()

    def test_no_endpoint_left_is_connection_error_and_nothing_is_sent(self, mock_chain_deps):
        import requests

        client = self._client(mock_chain_deps)
        client._contract.get_transformation_links = MagicMock(
            side_effect=requests.exceptions.ConnectionError("down")
        )

        with pytest.raises(ChainConnectionError):
            client.transform(original_hash=DUMMY_HASH, new_hash="b" * 64, description="d")

        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()
        mock_chain_deps["account"].sign_transaction.assert_not_called()

    def test_other_errors_stop_the_write(self, mock_chain_deps):
        """A duplicate check that could not run stops the write (#230 review)."""
        from swarm_provenance_uploader.exceptions import ChainError

        client = self._client(mock_chain_deps)
        client._contract.get_transformation_links = MagicMock(side_effect=ValueError("bad answer"))

        with pytest.raises(ChainError, match="duplicate transformation check: bad answer. Nothing was sent."):
            client.transform(original_hash=DUMMY_HASH, new_hash="b" * 64, description="d")

        client._provider._try_fallback.assert_not_called()
        mock_chain_deps["account"].sign_transaction.assert_not_called()
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()

    def test_v1_block_number_read_falls_back(self, mock_chain_deps, monkeypatch):
        import requests
        from swarm_provenance_uploader.chain import event_cache

        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._contract.supports_transformation_links = MagicMock(return_value=False)
        cache = MagicMock()
        cache.get_maps.return_value = ({}, {})
        monkeypatch.setattr(event_cache, "get_cache", lambda *a, **k: cache)
        web3 = mock_chain_deps["web3_instance"]
        type(web3.eth).block_number = PropertyMock(
            side_effect=[requests.exceptions.ConnectionError("down"), 123, 124, 125]
        )
        try:
            client.transform(original_hash=DUMMY_HASH, new_hash="b" * 64, description="d")
        finally:
            del type(web3.eth).block_number

        client._provider._try_fallback.assert_called_once()
        cache.get_maps.assert_called_once()
        web3.eth.send_raw_transaction.assert_called_once()


class TestTransformV1PreCheckScanUsesFallbacks:
    """transform()'s v1 duplicate check runs its event scan through the fallbacks (#168 review 3)."""

    def _client(self, mock_chain_deps, monkeypatch, get_maps_side_effect):
        from swarm_provenance_uploader.chain import event_cache

        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._contract.supports_transformation_links = MagicMock(return_value=False)
        cache = MagicMock()
        cache.get_maps.side_effect = get_maps_side_effect
        monkeypatch.setattr(event_cache, "get_cache", lambda *a, **k: cache)
        return client, cache

    def test_scan_failure_falls_back_and_finds_the_duplicate(self, mock_chain_deps, monkeypatch):
        import requests

        new_hash = "b" * 64
        client, cache = self._client(mock_chain_deps, monkeypatch, [
            requests.exceptions.ConnectionError("down"),
            ({DUMMY_HASH: [(new_hash, "existing")]}, {}),
        ])

        with pytest.raises(TransformationAlreadyExistsError):
            client.transform(original_hash=DUMMY_HASH, new_hash=new_hash, description="d")

        assert cache.get_maps.call_count == 2
        client._provider._try_fallback.assert_called_once()
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()

    def test_scan_failure_on_every_endpoint_fails_closed(self, mock_chain_deps, monkeypatch):
        import requests

        client, cache = self._client(
            mock_chain_deps, monkeypatch, requests.exceptions.ConnectionError("down")
        )

        with pytest.raises(ChainConnectionError, match="duplicate transformation check"):
            client.transform(original_hash=DUMMY_HASH, new_hash="b" * 64, description="d")

        assert client._provider._try_fallback.call_count == 2  # one switch, then none left
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()
        mock_chain_deps["account"].sign_transaction.assert_not_called()

    def test_other_scan_errors_stop_the_write(self, mock_chain_deps, monkeypatch):
        """A duplicate check that could not run stops the write (#230 review)."""
        from swarm_provenance_uploader.exceptions import ChainError

        client, cache = self._client(mock_chain_deps, monkeypatch, ValueError("bad log"))

        with pytest.raises(ChainError, match="duplicate transformation check: bad log. Nothing was sent."):
            client.transform(original_hash=DUMMY_HASH, new_hash="b" * 64, description="d")

        client._provider._try_fallback.assert_not_called()
        mock_chain_deps["account"].sign_transaction.assert_not_called()
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()


class TestNestedFallbackGuard:
    """A _with_fallback call inside an active loop runs once and leaves the fallback to the outer loop (#168 review 3)."""

    def _provider(self, switches):
        from types import SimpleNamespace

        return SimpleNamespace(
            rpc_url="https://primary.rpc.io",
            _fallback_active=False,
            _fallback_tried=None,
            _try_fallback=MagicMock(side_effect=switches),
        )

    def test_inner_failure_reruns_the_outer_operation(self):
        import requests
        from swarm_provenance_uploader.core.chain_client import _with_fallback

        provider = self._provider([True, False])
        inner = MagicMock(side_effect=[requests.exceptions.ConnectionError("down"), "record"])
        outer_runs = []

        def outer():
            outer_runs.append(provider._fallback_active)
            return _with_fallback(provider, inner)

        assert _with_fallback(provider, outer) == "record"

        # The outer loop handled the failure and ran the whole operation again
        assert len(outer_runs) == 2
        assert inner.call_count == 2
        provider._try_fallback.assert_called_once()

    def test_inner_call_keeps_the_outer_loop_active(self):
        from swarm_provenance_uploader.core.chain_client import _with_fallback

        provider = self._provider([])
        seen = []

        def outer():
            _with_fallback(provider, lambda: None)
            seen.append(provider._fallback_active)

        _with_fallback(provider, outer)

        assert seen == [True]
        assert provider._fallback_active is False


@pytest.fixture
def real_web3_exceptions():
    """The real web3.exceptions module, imported before mock_chain_deps replaces web3.

    List it before mock_chain_deps in a test's arguments. Set it as
    ``sys.modules["web3"].exceptions`` inside the test, so _is_rpc_failure
    sees the real classes while the rest of web3 stays mocked.
    """
    return pytest.importorskip("web3.exceptions")


def _inject_real_exceptions(real_web3_exceptions):
    import sys

    assert not isinstance(real_web3_exceptions, MagicMock)
    sys.modules["web3"].exceptions = real_web3_exceptions


class TestProvenanceChainRejectionDoesNotFallBack:
    """A JSON-RPC error answer during the walk is not a connection failure (#168 review 4).

    With the real web3.exceptions classes: a Web3RPCError from a link,
    parent or event read became ChainConnectionError in _traversal_error,
    so the walk moved to a fallback, and a rejection on every endpoint was
    reported as "Cannot connect to chain".
    """

    def _client(self, mock_chain_deps):
        from swarm_provenance_uploader.core.chain_client import ChainClient

        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, OTHER_ADDRESS, 1, "t", b"\x00" * 32, [], [], 0,
        )
        client = ChainClient(chain="base-sepolia", require_wallet=False)
        client._provider._try_fallback = MagicMock(side_effect=[True, False, False])
        return client

    def test_state_path(self, real_web3_exceptions, mock_chain_deps):
        _inject_real_exceptions(real_web3_exceptions)
        client = self._client(mock_chain_deps)
        client._contract.supports_transformation_links = MagicMock(return_value=True)
        client._contract.get_transformation_links = MagicMock(
            side_effect=real_web3_exceptions.Web3RPCError("limit exceeded")
        )

        with pytest.raises(ChainConfigurationError) as exc_info:
            client.get_provenance_chain(DUMMY_HASH)

        assert not isinstance(exc_info.value, ChainConnectionError)
        assert "limit exceeded" in str(exc_info.value)
        client._provider._try_fallback.assert_not_called()

    def test_parents_read(self, real_web3_exceptions, mock_chain_deps):
        _inject_real_exceptions(real_web3_exceptions)
        client = self._client(mock_chain_deps)
        client._contract.supports_transformation_links = MagicMock(return_value=True)
        client._contract.get_transformation_links = MagicMock(return_value=[])
        client._contract.get_transformation_parents = MagicMock(
            side_effect=real_web3_exceptions.Web3RPCError("invalid params")
        )

        with pytest.raises(ChainConfigurationError):
            client.get_provenance_chain(DUMMY_HASH)

        client._provider._try_fallback.assert_not_called()

    def test_per_node_event_path(self, real_web3_exceptions, mock_chain_deps):
        _inject_real_exceptions(real_web3_exceptions)
        client = self._client(mock_chain_deps)
        client._contract.supports_transformation_links = MagicMock(return_value=False)
        client._provider.deploy_block = None  # no event index: per-node queries
        mock_chain_deps["web3_instance"].eth.block_number = 1_000  # window reaches block 0 (#231)
        client._contract.get_transformations_from = MagicMock(
            side_effect=real_web3_exceptions.Web3RPCError("invalid params")
        )

        with pytest.raises(ChainConfigurationError) as exc_info:
            client.get_provenance_chain(DUMMY_HASH)

        assert not isinstance(exc_info.value, ChainConnectionError)
        client._provider._try_fallback.assert_not_called()

    def test_transport_failure_in_the_walk_still_falls_back(self, real_web3_exceptions, mock_chain_deps):
        _inject_real_exceptions(real_web3_exceptions)
        client = self._client(mock_chain_deps)
        client._contract.supports_transformation_links = MagicMock(return_value=True)
        client._contract.get_transformation_links = MagicMock(side_effect=[
            real_web3_exceptions.ProviderConnectionError("down"), [],
        ])
        client._contract.get_transformation_parents = MagicMock(return_value=[])

        chain = client.get_provenance_chain(DUMMY_HASH)

        assert [r.data_hash for r in chain] == [DUMMY_HASH]
        client._provider._try_fallback.assert_called_once()


class TestWriteChainIdCheckFallsBack:
    """The chain ID check before a write moves to a fallback when eth_chainId fails (#168 review 4)."""

    @pytest.mark.parametrize("kind", ["connection_error", "json_rpc_error"])
    def test_write_proceeds_on_the_fallback(self, real_web3_exceptions, mock_chain_deps, kind):
        import requests

        error = {
            "connection_error": requests.exceptions.ConnectionError("refused"),
            # Documented exception: a JSON-RPC error answer to eth_chainId
            # falls back too (nothing is sent; the fallback is chain-checked)
            "json_rpc_error": real_web3_exceptions.Web3RPCError("rate limited"),
        }[kind]
        web3 = mock_chain_deps["web3_instance"]
        client = _fallback_client(mock_chain_deps, [_log("DataStatusChanged")])
        type(web3.eth).chain_id = PropertyMock(side_effect=[error, 84532, 84532, 84532])
        try:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)
        finally:
            del type(web3.eth).chain_id

        client._provider._try_fallback.assert_called_once()
        assert client._provider._chain_id_confirmed is True
        web3.eth.send_raw_transaction.assert_called_once()
        mock_chain_deps["account"].sign_transaction.assert_called_once()


class TestBlockNumberRejectionDoesNotFallBack:
    """A JSON-RPC error answer to eth_blockNumber is a rejection, not a connection failure (#168 review 5)."""

    def test_provider_get_block_number(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        _inject_real_exceptions(real_web3_exceptions)
        web3 = mock_chain_deps["web3_instance"]
        provider = ChainProvider(chain="base-sepolia")
        provider._try_fallback = MagicMock(side_effect=[True, False])
        rejection = real_web3_exceptions.Web3RPCError("limit exceeded")
        type(web3.eth).block_number = PropertyMock(side_effect=rejection)
        try:
            with pytest.raises(real_web3_exceptions.Web3RPCError):
                provider.get_block_number()
        finally:
            del type(web3.eth).block_number
        provider._try_fallback.assert_not_called()

    def test_provider_get_block_number_transport_failure_still_falls_back(
        self, real_web3_exceptions, mock_chain_deps
    ):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        _inject_real_exceptions(real_web3_exceptions)
        web3 = mock_chain_deps["web3_instance"]
        provider = ChainProvider(chain="base-sepolia")
        provider._try_fallback = MagicMock(side_effect=[True, False])
        type(web3.eth).block_number = PropertyMock(side_effect=[
            real_web3_exceptions.ProviderConnectionError("down"), 123,
        ])
        try:
            assert provider.get_block_number() == 123
        finally:
            del type(web3.eth).block_number
        provider._try_fallback.assert_called_once()

    def test_client_health_check_real_web3(self, failing_rpc_server, no_web3_retry_sleep):
        """Real web3: the primary answers eth_blockNumber with a JSON-RPC error; the fallback gets no request."""
        pytest.importorskip("web3")
        from swarm_provenance_uploader.core.chain_client import ChainClient

        failing_rpc_server.mode = "jsonrpc"
        node = {"web3_clientVersion": "stub/1.0", "eth_chainId": BASE_SEPOLIA_CHAIN_ID_HEX}
        failing_rpc_server.path_answers = {
            "/p": dict(node),
            "/f": {**node, "eth_blockNumber": "0x10"},
        }
        base = f"http://127.0.0.1:{failing_rpc_server.server_port}"
        client = ChainClient(
            chain="base-sepolia", rpc_url=f"{base}/p", rpc_fallbacks=[f"{base}/f"], require_wallet=False
        )

        with pytest.raises(ChainConfigurationError) as exc_info:
            client.health_check()

        assert not isinstance(exc_info.value, ChainConnectionError)
        assert client._provider.rpc_url == f"{base}/p"
        assert "/f" not in [path for path, _ in failing_rpc_server.requests]


class TestSkippedFallbackIsNotProbedAgain:
    """A fallback skipped once in a call is not probed again by a later step (#168 review 5)."""

    @pytest.mark.parametrize("middle", ["dead", "wrong_chain"])
    def test_later_step_does_not_probe_the_skipped_fallback(self, mock_chain_deps, middle):
        import requests
        from swarm_provenance_uploader.chain.provider import CHAIN_PRESETS

        primary = CHAIN_PRESETS["base-sepolia"]["rpc_url"]
        fallback1, fallback2 = CHAIN_PRESETS["base-sepolia"]["rpc_fallbacks"]
        shared = mock_chain_deps["web3_instance"]

        def candidate(connected, chain_id):
            node = MagicMock()
            node.is_connected.return_value = connected
            node.eth.chain_id = chain_id
            return node

        candidates = {
            fallback1: candidate(False, 84532) if middle == "dead" else candidate(True, 8453),
            fallback2: candidate(True, 84532),
        }
        probes = []
        web3_class = mock_chain_deps["web3_class"]
        web3_class.HTTPProvider.side_effect = lambda url, **kw: probes.append(url) or url
        # The client's own Web3 object is the shared mock; probes get their own node
        web3_class.side_effect = lambda url: shared if url == primary else candidates[url]

        client = _write_client(mock_chain_deps, [_log("DataStatusChanged")])
        probes.clear()
        # Step 1 (contract code check) fails on the primary: switch past fallback1 to fallback2
        shared.eth.get_code.side_effect = [requests.exceptions.ConnectionError("down"), DUMMY_CODE]
        # Step 2 (nonce) fails on fallback2: no endpoint is left
        shared.eth.get_transaction_count.side_effect = requests.exceptions.ConnectionError("down")

        with pytest.raises(ChainConnectionError):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert probes == [fallback1, fallback2]
        shared.eth.send_raw_transaction.assert_not_called()


# Receipt timeouts, replaced transactions and chain wait (#167)


def _timeout_client(mock_chain_deps, real_web3_exceptions, logs=(), mined_nonce=0):
    """A write client whose receipt wait times out with the real TimeExhausted.

    The pending nonce (the one the write uses) is 5; the mined nonce
    ("latest") is mined_nonce, or the exception it is set to.
    """
    _inject_real_exceptions(real_web3_exceptions)
    web3 = mock_chain_deps["web3_instance"]
    client = _write_client(mock_chain_deps, list(logs))
    web3.eth.wait_for_transaction_receipt.side_effect = real_web3_exceptions.TimeExhausted(
        "Transaction is not in the chain after 120 seconds"
    )

    def transaction_count(address, block):
        if block == "pending":
            return 5
        if isinstance(mined_nonce, Exception):
            raise mined_nonce
        return mined_nonce

    web3.eth.get_transaction_count.side_effect = transaction_count
    web3.eth.get_transaction_receipt.side_effect = real_web3_exceptions.TransactionNotFound("not found")
    return client


def _receipt(logs, status=1):
    return {
        "status": status,
        "transactionHash": DUMMY_TX_HASH_BYTES,
        "blockNumber": 12345679,
        "gasUsed": 95_000,
        "logs": list(logs),
    }


class TestReceiptTimeout:
    """A receipt timeout is pending, replaced, or mined after all; never "failed" (#167)."""

    def test_timeout_is_receipt_timeout_with_details(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import (
            ReceiptTimeoutError,
            TransactionOutcomeUnknownError,
        )

        client = _timeout_client(mock_chain_deps, real_web3_exceptions, [_log("DataStatusChanged")], mined_nonce=5)

        with pytest.raises(ReceiptTimeoutError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        e = exc_info.value
        assert isinstance(e, TransactionOutcomeUnknownError)
        assert e.tx_hash == DUMMY_TX_HASH_BYTES.hex()
        assert e.explorer_url == client._provider.get_explorer_tx_url(DUMMY_TX_HASH_BYTES.hex())
        assert e.event_name == "DataStatusChanged"
        assert e.expected_count == 1
        assert e.timeout == 120
        assert e.contract_address == DUMMY_CONTRACT
        assert "Not confirmed yet" in str(e)
        assert "failed" not in str(e).lower()
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_called_once()

    def test_nonce_check_uses_sender_and_latest(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import ReceiptTimeoutError

        web3 = mock_chain_deps["web3_instance"]
        client = _timeout_client(mock_chain_deps, real_web3_exceptions, [_log("DataStatusChanged")], mined_nonce=5)

        with pytest.raises(ReceiptTimeoutError):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        web3.eth.get_transaction_count.assert_any_call(DUMMY_ADDRESS, "latest")
        # The nonce is not above the transaction's: no second receipt lookup
        web3.eth.get_transaction_receipt.assert_not_called()

    def test_replaced_when_nonce_used_and_no_receipt(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import (
            TransactionOutcomeUnknownError,
            TransactionReplacedError,
            TransactionUnconfirmedError,
        )

        web3 = mock_chain_deps["web3_instance"]
        client = _timeout_client(mock_chain_deps, real_web3_exceptions, [_log("DataStatusChanged")], mined_nonce=6)

        with pytest.raises(TransactionReplacedError) as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

        e = exc_info.value
        assert isinstance(e, TransactionUnconfirmedError)
        assert not isinstance(e, TransactionOutcomeUnknownError)
        assert e.nonce == 5
        assert e.tx_hash == DUMMY_TX_HASH_BYTES.hex()
        assert e.event_name == "DataStatusChanged"
        assert e.explorer_url
        assert "Replaced" in str(e)
        assert "chain get" in str(e)
        web3.eth.get_transaction_receipt.assert_called_once_with(DUMMY_TX_HASH_BYTES)
        web3.eth.send_raw_transaction.assert_called_once()

    def test_replaced_delegate_advice_has_no_chain_get(self, real_web3_exceptions, mock_chain_deps):
        """A delegate write has no data record to read back (#240 review)."""
        from swarm_provenance_uploader.exceptions import TransactionReplacedError

        client = _timeout_client(mock_chain_deps, real_web3_exceptions, [_log("DelegateAuthorized")], mined_nonce=6)

        with pytest.raises(TransactionReplacedError) as exc_info:
            client.set_delegate(OTHER_ADDRESS, True)

        assert exc_info.value.event_name == "DelegateAuthorized"
        assert "chain get" not in str(exc_info.value)
        assert "delegate" in str(exc_info.value)
        assert "block explorer" in str(exc_info.value)

    def test_replaced_when_second_lookup_returns_none(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import TransactionReplacedError

        web3 = mock_chain_deps["web3_instance"]
        client = _timeout_client(mock_chain_deps, real_web3_exceptions, [_log("DataStatusChanged")], mined_nonce=6)
        web3.eth.get_transaction_receipt.side_effect = None
        web3.eth.get_transaction_receipt.return_value = None

        with pytest.raises(TransactionReplacedError):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

    def test_mined_after_wait_continues_normal_path(self, real_web3_exceptions, mock_chain_deps):
        web3 = mock_chain_deps["web3_instance"]
        client = _timeout_client(mock_chain_deps, real_web3_exceptions, mined_nonce=6)
        web3.eth.get_transaction_receipt.side_effect = None
        web3.eth.get_transaction_receipt.return_value = _receipt([_log("DataStatusChanged")])

        result = client.set_status(swarm_hash=DUMMY_HASH, status=1)

        assert result.block_number == 12345679
        assert result.gas_used == 95_000

    def test_mined_after_wait_reverted(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import TransactionUnconfirmedError

        web3 = mock_chain_deps["web3_instance"]
        client = _timeout_client(mock_chain_deps, real_web3_exceptions, mined_nonce=6)
        web3.eth.get_transaction_receipt.side_effect = None
        web3.eth.get_transaction_receipt.return_value = _receipt([], status=0)

        with pytest.raises(ChainTransactionError, match="reverted") as exc_info:
            client.set_status(swarm_hash=DUMMY_HASH, status=1)
        assert not isinstance(exc_info.value, TransactionUnconfirmedError)

    def test_mined_after_wait_not_recorded(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import TransactionNotRecordedError

        web3 = mock_chain_deps["web3_instance"]
        client = _timeout_client(mock_chain_deps, real_web3_exceptions, mined_nonce=6)
        web3.eth.get_transaction_receipt.side_effect = None
        web3.eth.get_transaction_receipt.return_value = _receipt([])

        with pytest.raises(TransactionNotRecordedError):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

    def test_nonce_check_failure_stays_receipt_timeout(self, real_web3_exceptions, mock_chain_deps):
        import requests
        from swarm_provenance_uploader.exceptions import ReceiptTimeoutError

        client = _timeout_client(
            mock_chain_deps, real_web3_exceptions, [_log("DataStatusChanged")],
            mined_nonce=requests.exceptions.ConnectionError("connection refused"),
        )

        with pytest.raises(ReceiptTimeoutError):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

    def test_second_lookup_failure_stays_receipt_timeout(self, real_web3_exceptions, mock_chain_deps):
        import requests
        from swarm_provenance_uploader.exceptions import ReceiptTimeoutError

        web3 = mock_chain_deps["web3_instance"]
        client = _timeout_client(mock_chain_deps, real_web3_exceptions, [_log("DataStatusChanged")], mined_nonce=6)
        web3.eth.get_transaction_receipt.side_effect = requests.exceptions.ConnectionError("reset")

        with pytest.raises(ReceiptTimeoutError):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)

    def test_batch_timeout_keeps_expected_count(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import ReceiptTimeoutError

        client = _timeout_client(mock_chain_deps, real_web3_exceptions, mined_nonce=5)

        with pytest.raises(ReceiptTimeoutError) as exc_info:
            client.batch_anchor([DUMMY_HASH, "c" * 64], ["t", "t"])
        assert exc_info.value.event_name == "DataRegistered"
        assert exc_info.value.expected_count == 2

    def test_new_exceptions_exported(self):
        from swarm_provenance_uploader import exceptions
        from swarm_provenance_uploader.chain import exceptions as chain_exceptions

        for name in ("ReceiptTimeoutError", "TransactionReplacedError", "TransactionNotFoundError"):
            assert getattr(exceptions, name) is getattr(chain_exceptions, name)
            assert name in dir(exceptions)
        assert issubclass(exceptions.ReceiptTimeoutError, exceptions.TransactionOutcomeUnknownError)
        assert issubclass(exceptions.TransactionReplacedError, exceptions.TransactionUnconfirmedError)
        assert not issubclass(exceptions.TransactionReplacedError, exceptions.TransactionOutcomeUnknownError)
        assert issubclass(exceptions.TransactionNotFoundError, exceptions.ChainTransactionError)
        assert not issubclass(exceptions.TransactionNotFoundError, exceptions.TransactionUnconfirmedError)


TX_HASH = "0x" + "bb" * 32


def _wait_client(mock_chain_deps, real_web3_exceptions, logs=()):
    """A client without a wallet key, for chain wait."""
    from swarm_provenance_uploader.core.chain_client import ChainClient

    _inject_real_exceptions(real_web3_exceptions)
    receipt = mock_chain_deps["web3_instance"].eth.wait_for_transaction_receipt.return_value
    receipt["logs"] = list(logs)
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("PROVENANCE_WALLET_KEY", None)
        return ChainClient(chain="base-sepolia", require_wallet=False)


class TestWaitForTransaction:
    """ChainClient.wait_for_transaction resumes a wait with the write's checks (#167)."""

    def test_confirmed_with_event(self, real_web3_exceptions, mock_chain_deps):
        web3 = mock_chain_deps["web3_instance"]
        client = _wait_client(mock_chain_deps, real_web3_exceptions, [_log("DataRegistered")])

        result = client.wait_for_transaction(TX_HASH, "DataRegistered")

        assert result.tx_hash == TX_HASH
        assert result.block_number == 12345679
        assert result.gas_used == 95_000
        assert result.status == 1
        assert result.event == "DataRegistered"
        assert result.emitted_count == 1
        assert result.explorer_url == client._provider.get_explorer_tx_url(TX_HASH)
        web3.eth.wait_for_transaction_receipt.assert_called_once_with(TX_HASH, timeout=120)
        web3.eth.send_raw_transaction.assert_not_called()
        mock_chain_deps["account"].sign_transaction.assert_not_called()

    def test_hash_without_prefix(self, real_web3_exceptions, mock_chain_deps):
        client = _wait_client(mock_chain_deps, real_web3_exceptions)

        result = client.wait_for_transaction("BB" * 32)

        assert result.tx_hash == "0x" + "BB" * 32

    def test_no_event_check_without_event(self, real_web3_exceptions, mock_chain_deps):
        client = _wait_client(mock_chain_deps, real_web3_exceptions, [])

        result = client.wait_for_transaction(TX_HASH, timeout=5)

        assert result.event is None
        assert result.emitted_count is None
        mock_chain_deps["contract"].events.DataRegistered.return_value.process_receipt.assert_not_called()
        mock_chain_deps["web3_instance"].eth.wait_for_transaction_receipt.assert_called_once_with(TX_HASH, timeout=5)

    def test_reverted(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import TransactionUnconfirmedError

        client = _wait_client(mock_chain_deps, real_web3_exceptions)
        mock_chain_deps["web3_instance"].eth.wait_for_transaction_receipt.return_value["status"] = 0

        with pytest.raises(ChainTransactionError, match="reverted") as exc_info:
            client.wait_for_transaction(TX_HASH)
        assert not isinstance(exc_info.value, TransactionUnconfirmedError)
        assert exc_info.value.tx_hash == TX_HASH

    def test_not_recorded(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import TransactionNotRecordedError

        client = _wait_client(mock_chain_deps, real_web3_exceptions, [_log("DataRegistered")])

        with pytest.raises(TransactionNotRecordedError) as exc_info:
            client.wait_for_transaction(TX_HASH, "DataRegistered", expected_count=2)
        assert exc_info.value.emitted_count == 1
        assert exc_info.value.expected_count == 2

    def _time_out(self, mock_chain_deps, real_web3_exceptions):
        web3 = mock_chain_deps["web3_instance"]
        web3.eth.wait_for_transaction_receipt.side_effect = real_web3_exceptions.TimeExhausted("timeout")
        web3.eth.get_transaction_receipt.side_effect = real_web3_exceptions.TransactionNotFound("not found")
        return web3

    def test_timeout_pending_uses_sender_of_transaction(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import ReceiptTimeoutError

        client = _wait_client(mock_chain_deps, real_web3_exceptions)
        web3 = self._time_out(mock_chain_deps, real_web3_exceptions)
        web3.eth.get_transaction.return_value = {"from": OTHER_ADDRESS, "nonce": 7}
        web3.eth.get_transaction_count.return_value = 7

        with pytest.raises(ReceiptTimeoutError) as exc_info:
            client.wait_for_transaction(TX_HASH, "DataRegistered", timeout=30)

        assert exc_info.value.timeout == 30
        assert exc_info.value.tx_hash == TX_HASH
        assert exc_info.value.event_name == "DataRegistered"
        web3.eth.get_transaction.assert_called_once_with(TX_HASH)
        web3.eth.get_transaction_count.assert_called_once_with(OTHER_ADDRESS, "latest")

    def test_timeout_replaced(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import TransactionReplacedError

        client = _wait_client(mock_chain_deps, real_web3_exceptions)
        web3 = self._time_out(mock_chain_deps, real_web3_exceptions)
        web3.eth.get_transaction.return_value = {"from": OTHER_ADDRESS, "nonce": 7}
        web3.eth.get_transaction_count.return_value = 8

        with pytest.raises(TransactionReplacedError) as exc_info:
            client.wait_for_transaction(TX_HASH)
        assert exc_info.value.nonce == 7

    def test_timeout_unknown_hash_not_found(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import TransactionNotFoundError

        client = _wait_client(mock_chain_deps, real_web3_exceptions)
        web3 = self._time_out(mock_chain_deps, real_web3_exceptions)
        web3.eth.get_transaction.side_effect = real_web3_exceptions.TransactionNotFound("not found")

        with pytest.raises(TransactionNotFoundError) as exc_info:
            client.wait_for_transaction(TX_HASH)
        assert exc_info.value.tx_hash == TX_HASH
        assert exc_info.value.explorer_url == client._provider.get_explorer_tx_url(TX_HASH)
        web3.eth.get_transaction_count.assert_not_called()

    def test_timeout_transaction_lookup_transport_failure_is_pending(self, real_web3_exceptions, mock_chain_deps):
        import requests
        from swarm_provenance_uploader.exceptions import ReceiptTimeoutError

        client = _wait_client(mock_chain_deps, real_web3_exceptions)
        web3 = self._time_out(mock_chain_deps, real_web3_exceptions)
        web3.eth.get_transaction.side_effect = requests.exceptions.ConnectionError("reset")

        with pytest.raises(ReceiptTimeoutError):
            client.wait_for_transaction(TX_HASH)

    def test_transport_failure_falls_back_for_same_hash(self, real_web3_exceptions, mock_chain_deps):
        import requests

        client = _wait_client(mock_chain_deps, real_web3_exceptions, [_log("DataRegistered")])
        web3 = mock_chain_deps["web3_instance"]
        receipt = web3.eth.wait_for_transaction_receipt.return_value
        web3.eth.wait_for_transaction_receipt.side_effect = [
            requests.exceptions.ConnectionError("reset"), receipt,
        ]
        client._provider._try_fallback = MagicMock(side_effect=[True, False])

        result = client.wait_for_transaction(TX_HASH, "DataRegistered")

        assert result.emitted_count == 1
        client._provider._try_fallback.assert_called_once()
        assert [c.args[0] for c in web3.eth.wait_for_transaction_receipt.call_args_list] == [TX_HASH, TX_HASH]

    @pytest.mark.parametrize("kwargs", [
        {"tx_hash": "0x1234"},
        {"tx_hash": "zz" * 32},
        {"tx_hash": TX_HASH, "expected_event": "NoSuchEvent"},
        {"tx_hash": TX_HASH, "expected_event": "DataRegistered", "expected_count": 0},
        {"tx_hash": TX_HASH, "timeout": 0},
    ])
    def test_invalid_arguments(self, real_web3_exceptions, mock_chain_deps, kwargs):
        client = _wait_client(mock_chain_deps, real_web3_exceptions)

        with pytest.raises(ChainValidationError):
            client.wait_for_transaction(**kwargs)
        mock_chain_deps["web3_instance"].eth.wait_for_transaction_receipt.assert_not_called()

    def test_write_and_wait_share_the_receipt_checks(self, real_web3_exceptions, mock_chain_deps):
        """_send_transaction and wait_for_transaction both go through _await_receipt."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        _inject_real_exceptions(real_web3_exceptions)
        client = _write_client(mock_chain_deps, [_log("DataStatusChanged"), _log("DataRegistered")])
        seen = []
        original = ChainClient._await_receipt

        def spy(self, *args, **kwargs):
            seen.append(args[2])
            return original(self, *args, **kwargs)

        with patch.object(ChainClient, "_await_receipt", spy):
            client.set_status(swarm_hash=DUMMY_HASH, status=1)
            client.wait_for_transaction(TX_HASH, "DataRegistered")

        assert seen == ["DataStatusChanged", "DataRegistered"]


class TestAbiEventNames:
    def test_lists_contract_events(self):
        from swarm_provenance_uploader.chain.contract import abi_event_names

        names = abi_event_names()
        for name in WRITE_EVENTS:
            assert name in names
        assert names == sorted(names)


class TestLinksProbeClassification:
    """The transformation-links probe caches v1 only on a contract answer (#230).

    With the real web3.exceptions classes. A revert or an empty result
    means the function does not exist (v1). Any other error, such as a
    transport failure or a JSON-RPC rejection, says nothing about the
    contract: it is raised and not cached, so the next call probes again.
    """

    def _contract(self, mock_chain_deps, side_effect):
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        call = mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call
        call.side_effect = side_effect
        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"], contract_address=DUMMY_CONTRACT,
        )
        return contract, call

    def test_revert_is_v1_and_cached(self, real_web3_exceptions, mock_chain_deps):
        contract, call = self._contract(
            mock_chain_deps, real_web3_exceptions.ContractLogicError("execution reverted")
        )
        assert contract.supports_transformation_links() is False
        assert contract.supports_transformation_links() is False
        assert call.call_count == 1

    def test_empty_result_is_v1_and_cached(self, real_web3_exceptions, mock_chain_deps):
        contract, call = self._contract(
            mock_chain_deps, real_web3_exceptions.BadFunctionCallOutput("returned b''")
        )
        assert contract.supports_transformation_links() is False
        assert contract.supports_transformation_links() is False
        assert call.call_count == 1

    @pytest.mark.parametrize("make_error", [
        lambda exc: exc.ProviderConnectionError("connection refused"),
        lambda exc: exc.Web3RPCError("limit exceeded"),
        lambda exc: OSError("timed out"),
    ])
    def test_other_errors_are_raised_and_not_cached(self, real_web3_exceptions, mock_chain_deps, make_error):
        error = make_error(real_web3_exceptions)
        contract, call = self._contract(mock_chain_deps, [error, []])

        with pytest.raises(type(error)):
            contract.supports_transformation_links()
        assert contract.supports_transformation_links() is True
        assert call.call_count == 2


class TestLinksProbeUsesFallbacks:
    """A transport failure in the probe goes to a fallback, not to the v1 paths (#230)."""

    def test_provenance_chain_uses_state_reads_after_probe_failure(self, real_web3_exceptions, mock_chain_deps):
        _inject_real_exceptions(real_web3_exceptions)
        from swarm_provenance_uploader.core.chain_client import ChainClient

        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, OTHER_ADDRESS, 1, "t", b"\x00" * 32, [], [], 0,
        )
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.side_effect = [
            real_web3_exceptions.ProviderConnectionError("down"), [], [],
        ]
        mock_chain_deps["contract"].functions.getTransformationParents.return_value.call.return_value = []
        client = ChainClient(chain="base-sepolia", require_wallet=False)
        client._provider._try_fallback = MagicMock(side_effect=[True, False])
        client._contract.get_transformations_from = MagicMock(return_value=[])
        client._contract.get_transformations_to = MagicMock(return_value=[])
        client._contract.get_all_transformations = MagicMock(return_value=[])

        chain = client.get_provenance_chain(DUMMY_HASH)

        assert [r.data_hash for r in chain] == [DUMMY_HASH]
        assert client._contract._supports_v2 is True
        client._provider._try_fallback.assert_called_once()
        client._contract.get_transformations_from.assert_not_called()
        client._contract.get_all_transformations.assert_not_called()

    def test_provenance_chain_probe_rejection_does_not_fall_back(self, real_web3_exceptions, mock_chain_deps):
        _inject_real_exceptions(real_web3_exceptions)
        from swarm_provenance_uploader.core.chain_client import ChainClient

        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.side_effect = (
            real_web3_exceptions.Web3RPCError("invalid params")
        )
        client = ChainClient(chain="base-sepolia", require_wallet=False)
        client._provider._try_fallback = MagicMock(side_effect=[True, False])
        client._contract.get_transformations_from = MagicMock(return_value=[])

        with pytest.raises(ChainConfigurationError) as exc_info:
            client.get_provenance_chain(DUMMY_HASH)

        assert not isinstance(exc_info.value, ChainConnectionError)
        assert client._contract._supports_v2 is None
        client._provider._try_fallback.assert_not_called()
        client._contract.get_transformations_from.assert_not_called()

    def test_transform_finds_duplicate_after_probe_failure(self, real_web3_exceptions, mock_chain_deps):
        """With no deploy block (base preset), a dead primary no longer skips the check (#230 comment)."""
        _inject_real_exceptions(real_web3_exceptions)
        new_hash = "b" * 64
        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._provider.deploy_block = None
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.side_effect = [
            real_web3_exceptions.ProviderConnectionError("down"),
            [],
            [(bytes.fromhex(new_hash), "existing")],
        ]

        with pytest.raises(TransformationAlreadyExistsError):
            client.transform(original_hash=DUMMY_HASH, new_hash=new_hash, description="d")

        client._provider._try_fallback.assert_called_once()
        mock_chain_deps["account"].sign_transaction.assert_not_called()
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()

    def test_transform_probe_failure_on_every_endpoint_fails_closed(self, real_web3_exceptions, mock_chain_deps):
        _inject_real_exceptions(real_web3_exceptions)
        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._provider.deploy_block = None
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.side_effect = (
            real_web3_exceptions.ProviderConnectionError("down")
        )

        with pytest.raises(ChainConnectionError, match="duplicate transformation check"):
            client.transform(original_hash=DUMMY_HASH, new_hash="b" * 64, description="d")

        assert client._contract._supports_v2 is None
        mock_chain_deps["account"].sign_transaction.assert_not_called()
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()

    def test_transform_v1_without_deploy_block_warns(self, real_web3_exceptions, mock_chain_deps, caplog):
        import logging

        _inject_real_exceptions(real_web3_exceptions)
        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._provider.deploy_block = None
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.side_effect = (
            real_web3_exceptions.ContractLogicError("execution reverted")
        )

        with caplog.at_level(logging.WARNING, logger="swarm_provenance_uploader"):
            client.transform(original_hash=DUMMY_HASH, new_hash="b" * 64, description="d")

        assert "Duplicate transformation check skipped" in caplog.text
        assert "CHAIN_DEPLOY_BLOCK" in caplog.text
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_called_once()


class TestDeployBlockSetting:
    """CHAIN_DEPLOY_BLOCK / deploy_block, and no preset deploy block for a custom contract (#231)."""

    CUSTOM = "0x1234567890abcdef1234567890abcdef12345678"

    def test_preset_deploy_block_for_preset_contract(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        assert ChainProvider(chain="base-sepolia").deploy_block == 39_905_249
        # The preset contract given explicitly, in another case, is still the preset's
        provider = ChainProvider(chain="base-sepolia", contract_address=DUMMY_CONTRACT.lower())
        assert provider.deploy_block == 39_905_249

    def test_custom_contract_does_not_use_the_preset_deploy_block(self, mock_chain_deps):
        """A contract deployed before the preset block would lose its older events."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia", contract_address=self.CUSTOM)
        assert provider.deploy_block is None

    def test_custom_contract_with_deploy_block(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia", contract_address=self.CUSTOM, deploy_block=1_000)
        assert provider.deploy_block == 1_000

    @pytest.mark.parametrize("value, expected", [
        (0, 0), (123, 123), ("123", 123), (" 7 ", 7), ("", 39_905_249), (None, 39_905_249),
    ])
    def test_deploy_block_values(self, mock_chain_deps, value, expected):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        assert ChainProvider(chain="base-sepolia", deploy_block=value).deploy_block == expected

    @pytest.mark.parametrize("value", [-1, "-1", "abc", "1.5", "1_000", "0x10", "١٢", True, 1.0])
    def test_invalid_deploy_block_rejected(self, mock_chain_deps, value):
        from swarm_provenance_uploader.chain.provider import ChainProvider

        with pytest.raises(ChainConfigurationError) as exc_info:
            ChainProvider(chain="base-sepolia", deploy_block=value)
        assert "CHAIN_DEPLOY_BLOCK" in str(exc_info.value)
        assert "non-negative integer" in str(exc_info.value)

    def test_chain_client_passes_deploy_block(self, mock_chain_deps):
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(
            chain="base-sepolia", contract_address=self.CUSTOM, deploy_block="2000", require_wallet=False,
        )
        assert client._provider.deploy_block == 2_000

    def test_deploy_block_used_by_the_event_scan(self, mock_chain_deps):
        """A v1 custom contract with CHAIN_DEPLOY_BLOCK uses the event index from that block."""
        from swarm_provenance_uploader.chain.event_cache import clear_registry
        from swarm_provenance_uploader.core.chain_client import ChainClient

        clear_registry()
        client = ChainClient(
            chain="base-sepolia", contract_address=self.CUSTOM, deploy_block=2_000, require_wallet=False,
        )
        client._contract._supports_v2 = False
        client._contract.get_all_transformations = MagicMock(return_value=[])
        client._contract.get_all_merge_events = MagicMock(return_value=[])
        client._contract.get_transformations_from = MagicMock(return_value=[])

        client.get_provenance_chain(DUMMY_HASH)

        assert client._contract.get_all_transformations.call_args.kwargs["from_block"] == 2_000
        client._contract.get_transformations_from.assert_not_called()
        clear_registry()


class TestProvenanceChainIncompleteLineageFailsClosed:
    """A lineage that may be incomplete is never returned (#231).

    The per-node event lookup scans only the last 50,000 blocks. It is used
    when the deploy block is unknown; it was also the fallback after a
    failed full event scan. In both cases it could miss older
    transformations without an error.
    """

    def _v1_client(self, mock_chain_deps, deploy_block, block_number):
        from swarm_provenance_uploader.chain.event_cache import clear_registry
        from swarm_provenance_uploader.core.chain_client import ChainClient

        clear_registry()
        client = ChainClient(chain="base-sepolia", require_wallet=False)
        client._contract._supports_v2 = False
        client._provider.deploy_block = deploy_block
        mock_chain_deps["web3_instance"].eth.block_number = block_number
        client._contract.get_transformations_from = MagicMock(return_value=[])
        client._contract.get_transformations_to = MagicMock(return_value=[])
        return client

    def test_unknown_deploy_block_on_a_long_chain_fails_closed(self, mock_chain_deps):
        client = self._v1_client(mock_chain_deps, None, 60_000)

        with pytest.raises(ChainConfigurationError) as exc_info:
            client.get_provenance_chain(DUMMY_HASH)

        message = str(exc_info.value)
        assert "incomplete" in message
        assert "50,000" in message
        assert "CHAIN_DEPLOY_BLOCK" in message
        client._contract.get_transformations_from.assert_not_called()

    def test_unknown_deploy_block_window_reaching_block_0_is_complete(self, mock_chain_deps):
        client = self._v1_client(mock_chain_deps, None, 50_000)

        chain = client.get_provenance_chain(DUMMY_HASH)

        assert [r.data_hash for r in chain] == [DUMMY_HASH]
        client._contract.get_transformations_from.assert_called_once()

    def test_full_scan_transport_failure_falls_back_then_fails_closed(self, mock_chain_deps):
        import requests

        client = self._v1_client(mock_chain_deps, 0, 60_000)
        client._contract.get_all_transformations = MagicMock(
            side_effect=requests.exceptions.ConnectionError("down")
        )
        client._provider._try_fallback = MagicMock(side_effect=[True, False])

        with pytest.raises(ChainConnectionError):
            client.get_provenance_chain(DUMMY_HASH)

        assert client._contract.get_all_transformations.call_count == 2
        client._contract.get_transformations_from.assert_not_called()

    def test_full_scan_other_error_fails_closed(self, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import ChainError

        client = self._v1_client(mock_chain_deps, 0, 60_000)
        client._contract.get_all_transformations = MagicMock(side_effect=ValueError("bad log"))

        with pytest.raises(ChainError) as exc_info:
            client.get_provenance_chain(DUMMY_HASH)

        assert "event scan failed" in str(exc_info.value)
        assert "bad log" in str(exc_info.value)
        client._contract.get_transformations_from.assert_not_called()

    def test_full_scan_after_fallback_succeeds(self, mock_chain_deps):
        import requests

        child = "b" * 64
        client = self._v1_client(mock_chain_deps, 0, 60_000)
        client._contract.get_all_transformations = MagicMock(side_effect=[
            requests.exceptions.ConnectionError("down"),
            [(DUMMY_HASH_BYTES, bytes.fromhex(child), "step")],
        ])
        client._contract.get_all_merge_events = MagicMock(return_value=[])
        client._provider._try_fallback = MagicMock(side_effect=[True, False])

        chain = client.get_provenance_chain(DUMMY_HASH, max_depth=0)

        assert chain[0].transformations[0].new_data_hash == child
        client._contract.get_transformations_from.assert_not_called()


class TestTransformDuplicateCheckRejectionStopsTheWrite:
    """A duplicate check that could not run stops the write before signing (#230 review).

    With the real web3.exceptions classes. transform() logged a JSON-RPC
    error answer or another error, then signed and sent the transaction,
    so a duplicate could be recorded.
    """

    MESSAGE = "The RPC rejected the request during the duplicate transformation check"

    def _assert_nothing_sent(self, mock_chain_deps):
        mock_chain_deps["account"].sign_transaction.assert_not_called()
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()

    def test_probe_rejection(self, real_web3_exceptions, mock_chain_deps):
        _inject_real_exceptions(real_web3_exceptions)
        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.side_effect = (
            real_web3_exceptions.Web3RPCError("rate limited")
        )

        with pytest.raises(ChainConfigurationError) as exc_info:
            client.transform(original_hash=DUMMY_HASH, new_hash="b" * 64, description="d")

        assert str(exc_info.value) == f"{self.MESSAGE}: rate limited. Nothing was sent."
        client._provider._try_fallback.assert_not_called()
        self._assert_nothing_sent(mock_chain_deps)

    def test_state_read_rejection(self, real_web3_exceptions, mock_chain_deps):
        _inject_real_exceptions(real_web3_exceptions)
        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._contract.supports_transformation_links = MagicMock(return_value=True)
        client._contract.get_transformation_links = MagicMock(
            side_effect=real_web3_exceptions.Web3RPCError("rate limited")
        )

        with pytest.raises(ChainConfigurationError, match=f"{self.MESSAGE}: rate limited. Nothing was sent."):
            client.transform(original_hash=DUMMY_HASH, new_hash="b" * 64, description="d")

        client._provider._try_fallback.assert_not_called()
        self._assert_nothing_sent(mock_chain_deps)

    def test_v1_scan_rejection(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.chain.event_cache import clear_registry

        _inject_real_exceptions(real_web3_exceptions)
        clear_registry()
        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._contract.supports_transformation_links = MagicMock(return_value=False)
        client._provider.deploy_block = 0
        client._contract.get_all_transformations = MagicMock(
            side_effect=real_web3_exceptions.Web3RPCError("query returned more than 10000 results")
        )

        try:
            with pytest.raises(ChainConfigurationError, match="more than 10000 results. Nothing was sent."):
                client.transform(original_hash=DUMMY_HASH, new_hash="b" * 64, description="d")
        finally:
            clear_registry()

        client._provider._try_fallback.assert_not_called()
        self._assert_nothing_sent(mock_chain_deps)

    def test_probe_other_error(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.exceptions import ChainError

        _inject_real_exceptions(real_web3_exceptions)
        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._contract.supports_transformation_links = MagicMock(side_effect=ValueError("odd answer"))

        with pytest.raises(ChainError) as exc_info:
            client.transform(original_hash=DUMMY_HASH, new_hash="b" * 64, description="d")

        assert not isinstance(exc_info.value, (ChainConfigurationError, ChainConnectionError))
        assert "duplicate transformation check: odd answer. Nothing was sent." in str(exc_info.value)
        self._assert_nothing_sent(mock_chain_deps)


class TestEventCacheKeyedByDeployBlock:
    """Two clients with different deploy blocks do not share one event cache (#231 review)."""

    def test_earlier_deploy_block_sees_older_edge(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.event_cache import clear_registry
        from swarm_provenance_uploader.core.chain_client import ChainClient

        clear_registry()
        child = "b" * 64

        def scan(from_block, to_block):
            # One edge, at block 500
            if from_block <= 500 <= to_block:
                return [(DUMMY_HASH_BYTES, bytes.fromhex(child), "step")]
            return []

        def make_client(deploy_block):
            client = ChainClient(chain="base-sepolia", deploy_block=deploy_block, require_wallet=False)
            client._contract._supports_v2 = False
            client._contract.get_all_transformations = MagicMock(side_effect=scan)
            client._contract.get_all_merge_events = MagicMock(return_value=[])
            return client

        mock_chain_deps["web3_instance"].eth.block_number = 60_000
        client_a = make_client(1_000)
        client_b = make_client(0)
        try:
            chain_a = client_a.get_provenance_chain(DUMMY_HASH, max_depth=0)
            chain_b = client_b.get_provenance_chain(DUMMY_HASH, max_depth=0)
        finally:
            clear_registry()

        assert chain_a[0].transformations == []
        assert [t.new_data_hash for t in chain_b[0].transformations] == [child]
        assert client_b._contract.get_all_transformations.call_args.kwargs["from_block"] == 0


class TestPerNodeWindowIsTheCheckedWindow:
    """The per-node queries scan the window that the completeness check checked (#231 review)."""

    def test_queries_use_the_checked_block(self, mock_chain_deps):
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia", require_wallet=False)
        client._contract._supports_v2 = False
        client._provider.deploy_block = None
        client._contract.get_transformations_from = MagicMock(return_value=[])
        client._contract.get_transformations_to = MagicMock(return_value=[])
        web3 = mock_chain_deps["web3_instance"]
        # Checked at 50,000; a later read would see a longer chain
        type(web3.eth).block_number = PropertyMock(side_effect=[50_000] + [60_000] * 10)
        try:
            client.get_provenance_chain(DUMMY_HASH)
        finally:
            del type(web3.eth).block_number

        assert client._contract.get_transformations_from.call_args.kwargs["to_block"] == 50_000
        assert client._contract.get_transformations_to.call_args.kwargs["to_block"] == 50_000

    @pytest.mark.parametrize("method", ["get_transformations_from", "get_transformations_to"])
    def test_contract_query_ends_at_to_block(self, mock_chain_deps, method):
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        web3 = mock_chain_deps["web3_instance"]
        contract = DataProvenanceContract(web3=web3, contract_address=DUMMY_CONTRACT)
        contract._get_logs_chunked = MagicMock(return_value=[])
        type(web3.eth).block_number = PropertyMock(side_effect=AssertionError("block number read"))
        try:
            getattr(contract, method)(DUMMY_HASH, to_block=70_000)
        finally:
            del type(web3.eth).block_number

        _, _, from_block, to_block = contract._get_logs_chunked.call_args.args
        assert (from_block, to_block) == (20_000, 70_000)


class TestRecordReadProbeTransportFailure:
    """getDataRecord fails, then the probe hits a transport failure (#230 review)."""

    def test_contract_raises_and_does_not_cache(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        functions = mock_chain_deps["contract"].functions
        functions.getDataRecord.return_value.call.side_effect = OverflowError("decode")
        functions.getTransformationLinks.return_value.call.side_effect = (
            real_web3_exceptions.ProviderConnectionError("down")
        )
        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"], contract_address=DUMMY_CONTRACT,
        )

        with pytest.raises(real_web3_exceptions.ProviderConnectionError):
            contract.get_data_record(DUMMY_HASH)
        assert contract._supports_v2 is None
        functions.dataRecords.return_value.call.assert_not_called()

    def test_read_loop_falls_back(self, real_web3_exceptions, mock_chain_deps):
        from swarm_provenance_uploader.core.chain_client import ChainClient

        _inject_real_exceptions(real_web3_exceptions)
        functions = mock_chain_deps["contract"].functions
        functions.getDataRecord.return_value.call.side_effect = [
            OverflowError("decode"),
            (DUMMY_HASH_BYTES, OTHER_ADDRESS, 1, "t", b"\x00" * 32, [], [], 0),
        ]
        functions.getTransformationLinks.return_value.call.side_effect = (
            real_web3_exceptions.ProviderConnectionError("down")
        )
        client = ChainClient(chain="base-sepolia", require_wallet=False)
        client._provider._try_fallback = MagicMock(side_effect=[True, False])

        record = client.get(DUMMY_HASH)

        assert record.owner == OTHER_ADDRESS
        client._provider._try_fallback.assert_called_once()
        assert client._contract._supports_v2 is None
        functions.dataRecords.return_value.call.assert_not_called()


class TestDeployBlockAboveChainHead:
    """A deploy block above the chain head is a configuration error, not an empty lineage (#231 review 2).

    The usual cause is a CHAIN_DEPLOY_BLOCK left over after a change of
    CHAIN_NAME. The first scan returned empty maps, so the lineage was the
    start node only and transform()'s v1 duplicate check passed.
    """

    def test_get_maps_raises_on_first_scan(self):
        from swarm_provenance_uploader.chain.event_cache import TransformationEventCache

        cache = TransformationEventCache()
        contract = MagicMock()
        with pytest.raises(ChainConfigurationError) as exc_info:
            cache.get_maps(contract, deploy_block=100_000, current_block=60_000)
        message = str(exc_info.value)
        assert "CHAIN_DEPLOY_BLOCK" in message
        assert "100,000" in message
        assert "60,000" in message
        contract.get_all_transformations.assert_not_called()
        assert cache._last_scanned_block is None

    def test_no_new_blocks_after_a_scan_is_not_an_error(self):
        from swarm_provenance_uploader.chain.event_cache import TransformationEventCache

        cache = TransformationEventCache()
        contract = MagicMock()
        contract.get_all_transformations.return_value = []
        contract.get_all_merge_events.return_value = []
        cache.get_maps(contract, deploy_block=0, current_block=1_000)
        assert cache.get_maps(contract, deploy_block=0, current_block=1_000) == ({}, {})

    def _v1_client(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.event_cache import clear_registry
        from swarm_provenance_uploader.core.chain_client import ChainClient

        clear_registry()
        client = ChainClient(chain="base-sepolia", deploy_block=100_000)
        client._contract._supports_v2 = False
        client._contract.get_all_transformations = MagicMock(return_value=[])
        client._contract.get_all_merge_events = MagicMock(return_value=[])
        mock_chain_deps["web3_instance"].eth.block_number = 60_000
        return client

    def test_provenance_chain_raises(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.event_cache import clear_registry

        client = self._v1_client(mock_chain_deps)
        try:
            with pytest.raises(ChainConfigurationError, match="CHAIN_DEPLOY_BLOCK"):
                client.get_provenance_chain(DUMMY_HASH)
        finally:
            clear_registry()

    def test_transform_raises_and_sends_nothing(self, mock_chain_deps):
        from swarm_provenance_uploader.chain.event_cache import clear_registry

        client = self._v1_client(mock_chain_deps)
        try:
            with pytest.raises(ChainConfigurationError, match="CHAIN_DEPLOY_BLOCK"):
                client.transform(original_hash=DUMMY_HASH, new_hash="b" * 64, description="d")
        finally:
            clear_registry()
        mock_chain_deps["account"].sign_transaction.assert_not_called()
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()


# 0x prefix and upper case, for the original and the new hash
_HASH_SPELLINGS = [
    pytest.param(lambda h: "0x" + h, lambda h: h, id="original-0x"),
    pytest.param(lambda h: h.upper(), lambda h: h, id="original-upper"),
    pytest.param(lambda h: h, lambda h: "0x" + h, id="new-0x"),
    pytest.param(lambda h: h, lambda h: h.upper(), id="new-upper"),
    pytest.param(lambda h: "0x" + h.upper(), lambda h: "0x" + h.upper(), id="both"),
]


class TestTransformDuplicateCheckNormalizesHashes:
    """The duplicate check finds a duplicate however the hashes are written (#230 review 2).

    It compared the input as given with lower-case hex without 0x, so a
    0x prefix or upper case skipped the check and the duplicate was sent.
    """

    ORIGINAL = "ab" * 32
    NEW = "cd" * 32

    def _assert_nothing_sent(self, mock_chain_deps):
        mock_chain_deps["account"].sign_transaction.assert_not_called()
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()

    @pytest.mark.parametrize("spell_original, spell_new", _HASH_SPELLINGS)
    def test_v2_duplicate_found(self, mock_chain_deps, spell_original, spell_new):
        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._contract.supports_transformation_links = MagicMock(return_value=True)
        client._contract.get_transformation_links = MagicMock(
            return_value=[(bytes.fromhex(self.NEW), "existing")]
        )

        with pytest.raises(TransformationAlreadyExistsError):
            client.transform(
                original_hash=spell_original(self.ORIGINAL), new_hash=spell_new(self.NEW), description="d"
            )
        self._assert_nothing_sent(mock_chain_deps)

    @pytest.mark.parametrize("spell_original, spell_new", _HASH_SPELLINGS)
    def test_v1_duplicate_found(self, mock_chain_deps, monkeypatch, spell_original, spell_new):
        from swarm_provenance_uploader.chain import event_cache

        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._contract.supports_transformation_links = MagicMock(return_value=False)
        client._provider.deploy_block = 0
        cache = MagicMock()
        cache.get_maps.return_value = ({self.ORIGINAL: [(self.NEW, "existing")]}, {})
        monkeypatch.setattr(event_cache, "get_cache", lambda *a, **k: cache)

        with pytest.raises(TransformationAlreadyExistsError):
            client.transform(
                original_hash=spell_original(self.ORIGINAL), new_hash=spell_new(self.NEW), description="d"
            )
        self._assert_nothing_sent(mock_chain_deps)

    def test_sent_hashes_and_result_unchanged(self, mock_chain_deps):
        """A transformation that is not a duplicate is encoded and reported as before."""
        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._contract.supports_transformation_links = MagicMock(return_value=True)
        client._contract.get_transformation_links = MagicMock(return_value=[])
        original, new = "0x" + self.ORIGINAL.upper(), "0x" + self.NEW

        result = client.transform(original_hash=original, new_hash=new, description="d")

        record = mock_chain_deps["contract"].functions.recordTransformation
        assert record.call_args.args == (bytes.fromhex(self.ORIGINAL), bytes.fromhex(self.NEW), "d")
        assert (result.original_hash, result.new_hash) == (original, new)
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_called_once()


class TestTransformInvalidHashIsAValidationError:
    """An invalid hash raises ChainValidationError before the duplicate check (#230 review 2)."""

    @pytest.mark.parametrize("v2", [True, False], ids=["v2", "v1"])
    @pytest.mark.parametrize("field", ["original_hash", "new_hash"])
    def test_invalid_hash(self, mock_chain_deps, v2, field):
        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._contract.supports_transformation_links = MagicMock(return_value=v2)
        client._contract.get_transformation_links = MagicMock(return_value=[])
        client._provider.deploy_block = None
        hashes = {"original_hash": DUMMY_HASH, "new_hash": "b" * 64, field: "zz"}

        with pytest.raises(ChainValidationError):
            client.transform(description="d", **hashes)

        client._contract.supports_transformation_links.assert_not_called()
        mock_chain_deps["account"].sign_transaction.assert_not_called()
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()

    def test_validation_error_from_the_check_passes_through(self, mock_chain_deps):
        """A ChainError other than a connection error from the check keeps its class and message."""
        client = _fallback_client(mock_chain_deps, [_log("DataTransformed")])
        client._contract.supports_transformation_links = MagicMock(return_value=True)
        client._contract.get_transformation_links = MagicMock(side_effect=ChainValidationError("bad hash"))

        with pytest.raises(ChainValidationError) as exc_info:
            client.transform(original_hash=DUMMY_HASH, new_hash="b" * 64, description="d")

        assert str(exc_info.value) == "bad hash"
        mock_chain_deps["web3_instance"].eth.send_raw_transaction.assert_not_called()
