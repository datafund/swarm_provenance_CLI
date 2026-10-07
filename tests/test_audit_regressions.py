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


@pytest.fixture(autouse=True)
def _restore_cli_config():
    """Global flags (--backend, --x402 ...) persist in module state between invocations."""
    from swarm_provenance_uploader import cli

    saved = {name: dict(getattr(cli, name)) for name in ("_backend_config", "_x402_config", "_chain_config")}
    yield
    for name, values in saved.items():
        getattr(cli, name).clear()
        getattr(cli, name).update(values)

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

    def test_cli_accepts_0x_prefixed_reference(self, mocker, tmp_path):
        """Chain commands print hashes with 0x; download takes them as pasted."""
        client = MagicMock()
        client.download_data.return_value = json.dumps(_metadata(b"hi")).encode()
        mocker.patch("swarm_provenance_uploader.cli.GatewayClient", return_value=client)
        result = runner.invoke(app, ["download", "0x" + REFERENCE, "--output-dir", str(tmp_path), "--no-verify"])
        assert result.exit_code == 0, result.output
        assert client.download_data.call_args.args[0] == REFERENCE

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
        assert "Content hash mismatch" in result.output
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

    def test_without_strict_a_foreign_signature_fails(self, mocker, tmp_path):
        """A failed signature exits 1 by default, and nothing is saved (#135)."""
        document = _metadata(b"foreign")
        document["signatures"] = [_notary_signature(document, FOREIGN_KEY)]
        result = _download(mocker, tmp_path, document)
        assert result.exit_code == 1
        assert "Signature: ✗ FAILED" in result.output
        assert not any(tmp_path.iterdir())


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


class TestStampIdValidation:
    @pytest.mark.parametrize("method,args", [
        ("get_stamp", ()), ("extend_stamp", (1000,)), ("check_stamp_health", ()),
    ])
    @pytest.mark.parametrize("stamp_id", ["../../wallet", "a" * 63, "x" * 64])
    def test_gateway_refuses_bad_stamp_id(self, requests_mock, method, args, stamp_id):
        with pytest.raises(ValueError, match="Not a stamp ID"):
            getattr(GatewayClient(base_url="https://gw.test"), method)(stamp_id, *args)
        assert requests_mock.call_count == 0

    @pytest.mark.parametrize("command", [["upload", "--file", "f.txt"], ["upload-collection", "d"]])
    def test_cli_refuses_bad_stamp_id_up_front(self, mocker, tmp_path, monkeypatch, command):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "f.txt").write_text("x")
        (tmp_path / "d").mkdir()
        (tmp_path / "d" / "a.txt").write_text("a")
        constructor = mocker.patch("swarm_provenance_uploader.cli.GatewayClient")
        result = runner.invoke(app, [*command, "--stamp-id", "../../x"])
        assert result.exit_code == 1
        assert "not a stamp ID" in result.output
        constructor.assert_not_called()

    def test_cli_accepts_0x_prefixed_stamp_id(self, mocker, tmp_path, monkeypatch):
        from swarm_provenance_uploader.models import StampDetails

        monkeypatch.chdir(tmp_path)
        (tmp_path / "f.txt").write_text("x")
        client = MagicMock()
        client.get_stamp.return_value = StampDetails(batchID=STAMP, usable=True, depth=17, amount="1",
                                                     bucketDepth=16, immutableFlag=False, batchTTL=3600)
        client.upload_data.return_value = REFERENCE
        mocker.patch("swarm_provenance_uploader.cli.GatewayClient", return_value=client)
        result = runner.invoke(app, ["upload", "--file", "f.txt", "--stamp-id", "0x" + STAMP])
        assert result.exit_code == 0, result.output
        assert client.get_stamp.call_args.args[0] == STAMP


# --- Notary checking is enforced (#135) --------------------------------------

