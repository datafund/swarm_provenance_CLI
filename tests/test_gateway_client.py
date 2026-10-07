"""Tests for the GatewayClient module."""

import pytest
import requests
from swarm_provenance_uploader.core.gateway_client import GatewayClient
from swarm_provenance_uploader.models import (
    StampDetails,
    StampListResponse,
    WalletResponse,
    ChequebookResponse,
)


# Test constants
DUMMY_STAMP = "a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3"
DUMMY_SWARM_REF = "b5d4ea763a1396676771151158461f73678f1676166acd06a0a18600b85de8a4"


class TestGatewayClientInit:
    """Tests for GatewayClient initialization."""

    def test_default_url(self):
        """Tests default gateway URL."""
        client = GatewayClient()
        assert client.base_url == "https://provenance-gateway.datafund.io"

    def test_custom_url(self):
        """Tests custom gateway URL."""
        client = GatewayClient(base_url="https://custom.gateway.io")
        assert client.base_url == "https://custom.gateway.io"

    def test_url_trailing_slash_stripped(self):
        """Tests trailing slash is stripped from URL."""
        client = GatewayClient(base_url="https://custom.gateway.io/")
        assert client.base_url == "https://custom.gateway.io"

    def test_api_key_stored(self):
        """Tests API key is stored."""
        client = GatewayClient(api_key="test-key")
        assert client.api_key == "test-key"


