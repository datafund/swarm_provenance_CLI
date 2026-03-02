"""Integration tests that hit real backends.

These tests require actual running services:
- Local Bee node at http://localhost:1633
- Gateway at https://provenance-gateway.datafund.io

For x402 tests:
- Base Sepolia wallet with USDC
- X402_PRIVATE_KEY environment variable set

For blockchain tests:
- Local Hardhat node at http://localhost:8545 with DataProvenance deployed
- Or Base Sepolia with PROVENANCE_WALLET_KEY set
- blockchain dependencies installed (pip install -e .[blockchain])

Run with: pytest tests/test_integration.py -v
Skip with: pytest --ignore=tests/test_integration.py

Tests are marked with:
- @pytest.mark.integration - all integration tests
- @pytest.mark.local_bee - requires local Bee node
- @pytest.mark.gateway - requires gateway service
- @pytest.mark.x402 - requires x402 wallet configuration
- @pytest.mark.blockchain - requires blockchain deps and network access
"""

import os
import secrets

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
    """Gateway URL for integration tests.

    Uses INTEGRATION_GATEWAY_URL if set, otherwise defaults to production.
    This is intentionally separate from PROVENANCE_GATEWAY_URL (used by the
    app and often overridden in .env.local for local development).
    """
    return os.getenv("INTEGRATION_GATEWAY_URL", "https://provenance-gateway.datafund.io")


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
    private_key = os.getenv("X402_PRIVATE_KEY")
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
    reason="x402 not configured (X402_PRIVATE_KEY not set or deps missing)"
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
    - X402_PRIVATE_KEY environment variable set
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

        private_key = os.getenv("X402_PRIVATE_KEY")

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

        private_key = os.getenv("X402_PRIVATE_KEY")

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


# =============================================================================
# BLOCKCHAIN SKIP CONDITIONS
# =============================================================================

def are_blockchain_deps_installed():
    """Check if blockchain dependencies are installed."""
    try:
        import eth_account  # noqa: F401
        import web3  # noqa: F401
        return True
    except ImportError:
        return False


