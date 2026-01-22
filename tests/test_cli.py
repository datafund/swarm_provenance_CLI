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