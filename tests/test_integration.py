"""Integration tests that hit real backends.

These tests require actual running services:
- Local Bee node at http://localhost:1633
- Gateway at https://provenance-gateway.datafund.io

Run with: pytest tests/test_integration.py -v
Skip with: pytest --ignore=tests/test_integration.py

Tests are marked with:
- @pytest.mark.integration - all integration tests
- @pytest.mark.local_bee - requires local Bee node
- @pytest.mark.gateway - requires gateway service
"""

import pytest
import requests

from swarm_provenance_uploader.core.gateway_client import GatewayClient
from swarm_provenance_uploader.core import swarm_client


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def local_bee_url():
    """Local Bee node URL."""
    return "http://localhost:1633"


@pytest.fixture
def gateway_url():
    """Gateway URL."""
    return "https://provenance-gateway.datafund.io"


@pytest.fixture
def gateway_client(gateway_url):
    """GatewayClient instance."""
    return GatewayClient(base_url=gateway_url)


# =============================================================================
# SKIP CONDITIONS
# =============================================================================

def is_local_bee_available():
    """Check if local Bee node is reachable."""
    try:
        resp = requests.get("http://localhost:1633/", timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def is_gateway_available():
    """Check if gateway is reachable."""
    try:
        resp = requests.get("https://provenance-gateway.datafund.io/", timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False


skip_if_no_local_bee = pytest.mark.skipif(
    not is_local_bee_available(),
    reason="Local Bee node not available at localhost:1633"
)

skip_if_no_gateway = pytest.mark.skipif(
    not is_gateway_available(),
    reason="Gateway not available at provenance-gateway.datafund.io"
)


# =============================================================================
# LOCAL BEE INTEGRATION TESTS
# =============================================================================

@pytest.mark.integration
@pytest.mark.local_bee
class TestLocalBeeIntegration:
    """Integration tests against real local Bee node."""

    @skip_if_no_local_bee
    def test_health_check(self, local_bee_url):
        """Test local Bee health check."""
        resp = requests.get(f"{local_bee_url}/", timeout=5)
        assert resp.status_code == 200

    @skip_if_no_local_bee
    def test_get_stamps(self, local_bee_url):
        """Test listing stamps from local Bee."""
        resp = requests.get(f"{local_bee_url}/stamps", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "stamps" in data

    @skip_if_no_local_bee
    def test_get_wallet(self, local_bee_url):
        """Test getting wallet info from local Bee."""
        resp = requests.get(f"{local_bee_url}/wallet", timeout=10)
        # Wallet endpoint may not exist on all Bee versions
        assert resp.status_code in [200, 404]


# =============================================================================
# GATEWAY INTEGRATION TESTS
# =============================================================================

@pytest.mark.integration
@pytest.mark.gateway
class TestGatewayIntegration:
    """Integration tests against real gateway."""

    @skip_if_no_gateway
    def test_health_check(self, gateway_client):
        """Test gateway health check."""
        result = gateway_client.health_check()
        assert result is True

    @skip_if_no_gateway
    def test_list_stamps(self, gateway_client):
        """Test listing stamps from gateway."""
        try:
            result = gateway_client.list_stamps()
            assert result is not None
            assert hasattr(result, 'stamps')
        except ConnectionError as e:
            # Gateway may have backend issues
            pytest.skip(f"Gateway backend error: {e}")

    @skip_if_no_gateway
    def test_get_wallet(self, gateway_client):
        """Test getting wallet info from gateway."""
        try:
            result = gateway_client.get_wallet()
            assert result is not None
            assert hasattr(result, 'walletAddress')
        except ConnectionError as e:
            pytest.skip(f"Gateway backend error: {e}")

    @skip_if_no_gateway
    def test_get_chequebook(self, gateway_client):
        """Test getting chequebook info from gateway."""
        try:
            result = gateway_client.get_chequebook()
            assert result is not None
            assert hasattr(result, 'chequebookAddress')
        except ConnectionError as e:
            pytest.skip(f"Gateway backend error: {e}")


# =============================================================================
# CROSS-BACKEND COMPARISON TESTS
# =============================================================================

@pytest.mark.integration
class TestCrossBackendComparison:
    """Tests that compare behavior across backends."""

    @skip_if_no_local_bee
    @skip_if_no_gateway
    def test_both_backends_healthy(self, local_bee_url, gateway_client):
        """Verify both backends are reachable."""
        # Local Bee
        local_resp = requests.get(f"{local_bee_url}/", timeout=5)
        assert local_resp.status_code == 200

        # Gateway
        gateway_healthy = gateway_client.health_check()
        assert gateway_healthy is True
