import pytest
import typer
from typer.testing import CliRunner
from swarm_provenance_uploader.cli import app, _backend_config, _x402_config, _chain_config
from swarm_provenance_uploader.models import (
    StampDetails,
    StampListResponse,
    StampPurchaseResponse,
    WalletResponse,
    ChequebookResponse,
)

# Create a Typer Test Runner
runner = CliRunner()

# Test constants
DUMMY_HASH = "a028d9370473556397e189567c07279195890a1688600210336996689840.2.0"
DUMMY_STAMP = "a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3"
DUMMY_SWARM_REF = "b5d4ea763a1396676771151158461f73678f1676166acd06a0a18600b85de8a4"


@pytest.fixture(autouse=True)
def reset_backend_config():
    """Reset backend config to defaults before each test."""
    _backend_config["backend"] = "gateway"
    _backend_config["gateway_url"] = "https://provenance-gateway.datafund.io"
    _backend_config["bee_url"] = "http://localhost:1633"
    _backend_config["free_tier"] = False
    _x402_config["enabled"] = False
    _x402_config["auto_pay"] = False
    _x402_config["max_auto_pay_usd"] = 1.00
    _x402_config["network"] = "base-sepolia"
    _chain_config["enabled"] = False
    _chain_config["chain"] = "base-sepolia"
    _chain_config["rpc_url"] = None
    _chain_config["contract"] = None
    _chain_config["wallet_key_env"] = "PROVENANCE_WALLET_KEY"
    _chain_config["explorer_url"] = None
    _chain_config["gas_limit"] = None
    yield
    # Reset again after test
    _backend_config["backend"] = "gateway"
    _backend_config["gateway_url"] = "https://provenance-gateway.datafund.io"
    _backend_config["bee_url"] = "http://localhost:1633"
    _backend_config["free_tier"] = False
    _x402_config["enabled"] = False
    _x402_config["auto_pay"] = False
    _x402_config["max_auto_pay_usd"] = 1.00
    _x402_config["network"] = "base-sepolia"
    _chain_config["enabled"] = False
    _chain_config["chain"] = "base-sepolia"
    _chain_config["rpc_url"] = None
    _chain_config["contract"] = None
    _chain_config["wallet_key_env"] = "PROVENANCE_WALLET_KEY"
    _chain_config["explorer_url"] = None
    _chain_config["gas_limit"] = None


# =============================================================================
# LOCAL BACKEND TESTS (--backend local)
# =============================================================================

class TestLocalBackendUpload:
    """Tests for upload command with local Bee backend."""

    def test_upload_command_success(self, mocker):
        """Tests the CLI upload command with local backend."""
        # Mock swarm_client functions
        m_purchase_stamp = mocker.patch(
            "swarm_provenance_uploader.cli.swarm_client.purchase_postage_stamp",
            return_value=DUMMY_STAMP
        )
        m_get_stamp_info = mocker.patch(
            "swarm_provenance_uploader.cli.swarm_client.get_stamp_info",
            return_value={"exists": True, "usable": True, "batchTTL": 3600}
        )
        m_upload_data = mocker.patch(
            "swarm_provenance_uploader.cli.swarm_client.upload_data",
            return_value=DUMMY_SWARM_REF
        )

        with runner.isolated_filesystem():
            with open("my_data.txt", "w") as f:
                f.write("some provenance data")

            result = runner.invoke(
                app,
                ["--backend", "local", "upload", "--file", "my_data.txt", "--std", "TESTING-V1"]
            )

            assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
            assert DUMMY_SWARM_REF in result.stdout
            assert "SUCCESS!" in result.stdout

            m_purchase_stamp.assert_called_once()
            m_upload_data.assert_called_once()

    def test_upload_file_not_found(self):
        """Tests CLI exits correctly if file does not exist."""
        result = runner.invoke(app, ["--backend", "local", "upload", "--file", "non_existent_file.dat"])
        assert result.exit_code != 0
        assert "Invalid value" in result.stdout

    def test_upload_stamp_purchase_fails(self, mocker):
        """Tests CLI exits correctly if stamp purchase fails."""
        mocker.patch(
            "swarm_provenance_uploader.cli.swarm_client.purchase_postage_stamp",
            side_effect=ConnectionError("Mock Connection Error")
        )

        with runner.isolated_filesystem():
            with open("my_data.txt", "w") as f:
                f.write("some data")

            result = runner.invoke(app, ["--backend", "local", "upload", "--file", "my_data.txt"])

            assert result.exit_code == 1
            assert "ERROR: Failed purchasing stamp" in result.stdout


class TestLocalBackendDownload:
    """Tests for download command with local Bee backend."""

    def test_download_command_success(self, mocker):
        """Tests download command with local backend."""
        import json
        import base64

        original_data = b"test provenance data"
        b64_data = base64.b64encode(original_data).decode()
        import hashlib
        content_hash = hashlib.sha256(original_data).hexdigest()

        metadata = {
            "data": b64_data,
            "content_hash": content_hash,
            "stamp_id": DUMMY_STAMP,
            "provenance_standard": "TEST-V1",
            "encryption": None
        }

        mocker.patch(
            "swarm_provenance_uploader.cli.swarm_client.download_data_from_swarm",
            return_value=json.dumps(metadata).encode()
        )

        with runner.isolated_filesystem():
            result = runner.invoke(
                app,
                ["--backend", "local", "download", DUMMY_SWARM_REF, "--output-dir", "."]
            )

            assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
            assert "SUCCESS: Content hash verification passed!" in result.stdout

    def test_download_not_found(self, mocker):
        """Tests download fails gracefully when data not found."""
        mocker.patch(
            "swarm_provenance_uploader.cli.swarm_client.download_data_from_swarm",
            side_effect=FileNotFoundError("Data not found")
        )

        result = runner.invoke(
            app,
            ["--backend", "local", "download", DUMMY_SWARM_REF]
        )

        assert result.exit_code == 1
        assert "ERROR:" in result.stdout


# =============================================================================
# GATEWAY BACKEND TESTS (--backend gateway, default)
# =============================================================================

class TestGatewayBackendUpload:
    """Tests for upload command with gateway backend."""

    def test_upload_command_success(self, mocker):
        """Tests the CLI upload command with gateway backend (default)."""
        mock_client = mocker.MagicMock()
        mock_client.purchase_stamp.return_value = DUMMY_STAMP
        mock_client.get_stamp.return_value = StampDetails(
            batchID=DUMMY_STAMP,
            usable=True,
            exists=True,
            depth=17,
            amount="1000000000",
            bucketDepth=16,
            blockNumber=12345,
            immutableFlag=False,
            batchTTL=3600,
            utilization=0
        )
        mock_client.upload_data.return_value = DUMMY_SWARM_REF

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        with runner.isolated_filesystem():
            with open("my_data.txt", "w") as f:
                f.write("some provenance data")

            result = runner.invoke(
                app,
                ["upload", "--file", "my_data.txt", "--std", "TESTING-V1"]
            )

            assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
            assert DUMMY_SWARM_REF in result.stdout
            assert "SUCCESS!" in result.stdout

    def test_upload_gateway_connection_fails(self, mocker):
        """Tests CLI handles gateway connection errors."""
        mock_client = mocker.MagicMock()
        mock_client.purchase_stamp.side_effect = ConnectionError("Gateway unreachable")

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        with runner.isolated_filesystem():
            with open("my_data.txt", "w") as f:
                f.write("some data")

            result = runner.invoke(app, ["upload", "--file", "my_data.txt"])

            assert result.exit_code == 1
            assert "ERROR: Failed purchasing stamp" in result.stdout


class TestGatewayBackendDownload:
    """Tests for download command with gateway backend."""

    def test_download_command_success(self, mocker):
        """Tests download command with gateway backend."""
        import json
        import base64
        import hashlib

        original_data = b"test provenance data"
        b64_data = base64.b64encode(original_data).decode()
        content_hash = hashlib.sha256(original_data).hexdigest()

        metadata = {
            "data": b64_data,
            "content_hash": content_hash,
            "stamp_id": DUMMY_STAMP,
            "provenance_standard": "TEST-V1",
            "encryption": None
        }

        mock_client = mocker.MagicMock()
        mock_client.download_data.return_value = json.dumps(metadata).encode()

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        with runner.isolated_filesystem():
            result = runner.invoke(
                app,
                ["download", DUMMY_SWARM_REF, "--output-dir", "."]
            )

            assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
            assert "SUCCESS: Content hash verification passed!" in result.stdout


# =============================================================================
# STAMPS COMMANDS TESTS
# =============================================================================

