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
    DataNotRegisteredError,
)
from swarm_provenance_uploader.models import (
    AnchorResult,
    AccessResult,
    ChainProvenanceRecord,
    ChainWalletInfo,
    DataStatusEnum,
    TransformResult,
)


# Test constants
DUMMY_PRIVATE_KEY = "0x" + "a" * 64
DUMMY_ADDRESS = "0x742d35Cc6634C0532925a3b844Bc9e7595f8fE00"
DUMMY_HASH = "a" * 64
DUMMY_HASH_BYTES = bytes.fromhex(DUMMY_HASH)
DUMMY_CONTRACT = "0x9a3c6F47B69211F05891CCb7aD33596290b9fE64"
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
            # Reset lazy import globals
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
        assert provider.contract_address == "0x9a3c6F47B69211F05891CCb7aD33596290b9fE64"

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
        assert url == "https://sepolia.basescan.org/tx/0xabc123"

    def test_explorer_tx_url_without_prefix(self, mock_chain_deps):
        """Tests explorer URL auto-adds 0x prefix."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia")
        url = provider.get_explorer_tx_url("abc123")
        assert url == "https://sepolia.basescan.org/tx/0xabc123"

    def test_explorer_address_url(self, mock_chain_deps):
        """Tests generating address explorer URL."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia")
        url = provider.get_explorer_address_url(DUMMY_ADDRESS)
        assert "sepolia.basescan.org/address/" in url


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

        client = ChainClient(chain="base-sepolia")
        result = client.anchor(swarm_hash=DUMMY_HASH, data_type="test-data")

        assert isinstance(result, AnchorResult)
        assert result.swarm_hash == DUMMY_HASH
        assert result.data_type == "test-data"
        assert result.owner == DUMMY_ADDRESS
        assert result.block_number == 12345679
        assert result.gas_used == 95_000
        assert "sepolia.basescan.org" in result.explorer_url

    def test_anchor_default_data_type(self, mock_chain_deps):
        """Tests anchor uses default data type."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient(chain="base-sepolia")
        result = client.anchor(swarm_hash=DUMMY_HASH)

        assert result.data_type == "swarm-provenance"

    def test_anchor_for_success(self, mock_chain_deps):
        """Tests anchoring on behalf of another owner."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

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

        client = ChainClient(chain="base-sepolia", gas_limit_multiplier=1.5)
        client.anchor(swarm_hash=DUMMY_HASH)

        # Verify gas was multiplied: 100000 * 1.5 = 150000
        # Check the tx dict that was passed to sign_transaction
        call_args = mock_chain_deps["account"].sign_transaction.call_args
        tx = call_args[0][0]
        assert tx["gas"] == 150_000


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
