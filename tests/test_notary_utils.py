"""Tests for notary signature verification utilities."""

import pytest
import json
import hashlib
from eth_account import Account
from eth_account.messages import encode_defunct

from swarm_provenance_uploader.core.notary_utils import (
    verify_notary_signature,
    extract_notary_signature,
    has_notary_signature,
)


# Helper to create a valid signed document
def create_signed_document(data: dict, private_key: str) -> dict:
    """Create a document with a valid notary signature."""
    account = Account.from_key(private_key)

    # Canonical JSON
    data_json = json.dumps(data, sort_keys=True, separators=(",", ":"))
    data_hash = hashlib.sha256(data_json.encode("utf-8")).hexdigest()

    timestamp = "2026-01-21T16:30:00+00:00"
    message = f"{data_hash}|{timestamp}"

    # Sign with EIP-191
    signable = encode_defunct(text=message)
    signed = account.sign_message(signable)

    return {
        "data": data,
        "signatures": [
            {
                "type": "notary",
                "signer": account.address,
                "timestamp": timestamp,
                "data_hash": data_hash,
                "signature": signed.signature.hex(),
                "signed_fields": ["data"],
            }
        ],
    }


# Test private key (DO NOT USE IN PRODUCTION)
TEST_PRIVATE_KEY = "0x" + "a" * 64


class TestVerifyNotarySignature:
    """Tests for verify_notary_signature function."""

    def test_valid_signature(self):
        """Test verification of a valid signature."""
        data = {"content": "test data", "value": 123}
        document = create_signed_document(data, TEST_PRIVATE_KEY)
        account = Account.from_key(TEST_PRIVATE_KEY)

        is_valid, error = verify_notary_signature(document, account.address)

        assert is_valid is True
        assert error is None

    def test_valid_signature_complex_data(self):
        """Test verification with complex nested data."""
        data = {
            "nested": {"a": 1, "b": [1, 2, 3]},
            "string": "hello",
            "number": 42.5,
        }
        document = create_signed_document(data, TEST_PRIVATE_KEY)
        account = Account.from_key(TEST_PRIVATE_KEY)

        is_valid, error = verify_notary_signature(document, account.address)

        assert is_valid is True
        assert error is None

    def test_missing_signatures_array(self):
        """Test document without signatures array."""
        document = {"data": "test"}

        is_valid, error = verify_notary_signature(document, "0x1234")

        assert is_valid is False
        assert "No signatures found" in error

    def test_empty_signatures_array(self):
        """Test document with empty signatures array."""
        document = {"data": "test", "signatures": []}

        is_valid, error = verify_notary_signature(document, "0x1234")

        assert is_valid is False
        assert "No signatures found" in error

    def test_no_notary_signature(self):
        """Test document with signatures but no notary type."""
        document = {
            "data": "test",
            "signatures": [
                {"type": "other", "signer": "0x1234", "signature": "0x5678"}
            ],
        }

        is_valid, error = verify_notary_signature(document, "0x1234")

        assert is_valid is False
        assert "No notary signature found" in error

    def test_signer_mismatch(self):
        """Test when signer doesn't match expected address."""
        data = {"content": "test"}
        document = create_signed_document(data, TEST_PRIVATE_KEY)
        wrong_address = "0x0000000000000000000000000000000000000001"

        is_valid, error = verify_notary_signature(document, wrong_address)

        assert is_valid is False
        assert "Signer mismatch" in error

    def test_data_hash_mismatch(self):
        """Test when data hash doesn't match."""
        data = {"content": "test"}
        document = create_signed_document(data, TEST_PRIVATE_KEY)
        account = Account.from_key(TEST_PRIVATE_KEY)

        # Modify the data after signing
        document["data"]["content"] = "tampered"

        is_valid, error = verify_notary_signature(document, account.address)

        assert is_valid is False
        assert "Data hash mismatch" in error

    def test_invalid_signature(self):
        """Test with corrupted/invalid signature."""
        data = {"content": "test"}
        document = create_signed_document(data, TEST_PRIVATE_KEY)
        account = Account.from_key(TEST_PRIVATE_KEY)

        # Corrupt the signature
        document["signatures"][0]["signature"] = "0x" + "00" * 65

        is_valid, error = verify_notary_signature(document, account.address)

        assert is_valid is False
        # Could be either "recovery mismatch" or "verification error"
        assert "mismatch" in error.lower() or "error" in error.lower()

    def test_missing_data_field(self):
        """Test document missing 'data' field."""
        document = {
            "signatures": [
                {
                    "type": "notary",
                    "signer": "0x1234",
                    "timestamp": "2026-01-21T16:30:00+00:00",
                    "data_hash": "abc123",
                    "signature": "0x5678",
                    "signed_fields": ["data"],
                }
            ]
        }

        is_valid, error = verify_notary_signature(document, "0x1234")

        assert is_valid is False
        assert "missing 'data' field" in error

    def test_missing_timestamp(self):
        """Test signature missing timestamp."""
        data = {"content": "test"}
        document = create_signed_document(data, TEST_PRIVATE_KEY)
        account = Account.from_key(TEST_PRIVATE_KEY)

        # Remove timestamp
        del document["signatures"][0]["timestamp"]

        is_valid, error = verify_notary_signature(document, account.address)

        assert is_valid is False
        assert "missing timestamp" in error

    def test_missing_signature_value(self):
        """Test signature missing signature value."""
        data = {"content": "test"}
        document = create_signed_document(data, TEST_PRIVATE_KEY)
        account = Account.from_key(TEST_PRIVATE_KEY)

        # Remove signature value
        del document["signatures"][0]["signature"]

        is_valid, error = verify_notary_signature(document, account.address)

        assert is_valid is False
        assert "missing signature value" in error

    def test_canonical_json_ordering(self):
        """Test that JSON key ordering is handled correctly."""
        # Create document with keys in different order
        data = {"z": 1, "a": 2, "m": 3}
        document = create_signed_document(data, TEST_PRIVATE_KEY)
        account = Account.from_key(TEST_PRIVATE_KEY)

        # Reorder keys in the document (Python 3.7+ preserves insertion order)
        document["data"] = {"m": 3, "z": 1, "a": 2}

        is_valid, error = verify_notary_signature(document, account.address)

        # Should still verify because canonical JSON uses sorted keys
        assert is_valid is True
        assert error is None

    def test_signature_without_0x_prefix(self):
        """Test signature without 0x prefix is handled."""
        data = {"content": "test"}
        document = create_signed_document(data, TEST_PRIVATE_KEY)
        account = Account.from_key(TEST_PRIVATE_KEY)

        # Remove 0x prefix
        sig = document["signatures"][0]["signature"]
        if sig.startswith("0x"):
            document["signatures"][0]["signature"] = sig[2:]

        is_valid, error = verify_notary_signature(document, account.address)

        assert is_valid is True
        assert error is None

    def test_case_insensitive_address_comparison(self):
        """Test that address comparison is case insensitive."""
        data = {"content": "test"}
        document = create_signed_document(data, TEST_PRIVATE_KEY)
        account = Account.from_key(TEST_PRIVATE_KEY)

        # Use different case
        expected_address = account.address.lower()

        is_valid, error = verify_notary_signature(document, expected_address)

        assert is_valid is True
        assert error is None