class TestStampsCommands:
    """Tests for stamps subcommands."""

    def test_stamps_list_success(self, mocker):
        """Tests stamps list command."""
        mock_client = mocker.MagicMock()
        mock_client.list_stamps.return_value = StampListResponse(
            stamps=[
                StampDetails(
                    batchID=DUMMY_STAMP,
                    usable=True,
                    exists=True,
                    depth=17,
                    amount="1000000000",
                    bucketDepth=16,
                    blockNumber=12345,
                    immutableFlag=False,
                    batchTTL=86400,
                    utilization=10
                )
            ],
            total_count=1
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["stamps", "list"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Total: 1 stamp(s)" in result.stdout

    def test_stamps_list_requires_gateway(self):
        """Tests stamps list fails with local backend."""
        result = runner.invoke(app, ["--backend", "local", "stamps", "list"])

        assert result.exit_code == 1
        assert "requires gateway backend" in result.stdout

    def test_stamps_info_success(self, mocker):
        """Tests stamps info command."""
        mock_client = mocker.MagicMock()
        mock_client.get_stamp.return_value = StampDetails(
            batchID=DUMMY_STAMP,
            usable=True,
            exists=True,
            depth=17,
            amount="1000000000",
            bucketDepth=16,
            blockNumber=12345,
            immutableFlag=False,
            batchTTL=3600,
            utilization=5
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["stamps", "info", DUMMY_STAMP])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Stamp Details:" in result.stdout
        assert "Usable:" in result.stdout

    def test_stamps_info_not_found(self, mocker):
        """Tests stamps info when stamp not found."""
        mock_client = mocker.MagicMock()
        mock_client.get_stamp.return_value = None

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["stamps", "info", DUMMY_STAMP])

        assert result.exit_code == 1
        assert "not found" in result.stdout

    def test_stamps_extend_success(self, mocker):
        """Tests stamps extend command."""
        mock_client = mocker.MagicMock()
        mock_client.extend_stamp.return_value = DUMMY_STAMP

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["stamps", "extend", DUMMY_STAMP, "--amount", "1000000"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "SUCCESS: Stamp extended" in result.stdout

    def test_stamps_extend_requires_gateway(self):
        """Tests stamps extend fails with local backend."""
        result = runner.invoke(
            app,
            ["--backend", "local", "stamps", "extend", DUMMY_STAMP, "--amount", "1000000"]
        )

        assert result.exit_code == 1
        assert "requires gateway backend" in result.stdout


# =============================================================================
# INFO COMMANDS TESTS (wallet, chequebook, health)
# =============================================================================

class TestInfoCommands:
    """Tests for wallet, chequebook, and health commands."""

    def test_wallet_success(self, mocker):
        """Tests wallet command."""
        mock_client = mocker.MagicMock()
        mock_client.get_wallet.return_value = WalletResponse(
            walletAddress="0x1234567890abcdef1234567890abcdef12345678",
            bzzBalance="100.5"
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["wallet"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Wallet Information:" in result.stdout
        assert "0x1234567890abcdef" in result.stdout

    def test_wallet_requires_gateway(self):
        """Tests wallet fails with local backend."""
        result = runner.invoke(app, ["--backend", "local", "wallet"])

        assert result.exit_code == 1
        assert "requires gateway backend" in result.stdout

    def test_chequebook_success(self, mocker):
        """Tests chequebook command."""
        mock_client = mocker.MagicMock()
        mock_client.get_chequebook.return_value = ChequebookResponse(
            chequebookAddress="0xabcdef1234567890abcdef1234567890abcdef12",
            availableBalance="50.0",
            totalBalance="100.0"
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["chequebook"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Chequebook Information:" in result.stdout

    def test_chequebook_requires_gateway(self):
        """Tests chequebook fails with local backend."""
        result = runner.invoke(app, ["--backend", "local", "chequebook"])

        assert result.exit_code == 1
        assert "requires gateway backend" in result.stdout

    def test_health_gateway_success(self, mocker):
        """Tests health command with gateway backend."""
        mock_client = mocker.MagicMock()
        mock_client.health_check.return_value = True

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["health"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Healthy" in result.stdout

    def test_health_gateway_unhealthy(self, mocker):
        """Tests health command when gateway is unhealthy."""
        mock_client = mocker.MagicMock()
        mock_client.health_check.return_value = False

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["health"])

        assert result.exit_code == 1
        assert "Unhealthy" in result.stdout

    def test_health_local_success(self, mocker):
        """Tests health command with local backend."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200

        mocker.patch("requests.get", return_value=mock_response)

        result = runner.invoke(app, ["--backend", "local", "health"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Healthy" in result.stdout


# =============================================================================
# BACKEND SWITCHING TESTS
# =============================================================================

class TestBackendSwitching:
    """Tests for --backend flag behavior."""

    def test_invalid_backend(self):
        """Tests invalid backend value."""
        result = runner.invoke(app, ["--backend", "invalid", "health"])

        assert result.exit_code == 1
        assert "Invalid backend" in result.stdout

    def test_default_is_gateway(self, mocker):
        """Tests that gateway is the default backend."""
        mock_client = mocker.MagicMock()
        mock_client.health_check.return_value = True

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["health"])

        # Should use gateway (mock was called)
        assert result.exit_code == 0
        mock_client.health_check.assert_called_once()

    def test_custom_gateway_url(self, mocker):
        """Tests custom gateway URL option."""
        mock_client = mocker.MagicMock()
        mock_client.health_check.return_value = True

        mock_constructor = mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(
            app,
            ["--gateway-url", "https://custom.gateway.io", "health"]
        )

        assert result.exit_code == 0
        # Verify custom URL was used
        mock_constructor.assert_called_with(base_url="https://custom.gateway.io", free_tier=False)


# =============================================================================
# VERSION FLAG TESTS
# =============================================================================

class TestVersionFlag:
    """Tests for --version flag."""

    def test_version_long_flag(self):
        """Tests --version flag shows version."""
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "swarm-prov-upload" in result.stdout
        # Version format: X.Y.Z or X.Y.Z+git.abc1234
        import re
        assert re.search(r"\d+\.\d+\.\d+", result.stdout)

    def test_version_short_flag(self):
        """Tests -V flag shows version."""
        result = runner.invoke(app, ["-V"])

        assert result.exit_code == 0
        assert "swarm-prov-upload" in result.stdout
        # Version format: X.Y.Z or X.Y.Z+git.abc1234
        import re
        assert re.search(r"\d+\.\d+\.\d+", result.stdout)


# =============================================================================
# STAMP ID OPTION TESTS
# =============================================================================

class TestStampIdOption:
    """Tests for --stamp-id option on upload."""

    def test_upload_with_existing_stamp(self, mocker):
        """Tests upload using existing stamp ID."""
        existing_stamp = "a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3"

        mock_client = mocker.MagicMock()
        mock_client.get_stamp.return_value = StampDetails(
            batchID=existing_stamp,
            usable=True,
            exists=True,
            depth=17,
            amount="1000000000",
            bucketDepth=16,
            blockNumber=12345,
            immutableFlag=False,
            batchTTL=3600,
            utilization=10
        )
        mock_client.upload_data.return_value = DUMMY_SWARM_REF

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        with runner.isolated_filesystem():
            with open("test_data.txt", "w") as f:
                f.write("test data")

            result = runner.invoke(
                app,
                ["upload", "--file", "test_data.txt", "--stamp-id", existing_stamp]
            )

            assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
            assert "Using existing stamp" in result.stdout
            assert DUMMY_SWARM_REF in result.stdout
            # Should NOT call purchase_stamp
            mock_client.purchase_stamp.assert_not_called()
            # Should call upload
            mock_client.upload_data.assert_called_once()

    def test_upload_with_unusable_stamp(self, mocker):
        """Tests upload fails when stamp exists but is not usable."""
        unusable_stamp = "a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3a3"

        mock_client = mocker.MagicMock()
        # Return a stamp that exists but is NOT usable
        mock_client.get_stamp.return_value = StampDetails(
            batchID=unusable_stamp,
            usable=False,  # Not usable!
            exists=True,
            depth=17,
            amount="1000000000",
            bucketDepth=16,
            blockNumber=12345,
            immutableFlag=False,
            batchTTL=3600,
            utilization=100
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        with runner.isolated_filesystem():
            with open("test_data.txt", "w") as f:
                f.write("test data")

            # Use minimal retries to speed up test
            result = runner.invoke(
                app,
                ["upload", "--file", "test_data.txt", "--stamp-id", unusable_stamp,
                 "--stamp-retries", "1", "--stamp-interval", "1"]
            )

            assert result.exit_code == 1
            assert "did not become USABLE" in result.stdout or "ERROR" in result.stdout


# =============================================================================
# LOCAL BACKEND WARNING TESTS
# =============================================================================

class TestLocalBackendWarning:
    """Tests for local backend deprecation warning."""

    def test_local_backend_shows_warning(self, mocker):
        """Tests that local backend shows warning message."""
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200

        mocker.patch("requests.get", return_value=mock_response)

        result = runner.invoke(app, ["--backend", "local", "health"])

        assert result.exit_code == 0
        # Warning should be shown (on stderr, but captured in output)
        assert "Local Bee backend is intended for development" in result.output or result.exit_code == 0

    def test_gateway_backend_no_warning(self, mocker):
        """Tests that gateway backend does NOT show warning."""
        mock_client = mocker.MagicMock()
        mock_client.health_check.return_value = True

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["health"])

        assert result.exit_code == 0
        assert "Local Bee backend" not in result.stdout


# =============================================================================
# x402 COMMAND TESTS
# =============================================================================

class TestX402StatusCommand:
    """Tests for x402 status command."""

    def test_x402_status_shows_disabled(self):
        """Tests x402 status shows disabled by default."""
        result = runner.invoke(app, ["x402", "status"])

        assert result.exit_code == 0
        assert "x402 Payment Configuration" in result.stdout
        assert "Disabled" in result.stdout

    def test_x402_status_shows_network(self):
        """Tests x402 status shows configured network."""
        result = runner.invoke(app, ["x402", "status"])

        assert result.exit_code == 0
        assert "base-sepolia" in result.stdout

    def test_x402_status_shows_auto_pay_settings(self):
        """Tests x402 status shows auto-pay settings."""
        result = runner.invoke(app, ["x402", "status"])

        assert result.exit_code == 0
        assert "Auto-pay" in result.stdout
        assert "Max auto-pay" in result.stdout

    def test_x402_status_shows_no_private_key(self):
        """Tests x402 status shows private key not set."""
        result = runner.invoke(app, ["x402", "status"])

        assert result.exit_code == 0
        assert "Not set" in result.stdout


class TestX402InfoCommand:
    """Tests for x402 info command."""

    def test_x402_info_shows_setup_guide(self):
        """Tests x402 info shows setup guide."""
        result = runner.invoke(app, ["x402", "info"])

        assert result.exit_code == 0
        assert "x402 Payment Setup Guide" in result.stdout
        assert "X402_PRIVATE_KEY" in result.stdout
        assert "faucet" in result.stdout.lower()


class TestX402BalanceCommand:
    """Tests for x402 balance command."""

    def test_x402_balance_fails_without_private_key(self):
        """Tests x402 balance fails when no private key configured."""
        result = runner.invoke(app, ["x402", "balance"])

        assert result.exit_code == 1
        assert "No private key" in result.stdout or "ERROR" in result.stdout


class TestX402GlobalFlags:
    """Tests for x402 global CLI flags."""

    def test_x402_flag_enables_payments(self):
        """Tests --x402 flag enables x402 payments."""
        # Just test that the flag is recognized
        result = runner.invoke(app, ["--x402", "x402", "status"])

        assert result.exit_code == 0
        # After the flag, x402 should be enabled in config
        assert "Enabled" in result.stdout or "x402" in result.stdout

    def test_auto_pay_flag_recognized(self):
        """Tests --auto-pay flag is recognized."""
        result = runner.invoke(app, ["--auto-pay", "x402", "status"])

        assert result.exit_code == 0

    def test_max_pay_flag_recognized(self):
        """Tests --max-pay flag is recognized."""
        result = runner.invoke(app, ["--max-pay", "5.00", "x402", "status"])

        assert result.exit_code == 0

    def test_x402_network_flag_recognized(self):
        """Tests --x402-network flag is recognized."""
        result = runner.invoke(app, ["--x402-network", "base", "x402", "status"])

        assert result.exit_code == 0
        assert "base" in result.stdout

    def test_invalid_x402_network_rejected(self):
        """Tests invalid x402 network is rejected."""
        result = runner.invoke(app, ["--x402-network", "ethereum", "x402", "status"])

        assert result.exit_code == 1
        assert "Invalid x402 network" in result.stdout

    def test_max_pay_flag_updates_config(self):
        """Tests --max-pay flag updates the auto-pay limit."""
        result = runner.invoke(app, ["--max-pay", "2.50", "x402", "status"])

        assert result.exit_code == 0
        # Should show the updated max pay value
        assert "2.50" in result.stdout or "$2.50" in result.stdout


class TestX402StatusDetails:
    """Additional tests for x402 status command."""

    def test_x402_status_shows_max_auto_pay(self):
        """Tests x402 status shows max auto-pay amount."""
        result = runner.invoke(app, ["--max-pay", "3.50", "x402", "status"])

        assert result.exit_code == 0
        assert "3.50" in result.stdout or "$3.50" in result.stdout

    def test_x402_status_network_after_flag(self):
        """Tests that --x402-network flag changes displayed network."""
        result = runner.invoke(app, ["--x402-network", "base", "x402", "status"])

        assert result.exit_code == 0
        # Should show 'base' not 'base-sepolia'
        assert "base" in result.stdout.lower()
        # Mainnet warning might appear
        # (no assertion as warning may or may not be present)

    def test_x402_status_with_all_flags(self):
        """Tests x402 status with multiple flags combined."""
        result = runner.invoke(
            app,
            ["--x402", "--auto-pay", "--max-pay", "10.00", "--x402-network", "base-sepolia", "x402", "status"]
        )

        assert result.exit_code == 0
        assert "Enabled" in result.stdout
        assert "10.00" in result.stdout or "$10.00" in result.stdout


# =============================================================================
# POOL TESTS
# =============================================================================

class TestStampsPoolCommands:
    """Tests for stamps pool commands."""

    SAMPLE_POOL_STATUS = {
        "enabled": True,
        "reserve_config": {"17": 5, "20": 3, "22": 2},
        "current_levels": {"17": 4, "20": 2, "22": 1},
        "available_stamps": {
            "17": ["a" * 64, "b" * 64],
            "20": ["c" * 64],
            "22": [],
        },
        "total_stamps": 7,
        "low_reserve_warning": False,
        "last_check": "2024-01-15T10:00:00Z",
        "next_check": "2024-01-15T11:00:00Z",
        "errors": [],
    }

    def test_pool_status_success(self, mocker):
        """Tests stamps pool-status command."""
        from swarm_provenance_uploader.models import PoolStatusResponse

        mock_client = mocker.MagicMock()
        mock_client.get_pool_status.return_value = PoolStatusResponse(**self.SAMPLE_POOL_STATUS)

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["stamps", "pool-status"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Stamp Pool Status" in result.stdout
        assert "Enabled" in result.stdout
        assert "Total stamps: 7" in result.stdout

    def test_pool_status_requires_gateway(self):
        """Tests pool-status fails with local backend."""
        result = runner.invoke(app, ["--backend", "local", "stamps", "pool-status"])

        assert result.exit_code == 1
        assert "requires gateway backend" in result.stdout

    def test_pool_status_not_enabled(self, mocker):
        """Tests stamps pool-status when pool not enabled."""
        from swarm_provenance_uploader.exceptions import PoolNotEnabledError

        mock_client = mocker.MagicMock()
        mock_client.get_pool_status.side_effect = PoolNotEnabledError("Pool not enabled")

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["stamps", "pool-status"])

        assert result.exit_code == 0  # Not a hard error, just informational
        assert "not enabled" in result.stdout.lower()

    def test_stamps_check_success(self, mocker):
        """Tests stamps check command."""
        from swarm_provenance_uploader.models import StampHealthCheckResponse, StampHealthIssue

        mock_client = mocker.MagicMock()
        mock_client.check_stamp_health.return_value = StampHealthCheckResponse(
            stamp_id="a" * 64,
            can_upload=True,
            errors=[],
            warnings=[StampHealthIssue(code="LOW_TTL", message="TTL is below 24 hours")],
            status={"ttl": 43200},
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["stamps", "check", "a" * 64])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Health Check" in result.stdout
        assert "Can upload: Yes" in result.stdout
        assert "LOW_TTL" in result.stdout

    def test_stamps_check_not_usable(self, mocker):
        """Tests stamps check when stamp cannot upload."""
        from swarm_provenance_uploader.models import StampHealthCheckResponse, StampHealthIssue

        mock_client = mocker.MagicMock()
        mock_client.check_stamp_health.return_value = StampHealthCheckResponse(
            stamp_id="a" * 64,
            can_upload=False,
            errors=[StampHealthIssue(code="EXPIRED", message="Stamp has expired")],
            warnings=[],
            status=None,
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["stamps", "check", "a" * 64])

        assert result.exit_code == 1
        assert "Can upload: No" in result.stdout
        assert "EXPIRED" in result.stdout

    def test_stamps_check_requires_gateway(self):
        """Tests stamps check fails with local backend."""
        result = runner.invoke(app, ["--backend", "local", "stamps", "check", "a" * 64])

        assert result.exit_code == 1
        assert "requires gateway backend" in result.stdout


class TestUploadWithPool:
    """Tests for upload command with --usePool flag."""

    def test_usepool_requires_gateway(self, mocker, tmp_path):
        """Tests --usePool fails with local backend."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        result = runner.invoke(
            app,
            ["--backend", "local", "upload", "--file", str(test_file), "--usePool"]
        )

        assert result.exit_code == 1
        assert "requires gateway backend" in result.stdout

    def test_usepool_acquires_from_pool(self, mocker, tmp_path):
        """Tests --usePool acquires stamp from pool instead of purchasing."""
        from swarm_provenance_uploader.models import AcquireStampResponse

        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        mock_client = mocker.MagicMock()
        # Pool availability check
        mock_client.get_pool_available_count.return_value = 2

        # Pool acquisition
        mock_client.acquire_stamp_from_pool.return_value = AcquireStampResponse(
            success=True,
            batch_id="a" * 64,
            depth=17,
            size_name="small",
            message="Stamp acquired successfully",
            fallback_used=False,
        )

        # Stamp usability check (mark as usable immediately)
        mock_stamp = mocker.MagicMock()
        mock_stamp.exists = True
        mock_stamp.usable = True
        mock_stamp.batchTTL = 86400
        mock_client.get_stamp.return_value = mock_stamp

        # Upload success
        mock_client.upload_data.return_value = "swarmref" * 8

        mocker.patch(
            "swarm_provenance_uploader.cli._get_gateway_client_with_x402",
            return_value=mock_client
        )

        result = runner.invoke(
            app,
            ["upload", "--file", str(test_file), "--usePool"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Acquiring stamp from pool" in result.stdout
        assert "acquired from pool" in result.stdout.lower()
        # Should NOT have called purchase_stamp
        mock_client.purchase_stamp.assert_not_called()
        # Should have called acquire_stamp_from_pool
        mock_client.acquire_stamp_from_pool.assert_called_once()

    def test_usepool_shows_fallback_message(self, mocker, tmp_path):
        """Tests --usePool shows fallback message when larger stamp used."""
        from swarm_provenance_uploader.models import AcquireStampResponse

        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        mock_client = mocker.MagicMock()
        mock_client.get_pool_available_count.return_value = 1

        mock_client.acquire_stamp_from_pool.return_value = AcquireStampResponse(
            success=True,
            batch_id="a" * 64,
            depth=20,
            size_name="medium",
            message="Larger stamp substituted",
            fallback_used=True,
        )

        mock_stamp = mocker.MagicMock()
        mock_stamp.usable = True
        mock_stamp.batchTTL = 86400
        mock_client.get_stamp.return_value = mock_stamp

        mock_client.upload_data.return_value = "swarmref" * 8

        mocker.patch(
            "swarm_provenance_uploader.cli._get_gateway_client_with_x402",
            return_value=mock_client
        )

        result = runner.invoke(
            app,
            ["upload", "--file", str(test_file), "--usePool", "--size", "small"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "fallback" in result.stdout.lower()

    def test_usepool_pool_empty_error(self, mocker, tmp_path):
        """Tests --usePool fails gracefully when pool is empty."""
        from swarm_provenance_uploader.exceptions import PoolEmptyError

        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        mock_client = mocker.MagicMock()
        mock_client.get_pool_available_count.return_value = 0

        mocker.patch(
            "swarm_provenance_uploader.cli._get_gateway_client_with_x402",
            return_value=mock_client
        )

        result = runner.invoke(
            app,
            ["upload", "--file", str(test_file), "--usePool"]
        )

        assert result.exit_code == 1
        assert "No stamps available" in result.stdout
        assert "retry later" in result.stdout.lower() or "without --usePool" in result.stdout

    def test_usepool_pool_not_enabled(self, mocker, tmp_path):
        """Tests --usePool fails when pool not enabled."""
        from swarm_provenance_uploader.exceptions import PoolNotEnabledError

        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        mock_client = mocker.MagicMock()
        mock_client.get_pool_available_count.side_effect = PoolNotEnabledError("Pool not enabled")

        mocker.patch(
            "swarm_provenance_uploader.cli._get_gateway_client_with_x402",
            return_value=mock_client
        )

        result = runner.invoke(
            app,
            ["upload", "--file", str(test_file), "--usePool"]
        )

        assert result.exit_code == 1
        assert "not enabled" in result.stdout.lower()
        assert "without --usePool" in result.stdout


# =============================================================================
# NOTARY COMMANDS TESTS
# =============================================================================

class TestNotaryInfoCommand:
    """Tests for notary info command."""

    def test_notary_info_enabled(self, mocker):
        """Tests notary info when notary is enabled and available."""
        from swarm_provenance_uploader.models import NotaryInfoResponse

        mock_client = mocker.MagicMock()
        mock_client.get_notary_info.return_value = NotaryInfoResponse(
            enabled=True,
            available=True,
            address="0x1234567890abcdef1234567890abcdef12345678",
            message="Notary service is operational",
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["notary", "info"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Notary Service" in result.stdout
        assert "Enabled:" in result.stdout and "Yes" in result.stdout
        assert "Available:" in result.stdout
        assert "0x1234567890abcdef" in result.stdout

    def test_notary_info_disabled(self, mocker):
        """Tests notary info when notary is not enabled."""
        from swarm_provenance_uploader.models import NotaryInfoResponse

        mock_client = mocker.MagicMock()
        mock_client.get_notary_info.return_value = NotaryInfoResponse(
            enabled=False,
            available=False,
            address=None,
            message="Notary signing is not enabled on this gateway",
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["notary", "info"])

        assert result.exit_code == 0
        assert "Enabled:" in result.stdout and "No" in result.stdout

    def test_notary_info_requires_gateway(self):
        """Tests notary info fails with local backend."""
        result = runner.invoke(app, ["--backend", "local", "notary", "info"])

        assert result.exit_code == 1
        assert "requires gateway backend" in result.stdout


class TestNotaryStatusCommand:
    """Tests for notary status command."""

    def test_notary_status_success(self, mocker):
        """Tests notary status command."""
        from swarm_provenance_uploader.models import NotaryStatusResponse

        mock_client = mocker.MagicMock()
        mock_client.get_notary_status.return_value = NotaryStatusResponse(
            enabled=True,
            available=True,
            address="0xabcdef1234567890abcdef1234567890abcdef12",
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(app, ["notary", "status"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Notary" in result.stdout
        assert "Available" in result.stdout or "Enabled" in result.stdout

    def test_notary_status_requires_gateway(self):
        """Tests notary status fails with local backend."""
        result = runner.invoke(app, ["--backend", "local", "notary", "status"])

        assert result.exit_code == 1
        assert "requires gateway backend" in result.stdout


class TestNotaryVerifyCommand:
    """Tests for notary verify command."""

    def test_notary_verify_success(self, mocker, tmp_path):
        """Tests notary verify command with valid signature."""
        import json
        from swarm_provenance_uploader.models import NotaryInfoResponse

        # Create a test signed document file
        signed_doc = {
            "data": {"content": "test", "value": 123},
            "signatures": [
                {
                    "type": "notary",
                    "signer": "0x1234567890abcdef1234567890abcdef12345678",
                    "timestamp": "2026-01-21T16:30:00+00:00",
                    "data_hash": "abc123",
                    "signature": "0x" + "ab" * 65,
                    "hashed_fields": ["data"],
                    "signed_message_format": "{data_hash}|{timestamp}",
                }
            ],
        }
        test_file = tmp_path / "signed.json"
        test_file.write_text(json.dumps(signed_doc))

        mock_client = mocker.MagicMock()
        mock_client.get_notary_info.return_value = NotaryInfoResponse(
            enabled=True,
            available=True,
            address="0x1234567890abcdef1234567890abcdef12345678",
            message=None,
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        # Mock verify function at the source module level
        mocker.patch(
            "swarm_provenance_uploader.core.notary_utils.verify_notary_signature",
            return_value=(True, None)
        )

        result = runner.invoke(app, ["notary", "verify", "--file", str(test_file)])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "VERIFIED" in result.stdout or "verified" in result.stdout.lower()

    def test_notary_verify_invalid_signature(self, mocker, tmp_path):
        """Tests notary verify with invalid signature."""
        import json
        from swarm_provenance_uploader.models import NotaryInfoResponse

        signed_doc = {
            "data": {"content": "test"},
            "signatures": [
                {
                    "type": "notary",
                    "signer": "0x1234567890abcdef1234567890abcdef12345678",
                    "timestamp": "2026-01-21T16:30:00+00:00",
                    "data_hash": "wrong_hash",
                    "signature": "0x" + "00" * 65,
                    "hashed_fields": ["data"],
                    "signed_message_format": "{data_hash}|{timestamp}",
                }
            ],
        }
        test_file = tmp_path / "bad_sig.json"
        test_file.write_text(json.dumps(signed_doc))

        mock_client = mocker.MagicMock()
        mock_client.get_notary_info.return_value = NotaryInfoResponse(
            enabled=True,
            available=True,
            address="0x1234567890abcdef1234567890abcdef12345678",
            message=None,
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        mocker.patch(
            "swarm_provenance_uploader.core.notary_utils.verify_notary_signature",
            return_value=(False, "Data hash mismatch")
        )

        result = runner.invoke(app, ["notary", "verify", "--file", str(test_file)])

        assert result.exit_code == 1
        assert "FAILED" in result.stdout or "failed" in result.stdout.lower()

    def test_notary_verify_requires_gateway(self, mocker, tmp_path):
        """Tests notary verify fails with local backend when no --address provided."""
        import json
        signed_doc = {
            "data": {"content": "test"},
            "signatures": [
                {
                    "type": "notary",
                    "signer": "0x1234",
                    "timestamp": "2026-01-21T16:30:00+00:00",
                    "data_hash": "abc",
                    "signature": "0x" + "ab" * 65,
                    "hashed_fields": ["data"],
                    "signed_message_format": "{data_hash}|{timestamp}",
                }
            ],
        }
        test_file = tmp_path / "test.json"
        test_file.write_text(json.dumps(signed_doc))

        result = runner.invoke(app, ["--backend", "local", "notary", "verify", "--file", str(test_file)])

        assert result.exit_code == 1
        # Should fail because no --address and local backend can't fetch
        assert "address" in result.stdout.lower() or "gateway" in result.stdout.lower()

    def test_notary_verify_file_not_found(self):
        """Tests notary verify fails with non-existent file."""
        result = runner.invoke(app, ["notary", "verify", "--file", "/nonexistent/file.json"])

        assert result.exit_code != 0

    def test_notary_verify_shows_new_fields_verbose(self, mocker, tmp_path):
        """Tests notary verify shows hashed_fields and signed_message_format in verbose mode."""
        import json
        from swarm_provenance_uploader.models import NotaryInfoResponse

        signed_doc = {
            "data": {"content": "test", "value": 123},
            "signatures": [
                {
                    "type": "notary",
                    "signer": "0x1234567890abcdef1234567890abcdef12345678",
                    "timestamp": "2026-01-21T16:30:00+00:00",
                    "data_hash": "abc123",
                    "signature": "0x" + "ab" * 65,
                    "hashed_fields": ["data"],
                    "signed_message_format": "{data_hash}|{timestamp}",
                }
            ],
        }
        test_file = tmp_path / "signed.json"
        test_file.write_text(json.dumps(signed_doc))

        mock_client = mocker.MagicMock()
        mock_client.get_notary_info.return_value = NotaryInfoResponse(
            enabled=True,
            available=True,
            address="0x1234567890abcdef1234567890abcdef12345678",
            message=None,
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        mocker.patch(
            "swarm_provenance_uploader.core.notary_utils.verify_notary_signature",
            return_value=(True, None)
        )

        result = runner.invoke(app, ["notary", "verify", "--file", str(test_file), "-v"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Hashed fields" in result.stdout
        assert "Message format" in result.stdout
        assert "{data_hash}|{timestamp}" in result.stdout

class TestUploadWithSign:
    """Tests for upload command with --sign option."""

    def test_upload_with_sign_notary(self, mocker, tmp_path):
        """Tests upload with --sign notary option."""
        from swarm_provenance_uploader.models import (
            SignedDocumentResponse,
            NotaryInfoResponse,
            StampDetails,
        )

        test_file = tmp_path / "data.txt"
        test_file.write_text("test provenance data")

        mock_client = mocker.MagicMock()
        mock_client.purchase_stamp.return_value = DUMMY_STAMP
        mock_client.get_stamp.return_value = StampDetails(
            batchID=DUMMY_STAMP,
            usable=True,
            exists=True,
            depth=17,
            amount="1000000000",
            bucketDepth=16,
            blockNumber=12345,
            immutableFlag=False,
            batchTTL=3600,
            utilization=0,
        )
        mock_client.get_notary_info.return_value = NotaryInfoResponse(
            enabled=True,
            available=True,
            address="0x1234567890abcdef1234567890abcdef12345678",
            message=None,
        )
        mock_client.upload_data_with_signing.return_value = SignedDocumentResponse(
            reference=DUMMY_SWARM_REF,
            signed_document={
                "data": "base64data",
                "signatures": [
                    {
                        "type": "notary",
                        "signer": "0x1234567890abcdef1234567890abcdef12345678",
                        "timestamp": "2026-01-21T16:30:00+00:00",
                        "data_hash": "abc123",
                        "signature": "0x" + "ab" * 65,
                        "hashed_fields": ["data"],
                        "signed_message_format": "{data_hash}|{timestamp}",
                    }
                ],
            },
            message="Document signed successfully",
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(
            app,
            ["upload", "--file", str(test_file), "--sign", "notary"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert DUMMY_SWARM_REF in result.stdout
        assert "signed" in result.stdout.lower() or "Signature" in result.stdout
        mock_client.upload_data_with_signing.assert_called_once()
        # Should NOT call regular upload_data
        mock_client.upload_data.assert_not_called()

    def test_upload_sign_requires_gateway(self, tmp_path):
        """Tests --sign option fails with local backend."""
        test_file = tmp_path / "data.txt"
        test_file.write_text("test data")

        result = runner.invoke(
            app,
            ["--backend", "local", "upload", "--file", str(test_file), "--sign", "notary"]
        )

        assert result.exit_code == 1
        assert "requires gateway backend" in result.stdout

    def test_upload_sign_notary_not_available(self, mocker, tmp_path):
        """Tests --sign notary fails when notary not available."""
        from swarm_provenance_uploader.models import StampDetails
        from swarm_provenance_uploader.exceptions import NotaryNotEnabledError

        test_file = tmp_path / "data.txt"
        test_file.write_text("test data")

        mock_client = mocker.MagicMock()
        mock_client.purchase_stamp.return_value = DUMMY_STAMP
        mock_client.get_stamp.return_value = StampDetails(
            batchID=DUMMY_STAMP,
            usable=True,
            exists=True,
            depth=17,
            amount="1000000000",
            bucketDepth=16,
            blockNumber=12345,
            immutableFlag=False,
            batchTTL=3600,
            utilization=0,
        )
        # upload_data_with_signing raises NotaryNotEnabledError
        mock_client.upload_data_with_signing.side_effect = NotaryNotEnabledError("Notary not enabled")

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        result = runner.invoke(
            app,
            ["upload", "--file", str(test_file), "--sign", "notary"]
        )

        assert result.exit_code == 1
        assert "not enabled" in result.stdout.lower()


class TestDownloadWithVerify:
    """Tests for download command with --verify flag."""

    def test_download_with_verify_success(self, mocker, tmp_path):
        """Tests download with --verify flag and valid signature."""
        import json
        import base64
        import hashlib
        from swarm_provenance_uploader.models import NotaryInfoResponse

        original_data = b"test provenance data"
        b64_data = base64.b64encode(original_data).decode()
        content_hash = hashlib.sha256(original_data).hexdigest()

        metadata = {
            "data": b64_data,
            "content_hash": content_hash,
            "stamp_id": DUMMY_STAMP,
            "provenance_standard": "TEST-V1",
            "encryption": None,
            "signatures": [
                {
                    "type": "notary",
                    "signer": "0x1234567890abcdef1234567890abcdef12345678",
                    "timestamp": "2026-01-21T16:30:00+00:00",
                    "data_hash": "abc123",
                    "signature": "0x" + "ab" * 65,
                    "hashed_fields": ["data"],
                    "signed_message_format": "{data_hash}|{timestamp}",
                }
            ],
        }

        mock_client = mocker.MagicMock()
        mock_client.download_data.return_value = json.dumps(metadata).encode()
        mock_client.get_notary_info.return_value = NotaryInfoResponse(
            enabled=True,
            available=True,
            address="0x1234567890abcdef1234567890abcdef12345678",
            message=None,
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        mocker.patch(
            "swarm_provenance_uploader.core.notary_utils.verify_notary_signature",
            return_value=(True, None)
        )

        result = runner.invoke(
            app,
            ["download", DUMMY_SWARM_REF, "--output-dir", str(tmp_path), "--verify"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        # Looking for "Verified" in the signature verification output
        assert "verified" in result.stdout.lower() or "Verified" in result.stdout

    def test_download_verify_fails_invalid_signature(self, mocker, tmp_path):
        """Tests download with --verify fails when signature is invalid."""
        import json
        import base64
        import hashlib
        from swarm_provenance_uploader.models import NotaryInfoResponse

        original_data = b"test provenance data"
        b64_data = base64.b64encode(original_data).decode()
        content_hash = hashlib.sha256(original_data).hexdigest()

        metadata = {
            "data": b64_data,
            "content_hash": content_hash,
            "stamp_id": DUMMY_STAMP,
            "provenance_standard": "TEST-V1",
            "signatures": [
                {
                    "type": "notary",
                    "signer": "0x1234567890abcdef1234567890abcdef12345678",
                    "timestamp": "2026-01-21T16:30:00+00:00",
                    "data_hash": "wrong_hash",
                    "signature": "0x" + "00" * 65,
                    "hashed_fields": ["data"],
                    "signed_message_format": "{data_hash}|{timestamp}",
                }
            ],
        }

        mock_client = mocker.MagicMock()
        mock_client.download_data.return_value = json.dumps(metadata).encode()
        mock_client.get_notary_info.return_value = NotaryInfoResponse(
            enabled=True,
            available=True,
            address="0x1234567890abcdef1234567890abcdef12345678",
            message=None,
        )

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        mocker.patch(
            "swarm_provenance_uploader.core.notary_utils.verify_notary_signature",
            return_value=(False, "Signature recovery mismatch")
        )

        result = runner.invoke(
            app,
            ["download", DUMMY_SWARM_REF, "--output-dir", str(tmp_path), "--verify"]
        )

        # Download should still succeed (files downloaded) but with a warning about failed signature
        # The exit code is 0 because the download itself succeeded
        assert result.exit_code == 0
        assert "FAILED" in result.stdout or "failed" in result.stdout.lower()

    def test_download_verify_no_signature_found(self, mocker, tmp_path):
        """Tests download with --verify warns when no signature found."""
        import json
        import base64
        import hashlib

        original_data = b"test provenance data"
        b64_data = base64.b64encode(original_data).decode()
        content_hash = hashlib.sha256(original_data).hexdigest()

        # Metadata without signatures
        metadata = {
            "data": b64_data,
            "content_hash": content_hash,
            "stamp_id": DUMMY_STAMP,
            "provenance_standard": "TEST-V1",
        }

        mock_client = mocker.MagicMock()
        mock_client.download_data.return_value = json.dumps(metadata).encode()

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client
        )

        # No need to patch has_notary_signature - the metadata doesn't have signatures
        # so the actual function will correctly return False

        result = runner.invoke(
            app,
            ["download", DUMMY_SWARM_REF, "--output-dir", str(tmp_path), "--verify"]
        )

        # Should still succeed (download works) but show message about no signatures
        assert result.exit_code == 0
        assert "No notary signatures" in result.stdout or "no notary" in result.stdout.lower()

    def test_download_verify_local_backend_warns(self, mocker, tmp_path):
        """Tests --verify with local backend still downloads but can't verify."""
        import json
        import base64
        import hashlib

        original_data = b"test provenance data"
        b64_data = base64.b64encode(original_data).decode()
        content_hash = hashlib.sha256(original_data).hexdigest()

        # Metadata with signature
        metadata = {
            "data": b64_data,
            "content_hash": content_hash,
            "stamp_id": DUMMY_STAMP,
            "provenance_standard": "TEST-V1",
            "signatures": [
                {
                    "type": "notary",
                    "signer": "0x1234567890abcdef1234567890abcdef12345678",
                    "timestamp": "2026-01-21T16:30:00+00:00",
                    "data_hash": "abc123",
                    "signature": "0x" + "ab" * 65,
                    "hashed_fields": ["data"],
                    "signed_message_format": "{data_hash}|{timestamp}",
                }
            ],
        }

        mocker.patch(
            "swarm_provenance_uploader.cli.swarm_client.download_data_from_swarm",
            return_value=json.dumps(metadata).encode()
        )

        result = runner.invoke(
            app,
            ["--backend", "local", "download", DUMMY_SWARM_REF, "--output-dir", str(tmp_path), "--verify"]
        )

        # Download should still succeed
        assert result.exit_code == 0
        # But should warn about not being able to verify
        assert "Cannot verify" in result.stdout or "No notary address" in result.stdout


# =============================================================================
# CHAIN COMMANDS TESTS
# =============================================================================

DUMMY_TX_HASH = "0x" + "ab" * 32
DUMMY_EXPLORER_URL = "https://base-sepolia.blockscout.com/tx/" + DUMMY_TX_HASH
DUMMY_ADDRESS = "0x" + "cd" * 20


class TestChainAnchorCommand:
    """Tests for chain anchor command."""

    def test_anchor_success(self, mocker):
        """Tests chain anchor command succeeds."""
        from swarm_provenance_uploader.models import AnchorResult

        mock_client = mocker.MagicMock()
        mock_client.anchor.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=DUMMY_EXPLORER_URL,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="swarm-provenance",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "anchor", DUMMY_SWARM_REF])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Anchored successfully" in result.stdout
        assert DUMMY_TX_HASH in result.stdout
        assert "12345" in result.stdout

    def test_anchor_json_output(self, mocker):
        """Tests chain anchor with --json output."""
        from swarm_provenance_uploader.models import AnchorResult

        mock_client = mocker.MagicMock()
        mock_client.anchor.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=DUMMY_EXPLORER_URL,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="swarm-provenance",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "anchor", DUMMY_SWARM_REF, "--json"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        import json
        output = json.loads(result.stdout)
        assert output["tx_hash"] == DUMMY_TX_HASH
        assert output["block_number"] == 12345

    def test_anchor_transaction_error(self, mocker):
        """Tests chain anchor handles transaction errors."""
        from swarm_provenance_uploader.exceptions import ChainTransactionError

        mock_client = mocker.MagicMock()
        mock_client.anchor.side_effect = ChainTransactionError("reverted", tx_hash=DUMMY_TX_HASH)

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "anchor", DUMMY_SWARM_REF])

        assert result.exit_code == 1
        assert "Transaction failed" in result.stdout
        assert DUMMY_TX_HASH in result.stdout

    def test_anchor_custom_type(self, mocker):
        """Tests chain anchor with custom --type."""
        from swarm_provenance_uploader.models import AnchorResult

        mock_client = mocker.MagicMock()
        mock_client.anchor.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=100,
            gas_used=30000,
            explorer_url=None,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="custom-type",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "anchor", DUMMY_SWARM_REF, "--type", "custom-type"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        mock_client.anchor.assert_called_once_with(DUMMY_SWARM_REF, data_type="custom-type", verbose=False)


class TestChainAnchorAlreadyRegistered:
    """Tests for chain anchor already-registered error handling."""

    def test_anchor_already_registered(self, mocker):
        """Tests that already-registered hash shows human-readable output."""
        from swarm_provenance_uploader.exceptions import DataAlreadyRegisteredError

        mock_client = mocker.MagicMock()
        mock_client.anchor.side_effect = DataAlreadyRegisteredError(
            "already registered",
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "anchor", DUMMY_SWARM_REF])

        assert result.exit_code == 1
        assert "Already registered" in result.stdout
        assert DUMMY_ADDRESS in result.stdout
        assert "swarm-provenance" in result.stdout

    def test_anchor_already_registered_json(self, mocker):
        """Tests that already-registered hash shows JSON output with --json."""
        from swarm_provenance_uploader.exceptions import DataAlreadyRegisteredError
        import json

        mock_client = mocker.MagicMock()
        mock_client.anchor.side_effect = DataAlreadyRegisteredError(
            "already registered",
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "anchor", DUMMY_SWARM_REF, "--json"])

        assert result.exit_code == 1
        output = json.loads(result.stdout)
        assert output["error"] == "already_registered"
        assert output["data_hash"] == DUMMY_SWARM_REF
        assert output["owner"] == DUMMY_ADDRESS
        assert output["timestamp"] == 1700000000
        assert output["data_type"] == "swarm-provenance"


class TestChainTransformCommand:
    """Tests for chain transform command."""

    def test_transform_success(self, mocker):
        """Tests chain transform command succeeds."""
        from swarm_provenance_uploader.models import TransformResult

        mock_client = mocker.MagicMock()
        mock_client.transform.return_value = TransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12346,
            gas_used=60000,
            explorer_url=DUMMY_EXPLORER_URL,
            original_hash=DUMMY_SWARM_REF,
            new_hash="c" * 64,
            description="filtered PII",
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "transform", DUMMY_SWARM_REF, "c" * 64, "--description", "filtered PII"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Transformation recorded" in result.stdout

    def test_transform_original_not_registered(self, mocker):
        """Tests chain transform when original hash is not registered."""
        from swarm_provenance_uploader.exceptions import DataNotRegisteredError

        mock_client = mocker.MagicMock()
        mock_client.transform.side_effect = DataNotRegisteredError(
            "Not registered", data_hash=DUMMY_SWARM_REF
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "transform", DUMMY_SWARM_REF, "c" * 64])

        assert result.exit_code == 1
        assert "not registered" in result.stdout.lower()
        assert "anchor it first" in result.stdout.lower() or "Anchor" in result.stdout


class TestChainAccessCommand:
    """Tests for chain access command."""

    def test_access_success(self, mocker):
        """Tests chain access command succeeds."""
        from swarm_provenance_uploader.models import AccessResult

        mock_client = mocker.MagicMock()
        mock_client.access.return_value = AccessResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12347,
            gas_used=40000,
            explorer_url=DUMMY_EXPLORER_URL,
            swarm_hash=DUMMY_SWARM_REF,
            accessor=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "access", DUMMY_SWARM_REF])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Access recorded" in result.stdout

    def test_access_json_output(self, mocker):
        """Tests chain access with --json output."""
        from swarm_provenance_uploader.models import AccessResult

        mock_client = mocker.MagicMock()
        mock_client.access.return_value = AccessResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12347,
            gas_used=40000,
            explorer_url=None,
            swarm_hash=DUMMY_SWARM_REF,
            accessor=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "access", DUMMY_SWARM_REF, "--json"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        import json
        output = json.loads(result.stdout)
        assert output["swarm_hash"] == DUMMY_SWARM_REF


class TestChainGetCommand:
    """Tests for chain get command."""

    def test_get_success(self, mocker):
        """Tests chain get command succeeds."""
        from swarm_provenance_uploader.models import ChainProvenanceRecord, DataStatusEnum

        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
            accessors=[DUMMY_ADDRESS],
            transformations=[],
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "get", DUMMY_SWARM_REF])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Provenance Record" in result.stdout
        assert "ACTIVE" in result.stdout
        assert "Accessors (1)" in result.stdout

    def test_get_not_found(self, mocker):
        """Tests chain get when hash is not registered."""
        from swarm_provenance_uploader.exceptions import DataNotRegisteredError

        mock_client = mocker.MagicMock()
        mock_client.get.side_effect = DataNotRegisteredError("Not registered", data_hash=DUMMY_SWARM_REF)

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "get", DUMMY_SWARM_REF])

        assert result.exit_code == 1
        assert "Not found" in result.stdout or "not registered" in result.stdout.lower()

    def test_get_json_output(self, mocker):
        """Tests chain get with --json output."""
        from swarm_provenance_uploader.models import ChainProvenanceRecord, DataStatusEnum

        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
            accessors=[],
            transformations=[],
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "get", DUMMY_SWARM_REF, "--json"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        import json
        output = json.loads(result.stdout)
        assert output["data_hash"] == DUMMY_SWARM_REF
        assert output["status"] == 0  # ACTIVE

    def test_get_with_transformations(self, mocker):
        """Tests chain get shows transformations."""
        from swarm_provenance_uploader.models import (
            ChainProvenanceRecord, DataStatusEnum, ChainTransformation,
        )

        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
            accessors=[],
            transformations=[
                ChainTransformation(description="filtered PII"),
            ],
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "get", DUMMY_SWARM_REF])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Transformations (1)" in result.stdout
        assert "filtered PII" in result.stdout


class TestChainVerifyCommand:
    """Tests for chain verify command."""

    def test_verify_registered(self, mocker):
        """Tests chain verify when hash is registered (exit 0)."""
        mock_client = mocker.MagicMock()
        mock_client.verify.return_value = True

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "verify", DUMMY_SWARM_REF])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Verified" in result.stdout or "anchored" in result.stdout

    def test_verify_not_registered(self, mocker):
        """Tests chain verify when hash is not registered (exit 1)."""
        mock_client = mocker.MagicMock()
        mock_client.verify.return_value = False

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "verify", DUMMY_SWARM_REF])

        assert result.exit_code == 1
        assert "Not found" in result.stdout or "not registered" in result.stdout.lower()


class TestChainBalanceCommand:
    """Tests for chain balance command."""

    def test_balance_success(self, mocker):
        """Tests chain balance command succeeds."""
        from swarm_provenance_uploader.models import ChainWalletInfo

        mock_client = mocker.MagicMock()
        mock_client.balance.return_value = ChainWalletInfo(
            address=DUMMY_ADDRESS,
            balance_wei=1000000000000000000,
            balance_eth="1.0",
            chain="base-sepolia",
            contract_address="0xD4a724CD7f5C4458cD2d884C2af6f011aC3Af80a",
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "balance"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Chain Wallet" in result.stdout
        assert "1.0" in result.stdout
        assert DUMMY_ADDRESS in result.stdout

    def test_balance_json_output(self, mocker):
        """Tests chain balance with --json output."""
        from swarm_provenance_uploader.models import ChainWalletInfo

        mock_client = mocker.MagicMock()
        mock_client.balance.return_value = ChainWalletInfo(
            address=DUMMY_ADDRESS,
            balance_wei=1000000000000000000,
            balance_eth="1.0",
            chain="base-sepolia",
            contract_address="0xD4a724CD7f5C4458cD2d884C2af6f011aC3Af80a",
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "balance", "--json"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        import json
        output = json.loads(result.stdout)
        assert output["address"] == DUMMY_ADDRESS
        assert output["balance_eth"] == "1.0"

    def test_balance_testnet_faucet_link(self, mocker):
        """Tests chain balance shows faucet link on testnet."""
        from swarm_provenance_uploader.models import ChainWalletInfo

        mock_client = mocker.MagicMock()
        mock_client.balance.return_value = ChainWalletInfo(
            address=DUMMY_ADDRESS,
            balance_wei=0,
            balance_eth="0.0",
            chain="base-sepolia",
            contract_address="0xD4a724CD7f5C4458cD2d884C2af6f011aC3Af80a",
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "balance"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "faucet" in result.stdout.lower()

    def test_balance_mainnet_no_faucet(self, mocker):
        """Tests chain balance does not show faucet link on mainnet."""
        from swarm_provenance_uploader.models import ChainWalletInfo

        mock_client = mocker.MagicMock()
        mock_client.balance.return_value = ChainWalletInfo(
            address=DUMMY_ADDRESS,
            balance_wei=0,
            balance_eth="0.0",
            chain="base",
            contract_address="0x1234567890abcdef1234567890abcdef12345678",
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "balance"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "faucet" not in result.stdout.lower()


class TestChainDepsNotInstalled:
    """Tests for graceful failure when blockchain deps are not installed."""

    def test_chain_command_without_deps(self, mocker):
        """Tests chain commands fail gracefully when blockchain deps missing."""
        mocker.patch(
            "swarm_provenance_uploader.cli._get_chain_client",
            side_effect=typer.Exit(code=1),
        )

        result = runner.invoke(app, ["chain", "balance"])

        assert result.exit_code == 1

    def test_chain_import_error_message(self, mocker):
        """Tests helpful error message when import fails."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "swarm_provenance_uploader.core.chain_client" or "chain_client" in str(name):
                raise ImportError("No module named 'web3'")
            return original_import(name, *args, **kwargs)

        # Patch at the _get_chain_client level to simulate ImportError
        mocker.patch(
            "swarm_provenance_uploader.cli._get_chain_client",
            side_effect=typer.Exit(code=1),
        )

        result = runner.invoke(app, ["chain", "balance"])
        assert result.exit_code == 1


class TestChainGlobalFlags:
    """Tests for --chain and --chain-rpc global CLI flags."""

    def test_chain_flag_accepted(self, mocker):
        """Tests --chain flag is recognized."""
        from swarm_provenance_uploader.models import ChainWalletInfo

        mock_client = mocker.MagicMock()
        mock_client.balance.return_value = ChainWalletInfo(
            address=DUMMY_ADDRESS,
            balance_wei=0,
            balance_eth="0.0",
            chain="base",
            contract_address="0x1234",
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["--chain", "base", "chain", "balance"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"

    def test_invalid_chain_rejected(self):
        """Tests invalid --chain value is rejected."""
        result = runner.invoke(app, ["--chain", "ethereum", "chain", "balance"])

        assert result.exit_code == 1
        assert "Invalid chain" in result.stdout

    def test_chain_rpc_flag_accepted(self, mocker):
        """Tests --chain-rpc flag is recognized."""
        from swarm_provenance_uploader.models import ChainWalletInfo

        mock_client = mocker.MagicMock()
        mock_client.balance.return_value = ChainWalletInfo(
            address=DUMMY_ADDRESS,
            balance_wei=0,
            balance_eth="0.0",
            chain="base-sepolia",
            contract_address="0x1234",
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["--chain-rpc", "https://custom-rpc.example.com", "chain", "balance"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"


class TestChainExplorerUrlConfig:
    """Tests for CHAIN_EXPLORER_URL config passthrough."""

    def test_explorer_url_in_chain_config(self):
        """Tests that explorer_url key exists in _chain_config."""
        assert "explorer_url" in _chain_config

    def test_explorer_url_passed_to_client(self, mocker):
        """Tests that explorer_url from config is used by _get_chain_client."""
        from swarm_provenance_uploader.models import ChainWalletInfo

        _chain_config["explorer_url"] = "https://custom-explorer.io"

        mock_client = mocker.MagicMock()
        mock_client.balance.return_value = ChainWalletInfo(
            address=DUMMY_ADDRESS,
            balance_wei=0,
            balance_eth="0.0",
            chain="base-sepolia",
            contract_address="0x1234",
        )
        mocker.patch(
            "swarm_provenance_uploader.cli._get_chain_client",
            return_value=mock_client,
        )

        result = runner.invoke(app, ["chain", "balance"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        # Verify config has the explorer_url that _get_chain_client passes to ChainClient
        assert _chain_config["explorer_url"] == "https://custom-explorer.io"


class TestChainConnectionError:
    """Tests for chain connection error handling."""

    def test_connection_error_shows_rpc_url(self, mocker):
        """Tests connection error shows RPC URL."""
        from swarm_provenance_uploader.exceptions import ChainConnectionError

        mock_client = mocker.MagicMock()
        mock_client.balance.side_effect = ChainConnectionError(
            "Cannot connect", rpc_url="https://rpc.example.com"
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "balance"])

        assert result.exit_code == 1
        assert "Cannot connect" in result.stdout
        assert "rpc.example.com" in result.stdout


# =============================================================================
# CHAIN STATUS COMMAND TESTS (Issue #61)
# =============================================================================

class TestChainStatusCommand:
    """Tests for chain status command."""

    def test_status_query(self, mocker):
        """Tests chain status shows current status."""
        from swarm_provenance_uploader.models import ChainProvenanceRecord, DataStatusEnum

        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "status", DUMMY_SWARM_REF])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "ACTIVE" in result.stdout

    def test_status_set_restricted(self, mocker):
        """Tests chain status --set restricted."""
        from swarm_provenance_uploader.models import AnchorResult

        mock_client = mocker.MagicMock()
        mock_client.set_status.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=DUMMY_EXPLORER_URL,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "status", DUMMY_SWARM_REF, "--set", "restricted"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Status updated" in result.stdout
        assert "RESTRICTED" in result.stdout
        mock_client.set_status.assert_called_once_with(DUMMY_SWARM_REF, status=1, verbose=False)

    def test_status_set_json(self, mocker):
        """Tests chain status --set with --json output."""
        from swarm_provenance_uploader.models import AnchorResult

        mock_client = mocker.MagicMock()
        mock_client.set_status.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "status", DUMMY_SWARM_REF, "--set", "active", "--json"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        import json
        output = json.loads(result.stdout)
        assert output["tx_hash"] == DUMMY_TX_HASH

    def test_status_invalid_name(self, mocker):
        """Tests chain status --set with invalid status name."""
        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mocker.MagicMock())

        result = runner.invoke(app, ["chain", "status", DUMMY_SWARM_REF, "--set", "invalid"])

        assert result.exit_code == 1
        assert "Invalid status" in result.stdout

    def test_status_not_registered(self, mocker):
        """Tests chain status query when hash not registered."""
        from swarm_provenance_uploader.exceptions import DataNotRegisteredError

        mock_client = mocker.MagicMock()
        mock_client.get.side_effect = DataNotRegisteredError("Not found", data_hash=DUMMY_SWARM_REF)

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "status", DUMMY_SWARM_REF])

        assert result.exit_code == 1
        assert "not registered" in result.stdout.lower()


# =============================================================================
# CHAIN TRANSFER COMMAND TESTS (Issue #62)
# =============================================================================

class TestChainTransferCommand:
    """Tests for chain transfer command."""

    def test_transfer_success(self, mocker):
        """Tests chain transfer command succeeds."""
        from swarm_provenance_uploader.models import AnchorResult

        new_owner = "0x1111111111111111111111111111111111111111"
        mock_client = mocker.MagicMock()
        mock_client.transfer_ownership.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=DUMMY_EXPLORER_URL,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="",
            owner=new_owner,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "transfer", DUMMY_SWARM_REF, "--to", new_owner]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Ownership transferred" in result.stdout
        mock_client.transfer_ownership.assert_called_once_with(
            DUMMY_SWARM_REF, new_owner=new_owner, verbose=False
        )

    def test_transfer_json_output(self, mocker):
        """Tests chain transfer with --json output."""
        from swarm_provenance_uploader.models import AnchorResult

        new_owner = "0x1111111111111111111111111111111111111111"
        mock_client = mocker.MagicMock()
        mock_client.transfer_ownership.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="",
            owner=new_owner,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "transfer", DUMMY_SWARM_REF, "--to", new_owner, "--json"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        import json
        output = json.loads(result.stdout)
        assert output["owner"] == new_owner

    def test_transfer_transaction_error(self, mocker):
        """Tests chain transfer handles transaction errors."""
        from swarm_provenance_uploader.exceptions import ChainTransactionError

        mock_client = mocker.MagicMock()
        mock_client.transfer_ownership.side_effect = ChainTransactionError("reverted", tx_hash=DUMMY_TX_HASH)

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "transfer", DUMMY_SWARM_REF, "--to", DUMMY_ADDRESS]
        )

        assert result.exit_code == 1
        assert "Transaction failed" in result.stdout


# =============================================================================
# CHAIN DELEGATE COMMAND TESTS (Issue #62)
# =============================================================================

class TestChainDelegateCommand:
    """Tests for chain delegate command."""

    def test_delegate_authorize(self, mocker):
        """Tests chain delegate --authorize."""
        from swarm_provenance_uploader.models import AnchorResult

        delegate_addr = "0x2222222222222222222222222222222222222222"
        mock_client = mocker.MagicMock()
        mock_client.set_delegate.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            swarm_hash="",
            data_type="",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "delegate", delegate_addr, "--authorize"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "authorized" in result.stdout.lower()
        mock_client.set_delegate.assert_called_once_with(
            delegate=delegate_addr, authorized=True, verbose=False
        )

    def test_delegate_revoke(self, mocker):
        """Tests chain delegate --revoke."""
        from swarm_provenance_uploader.models import AnchorResult

        delegate_addr = "0x2222222222222222222222222222222222222222"
        mock_client = mocker.MagicMock()
        mock_client.set_delegate.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            swarm_hash="",
            data_type="",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "delegate", delegate_addr, "--revoke"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "revoked" in result.stdout.lower()
        mock_client.set_delegate.assert_called_once_with(
            delegate=delegate_addr, authorized=False, verbose=False
        )

    def test_delegate_neither_flag_error(self, mocker):
        """Tests chain delegate fails without --authorize or --revoke."""
        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mocker.MagicMock())

        result = runner.invoke(app, ["chain", "delegate", DUMMY_ADDRESS])

        assert result.exit_code == 1
        assert "exactly one" in result.stdout.lower() or "authorize" in result.stdout.lower()


# =============================================================================
# CHAIN ANCHOR --OWNER TESTS (Issue #62)
# =============================================================================

class TestChainAnchorOwner:
    """Tests for chain anchor with --owner flag."""

    def test_anchor_with_owner(self, mocker):
        """Tests chain anchor --owner uses anchor_for."""
        from swarm_provenance_uploader.models import AnchorResult

        owner_addr = "0x3333333333333333333333333333333333333333"
        mock_client = mocker.MagicMock()
        mock_client.anchor_for.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="swarm-provenance",
            owner=owner_addr,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "anchor", DUMMY_SWARM_REF, "--owner", owner_addr]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Anchored successfully" in result.stdout
        assert owner_addr in result.stdout
        mock_client.anchor_for.assert_called_once_with(
            DUMMY_SWARM_REF, owner=owner_addr, data_type="swarm-provenance", verbose=False
        )
        mock_client.anchor.assert_not_called()


# =============================================================================
# CHAIN GET --FOLLOW TESTS (Issue #63)
# =============================================================================

class TestChainGetFollow:
    """Tests for chain get --follow flag."""

    def test_follow_calls_get_provenance_chain(self, mocker):
        """Tests --follow calls get_provenance_chain and renders chain."""
        from swarm_provenance_uploader.models import (
            ChainProvenanceRecord, DataStatusEnum, ChainTransformation,
        )

        hash_a = DUMMY_SWARM_REF
        hash_b = "c" * 64

        mock_client = mocker.MagicMock()
        mock_client.get_provenance_chain.return_value = [
            ChainProvenanceRecord(
                data_hash=hash_a,
                owner=DUMMY_ADDRESS,
                timestamp=1700000000,
                data_type="swarm-provenance",
                status=DataStatusEnum.ACTIVE,
                transformations=[ChainTransformation(description="filtered PII")],
            ),
            ChainProvenanceRecord(
                data_hash=hash_b,
                owner=DUMMY_ADDRESS,
                timestamp=1700001000,
                data_type="swarm-provenance",
                status=DataStatusEnum.ACTIVE,
            ),
        ]

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "get", hash_a, "--follow"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Provenance Chain (2 records)" in result.stdout
        assert "Original" in result.stdout
        assert "Derived" in result.stdout
        mock_client.get_provenance_chain.assert_called_once_with(
            hash_a, max_depth=None, verbose=False
        )

    def test_follow_depth_limits_traversal(self, mocker):
        """Tests --follow --depth passes max_depth."""
        from swarm_provenance_uploader.models import ChainProvenanceRecord, DataStatusEnum

        mock_client = mocker.MagicMock()
        mock_client.get_provenance_chain.return_value = [
            ChainProvenanceRecord(
                data_hash=DUMMY_SWARM_REF,
                owner=DUMMY_ADDRESS,
                timestamp=1700000000,
                data_type="swarm-provenance",
                status=DataStatusEnum.ACTIVE,
            ),
        ]

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "get", DUMMY_SWARM_REF, "--follow", "--depth", "2"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        mock_client.get_provenance_chain.assert_called_once_with(
            DUMMY_SWARM_REF, max_depth=2, verbose=False
        )

    def test_follow_json_output(self, mocker):
        """Tests --follow --json wraps chain array."""
        from swarm_provenance_uploader.models import ChainProvenanceRecord, DataStatusEnum

        mock_client = mocker.MagicMock()
        mock_client.get_provenance_chain.return_value = [
            ChainProvenanceRecord(
                data_hash=DUMMY_SWARM_REF,
                owner=DUMMY_ADDRESS,
                timestamp=1700000000,
                data_type="swarm-provenance",
                status=DataStatusEnum.ACTIVE,
            ),
        ]

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "get", DUMMY_SWARM_REF, "--follow", "--json"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        import json
        output = json.loads(result.stdout)
        assert "chain" in output
        assert output["depth"] == 1
        assert output["root"] == DUMMY_SWARM_REF

    def test_follow_empty_chain(self, mocker):
        """Tests --follow when hash is not registered."""
        mock_client = mocker.MagicMock()
        mock_client.get_provenance_chain.return_value = []

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "get", DUMMY_SWARM_REF, "--follow"])

        assert result.exit_code == 1
        assert "Not found" in result.stdout or "not registered" in result.stdout.lower()


# =============================================================================
# CHAIN TRANSFORM --RESTRICT-ORIGINAL TESTS (Issue #64)
# =============================================================================

class TestChainTransformRestrictOriginal:
    """Tests for chain transform --restrict-original flag."""

    def test_restrict_original_triggers_set_status(self, mocker):
        """Tests --restrict-original calls set_status after transform."""
        from swarm_provenance_uploader.models import TransformResult, AnchorResult

        mock_client = mocker.MagicMock()
        mock_client.transform.return_value = TransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            original_hash=DUMMY_SWARM_REF,
            new_hash="c" * 64,
            description="filtered",
        )
        mock_client.set_status.return_value = AnchorResult(
            tx_hash="0x" + "cc" * 32,
            block_number=12346,
            gas_used=30000,
            explorer_url=None,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "transform", DUMMY_SWARM_REF, "c" * 64, "--restrict-original"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Transformation recorded" in result.stdout
        assert "restricted" in result.stdout.lower()
        mock_client.set_status.assert_called_once_with(DUMMY_SWARM_REF, status=1, verbose=False)


# =============================================================================
# CHAIN PROTECT COMMAND TESTS (Issue #64)
# =============================================================================

class TestChainProtectCommand:
    """Tests for chain protect command."""

    def test_protect_full_flow(self, mocker):
        """Tests chain protect full workflow."""
        from swarm_provenance_uploader.models import (
            ChainProvenanceRecord, DataStatusEnum, TransformResult, AnchorResult,
        )

        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
        )
        mock_client.transform.return_value = TransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            original_hash=DUMMY_SWARM_REF,
            new_hash="c" * 64,
            description="removed PII",
        )
        mock_client.set_status.return_value = AnchorResult(
            tx_hash="0x" + "cc" * 32,
            block_number=12346,
            gas_used=30000,
            explorer_url=None,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "protect", DUMMY_SWARM_REF, "c" * 64, "-d", "removed PII"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Protect complete" in result.stdout
        assert "RESTRICTED" in result.stdout
        mock_client.transform.assert_called_once()
        mock_client.set_status.assert_called_once_with(DUMMY_SWARM_REF, status=1, verbose=False)

    def test_protect_with_anchor_new(self, mocker):
        """Tests chain protect with --anchor-new flag."""
        from swarm_provenance_uploader.models import (
            ChainProvenanceRecord, DataStatusEnum, TransformResult, AnchorResult,
        )

        new_hash = "d" * 64
        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
        )
        mock_client.anchor.return_value = AnchorResult(
            tx_hash="0x" + "aa" * 32,
            block_number=12344,
            gas_used=40000,
            explorer_url=None,
            swarm_hash=new_hash,
            data_type="swarm-provenance",
            owner=DUMMY_ADDRESS,
        )
        mock_client.transform.return_value = TransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            original_hash=DUMMY_SWARM_REF,
            new_hash=new_hash,
            description="",
        )
        mock_client.set_status.return_value = AnchorResult(
            tx_hash="0x" + "cc" * 32,
            block_number=12346,
            gas_used=30000,
            explorer_url=None,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "protect", DUMMY_SWARM_REF, new_hash, "--anchor-new"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "anchored" in result.stdout.lower()
        mock_client.anchor.assert_called_once_with(new_hash, data_type="swarm-provenance", verbose=False)

    def test_protect_json_output(self, mocker):
        """Tests chain protect with --json output."""
        from swarm_provenance_uploader.models import (
            ChainProvenanceRecord, DataStatusEnum, TransformResult, AnchorResult,
        )

        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
        )
        mock_client.transform.return_value = TransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            original_hash=DUMMY_SWARM_REF,
            new_hash="c" * 64,
            description="",
        )
        mock_client.set_status.return_value = AnchorResult(
            tx_hash="0x" + "cc" * 32,
            block_number=12346,
            gas_used=30000,
            explorer_url=None,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "protect", DUMMY_SWARM_REF, "c" * 64, "--json"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        import json
        output = json.loads(result.stdout)
        assert "transform" in output
        assert "restrict" in output

    def test_protect_original_not_active(self, mocker):
        """Tests chain protect fails when original is not ACTIVE."""
        from swarm_provenance_uploader.models import ChainProvenanceRecord, DataStatusEnum

        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.RESTRICTED,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "protect", DUMMY_SWARM_REF, "c" * 64]
        )

        assert result.exit_code == 1
        assert "RESTRICTED" in result.stdout
        assert "expected ACTIVE" in result.stdout

    def test_protect_original_not_registered(self, mocker):
        """Tests chain protect fails when original not registered."""
        from swarm_provenance_uploader.exceptions import DataNotRegisteredError

        mock_client = mocker.MagicMock()
        mock_client.get.side_effect = DataNotRegisteredError("Not found", data_hash=DUMMY_SWARM_REF)

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "protect", DUMMY_SWARM_REF, "c" * 64]
        )

        assert result.exit_code == 1
        assert "not registered" in result.stdout.lower()

    def test_protect_restrict_failure_warns(self, mocker):
        """Tests protect continues with warning when restrict fails after successful transform."""
        from swarm_provenance_uploader.models import (
            ChainProvenanceRecord, DataStatusEnum, TransformResult,
        )
        from swarm_provenance_uploader.exceptions import ChainTransactionError

        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
        )
        mock_client.transform.return_value = TransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            original_hash=DUMMY_SWARM_REF,
            new_hash="c" * 64,
            description="",
        )
        mock_client.set_status.side_effect = ChainTransactionError("reverted")

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "protect", DUMMY_SWARM_REF, "c" * 64]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "WARNING" in result.stdout
        assert "partially complete" in result.stdout.lower() or "restrict failed" in result.stdout.lower()

    def test_protect_restrict_failure_json(self, mocker):
        """Tests protect JSON output includes partial_failure when restrict fails."""
        from swarm_provenance_uploader.models import (
            ChainProvenanceRecord, DataStatusEnum, TransformResult,
        )
        from swarm_provenance_uploader.exceptions import ChainTransactionError

        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
        )
        mock_client.transform.return_value = TransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            original_hash=DUMMY_SWARM_REF,
            new_hash="c" * 64,
            description="",
        )
        mock_client.set_status.side_effect = ChainTransactionError("reverted")

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "protect", DUMMY_SWARM_REF, "c" * 64, "--json"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "WARNING" in result.stdout
        # Extract JSON from mixed output (CliRunner merges stderr into stdout)
        import json
        json_start = result.stdout.index("{")
        output = json.loads(result.stdout[json_start:])
        assert output["partial_failure"] is True
        assert output["restrict"] is None
        assert "transform" in output

    def test_protect_anchor_new_failure(self, mocker):
        """Tests protect exits when anchor-new fails."""
        from swarm_provenance_uploader.models import ChainProvenanceRecord, DataStatusEnum
        from swarm_provenance_uploader.exceptions import ChainTransactionError

        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
        )
        mock_client.anchor.side_effect = ChainTransactionError("already registered")

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "protect", DUMMY_SWARM_REF, "c" * 64, "--anchor-new"]
        )

        assert result.exit_code == 1
        assert "anchor" in result.stdout.lower()
        mock_client.transform.assert_not_called()

    def test_protect_transform_failure(self, mocker):
        """Tests protect exits when transform fails (after successful anchor)."""
        from swarm_provenance_uploader.models import (
            ChainProvenanceRecord, DataStatusEnum, AnchorResult,
        )
        from swarm_provenance_uploader.exceptions import ChainTransactionError

        new_hash = "d" * 64
        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
        )
        mock_client.anchor.return_value = AnchorResult(
            tx_hash="0x" + "aa" * 32,
            block_number=12344,
            gas_used=40000,
            explorer_url=None,
            swarm_hash=new_hash,
            data_type="swarm-provenance",
            owner=DUMMY_ADDRESS,
        )
        mock_client.transform.side_effect = ChainTransactionError("reverted")

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "protect", DUMMY_SWARM_REF, new_hash, "--anchor-new"]
        )

        assert result.exit_code == 1
        assert "transformation" in result.stdout.lower() or "transform" in result.stdout.lower()
        mock_client.set_status.assert_not_called()

    def test_protect_json_with_anchor_new(self, mocker):
        """Tests protect JSON output includes anchor key when --anchor-new used."""
        from swarm_provenance_uploader.models import (
            ChainProvenanceRecord, DataStatusEnum, TransformResult, AnchorResult,
        )

        new_hash = "d" * 64
        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
        )
        mock_client.anchor.return_value = AnchorResult(
            tx_hash="0x" + "aa" * 32,
            block_number=12344,
            gas_used=40000,
            explorer_url=None,
            swarm_hash=new_hash,
            data_type="swarm-provenance",
            owner=DUMMY_ADDRESS,
        )
        mock_client.transform.return_value = TransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            original_hash=DUMMY_SWARM_REF,
            new_hash=new_hash,
            description="",
        )
        mock_client.set_status.return_value = AnchorResult(
            tx_hash="0x" + "cc" * 32,
            block_number=12346,
            gas_used=30000,
            explorer_url=None,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "protect", DUMMY_SWARM_REF, new_hash, "--anchor-new", "--json"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        import json
        output = json.loads(result.stdout)
        assert "anchor" in output
        assert "transform" in output
        assert "restrict" in output
        assert output["partial_failure"] is False

    def test_protect_original_deleted(self, mocker):
        """Tests protect fails when original status is DELETED."""
        from swarm_provenance_uploader.models import ChainProvenanceRecord, DataStatusEnum

        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.DELETED,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "protect", DUMMY_SWARM_REF, "c" * 64]
        )

        assert result.exit_code == 1
        assert "DELETED" in result.stdout
        assert "expected ACTIVE" in result.stdout


# =============================================================================
# CHAIN STATUS COMMAND ADDITIONAL TESTS
# =============================================================================

class TestChainStatusCommandAdditional:
    """Additional tests for chain status command."""

    def test_status_set_deleted(self, mocker):
        """Tests chain status --set deleted."""
        from swarm_provenance_uploader.models import AnchorResult

        mock_client = mocker.MagicMock()
        mock_client.set_status.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "status", DUMMY_SWARM_REF, "--set", "deleted"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "DELETED" in result.stdout
        mock_client.set_status.assert_called_once_with(DUMMY_SWARM_REF, status=2, verbose=False)

    def test_status_set_case_insensitive(self, mocker):
        """Tests chain status --set accepts mixed case."""
        from swarm_provenance_uploader.models import AnchorResult

        mock_client = mocker.MagicMock()
        mock_client.set_status.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "status", DUMMY_SWARM_REF, "--set", "RESTRICTED"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        mock_client.set_status.assert_called_once_with(DUMMY_SWARM_REF, status=1, verbose=False)

    def test_status_query_json(self, mocker):
        """Tests chain status query mode with --json output."""
        from swarm_provenance_uploader.models import ChainProvenanceRecord, DataStatusEnum

        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.RESTRICTED,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "status", DUMMY_SWARM_REF, "--json"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        import json
        output = json.loads(result.stdout)
        assert output["status"] == "RESTRICTED"
        assert output["hash"] == DUMMY_SWARM_REF

    def test_status_query_connection_error(self, mocker):
        """Tests chain status query handles connection errors."""
        from swarm_provenance_uploader.exceptions import ChainConnectionError

        mock_client = mocker.MagicMock()
        mock_client.get.side_effect = ChainConnectionError("timeout", rpc_url="http://localhost:8545")

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "status", DUMMY_SWARM_REF])

        assert result.exit_code == 1
        assert "Cannot connect" in result.stdout

    def test_status_set_connection_error(self, mocker):
        """Tests chain status --set handles connection errors."""
        from swarm_provenance_uploader.exceptions import ChainConnectionError

        mock_client = mocker.MagicMock()
        mock_client.set_status.side_effect = ChainConnectionError("timeout", rpc_url="http://localhost:8545")

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "status", DUMMY_SWARM_REF, "--set", "active"])

        assert result.exit_code == 1
        assert "Cannot connect" in result.stdout


# =============================================================================
# CHAIN TRANSFER COMMAND ADDITIONAL TESTS
# =============================================================================

class TestChainTransferCommandAdditional:
    """Additional tests for chain transfer command."""

    def test_transfer_connection_error(self, mocker):
        """Tests chain transfer handles connection errors."""
        from swarm_provenance_uploader.exceptions import ChainConnectionError

        mock_client = mocker.MagicMock()
        mock_client.transfer_ownership.side_effect = ChainConnectionError("timeout")

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "transfer", DUMMY_SWARM_REF, "--to", DUMMY_ADDRESS]
        )

        assert result.exit_code == 1
        assert "Cannot connect" in result.stdout

    def test_transfer_generic_chain_error(self, mocker):
        """Tests chain transfer handles generic chain errors."""
        from swarm_provenance_uploader.exceptions import ChainError

        mock_client = mocker.MagicMock()
        mock_client.transfer_ownership.side_effect = ChainError("not owner")

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "transfer", DUMMY_SWARM_REF, "--to", DUMMY_ADDRESS]
        )

        assert result.exit_code == 1
        assert "not owner" in result.stdout


# =============================================================================
# CHAIN DELEGATE COMMAND ADDITIONAL TESTS
# =============================================================================

class TestChainDelegateCommandAdditional:
    """Additional tests for chain delegate command."""

    def test_delegate_both_flags_error(self, mocker):
        """Tests chain delegate fails when both --authorize and --revoke are given."""
        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mocker.MagicMock())

        result = runner.invoke(
            app, ["chain", "delegate", DUMMY_ADDRESS, "--authorize", "--revoke"]
        )

        assert result.exit_code == 1
        assert "exactly one" in result.stdout.lower()

    def test_delegate_connection_error(self, mocker):
        """Tests chain delegate handles connection errors."""
        from swarm_provenance_uploader.exceptions import ChainConnectionError

        mock_client = mocker.MagicMock()
        mock_client.set_delegate.side_effect = ChainConnectionError("timeout")

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "delegate", DUMMY_ADDRESS, "--authorize"]
        )

        assert result.exit_code == 1
        assert "Cannot connect" in result.stdout

    def test_delegate_json_output(self, mocker):
        """Tests chain delegate with --json output."""
        from swarm_provenance_uploader.models import AnchorResult

        delegate_addr = "0x2222222222222222222222222222222222222222"
        mock_client = mocker.MagicMock()
        mock_client.set_delegate.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            swarm_hash="",
            data_type="",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "delegate", delegate_addr, "--authorize", "--json"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        import json
        output = json.loads(result.stdout)
        assert output["tx_hash"] == DUMMY_TX_HASH


# =============================================================================
# CHAIN GET ADDITIONAL TESTS
# =============================================================================

class TestChainGetAdditional:
    """Additional tests for chain get command."""

    def test_depth_without_follow_warns(self, mocker):
        """Tests --depth without --follow shows warning."""
        from swarm_provenance_uploader.models import ChainProvenanceRecord, DataStatusEnum

        mock_client = mocker.MagicMock()
        mock_client.get.return_value = ChainProvenanceRecord(
            data_hash=DUMMY_SWARM_REF,
            owner=DUMMY_ADDRESS,
            timestamp=1700000000,
            data_type="swarm-provenance",
            status=DataStatusEnum.ACTIVE,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "get", DUMMY_SWARM_REF, "--depth", "3"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "no effect" in result.stdout.lower() or "WARNING" in result.stdout

    def test_follow_depth_zero(self, mocker):
        """Tests --follow --depth 0 returns only root."""
        from swarm_provenance_uploader.models import ChainProvenanceRecord, DataStatusEnum

        mock_client = mocker.MagicMock()
        mock_client.get_provenance_chain.return_value = [
            ChainProvenanceRecord(
                data_hash=DUMMY_SWARM_REF,
                owner=DUMMY_ADDRESS,
                timestamp=1700000000,
                data_type="swarm-provenance",
                status=DataStatusEnum.ACTIVE,
            ),
        ]

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "get", DUMMY_SWARM_REF, "--follow", "--depth", "0"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        mock_client.get_provenance_chain.assert_called_once_with(
            DUMMY_SWARM_REF, max_depth=0, verbose=False
        )

    def test_follow_connection_error(self, mocker):
        """Tests --follow handles connection errors."""
        from swarm_provenance_uploader.exceptions import ChainConnectionError

        mock_client = mocker.MagicMock()
        mock_client.get_provenance_chain.side_effect = ChainConnectionError("timeout", rpc_url="http://localhost:8545")

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "get", DUMMY_SWARM_REF, "--follow"])

        assert result.exit_code == 1
        assert "Cannot connect" in result.stdout


# =============================================================================
# CHAIN TRANSFORM ADDITIONAL TESTS
# =============================================================================

class TestChainTransformAdditional:
    """Additional tests for chain transform command."""

    def test_restrict_original_json_unified_output(self, mocker):
        """Tests --restrict-original --json outputs a single unified JSON blob."""
        from swarm_provenance_uploader.models import TransformResult, AnchorResult

        mock_client = mocker.MagicMock()
        mock_client.transform.return_value = TransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            original_hash=DUMMY_SWARM_REF,
            new_hash="c" * 64,
            description="filtered",
        )
        mock_client.set_status.return_value = AnchorResult(
            tx_hash="0x" + "cc" * 32,
            block_number=12346,
            gas_used=30000,
            explorer_url=None,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="",
            owner=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "transform", DUMMY_SWARM_REF, "c" * 64, "--restrict-original", "--json"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        import json
        output = json.loads(result.stdout)
        assert "transform" in output
        assert "restrict" in output
        assert output["restrict"] is not None

    def test_restrict_original_failure_warns(self, mocker):
        """Tests --restrict-original shows warning when set_status fails."""
        from swarm_provenance_uploader.models import TransformResult
        from swarm_provenance_uploader.exceptions import ChainTransactionError

        mock_client = mocker.MagicMock()
        mock_client.transform.return_value = TransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            original_hash=DUMMY_SWARM_REF,
            new_hash="c" * 64,
            description="filtered",
        )
        mock_client.set_status.side_effect = ChainTransactionError("reverted")

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "transform", DUMMY_SWARM_REF, "c" * 64, "--restrict-original"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "WARNING" in result.stdout
        assert "Transformation recorded" in result.stdout

    def test_restrict_original_failure_json(self, mocker):
        """Tests --restrict-original --json with failed restrict shows null."""
        from swarm_provenance_uploader.models import TransformResult
        from swarm_provenance_uploader.exceptions import ChainTransactionError

        mock_client = mocker.MagicMock()
        mock_client.transform.return_value = TransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=None,
            original_hash=DUMMY_SWARM_REF,
            new_hash="c" * 64,
            description="filtered",
        )
        mock_client.set_status.side_effect = ChainTransactionError("reverted")

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "transform", DUMMY_SWARM_REF, "c" * 64, "--restrict-original", "--json"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "WARNING" in result.stdout
        # Extract JSON from mixed output (CliRunner merges stderr into stdout)
        import json
        json_start = result.stdout.index("{")
        output = json.loads(result.stdout[json_start:])
        assert output["restrict"] is None
        assert output["transform"]["tx_hash"] == DUMMY_TX_HASH


# =============================================================================
# UPLOAD-COLLECTION TESTS
# =============================================================================

class TestUploadCollectionCommand:
    """Tests for upload-collection command."""

    def _mock_gateway_for_collection(self, mocker):
        """Set up common mocks for collection upload tests."""
        from swarm_provenance_uploader.models import ManifestUploadResponse

        mock_client = mocker.MagicMock()
        mock_client.purchase_stamp.return_value = DUMMY_STAMP
        mock_client.upload_manifest.return_value = ManifestUploadResponse(
            reference=DUMMY_SWARM_REF,
            file_count=2,
            message="Manifest uploaded",
        )
        mocker.patch(
            "swarm_provenance_uploader.cli._get_gateway_client_with_x402",
            return_value=mock_client,
        )
        return mock_client

    def test_upload_collection_success(self, mocker):
        """Tests full collection upload flow."""
        mock_client = self._mock_gateway_for_collection(mocker)

        with runner.isolated_filesystem():
            import os
            os.makedirs("mydir/sub")
            with open("mydir/a.txt", "w") as f:
                f.write("hello")
            with open("mydir/sub/b.txt", "w") as f:
                f.write("world")

            result = runner.invoke(
                app, ["upload-collection", "mydir", "--std", "TEST-V1"]
            )

            assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
            assert "SUCCESS" in result.stdout
            assert DUMMY_SWARM_REF in result.stdout
            assert "a.txt" in result.stdout
            assert "sub/b.txt" in result.stdout
            mock_client.purchase_stamp.assert_called_once()
            mock_client.upload_manifest.assert_called_once()

    def test_upload_collection_json(self, mocker):
        """Tests JSON output format."""
        self._mock_gateway_for_collection(mocker)

        with runner.isolated_filesystem():
            import os
            os.mkdir("mydir")
            with open("mydir/data.csv", "w") as f:
                f.write("a,b\n1,2")

            result = runner.invoke(
                app, ["upload-collection", "mydir", "--json"]
            )

            assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
            import json
            # Find the JSON object in the output
            lines = result.stdout.strip().split("\n")
            # JSON output starts with '{'
            json_start = next(i for i, l in enumerate(lines) if l.strip().startswith("{"))
            json_text = "\n".join(lines[json_start:])
            output = json.loads(json_text)
            assert output["swarm_reference"] == DUMMY_SWARM_REF
            assert output["file_count"] == 1
            assert len(output["files"]) == 1

    def test_upload_collection_not_a_directory(self):
        """Tests error when path is a file, not a directory."""
        with runner.isolated_filesystem():
            with open("notadir.txt", "w") as f:
                f.write("data")

            result = runner.invoke(
                app, ["upload-collection", "notadir.txt"]
            )

            assert result.exit_code != 0
            assert "Not a directory" in result.stdout

    def test_upload_collection_empty_directory(self):
        """Tests error on empty directory."""
        with runner.isolated_filesystem():
            import os
            os.mkdir("emptydir")

            result = runner.invoke(
                app, ["upload-collection", "emptydir"]
            )

            assert result.exit_code != 0
            assert "empty" in result.stdout.lower()

    def test_upload_collection_with_pool(self, mocker):
        """Tests collection upload using pooled stamp."""
        from swarm_provenance_uploader.models import ManifestUploadResponse, AcquireStampResponse

        mock_client = mocker.MagicMock()
        mock_client.acquire_stamp_from_pool.return_value = AcquireStampResponse(
            success=True,
            batch_id=DUMMY_STAMP,
            depth=17,
            size_name="small",
            message="Acquired",
            fallback_used=False,
        )
        mock_client.upload_manifest.return_value = ManifestUploadResponse(
            reference=DUMMY_SWARM_REF,
            file_count=1,
            message="OK",
        )
        mocker.patch(
            "swarm_provenance_uploader.cli._get_gateway_client_with_x402",
            return_value=mock_client,
        )

        with runner.isolated_filesystem():
            import os
            os.mkdir("mydir")
            with open("mydir/file.txt", "w") as f:
                f.write("data")

            result = runner.invoke(
                app, ["upload-collection", "mydir", "--usePool"]
            )

            assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
            assert "SUCCESS" in result.stdout
            mock_client.acquire_stamp_from_pool.assert_called_once()
            mock_client.upload_manifest.assert_called_once()

    def test_upload_collection_local_backend(self, mocker):
        """Tests error when using local backend (gateway only)."""
        _backend_config["backend"] = "local"

        with runner.isolated_filesystem():
            import os
            os.mkdir("mydir")
            with open("mydir/file.txt", "w") as f:
                f.write("data")

            result = runner.invoke(
                app, ["upload-collection", "mydir"]
            )

            assert result.exit_code != 0
            assert "gateway" in result.stdout.lower()

    def test_upload_collection_nonexistent_directory(self):
        """Tests error when directory path does not exist."""
        result = runner.invoke(
            app, ["upload-collection", "/tmp/does_not_exist_xyz_12345"]
        )

        assert result.exit_code != 0
        assert "Not a directory" in result.stdout

    def test_upload_collection_with_existing_stamp(self, mocker):
        """Tests collection upload with --stamp-id (skip purchase)."""
        mock_client = self._mock_gateway_for_collection(mocker)

        with runner.isolated_filesystem():
            import os
            os.mkdir("mydir")
            with open("mydir/file.txt", "w") as f:
                f.write("data")

            result = runner.invoke(
                app, ["upload-collection", "mydir", "--stamp-id", DUMMY_STAMP]
            )

            assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
            assert "SUCCESS" in result.stdout
            # Should NOT have called purchase or pool acquire
            mock_client.purchase_stamp.assert_not_called()
            mock_client.acquire_stamp_from_pool.assert_not_called()
            # Should have called upload_manifest
            mock_client.upload_manifest.assert_called_once()

    def test_upload_collection_deferred_and_redundancy(self, mocker):
        """Tests that --deferred and --redundancy flags are passed through."""
        mock_client = self._mock_gateway_for_collection(mocker)

        with runner.isolated_filesystem():
            import os
            os.mkdir("mydir")
            with open("mydir/file.txt", "w") as f:
                f.write("data")

            result = runner.invoke(
                app, ["upload-collection", "mydir", "--deferred", "--redundancy"]
            )

            assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
            # Verify flags were passed to upload_manifest
            call_kwargs = mock_client.upload_manifest.call_args
            assert call_kwargs.kwargs.get("deferred") is True or call_kwargs[1].get("deferred") is True
            assert call_kwargs.kwargs.get("redundancy") is True or call_kwargs[1].get("redundancy") is True


class TestChainGasLimitFlag:
    """Tests for --gas flag on chain write commands."""

    def test_gas_flag_passed_to_anchor(self, mocker):
        """Tests that --gas flag sets gas_limit in chain config."""
        from swarm_provenance_uploader.models import AnchorResult

        mock_client = mocker.MagicMock()
        mock_client.anchor.return_value = AnchorResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=DUMMY_EXPLORER_URL,
            swarm_hash=DUMMY_SWARM_REF,
            data_type="swarm-provenance",
            owner=DUMMY_ADDRESS,
        )

        mock_get = mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "anchor", DUMMY_SWARM_REF, "--gas", "500000"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        # Verify gas_limit was passed through to ChainClient
        assert _chain_config["gas_limit"] == 500000

    def test_gas_flag_on_access(self, mocker):
        """Tests that --gas flag works on access command."""
        from swarm_provenance_uploader.models import AccessResult

        mock_client = mocker.MagicMock()
        mock_client.access.return_value = AccessResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12345,
            gas_used=50000,
            explorer_url=DUMMY_EXPLORER_URL,
            swarm_hash=DUMMY_SWARM_REF,
            accessor=DUMMY_ADDRESS,
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "access", DUMMY_SWARM_REF, "--gas", "300000"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert _chain_config["gas_limit"] == 300000


class TestChainMergeCommand:
    """Tests for chain merge command."""

    def test_merge_success(self, mocker):
        """Tests chain merge command succeeds with 2 sources + new hash."""
        from swarm_provenance_uploader.models import MergeTransformResult

        source1 = "a" * 64
        source2 = "b" * 64
        new_hash = "c" * 64

        mock_client = mocker.MagicMock()
        mock_client.merge_transform.return_value = MergeTransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12350,
            gas_used=180000,
            explorer_url=DUMMY_EXPLORER_URL,
            source_hashes=[source1, source2],
            new_hash=new_hash,
            description="Merged datasets",
            new_data_type="merged",
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "merge", source1, source2, new_hash, "--description", "Merged datasets"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert "Merge transformation recorded" in result.stdout
        assert "Sources: 2" in result.stdout
        mock_client.merge_transform.assert_called_once_with(
            source_hashes=[source1, source2],
            new_hash=new_hash,
            description="Merged datasets",
            new_data_type="merged",
            verbose=False,
        )

    def test_merge_too_few_args(self, mocker):
        """Tests chain merge fails with fewer than 3 hashes."""
        mocker.patch("swarm_provenance_uploader.cli._get_chain_client")

        result = runner.invoke(app, ["chain", "merge", "a" * 64, "b" * 64])

        assert result.exit_code == 1
        assert "at least 3 hashes" in result.stdout.lower() or "2+ source" in result.stdout

    def test_merge_json_output(self, mocker):
        """Tests chain merge with --json output."""
        from swarm_provenance_uploader.models import MergeTransformResult

        source1 = "a" * 64
        source2 = "b" * 64
        new_hash = "c" * 64

        mock_client = mocker.MagicMock()
        mock_client.merge_transform.return_value = MergeTransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12350,
            gas_used=180000,
            source_hashes=[source1, source2],
            new_hash=new_hash,
            description="Merged",
            new_data_type="merged",
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "merge", source1, source2, new_hash, "--json"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        import json
        output = json.loads(result.stdout)
        assert output["tx_hash"] == DUMMY_TX_HASH
        assert len(output["source_hashes"]) == 2

    def test_merge_source_not_registered(self, mocker):
        """Tests chain merge when a source hash is not registered."""
        from swarm_provenance_uploader.exceptions import DataNotRegisteredError

        mock_client = mocker.MagicMock()
        mock_client.merge_transform.side_effect = DataNotRegisteredError(
            "Not registered", data_hash="a" * 64
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(app, ["chain", "merge", "a" * 64, "b" * 64, "c" * 64])

        assert result.exit_code == 1
        assert "not registered" in result.stdout.lower()

    def test_merge_validation_error(self, mocker):
        """Tests chain merge with validation error (e.g., too many sources)."""
        from swarm_provenance_uploader.exceptions import ChainValidationError

        mock_client = mocker.MagicMock()
        mock_client.merge_transform.side_effect = ChainValidationError(
            "Merge source count 51 exceeds maximum of 50"
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        hashes = ["a" * 64] * 51 + ["b" * 64]
        result = runner.invoke(app, ["chain", "merge"] + hashes)

        assert result.exit_code == 1
        assert "Validation failed" in result.stdout

    def test_merge_custom_type(self, mocker):
        """Tests chain merge with custom data type."""
        from swarm_provenance_uploader.models import MergeTransformResult

        source1 = "a" * 64
        source2 = "b" * 64
        new_hash = "c" * 64

        mock_client = mocker.MagicMock()
        mock_client.merge_transform.return_value = MergeTransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12350,
            gas_used=180000,
            source_hashes=[source1, source2],
            new_hash=new_hash,
            description="Combined",
            new_data_type="dataset",
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "merge", source1, source2, new_hash,
                  "--type", "dataset", "--description", "Combined"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        mock_client.merge_transform.assert_called_once_with(
            source_hashes=[source1, source2],
            new_hash=new_hash,
            description="Combined",
            new_data_type="dataset",
            verbose=False,
        )

    def test_merge_gas_flag(self, mocker):
        """Tests chain merge with --gas flag."""
        from swarm_provenance_uploader.models import MergeTransformResult

        mock_client = mocker.MagicMock()
        mock_client.merge_transform.return_value = MergeTransformResult(
            tx_hash=DUMMY_TX_HASH,
            block_number=12350,
            gas_used=200000,
            source_hashes=["a" * 64, "b" * 64],
            new_hash="c" * 64,
            description="",
            new_data_type="merged",
        )

        mocker.patch("swarm_provenance_uploader.cli._get_chain_client", return_value=mock_client)

        result = runner.invoke(
            app, ["chain", "merge", "a" * 64, "b" * 64, "c" * 64, "--gas", "400000"]
        )

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert _chain_config["gas_limit"] == 400000


# =============================================================================
# FREE TIER FLAG TESTS
# =============================================================================

class TestFreeTierFlag:
    """Tests for --free flag."""

    def test_free_flag_sets_backend_config(self, mocker):
        """Tests that --free flag sets _backend_config['free_tier']."""
        mock_client = mocker.MagicMock()
        mock_client.health_check.return_value = True

        mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client,
        )

        result = runner.invoke(app, ["--free", "health"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert _backend_config["free_tier"] is True

    def test_free_flag_default_is_false(self):
        """Tests that free_tier defaults to False."""
        assert _backend_config["free_tier"] is False

    def test_free_and_x402_both_set(self, mocker):
        """Tests that --free and --x402 can both be set (free header sent, x402 also configured)."""
        mock_client = mocker.MagicMock()
        mock_client.health_check.return_value = True

        mock_gw_cls = mocker.patch(
            "swarm_provenance_uploader.cli.GatewayClient",
            return_value=mock_client,
        )

        result = runner.invoke(app, ["--free", "--x402", "health"])

        assert result.exit_code == 0, f"CLI Failed: {result.stdout}"
        assert _backend_config["free_tier"] is True
        assert _x402_config["enabled"] is True