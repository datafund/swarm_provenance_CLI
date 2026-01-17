"""Tests for the x402 payment client module."""

import base64
import json
import os
import pytest
from unittest.mock import MagicMock, patch

from swarm_provenance_uploader.exceptions import (
    InsufficientBalanceError,
    PaymentRequiredError,
    X402ConfigurationError,
    X402NetworkError,
)
from swarm_provenance_uploader.models import (
    X402PaymentOption,
    X402PaymentRequirements,
)


# Test constants
DUMMY_PRIVATE_KEY = "0x" + "a" * 64  # 32 bytes hex
DUMMY_ADDRESS = "0x742d35Cc6634C0532925a3b844Bc9e7595f8fE00"
DUMMY_PAY_TO = "0x1234567890AbcdEF1234567890aBcDeF12345678"


# Sample 402 response
SAMPLE_402_RESPONSE = {
    "x402Version": 1,
    "accepts": [
        {
            "scheme": "exact",
            "network": "base-sepolia",
            "maxAmountRequired": "50000",  # $0.05 USDC
            "resource": "/api/v1/stamps/",
            "description": "Stamp purchase",
            "payTo": DUMMY_PAY_TO,
            "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        }
    ],
}


@pytest.fixture
def mock_eth_deps():
    """Mock eth-account and web3 dependencies."""
    with patch.dict(os.environ, {"SWARM_X402_PRIVATE_KEY": DUMMY_PRIVATE_KEY}):
        # Mock eth_account
        mock_account = MagicMock()
        mock_account.address = DUMMY_ADDRESS
        mock_account.sign_message.return_value = MagicMock(
            signature=MagicMock(hex=lambda: "0x" + "b" * 130)
        )

        mock_account_class = MagicMock()
        mock_account_class.from_key.return_value = mock_account

        # Mock web3
        mock_web3_instance = MagicMock()
        mock_contract = MagicMock()
        mock_contract.functions.balanceOf.return_value.call.return_value = 10_000_000  # $10 USDC
        mock_web3_instance.eth.contract.return_value = mock_contract
        mock_web3_instance.to_checksum_address = lambda x: x

        mock_web3_class = MagicMock(return_value=mock_web3_instance)
        mock_web3_class.HTTPProvider = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "eth_account": MagicMock(Account=mock_account_class),
                "eth_account.messages": MagicMock(encode_typed_data=MagicMock(return_value=b"typed_data")),
                "web3": MagicMock(Web3=mock_web3_class),
            },
        ):
            yield {
                "account": mock_account,
                "account_class": mock_account_class,
                "web3_instance": mock_web3_instance,
                "web3_class": mock_web3_class,
                "contract": mock_contract,
            }


class TestX402ClientInit:
    """Tests for X402Client initialization."""

    def test_missing_private_key_raises_error(self, mock_eth_deps):
        """Tests that missing private key raises configuration error."""
        # Clear env vars and re-test
        with patch.dict(os.environ, {}, clear=True):
            from swarm_provenance_uploader.core.x402_client import X402Client

            with pytest.raises(X402ConfigurationError) as exc_info:
                X402Client()

            assert "private key not configured" in str(exc_info.value).lower()

    def test_unsupported_network_raises_error(self, mock_eth_deps):
        """Tests that unsupported network raises error."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        with pytest.raises(X402NetworkError) as exc_info:
            X402Client(network="ethereum-mainnet")

        assert "unsupported network" in str(exc_info.value).lower()

    def test_valid_init_with_env_key(self, mock_eth_deps):
        """Tests successful initialization with env var key."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client()

        assert client.address == DUMMY_ADDRESS
        assert client.network == "base-sepolia"

    def test_valid_init_with_provided_key(self, mock_eth_deps):
        """Tests successful initialization with provided key."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client(private_key=DUMMY_PRIVATE_KEY)

        assert client.address == DUMMY_ADDRESS

    def test_network_selection(self, mock_eth_deps):
        """Tests network can be specified."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client(network="base")

        assert client.network == "base"


