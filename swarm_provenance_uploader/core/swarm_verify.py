"""
Verify content against a Swarm reference, chunk by chunk (#134).

A `/bzz` reference is the address of a mantaray manifest. Downloading it
returns only the file's bytes, so nothing in a download proves they belong
to the reference. This module rebuilds that proof from raw chunks:

1. Every chunk fetched is checked against its address (the BMT hash), so
   whoever serves the chunks cannot alter them.
2. The manifest is walked from the reference to the file entry the same
   way Bee resolves `GET /bzz/<ref>` (root node, index document, entry).
3. The file's chunk tree is walked, following data references and skipping
   erasure-coding parity, and the bytes are reassembled.

The result is the content the reference points to; compare it with the
downloaded bytes. Formats follow Bee (pkg/bmt, pkg/file/joiner,
pkg/file/redundancy, pkg/manifest/mantaray). Encrypted references (64-byte)
are not supported.

`fetch_chunk(address_hex) -> bytes` supplies raw chunks (8-byte span plus
payload), e.g. Bee's `GET /chunks/{address}`. It need not be trusted.
"""

import json
from typing import Callable, Dict, List, Optional, Tuple

CHUNK_SIZE = 4096
# Manifest nodes are read with their own size limit (a collection's root
# node is a few KB per hundred files)
MAX_MANIFEST_NODE_SIZE = 4 * 1024 * 1024
SPAN_SIZE = 8
HASH_SIZE = 32
BRANCHES = CHUNK_SIZE // HASH_SIZE  # 128

ChunkFetcher = Callable[[str], bytes]


class SwarmVerificationError(Exception):
    """The content could not be verified against the reference."""


class _TooLarge(SwarmVerificationError):
    """The reference holds more bytes than allowed."""


# --- Keccak-256 ------------------------------------------------------------

def _keccak_backend():
    try:
        from Crypto.Hash import keccak as _k  # pycryptodome (installed with web3)

        return lambda data: _k.new(digest_bits=256, data=data).digest()
    except ImportError:
        pass
    try:
        from eth_hash.auto import keccak as _eth_keccak

        _eth_keccak(b"")  # eth-hash imports without a backend and fails on first use
        return _eth_keccak
    except Exception:
        return _keccak256_pure


_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROT = [[0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61], [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]]
_M64 = (1 << 64) - 1


def _keccak_f(a):
    for rc in _RC:
        c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ (((c[(x + 1) % 5] << 1) | (c[(x + 1) % 5] >> 63)) & _M64) for x in range(5)]
        a = [[a[x][y] ^ d[x] for y in range(5)] for x in range(5)]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                r = _ROT[x][y]
                b[y][(2 * x + 3 * y) % 5] = ((a[x][y] << r) | (a[x][y] >> (64 - r))) & _M64 if r else a[x][y]
        a = [[b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y]) for y in range(5)] for x in range(5)]
        a[0][0] ^= rc
    return a


