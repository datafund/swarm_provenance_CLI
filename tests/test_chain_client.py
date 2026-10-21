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

        mock_chain_deps["web3_instance"].eth.chain_id = 9999
        provider = ChainProvider(chain="base-sepolia")

        with pytest.raises(ChainConnectionError) as exc_info:
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

    def test_get_provenance_chain_default_cap_at_50(self, mock_chain_deps):
        """Tests that max_depth=None defaults to 50 (safety cap)."""
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

        # max_depth=None should use internal cap of 50, not error
        chain = client.get_provenance_chain(swarm_hash=hash_a, max_depth=None)
        assert len(chain) == 1

    def test_get_provenance_chain_negative_depth(self, mock_chain_deps):
        """Tests that negative max_depth returns empty results (no records traversed)."""
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

        # Negative depth: current_depth (0) > effective_max (-1) → skipped
        chain = client.get_provenance_chain(swarm_hash=hash_a, max_depth=-1)
        assert len(chain) == 0


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

    def test_detects_v1_contract(self, mock_chain_deps):
        """Tests that v1 contract is detected when getTransformationLinks reverts."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.side_effect = Exception("revert")

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

    def test_get_data_record_v1_fallback(self, mock_chain_deps):
        """Tests fallback to dataRecords() when v4 ABI decode fails on v1."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        # getDataRecord fails (v4 ABI decode error on v1 contract)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.side_effect = OverflowError("decode")
        # getTransformationLinks also fails (v1 contract)
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.side_effect = Exception("revert")
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

    def test_get_data_record_v4_fallback_with_storage_ref(self, mock_chain_deps):
        """Tests fallback to dataRecords() on v4 contract (6-field tuple with storageRef)."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        storage_ref = bytes.fromhex("bb" * 32)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.side_effect = OverflowError("decode")
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.side_effect = Exception("revert")
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

        cache1 = get_cache("base-sepolia", DUMMY_CONTRACT)
        cache2 = get_cache("base-sepolia", DUMMY_CONTRACT)
        assert cache1 is cache2

    def test_different_keys_different_instances(self):
        """Tests that different chain/contract combos get different caches."""
        from swarm_provenance_uploader.chain.event_cache import get_cache

        cache1 = get_cache("base-sepolia", DUMMY_CONTRACT)
        cache2 = get_cache("base", "0x" + "11" * 20)
        assert cache1 is not cache2

    def test_case_insensitive_address(self):
        """Tests that contract address lookup is case-insensitive."""
        from swarm_provenance_uploader.chain.event_cache import get_cache

        cache1 = get_cache("base-sepolia", "0xABCDEF")
        cache2 = get_cache("base-sepolia", "0xabcdef")
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

    def test_merge_events_skipped_on_v1(self):
        """Tests that DataMerged scan failure is silently skipped (v1 contracts)."""
        from swarm_provenance_uploader.chain.event_cache import TransformationEventCache

        cache = TransformationEventCache()
        mock_contract = MagicMock()
        mock_contract.get_all_transformations.return_value = []
        mock_contract.get_all_merge_events.side_effect = Exception("no DataMerged event")

        # Should not raise
        forward, reverse = cache.get_maps(mock_contract, deploy_block=0, current_block=1000)
        assert forward == {}
        assert reverse == {}


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
        """Endpoints that connect but report the wrong chain used to be switched between forever (#132)."""
        from swarm_provenance_uploader.chain.provider import ChainProvider
        from swarm_provenance_uploader.chain.exceptions import ChainConnectionError

        web3 = mock_chain_deps["web3_instance"]
        web3.is_connected.side_effect = None
        web3.is_connected.return_value = True
        web3.eth.chain_id = 1  # not Base Sepolia, on every endpoint

        provider = ChainProvider(chain="base-sepolia")
        with pytest.raises(ChainConnectionError, match="Chain ID mismatch"):
            provider.health_check()
        assert web3.is_connected.call_count <= 2 * len(provider._rpc_urls)

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
        ChainClient._build_tx(MagicMock(), build)

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
        ChainClient._build_tx(MagicMock(), failing(rejection))
    assert type(exc_info.value) is ChainTransactionError
    assert "The RPC rejected the transaction: nonce too low" in str(exc_info.value)

    for transport in (
        web3_exceptions.ProviderConnectionError("refused"),
        web3_exceptions.TimeExhausted("timeout"),
        web3_exceptions.BadResponseFormat("bad"),
        json.JSONDecodeError("Expecting value", "<html>", 0),
    ):
        with pytest.raises(ChainConnectionError):
            ChainClient._build_tx(MagicMock(), failing(transport))