class TestNotaryEnforcement:
    @pytest.fixture(autouse=True)
    def _needs_eth_account(self):
        pytest.importorskip("eth_account")

    def _address(self, key):
        from eth_account import Account
        return Account.from_key(key).address

    def test_unsigned_document_passes_by_default(self, mocker, tmp_path):
        result = _download(mocker, tmp_path, _metadata(b"plain"))
        assert result.exit_code == 0, result.output

    @pytest.mark.parametrize("flag", ["--require-signature", "--strict"])
    def test_missing_signature_fails_when_required(self, mocker, tmp_path, flag):
        """A document whose signatures were stripped no longer passes --strict."""
        result = _download(mocker, tmp_path, _metadata(b"stripped"), flag)
        assert result.exit_code == 1
        assert "no notary signature" in result.output
        assert not any(tmp_path.iterdir())

    def test_pinned_address_beats_the_serving_gateway(self, mocker, tmp_path):
        """A gateway serving forged data can name its own key as notary; a pin stops that."""
        document = _metadata(b"forged by the gateway")
        document["signatures"] = [_notary_signature(document, FOREIGN_KEY)]
        # The gateway vouches for its own key...
        unpinned = _download(mocker, tmp_path / "a", document, notary_key=FOREIGN_KEY)
        assert unpinned.exit_code == 0
        # ...but not against the pinned notary
        pinned = _download(mocker, tmp_path / "b", document, "--notary-address", self._address(NOTARY_KEY),
                           notary_key=FOREIGN_KEY)
        assert pinned.exit_code == 1
        assert "(pinned)" in pinned.output

    def test_pinned_address_from_environment(self, mocker, tmp_path, monkeypatch):
        document = _metadata(b"genuine")
        document["signatures"] = [_notary_signature(document, NOTARY_KEY)]
        monkeypatch.setenv("NOTARY_ADDRESS", self._address(NOTARY_KEY))
        client_notary = FOREIGN_KEY  # the gateway's answer must not be used
        result = _download(mocker, tmp_path, document, notary_key=client_notary)
        assert result.exit_code == 0, result.output
        assert "(pinned)" in result.output

    def test_local_backend_verifies_with_pinned_address(self, mocker, tmp_path):
        document = _metadata(b"local")
        document["signatures"] = [_notary_signature(document, NOTARY_KEY)]
        mocker.patch("swarm_provenance_uploader.cli.swarm_client.download_data_from_swarm",
                     return_value=json.dumps(document).encode())
        result = runner.invoke(app, ["--backend", "local", "download", REFERENCE, "--output-dir", str(tmp_path),
                                     "--notary-address", self._address(NOTARY_KEY)])
        assert result.exit_code == 0, result.output
        assert "Verified" in result.output

    def test_invalid_pinned_address_rejected(self, mocker, tmp_path):
        document = _metadata(b"genuine")
        document["signatures"] = [_notary_signature(document, NOTARY_KEY)]
        result = _download(mocker, tmp_path, document, "--notary-address", "notary.eth")
        assert result.exit_code == 1
        assert "is not an address" in result.output

    def test_saved_metadata_keeps_signatures_and_reverifies(self, mocker, tmp_path):
        from swarm_provenance_uploader.core.notary_utils import verify_notary_signature

        document = _metadata(b"keep me")
        document["signatures"] = [_notary_signature(document, NOTARY_KEY)]
        result = _download(mocker, tmp_path, document)
        assert result.exit_code == 0, result.output
        saved = json.loads((tmp_path / f"{REFERENCE}.meta.json").read_text())
        assert saved["signatures"] == document["signatures"]
        assert verify_notary_signature(saved, self._address(NOTARY_KEY)) == (True, None)