class TestGatewayClientHealth:
    """Tests for health check functionality."""

    def test_health_check_success(self, requests_mock):
        """Tests successful health check."""
        requests_mock.get("https://test.gateway.io/", json={})

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.health_check()

        assert result is True

    def test_health_check_failure(self, requests_mock):
        """Tests health check failure."""
        requests_mock.get("https://test.gateway.io/", status_code=500)

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.health_check()

        assert result is False

    def test_health_check_connection_error(self, requests_mock):
        """Tests health check with connection error."""
        requests_mock.get(
            "https://test.gateway.io/",
            exc=requests.exceptions.ConnectionError
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.health_check()

        assert result is False


class TestGatewayClientStamps:
    """Tests for stamp-related functionality."""

    def test_list_stamps_success(self, requests_mock):
        """Tests listing stamps."""
        requests_mock.get(
            "https://test.gateway.io/api/v1/stamps/",
            json={
                "stamps": [
                    {
                        "batchID": DUMMY_STAMP,
                        "utilization": 10,
                        "usable": True,
                        "label": None,
                        "depth": 17,
                        "amount": "1000000000",
                        "bucketDepth": 16,
                        "blockNumber": 12345,
                        "immutableFlag": False,
                        "exists": True,
                        "batchTTL": 86400,
                    }
                ],
                "total_count": 1
            }
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.list_stamps()

        assert isinstance(result, StampListResponse)
        assert len(result.stamps) == 1
        assert result.stamps[0].batchID == DUMMY_STAMP
        assert result.total_count == 1

    def test_list_stamps_empty(self, requests_mock):
        """Tests listing stamps when none exist."""
        requests_mock.get(
            "https://test.gateway.io/api/v1/stamps/",
            json={"stamps": [], "total_count": 0}
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.list_stamps()

        assert len(result.stamps) == 0
        assert result.total_count == 0

    def test_purchase_stamp_success(self, requests_mock):
        """Tests purchasing a stamp with duration_hours."""
        requests_mock.post(
            "https://test.gateway.io/api/v1/stamps/",
            json={"batchID": DUMMY_STAMP, "message": "Stamp purchased"},
            status_code=201
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.purchase_stamp(duration_hours=48)

        assert result == DUMMY_STAMP

    def test_purchase_stamp_with_size(self, requests_mock):
        """Tests purchasing a stamp with size preset."""
        adapter = requests_mock.post(
            "https://test.gateway.io/api/v1/stamps/",
            json={"batchID": DUMMY_STAMP},
            status_code=201
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        client.purchase_stamp(size="medium")

        # Verify size was sent in request
        assert adapter.last_request.json()["size"] == "medium"

    def test_purchase_stamp_with_label(self, requests_mock):
        """Tests purchasing a stamp with label."""
        adapter = requests_mock.post(
            "https://test.gateway.io/api/v1/stamps/",
            json={"batchID": DUMMY_STAMP},
            status_code=201
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        client.purchase_stamp(duration_hours=24, label="test-label")

        # Verify label was sent in request
        assert adapter.last_request.json()["label"] == "test-label"

    def test_purchase_stamp_legacy_amount(self, requests_mock):
        """Tests purchasing a stamp with legacy amount parameter."""
        adapter = requests_mock.post(
            "https://test.gateway.io/api/v1/stamps/",
            json={"batchID": DUMMY_STAMP},
            status_code=201
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        client.purchase_stamp(amount=1000000000, depth=17)

        # Verify legacy params were sent
        assert adapter.last_request.json()["amount"] == 1000000000
        assert adapter.last_request.json()["depth"] == 17

    def test_get_stamp_success(self, requests_mock):
        """Tests getting stamp details."""
        requests_mock.get(
            f"https://test.gateway.io/api/v1/stamps/{DUMMY_STAMP.lower()}",
            json={
                "batchID": DUMMY_STAMP,
                "utilization": 5,
                "usable": True,
                "label": "test",
                "depth": 17,
                "amount": "1000000000",
                "bucketDepth": 16,
                "blockNumber": 12345,
                "immutableFlag": False,
                "exists": True,
                "batchTTL": 3600,
            }
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.get_stamp(DUMMY_STAMP)

        assert isinstance(result, StampDetails)
        assert result.batchID == DUMMY_STAMP
        assert result.usable is True

    def test_get_stamp_not_found(self, requests_mock):
        """Tests getting non-existent stamp."""
        requests_mock.get(
            f"https://test.gateway.io/api/v1/stamps/{DUMMY_STAMP.lower()}",
            status_code=404
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.get_stamp(DUMMY_STAMP)

        assert result is None

    def test_extend_stamp_success(self, requests_mock):
        """Tests extending a stamp."""
        requests_mock.patch(
            f"https://test.gateway.io/api/v1/stamps/{DUMMY_STAMP.lower()}/extend",
            json={"batchID": DUMMY_STAMP, "message": "Stamp extended"}
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.extend_stamp(DUMMY_STAMP, amount=500000000)

        assert result == DUMMY_STAMP


class TestGatewayClientData:
    """Tests for data upload/download functionality."""

    def test_upload_data_success(self, requests_mock):
        """Tests uploading data."""
        requests_mock.post(
            "https://test.gateway.io/api/v1/data/",
            json={"reference": DUMMY_SWARM_REF, "message": "Upload successful"}
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.upload_data(
            data=b"test data",
            stamp_id=DUMMY_STAMP
        )

        assert result == DUMMY_SWARM_REF

    def test_upload_data_with_content_type(self, requests_mock):
        """Tests uploading data with custom content type."""
        adapter = requests_mock.post(
            "https://test.gateway.io/api/v1/data/",
            json={"reference": DUMMY_SWARM_REF}
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        client.upload_data(
            data=b"test data",
            stamp_id=DUMMY_STAMP,
            content_type="text/plain"
        )

        # Verify content_type param was sent
        assert "content_type=text" in adapter.last_request.url

    def test_download_data_success(self, requests_mock):
        """Tests downloading data."""
        test_data = b"downloaded test data"
        requests_mock.get(
            f"https://test.gateway.io/api/v1/data/{DUMMY_SWARM_REF.lower()}",
            content=test_data
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.download_data(DUMMY_SWARM_REF)

        assert result == test_data

    def test_download_data_not_found(self, requests_mock):
        """Tests downloading non-existent data."""
        requests_mock.get(
            f"https://test.gateway.io/api/v1/data/{DUMMY_SWARM_REF.lower()}",
            status_code=404
        )

        client = GatewayClient(base_url="https://test.gateway.io")

        with pytest.raises(FileNotFoundError):
            client.download_data(DUMMY_SWARM_REF)


class TestGatewayClientWallet:
    """Tests for wallet/chequebook functionality."""

    def test_get_wallet_success(self, requests_mock):
        """Tests getting wallet info."""
        requests_mock.get(
            "https://test.gateway.io/api/v1/wallet",
            json={
                "walletAddress": "0x1234567890abcdef1234567890abcdef12345678",
                "bzzBalance": "100.5"
            }
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.get_wallet()

        assert isinstance(result, WalletResponse)
        assert result.walletAddress == "0x1234567890abcdef1234567890abcdef12345678"
        assert result.bzzBalance == "100.5"

    def test_get_chequebook_success(self, requests_mock):
        """Tests getting chequebook info."""
        requests_mock.get(
            "https://test.gateway.io/api/v1/chequebook",
            json={
                "chequebookAddress": "0xabcdef1234567890abcdef1234567890abcdef12",
                "availableBalance": "50.0",
                "totalBalance": "100.0"
            }
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.get_chequebook()

        assert isinstance(result, ChequebookResponse)
        assert result.availableBalance == "50.0"


class TestGatewayClientErrorHandling:
    """Tests for error handling."""

    def test_connection_error_on_list_stamps(self, requests_mock):
        """Tests connection error handling."""
        requests_mock.get(
            "https://test.gateway.io/api/v1/stamps/",
            exc=requests.exceptions.ConnectionError
        )

        client = GatewayClient(base_url="https://test.gateway.io")

        with pytest.raises(ConnectionError):
            client.list_stamps()

    def test_timeout_error(self, requests_mock):
        """Tests timeout error handling."""
        requests_mock.get(
            "https://test.gateway.io/api/v1/wallet",
            exc=requests.exceptions.Timeout
        )

        client = GatewayClient(base_url="https://test.gateway.io")

        with pytest.raises(ConnectionError):
            client.get_wallet()

    def test_api_key_in_headers(self, requests_mock):
        """Tests API key is included in headers."""
        adapter = requests_mock.get(
            "https://test.gateway.io/api/v1/stamps/",
            json={"stamps": [], "total_count": 0}
        )

        client = GatewayClient(base_url="https://test.gateway.io", api_key="secret-key")
        client.list_stamps()

        assert adapter.last_request.headers.get("Authorization") == "Bearer secret-key"


# =============================================================================
# x402 PAYMENT HANDLING TESTS
# =============================================================================

class TestGatewayClientX402:
    """Tests for x402 payment handling."""

    # Sample 402 response
    SAMPLE_402_RESPONSE = {
        "x402Version": 1,
        "accepts": [
            {
                "scheme": "exact",
                "network": "base-sepolia",
                "maxAmountRequired": "50000",
                "resource": "/api/v1/stamps/",
                "description": "Stamp purchase",
                "payTo": "0x1234567890AbcdEF1234567890aBcDeF12345678",
                "asset": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
            }
        ],
    }

    def test_402_without_x402_enabled_raises_error(self, requests_mock):
        """Tests that 402 response raises PaymentRequiredError when x402 disabled."""
        from swarm_provenance_uploader.exceptions import PaymentRequiredError

        requests_mock.post(
            "https://test.gateway.io/api/v1/stamps/",
            status_code=402,
            json=self.SAMPLE_402_RESPONSE,
        )

        client = GatewayClient(base_url="https://test.gateway.io", x402_enabled=False)

        with pytest.raises(PaymentRequiredError) as exc_info:
            client.purchase_stamp(duration_hours=24)

        assert "x402" in str(exc_info.value).lower() or "payment required" in str(exc_info.value).lower()

    def test_402_error_includes_payment_options(self, requests_mock):
        """Tests that PaymentRequiredError includes payment options."""
        from swarm_provenance_uploader.exceptions import PaymentRequiredError

        requests_mock.post(
            "https://test.gateway.io/api/v1/stamps/",
            status_code=402,
            json=self.SAMPLE_402_RESPONSE,
        )

        client = GatewayClient(base_url="https://test.gateway.io", x402_enabled=False)

        with pytest.raises(PaymentRequiredError) as exc_info:
            client.purchase_stamp()

        # Should have payment options in the exception
        assert exc_info.value.payment_options is not None

    def test_x402_init_parameters(self):
        """Tests x402 initialization parameters are stored."""
        client = GatewayClient(
            base_url="https://test.gateway.io",
            x402_enabled=True,
            x402_network="base",
            x402_auto_pay=True,
            x402_max_auto_pay_usd=5.00,
        )

        assert client.x402_enabled is True
        assert client._x402_network == "base"
        assert client._x402_auto_pay is True
        assert client._x402_max_auto_pay_usd == 5.00

    def test_should_auto_pay_within_limit(self):
        """Tests auto-pay check when within limit."""
        client = GatewayClient(
            base_url="https://test.gateway.io",
            x402_enabled=True,
            x402_auto_pay=True,
            x402_max_auto_pay_usd=1.00,
        )

        assert client._should_auto_pay(0.50) is True
        assert client._should_auto_pay(1.00) is True
        assert client._should_auto_pay(1.01) is False

    def test_should_auto_pay_disabled(self):
        """Tests auto-pay check when disabled."""
        client = GatewayClient(
            base_url="https://test.gateway.io",
            x402_enabled=True,
            x402_auto_pay=False,
            x402_max_auto_pay_usd=10.00,
        )

        assert client._should_auto_pay(0.50) is False

    def test_upload_data_402_without_x402(self, requests_mock):
        """Tests that upload_data handles 402 when x402 disabled."""
        from swarm_provenance_uploader.exceptions import PaymentRequiredError

        requests_mock.post(
            "https://test.gateway.io/api/v1/data/",
            status_code=402,
            json=self.SAMPLE_402_RESPONSE,
        )

        client = GatewayClient(base_url="https://test.gateway.io", x402_enabled=False)

        with pytest.raises(PaymentRequiredError):
            client.upload_data(data=b"test", stamp_id=DUMMY_STAMP)

    def test_payment_callback_called(self, requests_mock):
        """Tests that payment callback is called for confirmation."""
        from unittest.mock import MagicMock, patch
        from swarm_provenance_uploader.exceptions import PaymentRequiredError

        # First request returns 402
        requests_mock.post(
            "https://test.gateway.io/api/v1/stamps/",
            [
                {"status_code": 402, "json": self.SAMPLE_402_RESPONSE},
                {"status_code": 201, "json": {"batchID": DUMMY_STAMP}},
            ],
        )

        callback = MagicMock(return_value=False)  # User declines

        client = GatewayClient(
            base_url="https://test.gateway.io",
            x402_enabled=True,
            x402_private_key="0x" + "a" * 64,
            x402_auto_pay=False,
            x402_payment_callback=callback,
        )

        # Mock the x402 client
        with patch.object(client, '_get_x402_client') as mock_get_client:
            mock_x402 = MagicMock()
            mock_x402.parse_402_response.return_value = MagicMock(accepts=[MagicMock(
                scheme="exact",
                network="base-sepolia",
                maxAmountRequired="50000",
                resource="/api/v1/stamps/",
                description="Stamp purchase",
                model_dump=lambda: {},
            )])
            mock_x402.select_payment_option.return_value = MagicMock(
                maxAmountRequired="50000",
                network="base-sepolia",
                description="Stamp purchase",
                resource="/api/v1/stamps/",
                model_dump=lambda: {},
            )
            mock_x402.format_amount_usd.return_value = "$0.05"
            mock_get_client.return_value = mock_x402

            with pytest.raises(PaymentRequiredError) as exc_info:
                client.purchase_stamp()

            # Callback should have been called
            callback.assert_called_once()
            assert "declined" in str(exc_info.value).lower()

    def test_auto_pay_skips_callback(self, requests_mock):
        """Tests that auto-pay bypasses callback when within limit."""
        from unittest.mock import MagicMock, patch

        # First request returns 402, second succeeds
        requests_mock.post(
            "https://test.gateway.io/api/v1/stamps/",
            [
                {"status_code": 402, "json": self.SAMPLE_402_RESPONSE},
                {"status_code": 201, "json": {"batchID": DUMMY_STAMP}},
            ],
        )

        callback = MagicMock(return_value=True)

        client = GatewayClient(
            base_url="https://test.gateway.io",
            x402_enabled=True,
            x402_private_key="0x" + "a" * 64,
            x402_auto_pay=True,
            x402_max_auto_pay_usd=1.00,  # $1 limit, payment is $0.05
            x402_payment_callback=callback,
        )

        # Mock the x402 client
        with patch.object(client, '_get_x402_client') as mock_get_client:
            mock_x402 = MagicMock()
            mock_x402.parse_402_response.return_value = MagicMock(accepts=[MagicMock(
                maxAmountRequired="50000",  # $0.05
            )])
            mock_x402.select_payment_option.return_value = MagicMock(
                maxAmountRequired="50000",
                network="base-sepolia",
                description="Stamp purchase",
            )
            mock_x402.format_amount_usd.return_value = "$0.05"
            # Return a valid string for the payment header
            mock_x402.sign_payment.return_value = "ZHVtbXlfcGF5bWVudF9oZWFkZXI="  # base64 encoded
            mock_get_client.return_value = mock_x402

            # Should succeed without calling callback (auto-pay within limit)
            result = client.purchase_stamp()

            # Callback should NOT be called since auto-pay handles it
            callback.assert_not_called()
            assert result is not None

    def test_auto_pay_exceeds_limit_calls_callback(self, requests_mock):
        """Tests that auto-pay calls callback when payment exceeds limit."""
        from unittest.mock import MagicMock, patch
        from swarm_provenance_uploader.exceptions import PaymentRequiredError

        requests_mock.post(
            "https://test.gateway.io/api/v1/stamps/",
            [
                {"status_code": 402, "json": self.SAMPLE_402_RESPONSE},
            ],
        )

        callback = MagicMock(return_value=False)  # User declines

        client = GatewayClient(
            base_url="https://test.gateway.io",
            x402_enabled=True,
            x402_private_key="0x" + "a" * 64,
            x402_auto_pay=True,
            x402_max_auto_pay_usd=0.01,  # $0.01 limit, payment is $0.05
            x402_payment_callback=callback,
        )

        with patch.object(client, '_get_x402_client') as mock_get_client:
            mock_x402 = MagicMock()
            mock_x402.parse_402_response.return_value = MagicMock(accepts=[MagicMock(
                maxAmountRequired="50000",  # $0.05 exceeds $0.01 limit
            )])
            mock_x402.select_payment_option.return_value = MagicMock(
                maxAmountRequired="50000",
                network="base-sepolia",
                description="Stamp purchase",
            )
            mock_x402.format_amount_usd.return_value = "$0.05"
            mock_get_client.return_value = mock_x402

            with pytest.raises(PaymentRequiredError):
                client.purchase_stamp()

            # Callback SHOULD be called since payment exceeds auto-pay limit
            callback.assert_called_once()

    def test_x402_disabled_by_default(self):
        """Tests that x402 is disabled by default."""
        client = GatewayClient(base_url="https://test.gateway.io")
        assert client.x402_enabled is False

    def test_x402_default_network_is_base_sepolia(self):
        """Tests default x402 network is base-sepolia."""
        client = GatewayClient(
            base_url="https://test.gateway.io",
            x402_enabled=True,
        )
        assert client._x402_network == "base-sepolia"

    def test_402_disabled_detail_wrapped(self, requests_mock):
        """Tests that x402-disabled path extracts amounts from detail-wrapped 402."""
        from swarm_provenance_uploader.exceptions import PaymentRequiredError

        wrapped_response = {"detail": self.SAMPLE_402_RESPONSE}

        requests_mock.post(
            "https://test.gateway.io/api/v1/stamps/",
            status_code=402,
            json=wrapped_response,
        )

        client = GatewayClient(base_url="https://test.gateway.io", x402_enabled=False)

        with pytest.raises(PaymentRequiredError) as exc_info:
            client.purchase_stamp(duration_hours=24)

        # Should have extracted payment options from inside detail wrapper
        assert exc_info.value.payment_options is not None
        assert len(exc_info.value.payment_options) == 1
        assert "50000" in str(exc_info.value)

    def test_402_non_json_response(self, requests_mock):
        """Tests handling of 402 with non-JSON response body."""
        from swarm_provenance_uploader.exceptions import PaymentRequiredError

        requests_mock.post(
            "https://test.gateway.io/api/v1/stamps/",
            status_code=402,
            text="Payment Required",
        )

        client = GatewayClient(base_url="https://test.gateway.io", x402_enabled=False)

        with pytest.raises(PaymentRequiredError):
            client.purchase_stamp()


class TestGatewayClientPool:
    """Tests for stamp pool functionality."""

    SAMPLE_POOL_STATUS = {
        "enabled": True,
        "reserve_config": {"17": 5, "20": 3, "22": 2},
        "current_levels": {"17": 4, "20": 2, "22": 1},
        "available_stamps": {
            "17": [DUMMY_STAMP, "b" * 64],
            "20": ["c" * 64],
            "22": [],
        },
        "total_stamps": 7,
        "low_reserve_warning": False,
        "last_check": "2024-01-15T10:00:00Z",
        "next_check": "2024-01-15T11:00:00Z",
        "errors": [],
    }

    SAMPLE_ACQUIRE_RESPONSE = {
        "success": True,
        "batch_id": DUMMY_STAMP,
        "depth": 17,
        "size_name": "small",
        "message": "Stamp acquired successfully",
        "fallback_used": False,
    }

    SAMPLE_HEALTH_CHECK = {
        "stamp_id": DUMMY_STAMP,
        "can_upload": True,
        "errors": [],
        "warnings": [
            {
                "code": "LOW_TTL",
                "message": "TTL is below 24 hours",
                "details": {"ttl_hours": 12},
            }
        ],
        "status": {"ttl": 43200, "depth": 17, "utilization": 25},
    }

    def test_get_pool_status_success(self, requests_mock):
        """Tests getting pool status."""
        requests_mock.get(
            "https://test.gateway.io/api/v1/pool/status",
            json=self.SAMPLE_POOL_STATUS,
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        status = client.get_pool_status()

        assert status.enabled is True
        assert status.total_stamps == 7
        assert status.low_reserve_warning is False
        assert len(status.available_stamps["17"]) == 2
        assert status.reserve_config["17"] == 5

    def test_get_pool_status_disabled(self, requests_mock):
        """Tests getting pool status when pool is disabled."""
        from swarm_provenance_uploader.exceptions import PoolNotEnabledError

        requests_mock.get(
            "https://test.gateway.io/api/v1/pool/status",
            status_code=404,
            json={"error": "Pool not enabled"},
        )

        client = GatewayClient(base_url="https://test.gateway.io")

        with pytest.raises(PoolNotEnabledError):
            client.get_pool_status()

    def test_get_pool_available_count_by_size(self, requests_mock):
        """Tests getting available stamp count by size."""
        requests_mock.get(
            "https://test.gateway.io/api/v1/pool/status",
            json=self.SAMPLE_POOL_STATUS,
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        count = client.get_pool_available_count(size="small")

        assert count == 2  # From SAMPLE_POOL_STATUS available_stamps["17"]

    def test_get_pool_available_count_by_depth(self, requests_mock):
        """Tests getting available stamp count by depth."""
        requests_mock.get(
            "https://test.gateway.io/api/v1/pool/status",
            json=self.SAMPLE_POOL_STATUS,
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        count = client.get_pool_available_count(depth=20)

        assert count == 1  # From SAMPLE_POOL_STATUS available_stamps["20"]

    def test_get_pool_available_count_default(self, requests_mock):
        """Tests getting available stamp count with default size."""
        requests_mock.get(
            "https://test.gateway.io/api/v1/pool/status",
            json=self.SAMPLE_POOL_STATUS,
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        count = client.get_pool_available_count()

        assert count == 2  # Defaults to small (depth 17)

    def test_acquire_stamp_from_pool_success(self, requests_mock):
        """Tests acquiring stamp from pool."""
        requests_mock.post(
            "https://test.gateway.io/api/v1/pool/acquire",
            json=self.SAMPLE_ACQUIRE_RESPONSE,
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.acquire_stamp_from_pool(size="small")

        assert result.success is True
        assert result.batch_id == DUMMY_STAMP
        assert result.depth == 17
        assert result.size_name == "small"
        assert result.fallback_used is False

    def test_acquire_stamp_from_pool_with_fallback(self, requests_mock):
        """Tests acquiring stamp from pool with fallback."""
        fallback_response = {
            "success": True,
            "batch_id": DUMMY_STAMP,
            "depth": 20,
            "size_name": "medium",
            "message": "Larger stamp substituted",
            "fallback_used": True,
        }
        requests_mock.post(
            "https://test.gateway.io/api/v1/pool/acquire",
            json=fallback_response,
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.acquire_stamp_from_pool(size="small")

        assert result.success is True
        assert result.fallback_used is True
        assert result.size_name == "medium"

    def test_acquire_stamp_acquisition_fails(self, requests_mock):
        """Tests handling acquisition failure."""
        from swarm_provenance_uploader.exceptions import PoolAcquisitionError

        # Acquisition fails
        requests_mock.post(
            "https://test.gateway.io/api/v1/pool/acquire",
            json={
                "success": False,
                "batch_id": None,
                "message": "No stamps available",
                "fallback_used": False,
            },
        )

        client = GatewayClient(base_url="https://test.gateway.io")

        with pytest.raises(PoolAcquisitionError):
            client.acquire_stamp_from_pool(size="small")

    def test_list_pool_stamps(self, requests_mock):
        """Tests listing stamps in the pool."""
        stamps_response = {
            "stamps": [
                {
                    "batch_id": DUMMY_STAMP,
                    "depth": 17,
                    "size_name": "small",
                    "created_at": "2024-01-15T08:00:00Z",
                    "ttl_at_creation": 86400,
                },
                {
                    "batch_id": "b" * 64,
                    "depth": 20,
                    "size_name": "medium",
                    "created_at": "2024-01-15T09:00:00Z",
                    "ttl_at_creation": 172800,
                },
            ],
            "count": 2,
        }
        requests_mock.get(
            "https://test.gateway.io/api/v1/pool/stamps",
            json=stamps_response,
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        stamps = client.list_pool_stamps()

        assert len(stamps) == 2
        assert stamps[0].batch_id == DUMMY_STAMP
        assert stamps[0].depth == 17
        assert stamps[1].size_name == "medium"

    def test_check_stamp_health_success(self, requests_mock):
        """Tests stamp health check."""
        requests_mock.get(
            f"https://test.gateway.io/api/v1/stamps/{DUMMY_STAMP}/check",
            json=self.SAMPLE_HEALTH_CHECK,
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        health = client.check_stamp_health(DUMMY_STAMP)

        assert health.stamp_id == DUMMY_STAMP
        assert health.can_upload is True
        assert len(health.errors) == 0
        assert len(health.warnings) == 1
        assert health.warnings[0].code == "LOW_TTL"

    def test_check_stamp_health_not_usable(self, requests_mock):
        """Tests stamp health check when stamp is not usable."""
        unhealthy_response = {
            "stamp_id": DUMMY_STAMP,
            "can_upload": False,
            "errors": [
                {
                    "code": "EXPIRED",
                    "message": "Stamp has expired",
                    "details": {"expired_at": "2024-01-10T00:00:00Z"},
                }
            ],
            "warnings": [],
            "status": None,
        }
        requests_mock.get(
            f"https://test.gateway.io/api/v1/stamps/{DUMMY_STAMP}/check",
            json=unhealthy_response,
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        health = client.check_stamp_health(DUMMY_STAMP)

        assert health.can_upload is False
        assert len(health.errors) == 1
        assert health.errors[0].code == "EXPIRED"

    def test_check_stamp_health_not_found(self, requests_mock):
        """Tests stamp health check when stamp not found."""
        from swarm_provenance_uploader.exceptions import StampNotFoundError

        requests_mock.get(
            f"https://test.gateway.io/api/v1/stamps/{DUMMY_STAMP}/check",
            status_code=404,
            json={"error": "Stamp not found"},
        )

        client = GatewayClient(base_url="https://test.gateway.io")

        with pytest.raises(StampNotFoundError):
            client.check_stamp_health(DUMMY_STAMP)


class TestGatewayClientNotary:
    """Tests for notary signing functionality."""

    def test_get_notary_info_enabled(self, requests_mock):
        """Tests getting notary info when enabled."""
        notary_response = {
            "enabled": True,
            "available": True,
            "address": "0x54e5e8477D2352dFBCab55B0306bA77038074670",
            "message": "Notary signing is available. Use sign=notary on upload.",
        }
        requests_mock.get(
            "https://test.gateway.io/api/v1/notary/info",
            json=notary_response,
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        info = client.get_notary_info()

        assert info.enabled is True
        assert info.available is True
        assert info.address == "0x54e5e8477D2352dFBCab55B0306bA77038074670"
        assert "sign=notary" in info.message

    def test_get_notary_info_disabled(self, requests_mock):
        """Tests getting notary info when disabled (404)."""
        from swarm_provenance_uploader.exceptions import NotaryNotEnabledError

        requests_mock.get(
            "https://test.gateway.io/api/v1/notary/info",
            status_code=404,
            json={"error": "Not found"},
        )

        client = GatewayClient(base_url="https://test.gateway.io")

        with pytest.raises(NotaryNotEnabledError):
            client.get_notary_info()

    def test_get_notary_info_not_configured(self, requests_mock):
        """Tests getting notary info when enabled but not configured."""
        notary_response = {
            "enabled": True,
            "available": False,
            "address": None,
            "message": "Notary is enabled but private key is not configured.",
        }
        requests_mock.get(
            "https://test.gateway.io/api/v1/notary/info",
            json=notary_response,
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        info = client.get_notary_info()

        assert info.enabled is True
        assert info.available is False
        assert info.address is None

    def test_get_notary_status(self, requests_mock):
        """Tests getting notary status."""
        status_response = {
            "enabled": True,
            "available": True,
            "address": "0x54e5e8477D2352dFBCab55B0306bA77038074670",
        }
        requests_mock.get(
            "https://test.gateway.io/api/v1/notary/status",
            json=status_response,
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        status = client.get_notary_status()

        assert status.enabled is True
        assert status.available is True

    def test_upload_with_signing(self, requests_mock):
        """Tests upload with sign=notary parameter."""
        upload_response = {
            "reference": DUMMY_SWARM_REF,
            "signed_document": {
                "data": "dGVzdCBkYXRh",
                "signatures": [
                    {
                        "type": "notary",
                        "signer": "0x54e5e8477D2352dFBCab55B0306bA77038074670",
                        "timestamp": "2026-01-21T16:30:00+00:00",
                        "data_hash": "abc123",
                        "signature": "0x" + "a" * 130,
                        "hashed_fields": ["data"],
                        "signed_message_format": "{data_hash}|{timestamp}",
                    }
                ],
            },
            "message": "Upload successful with notary signature",
        }
        requests_mock.post(
            "https://test.gateway.io/api/v1/data/",
            json=upload_response,
        )

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.upload_data_with_signing(b'{"data": "test"}', DUMMY_STAMP)

        assert result.reference == DUMMY_SWARM_REF
        assert result.signed_document is not None
        assert len(result.signed_document["signatures"]) == 1
        assert result.signed_document["signatures"][0]["type"] == "notary"

    def test_upload_with_signing_notary_not_enabled(self, requests_mock):
        """Tests upload when notary not enabled."""
        from swarm_provenance_uploader.exceptions import NotaryNotEnabledError

        requests_mock.post(
            "https://test.gateway.io/api/v1/data/",
            status_code=400,
            json={"code": "NOTARY_NOT_ENABLED", "detail": "Notary signing is not enabled"},
        )

        client = GatewayClient(base_url="https://test.gateway.io")

        with pytest.raises(NotaryNotEnabledError):
            client.upload_data_with_signing(b'{"data": "test"}', DUMMY_STAMP)

    def test_upload_with_signing_notary_not_configured(self, requests_mock):
        """Tests upload when notary not configured."""
        from swarm_provenance_uploader.exceptions import NotaryNotConfiguredError

        requests_mock.post(
            "https://test.gateway.io/api/v1/data/",
            status_code=400,
            json={"code": "NOTARY_NOT_CONFIGURED", "detail": "Missing private key"},
        )

        client = GatewayClient(base_url="https://test.gateway.io")

        with pytest.raises(NotaryNotConfiguredError):
            client.upload_data_with_signing(b'{"data": "test"}', DUMMY_STAMP)

    def test_upload_with_signing_invalid_document(self, requests_mock):
        """Tests upload with invalid document format."""
        from swarm_provenance_uploader.exceptions import InvalidDocumentFormatError

        requests_mock.post(
            "https://test.gateway.io/api/v1/data/",
            status_code=400,
            json={"code": "INVALID_DOCUMENT_FORMAT", "detail": "Missing 'data' field"},
        )

        client = GatewayClient(base_url="https://test.gateway.io")

        with pytest.raises(InvalidDocumentFormatError):
            client.upload_data_with_signing(b'{"invalid": "document"}', DUMMY_STAMP)


class TestGatewayClientManifest:
    """Tests for manifest/collection upload."""

    def test_upload_manifest_success(self, requests_mock, tmp_path):
        """Tests successful manifest upload."""
        requests_mock.post(
            "https://test.gateway.io/api/v1/data/manifest",
            json={
                "reference": DUMMY_SWARM_REF,
                "file_count": 3,
                "message": "Manifest uploaded successfully",
            },
        )

        # Create a small tar file
        import tarfile
        tar_path = tmp_path / "test.tar"
        file1 = tmp_path / "file1.txt"
        file1.write_text("hello")
        with tarfile.open(tar_path, "w") as tar:
            tar.add(str(file1), arcname="file1.txt")

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.upload_manifest(str(tar_path), DUMMY_STAMP)

        assert result.reference == DUMMY_SWARM_REF
        assert result.file_count == 3
        assert result.message == "Manifest uploaded successfully"

    def test_upload_manifest_with_timing(self, requests_mock, tmp_path):
        """Tests manifest upload with timing info."""
        requests_mock.post(
            "https://test.gateway.io/api/v1/data/manifest",
            json={
                "reference": DUMMY_SWARM_REF,
                "file_count": 2,
                "timing": {
                    "stamp_check_ms": 50,
                    "upload_ms": 1200,
                    "total_ms": 1250,
                },
            },
        )

        import tarfile
        tar_path = tmp_path / "test.tar"
        file1 = tmp_path / "f.txt"
        file1.write_text("data")
        with tarfile.open(tar_path, "w") as tar:
            tar.add(str(file1), arcname="f.txt")

        client = GatewayClient(base_url="https://test.gateway.io")
        result = client.upload_manifest(str(tar_path), DUMMY_STAMP, include_timing=True)

        assert result.reference == DUMMY_SWARM_REF
        assert result.timing is not None
        assert result.timing.total_ms == 1250
        assert result.timing.upload_ms == 1200

    def test_upload_manifest_invalid_stamp(self, requests_mock, tmp_path):
        """Tests manifest upload with invalid stamp returns error."""
        requests_mock.post(
            "https://test.gateway.io/api/v1/data/manifest",
            status_code=400,
            json={"detail": "Invalid stamp"},
        )

        import tarfile
        tar_path = tmp_path / "test.tar"
        file1 = tmp_path / "f.txt"
        file1.write_text("data")
        with tarfile.open(tar_path, "w") as tar:
            tar.add(str(file1), arcname="f.txt")

        client = GatewayClient(base_url="https://test.gateway.io")
        with pytest.raises(Exception):
            client.upload_manifest(str(tar_path), "bad_stamp")

    def test_upload_manifest_server_error(self, requests_mock, tmp_path):
        """Tests manifest upload handles 500 error."""
        requests_mock.post(
            "https://test.gateway.io/api/v1/data/manifest",
            status_code=500,
            json={"detail": "Internal server error"},
        )

        import tarfile
        tar_path = tmp_path / "test.tar"
        file1 = tmp_path / "f.txt"
        file1.write_text("data")
        with tarfile.open(tar_path, "w") as tar:
            tar.add(str(file1), arcname="f.txt")

        client = GatewayClient(base_url="https://test.gateway.io")
        with pytest.raises(Exception):
            client.upload_manifest(str(tar_path), DUMMY_STAMP)

    def test_upload_manifest_deferred_param(self, requests_mock, tmp_path):
        """Tests that deferred=True is sent as query parameter."""
        mock = requests_mock.post(
            "https://test.gateway.io/api/v1/data/manifest",
            json={"reference": DUMMY_SWARM_REF},
        )

        import tarfile
        tar_path = tmp_path / "test.tar"
        file1 = tmp_path / "f.txt"
        file1.write_text("data")
        with tarfile.open(tar_path, "w") as tar:
            tar.add(str(file1), arcname="f.txt")

        client = GatewayClient(base_url="https://test.gateway.io")
        client.upload_manifest(str(tar_path), DUMMY_STAMP, deferred=True)

        assert mock.called
        assert "deferred=true" in mock.last_request.url.lower()

    def test_upload_manifest_redundancy_param(self, requests_mock, tmp_path):
        """Tests that redundancy=True is sent as query parameter."""
        mock = requests_mock.post(
            "https://test.gateway.io/api/v1/data/manifest",
            json={"reference": DUMMY_SWARM_REF},
        )

        import tarfile
        tar_path = tmp_path / "test.tar"
        file1 = tmp_path / "f.txt"
        file1.write_text("data")
        with tarfile.open(tar_path, "w") as tar:
            tar.add(str(file1), arcname="f.txt")

        client = GatewayClient(base_url="https://test.gateway.io")
        client.upload_manifest(str(tar_path), DUMMY_STAMP, redundancy=True)

        assert mock.called
        assert "redundancy=true" in mock.last_request.url.lower()

    def test_upload_manifest_deferred_and_redundancy(self, requests_mock, tmp_path):
        """Tests both deferred and redundancy params sent together."""
        mock = requests_mock.post(
            "https://test.gateway.io/api/v1/data/manifest",
            json={"reference": DUMMY_SWARM_REF},
        )

        import tarfile
        tar_path = tmp_path / "test.tar"
        file1 = tmp_path / "f.txt"
        file1.write_text("data")
        with tarfile.open(tar_path, "w") as tar:
            tar.add(str(file1), arcname="f.txt")

        client = GatewayClient(base_url="https://test.gateway.io")
        client.upload_manifest(
            str(tar_path), DUMMY_STAMP, deferred=True, redundancy=True
        )

        assert mock.called
        url = mock.last_request.url.lower()
        assert "deferred=true" in url
        assert "redundancy=true" in url


class TestGatewayClientFreeTier:
    """Tests for free tier header functionality."""

    def test_free_tier_constructor(self):
        """Tests that free_tier parameter is stored correctly."""
        client = GatewayClient(base_url="https://test.gateway.io", free_tier=True)
        assert client.free_tier is True

        client2 = GatewayClient(base_url="https://test.gateway.io", free_tier=False)
        assert client2.free_tier is False

    def test_free_tier_disabled_by_default(self):
        """Tests that free_tier is disabled by default."""
        client = GatewayClient(base_url="https://test.gateway.io")
        assert client.free_tier is False

    def test_free_tier_header_in_get_headers(self):
        """Tests that free_tier=True adds X-Payment-Mode: free header."""
        client = GatewayClient(base_url="https://test.gateway.io", free_tier=True)
        headers = client._get_headers()
        assert headers.get("X-Payment-Mode") == "free"

    def test_free_tier_header_not_set_by_default(self):
        """Tests that free_tier=False does not add X-Payment-Mode header."""
        client = GatewayClient(base_url="https://test.gateway.io", free_tier=False)
        headers = client._get_headers()
        assert "X-Payment-Mode" not in headers

    def test_free_tier_header_in_upload_data(self, requests_mock):
        """Tests that free tier header is sent in upload_data requests."""
        adapter = requests_mock.post(
            "https://test.gateway.io/api/v1/data/",
            json={"reference": DUMMY_SWARM_REF},
        )

        client = GatewayClient(base_url="https://test.gateway.io", free_tier=True)
        client.upload_data(data=b"test data", stamp_id=DUMMY_STAMP)

        assert adapter.last_request.headers.get("X-Payment-Mode") == "free"

    def test_free_tier_header_not_in_upload_when_disabled(self, requests_mock):
        """Tests that free tier header is NOT sent when disabled."""
        adapter = requests_mock.post(
            "https://test.gateway.io/api/v1/data/",
            json={"reference": DUMMY_SWARM_REF},
        )

        client = GatewayClient(base_url="https://test.gateway.io", free_tier=False)
        client.upload_data(data=b"test data", stamp_id=DUMMY_STAMP)

        assert "X-Payment-Mode" not in adapter.last_request.headers


# --- Payment outcome after a sent X-PAYMENT (#127) ---

PAYER = "0x742d35Cc6634C0532925a3b844Bc9e7595f8fE00"
PAY_TO = "0x1234567890AbcdEF1234567890aBcDeF12345678"
NONCE = "0x" + "ab" * 32
TX_HASH = "0x" + "cd" * 32
GW = "https://test.gateway.io"


def _signed_header():
    """An X-PAYMENT header shaped like X402Client.sign_payment's output."""
    import base64
    import json

    payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "base-sepolia",
        "payload": {
            "signature": "0x" + "ee" * 65,
            "authorization": {
                "from": PAYER, "to": PAY_TO, "value": "50000",
                "validAfter": "0", "validBefore": "9999999999", "nonce": NONCE,
            },
        },
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


@pytest.fixture
def paying_client():
    """A GatewayClient that answers every 402 with a signed payment, no prompt."""
    from unittest.mock import patch

    client = GatewayClient(base_url=GW, x402_enabled=True, x402_auto_pay=True)
    with patch.object(client, "_handle_402_response", return_value=(_signed_header(), "$0.050000")):
        yield client


PAYMENT_REQUIRED = {"status_code": 402, "json": {"accepts": []}}


class TestPaidRequestOutcome:
    """Failures after the payment was sent must not look like plain failures."""

    def _assert_identifies_payment(self, err):
        assert err.payer == PAYER
        assert err.nonce == NONCE
        assert err.amount == "50000"
        assert err.amount_usd == "$0.050000"
        assert err.pay_to == PAY_TO
        assert err.network == "base-sepolia"

    def test_read_timeout_after_payment_is_outcome_unknown(self, paying_client, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentOutcomeUnknownError

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"exc": requests.exceptions.ReadTimeout}])
        with pytest.raises(PaymentOutcomeUnknownError) as exc_info:
            paying_client.purchase_stamp()
        assert not exc_info.value.settled
        assert "may have been taken" in str(exc_info.value)
        self._assert_identifies_payment(exc_info.value)

    def test_dropped_connection_after_payment_is_outcome_unknown(self, paying_client, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentOutcomeUnknownError

        requests_mock.post(f"{GW}/api/v1/data/", [PAYMENT_REQUIRED, {"exc": requests.exceptions.ConnectionError}])
        with pytest.raises(PaymentOutcomeUnknownError):
            paying_client.upload_data(b"x", DUMMY_STAMP)

    def test_connect_timeout_after_payment_is_plain_failure(self, paying_client, requests_mock):
        """Never connected, so the payment was never sent: not an unknown outcome."""
        from swarm_provenance_uploader.exceptions import PaymentOutcomeUnknownError

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"exc": requests.exceptions.ConnectTimeout}])
        with pytest.raises(ConnectionError) as exc_info:
            paying_client.purchase_stamp()
        assert not isinstance(exc_info.value, PaymentOutcomeUnknownError)

    @pytest.mark.parametrize("status", [500, 502, 504])
    def test_5xx_after_payment_is_outcome_unknown(self, paying_client, requests_mock, status):
        from swarm_provenance_uploader.exceptions import PaymentOutcomeUnknownError

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"status_code": status, "text": "Bad gateway"}])
        with pytest.raises(PaymentOutcomeUnknownError) as exc_info:
            paying_client.purchase_stamp()
        assert exc_info.value.status_code == status
        self._assert_identifies_payment(exc_info.value)

    def test_delivery_failed_after_payment_is_settled(self, paying_client, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentSettledNotDeliveredError

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {
            "status_code": 500,
            "json": {"code": "DELIVERY_FAILED_AFTER_PAYMENT", "message": "Contact the operator.",
                     "transaction": TX_HASH, "x402_status": "settled_not_delivered"},
            "headers": {"X-Payment-Transaction": TX_HASH, "X-Payment-Status": "settled_not_delivered"},
        }])
        with pytest.raises(PaymentSettledNotDeliveredError) as exc_info:
            paying_client.purchase_stamp()
        err = exc_info.value
        assert err.settled
        assert err.transaction == TX_HASH
        assert err.code == "DELIVERY_FAILED_AFTER_PAYMENT"
        assert "Contact the operator." in str(err)
        self._assert_identifies_payment(err)

    def test_settled_not_delivered_header_on_4xx_is_settled(self, paying_client, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentSettledNotDeliveredError

        requests_mock.post(f"{GW}/api/v1/data/", [PAYMENT_REQUIRED, {
            "status_code": 400, "json": {"detail": "Stamp not usable"},
            "headers": {"X-Payment-Transaction": TX_HASH, "X-Payment-Status": "settled_not_delivered"},
        }])
        with pytest.raises(PaymentSettledNotDeliveredError) as exc_info:
            paying_client.upload_data(b"x", DUMMY_STAMP)
        assert exc_info.value.transaction == TX_HASH

    def test_402_after_payment_is_rejected(self, paying_client, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentRejectedError

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {
            "status_code": 402,
            "json": {"code": "PAYMENT_SETTLEMENT_FAILED", "message": "The payment could not be settled (insufficient_funds)."},
        }])
        with pytest.raises(PaymentRejectedError, match="insufficient_funds"):
            paying_client.purchase_stamp()

    def test_4xx_before_settlement_is_plain_failure(self, paying_client, requests_mock):
        """The gateway refused before collecting: an ordinary error."""
        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"status_code": 400, "json": {"detail": "bad depth"}}])
        with pytest.raises(ConnectionError, match="Failed to purchase stamp"):
            paying_client.purchase_stamp()

    def test_unknown_transaction_placeholder_dropped(self, paying_client, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentSettledNotDeliveredError

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {
            "status_code": 500, "json": {"code": "DELIVERY_FAILED_AFTER_PAYMENT"},
            "headers": {"X-Payment-Transaction": "unknown"},
        }])
        with pytest.raises(PaymentSettledNotDeliveredError) as exc_info:
            paying_client.purchase_stamp()
        assert exc_info.value.transaction is None

    def test_success_after_payment_returns_result(self, paying_client, requests_mock):
        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {
            "status_code": 201, "json": {"batchID": DUMMY_STAMP}, "headers": {"X-Payment-Transaction": TX_HASH},
        }])
        assert paying_client.purchase_stamp() == DUMMY_STAMP

    def test_unpaid_5xx_stays_plain_failure(self, requests_mock):
        """No payment was sent, so a server error is just a server error."""
        requests_mock.post(f"{GW}/api/v1/stamps/", status_code=500)
        client = GatewayClient(base_url=GW)
        with pytest.raises(ConnectionError, match="Failed to purchase stamp"):
            client.purchase_stamp()


class TestPurchasePending:
    """202 PURCHASE_PENDING: paid, batch not confirmed yet."""

    PENDING = {
        "code": "PURCHASE_PENDING",
        "message": "Payment received, but the Bee node did not confirm the purchase in time.",
        "transaction": TX_HASH,
        "label": "x402-abc123",
        "depth": 17,
        "amount": "1000000000",
        "lookup": f"GET /api/v1/stamps/?wallet={PAYER} and look for this label.",
    }

    def test_202_raises_pending_without_validation_error(self, paying_client, requests_mock):
        from swarm_provenance_uploader.exceptions import StampPurchasePendingError

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"status_code": 202, "json": self.PENDING}])
        with pytest.raises(StampPurchasePendingError) as exc_info:
            paying_client.purchase_stamp()
        err = exc_info.value
        assert err.settled
        assert err.transaction == TX_HASH
        assert err.label == "x402-abc123"
        assert err.depth == 17
        assert "wallet=" in err.lookup
        assert err.nonce == NONCE
        assert err.amount == "50000"  # the USDC payment, not the BZZ batch amount


class TestPaidRequestTimeouts:
    """Paid calls must wait longer than the gateway's own post-settlement work."""

    def test_paid_timeout_outlasts_gateway_work(self):
        connect, read = GatewayClient.PAID_REQUEST_TIMEOUT
        assert read >= 180
        assert connect <= 30  # an unreachable gateway was never paid; fail fast

    def _assert_paid_timeout(self, requests_mock):
        assert requests_mock.call_count >= 1
        for request in requests_mock.request_history:
            assert request.timeout == GatewayClient.PAID_REQUEST_TIMEOUT

    def test_purchase_timeout(self, requests_mock):
        requests_mock.post(f"{GW}/api/v1/stamps/", status_code=201, json={"batchID": DUMMY_STAMP})
        GatewayClient(base_url=GW).purchase_stamp()
        self._assert_paid_timeout(requests_mock)

    def test_upload_timeout(self, requests_mock):
        requests_mock.post(f"{GW}/api/v1/data/", json={"reference": DUMMY_SWARM_REF})
        GatewayClient(base_url=GW).upload_data(b"x", DUMMY_STAMP)
        self._assert_paid_timeout(requests_mock)

    def test_signed_upload_timeout(self, requests_mock):
        requests_mock.post(f"{GW}/api/v1/data/", json={"reference": DUMMY_SWARM_REF})
        GatewayClient(base_url=GW).upload_data_with_signing(b"{}", DUMMY_STAMP)
        self._assert_paid_timeout(requests_mock)

    def test_pool_acquire_timeout(self, requests_mock):
        requests_mock.post(f"{GW}/api/v1/pool/acquire", json={
            "success": True, "batch_id": DUMMY_STAMP, "depth": 17, "size_name": "small",
            "message": "ok", "fallback_used": False,
        })
        GatewayClient(base_url=GW).acquire_stamp_from_pool()
        self._assert_paid_timeout(requests_mock)

    def test_manifest_timeout(self, requests_mock, tmp_path):
        tar = tmp_path / "c.tar"
        tar.write_bytes(b"tar")
        requests_mock.post(f"{GW}/api/v1/data/manifest", json={"reference": DUMMY_SWARM_REF})
        GatewayClient(base_url=GW).upload_manifest(str(tar), DUMMY_STAMP)
        self._assert_paid_timeout(requests_mock)


# --- Hard auto-pay cap and confirmation (#128) ---

def _option(amount="50000", network="base-sepolia"):
    from swarm_provenance_uploader.models import X402PaymentOption

    return X402PaymentOption(
        scheme="exact", network=network, maxAmountRequired=amount, resource="/api/v1/stamps/",
        description="Stamp purchase", payTo=PAY_TO,
        asset="0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    )


@pytest.fixture
def mock_x402():
    """A stand-in X402Client offering one option; signing is recorded, never real."""
    from unittest.mock import MagicMock

    x402 = MagicMock()
    x402.parse_402_response.return_value = MagicMock()
    x402.select_payment_option.return_value = _option()
    x402.format_amount_usd.side_effect = lambda a: f"${int(a) // 1_000_000}.{int(a) % 1_000_000:06d}"
    x402.sign_payment.return_value = _signed_header()
    return x402


def _client_with(mock_x402, **kwargs):
    from unittest.mock import patch

    client = GatewayClient(base_url=GW, x402_enabled=True, **kwargs)
    patcher = patch.object(client, "_get_x402_client", return_value=mock_x402)
    patcher.start()
    return client, patcher


class TestAutoPayHardCap:
    def test_above_cap_without_callback_refuses_before_signing(self, mock_x402, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentRequiredError

        mock_x402.select_payment_option.return_value = _option(amount="5000000")  # $5
        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"status_code": 201, "json": {"batchID": DUMMY_STAMP}}])
        client, patcher = _client_with(mock_x402, x402_auto_pay=True, x402_max_auto_pay_usd=1.00)
        try:
            with pytest.raises(PaymentRequiredError, match="exceeds the auto-pay limit"):
                client.purchase_stamp()
        finally:
            patcher.stop()
        mock_x402.sign_payment.assert_not_called()
        assert requests_mock.call_count == 1  # never retried with a payment

    def test_just_above_cap_refused(self, mock_x402, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentRequiredError

        mock_x402.select_payment_option.return_value = _option(amount="1000001")  # $1.000001
        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED])
        client, patcher = _client_with(mock_x402, x402_auto_pay=True, x402_max_auto_pay_usd=1.00)
        try:
            with pytest.raises(PaymentRequiredError):
                client.purchase_stamp()
        finally:
            patcher.stop()
        mock_x402.sign_payment.assert_not_called()

    def test_at_cap_auto_pays(self, mock_x402, requests_mock):
        mock_x402.select_payment_option.return_value = _option(amount="1000000")  # exactly $1
        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"status_code": 201, "json": {"batchID": DUMMY_STAMP}}])
        client, patcher = _client_with(mock_x402, x402_auto_pay=True, x402_max_auto_pay_usd=1.00)
        try:
            assert client.purchase_stamp() == DUMMY_STAMP
        finally:
            patcher.stop()
        mock_x402.sign_payment.assert_called_once()

    def test_above_cap_with_callback_asks(self, mock_x402, requests_mock):
        from unittest.mock import MagicMock

        mock_x402.select_payment_option.return_value = _option(amount="5000000")
        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"status_code": 201, "json": {"batchID": DUMMY_STAMP}}])
        callback = MagicMock(return_value=True)
        client, patcher = _client_with(mock_x402, x402_auto_pay=True, x402_max_auto_pay_usd=1.00,
                                       x402_payment_callback=callback)
        try:
            assert client.purchase_stamp() == DUMMY_STAMP
        finally:
            patcher.stop()
        callback.assert_called_once()


class TestPaymentCallbackOption:
    def test_two_argument_callback_still_supported(self, mock_x402, requests_mock):
        calls = []

        def legacy(amount_usd, description):
            calls.append((amount_usd, description))
            return True

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"status_code": 201, "json": {"batchID": DUMMY_STAMP}}])
        client, patcher = _client_with(mock_x402, x402_payment_callback=legacy)
        try:
            client.purchase_stamp()
        finally:
            patcher.stop()
        assert calls == [("$0.050000", 'POST /api/v1/stamps/ (gateway says: "Stamp purchase")')]

    def test_callback_accepting_option_receives_it(self, mock_x402, requests_mock):
        seen = {}

        def confirm(amount_usd, description, option=None):
            seen["option"] = option
            return True

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"status_code": 201, "json": {"batchID": DUMMY_STAMP}}])
        client, patcher = _client_with(mock_x402, x402_payment_callback=confirm)
        try:
            client.purchase_stamp()
        finally:
            patcher.stop()
        assert seen["option"].payTo == PAY_TO
        assert seen["option"].network == "base-sepolia"