def _keccak256_pure(data: bytes) -> bytes:
    """Keccak-256 (the Ethereum variant), for installs without a C backend."""
    rate = 136
    msg = bytearray(data) + b"\x01"
    msg += b"\x00" * ((-len(msg)) % rate)
    msg[-1] |= 0x80
    a = [[0] * 5 for _ in range(5)]
    for off in range(0, len(msg), rate):
        block = msg[off:off + rate]
        for i in range(rate // 8):
            a[i % 5][i // 5] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        a = _keccak_f(a)
    out = b"".join(a[i % 5][i // 5].to_bytes(8, "little") for i in range(4))
    return out


keccak256 = _keccak_backend()


# --- Chunks ------------------------------------------------------------------

def chunk_address(chunk: bytes) -> bytes:
    """The address of a content-addressed chunk: keccak(span || BMT root of payload)."""
    if len(chunk) < SPAN_SIZE or len(chunk) > SPAN_SIZE + CHUNK_SIZE:
        raise SwarmVerificationError(f"chunk has invalid size {len(chunk)}")
    span, payload = chunk[:SPAN_SIZE], chunk[SPAN_SIZE:]
    level = [payload.ljust(CHUNK_SIZE, b"\x00")[i:i + HASH_SIZE] for i in range(0, CHUNK_SIZE, HASH_SIZE)]
    while len(level) > 1:
        level = [keccak256(level[i] + level[i + 1]) for i in range(0, len(level), 2)]
    return keccak256(span + level[0])


def decode_span(span: bytes) -> Tuple[int, int]:
    """(redundancy level, byte length): Bee stores the level in the span's top byte."""
    if span[-1] > 128:
        return span[-1] & 0x7F, int.from_bytes(span[:-1] + b"\x00", "little")
    return 0, int.from_bytes(span, "little")


# Erasure-coding tables (pkg/file/redundancy/level.go): (shards, parities) per level
_ERASURE_TABLES = {
    1: ([95, 69, 47, 29, 15, 6, 2, 1], [9, 8, 7, 6, 5, 4, 3, 2]),
    2: ([105, 96, 87, 78, 70, 62, 54, 47, 40, 33, 27, 21, 16, 11, 7, 4, 2, 1],
        [21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4]),
    3: ([93, 88, 83, 78, 74, 69, 64, 60, 55, 51, 46, 42, 38, 34, 30, 27, 23, 20, 17, 14, 11, 9, 6, 4, 3, 2, 1],
        [31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21, 20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5]),
    4: (list(range(37, 0, -1)),
        [89, 87, 86, 84, 83, 81, 80, 78, 76, 75, 73, 71, 70, 68, 66, 65, 63, 61, 59, 58,
         56, 54, 52, 50, 48, 47, 45, 43, 40, 38, 36, 34, 31, 29, 26, 23, 19]),
}


def _parities(level: int, shards: int) -> int:
    if level == 0:
        return 0
    if level not in _ERASURE_TABLES:
        raise SwarmVerificationError(f"unknown redundancy level {level}")
    table_shards, table_parities = _ERASURE_TABLES[level]
    for s, p in zip(table_shards, table_parities):
        if shards >= s:
            return p
    return 0


def _parity_count(span: int, level: int) -> int:
    """Parity references in an intermediate chunk of this span (file.ReferenceCount)."""
    if level == 0:
        return 0
    branching = BRANCHES - _parities(level, BRANCHES)
    branch_size, branch_level = CHUNK_SIZE, 1
    while branch_size < span:
        branch_size *= branching
        branch_level += 1
    reference_size = CHUNK_SIZE
    for _ in range(1, branch_level - 1):
        reference_size *= branching
    data_refs, offset = 1, reference_size
    while offset < span:
        offset += reference_size
        data_refs += 1
    return _parities(level, data_refs)


# Deeper than any real tree: 4096 * 128**7 bytes is far beyond any limit used here.
MAX_TREE_DEPTH = 8


def _branch_size(span: int, refs: int, branching: int) -> int:
    """Bytes under each non-last child (joiner.subtrieSection): all but the last child are full."""
    branch_size = CHUNK_SIZE
    while span - branch_size * (refs - 1) > branch_size:
        branch_size *= branching
    return branch_size


def read_file(fetch_chunk: ChunkFetcher, reference: bytes, max_size: int,
              _expected_span: Optional[int] = None, _root_level: Optional[int] = None,
              _depth: int = 0) -> bytes:
    """
    The bytes of the file whose chunk tree has root `reference`, every chunk verified.

    The tree must have the shape Bee's splitter produces (and its joiner
    accepts): each non-last child holds exactly a full branch, and chunks
    under an unredundant root carry no redundancy level.

    Raises:
        SwarmVerificationError: A chunk does not match its address, the tree is
            malformed, or the file is larger than max_size.
    """
    if _depth > MAX_TREE_DEPTH:
        raise SwarmVerificationError("file tree is deeper than any valid tree")
    chunk = fetch_chunk(reference.hex())
    if chunk_address(chunk) != reference:
        raise SwarmVerificationError(f"chunk {reference.hex()} does not match its address")
    level, span = decode_span(chunk[:SPAN_SIZE])
    payload = chunk[SPAN_SIZE:]
    if _root_level is None:
        _root_level = level
    elif _root_level == 0 and level != 0:
        raise SwarmVerificationError(f"chunk {reference.hex()} has a redundancy level under an unredundant root")
    if _expected_span is not None and span != _expected_span:
        raise SwarmVerificationError(f"chunk {reference.hex()} spans {span} bytes where the tree needs {_expected_span}")
    if span > max_size:
        raise _TooLarge(f"file is larger than the {max_size}-byte limit")
    if span <= CHUNK_SIZE:
        # Zero padding after the span does not change the address (the BMT
        # pads with zeros) and Bee serves such a chunk as its first `span` bytes.
        if len(payload) < span or any(payload[span:]):
            raise SwarmVerificationError(f"chunk {reference.hex()} span {span} != payload {len(payload)}")
        return payload[:span]
    # Intermediate chunk: data references, then parity references (skipped)
    refs_len = len(payload)
    while refs_len >= HASH_SIZE and payload[refs_len - HASH_SIZE:refs_len] == b"\x00" * HASH_SIZE:
        refs_len -= HASH_SIZE
    if refs_len == 0 or refs_len % HASH_SIZE:
        raise SwarmVerificationError(f"intermediate chunk {reference.hex()} is malformed")
    data_refs = refs_len // HASH_SIZE - _parity_count(span, level)
    if data_refs < 1:
        raise SwarmVerificationError(f"intermediate chunk {reference.hex()} has no data references")
    branching = BRANCHES - _parities(_root_level, BRANCHES) if _root_level else BRANCHES
    branch = _branch_size(span, data_refs, branching)
    last = span - branch * (data_refs - 1)
    if last <= 0:
        raise SwarmVerificationError(f"intermediate chunk {reference.hex()} has more children than its span allows")
    parts: List[bytes] = []
    for i in range(data_refs):
        parts.append(read_file(
            fetch_chunk, payload[i * HASH_SIZE:(i + 1) * HASH_SIZE], max_size,
            _expected_span=last if i == data_refs - 1 else branch,
            _root_level=_root_level, _depth=_depth + 1,
        ))
    return b"".join(parts)


# --- Mantaray manifests ------------------------------------------------------

_VERSION_01 = bytes.fromhex("025184789d63635766d78c41900196b57d7400875ebe4d9b5d1e76bd9652a9b7")[:31]
_VERSION_02 = bytes.fromhex("5768b3b6a7db56d21d1abff40d41cebfc83448fed8d7e9b06ec0d3b073f28f7b")[:31]
_TYPE_WITH_METADATA = 16
_HEADER = 32 + 31 + 1


_TYPE_VALUE = 2


class _Node:
    def __init__(self, entry: bytes, forks: Dict[int, Tuple[bytes, bytes, Dict[str, str], int]]):
        self.entry = entry
        # first byte -> (prefix, child reference, child metadata, child node type)
        self.forks = forks


def parse_node(data: bytes) -> _Node:
    """Unmarshal a mantaray node (versions 0.1 and 0.2)."""
    if len(data) < _HEADER:
        raise SwarmVerificationError("manifest node too short")
    key = data[:32]
    plain = bytearray(data)
    for i in range(32, len(data)):
        plain[i] ^= key[(i - 32) % 32]
    version = bytes(plain[32:63])
    if version not in (_VERSION_01, _VERSION_02):
        raise SwarmVerificationError("not a mantaray manifest node (unknown version)")
    ref_size = plain[_HEADER - 1]
    entry = bytes(plain[_HEADER:_HEADER + ref_size])
    offset = _HEADER + ref_size
    bitmap = plain[offset:offset + 32]
    offset += 32
    forks: Dict[int, Tuple[bytes, bytes, Dict[str, str], int]] = {}
    if ref_size == 0:
        return _Node(entry, forks)
    for byte in range(256):
        if not (bitmap[byte // 8] >> (byte % 8)) & 1:
            continue
        if offset + 32 + ref_size > len(plain):
            raise SwarmVerificationError("manifest node truncated")
        node_type, prefix_len = plain[offset], plain[offset + 1]
        if not 0 < prefix_len <= 30:
            raise SwarmVerificationError("manifest fork has an invalid prefix length")
        prefix = bytes(plain[offset + 2:offset + 2 + prefix_len])
        ref = bytes(plain[offset + 32:offset + 32 + ref_size])
        size = 32 + ref_size
        metadata: Dict[str, str] = {}
        if version == _VERSION_02 and node_type & _TYPE_WITH_METADATA:
            meta_len = int.from_bytes(plain[offset + size:offset + size + 2], "big")
            if offset + size + 2 + meta_len > len(plain):
                raise SwarmVerificationError("manifest metadata truncated")
            raw = bytes(plain[offset + size + 2:offset + size + 2 + meta_len])
            size += 2 + meta_len
            try:
                metadata = json.loads(raw) if raw.strip() else {}
            except ValueError as e:
                raise SwarmVerificationError(f"manifest metadata is not JSON: {e}") from e
            if not isinstance(metadata, dict) or not all(
                    isinstance(k, str) and isinstance(v, str) for k, v in metadata.items()):
                raise SwarmVerificationError("manifest metadata is not a map of strings")
        forks[byte] = (prefix, ref, metadata, node_type)
        offset += size
    return _Node(entry, forks)


def _lookup(fetch_chunk: ChunkFetcher, node: _Node, path: bytes,
            max_size: int) -> Tuple[_Node, Dict[str, str], Optional[int]]:
    """The node at `path`, its metadata and node type (mantaray Node.LookupNode)."""
    metadata: Dict[str, str] = {}
    node_type: Optional[int] = None
    while path:
        fork = node.forks.get(path[0])
        if fork is None or not path.startswith(fork[0]):
            raise SwarmVerificationError(f"path {path!r} is not in the manifest")
        prefix, ref, metadata, node_type = fork
        if len(ref) != HASH_SIZE:
            raise SwarmVerificationError("encrypted manifest references are not supported")
        node = parse_node(read_file(fetch_chunk, ref, max_size))
        path = path[len(prefix):]
    return node, metadata, node_type


def _go_path_join(element: str) -> str:
    """Go's path.Join("", element): "" stays "", anything else is path.Clean'ed."""
    if element == "":
        return ""
    import posixpath

    cleaned = posixpath.normpath(element)
    if cleaned.startswith("//"):  # POSIX keeps "//", Go's Clean does not
        cleaned = "/" + cleaned.lstrip("/")
    return cleaned


def content_of_reference(fetch_chunk: ChunkFetcher, reference: str, max_size: int = 100 * 1024 * 1024) -> bytes:
    """
    The content `GET /bzz/<reference>` serves, rebuilt from verified chunks.

    Raises:
        SwarmVerificationError: The reference does not lead to verifiable content.
    """
    try:
        ref = bytes.fromhex(reference)
    except ValueError as e:
        raise SwarmVerificationError(f"not a hex reference: {reference!r}") from e
    if len(ref) != HASH_SIZE:
        raise SwarmVerificationError("only unencrypted (32-byte) references can be verified")
    # Manifest nodes are small files of their own, with their own budget: the
    # content limit is about the file, not about the manifest around it.
    root = parse_node(read_file(fetch_chunk, ref, MAX_MANIFEST_NODE_SIZE))
    # Resolve exactly as Bee serves GET /bzz/<ref> (pkg/api/bzz.go): the
    # metadata at "/" names the index document, the path is path.Join'ed,
    # and the node found must be a value node with a file entry.
    _, root_meta, _ = _lookup(fetch_chunk, root, b"/", MAX_MANIFEST_NODE_SIZE)
    if "swarm-feed-owner" in root_meta or "swarm-feed-topic" in root_meta:
        raise SwarmVerificationError("feed manifests are not supported")
    index = root_meta.get("website-index-document")
    if index is None:
        raise SwarmVerificationError("manifest has no index document")
    path = _go_path_join(index)
    if not path:
        raise SwarmVerificationError("manifest index document is empty")
    node, _, node_type = _lookup(fetch_chunk, root, path.encode(), MAX_MANIFEST_NODE_SIZE)
    if node_type is None or not node_type & _TYPE_VALUE:
        raise SwarmVerificationError(f"manifest path {path!r} is not a file")
    if len(node.entry) != HASH_SIZE or node.entry == b"\x00" * HASH_SIZE:
        raise SwarmVerificationError("manifest entry has no unencrypted file reference")
    return read_file(fetch_chunk, node.entry, max_size)


def verify_content(fetch_chunk: ChunkFetcher, reference: str, content: bytes,
                   max_size: Optional[int] = None) -> None:
    """
    Check that `content` is what `reference` points to.

    Raises:
        SwarmVerificationError: It is not, or it cannot be verified.
    """
    try:
        # Bounded by the downloaded size: the reference holding more bytes is
        # already a mismatch, and nothing larger than that is fetched.
        expected = content_of_reference(fetch_chunk, reference, max_size or max(len(content), CHUNK_SIZE))
    except _TooLarge:
        if max_size:
            raise
        raise SwarmVerificationError("the downloaded content is not the content of this reference "
                                     "(the reference holds more bytes)")
    if expected != content:
        raise SwarmVerificationError("the downloaded content is not the content of this reference")
