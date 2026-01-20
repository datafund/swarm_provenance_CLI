"""
Client for provenance-gateway.datafund.io API.

This client interfaces with the gateway API which provides a simpler
interface to Swarm without requiring a local Bee node.

Supports x402 pay-per-request payments when enabled.
"""

import base64
import json
import requests
import os
from typing import Callable, Optional, Tuple
from urllib.parse import urljoin

from ..exceptions import PaymentRequiredError, PaymentTransactionFailedError
from ..models import (
    StampDetails,
    StampListResponse,
    StampPurchaseResponse,
    StampExtensionResponse,
    DataUploadResponse,
    WalletResponse,
    ChequebookResponse,
    X402PaymentResponse,
)


class GatewayClient:
    """Client for provenance-gateway.datafund.io API.

    Supports optional x402 payment integration for pay-per-request mode.
    When x402 is enabled, protected endpoints (stamp purchase, data upload)
    will automatically handle 402 Payment Required responses.
    """

    DEFAULT_URL = "https://provenance-gateway.datafund.io"

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        x402_enabled: bool = False,
        x402_private_key: Optional[str] = None,
        x402_network: str = "base-sepolia",
        x402_auto_pay: bool = False,
        x402_max_auto_pay_usd: float = 1.00,
        x402_payment_callback: Optional[Callable[[str, str], bool]] = None,
    ):
        """
        Initialize the gateway client.

        Args:
            base_url: Gateway URL. Defaults to provenance-gateway.datafund.io
            api_key: Optional API key for authentication (future use)
            x402_enabled: Enable x402 payment support
            x402_private_key: Private key for signing payments
            x402_network: Network for payments ('base-sepolia' or 'base')
            x402_auto_pay: Auto-pay without prompting (up to max amount)
            x402_max_auto_pay_usd: Maximum auto-pay amount in USD
            x402_payment_callback: Optional callback for payment confirmation.
                                   Called with (amount_usd, description) -> bool
        """
        self.base_url = (base_url or os.getenv("PROVENANCE_GATEWAY_URL", self.DEFAULT_URL)).rstrip("/")
        self.api_key = api_key or os.getenv("PROVENANCE_GATEWAY_API_KEY")

        # x402 configuration
        self.x402_enabled = x402_enabled
        self._x402_private_key = x402_private_key
        self._x402_network = x402_network
        self._x402_auto_pay = x402_auto_pay
        self._x402_max_auto_pay_usd = x402_max_auto_pay_usd
        self._x402_payment_callback = x402_payment_callback
        self._x402_client = None  # Lazy initialization

    def _get_x402_client(self):
        """Get or create the x402 client (lazy initialization)."""
        if self._x402_client is None and self.x402_enabled:
            from .x402_client import X402Client
            self._x402_client = X402Client(
                private_key=self._x402_private_key,
                network=self._x402_network,
            )
        return self._x402_client

    def _get_headers(self) -> dict:
        """Get default headers for requests."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _make_url(self, path: str) -> str:
        """Construct full URL from path."""
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _should_auto_pay(self, amount_usd: float) -> bool:
        """Check if amount is within auto-pay limit."""
        return self._x402_auto_pay and amount_usd <= self._x402_max_auto_pay_usd

    def _handle_402_response(
        self,
        response: requests.Response,
        verbose: bool = False,
    ) -> Tuple[str, str]:
        """
        Handle a 402 Payment Required response.

        Args:
            response: The 402 response from the server
            verbose: Enable debug output

        Returns:
            Tuple of (payment_header, amount_usd_formatted)

        Raises:
            PaymentRequiredError: If x402 not enabled or payment not confirmed
        """
        if not self.x402_enabled:
            # Parse 402 response for useful error message
            try:
                body = response.json()
                accepts = body.get("accepts", [])
                if accepts:
                    amounts = [opt.get("maxAmountRequired", "?") for opt in accepts]
                    raise PaymentRequiredError(
                        f"Payment required (amounts: {amounts}). "
                        "Enable x402 with --x402 flag or X402_ENABLED=true",
                        payment_options=accepts,
                    )
            except (ValueError, KeyError):
                pass
            raise PaymentRequiredError(
                "Payment required. Enable x402 with --x402 flag or X402_ENABLED=true"
            )

        x402_client = self._get_x402_client()

        # Parse the 402 response
        try:
            body = response.json()
        except ValueError as e:
            raise PaymentRequiredError(f"Invalid 402 response: {e}")

        if verbose:
            print(f"DEBUG: Received 402 Payment Required")
            print(f"DEBUG: Payment options: {body}")

        # Parse and select payment option
        requirements = x402_client.parse_402_response(body)
        option = x402_client.select_payment_option(requirements)
        amount_usd = x402_client.format_amount_usd(option.maxAmountRequired)
        amount_float = int(option.maxAmountRequired) / 1_000_000

        if verbose:
            print(f"DEBUG: Selected payment option: {amount_usd} on {option.network}")

        # Check if we should auto-pay or need confirmation
        if not self._should_auto_pay(amount_float):
            if self._x402_payment_callback:
                description = option.description or f"API request to {option.resource}"
                if not self._x402_payment_callback(amount_usd, description):
                    raise PaymentRequiredError(
                        f"Payment of {amount_usd} declined by user",
                        payment_options=[option.model_dump()],
                    )
            elif not self._x402_auto_pay:
                # No callback and not auto-pay mode - raise for CLI to handle
                raise PaymentRequiredError(
                    f"Payment required: {amount_usd}. Use --auto-pay or confirm payment.",
                    payment_options=[option.model_dump()],
                )

        # Sign and create payment header
        payment_header = x402_client.sign_payment(option)

        if verbose:
            print(f"DEBUG: Payment signed, header length: {len(payment_header)}")

        return payment_header, amount_usd

    def _parse_payment_response(
        self,
        response: requests.Response,
        verbose: bool = False,
    ) -> Optional[X402PaymentResponse]:
        """
        Parse the x-payment-response header from a response.

        The header value is base64-encoded JSON containing payment result.

        Args:
            response: The HTTP response
            verbose: Enable debug output

        Returns:
            X402PaymentResponse if header present and valid, None otherwise
        """
        header_value = response.headers.get("x-payment-response")
        if not header_value:
            return None

        try:
            # Header is base64-encoded JSON
            decoded = base64.b64decode(header_value)
            data = json.loads(decoded)
            if verbose:
                print(f"DEBUG: x-payment-response: {data}")
            return X402PaymentResponse.model_validate(data)
        except (ValueError, json.JSONDecodeError) as e:
            if verbose:
                print(f"DEBUG: Failed to parse x-payment-response: {e}")
            return None

    def _make_paid_request(
        self,
        method: str,
        url: str,
        verbose: bool = False,
        **kwargs,
    ) -> requests.Response:
        """
        Make a request with automatic 402 payment handling.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            verbose: Enable debug output
            **kwargs: Additional arguments for requests

        Returns:
            The response (after payment if needed)

        Raises:
            PaymentRequiredError: If payment required but not configured/confirmed
            PaymentTransactionFailedError: If payment was signed but on-chain tx failed
        """
        response = requests.request(method, url, **kwargs)

        if response.status_code == 402:
            payment_header, amount_usd = self._handle_402_response(response, verbose)

            # Add payment header and retry
            headers = kwargs.get("headers", {}).copy()
            headers["X-PAYMENT"] = payment_header
            kwargs["headers"] = headers

            if verbose:
                print(f"DEBUG: Retrying request with X-PAYMENT header ({amount_usd})")

            response = requests.request(method, url, **kwargs)

            if verbose:
                print(f"DEBUG: Paid request status: {response.status_code}")

            # Check x-payment-response header to verify payment actually succeeded
            payment_result = self._parse_payment_response(response, verbose)
            if payment_result:
                if not payment_result.success:
                    # Payment was signed but the on-chain transaction failed
                    # Gateway may have fallen back to free tier
                    error_msg = (
                        f"Payment transaction failed: {payment_result.errorReason or 'unknown error'}. "
                        "The gateway may have used free tier instead."
                    )
                    if verbose:
                        print(f"WARNING: {error_msg}")
                    raise PaymentTransactionFailedError(
                        error_msg,
                        error_reason=payment_result.errorReason,
                        payer=payment_result.payer,
                    )
                else:
                    if verbose:
                        tx_hash = payment_result.transaction or "pending"
                        print(f"DEBUG: Payment successful, tx: {tx_hash}")

        return response

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
            # Use _make_paid_request for x402 support
            response = self._make_paid_request(
                "POST",
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=120,
                verbose=verbose,
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

            # Use _make_paid_request for x402 support
            response = self._make_paid_request(
                "POST",
                url,
                params=params,
                files=files,
                headers=headers,
                timeout=60,
                verbose=verbose,
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
