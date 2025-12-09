"""Custom exceptions for the Swarm Provenance CLI.

Provides unified error handling across both gateway and local Bee backends.
"""


class ProvenanceError(Exception):
    """Base exception for all provenance CLI errors."""
    pass


class ConnectionError(ProvenanceError):
    """Failed to connect to backend (gateway or local Bee)."""
    pass


class StampNotFoundError(ProvenanceError):
    """Stamp does not exist."""
    pass


class StampNotUsableError(ProvenanceError):
    """Stamp exists but is not usable for uploads."""
    pass


class StampPurchaseError(ProvenanceError):
    """Failed to purchase a new stamp."""
    pass


class UploadError(ProvenanceError):
    """Failed to upload data to Swarm."""
    pass


class DownloadError(ProvenanceError):
    """Failed to download data from Swarm."""
    pass


class DataNotFoundError(ProvenanceError):
    """Requested data not found on Swarm."""
    pass


class ValidationError(ProvenanceError):
    """Data validation failed (e.g., hash mismatch, invalid format)."""
    pass


class AuthenticationError(ProvenanceError):
    """Authentication failed (for future API key support)."""
    pass