class TestX402ClientParse402:
    """Tests for parsing 402 responses."""

    def test_parse_valid_402_response(self, mock_eth_deps):
        """Tests parsing a valid 402 response."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client()
        requirements = client.parse_402_response(SAMPLE_402_RESPONSE)

        assert isinstance(requirements, X402PaymentRequirements)
        assert len(requirements.accepts) == 1
        assert requirements.accepts[0].network == "base-sepolia"
        assert requirements.accepts[0].maxAmountRequired == "50000"

    def test_parse_invalid_402_response(self, mock_eth_deps):
        """Tests parsing an invalid 402 response raises error."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client()

        with pytest.raises(PaymentRequiredError):
            client.parse_402_response({"invalid": "data"})


class TestX402ClientSelectPaymentOption:
    """Tests for selecting payment options."""

    def test_select_matching_network_option(self, mock_eth_deps):
        """Tests selecting an option matching configured network."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client(network="base-sepolia")
        requirements = X402PaymentRequirements(
            accepts=[
                X402PaymentOption(
                    scheme="exact",
                    network="base-sepolia",
                    maxAmountRequired="50000",
                    resource="/test",
                    payTo=DUMMY_PAY_TO,
                ),
                X402PaymentOption(
                    scheme="exact",
                    network="base",
                    maxAmountRequired="100000",
                    resource="/test",
                    payTo=DUMMY_PAY_TO,
                ),
            ]
        )

        option = client.select_payment_option(requirements)

        assert option.network == "base-sepolia"
        assert option.maxAmountRequired == "50000"

    def test_no_matching_network_raises_error(self, mock_eth_deps):
        """Tests that no matching network raises error."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client(network="base-sepolia")
        requirements = X402PaymentRequirements(
            accepts=[
                X402PaymentOption(
                    scheme="exact",
                    network="base",  # Different network
                    maxAmountRequired="50000",
                    resource="/test",
                    payTo=DUMMY_PAY_TO,
                ),
            ]
        )

        with pytest.raises(X402NetworkError) as exc_info:
            client.select_payment_option(requirements)

        assert "base-sepolia" in str(exc_info.value)

    def test_prefers_exact_scheme(self, mock_eth_deps):
        """Tests that 'exact' scheme is preferred."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client(network="base-sepolia")
        requirements = X402PaymentRequirements(
            accepts=[
                X402PaymentOption(
                    scheme="other",
                    network="base-sepolia",
                    maxAmountRequired="100000",
                    resource="/test",
                    payTo=DUMMY_PAY_TO,
                ),
                X402PaymentOption(
                    scheme="exact",
                    network="base-sepolia",
                    maxAmountRequired="50000",
                    resource="/test",
                    payTo=DUMMY_PAY_TO,
                ),
            ]
        )

        option = client.select_payment_option(requirements)

        assert option.scheme == "exact"


class TestX402ClientBalance:
    """Tests for balance checking."""

    def test_get_balance_success(self, mock_eth_deps):
        """Tests getting USDC balance."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client()
        raw, usdc = client.get_usdc_balance()

        assert raw == 10_000_000  # Raw units
        assert usdc == 10.0  # USDC (6 decimals)

    def test_balance_sufficient(self, mock_eth_deps):
        """Tests balance check when sufficient."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client()
        result = client.check_balance_sufficient("50000")  # $0.05

        assert result is True

    def test_balance_insufficient(self):
        """Tests balance check when insufficient."""
        with patch.dict(os.environ, {"SWARM_X402_PRIVATE_KEY": DUMMY_PRIVATE_KEY}):
            # Mock eth_account
            mock_account = MagicMock()
            mock_account.address = DUMMY_ADDRESS

            mock_account_class = MagicMock()
            mock_account_class.from_key.return_value = mock_account

            # Mock web3 with low balance
            mock_web3_instance = MagicMock()
            mock_contract = MagicMock()
            mock_contract.functions.balanceOf.return_value.call.return_value = 10_000  # $0.01
            mock_web3_instance.eth.contract.return_value = mock_contract
            mock_web3_instance.to_checksum_address = lambda x: x

            mock_web3_class = MagicMock(return_value=mock_web3_instance)
            mock_web3_class.HTTPProvider = MagicMock()

            with patch.dict(
                "sys.modules",
                {
                    "eth_account": MagicMock(Account=mock_account_class),
                    "eth_account.messages": MagicMock(encode_typed_data=MagicMock(return_value=b"typed_data")),
                    "web3": MagicMock(Web3=mock_web3_class),
                },
            ):
                # Force reimport to get new mocks
                import importlib
                import swarm_provenance_uploader.core.x402_client as x402_module
                # Reset the lazy import globals
                x402_module._eth_account = None
                x402_module._web3 = None

                from swarm_provenance_uploader.core.x402_client import X402Client

                client = X402Client()

                with pytest.raises(InsufficientBalanceError) as exc_info:
                    client.check_balance_sufficient("50000")  # $0.05

                assert exc_info.value.required == "50000"
                assert exc_info.value.available == "10000"


class TestX402ClientSignPayment:
    """Tests for payment signing."""

    def test_sign_payment_success(self, mock_eth_deps):
        """Tests signing a payment."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client()
        option = X402PaymentOption(
            scheme="exact",
            network="base-sepolia",
            maxAmountRequired="50000",
            resource="/test",
            payTo=DUMMY_PAY_TO,
        )

        header = client.sign_payment(option)

        # Verify it's base64 encoded
        decoded = base64.b64decode(header)
        payload = json.loads(decoded)

        assert payload["x402Version"] == 1
        assert payload["scheme"] == "exact"
        assert payload["network"] == "base-sepolia"
        assert "signature" in payload["payload"]
        assert "authorization" in payload["payload"]