class TestPaymentSentHook:
    def test_hook_called_for_sent_payment(self, mock_x402, requests_mock):
        sent = []
        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {
            "status_code": 201, "json": {"batchID": DUMMY_STAMP}, "headers": {"X-Payment-Transaction": TX_HASH},
        }])
        client, patcher = _client_with(mock_x402, x402_auto_pay=True, x402_on_payment_sent=sent.append)
        try:
            client.purchase_stamp()
        finally:
            patcher.stop()
        assert len(sent) == 1
        assert sent[0]["amount"] == "50000"
        assert sent[0]["transaction"] == TX_HASH

    def test_hook_called_when_outcome_unknown(self, mock_x402, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentOutcomeUnknownError

        sent = []
        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"exc": requests.exceptions.ReadTimeout}])
        client, patcher = _client_with(mock_x402, x402_auto_pay=True, x402_on_payment_sent=sent.append)
        try:
            with pytest.raises(PaymentOutcomeUnknownError):
                client.purchase_stamp()
        finally:
            patcher.stop()
        assert len(sent) == 1

    def test_hook_not_called_when_payment_rejected(self, mock_x402, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentRejectedError

        sent = []
        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, PAYMENT_REQUIRED])
        client, patcher = _client_with(mock_x402, x402_auto_pay=True, x402_on_payment_sent=sent.append)
        try:
            with pytest.raises(PaymentRejectedError):
                client.purchase_stamp()
        finally:
            patcher.stop()
        assert sent == []

    def test_failing_hook_does_not_break_request(self, mock_x402, requests_mock):
        def boom(payment):
            raise RuntimeError("hook bug")

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"status_code": 201, "json": {"batchID": DUMMY_STAMP}}])
        client, patcher = _client_with(mock_x402, x402_auto_pay=True, x402_on_payment_sent=boom)
        try:
            assert client.purchase_stamp() == DUMMY_STAMP
        finally:
            patcher.stop()