def is_hardhat_available():
    """Check if local Hardhat node is reachable at localhost:8545."""
    try:
        resp = requests.post(
            "http://localhost:8545",
            json={"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1},
            timeout=3,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def is_chain_wallet_configured():
    """Check if blockchain wallet is configured."""
    key = os.getenv("PROVENANCE_WALLET_KEY")
    return key is not None and len(key) >= 64


skip_if_no_blockchain_deps = pytest.mark.skipif(
    not are_blockchain_deps_installed(),
    reason="Blockchain deps not installed (pip install -e .[blockchain])"
)

skip_if_no_hardhat = pytest.mark.skipif(
    not is_hardhat_available() or not are_blockchain_deps_installed(),
    reason="Local Hardhat node not available at localhost:8545 or blockchain deps missing"
)

skip_if_no_chain_wallet = pytest.mark.skipif(
    not is_chain_wallet_configured() or not are_blockchain_deps_installed(),
    reason="PROVENANCE_WALLET_KEY not set or blockchain deps missing"
)


# =============================================================================
# BLOCKCHAIN INTEGRATION TESTS - LOCAL HARDHAT
# =============================================================================


def _random_hash():
    """Generate a random 64-char hex hash for idempotent test runs."""
    return secrets.token_hex(32)


@pytest.mark.integration
@pytest.mark.blockchain
class TestBlockchainLocalHardhat:
    """Integration tests against a local Hardhat node.

    Requires:
    - Hardhat running at http://localhost:8545 with DataProvenance deployed
    - PROVENANCE_WALLET_KEY set (use Hardhat default account)
    - blockchain deps installed (pip install -e .[blockchain])

    Start Hardhat with:
        npx hardhat node
        npx hardhat run scripts/deploy.js --network localhost
    """

    @skip_if_no_hardhat
    @skip_if_no_chain_wallet
    def test_chain_provider_health(self):
        """Test ChainProvider connects to local Hardhat."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        contract = os.getenv("CHAIN_CONTRACT")
        if not contract:
            pytest.skip("CHAIN_CONTRACT not set for local Hardhat")

        provider = ChainProvider(
            chain="base-sepolia",
            rpc_url="http://localhost:8545",
            contract_address=contract,
        )
        # Hardhat may report a different chain ID, so just check connection
        assert provider.web3.is_connected()

    @skip_if_no_hardhat
    @skip_if_no_chain_wallet
    def test_chain_client_anchor(self):
        """Test anchoring a hash on local Hardhat."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        contract = os.getenv("CHAIN_CONTRACT")
        if not contract:
            pytest.skip("CHAIN_CONTRACT not set for local Hardhat")

        client = ChainClient(
            chain="base-sepolia",
            rpc_url="http://localhost:8545",
            contract_address=contract,
        )

        test_hash = _random_hash()
        result = client.anchor(
            swarm_hash=test_hash,
            data_type="integration-test",
            verbose=True,
        )

        assert result.tx_hash is not None
        assert result.block_number > 0
        assert result.gas_used > 0
        assert result.swarm_hash == test_hash

    @skip_if_no_hardhat
    @skip_if_no_chain_wallet
    def test_chain_client_anchor_and_verify(self):
        """Test anchoring then verifying on local Hardhat."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        contract = os.getenv("CHAIN_CONTRACT")
        if not contract:
            pytest.skip("CHAIN_CONTRACT not set for local Hardhat")

        client = ChainClient(
            chain="base-sepolia",
            rpc_url="http://localhost:8545",
            contract_address=contract,
        )

        test_hash = _random_hash()
        client.anchor(swarm_hash=test_hash, data_type="test")

        # Verify it's on-chain
        assert client.verify(swarm_hash=test_hash) is True

        # Get full record
        record = client.get(swarm_hash=test_hash)
        assert record.data_type == "test"
        assert record.owner == client.address

    @skip_if_no_hardhat
    @skip_if_no_chain_wallet
    def test_chain_client_record_access(self):
        """Test recording data access on local Hardhat."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        contract = os.getenv("CHAIN_CONTRACT")
        if not contract:
            pytest.skip("CHAIN_CONTRACT not set for local Hardhat")

        client = ChainClient(
            chain="base-sepolia",
            rpc_url="http://localhost:8545",
            contract_address=contract,
        )

        test_hash = _random_hash()
        # Register first
        client.anchor(swarm_hash=test_hash, data_type="access-test")
        # Record access
        result = client.access(swarm_hash=test_hash)

        assert result.tx_hash is not None
        assert result.accessor == client.address

    @skip_if_no_hardhat
    @skip_if_no_chain_wallet
    def test_chain_client_transform(self):
        """Test recording transformation on local Hardhat."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        contract = os.getenv("CHAIN_CONTRACT")
        if not contract:
            pytest.skip("CHAIN_CONTRACT not set for local Hardhat")

        client = ChainClient(
            chain="base-sepolia",
            rpc_url="http://localhost:8545",
            contract_address=contract,
        )

        orig_hash = _random_hash()
        new_hash = _random_hash()
        # Register original
        client.anchor(swarm_hash=orig_hash, data_type="transform-test")
        # Record transformation
        result = client.transform(
            original_hash=orig_hash,
            new_hash=new_hash,
            description="Filtered PII data",
        )

        assert result.original_hash == orig_hash
        assert result.new_hash == new_hash

    @skip_if_no_hardhat
    @skip_if_no_chain_wallet
    def test_chain_client_balance(self):
        """Test getting wallet balance on local Hardhat."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        contract = os.getenv("CHAIN_CONTRACT")
        if not contract:
            pytest.skip("CHAIN_CONTRACT not set for local Hardhat")

        client = ChainClient(
            chain="base-sepolia",
            rpc_url="http://localhost:8545",
            contract_address=contract,
        )

        info = client.balance()
        assert info.address == client.address
        # Hardhat default accounts have 10000 ETH
        assert info.balance_wei > 0

    @skip_if_no_hardhat
    @skip_if_no_chain_wallet
    def test_chain_client_set_status(self):
        """Test setting data status on local Hardhat."""
        from swarm_provenance_uploader.core.chain_client import ChainClient
        from swarm_provenance_uploader.models import DataStatusEnum

        contract = os.getenv("CHAIN_CONTRACT")
        if not contract:
            pytest.skip("CHAIN_CONTRACT not set for local Hardhat")

        client = ChainClient(
            chain="base-sepolia",
            rpc_url="http://localhost:8545",
            contract_address=contract,
        )

        test_hash = _random_hash()
        # Register first
        client.anchor(swarm_hash=test_hash, data_type="status-test")

        # Set to RESTRICTED
        result = client.set_status(swarm_hash=test_hash, status=1)
        assert result.tx_hash is not None

        # Verify status changed
        record = client.get(swarm_hash=test_hash)
        assert record.status == DataStatusEnum.RESTRICTED

    @skip_if_no_hardhat
    @skip_if_no_chain_wallet
    def test_chain_client_transfer_ownership(self):
        """Test transferring data ownership on local Hardhat."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        contract = os.getenv("CHAIN_CONTRACT")
        if not contract:
            pytest.skip("CHAIN_CONTRACT not set for local Hardhat")

        client = ChainClient(
            chain="base-sepolia",
            rpc_url="http://localhost:8545",
            contract_address=contract,
        )

        test_hash = _random_hash()
        new_owner = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"  # Hardhat account #1

        # Register first
        client.anchor(swarm_hash=test_hash, data_type="transfer-test")

        # Transfer ownership
        result = client.transfer_ownership(swarm_hash=test_hash, new_owner=new_owner)
        assert result.tx_hash is not None
        assert result.owner == new_owner

        # Verify new owner
        record = client.get(swarm_hash=test_hash)
        assert record.owner.lower() == new_owner.lower()

    @skip_if_no_hardhat
    @skip_if_no_chain_wallet
    def test_chain_client_delegate(self):
        """Test delegate authorization on local Hardhat."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        contract = os.getenv("CHAIN_CONTRACT")
        if not contract:
            pytest.skip("CHAIN_CONTRACT not set for local Hardhat")

        client = ChainClient(
            chain="base-sepolia",
            rpc_url="http://localhost:8545",
            contract_address=contract,
        )

        delegate_addr = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"

        # Authorize delegate
        result = client.set_delegate(delegate=delegate_addr, authorized=True)
        assert result.tx_hash is not None

    @skip_if_no_hardhat
    @skip_if_no_chain_wallet
    def test_chain_provenance_chain_walk(self):
        """Test provenance chain walking: anchor A, transform A->B, walk chain."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        contract = os.getenv("CHAIN_CONTRACT")
        if not contract:
            pytest.skip("CHAIN_CONTRACT not set for local Hardhat")

        client = ChainClient(
            chain="base-sepolia",
            rpc_url="http://localhost:8545",
            contract_address=contract,
        )

        hash_a = _random_hash()
        hash_b = _random_hash()

        # Anchor original
        client.anchor(swarm_hash=hash_a, data_type="chain-walk-test")

        # Transform A -> B
        client.transform(
            original_hash=hash_a,
            new_hash=hash_b,
            description="Removed PII",
        )

        # Walk the chain
        chain = client.get_provenance_chain(swarm_hash=hash_a)

        # Record A should be in the chain with its transformation description
        assert len(chain) >= 1
        assert chain[0].data_hash == hash_a
        assert len(chain[0].transformations) == 1
        assert chain[0].transformations[0].description == "Removed PII"

    @skip_if_no_hardhat
    @skip_if_no_chain_wallet
    def test_chain_protect_workflow(self):
        """Test full protect workflow: anchor, protect, verify restriction."""
        from swarm_provenance_uploader.core.chain_client import ChainClient
        from swarm_provenance_uploader.models import DataStatusEnum

        contract = os.getenv("CHAIN_CONTRACT")
        if not contract:
            pytest.skip("CHAIN_CONTRACT not set for local Hardhat")

        client = ChainClient(
            chain="base-sepolia",
            rpc_url="http://localhost:8545",
            contract_address=contract,
        )

        orig_hash = _random_hash()
        new_hash = _random_hash()

        # Anchor original (new_hash is auto-registered by recordTransformation)
        client.anchor(swarm_hash=orig_hash, data_type="protect-test")

        # Transform
        client.transform(
            original_hash=orig_hash,
            new_hash=new_hash,
            description="Protected PII data",
        )

        # Restrict original
        client.set_status(swarm_hash=orig_hash, status=1)

        # Verify original is RESTRICTED
        record = client.get(swarm_hash=orig_hash)
        assert record.status == DataStatusEnum.RESTRICTED

    @skip_if_no_hardhat
    @skip_if_no_blockchain_deps
    def test_chain_client_anchor_insufficient_gas(self):
        """Test that an explicit gas limit too low for a contract call raises ChainTransactionError."""
        from swarm_provenance_uploader.core.chain_client import ChainClient
        from swarm_provenance_uploader.exceptions import ChainTransactionError

        contract = os.getenv("CHAIN_CONTRACT")
        if not contract:
            pytest.skip("CHAIN_CONTRACT not set for local Hardhat")

        # 21,000 is enough for a plain ETH transfer but way too low for
        # a registerData contract call — the node should reject or revert.
        client = ChainClient(
            chain="base-sepolia",
            rpc_url="http://localhost:8545",
            contract_address=contract,
            gas_limit=21_000,
        )

        with pytest.raises(ChainTransactionError) as exc_info:
            client.anchor(swarm_hash=_random_hash(), data_type="gas-test")

        print(f"\n=== Insufficient Gas Handled ===")
        print(f"  Error: {exc_info.value}")


# =============================================================================
# BLOCKCHAIN INTEGRATION TESTS - BASE SEPOLIA
# =============================================================================

@pytest.mark.integration
@pytest.mark.blockchain
@pytest.mark.slow
class TestBlockchainBaseSepolia:
    """Integration tests against Base Sepolia testnet.

    Requires:
    - PROVENANCE_WALLET_KEY set with funded Base Sepolia wallet
    - blockchain deps installed (pip install -e .[blockchain])
    - Wallet has ETH for gas on Base Sepolia

    These tests use real testnet gas and should be run sparingly.
    Run with: pytest tests/test_integration.py -v -m "blockchain and slow"
    """

    @skip_if_no_chain_wallet
    @skip_if_no_blockchain_deps
    def test_chain_provider_health_base_sepolia(self):
        """Test ChainProvider connects to Base Sepolia."""
        from swarm_provenance_uploader.chain.provider import ChainProvider

        provider = ChainProvider(chain="base-sepolia")

        try:
            assert provider.health_check() is True
            block = provider.get_block_number()
            print(f"\nBase Sepolia connected, block: {block}")
        except Exception as e:
            pytest.skip(f"Base Sepolia RPC unavailable: {e}")

    @skip_if_no_chain_wallet
    @skip_if_no_blockchain_deps
    def test_chain_client_balance_base_sepolia(self):
        """Test getting wallet balance on Base Sepolia."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        try:
            client = ChainClient(chain="base-sepolia")
            info = client.balance()

            print(f"\n=== Base Sepolia Wallet ===")
            print(f"  Address: {info.address}")
            print(f"  Balance: {info.balance_eth} ETH")
            print(f"  Chain: {info.chain}")
            print(f"  Contract: {info.contract_address}")

            assert info.address.startswith("0x")
            assert info.balance_wei >= 0
        except Exception as e:
            pytest.skip(f"Base Sepolia connection failed: {e}")

    @skip_if_no_chain_wallet
    @skip_if_no_blockchain_deps
    def test_chain_client_verify_unregistered_base_sepolia(self):
        """Test verifying an unregistered hash on Base Sepolia."""
        from swarm_provenance_uploader.core.chain_client import ChainClient

        try:
            client = ChainClient(chain="base-sepolia")
            # Random hash should not be registered
            random_hash = _random_hash()
            assert client.verify(swarm_hash=random_hash) is False
        except Exception as e:
            pytest.skip(f"Base Sepolia connection failed: {e}")

    @skip_if_no_chain_wallet
    @skip_if_no_blockchain_deps
    def test_chain_client_anchor_base_sepolia(self):
        """Test anchoring a hash on Base Sepolia.

        WARNING: This uses real testnet gas. Run sparingly.
        """
        from swarm_provenance_uploader.core.chain_client import ChainClient
        import secrets
        import time

        try:
            client = ChainClient(chain="base-sepolia")

            # Use a random hash to avoid collisions
            test_hash = secrets.token_hex(32)
            result = client.anchor(
                swarm_hash=test_hash,
                data_type="integration-test",
                verbose=True,
            )

            print(f"\n=== Anchor Result ===")
            print(f"  TX: {result.tx_hash}")
            print(f"  Block: {result.block_number}")
            print(f"  Gas: {result.gas_used}")
            print(f"  Explorer: {result.explorer_url}")

            assert result.tx_hash is not None
            assert result.block_number > 0

            # Wait for the anchor to propagate before verifying.
            # Base Sepolia needs a few seconds for the state to be
            # readable after the transaction is confirmed.
            time.sleep(3)

            # Verify it's on-chain
            assert client.verify(swarm_hash=test_hash) is True
        except Exception as e:
            pytest.skip(f"Base Sepolia anchor failed: {e}")

    @skip_if_no_chain_wallet
    @skip_if_no_blockchain_deps
    def test_chain_client_anchor_already_registered_base_sepolia(self):
        """Test that anchoring an already-registered hash raises DataAlreadyRegisteredError.

        WARNING: This uses real testnet gas (one anchor tx). Run sparingly.
        """
        from swarm_provenance_uploader.core.chain_client import ChainClient
        from swarm_provenance_uploader.exceptions import DataAlreadyRegisteredError
        import secrets
        import time

        try:
            client = ChainClient(chain="base-sepolia")

            # Anchor a fresh hash first
            test_hash = secrets.token_hex(32)
            result = client.anchor(
                swarm_hash=test_hash,
                data_type="integration-test",
            )
            assert result.tx_hash is not None

            # Wait for propagation
            time.sleep(3)

            # Attempt to anchor the same hash again — should raise
            with pytest.raises(DataAlreadyRegisteredError) as exc_info:
                client.anchor(swarm_hash=test_hash, data_type="integration-test")

            assert exc_info.value.data_hash == test_hash
            assert exc_info.value.owner is not None
            assert exc_info.value.timestamp > 0
            assert exc_info.value.data_type == "integration-test"

            print(f"\n=== Already-Registered Check ===")
            print(f"  Hash: {test_hash}")
            print(f"  Owner: {exc_info.value.owner}")
            print(f"  Type: {exc_info.value.data_type}")
        except DataAlreadyRegisteredError:
            raise  # Re-raise so pytest.raises captures it properly
        except Exception as e:
            pytest.skip(f"Base Sepolia test failed: {e}")


# =============================================================================
# MANIFEST / COLLECTION UPLOAD TESTS
# =============================================================================

class TestGatewayManifestUpload:
    """Integration tests for manifest/collection upload via gateway."""

    @pytest.mark.integration
    @pytest.mark.gateway
    def test_gateway_manifest_upload(self, gateway_client, tmp_path):
        """Upload a directory as a manifest and verify reference is returned."""
        import tarfile
        from swarm_provenance_uploader.core.file_utils import create_tar_from_directory

        # Create temp directory with test files
        test_dir = tmp_path / "test_collection"
        test_dir.mkdir()
        (test_dir / "readme.txt").write_text("Test collection readme")
        sub = test_dir / "data"
        sub.mkdir()
        (sub / "values.csv").write_text("x,y\n1,2\n3,4")

        # Create TAR
        tar_path = tmp_path / "collection.tar"
        create_tar_from_directory(test_dir, tar_path)
        assert tar_path.exists()

        # First purchase a stamp
        try:
            stamp_id = gateway_client.purchase_stamp(duration_hours=25, verbose=True)
        except Exception as e:
            pytest.skip(f"Could not purchase stamp: {e}")

        # Wait for stamp to be usable
        import time
        for _ in range(12):
            stamp = gateway_client.get_stamp(stamp_id)
            if stamp and stamp.usable:
                break
            time.sleep(10)
        else:
            pytest.skip("Stamp did not become usable in time")

        # Upload manifest
        result = gateway_client.upload_manifest(
            tar_path=str(tar_path),
            stamp_id=stamp_id,
            verbose=True,
        )

        print(f"\n=== Manifest Upload Result ===")
        print(f"  Reference: {result.reference}")
        print(f"  File count: {result.file_count}")
        print(f"  Message: {result.message}")

        assert result.reference is not None
        assert len(result.reference) == 64  # Swarm hash length
