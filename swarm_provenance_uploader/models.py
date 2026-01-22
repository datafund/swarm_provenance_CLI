from pydantic import BaseModel, Field, ValidationError
from typing import Any, Dict, Optional, List

class ProvenanceMetadata(BaseModel):
    """
     Defines the structure for the metadata JSON that wraps
     the base64-encoded provenance data.
    """
    data: str = Field(description="Base64 encoded string of the original provenance file content.")
    content_hash: str = Field(description="SHA256 hash of the original, raw provenance file content.")
    stamp_id: str = Field(description="Swarm Postage Stamp ID used for this upload.")
    provenance_standard: Optional[str] = Field(default=None, description="Identifier for the provenance standard used (e.g., 'PROV-O').")
    encryption: Optional[str] = Field(default=None, description="Details about encryption scheme, if any, used on ORIGINAL data.")


# --- Gateway API Response Models ---

class StampDetails(BaseModel):
    """Details of a postage stamp batch."""
    batchID: str = Field(description="The batch ID (stamp ID)")
    utilization: Optional[int] = Field(default=None, description="Utilization percentage (may be null)")
    usable: bool = Field(description="Whether the stamp is usable for uploads")
    label: Optional[str] = Field(default=None, description="Optional label for the stamp")
    depth: int = Field(description="Stamp depth")
    amount: str = Field(description="Stamp amount (as string for large numbers)")
    bucketDepth: int = Field(description="Bucket depth")
    immutableFlag: bool = Field(description="Whether the stamp is immutable")
    batchTTL: int = Field(description="Time to live in seconds")
    # Optional fields that may or may not be present depending on API version
    blockNumber: Optional[int] = Field(default=None, description="Block number when stamp was created")
    exists: Optional[bool] = Field(default=None, description="Whether the stamp exists")
    start: Optional[int] = Field(default=None, description="Start block number")
    owner: Optional[str] = Field(default=None, description="Owner address")
    expectedExpiration: Optional[str] = Field(default=None, description="Expected expiration date")
    local: Optional[bool] = Field(default=None, description="Whether stamp is local")


class StampListResponse(BaseModel):
    """Response from listing all stamps."""
    stamps: List[StampDetails] = Field(default_factory=list, description="List of stamp batches")
    total_count: int = Field(default=0, description="Total number of stamps")


class StampPurchaseRequest(BaseModel):
    """Request body for purchasing a new stamp (gateway API)."""
    duration_hours: Optional[int] = Field(default=None, ge=24, description="Hours of validity (min 24, default 25)")
    size: Optional[str] = Field(default=None, description="Preset size: 'small', 'medium', or 'large'")
    depth: Optional[int] = Field(default=None, ge=16, le=32, description="Technical depth parameter (16-32)")
    label: Optional[str] = Field(default=None, description="Optional label for the stamp")
    amount: Optional[int] = Field(default=None, description="Legacy: PLUR amount (use duration_hours instead)")


class StampPurchaseResponse(BaseModel):
    """Response from purchasing a stamp."""
    batchID: str = Field(description="The newly created batch ID")
    message: Optional[str] = Field(default=None, description="Status message")


class StampExtensionRequest(BaseModel):
    """Request body for extending a stamp."""
    amount: int = Field(description="Amount of BZZ to add to the stamp")


class StampExtensionResponse(BaseModel):
    """Response from extending a stamp."""
    batchID: str = Field(description="The extended batch ID")
    message: Optional[str] = Field(default=None, description="Status message")


class DataUploadResponse(BaseModel):
    """Response from uploading data."""
    reference: str = Field(description="Swarm reference hash")
    message: Optional[str] = Field(default=None, description="Status message")


class DataDownloadResponse(BaseModel):
    """Response from downloading data as JSON."""
    data: str = Field(description="Base64 encoded data")
    content_type: str = Field(description="Content type of the data")
    size: int = Field(description="Size of the data in bytes")
    reference: str = Field(description="Swarm reference hash")


class WalletResponse(BaseModel):
    """Response from wallet endpoint."""
    walletAddress: str = Field(description="Ethereum wallet address")
    bzzBalance: str = Field(description="BZZ balance (as string for precision)")


class ChequebookResponse(BaseModel):
    """Response from chequebook endpoint."""
    chequebookAddress: str = Field(description="Chequebook contract address")
    availableBalance: str = Field(description="Available balance")
    totalBalance: str = Field(description="Total balance")


# --- x402 Payment Models ---

class X402PaymentOption(BaseModel):
    """A single payment option from the 402 response accepts array."""
    scheme: str = Field(description="Payment scheme (e.g., 'exact')")
    network: str = Field(description="Network identifier (e.g., 'base-sepolia', 'base')")
    maxAmountRequired: str = Field(description="Maximum payment amount in smallest units")
    resource: str = Field(description="Resource being paid for")
    description: Optional[str] = Field(default=None, description="Human-readable description")
    mimeType: Optional[str] = Field(default=None, description="MIME type of resource")
    payTo: str = Field(description="Address to pay to")
    maxTimeoutSeconds: Optional[int] = Field(default=None, description="Max timeout for payment")
    asset: Optional[str] = Field(default=None, description="Asset/token contract address")
    extra: Optional[dict] = Field(default=None, description="Additional provider-specific data")


class X402PaymentRequirements(BaseModel):
    """Parsed from HTTP 402 response."""
    accepts: List[X402PaymentOption] = Field(description="List of accepted payment options")
    error: Optional[str] = Field(default=None, description="Error message if present")
    x402Version: int = Field(default=1, description="x402 protocol version")


