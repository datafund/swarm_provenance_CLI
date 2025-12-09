from pydantic import BaseModel, Field, ValidationError
from typing import Optional, List

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
    utilization: int = Field(default=0, description="Utilization percentage")
    usable: bool = Field(description="Whether the stamp is usable for uploads")
    label: Optional[str] = Field(default=None, description="Optional label for the stamp")
    depth: int = Field(description="Stamp depth")
    amount: str = Field(description="Stamp amount (as string for large numbers)")
    bucketDepth: int = Field(description="Bucket depth")
    blockNumber: int = Field(description="Block number when stamp was created")
    immutableFlag: bool = Field(description="Whether the stamp is immutable")
    exists: bool = Field(description="Whether the stamp exists")
    batchTTL: int = Field(description="Time to live in seconds")


class StampListResponse(BaseModel):
    """Response from listing all stamps."""
    stamps: List[StampDetails] = Field(default_factory=list, description="List of stamp batches")
    total_count: int = Field(default=0, description="Total number of stamps")


class StampPurchaseRequest(BaseModel):
    """Request body for purchasing a new stamp."""
    amount: int = Field(description="Amount of BZZ to fund the stamp")
    depth: int = Field(description="Depth of the stamp (determines capacity)")
    label: Optional[str] = Field(default=None, description="Optional label for the stamp")


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