class TestExtractNotarySignature:
    """Tests for extract_notary_signature function."""

    def test_extracts_notary_signature(self):
        """Test extraction of notary signature."""
        data = {"content": "test"}
        document = create_signed_document(data, TEST_PRIVATE_KEY)

        sig = extract_notary_signature(document)

        assert sig is not None
        assert sig["type"] == "notary"

    def test_returns_none_for_no_signatures(self):
        """Test returns None when no signatures."""
        document = {"data": "test"}

        sig = extract_notary_signature(document)

        assert sig is None

    def test_returns_none_for_no_notary_type(self):
        """Test returns None when no notary type signature."""
        document = {
            "data": "test",
            "signatures": [{"type": "other", "signer": "0x1234"}],
        }

        sig = extract_notary_signature(document)

        assert sig is None

    def test_extracts_first_notary_signature(self):
        """Test extracts first notary signature when multiple exist."""
        document = {
            "data": "test",
            "signatures": [
                {"type": "other", "signer": "0x1111"},
                {"type": "notary", "signer": "0x2222"},
                {"type": "notary", "signer": "0x3333"},
            ],
        }

        sig = extract_notary_signature(document)

        assert sig["signer"] == "0x2222"


class TestHasNotarySignature:
    """Tests for has_notary_signature function."""

    def test_returns_true_for_signed_document(self):
        """Test returns True for document with notary signature."""
        data = {"content": "test"}
        document = create_signed_document(data, TEST_PRIVATE_KEY)

        assert has_notary_signature(document) is True

    def test_returns_false_for_unsigned_document(self):
        """Test returns False for document without signatures."""
        document = {"data": "test"}

        assert has_notary_signature(document) is False

    def test_returns_false_for_other_signature_types(self):
        """Test returns False when only other signature types."""
        document = {
            "data": "test",
            "signatures": [{"type": "other", "signer": "0x1234"}],
        }

        assert has_notary_signature(document) is False