# --- Payment request presentation and transport (#129) ---

class TestInsecureGatewayWarning:
    @pytest.mark.parametrize("url", ["http://gateway.example.com", "http://10.0.0.5:8000"])
    def test_plain_http_with_x402_warns(self, url):
        from swarm_provenance_uploader.exceptions import InsecureGatewayWarning

        with pytest.warns(InsecureGatewayWarning):
            GatewayClient(base_url=url, x402_enabled=True)

    @pytest.mark.parametrize("url,x402", [
        ("https://gateway.example.com", True),
        ("http://localhost:8000", True),
        ("http://127.0.0.1:8000", True),
        ("http://[::1]:8000", True),
        ("http://gateway.example.com", False),
    ])
    def test_no_warning(self, url, x402):
        import warnings
        from swarm_provenance_uploader.exceptions import InsecureGatewayWarning

        with warnings.catch_warnings():
            warnings.simplefilter("error", InsecureGatewayWarning)
            GatewayClient(base_url=url, x402_enabled=x402)


class TestPaymentDescription:
    def test_leads_with_client_request_and_marks_gateway_text(self, mock_x402, requests_mock):
        seen = []
        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"status_code": 201, "json": {"batchID": DUMMY_STAMP}}])
        client, patcher = _client_with(mock_x402, x402_payment_callback=lambda a, d: seen.append(d) or True)
        try:
            client.purchase_stamp()
        finally:
            patcher.stop()
        assert seen == ['POST /api/v1/stamps/ (gateway says: "Stamp purchase")']

    def test_gateway_text_sanitized_and_truncated(self):
        from swarm_provenance_uploader.models import X402PaymentOption

        option = X402PaymentOption(
            scheme="exact", network="base-sepolia", maxAmountRequired="1", resource="/x",
            payTo=PAY_TO, description="Free!\x1b[2K\rPay now?\n" + "x" * 200,
        )
        described = GatewayClient._describe_request(option)
        assert "\x1b" not in described and "\r" not in described and "\n" not in described
        assert described.startswith("API request to /x")
        assert len(described) < 130

    def test_no_gateway_description(self):
        from swarm_provenance_uploader.models import X402PaymentOption

        option = X402PaymentOption(scheme="exact", network="base-sepolia", maxAmountRequired="1",
                                   resource="/x", payTo=PAY_TO)
        assert GatewayClient._describe_request(option) == "API request to /x"


