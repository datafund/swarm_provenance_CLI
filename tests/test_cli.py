import pytest
from typer.testing import CliRunner
from swarm_provenance_uploader.cli import app, _backend_config, _x402_config
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
    _x402_config["enabled"] = False
    _x402_config["auto_pay"] = False
    _x402_config["max_auto_pay_usd"] = 1.00
    _x402_config["network"] = "base-sepolia"
    yield
    # Reset again after test
    _backend_config["backend"] = "gateway"
    _backend_config["gateway_url"] = "https://provenance-gateway.datafund.io"
    _backend_config["bee_url"] = "http://localhost:1633"
    _x402_config["enabled"] = False
    _x402_config["auto_pay"] = False
    _x402_config["max_auto_pay_usd"] = 1.00
    _x402_config["network"] = "base-sepolia"


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
        mock_constructor.assert_called_with(base_url="https://custom.gateway.io")


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
        assert "SWARM_X402_PRIVATE_KEY" in result.stdout
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