class X402PaymentAuthorization(BaseModel):
    """Authorization data for payment signature."""
    from_address: str = Field(alias="from", description="Payer wallet address")
    to: str = Field(description="Recipient address")
    value: str = Field(description="Payment amount in smallest units")
    validAfter: int = Field(default=0, description="Timestamp after which payment is valid")
    validBefore: int = Field(description="Timestamp before which payment is valid")
    nonce: str = Field(description="Unique nonce for this payment")


class X402PaymentPayload(BaseModel):
    """Payload for X-PAYMENT header."""
    x402Version: int = Field(default=1, description="x402 protocol version")
    scheme: str = Field(default="exact", description="Payment scheme")
    network: str = Field(description="Network identifier")
    payload: dict = Field(description="Contains signature and authorization data")


class X402PaymentResponse(BaseModel):
    """Response from x-payment-response header after payment attempt."""
    success: bool = Field(description="Whether the payment was successful")
    errorReason: Optional[str] = Field(default=None, description="Error reason if payment failed")
    transaction: Optional[str] = Field(default=None, description="Transaction hash if successful")
    network: Optional[str] = Field(default=None, description="Network the payment was made on")
    payer: Optional[str] = Field(default=None, description="Address of the payer")


# --- Stamp Pool Models ---

class PoolStatusResponse(BaseModel):
    """Response from pool status endpoint."""
    enabled: bool = Field(description="Whether the stamp pool is enabled")
    reserve_config: Dict[str, int] = Field(description="Target reserve levels by depth")
    current_levels: Dict[str, int] = Field(description="Current stamp counts by depth")
    available_stamps: Dict[str, List[str]] = Field(description="Available batch IDs by depth")
    total_stamps: int = Field(description="Total number of stamps in pool")
    low_reserve_warning: bool = Field(description="True if pool is below target reserve")
    last_check: Optional[str] = Field(default=None, description="ISO timestamp of last maintenance check")
    next_check: Optional[str] = Field(default=None, description="ISO timestamp of next scheduled check")
    errors: List[str] = Field(default_factory=list, description="Any errors from last check")


class AcquireStampRequest(BaseModel):
    """Request body for acquiring stamp from pool."""
    size: Optional[str] = Field(default=None, description="Preferred size: 'small', 'medium', 'large'")
    depth: Optional[int] = Field(default=None, description="Specific depth (overrides size)")


class AcquireStampResponse(BaseModel):
    """Response from pool acquire endpoint."""
    success: bool = Field(description="Whether acquisition was successful")
    batch_id: Optional[str] = Field(default=None, description="Acquired stamp batch ID")
    depth: Optional[int] = Field(default=None, description="Depth of acquired stamp")
    size_name: Optional[str] = Field(default=None, description="Size name of acquired stamp")
    message: str = Field(description="Status message")
    fallback_used: bool = Field(description="True if a larger stamp was substituted")


class PoolStampInfo(BaseModel):
    """Information about a stamp in the pool."""
    batch_id: str = Field(description="Stamp batch ID")
    depth: int = Field(description="Stamp depth")
    size_name: str = Field(description="Size name (small/medium/large)")
    created_at: str = Field(description="ISO timestamp when stamp was created")
    ttl_at_creation: int = Field(description="TTL in seconds at creation time")


class StampHealthIssue(BaseModel):
    """A health issue (error or warning) for a stamp."""
    code: str = Field(description="Issue code (e.g., 'EXPIRED', 'LOW_TTL')")
    message: str = Field(description="Human-readable message")
    details: Optional[Dict] = Field(default=None, description="Additional details")


class StampHealthCheckResponse(BaseModel):
    """Response from stamp health check endpoint."""
    stamp_id: str = Field(description="The stamp batch ID")
    can_upload: bool = Field(description="Whether the stamp can be used for uploads")
    errors: List[StampHealthIssue] = Field(default_factory=list, description="Blocking issues")
    warnings: List[StampHealthIssue] = Field(default_factory=list, description="Non-blocking warnings")
    status: Optional[Dict] = Field(default=None, description="Detailed status metrics")


# --- Notary Signing Models ---

class NotaryInfoResponse(BaseModel):
    """Response from GET /api/v1/notary/info endpoint."""
    enabled: bool = Field(description="Whether notary signing is enabled on this gateway")
    available: bool = Field(description="Whether notary signing is currently available (enabled + configured)")
    address: Optional[str] = Field(default=None, description="Ethereum address of the notary signer")
    message: Optional[str] = Field(default=None, description="Human-readable status message")


class NotaryStatusResponse(BaseModel):
    """Response from GET /api/v1/notary/status endpoint (simplified health check)."""
    enabled: bool = Field(description="Whether notary signing is enabled")
    available: bool = Field(description="Whether notary signing is available")
    address: Optional[str] = Field(default=None, description="Notary signer address")


class NotarySignature(BaseModel):
    """A notary signature within a signed document."""
    type: str = Field(description="Signature type, e.g., 'notary'")
    signer: str = Field(description="Ethereum address of the signer")
    timestamp: str = Field(description="ISO 8601 timestamp when signature was created")
    data_hash: str = Field(description="SHA256 hash of the canonical JSON of the data field")
    signature: str = Field(description="EIP-191 signature (hex string, may include 0x prefix)")
    hashed_fields: List[str] = Field(description="List of field names whose values were hashed (typically ['data'])")
    signed_message_format: str = Field(description="Format of the signed message, e.g., '{data_hash}|{timestamp}'")


class SignedDocumentResponse(BaseModel):
    """Response when uploading with sign=notary parameter.

    Contains both the Swarm reference and the full signed document.
    """
    reference: str = Field(description="Swarm reference hash")
    signed_document: Optional[Dict[str, Any]] = Field(
        default=None,
        description="The full signed document including data and signatures array"
    )
    message: Optional[str] = Field(default=None, description="Status message")
