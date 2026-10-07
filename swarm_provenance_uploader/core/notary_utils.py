"""
Utilities for notary signature verification.

Provides client-side verification of EIP-191 signatures added by the
provenance gateway's notary service.
"""

import json
import hashlib
from typing import Optional, Tuple


def verify_notary_signature(
    document: dict,
    expected_address: str,
) -> Tuple[bool, Optional[str]]:
    """
    Verify a notary signature locally using EIP-191.

    Args:
        document: The signed document dict with 'data' and 'signatures' fields
        expected_address: Expected signer address (from gateway notary info)

    Returns:
        (is_valid, error_message) - error_message is None if valid

    Verification steps:
    1. Find notary signature in document['signatures']
    2. Verify signer matches expected_address
    3. Reconstruct data hash using canonical JSON of document['data']
    4. Reconstruct signed message: "{data_hash}|{timestamp}"
    5. Verify EIP-191 signature using eth_account
    """
    # 1. Find notary signature
    malformed = malformed_signatures_reason(document)
    if malformed:
        return False, f"Malformed signatures: {malformed}"
    if not (isinstance(document, dict) and document.get("signatures")):
        return False, "No signatures found in document"

    notary_sig = extract_notary_signature(document)
    if not notary_sig:
        return False, "No notary signature found in document"

    # 2. Verify signer matches expected address
    signer = notary_sig.get("signer", "")
    if signer.lower() != expected_address.lower():
        return False, f"Signer mismatch: expected {expected_address}, got {signer}"

    # 3. Reconstruct data hash (canonical JSON - sorted keys, no whitespace)
    data_field = document.get("data")
    if data_field is None:
        return False, "Document missing 'data' field"

    data_json = json.dumps(data_field, sort_keys=True, separators=(",", ":"))
    computed_hash = hashlib.sha256(data_json.encode("utf-8")).hexdigest()

    expected_hash = notary_sig.get("data_hash", "")
    if computed_hash != expected_hash:
        return False, f"Data hash mismatch: computed {computed_hash}, expected {expected_hash}"

    # 4. Reconstruct signed message
    timestamp = notary_sig.get("timestamp", "")
    if not timestamp:
        return False, "Signature missing timestamp"

    message = f"{expected_hash}|{timestamp}"

    # 5. Verify EIP-191 signature
    try:
        from eth_account import Account
        from eth_account.messages import encode_defunct
    except ImportError:
        from .._requirements import INSTALL_ETH_ACCOUNT
        return False, f"eth_account not installed ({INSTALL_ETH_ACCOUNT})"

    signable = encode_defunct(text=message)
    signature = notary_sig.get("signature", "")
    if not signature:
        return False, "Signature missing signature value"

    # Ensure signature has 0x prefix
    if not signature.startswith("0x"):
        signature = f"0x{signature}"

    try:
        recovered = Account.recover_message(signable, signature=signature)
        if recovered.lower() != expected_address.lower():
            return False, f"Signature recovery mismatch: recovered {recovered}, expected {expected_address}"
        return True, None
    except Exception as e:
        return False, f"Signature verification error: {e}"


def extract_notary_signature(document: dict) -> Optional[dict]:
    """
    Extract the notary signature from a signed document.

    Args:
        document: The signed document dict

    Returns:
        The notary signature dict, or None if not found
    """
    if not isinstance(document, dict):
        return None
    signatures = document.get("signatures") or []
    if not isinstance(signatures, list):
        return None
    for sig in signatures:
        if isinstance(sig, dict) and sig.get("type") == "notary":
            return sig
    return None


def malformed_signatures_reason(document) -> Optional[str]:
    """
    Why a document's `signatures` field cannot be checked, or None if it is well formed.

    A present `signatures` field must be a list of objects, and a notary entry
    must not carry non-text `signer`, `signature`, `data_hash` or `timestamp`
    (missing ones are reported by verify_notary_signature). Anything else is
    reported rather than treated as "unsigned" or crashing.
    """
    if not isinstance(document, dict) or "signatures" not in document:
        return None
    signatures = document["signatures"]
    if not isinstance(signatures, list) or not all(isinstance(s, dict) for s in signatures):
        return "'signatures' is not a list of objects"
    for sig in signatures:
        if sig.get("type") == "notary":
            bad = [f for f in ("signer", "signature", "data_hash", "timestamp")
                   if f in sig and not isinstance(sig[f], str)]
            if bad:
                return f"notary signature field(s) {', '.join(bad)} not text"
    return None


def has_notary_signature(document: dict) -> bool:
    """
    Check if a document has a notary signature.

    Args:
        document: The document dict to check

    Returns:
        True if document has a notary signature
    """
    return extract_notary_signature(document) is not None
