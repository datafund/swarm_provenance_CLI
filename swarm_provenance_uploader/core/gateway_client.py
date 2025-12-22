"""
Client for provenance-gateway.datafund.io API.

This client interfaces with the gateway API which provides a simpler
interface to Swarm without requiring a local Bee node.
"""

import requests
import os
from urllib.parse import urljoin
from typing import Optional

from ..models import (
    StampDetails,
    StampListResponse,
    StampPurchaseResponse,
    StampExtensionResponse,
    DataUploadResponse,
    WalletResponse,
    ChequebookResponse,
)


class GatewayClient:
    """Client for provenance-gateway.datafund.io API."""

    DEFAULT_URL = "https://provenance-gateway.datafund.io"

    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize the gateway client.

        Args:
            base_url: Gateway URL. Defaults to provenance-gateway.datafund.io
            api_key: Optional API key for authentication (future use)
        """
        self.base_url = (base_url or os.getenv("PROVENANCE_GATEWAY_URL", self.DEFAULT_URL)).rstrip("/")
        self.api_key = api_key or os.getenv("PROVENANCE_GATEWAY_API_KEY")

    def _get_headers(self) -> dict:
        """Get default headers for requests."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _make_url(self, path: str) -> str:
        """Construct full URL from path."""
        return urljoin(self.base_url + "/", path.lstrip("/"))

    # --- Health ---

    def health_check(self, verbose: bool = False) -> bool:
        """
        Check if the gateway is healthy.

        Returns:
            True if gateway is reachable and healthy.
        """
        url = self._make_url("/")
        if verbose:
            print(f"--- DEBUG: Health Check ---")
            print(f"URL: GET {url}")

        try:
            response = requests.get(url, timeout=10)
            if verbose:
                print(f"DEBUG: Health check status: {response.status_code}")
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Health check failed: {e}")
            return False

    # --- Stamps ---

    def list_stamps(self, verbose: bool = False) -> StampListResponse:
        """
        List all postage stamp batches.

        Returns:
            StampListResponse with list of stamps and total count.
        """
        url = self._make_url("/api/v1/stamps/")
        if verbose:
            print(f"--- DEBUG: List Stamps ---")
            print(f"URL: GET {url}")

        try:
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            if verbose:
                print(f"DEBUG: List stamps status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            return StampListResponse.model_validate(data)
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: List stamps failed: {e}")
            raise ConnectionError(f"Failed to list stamps: {e}") from e

    def purchase_stamp(
        self,
        duration_hours: Optional[int] = None,
        size: Optional[str] = None,
        depth: Optional[int] = None,
        label: Optional[str] = None,
        amount: Optional[int] = None,
        verbose: bool = False
    ) -> str:
        """
        Purchase a new postage stamp.

        Args:
            duration_hours: Hours of validity (min 24, default 25)
            size: Preset size - 'small', 'medium', or 'large'
            depth: Technical depth parameter (16-32)
            label: Optional label for the stamp
            amount: Legacy - PLUR amount (use duration_hours instead)
            verbose: Enable debug output

        Returns:
            The batch ID (stamp ID) of the newly created stamp.
        """
        url = self._make_url("/api/v1/stamps/")
        payload = {}

        # New duration-based parameter (preferred)
        if duration_hours is not None:
            payload["duration_hours"] = duration_hours

        # Size preset
        if size is not None:
            payload["size"] = size

        # Depth parameter
        if depth is not None:
            payload["depth"] = depth

        # Label
        if label is not None:
            payload["label"] = label

        # Legacy amount (for backwards compatibility)
        if amount is not None:
            payload["amount"] = amount

        if verbose:
            print(f"--- DEBUG: Purchase Stamp ---")
            print(f"URL: POST {url}")
            print(f"Payload: {payload}")

        try:
            response = requests.post(
                url, json=payload, headers=self._get_headers(), timeout=120
            )
            if verbose:
                print(f"DEBUG: Purchase stamp status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            result = StampPurchaseResponse.model_validate(data)
            if verbose:
                print(f"DEBUG: Purchased stamp ID: {result.batchID}")
            return result.batchID
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Purchase stamp failed: {e}")
            raise ConnectionError(f"Failed to purchase stamp: {e}") from e

    def get_stamp(self, stamp_id: str, verbose: bool = False) -> Optional[StampDetails]:
        """
        Get details of a specific stamp.

        Args:
            stamp_id: The stamp batch ID
            verbose: Enable debug output

        Returns:
            StampDetails if found, None if stamp doesn't exist.
        """
        url = self._make_url(f"/api/v1/stamps/{stamp_id.lower()}")
        if verbose:
            print(f"--- DEBUG: Get Stamp ---")
            print(f"URL: GET {url}")

        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            if verbose:
                print(f"DEBUG: Get stamp status: {response.status_code}")
            if response.status_code == 404:
                if verbose:
                    print(f"DEBUG: Stamp {stamp_id} not found")
                return None
            response.raise_for_status()
            data = response.json()
            return StampDetails.model_validate(data)
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Get stamp failed: {e}")
            raise ConnectionError(f"Failed to get stamp {stamp_id}: {e}") from e

    def extend_stamp(self, stamp_id: str, amount: int, verbose: bool = False) -> str:
        """
        Extend an existing stamp by adding funds.

        Args:
            stamp_id: The stamp batch ID to extend
            amount: Amount of BZZ to add
            verbose: Enable debug output

        Returns:
            The batch ID of the extended stamp.
        """
        url = self._make_url(f"/api/v1/stamps/{stamp_id.lower()}/extend")
        payload = {"amount": amount}

        if verbose:
            print(f"--- DEBUG: Extend Stamp ---")
            print(f"URL: PATCH {url}")
            print(f"Payload: {payload}")

        try:
            response = requests.patch(
                url, json=payload, headers=self._get_headers(), timeout=60
            )
            if verbose:
                print(f"DEBUG: Extend stamp status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            result = StampExtensionResponse.model_validate(data)
            if verbose:
                print(f"DEBUG: Extended stamp ID: {result.batchID}")
            return result.batchID
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Extend stamp failed: {e}")
            raise ConnectionError(f"Failed to extend stamp {stamp_id}: {e}") from e

    # --- Data ---

    def upload_data(
        self,
        data: bytes,
        stamp_id: str,
        content_type: str = "application/json",
        verbose: bool = False,
    ) -> str:
        """
        Upload data to Swarm via the gateway.

        Args:
            data: The bytes to upload
            stamp_id: Postage stamp ID to use
            content_type: Content type of the data
            verbose: Enable debug output

        Returns:
            The Swarm reference hash.
        """
        url = self._make_url("/api/v1/data/")
        params = {"stamp_id": stamp_id.lower(), "content_type": content_type}

        if verbose:
            print(f"--- DEBUG: Upload Data ---")
            print(f"URL: POST {url}")
            print(f"Params: {params}")
            print(f"Data size: {len(data)} bytes")

        try:
            # Gateway expects multipart form data
            files = {"file": ("data", data, content_type)}
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            response = requests.post(
                url, params=params, files=files, headers=headers, timeout=60
            )
            if verbose:
                print(f"DEBUG: Upload status: {response.status_code}")
            response.raise_for_status()
            data_response = response.json()
            result = DataUploadResponse.model_validate(data_response)
            if verbose:
                print(f"DEBUG: Upload reference: {result.reference}")
            return result.reference
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Upload failed: {e}")
            raise ConnectionError(f"Failed to upload data: {e}") from e

    def download_data(self, reference: str, verbose: bool = False) -> bytes:
        """
        Download data from Swarm via the gateway.

        Args:
            reference: Swarm reference hash
            verbose: Enable debug output

        Returns:
            The raw bytes of the content.
        """
        url = self._make_url(f"/api/v1/data/{reference.lower()}")
        if verbose:
            print(f"--- DEBUG: Download Data ---")
            print(f"URL: GET {url}")

        try:
            response = requests.get(url, timeout=60)
            if verbose:
                print(f"DEBUG: Download status: {response.status_code}")
            if response.status_code == 404:
                raise FileNotFoundError(f"Data not found on Swarm: {reference}")
            response.raise_for_status()
            if verbose:
                print(f"DEBUG: Downloaded {len(response.content)} bytes")
            return response.content
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Download failed: {e}")
            raise ConnectionError(f"Failed to download {reference}: {e}") from e

    # --- Wallet ---

    def get_wallet(self, verbose: bool = False) -> WalletResponse:
        """
        Get wallet information.

        Returns:
            WalletResponse with address and balance.
        """
        url = self._make_url("/api/v1/wallet")
        if verbose:
            print(f"--- DEBUG: Get Wallet ---")
            print(f"URL: GET {url}")

        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            if verbose:
                print(f"DEBUG: Get wallet status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            return WalletResponse.model_validate(data)
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Get wallet failed: {e}")
            raise ConnectionError(f"Failed to get wallet info: {e}") from e

    def get_chequebook(self, verbose: bool = False) -> ChequebookResponse:
        """
        Get chequebook information.

        Returns:
            ChequebookResponse with address and balances.
        """
        url = self._make_url("/api/v1/chequebook")
        if verbose:
            print(f"--- DEBUG: Get Chequebook ---")
            print(f"URL: GET {url}")

        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            if verbose:
                print(f"DEBUG: Get chequebook status: {response.status_code}")
            response.raise_for_status()
            data = response.json()
            return ChequebookResponse.model_validate(data)
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Get chequebook failed: {e}")
            raise ConnectionError(f"Failed to get chequebook info: {e}") from e