class TestExpectedPayToPassedThrough:
    def test_expected_pay_to_reaches_x402_client(self):
        from unittest.mock import patch

        client = GatewayClient(base_url=GW, x402_enabled=True, x402_private_key="0x" + "a" * 64,
                               x402_expected_pay_to=PAY_TO)
        with patch("swarm_provenance_uploader.core.x402_client.X402Client") as cls:
            client._get_x402_client()
        assert cls.call_args.kwargs["expected_pay_to"] == PAY_TO


class TestPaidRequestOutcomeReviewCases:
    """Cases from the #127 review: interrupts, unreadable success, not-charged 5xx."""

    def test_keyboard_interrupt_after_payment_is_outcome_unknown(self, paying_client, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentOutcomeUnknownError

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"exc": KeyboardInterrupt}])
        with pytest.raises(PaymentOutcomeUnknownError, match="Interrupted") as exc_info:
            paying_client.purchase_stamp()
        assert exc_info.value.nonce == NONCE

    def test_valid_before_extracted(self, paying_client, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentOutcomeUnknownError

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"exc": requests.exceptions.ReadTimeout}])
        with pytest.raises(PaymentOutcomeUnknownError) as exc_info:
            paying_client.purchase_stamp()
        assert exc_info.value.valid_before == 9999999999

    @pytest.mark.parametrize("body", [{"text": "<html>proxy page</html>"}, {"json": {"unexpected": True}}])
    def test_unreadable_success_after_payment_is_settled(self, paying_client, requests_mock, body):
        from swarm_provenance_uploader.exceptions import PaymentSettledNotDeliveredError

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, dict(status_code=201, **body)])
        with pytest.raises(PaymentSettledNotDeliveredError, match="could not be read") as exc_info:
            paying_client.purchase_stamp()
        assert exc_info.value.nonce == NONCE

    def test_unreadable_success_without_payment_stays_plain(self, requests_mock):
        requests_mock.post(f"{GW}/api/v1/stamps/", status_code=201, text="<html>")
        with pytest.raises(ConnectionError):
            GatewayClient(base_url=GW).purchase_stamp()

    def test_paid_upload_without_reference_is_settled(self, paying_client, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentSettledNotDeliveredError

        requests_mock.post(f"{GW}/api/v1/data/", [PAYMENT_REQUIRED, {"status_code": 200, "json": {"message": "ok"}}])
        with pytest.raises(PaymentSettledNotDeliveredError):
            paying_client.upload_data(b"x", DUMMY_STAMP)

    def test_paid_signed_upload_without_reference_is_settled(self, paying_client, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentSettledNotDeliveredError

        requests_mock.post(f"{GW}/api/v1/data/", [PAYMENT_REQUIRED, {"status_code": 200, "json": {}}])
        with pytest.raises(PaymentSettledNotDeliveredError):
            paying_client.upload_data_with_signing(b"{}", DUMMY_STAMP)

    def test_paid_manifest_without_reference_is_settled(self, paying_client, requests_mock, tmp_path):
        from swarm_provenance_uploader.exceptions import PaymentSettledNotDeliveredError

        tar = tmp_path / "c.tar"
        tar.write_bytes(b"tar")
        requests_mock.post(f"{GW}/api/v1/data/manifest", [PAYMENT_REQUIRED, {"status_code": 200, "json": {}}])
        with pytest.raises(PaymentSettledNotDeliveredError):
            paying_client.upload_manifest(str(tar), DUMMY_STAMP)

    def test_pool_acquire_timeout_after_payment_is_outcome_unknown(self, paying_client, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentOutcomeUnknownError

        requests_mock.post(f"{GW}/api/v1/pool/acquire", [PAYMENT_REQUIRED, {"exc": requests.exceptions.ReadTimeout}])
        with pytest.raises(PaymentOutcomeUnknownError):
            paying_client.acquire_stamp_from_pool()

    @pytest.mark.parametrize("status,body", [
        (503, {"detail": {"code": "PURCHASE_CAPACITY", "message": "You were not charged; retry shortly."}}),
        (500, {"detail": "Internal server error. You were not charged."}),
    ])
    def test_not_charged_5xx_is_plain_failure(self, paying_client, requests_mock, status, body):
        from swarm_provenance_uploader.exceptions import PaymentOutcomeUnknownError

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"status_code": status, "json": body}])
        with pytest.raises(ConnectionError) as exc_info:
            paying_client.purchase_stamp()
        assert not isinstance(exc_info.value, PaymentOutcomeUnknownError)


