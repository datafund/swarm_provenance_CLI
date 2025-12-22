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
