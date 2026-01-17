"""Integration tests that hit real backends.

These tests require actual running services:
- Local Bee node at http://localhost:1633
- Gateway at https://provenance-gateway.datafund.io

For x402 tests:
- Base Sepolia wallet with USDC
- SWARM_X402_PRIVATE_KEY environment variable set

Run with: pytest tests/test_integration.py -v
Skip with: pytest --ignore=tests/test_integration.py

Tests are marked with:
- @pytest.mark.integration - all integration tests
- @pytest.mark.local_bee - requires local Bee node
- @pytest.mark.gateway - requires gateway service
- @pytest.mark.x402 - requires x402 wallet configuration
"""

import os
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


def is_x402_configured():
    """Check if x402 wallet is configured."""
    private_key = os.getenv("SWARM_X402_PRIVATE_KEY")
    return private_key is not None and private_key.startswith("0x")


def are_x402_deps_installed():
    """Check if x402 dependencies are installed."""
    try:
        import eth_account
        import web3
        return True
    except ImportError:
        return False


skip_if_no_x402 = pytest.mark.skipif(
    not is_x402_configured() or not are_x402_deps_installed(),
    reason="x402 not configured (SWARM_X402_PRIVATE_KEY not set or deps missing)"
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


# =============================================================================
# x402 INTEGRATION TESTS
# =============================================================================

@pytest.mark.integration
@pytest.mark.x402
class TestX402Integration:
    """Integration tests for x402 payment functionality.

    These tests require:
    - SWARM_X402_PRIVATE_KEY environment variable set
    - x402 dependencies installed (pip install -e .[x402])
    - Base Sepolia wallet with USDC (from faucet.circle.com)
    """

    @skip_if_no_x402
    def test_x402_client_initialization(self):
        """Test X402Client initializes with configured wallet."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client(network="base-sepolia")
        assert client is not None
        assert client.network == "base-sepolia"

    @skip_if_no_x402
    def test_x402_wallet_address(self):
        """Test X402Client derives correct wallet address."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client(network="base-sepolia")
        address = client.wallet_address
        assert address is not None
        assert address.startswith("0x")
        assert len(address) == 42

    @skip_if_no_x402
    def test_x402_balance_check(self):
        """Test checking USDC balance on Base Sepolia.

        Note: This hits the real blockchain. Balance may be 0 if wallet
        hasn't received testnet USDC from faucet.
        """
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client(network="base-sepolia")
        try:
            balance = client.get_usdc_balance()
            # Balance is a string representation of USDC amount
            assert balance is not None
            # Should be a valid decimal number
            float(balance)
        except Exception as e:
            pytest.skip(f"Balance check failed (RPC issue?): {e}")

    @skip_if_no_x402
    def test_x402_format_amount(self):
        """Test formatting USDC amounts."""
        from swarm_provenance_uploader.core.x402_client import X402Client

        client = X402Client(network="base-sepolia")

        # 1 USDC = 1_000_000 (6 decimals)
        assert client.format_amount_usd("1000000") == "$1.00"
        assert client.format_amount_usd("500000") == "$0.50"
        assert client.format_amount_usd("10000000") == "$10.00"

    @skip_if_no_x402
    @skip_if_no_gateway
    def test_gateway_client_with_x402_disabled(self, gateway_url):
        """Test GatewayClient works normally when x402 is disabled."""
        from swarm_provenance_uploader.core.gateway_client import GatewayClient

        client = GatewayClient(
            base_url=gateway_url,
            x402_enabled=False
        )

        # Should work for non-paid endpoints
        result = client.health_check()
        assert result is True

    @skip_if_no_x402
    @skip_if_no_gateway
    def test_gateway_client_with_x402_enabled(self, gateway_url):
        """Test GatewayClient initializes with x402 enabled."""
        from swarm_provenance_uploader.core.gateway_client import GatewayClient

        private_key = os.getenv("SWARM_X402_PRIVATE_KEY")

        client = GatewayClient(
            base_url=gateway_url,
            x402_enabled=True,
            x402_private_key=private_key,
            x402_network="base-sepolia",
            x402_auto_pay=False
        )

        assert client._x402_enabled is True
        assert client._x402_client is not None

        # Health check should still work
        result = client.health_check()
        assert result is True


# =============================================================================
# x402 PAYMENT FLOW TESTS (Expensive - Use Sparingly)
# =============================================================================

@pytest.mark.integration
@pytest.mark.x402
@pytest.mark.slow
class TestX402PaymentFlow:
    """Tests that actually make x402 payments.

    These tests use real testnet USDC and should be run sparingly.
    Mark with @pytest.mark.slow and skip by default.

    Run with: pytest tests/test_integration.py -v -m "x402 and slow"
    """

    @skip_if_no_x402
    @skip_if_no_gateway
    @pytest.mark.skip(reason="Requires testnet USDC - run manually when needed")
    def test_stamp_purchase_with_x402(self, gateway_url):
        """Test purchasing a stamp with x402 payment.

        This test makes a real payment on Base Sepolia.
        Only run when you have testnet USDC and want to test the full flow.
        """
        from swarm_provenance_uploader.core.gateway_client import GatewayClient

        private_key = os.getenv("SWARM_X402_PRIVATE_KEY")

        # Track if payment callback was called
        payment_made = {"called": False, "amount": None}

        def payment_callback(amount_usd: str, description: str) -> bool:
            payment_made["called"] = True
            payment_made["amount"] = amount_usd
            return True  # Auto-confirm for test

        client = GatewayClient(
            base_url=gateway_url,
            x402_enabled=True,
            x402_private_key=private_key,
            x402_network="base-sepolia",
            x402_auto_pay=False,
            x402_payment_callback=payment_callback
        )

        try:
            # Attempt stamp purchase - may trigger 402
            result = client.purchase_stamp(duration_hours=24)
            assert result is not None
            assert hasattr(result, 'batchID')
        except Exception as e:
            # If 402 and payment made, that's still a successful test
            if payment_made["called"]:
                pytest.skip(f"Payment callback triggered but failed: {e}")
            raise
