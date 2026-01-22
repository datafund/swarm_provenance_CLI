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