class TestNotaryReviewCases:
    """Cases from the review of #135 (no eth-account needed unless stated)."""

    def _plain_download(self, mocker, tmp_path, document, *args):
        client = MagicMock()
        client.download_data.return_value = json.dumps(document).encode()
        mocker.patch("swarm_provenance_uploader.cli.GatewayClient", return_value=client)
        return runner.invoke(app, ["download", REFERENCE, "--output-dir", str(tmp_path), *args])

    @pytest.mark.parametrize("signatures", [
        "abc", {"type": "notary"}, [1], None,
        [{"type": "notary", "signer": 123, "signature": "0x00", "data_hash": "x", "timestamp": "t"}],
        [{"type": "notary", "signer": "0x" + "1" * 40, "signature": 5, "data_hash": "x", "timestamp": "t"}],
    ])
    def test_malformed_signatures_fail_cleanly(self, mocker, tmp_path, signatures):
        document = _metadata(b"x")
        document["signatures"] = signatures
        result = self._plain_download(mocker, tmp_path, document)
        assert result.exit_code == 1
        assert "cannot be checked" in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)
        assert not any(tmp_path.iterdir())

    @pytest.mark.parametrize("flag", ["--require-signature", "--strict"])
    def test_no_verify_conflicts_with_required_signature(self, mocker, tmp_path, flag):
        result = self._plain_download(mocker, tmp_path, _metadata(b"x"), "--no-verify", flag)
        assert result.exit_code == 2
        assert not any(tmp_path.iterdir())

    def test_bad_pin_rejected_even_for_unsigned_document(self, mocker, tmp_path):
        result = self._plain_download(mocker, tmp_path, _metadata(b"x"), "--notary-address", "notary.eth")
        assert result.exit_code == 1
        assert "is not an address" in result.output

    def test_unsigned_document_downloads_without_eth_account(self, mocker, tmp_path):
        """Verification is on, but an unsigned document needs no crypto."""
        result = self._plain_download(mocker, tmp_path, _metadata(b"plain"))
        assert result.exit_code == 0, result.output
        assert (tmp_path / f"{REFERENCE}.data").read_bytes() == b"plain"

    def test_notary_verify_reads_pin_from_environment(self, mocker, tmp_path, monkeypatch):
        pytest.importorskip("eth_account")
        from eth_account import Account

        document = _metadata(b"genuine")
        document["signatures"] = [_notary_signature(document, NOTARY_KEY)]
        path = tmp_path / "doc.json"
        path.write_text(json.dumps(document))
        gateway = mocker.patch("swarm_provenance_uploader.cli.GatewayClient")
        monkeypatch.setenv("NOTARY_ADDRESS", Account.from_key(NOTARY_KEY).address)
        result = runner.invoke(app, ["notary", "verify", "--file", str(path)])
        assert result.exit_code == 0, result.output
        gateway.return_value.get_notary_info.assert_not_called()


# --- What download actually checks (#134) ------------------------------------

class TestDownloadClaims:
    """The content is not checked against the Swarm reference, so the output must not say so."""

    def test_unsigned_self_consistent_document_is_not_called_verified(self, mocker, tmp_path):
        client = MagicMock()
        client.download_data.return_value = json.dumps(_metadata(b"anything at all")).encode()
        mocker.patch("swarm_provenance_uploader.cli.GatewayClient", return_value=client)
        result = runner.invoke(app, ["download", REFERENCE, "--output-dir", str(tmp_path)])
        assert result.exit_code == 0, result.output
        assert "verification successful" not in result.output.lower()
        assert "verification passed" not in result.output.lower()
        assert "not checked against the Swarm reference" in result.output

    def test_self_consistent_forgery_fails_against_a_pinned_notary(self, mocker, tmp_path):
        """What does tie the content to a trusted party today: a pinned notary signature."""
        pytest.importorskip("eth_account")
        from eth_account import Account

        forged = _metadata(b"different content, consistent hash")
        forged["signatures"] = [_notary_signature(forged, FOREIGN_KEY)]
        result = _download(mocker, tmp_path, forged, "--notary-address", Account.from_key(NOTARY_KEY).address,
                           notary_key=FOREIGN_KEY)
        assert result.exit_code == 1
        assert not any(tmp_path.iterdir())

    def test_pinned_signature_summary(self, mocker, tmp_path):
        pytest.importorskip("eth_account")
        from eth_account import Account

        document = _metadata(b"genuine")
        document["signatures"] = [_notary_signature(document, NOTARY_KEY)]
        result = _download(mocker, tmp_path, document, "--notary-address", Account.from_key(NOTARY_KEY).address)
        assert result.exit_code == 0, result.output
        assert "signed by the pinned notary" in result.output
