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


# --- Crafted trees and manifests (review of the verifier) ----------------------

def _chunk(payload, span=None, level=0):
    raw_span = bytearray((len(payload) if span is None else span).to_bytes(8, "little"))
    if level:
        raw_span[7] = level | 0x80
    chunk = bytes(raw_span) + payload
    return sv.chunk_address(chunk), chunk


class _Store:
    def __init__(self):
        self.chunks = {}

    def put(self, payload, span=None, level=0):
        address, chunk = _chunk(payload, span, level)
        self.chunks[address.hex()] = chunk
        return address

    def fetch(self, address):
        if address not in self.chunks:
            raise sv.SwarmVerificationError(f"missing {address}")
        return self.chunks[address]

    def file(self, data):
        """A small unredundant file: one leaf, or one intermediate over full leaves."""
        if len(data) <= sv.CHUNK_SIZE:
            return self.put(data)
        refs = [self.put(data[i:i + sv.CHUNK_SIZE]) for i in range(0, len(data), sv.CHUNK_SIZE)]
        return self.put(b"".join(refs), span=len(data))


def _node(entry=b"\x00" * 32, forks=()):
    """A mantaray 0.2 node (zero obfuscation key). forks: (prefix, ref, metadata or None, node_type)."""
    out = bytearray(b"\x00" * 32) + sv._VERSION_02 + bytes([32]) + entry
    bitmap = bytearray(32)
    body = bytearray()
    for prefix, ref, metadata, node_type in sorted(forks, key=lambda f: f[0][0]):
        bitmap[prefix[0] // 8] |= 1 << (prefix[0] % 8)
        if metadata is not None:
            node_type |= sv._TYPE_WITH_METADATA
        body += bytes([node_type, len(prefix)]) + prefix.ljust(30, b"\x00") + ref
        if metadata is not None:
            raw = json.dumps(metadata).encode() if not isinstance(metadata, bytes) else metadata
            body += len(raw).to_bytes(2, "big") + raw
    return bytes(out + bitmap + body)


def _manifest(store, index, files, root_meta_extra=None, file_type=sv._TYPE_VALUE):
    """A single-file style manifest: "/" with the index document, plus file forks."""
    slash_meta = {"website-index-document": index, **(root_meta_extra or {})}
    slash = store.file(_node())
    forks = [(b"/", slash, slash_meta, 0)]
    for path, data in files.items():
        leaf = store.file(_node(entry=store.file(data)))
        forks.append((path.encode(), leaf, {"Content-Type": "text/plain"}, file_type))
    return store.file(_node(forks=forks)).hex()


class TestManifestResolutionMatchesBee:
    def test_index_path_is_cleaned_like_go_path_join(self):
        store = _Store()
        ref = _manifest(store, "./a", {"a": b"HONEST", "./a": b"FORGED"})
        assert sv.content_of_reference(store.fetch, ref) == b"HONEST"

    def test_feed_manifest_refused(self):
        store = _Store()
        ref = _manifest(store, "a", {"a": b"X"}, {"swarm-feed-owner": "ab" * 20, "swarm-feed-topic": "cd" * 32})
        with pytest.raises(sv.SwarmVerificationError, match="feed"):
            sv.content_of_reference(store.fetch, ref)

    def test_non_value_node_refused(self):
        store = _Store()
        ref = _manifest(store, "a", {"a": b"X"}, file_type=4)  # edge, not value
        with pytest.raises(sv.SwarmVerificationError, match="not a file"):
            sv.content_of_reference(store.fetch, ref)

    def test_empty_index_refused(self):
        store = _Store()
        ref = _manifest(store, "", {"a": b"X"})
        with pytest.raises(sv.SwarmVerificationError, match="empty"):
            sv.content_of_reference(store.fetch, ref)

    def test_metadata_that_is_not_a_string_map_refused(self):
        store = _Store()
        slash = store.file(_node())
        root = store.file(_node(forks=[(b"/", slash, b'["not", "a", "map"]', 0)])).hex()
        with pytest.raises(sv.SwarmVerificationError, match="map of strings"):
            sv.content_of_reference(store.fetch, root)

    def test_truncated_metadata_refused(self):
        node = bytearray(_node(forks=[(b"/", b"\x11" * 32, {"website-index-document": "a"}, 0)]))
        with pytest.raises(sv.SwarmVerificationError, match="truncated"):
            sv.parse_node(bytes(node[:-5]))

    def test_manifest_larger_than_the_content_is_fine(self):
        """Manifest nodes have their own budget (a collection's root node outgrows small content)."""
        store = _Store()
        # Distinct first bytes (this builder makes one fork per first byte):
        # 120 forks with metadata make a root node of several chunks.
        files = {chr(c) + "file": b"x" for c in range(0x30, 0x30 + 120) if chr(c) not in "/i"}
        files["index.html"] = b"tiny"
        ref = _manifest(store, "index.html", files)
        sv.verify_content(store.fetch, ref, b"tiny")


class TestTreeShapeMatchesBeeJoiner:
    def _manifest_for(self, store, file_ref):
        slash = store.file(_node())
        leaf = store.file(_node(entry=file_ref))
        return store.file(_node(forks=[(b"/", slash, {"website-index-document": "f"}, 0),
                                       (b"f", leaf, {}, sv._TYPE_VALUE)])).hex()

    def test_uneven_children_refused(self):
        store = _Store()
        short, full = store.put(b"a" * 10), store.put(b"b" * 4096)
        file_ref = store.put(short + full, span=4106)
        with pytest.raises(sv.SwarmVerificationError, match="tree needs"):
            sv.content_of_reference(store.fetch, self._manifest_for(store, file_ref))

    def test_level_byte_under_unredundant_root_refused(self):
        store = _Store()
        first, second = store.put(b"a" * 4096, level=2), store.put(b"b" * 10)
        file_ref = store.put(first + second, span=4106)
        with pytest.raises(sv.SwarmVerificationError, match="redundancy level under an unredundant root"):
            sv.content_of_reference(store.fetch, self._manifest_for(store, file_ref))

    def test_zero_padded_leaf_accepted(self):
        """Same address as the unpadded chunk (the BMT pads with zeros); Bee serves it."""
        store = _Store()
        address = store.put(b"hello\x00\x00", span=5)
        assert sv.read_file(store.fetch, address, 100) == b"hello"

    def test_padding_that_is_not_zero_refused(self):
        store = _Store()
        address = store.put(b"hello!!", span=5)
        with pytest.raises(sv.SwarmVerificationError):
            sv.read_file(store.fetch, address, 100)

    def test_deep_chain_refused_without_recursion_error(self):
        store = _Store()
        ref = store.put(b"x" * 4096)
        span = 4096
        for _ in range(sv.MAX_TREE_DEPTH + 2):
            span += 0  # a chain of single-child intermediates
            ref = store.put(ref, span=span + 1)
            span += 1
        with pytest.raises(sv.SwarmVerificationError):
            sv.read_file(store.fetch, ref, 10 ** 9)


class TestGetChunk:
    def test_404_is_file_not_found(self, requests_mock):
        from swarm_provenance_uploader.core import swarm_client

        requests_mock.get("http://bee.test/chunks/" + "ab" * 32, status_code=404)
        with pytest.raises(FileNotFoundError):
            swarm_client.get_chunk("http://bee.test", "ab" * 32)

    @pytest.mark.parametrize("address", ["../x", "ab" * 31, "zz" * 32])
    def test_address_validated(self, address, requests_mock):
        from swarm_provenance_uploader.core import swarm_client

        with pytest.raises(ValueError):
            swarm_client.get_chunk("http://bee.test", address)
        assert requests_mock.call_count == 0


class TestLocalDownloadReviewCases:
    def _invoke(self, mocker, tmp_path, reference, *args, chunk_error=None):
        from typer.testing import CliRunner
        from swarm_provenance_uploader import cli

        saved = dict(cli._backend_config)
        f = FIXTURES["provenance_doc_level2"]
        fetch = _fetcher("provenance_doc_level2")

        def get_chunk(url, address, verbose=False):
            if chunk_error:
                raise chunk_error
            return fetch(address)

        mocker.patch("swarm_provenance_uploader.cli.swarm_client.get_chunk", side_effect=get_chunk)
        mocker.patch("swarm_provenance_uploader.cli.swarm_client.download_data_from_swarm",
                     return_value=bytes.fromhex(f["content_hex"]))
        mocker.patch("swarm_provenance_uploader.cli.GatewayClient").return_value.download_data.return_value = \
            bytes.fromhex(f["content_hex"])
        try:
            return CliRunner().invoke(cli.app, [*args[:2], "download", reference, "--output-dir", str(tmp_path), *args[2:]])
        finally:
            cli._backend_config.clear()
            cli._backend_config.update(saved)

    def test_missing_chunk_fails_cleanly(self, mocker, tmp_path):
        ref = FIXTURES["provenance_doc_level2"]["reference"]
        result = self._invoke(mocker, tmp_path, ref, "--backend", "local",
                              chunk_error=FileNotFoundError("Chunk not found (404)"))
        assert result.exit_code == 1
        assert "could not be verified" in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)
        assert not any(tmp_path.iterdir())

    def test_unexpected_error_fails_cleanly(self, mocker, tmp_path):
        ref = FIXTURES["provenance_doc_level2"]["reference"]
        result = self._invoke(mocker, tmp_path, ref, "--backend", "local", chunk_error=RecursionError("deep"))
        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit)

    def test_encrypted_reference_skips_check_with_note(self, mocker, tmp_path):
        result = self._invoke(mocker, tmp_path, "ab" * 64, "--backend", "local")
        assert "encrypted references cannot be checked" in result.output

    def test_explicit_verify_reference_on_gateway_fails(self, mocker, tmp_path):
        """A script that asks for the check must not get exit 0 when it cannot run."""
        ref = FIXTURES["provenance_doc_level2"]["reference"]
        result = self._invoke(mocker, tmp_path, ref, "--backend", "gateway", "--verify-reference")
        assert result.exit_code == 1
        assert "the gateway does not serve the chunks" in result.output
        assert not any(tmp_path.iterdir())

    def test_explicit_verify_reference_on_encrypted_reference_fails(self, mocker, tmp_path):
        result = self._invoke(mocker, tmp_path, "ab" * 64, "--backend", "local", "--verify-reference")
        assert result.exit_code == 1
        assert "encrypted references cannot be checked" in result.output

    def test_gateway_default_needs_no_flag(self, mocker, tmp_path):
        ref = FIXTURES["provenance_doc_level2"]["reference"]
        result = self._invoke(mocker, tmp_path, ref, "--backend", "gateway")
        assert result.exit_code == 0, result.output
        assert "not checked against the Swarm reference" in result.output