class TestHardCapReviewCases:
    """Cases from the #128 review."""

    def test_huge_amount_does_not_overflow_and_is_refused(self, mock_x402, requests_mock):
        from swarm_provenance_uploader.exceptions import PaymentRequiredError

        mock_x402.select_payment_option.return_value = _option(amount="9" * 400)
        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED])
        client, patcher = _client_with(mock_x402, x402_auto_pay=True, x402_max_auto_pay_usd=1.00)
        try:
            with pytest.raises(PaymentRequiredError, match="exceeds the auto-pay limit"):
                client.purchase_stamp()
        finally:
            patcher.stop()
        mock_x402.sign_payment.assert_not_called()

    def test_kwargs_callback_not_given_option(self, mock_x402, requests_mock):
        seen = {}

        def forwarding(amount_usd, description, **kwargs):
            seen.update(kwargs)
            return True

        requests_mock.post(f"{GW}/api/v1/stamps/", [PAYMENT_REQUIRED, {"status_code": 201, "json": {"batchID": DUMMY_STAMP}}])
        client, patcher = _client_with(mock_x402, x402_payment_callback=forwarding)
        try:
            client.purchase_stamp()
        finally:
            patcher.stop()
        assert seen == {}


class TestPresentationReviewCases:
    """Cases from the #129 review."""

    def test_description_uses_original_request_not_redirect(self, mock_x402, requests_mock):
        seen = []
        requests_mock.post(f"{GW}/api/v1/stamps/", [
            {"status_code": 307, "headers": {"Location": f"{GW}/api/v1/elsewhere/"}},
            {"status_code": 201, "json": {"batchID": DUMMY_STAMP}},
        ])
        requests_mock.post(f"{GW}/api/v1/elsewhere/", status_code=402, json={"accepts": []})
        client, patcher = _client_with(mock_x402, x402_payment_callback=lambda a, d: seen.append(d) or True)
        try:
            client.purchase_stamp()
        finally:
            patcher.stop()
        assert seen[0].startswith("POST /api/v1/stamps/ ")

    def test_bidi_and_zero_width_characters_stripped(self):
        from swarm_provenance_uploader.core.gateway_client import _sanitize_gateway_text

        cleaned = _sanitize_gateway_text("abc‮evil​X⁦y﻿")
        for ch in "‮​⁦﻿":
            assert ch not in cleaned

    @pytest.mark.parametrize("url", ["http://127.0.0.2:8000", "http://LOCALHOST:8000", "http://[::1]:8000"])
    def test_loopback_variants_not_insecure(self, url):
        from swarm_provenance_uploader.core.gateway_client import is_insecure_gateway_url

        assert not is_insecure_gateway_url(url)

    @pytest.mark.parametrize("url", ["http://localhost.evil.com", "HTTP://gateway.example.com", "http://128.0.0.1"])
    def test_non_loopback_insecure(self, url):
        from swarm_provenance_uploader.core.gateway_client import is_insecure_gateway_url

        assert is_insecure_gateway_url(url)


class TestListStampsWallet:
    def test_wallet_query_param(self, requests_mock):
        requests_mock.get(f"{GW}/api/v1/stamps/", json={"stamps": [], "total_count": 0})
        GatewayClient(base_url=GW).list_stamps(wallet=PAYER)
        assert requests_mock.last_request.qs == {"wallet": [PAYER.lower()]}

    def test_no_wallet_no_param(self, requests_mock):
        requests_mock.get(f"{GW}/api/v1/stamps/", json={"stamps": [], "total_count": 0})
        GatewayClient(base_url=GW).list_stamps()
        assert requests_mock.last_request.qs == {}