class TestX402ClientCreatePaymentHeader:
    """Tests for the main entry point."""

    def test_create_payment_header_success(self, mock_eth_deps):
        """Tests creating a complete payment header."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client()
        header = client.create_payment_header(SAMPLE_402_RESPONSE)

        # Verify it's valid base64
        decoded = base64.b64decode(header)
        payload = json.loads(decoded)

        assert payload["x402Version"] == 1
        assert "payload" in payload

    def test_create_payment_header_with_balance_check(self, mock_eth_deps):
        """Tests payment header creation with balance check enabled."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client()
        header = client.create_payment_header(
            SAMPLE_402_RESPONSE,
            check_balance=True,
        )

        assert header is not None

    def test_create_payment_header_insufficient_balance(self):
        """Tests payment header creation fails with insufficient balance."""
        with patch.dict(os.environ, {"SWARM_X402_PRIVATE_KEY": DUMMY_PRIVATE_KEY}):
            # Mock eth_account
            mock_account = MagicMock()
            mock_account.address = DUMMY_ADDRESS

            mock_account_class = MagicMock()
            mock_account_class.from_key.return_value = mock_account

            # Mock web3 with low balance
            mock_web3_instance = MagicMock()
            mock_contract = MagicMock()
            mock_contract.functions.balanceOf.return_value.call.return_value = 10_000  # $0.01
            mock_web3_instance.eth.contract.return_value = mock_contract
            mock_web3_instance.to_checksum_address = lambda x: x

            mock_web3_class = MagicMock(return_value=mock_web3_instance)
            mock_web3_class.HTTPProvider = MagicMock()

            with patch.dict(
                "sys.modules",
                {
                    "eth_account": MagicMock(Account=mock_account_class),
                    "eth_account.messages": MagicMock(encode_typed_data=MagicMock(return_value=b"typed_data")),
                    "web3": MagicMock(Web3=mock_web3_class),
                },
            ):
                # Force reimport to get new mocks
                import swarm_provenance_uploader.core.x402_client as x402_module
                x402_module._eth_account = None
                x402_module._web3 = None

                from swarm_provenance_uploader.core.x402_client import X402Client

                client = X402Client()

                with pytest.raises(InsufficientBalanceError):
                    client.create_payment_header(
                        SAMPLE_402_RESPONSE,
                        check_balance=True,
                    )


class TestX402ClientFormatting:
    """Tests for formatting utilities."""

    def test_format_amount_usd(self, mock_eth_deps):
        """Tests formatting amount as USD."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client()

        assert client.format_amount_usd("50000") == "$0.05"
        assert client.format_amount_usd("1000000") == "$1.00"
        assert client.format_amount_usd("10000000") == "$10.00"
