"""
Utilities for notary signature verification.

Provides client-side verification of EIP-191 signatures added by the
provenance gateway's notary service.
"""

import json
import hashlib
from typing import Optional, Tuple

from eth_account import Account
from eth_account.messages import encode_defunct


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
    signatures = document.get("signatures", [])
    if not signatures:
        return False, "No signatures found in document"

    notary_sig = None
    for sig in signatures:
        if sig.get("type") == "notary":
            notary_sig = sig
            break

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
    signatures = document.get("signatures", [])
    for sig in signatures:
        if sig.get("type") == "notary":
            return sig
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
