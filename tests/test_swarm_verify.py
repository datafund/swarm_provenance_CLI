"""Tests for verifying content against a Swarm reference (#134).

The fixtures are real chunks recorded from a Bee 2.8.2 node: `/bzz`
single-file uploads with redundancy level 2, the way the gateway uploads.
Only the chunks the verifier fetches are recorded.
"""

import base64
import hashlib
import json
from pathlib import Path

import pytest

from swarm_provenance_uploader.core import swarm_verify as sv

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "swarm_chunks.json").read_text())


def _fetcher(name, tamper=None):
    chunks = {a: bytes.fromhex(c) for a, c in FIXTURES[name]["chunks"].items()}
    if tamper:
        address, chunk = tamper(chunks)
        chunks[address] = chunk

    def fetch(address):
        if address not in chunks:
            raise sv.SwarmVerificationError(f"chunk {address} not available")
        return chunks[address]

    return fetch


@pytest.mark.parametrize("name", list(FIXTURES))
def test_rebuilds_the_content_of_a_real_reference(name):
    f = FIXTURES[name]
    assert sv.content_of_reference(_fetcher(name), f["reference"]) == bytes.fromhex(f["content_hex"])


@pytest.mark.parametrize("name", list(FIXTURES))
def test_verify_content_accepts_the_right_bytes(name):
    f = FIXTURES[name]
    sv.verify_content(_fetcher(name), f["reference"], bytes.fromhex(f["content_hex"]))


@pytest.mark.parametrize("name", list(FIXTURES))
def test_self_consistent_but_different_document_fails(name):
    """The #134 acceptance case: a valid-looking document that is not this reference's content."""
    f = FIXTURES[name]
    other = json.dumps({"data": base64.b64encode(b"forged").decode(),
                        "content_hash": hashlib.sha256(b"forged").hexdigest()}).encode()
    with pytest.raises(sv.SwarmVerificationError, match="not the content of this reference"):
        sv.verify_content(_fetcher(name), f["reference"], other)


def test_one_flipped_byte_fails():
    f = FIXTURES["tree_level2"]
    content = bytearray(bytes.fromhex(f["content_hex"]))
    content[5000] ^= 1
    with pytest.raises(sv.SwarmVerificationError):
        sv.verify_content(_fetcher("tree_level2"), f["reference"], bytes(content))


def test_a_served_chunk_that_does_not_match_its_address_fails():
    """Whoever serves the chunks cannot alter them: each is checked against its address."""
    f = FIXTURES["tree_level2"]

    def tamper(chunks):
        address = sorted(chunks)[0]
        chunk = bytearray(chunks[address])
        chunk[-1] ^= 1
        return address, bytes(chunk)

    with pytest.raises(sv.SwarmVerificationError, match="does not match its address"):
        sv.content_of_reference(_fetcher("tree_level2", tamper), f["reference"])


def test_unknown_reference_fails():
    with pytest.raises(sv.SwarmVerificationError):
        sv.content_of_reference(_fetcher("tree_level2"), "ab" * 32)


def test_encrypted_reference_not_supported():
    with pytest.raises(sv.SwarmVerificationError, match="unencrypted"):
        sv.content_of_reference(_fetcher("tree_level2"), "ab" * 64)


def test_size_limit():
    f = FIXTURES["tree_level2"]
    with pytest.raises(sv.SwarmVerificationError, match="limit"):
        sv.content_of_reference(_fetcher("tree_level2"), f["reference"], max_size=100)


def test_pure_python_keccak_matches_known_vectors():
    assert sv._keccak256_pure(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert sv._keccak256_pure(b"abc").hex() == "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"
    data = bytes(range(256)) * 3  # crosses the 136-byte rate several times
    assert sv._keccak256_pure(data) == sv.keccak256(data)


def test_span_decoding():
    assert sv.decode_span((9000).to_bytes(8, "little")) == (0, 9000)
    span = bytearray((9000).to_bytes(8, "little"))
    span[7] = 2 | 0x80
    assert sv.decode_span(bytes(span)) == (2, 9000)


# --- download --backend local checks the reference ---------------------------

class TestLocalDownloadVerifiesReference:
    @pytest.fixture
    def run(self, mocker, tmp_path):
        from typer.testing import CliRunner
        from swarm_provenance_uploader import cli

        saved = {k: dict(getattr(cli, k)) for k in ("_backend_config", "_x402_config")}
        f = FIXTURES["provenance_doc_level2"]
        fetch = _fetcher("provenance_doc_level2")
        mocker.patch("swarm_provenance_uploader.cli.swarm_client.get_chunk", side_effect=lambda url, a, verbose=False: fetch(a))

        def invoke(content, *args):
            mocker.patch("swarm_provenance_uploader.cli.swarm_client.download_data_from_swarm", return_value=content)
            return CliRunner().invoke(cli.app, ["--backend", "local", "download", f["reference"],
                                                "--output-dir", str(tmp_path), *args])

        yield invoke, bytes.fromhex(f["content_hex"]), tmp_path
        for k, v in saved.items():
            getattr(cli, k).clear()
            getattr(cli, k).update(v)

    def test_matching_content_is_verified(self, run):
        invoke, content, out = run
        result = invoke(content)
        assert result.exit_code == 0, result.output
        assert "Reference: ✓ content matches" in result.output
        assert "checked against the Swarm reference, chunk by chunk" in result.output
        assert "not checked against the Swarm reference" not in result.output

    def test_substituted_document_fails_and_saves_nothing(self, run):
        invoke, content, out = run
        raw = b"substituted"
        forged = json.dumps({"data": base64.b64encode(raw).decode(), "content_hash": hashlib.sha256(raw).hexdigest(),
                             "stamp_id": "a3" * 32}).encode()
        result = invoke(forged)
        assert result.exit_code == 1
        assert "could not be verified against the reference" in result.output
        assert not any(out.iterdir())

    def test_check_can_be_skipped(self, run):
        invoke, content, out = run
        result = invoke(b'{"data": "", "content_hash": "' + hashlib.sha256(b"").hexdigest().encode()
                        + b'", "stamp_id": "' + b"a3" * 32 + b'"}', "--no-verify-reference")
        assert result.exit_code == 0, result.output
        assert "not checked against the Swarm reference" in result.output
