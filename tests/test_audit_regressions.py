"""Regression tests for the 2026-09 audit findings (#132).

Each test reproduces a finding against the real code path, without mocking
the part that was wrong: the download path handling, content-hash and
notary-signer checks with real signatures, and a pinned x402 signer vector
verified against the on-chain EIP-712 domain separator.
"""

import base64
import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from swarm_provenance_uploader.cli import app
from swarm_provenance_uploader.core import file_utils
from swarm_provenance_uploader.core.gateway_client import GatewayClient
from swarm_provenance_uploader.models import NotaryInfoResponse

runner = CliRunner()

STAMP = "a3" * 32
REFERENCE = "b5d4ea763a1396676771151158461f73678f1676166acd06a0a18600b85de8a4"
NOTARY_KEY = "0x" + "11" * 32
FOREIGN_KEY = "0x" + "22" * 32


def _metadata(data: bytes, content_hash: str = None, signatures=None) -> dict:
    document = {
        "data": base64.b64encode(data).decode(),
        "content_hash": content_hash or hashlib.sha256(data).hexdigest(),
        "stamp_id": STAMP,
        "provenance_standard": None,
        "encryption": None,
    }
    if signatures is not None:
        document["signatures"] = signatures
    return document


def _notary_signature(document: dict, signing_key: str, claimed_signer: str = None) -> dict:
    """A notary signature over `document['data']`, made with a real key."""
    from eth_account import Account
    from eth_account.messages import encode_defunct

    data_hash = hashlib.sha256(
        json.dumps(document["data"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    timestamp = "2026-10-08T12:00:00+00:00"
    signed = Account.sign_message(encode_defunct(text=f"{data_hash}|{timestamp}"), private_key=signing_key)
    return {
        "type": "notary",
        "signer": claimed_signer or Account.from_key(signing_key).address,
        "timestamp": timestamp,
        "data_hash": data_hash,
        "signature": "0x" + signed.signature.hex().replace("0x", "", 1),
        "hashed_fields": ["data"],
        "signed_message_format": "{data_hash}|{timestamp}",
    }


def _download(mocker, tmp_path, document, *args, notary_key=NOTARY_KEY):
    from eth_account import Account

    client = MagicMock()
    client.download_data.return_value = json.dumps(document).encode()
    client.get_notary_info.return_value = NotaryInfoResponse(
        enabled=True, available=True, address=Account.from_key(notary_key).address,
    )
    mocker.patch("swarm_provenance_uploader.cli.GatewayClient", return_value=client)
    return runner.invoke(app, ["download", REFERENCE, "--output-dir", str(tmp_path), *args])


# --- Path handling ----------------------------------------------------------

class TestDownloadPathHandling:
    @pytest.mark.parametrize("reference", [
        "../../outside", "..", "a" * 63, "a" * 65, "g" * 64, "/etc/passwd", REFERENCE + "/../x", "",
    ])
    def test_non_reference_refused_before_any_file_or_request(self, mocker, tmp_path, reference):
        client = MagicMock()
        mocker.patch("swarm_provenance_uploader.cli.GatewayClient", return_value=client)
        out = tmp_path / "out"
        result = runner.invoke(app, ["download", reference, "--output-dir", str(out)])
        assert result.exit_code == 1
        assert "Not a Swarm reference" in result.output
        client.download_data.assert_not_called()
        assert not any(p.is_file() for p in tmp_path.rglob("*"))

    def test_files_stay_inside_output_dir(self, mocker, tmp_path):
        client = MagicMock()
        client.download_data.return_value = json.dumps(_metadata(b"hello")).encode()
        mocker.patch("swarm_provenance_uploader.cli.GatewayClient", return_value=client)
        out = tmp_path / "out"
        result = runner.invoke(app, ["download", REFERENCE, "--output-dir", str(out), "--no-verify"])
        assert result.exit_code == 0, result.output
        written = [p for p in tmp_path.rglob("*") if p.is_file()]
        assert written and all(out in p.parents for p in written)

    @pytest.mark.parametrize("reference", ["a" * 64, "A" * 64, "ab" * 64])
    def test_references_accepted(self, reference):
        assert file_utils.is_swarm_reference(reference)

    @pytest.mark.parametrize("reference", ["../x", "a" * 64 + "\n", "0x" + "a" * 64, "a" * 96])
    def test_gateway_download_refuses_bad_reference(self, requests_mock, reference):
        with pytest.raises(ValueError, match="Not a Swarm reference"):
            GatewayClient(base_url="https://gw.test").download_data(reference)
        assert requests_mock.call_count == 0

    def test_local_bee_download_refuses_bad_reference(self, requests_mock):
        from swarm_provenance_uploader.core import swarm_client

        with pytest.raises(ValueError, match="Not a Swarm reference"):
            swarm_client.download_data_from_swarm("http://localhost:1633", "../../debug")
        assert requests_mock.call_count == 0


# --- Content hash -------------------------------------------------------------

class TestDownloadHashMismatch:
    def test_mismatch_exits_1_and_never_writes_the_verified_name(self, mocker, tmp_path):
        client = MagicMock()
        client.download_data.return_value = json.dumps(_metadata(b"tampered", content_hash="0" * 64)).encode()
        mocker.patch("swarm_provenance_uploader.cli.GatewayClient", return_value=client)

        result = runner.invoke(app, ["download", REFERENCE, "--output-dir", str(tmp_path), "--no-verify"])

        assert result.exit_code == 1
        assert "Content hash verification FAILED" in result.output
        assert not (tmp_path / f"{REFERENCE}.data").exists()
        assert (tmp_path / f"{REFERENCE}.UNVERIFIED.data").read_bytes() == b"tampered"


# --- Notary signer, with real signatures ------------------------------------

class TestForeignNotarySigner:
    @pytest.fixture(autouse=True)
    def _needs_eth_account(self):
        pytest.importorskip("eth_account")

    def test_genuine_notary_signature_verifies(self, mocker, tmp_path):
        document = _metadata(b"genuine")
        document["signatures"] = [_notary_signature(document, NOTARY_KEY)]
        result = _download(mocker, tmp_path, document, "--strict")
        assert result.exit_code == 0, result.output
        assert "Verified" in result.output

    def test_foreign_key_claiming_the_notary_is_refused(self, mocker, tmp_path):
        """Signed by another key but naming the gateway's notary as signer."""
        from eth_account import Account

        document = _metadata(b"forged")
        document["signatures"] = [_notary_signature(
            document, FOREIGN_KEY, claimed_signer=Account.from_key(NOTARY_KEY).address)]
        result = _download(mocker, tmp_path, document, "--strict")
        assert result.exit_code == 1
        assert "recovery mismatch" in result.output
        assert not (tmp_path / f"{REFERENCE}.data").exists()

    def test_foreign_signer_is_refused(self, mocker, tmp_path):
        """A valid signature, but by someone who is not the gateway's notary."""
        document = _metadata(b"foreign")
        document["signatures"] = [_notary_signature(document, FOREIGN_KEY)]
        result = _download(mocker, tmp_path, document, "--strict")
        assert result.exit_code == 1
        assert "Signer mismatch" in result.output

    def test_data_changed_after_signing_is_refused(self, mocker, tmp_path):
        document = _metadata(b"original")
        document["signatures"] = [_notary_signature(document, NOTARY_KEY)]
        tampered = _metadata(b"changed")
        tampered["signatures"] = document["signatures"]
        result = _download(mocker, tmp_path, tampered, "--strict")
        assert result.exit_code == 1
        assert "Data hash mismatch" in result.output

    def test_without_strict_a_foreign_signature_is_reported(self, mocker, tmp_path):
        """Verification is on by default; without --strict a failure is shown, not hidden."""
        document = _metadata(b"foreign")
        document["signatures"] = [_notary_signature(document, FOREIGN_KEY)]
        result = _download(mocker, tmp_path, document)
        assert "Signature: ✗ FAILED" in result.output


# --- Pinned x402 signer vector ---------------------------------------------

# Base Sepolia USDC DOMAIN_SEPARATOR, read on-chain 2026-10-07.
BASE_SEPOLIA_DOMAIN_SEPARATOR = "71f17a3b2ff373b803d70a5a07c046c1a2bc8e89c09ef722fcb047abe94c9818"
SIGNER_KEY = "0x" + "4c" * 32
PAY_TO = "0x1234567890AbcdEF1234567890aBcDeF12345678"
FIXED_NOW = 1_800_000_000
FIXED_NONCE = bytes(range(32))
# The X-PAYMENT signature for the vector below. A change to the signed
# message or domain changes it; the recovery test explains such a change.
PINNED_SIGNATURE = (
    "0xb9056d84f76b764457858b6dfe04ae2a0c6a1535be0098d1916c9c3578376fde"
    "73b240fed5f351aa1481775e14f899882aba40a4346b177b74bae128ce790bdc1c"
)


class TestPinnedSignerVector:
    """sign_payment output for fixed inputs, checked against the on-chain domain."""

    @pytest.fixture
    def signed(self, monkeypatch):
        pytest.importorskip("web3")
        pytest.importorskip("eth_account")
        from swarm_provenance_uploader.core import x402_client
        from swarm_provenance_uploader.models import X402PaymentOption

        # Real dependencies, not a mock cached by another test
        monkeypatch.setattr(x402_client, "_eth_account", None)
        monkeypatch.setattr(x402_client, "_web3", None)
        client = x402_client.X402Client(private_key=SIGNER_KEY, network="base-sepolia")  # validation NOT skipped
        web3 = MagicMock()
        web3.to_checksum_address = lambda a: a
        web3.eth.contract.return_value.functions.DOMAIN_SEPARATOR.return_value.call.return_value = (
            bytes.fromhex(BASE_SEPOLIA_DOMAIN_SEPARATOR))
        client._web3 = web3  # the on-chain value, as recorded

        option = X402PaymentOption(
            scheme="exact", network="base-sepolia", maxAmountRequired="26667", resource="/api/v1/stamps/",
            payTo=PAY_TO, asset=x402_client.USDC_CONTRACTS["base-sepolia"],
            extra={"name": "USDC", "version": "2"},
        )
        with patch.object(x402_client.time, "time", return_value=FIXED_NOW), \
                patch.object(client, "_generate_nonce", return_value=FIXED_NONCE):
            header = client.sign_payment(option)
        return client, json.loads(base64.b64decode(header))

    def test_authorization_fields(self, signed):
        client, payload = signed
        auth = payload["payload"]["authorization"]
        assert payload["scheme"] == "exact" and payload["network"] == "base-sepolia"
        assert auth == {
            "from": client.address, "to": PAY_TO, "value": "26667",
            "validAfter": str(FIXED_NOW - 60), "validBefore": str(FIXED_NOW + 300),
            "nonce": "0x" + FIXED_NONCE.hex(),
        }

    def test_signature_recovers_against_on_chain_domain(self, signed):
        """Rebuild the EIP-712 digest by hand from the recorded DOMAIN_SEPARATOR."""
        from eth_abi import encode
        from eth_account import Account
        from web3 import Web3

        client, payload = signed
        auth = payload["payload"]["authorization"]
        type_hash = Web3.keccak(text="TransferWithAuthorization(address from,address to,uint256 value,"
                                     "uint256 validAfter,uint256 validBefore,bytes32 nonce)")
        struct_hash = Web3.keccak(encode(
            ["bytes32", "address", "address", "uint256", "uint256", "uint256", "bytes32"],
            [type_hash, auth["from"], auth["to"], int(auth["value"]), int(auth["validAfter"]),
             int(auth["validBefore"]), bytes.fromhex(auth["nonce"][2:])],
        ))
        digest = Web3.keccak(b"\x19\x01" + bytes.fromhex(BASE_SEPOLIA_DOMAIN_SEPARATOR) + struct_hash)
        recovered = Account._recover_hash(digest, signature=payload["payload"]["signature"])
        assert recovered == client.address

    def test_signature_is_pinned(self, signed):
        _, payload = signed
        assert payload["payload"]["signature"] == PINNED_SIGNATURE
