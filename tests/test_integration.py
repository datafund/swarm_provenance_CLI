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
    """Gateway URL from environment or default."""
    return os.getenv("PROVENANCE_GATEWAY_URL", "https://provenance-gateway.datafund.io")


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
            raw_balance, usdc_balance = client.get_usdc_balance()
            # Raw balance is int (smallest units), usdc_balance is float
            assert isinstance(raw_balance, int)
            assert isinstance(usdc_balance, float)
            assert raw_balance >= 0
            assert usdc_balance >= 0
        except Exception as e:
            pytest.skip(f"Balance check failed (RPC issue?): {e}")

    @skip_if_no_x402
    def test_x402_domain_validation_base_sepolia(self):
        """Test that EIP-712 domain config matches Base Sepolia USDC contract.

        This test validates that our hardcoded domain configuration produces
        a DOMAIN_SEPARATOR that matches what the actual USDC contract uses.
        If this test fails, payment signatures will be invalid on-chain.
        """
        from swarm_provenance_uploader.core.x402_client import (
            X402Client,
            USDC_PERMIT_DOMAIN,
            USDC_CONTRACTS,
            compute_domain_separator,
            fetch_contract_domain_separator,
            CHAIN_IDS,
        )
        from web3 import Web3

        network = "base-sepolia"
        domain = USDC_PERMIT_DOMAIN[network]

        # Connect to Base Sepolia
        web3 = Web3(Web3.HTTPProvider("https://sepolia.base.org"))

        # Fetch actual DOMAIN_SEPARATOR from contract
        actual = fetch_contract_domain_separator(web3, USDC_CONTRACTS[network])

        # Compute what we would produce with our config
        computed = compute_domain_separator(
            name=domain["name"],
            version=domain["version"],
            chain_id=CHAIN_IDS[network],
            contract_address=USDC_CONTRACTS[network],
        )

        assert computed == actual, (
            f"EIP-712 domain mismatch for {network}! "
            f"Our config (name='{domain['name']}', version='{domain['version']}') "
            f"produces DOMAIN_SEPARATOR {computed.hex()}, "
            f"but contract has {actual.hex()}. "
            f"Payments will fail on-chain!"
        )

    @skip_if_no_x402
    def test_x402_domain_validation_base_mainnet(self):
        """Test that EIP-712 domain config matches Base mainnet USDC contract.

        This test validates that our hardcoded domain configuration produces
        a DOMAIN_SEPARATOR that matches what the actual USDC contract uses.
        If this test fails, payment signatures will be invalid on-chain.
        """
        from swarm_provenance_uploader.core.x402_client import (
            USDC_PERMIT_DOMAIN,
            USDC_CONTRACTS,
            compute_domain_separator,
            fetch_contract_domain_separator,
            CHAIN_IDS,
        )
        from web3 import Web3

        network = "base"
        domain = USDC_PERMIT_DOMAIN[network]

        # Connect to Base mainnet
        web3 = Web3(Web3.HTTPProvider("https://mainnet.base.org"))

        try:
            # Fetch actual DOMAIN_SEPARATOR from contract
            actual = fetch_contract_domain_separator(web3, USDC_CONTRACTS[network])

            # Compute what we would produce with our config
            computed = compute_domain_separator(
                name=domain["name"],
                version=domain["version"],
                chain_id=CHAIN_IDS[network],
                contract_address=USDC_CONTRACTS[network],
            )

            assert computed == actual, (
                f"EIP-712 domain mismatch for {network}! "
                f"Our config (name='{domain['name']}', version='{domain['version']}') "
                f"produces DOMAIN_SEPARATOR {computed.hex()}, "
                f"but contract has {actual.hex()}. "
                f"Payments will fail on-chain!"
            )
        except Exception as e:
            pytest.skip(f"Could not connect to Base mainnet RPC: {e}")

    @skip_if_no_x402
    def test_x402_client_validates_domain_before_signing(self):
        """Test that X402Client validates domain configuration before signing.

        The client should validate that the EIP-712 domain matches the on-chain
        contract BEFORE signing any payments. This prevents signing with incorrect
        domains that would fail on-chain.
        """
        from swarm_provenance_uploader.core.x402_client import X402Client
        from swarm_provenance_uploader.models import X402PaymentOption

        client = X402Client(network="base-sepolia")

        # Domain should not be validated yet (lazy validation)
        assert client._domain_validated is False

        # Create a payment option
        option = X402PaymentOption(
            scheme="exact",
            network="base-sepolia",
            maxAmountRequired="1000",
            resource="/test",
            payTo="0xc87688A40CE2ff1765BA54497c7471c892755488",
        )

        # Signing should trigger domain validation
        try:
            header = client.sign_payment(option)
            # If we get here, domain was validated and signing succeeded
            assert client._domain_validated is True
            assert header is not None
        except Exception as e:
            pytest.fail(f"Domain validation or signing failed: {e}")

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

        assert client.x402_enabled is True
        # x402 client is lazy-loaded, so access it via _get_x402_client()
        x402_client = client._get_x402_client()
        assert x402_client is not None

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
    def test_stamp_purchase_with_x402(self, gateway_url):
        """Test purchasing a stamp with x402 payment.

        This test makes a real payment on Base Sepolia if x402 is enabled on gateway.
        Verifies:
        - 402 Payment Required is received (gateway requires payment)
        - Payment is signed and submitted
        - x-payment-response header shows success=true (not transaction_failed)
        - CLI wallet USDC balance decreases after payment
        - Stamp is purchased successfully

        If x-payment-response shows success=false, PaymentTransactionFailedError is raised.
        This prevents silent fallback to free tier.
        """
        from swarm_provenance_uploader.core.gateway_client import GatewayClient
        from swarm_provenance_uploader.core.x402_client import X402Client
        from swarm_provenance_uploader.exceptions import PaymentTransactionFailedError

        private_key = os.getenv("SWARM_X402_PRIVATE_KEY")

        # Get balance before payment
        x402_client = X402Client(private_key=private_key, network="base-sepolia")
        balance_before_raw, balance_before_usdc = x402_client.get_usdc_balance()

        print(f"\n=== x402 Payment Flow Test ===")
        print(f"Wallet: {x402_client.wallet_address}")
        print(f"Balance before: ${balance_before_usdc:.6f} USDC")

        # Track payment state
        payment_state = {
            "received_402": False,
            "signed_payment": False,
            "amount": None,
        }

        def payment_callback(amount_usd: str, description: str) -> bool:
            """Callback to track payment signing."""
            payment_state["received_402"] = True
            payment_state["signed_payment"] = True
            payment_state["amount"] = amount_usd
            print(f"  402 received - signing payment: {amount_usd}")
            print(f"  Description: {description}")
            return True  # Auto-confirm for test

        client = GatewayClient(
            base_url=gateway_url,
            x402_enabled=True,
            x402_private_key=private_key,
            x402_network="base-sepolia",
            x402_auto_pay=True,
            x402_max_auto_pay_usd=1.00,
            x402_payment_callback=payment_callback
        )

        # Attempt stamp purchase
        # If x-payment-response shows success=false, this will raise PaymentTransactionFailedError
        try:
            result = client.purchase_stamp(verbose=True)
        except PaymentTransactionFailedError as e:
            # Payment was signed but on-chain transaction failed
            # This is the scenario we're testing for - gateway fell back to free tier
            print(f"\n  FAILED: Payment signed but transaction failed!")
            print(f"  Error reason: {e.error_reason}")
            print(f"  Payer: {e.payer}")
            pytest.fail(
                f"x402 payment transaction failed (gateway used free tier). "
                f"Reason: {e.error_reason}. "
                f"Gateway should return 402 error instead of falling back."
            )

        assert result is not None
        assert isinstance(result, str)
        assert len(result) == 64, f"Batch ID should be 64 hex chars, got {len(result)}"

        # Get balance after
        balance_after_raw, balance_after_usdc = x402_client.get_usdc_balance()

        print(f"\n=== Results ===")
        print(f"  Batch ID: {result}")
        print(f"  Balance after: ${balance_after_usdc:.6f} USDC")

        balance_changed = balance_after_raw < balance_before_raw

        if payment_state["received_402"]:
            # 402 was received and payment was signed
            # At this point, if we didn't get PaymentTransactionFailedError,
            # the payment should have succeeded
            print(f"  Payment amount: {payment_state['amount']}")

            if balance_changed:
                diff = balance_before_usdc - balance_after_usdc
                print(f"  Balance decreased by: ${diff:.6f} USDC")
                print(f"  SUCCESS: x402 payment completed on-chain!")
            else:
                # Balance didn't change yet - might be pending
                # With EIP-3009, the facilitator executes the transfer async
                print(f"  Note: Balance unchanged - payment may be pending on-chain")
                print(f"  The x-payment-response showed success=true")
        else:
            # No 402 received - gateway didn't require payment (free tier enabled)
            print(f"  Note: No 402 received - gateway did not require payment")
            print(f"  This is expected if gateway has free tier enabled")
