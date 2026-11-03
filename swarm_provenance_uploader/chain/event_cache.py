"""
In-memory cache for DataTransformed and DataMerged event logs.

On v1 contracts, the DataProvenance contract stores transformation
descriptions (string[]) but NOT the linked hashes in state — newDataHash
is only in event logs.  This forces get_provenance_chain to scan the full
contract history on every call (~1.4M blocks on Base Sepolia, ~20s).

This module provides a singleton cache per (chain, contract_address) that
does a full scan on first call and incremental scans on subsequent calls,
reducing repeat queries to <1s.  Also scans DataMerged events (v2+) and
adds forward/reverse entries for each merge source.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

# Module-level singleton registry keyed by (chain, contract_address_lower)
_registry: dict[tuple[str, str], TransformationEventCache] = {}
_registry_lock = threading.Lock()


def _hex(value) -> str:
    """A bytes32 value as hex without 0x; other values as str()."""
    return value.hex() if isinstance(value, bytes) else str(value)


class TransformationEventCache:
    """Thread-safe in-memory cache of DataTransformed events.

    Builds forward and reverse lookup maps from event logs.
    First call does a full scan from deploy_block; subsequent calls
    scan only new blocks since the last scan.
    """

    def __init__(self):
        self._forward: dict[str, list[tuple[str, str]]] = {}
        self._reverse: dict[str, list[tuple[str, str]]] = {}
        self._last_scanned_block: int | None = None
        self._lock = threading.Lock()

    def get_maps(
        self,
        contract,
        deploy_block: int,
        current_block: int,
    ) -> tuple[dict, dict]:
        """Return (forward, reverse) transformation maps.

        Args:
            contract: DataProvenanceContract instance with get_all_transformations().
            deploy_block: Contract deploy block (start of first scan).
            current_block: Latest block number (end of scan range).

        Returns:
            Tuple of (forward, reverse) dicts:
              forward: original_hex -> [(new_hex, description), ...]
              reverse: new_hex -> [(original_hex, description), ...]

        Raises:
            Exception: Propagated from contract.get_all_transformations()
                or contract.get_all_merge_events() on scan failure. The
                maps and the scan marker are then unchanged.
        """
        with self._lock:
            if self._last_scanned_block is None:
                from_block = deploy_block
            else:
                from_block = self._last_scanned_block + 1

            if from_block > current_block:
                return self._forward, self._reverse

            # Read both event types before changing anything: if either
            # scan fails, the maps and the scan marker stay as they were,
            # so the next call scans the same range again (#230)
            events = contract.get_all_transformations(
                from_block=from_block,
                to_block=current_block,
            )
            # DataMerged events (v2+ contracts; none on v1).
            # For each merge: each source -> new_hash (forward),
            # new_hash -> each source (reverse).
            merge_events = contract.get_all_merge_events(
                from_block=from_block,
                to_block=current_block,
            )

            for orig_bytes, new_bytes, desc in events:
                orig_hex = _hex(orig_bytes)
                new_hex = _hex(new_bytes)
                self._forward.setdefault(orig_hex, []).append((new_hex, desc))
                self._reverse.setdefault(new_hex, []).append((orig_hex, desc))

            for evt in merge_events:
                new_hex = _hex(evt.args.newDataHash)
                desc = evt.args.transformation
                for src_bytes in evt.args.sourceDataHashes:
                    src_hex = _hex(src_bytes)
                    self._forward.setdefault(src_hex, []).append((new_hex, desc))
                    self._reverse.setdefault(new_hex, []).append((src_hex, desc))

            self._last_scanned_block = current_block
            logger.debug(
                "Event cache updated: scanned blocks %d-%d, "
                "%d forward entries, %d reverse entries",
                from_block,
                current_block,
                len(self._forward),
                len(self._reverse),
            )

            return self._forward, self._reverse


def get_cache(chain: str, contract_address: str) -> TransformationEventCache:
    """Get or create the singleton cache for a (chain, contract) pair.

    Args:
        chain: Chain name (e.g. 'base-sepolia').
        contract_address: Contract address (case-insensitive).

    Returns:
        TransformationEventCache instance (shared across callers).
    """
    key = (chain, contract_address.lower())
    with _registry_lock:
        if key not in _registry:
            _registry[key] = TransformationEventCache()
        return _registry[key]


def clear_registry():
    """Clear all cached instances. For testing only."""
    with _registry_lock:
        _registry.clear()
