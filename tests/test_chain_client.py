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
DUMMY_CONTRACT = "0xD4a724CD7f5C4458cD2d884C2af6f011aC3Af80a"
DUMMY_TX_HASH_BYTES = bytes.fromhex("bb" * 32)
ZERO_ADDRESS = "0x" + "0" * 40


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
        mock_web3_instance.eth.get_transaction_count.return_value = 0
        mock_web3_instance.eth.estimate_gas.return_value = 100_000
        mock_web3_instance.eth.send_raw_transaction.return_value = DUMMY_TX_HASH_BYTES
        mock_web3_instance.eth.wait_for_transaction_receipt.return_value = {
            "status": 1,
            "transactionHash": DUMMY_TX_HASH_BYTES,
            "blockNumber": 12345679,
            "gasUsed": 95_000,
        }
        mock_web3_instance.is_connected.return_value = True

        # Mock contract
        mock_contract = MagicMock()
        mock_web3_instance.eth.contract.return_value = mock_contract

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

        # Mock read functions
        mock_contract.functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES,  # dataHash
            DUMMY_ADDRESS,     # owner
            1700000000,        # timestamp
            "swarm-provenance",  # dataType
            [],                # transformations
            [],                # accessors
            0,                 # status (ACTIVE)
        )
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
        assert provider.contract_address == "0xD4a724CD7f5C4458cD2d884C2af6f011aC3Af80a"

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
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", [], [], 0,
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
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", [], [], 0,
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
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", [], [], 0,
        )

        client = ChainClient(chain="base-sepolia")
        result = client.anchor(swarm_hash=DUMMY_HASH)

        assert result.data_type == "swarm-provenance"

    def test_anchor_for_success(self, mock_chain_deps):
        """Tests anchoring on behalf of another owner."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Pre-check expects unregistered hash
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", [], [], 0,
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
        client = ChainClient(chain="base-sepolia")
        result = client.batch_anchor(
            swarm_hashes=[DUMMY_HASH, hash2],
            data_types=["type1", "type2"],
        )

        assert isinstance(result, AnchorResult)
        assert result.swarm_hash == DUMMY_HASH

    def test_anchor_invalid_hash(self, mock_chain_deps):
        """Tests that invalid hash raises validation error."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")
        with pytest.raises(ChainValidationError):
            client.anchor(swarm_hash="tooshort")


class TestChainClientAlreadyRegistered:
    """Tests for already-registered hash pre-check in anchor/anchor_for."""

    def test_anchor_raises_already_registered(self, mock_chain_deps):
        """Tests that anchoring an already-registered hash raises DataAlreadyRegisteredError."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        # Default mock returns a registered record (owner=DUMMY_ADDRESS)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.return_value = (
            DUMMY_HASH_BYTES, DUMMY_ADDRESS, 1700000000, "swarm-provenance", [], [], 0,
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
            DUMMY_HASH_BYTES, DUMMY_ADDRESS, 1700000000, "swarm-provenance", [], [], 0,
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
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", [], [], 0,
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
            [],
            [],
            0,
        )

        client = ChainClient(chain="base-sepolia")
        assert client.verify(swarm_hash=DUMMY_HASH) is False

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
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", [], [], 0,
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
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", [], [], 0,
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
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", [], [], 0,
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
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", [], [], 0,
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
            DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", [], [], 0,
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
            ["filtered PII", "anonymized"],
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
            ["filtered"],
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
                    [], [], 0,
                )
            else:
                mock_call.call.return_value = (
                    data_hash, ZERO_ADDRESS, 0, "", [], [], 0,
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
                [], [], 0,
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
                    DUMMY_HASH_BYTES, ZERO_ADDRESS, 0, "", [], [], 0,
                )
            else:
                # Second call (after revert): now registered
                mock_call.call.return_value = (
                    DUMMY_HASH_BYTES, DUMMY_ADDRESS, 1700000000, "swarm-provenance", [], [], 0,
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
        """Tests fallback to dataRecords() when v2 ABI decode fails on v1."""
        from swarm_provenance_uploader.chain.contract import DataProvenanceContract

        # getDataRecord fails (v2 ABI decode error on v1 contract)
        mock_chain_deps["contract"].functions.getDataRecord.return_value.call.side_effect = OverflowError("decode")
        # getTransformationLinks also fails (v1 contract)
        mock_chain_deps["contract"].functions.getTransformationLinks.return_value.call.side_effect = Exception("revert")
        # dataRecords returns scalar-only tuple
        mock_chain_deps["contract"].functions.dataRecords.return_value.call.return_value = (
            DUMMY_HASH_BYTES, DUMMY_ADDRESS, 1700000000, "swarm-provenance", 0
        )

        contract = DataProvenanceContract(
            web3=mock_chain_deps["web3_instance"],
            contract_address=DUMMY_CONTRACT,
        )
        record = contract.get_data_record(DUMMY_HASH)

        # Should return 7-element tuple with empty arrays for transformations/accessors
        assert record[0] == DUMMY_HASH_BYTES
        assert record[1] == DUMMY_ADDRESS
        assert record[4] == []  # transformations (empty)
        assert record[5] == []  # accessors (empty)


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
        assert provider.deploy_block == 39_075_766


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
                    [], [], 0,
                )
            elif data_hash == hash_b_bytes:
                mock_call.call.return_value = (
                    hash_b_bytes, DUMMY_ADDRESS, 1700000001, "swarm-provenance",
                    [], [], 0,
                )
            else:
                mock_call.call.return_value = (data_hash, ZERO_ADDRESS, 0, "", [], [], 0)
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
                mock_call.call.return_value = (hash_a_bytes, DUMMY_ADDRESS, 1700000000, "type", [], [], 0)
            elif data_hash == hash_b_bytes:
                mock_call.call.return_value = (hash_b_bytes, DUMMY_ADDRESS, 1700000001, "type", [], [], 0)
            else:
                mock_call.call.return_value = (data_hash, ZERO_ADDRESS, 0, "", [], [], 0)
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
