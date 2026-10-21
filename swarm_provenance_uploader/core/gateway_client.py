"""
Client for provenance-gateway.datafund.io API.

This client interfaces with the gateway API which provides a simpler
interface to Swarm without requiring a local Bee node.

Supports x402 pay-per-request payments when enabled.
"""

import base64
import inspect
import ipaddress
import json
import requests
import os
import re
import time
import unicodedata
import uuid
import warnings
from contextlib import contextmanager
from decimal import Decimal
from typing import Callable, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from ..exceptions import (
    IdempotencyKeyError,
    InsecureGatewayWarning,
    PaymentDeliveredNotStoredError,
    PaymentOutcomeUnknownError,
    PaymentRejectedError,
    PaymentRequiredError,
    PaymentSettledNotDeliveredError,
    PaymentTransactionFailedError,
    StampPurchasePendingError,
    PoolNotEnabledError,
    PoolEmptyError,
    PoolAcquisitionError,
    StampNotFoundError,
    NotaryNotEnabledError,
    NotaryNotConfiguredError,
    InvalidDocumentFormatError,
)
from ..models import (
    StampDetails,
    StampListResponse,
    StampPurchaseResponse,
    StampExtensionResponse,
    DataUploadResponse,
    WalletResponse,
    ChequebookResponse,
    X402PaymentResponse,
    PoolStatusResponse,
    AcquireStampResponse,
    PoolStampInfo,
    StampHealthCheckResponse,
    NotaryInfoResponse,
    NotaryStatusResponse,
    SignedDocumentResponse,
    ManifestUploadResponse,
    ManifestUploadTiming,
)


IDEMPOTENCY_HEADER = "Idempotency-Key"


def is_valid_idempotency_key(key: str) -> bool:
    """The gateway's rule: 1-255 printable ASCII characters."""
    return 0 < len(key) <= 255 and key.isascii() and key.isprintable()


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_insecure_gateway_url(url: str) -> bool:
    """True for a plain-http URL that is not on this machine (loopback)."""
    parsed = urlparse(url)
    return parsed.scheme == "http" and not _is_loopback_host(parsed.hostname or "")


def _sanitize_gateway_text(text: Optional[str], limit: int = 80) -> Optional[str]:
    """Gateway-authored text made safe to show next to a payment prompt.

    Control characters (which could redraw the terminal) and invisible
    formatting characters (bidi overrides, zero-width) are dropped,
    whitespace is collapsed and the result is truncated.
    """
    if not text:
        return None
    text = "".join(
        " " if unicodedata.category(ch) in ("Cc", "Cf") else ch for ch in str(text)
    )
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text or None


class GatewayClient:
    """Client for provenance-gateway.datafund.io API.

    Supports optional x402 payment integration for pay-per-request mode.
    When x402 is enabled, protected endpoints (stamp purchase, data upload)
    will automatically handle 402 Payment Required responses.
    """

    DEFAULT_URL = "https://provenance-gateway.datafund.io"

    # (connect, read) timeout for requests that may carry a payment. The read
    # timeout must outlast the gateway's own work after settling: for a paid
    # stamp purchase that is the settlement, up to 120 s waiting on Bee and up
    # to 30 s looking the batch up afterwards. A client that gives up first sees
    # a failure for a request that was paid and usually delivered. The connect
    # timeout stays short: a gateway that cannot be reached was never paid.
    PAID_REQUEST_TIMEOUT = (10, 240)

    # How long to keep retrying a paid request the gateway answers with
    # IDEMPOTENCY_KEY_IN_PROGRESS (the first request with the key is still
    # running) or IDEMPOTENCY_UNAVAILABLE. Each retry carries the same key and a
    # new authorization, and the gateway settles at most one of them.
    IDEMPOTENT_RETRY_WINDOW = 300
    IDEMPOTENCY_UNAVAILABLE_RETRIES = 3
    # The gateway releases an authorization it answers with IN_PROGRESS or
    # UNAVAILABLE, so retries resend it; a new one is signed only after an
    # attempt whose own outcome is unknown, or when it is about to expire.
    # Each signature is valid for the full amount, so their number is capped.
    MAX_SIGNATURES_PER_OPERATION = 3
    RESIGN_BEFORE_EXPIRY_SECONDS = 60

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        x402_enabled: bool = False,
        x402_private_key: Optional[str] = None,
        x402_network: str = "base-sepolia",
        x402_auto_pay: bool = False,
        x402_max_auto_pay_usd: float = 1.00,
        x402_payment_callback: Optional[Callable[..., bool]] = None,
        free_tier: bool = False,
        x402_on_payment_sent: Optional[Callable[[dict], None]] = None,
        x402_expected_pay_to: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        idempotency_key_given: Optional[bool] = None,
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
            x402_max_auto_pay_usd: Maximum auto-pay amount in USD. With auto-pay
                                   and no callback this is a hard cap: a larger
                                   amount is refused before anything is signed.
            x402_payment_callback: Optional callback for payment confirmation,
                                   asked for any amount not auto-paid.
                                   Called with (amount_usd, description) -> bool;
                                   a callback with a parameter named `option`
                                   gets the X402PaymentOption (network, payTo,
                                   asset) as well, as a keyword argument.
            free_tier: Send X-Payment-Mode: free header (rate-limited)
            x402_on_payment_sent: Optional hook called with the payment's details
                                  (payer, nonce, amount, amount_usd, pay_to,
                                  network, transaction) once a signed payment has
                                  been sent and not refused.
            x402_expected_pay_to: Only sign payments to this address (falls back
                                  to the X402_EXPECTED_PAY_TO env var).
            idempotency_key: Idempotency-Key sent with every paid request. The
                             gateway scopes it to (payer, method, path), so one
                             key can serve one command's stamp purchase and
                             upload. Pass the key of an earlier run to have a
                             retry answered from that run's result instead of
                             charged again. If None, each paid operation gets
                             a fresh random key.
            idempotency_key_given: Whether a person chose `idempotency_key`
                                   (so a key refused as reused is their
                                   mistake, not a bug). Defaults to whether
                                   idempotency_key was passed.

        Warns:
            InsecureGatewayWarning: If x402 is enabled and the gateway URL is
                                    plain http on a non-loopback host.
        """
        self.base_url = (base_url or os.getenv("PROVENANCE_GATEWAY_URL", self.DEFAULT_URL)).rstrip("/")
        self.api_key = api_key or os.getenv("PROVENANCE_GATEWAY_API_KEY")
        self.free_tier = free_tier

        # x402 configuration
        self.x402_enabled = x402_enabled
        self._x402_private_key = x402_private_key  # gitleaks:allow (a variable name, not a key)
        self._x402_network = x402_network
        self._x402_auto_pay = x402_auto_pay
        self._x402_max_auto_pay_usd = x402_max_auto_pay_usd
        self._x402_payment_callback = x402_payment_callback
        self._x402_on_payment_sent = x402_on_payment_sent
        self._x402_expected_pay_to = x402_expected_pay_to
        self._x402_client = None  # Lazy initialization
        if idempotency_key is not None and not is_valid_idempotency_key(idempotency_key):
            raise ValueError("Idempotency-Key must be 1-255 printable ASCII characters")
        self.idempotency_key = idempotency_key
        self._idempotency_key_given = (idempotency_key is not None if idempotency_key_given is None
                                       else idempotency_key_given)

        if self.x402_enabled and is_insecure_gateway_url(self.base_url):
            warnings.warn(
                f"x402 payments are enabled but the gateway URL {self.base_url} is plain "
                "http: the payment request (amount, recipient) can be altered in transit. "
                "Use https.",
                InsecureGatewayWarning,
                stacklevel=2,
            )

    def _get_x402_client(self):
        """Get or create the x402 client (lazy initialization)."""
        if self._x402_client is None and self.x402_enabled:
            from .x402_client import X402Client
            self._x402_client = X402Client(
                private_key=self._x402_private_key,
                network=self._x402_network,
                expected_pay_to=self._x402_expected_pay_to,
            )
        return self._x402_client

    def _get_headers(self) -> dict:
        """Get default headers for requests."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.free_tier:
            headers["X-Payment-Mode"] = "free"
        return headers

    def _make_url(self, path: str) -> str:
        """Construct full URL from path."""
        return urljoin(self.base_url + "/", path.lstrip("/"))

    def _should_auto_pay(self, amount_usd) -> bool:
        """Check if amount (USD, float or Decimal) is within auto-pay limit."""
        return bool(self._x402_auto_pay and amount_usd <= self._x402_max_auto_pay_usd)

    def _handle_402_response(
        self,
        response: requests.Response,
        verbose: bool = False,
        method: Optional[str] = None,
        url: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Handle a 402 Payment Required response: approve and sign one payment.

        Returns:
            Tuple of (payment_header, amount_usd_formatted)
        """
        payment_header, amount_usd, _ = self._approve_payment(response, verbose, method, url)
        return payment_header, amount_usd

    def _approve_payment(
        self,
        response: requests.Response,
        verbose: bool = False,
        method: Optional[str] = None,
        url: Optional[str] = None,
    ) -> Tuple[str, str, object]:
        """
        Handle a 402 Payment Required response.

        Args:
            response: The 402 response from the server
            verbose: Enable debug output
            method: Method of the request being paid for (shown to the user)
            url: URL of the request being paid for, before any redirect

        Returns:
            Tuple of (payment_header, amount_usd_formatted, approved X402PaymentOption)

        Raises:
            PaymentRequiredError: If x402 not enabled or payment not confirmed
        """
        if not self.x402_enabled:
            # Parse 402 response for useful error message
            try:
                body = response.json()
                # Unwrap detail wrapper from new gateway format
                if "detail" in body and isinstance(body["detail"], dict):
                    body = body["detail"]
                accepts = body.get("accepts", [])
                if accepts:
                    amounts = [opt.get("maxAmountRequired", "?") for opt in accepts]
                    raise PaymentRequiredError(
                        f"Payment required (amounts: {amounts}). "
                        "Enable x402 with --x402 flag or use --free for free tier",
                        payment_options=accepts,
                    )
            except (ValueError, KeyError):
                pass
            raise PaymentRequiredError(
                "Payment required. Enable x402 with --x402 flag or use --free for free tier"
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
        # Exact, and no float overflow for an absurdly long amount
        amount_float = Decimal(int(option.maxAmountRequired)).scaleb(-6)

        if verbose:
            print(f"DEBUG: Selected payment option: {amount_usd} on {option.network}")

        # Check if we should auto-pay or need confirmation
        if not self._should_auto_pay(amount_float):
            if self._x402_payment_callback:
                if not self._confirm_payment(amount_usd, option, method, url):
                    raise PaymentRequiredError(
                        f"Payment of {amount_usd} declined by user",
                        payment_options=[option.model_dump()],
                    )
            elif self._x402_auto_pay:
                # Above the auto-pay limit and nobody to ask: the limit is a
                # hard cap, so refuse before anything is signed.
                raise PaymentRequiredError(
                    f"Payment of {amount_usd} exceeds the auto-pay limit of "
                    f"${self._x402_max_auto_pay_usd:.6f}; nothing was signed. "
                    "Raise the limit or confirm the payment interactively.",
                    payment_options=[option.model_dump()],
                )
            else:
                # No callback and not auto-pay mode - raise for CLI to handle
                raise PaymentRequiredError(
                    f"Payment required: {amount_usd}. Use --auto-pay or confirm payment.",
                    payment_options=[option.model_dump()],
                )

        # Sign and create payment header
        payment_header = x402_client.sign_payment(option)

        if verbose:
            print(f"DEBUG: Payment signed, header length: {len(payment_header)}")

        return payment_header, amount_usd, option

    @staticmethod
    def _describe_request(option, method: Optional[str] = None, url: Optional[str] = None) -> str:
        """
        What a payment is for, as shown to the user.

        Led by the request this client is paying for (method and path, as the
        client sends it, not where a redirect ended up), which the gateway
        cannot change. The gateway's own description follows, cleaned and
        marked as the gateway's words, so it cannot pose as the prompt.
        """
        if isinstance(method, str) and isinstance(url, str):
            described = f"{method} {urlparse(url).path or '/'}"
        else:
            described = f"API request to {_sanitize_gateway_text(option.resource) or 'unknown resource'}"
        note = _sanitize_gateway_text(option.description)
        if note:
            described += f' (gateway says: "{note}")'
        return described

    def _confirm_payment(self, amount_usd: str, option, method: Optional[str] = None,
                         url: Optional[str] = None) -> bool:
        """Ask the payment callback, passing the option if it accepts one."""
        callback = self._x402_payment_callback
        description = self._describe_request(option, method, url)
        try:
            params = inspect.signature(callback).parameters.values()
            # Only a callback that names an `option` parameter gets it; one with
            # **kwargs may forward them somewhere that does not expect it.
            takes_option = any(
                p.name == "option" and p.kind != inspect.Parameter.POSITIONAL_ONLY for p in params
            )
        except (TypeError, ValueError):
            takes_option = False
        if takes_option:
            return bool(callback(amount_usd, description, option=option))
        return bool(callback(amount_usd, description))

    def _notify_payment_sent(self, payment: dict) -> None:
        """Tell the x402_on_payment_sent hook; a failing hook never breaks the request."""
        if self._x402_on_payment_sent:
            try:
                self._x402_on_payment_sent(dict(payment))
            except Exception:
                pass

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
        response.x402_payment = None
        if response.status_code != 402:
            return response

        payment_header, amount_usd, option = self._approve_payment(response, verbose, method, url)
        # One key for every attempt of this paid operation (#124); the gateway
        # charges at most one attempt carrying it.
        key = self.idempotency_key or str(uuid.uuid4())
        base_headers = dict(kwargs.get("headers") or {})
        deadline = time.monotonic() + self.IDEMPOTENT_RETRY_WINDOW
        unavailable_left = self.IDEMPOTENCY_UNAVAILABLE_RETRIES
        signatures = 1
        # Proven once the gateway answers with an IDEMPOTENCY_* code. Until
        # then a gateway may ignore the key, and an automatic retry could pay
        # a second time.
        gateway_honours_key = False
        # The first attempt that reached the gateway without an answer: the
        # one that may have been collected. While it is set, nothing but an
        # IDEMPOTENCY_* answer or a success says what happened to it.
        outstanding = None

        def unknown(reason: str):
            self._notify_payment_sent(outstanding)
            return PaymentOutcomeUnknownError(f"{reason} The payment may have been taken.", **outstanding)

        def new_authorization() -> str:
            nonlocal signatures
            if option is None or signatures >= self.MAX_SIGNATURES_PER_OPERATION:
                raise PaymentRejectedError(
                    f"Stopped retrying after {signatures} signed payment(s) for one request.",
                    reason="retry limit",
                )
            signatures += 1
            return self._get_x402_client().sign_payment(option)

        while True:
            payment = self._describe_payment(payment_header, amount_usd)
            payment["idempotency_key"] = key
            kwargs["headers"] = {**base_headers, "X-PAYMENT": payment_header, IDEMPOTENCY_HEADER: key}

            if verbose:
                print(f"DEBUG: Sending paid request ({amount_usd}, {IDEMPOTENCY_HEADER}: {key})")

            # From here on the signed authorization has left the client. Any
            # failure that does not prove it was not collected is reported as
            # an unknown outcome, never as a plain connection error.
            try:
                response = requests.request(method, url, **kwargs)
            except (requests.exceptions.RequestException, KeyboardInterrupt) as e:
                # ConnectTimeout: never connected, so this attempt was never sent.
                never_sent = isinstance(e, requests.exceptions.ConnectTimeout)
                if never_sent and outstanding is None:
                    raise  # an ordinary failure: nothing was charged
                if not never_sent and outstanding is None:
                    outstanding = payment
                interrupted = isinstance(e, KeyboardInterrupt)
                reason = ("Interrupted while waiting for the paid request." if interrupted
                          else f"The paid request did not complete ({type(e).__name__}).")
                if not (gateway_honours_key and not interrupted and time.monotonic() < deadline):
                    raise unknown(reason) from e
                # The gateway answers a retry with this key from the first
                # request. An attempt that was sent may itself be in use, so
                # the next one is signed anew; one never sent is resent.
                try:
                    self._wait_before_retry(5, deadline, verbose)
                    if not never_sent:
                        payment_header = new_authorization()
                except PaymentRejectedError as retry_error:
                    raise unknown(f"{reason} Stopped retrying: {retry_error}") from retry_error
                except (Exception, KeyboardInterrupt) as retry_error:
                    raise unknown(reason) from retry_error
                continue

            if verbose:
                print(f"DEBUG: Paid request status: {response.status_code}")

            # Check x-payment-response header to verify payment actually succeeded
            payment_result = self._parse_payment_response(response, verbose)
            if payment_result:
                if not payment_result.success and outstanding is not None:
                    # This attempt failed on-chain; an earlier one may not have.
                    raise unknown("A retry's payment failed, which does not say what happened "
                                  "to an earlier attempt.")
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

            payment["transaction"] = self._payment_transaction(response, payment_result)
            response.x402_payment = payment
            body_code = str(self._error_body(response).get("code") or "")

            if body_code in ("IDEMPOTENCY_KEY_IN_PROGRESS", "IDEMPOTENCY_UNAVAILABLE") \
                    and response.status_code in (409, 503):
                # This attempt was not charged; try again with the same key.
                gateway_honours_key = True
                retry = time.monotonic() < deadline
                if body_code == "IDEMPOTENCY_UNAVAILABLE":
                    retry = retry and unavailable_left > 0
                    wait = 5 * 2 ** (self.IDEMPOTENCY_UNAVAILABLE_RETRIES - unavailable_left)
                    unavailable_left -= 1
                else:
                    wait = self._retry_after(response)
                if retry:
                    try:
                        self._wait_before_retry(wait, deadline, verbose)
                        # The gateway released this authorization: send it
                        # again, unless it would expire before being used.
                        valid_before = payment.get("valid_before")
                        if valid_before and valid_before - time.time() < self.RESIGN_BEFORE_EXPIRY_SECONDS:
                            payment_header = new_authorization()
                    except (Exception, KeyboardInterrupt) as retry_error:
                        if outstanding is None:
                            raise
                        raise unknown("Stopped while retrying the paid request.") from retry_error
                    continue

            if (response.status_code == 402 and gateway_honours_key
                    and "already been used" in str(self._error_body(response).get("error", ""))):
                # The resent authorization is in use or was used (reserved, or
                # it paid the first request): it may have been collected. Sign
                # a new one (within the cap) and carry on with the same key.
                if outstanding is None:
                    outstanding = payment
                try:
                    payment_header = new_authorization()
                except PaymentRejectedError as retry_error:
                    raise unknown(f"Stopped retrying: {retry_error}") from retry_error
                continue

            replayed = bool(response.headers.get("Idempotent-Replayed"))
            if replayed and outstanding is None:
                # The answer is an earlier run's; this run's authorization was unused.
                payment.update(nonce=None, valid_before=None)
            if (outstanding is not None and not 200 <= response.status_code < 300
                    and not body_code.startswith("IDEMPOTENCY")):
                # Says nothing about the earlier attempt that may have been collected.
                raise unknown(
                    f"A retry was answered with HTTP {response.status_code}, which does not say "
                    "what happened to an earlier attempt."
                )

            if self._charged_by_this_operation(response, body_code or None, outstanding):
                self._notify_payment_sent(outstanding or payment)
            self._raise_for_paid_failure(response, payment, outstanding)
            return response

    @staticmethod
    def _retry_after(response: requests.Response) -> int:
        """Seconds from Retry-After (default 5, at most 30)."""
        try:
            # At least 5 s: a gateway cannot make the client spin
            return max(5, min(30, int(response.headers.get("Retry-After", 5))))
        except (TypeError, ValueError):
            return 5

    @staticmethod
    def _wait_before_retry(seconds: float, deadline: float, verbose: bool = False) -> None:
        wait = max(0.0, min(seconds, deadline - time.monotonic()))
        if verbose:
            print(f"DEBUG: Retrying with the same {IDEMPOTENCY_HEADER} in {wait:.0f}s")
        time.sleep(wait)

    @staticmethod
    def _charged_by_this_operation(response: requests.Response, code: Optional[str],
                                   outstanding: Optional[dict]) -> bool:
        """
        Whether this paid operation is what paid, for the payments-sent total.

        A second 402 was not accepted. The IDEMPOTENCY_* answers and a replayed
        result refer to the first request with the key: this operation paid
        only if one of its own attempts is the one that may have been collected
        (otherwise it was an earlier run, already counted there).
        """
        if response.status_code == 402:
            return False
        if (code or "").startswith("IDEMPOTENCY") or response.headers.get("Idempotent-Replayed"):
            return outstanding is not None
        body_code = str(GatewayClient._error_body(response).get("code") or "")
        if body_code.startswith("IDEMPOTENCY"):
            return outstanding is not None
        return True

    @staticmethod
    def _describe_payment(payment_header: str, amount_usd: str) -> dict:
        """
        Identify a signed payment from its own X-PAYMENT header.

        Returns the keyword arguments of PaymentOutcomeUnknownError: payer,
        nonce, amount (smallest units), amount_usd, pay_to, network and
        valid_before (unix time after which the authorization can no longer
        be collected). Fields that cannot be read are None.
        """
        details = {
            "payer": None, "nonce": None, "amount": None, "amount_usd": amount_usd,
            "pay_to": None, "network": None, "transaction": None, "valid_before": None,
        }
        try:
            payload = json.loads(base64.b64decode(payment_header))
            authorization = payload["payload"]["authorization"]
            details.update(
                payer=authorization.get("from"),
                nonce=authorization.get("nonce"),
                amount=authorization.get("value"),
                pay_to=authorization.get("to"),
                network=payload.get("network"),
            )
            details["valid_before"] = int(authorization["validBefore"])
        except (ValueError, KeyError, TypeError):
            pass
        return details

    @staticmethod
    def _payment_transaction(
        response: requests.Response,
        payment_result: Optional[X402PaymentResponse],
    ) -> Optional[str]:
        """The settlement transaction hash, from the header or the payment response."""
        tx = response.headers.get("X-Payment-Transaction")
        if not tx and payment_result:
            tx = payment_result.transaction
        return tx if tx and tx != "unknown" else None

    @staticmethod
    def _error_body(response: requests.Response) -> dict:
        """The JSON error body, unwrapped from FastAPI's {"detail": {...}}."""
        try:
            body = response.json()
        except ValueError:
            return {}
        if isinstance(body, dict) and isinstance(body.get("detail"), dict):
            body = body["detail"]
        return body if isinstance(body, dict) else {}

    # Server errors the gateway sends only before it settles a payment.
    _NOT_CHARGED_CODES = {"PURCHASE_CAPACITY"}

    @classmethod
    def _says_not_charged(cls, body: dict) -> bool:
        """True for a 5xx the gateway answers before collecting the payment."""
        if body.get("code") in cls._NOT_CHARGED_CODES:
            return True
        # The gateway's answer to a paid request that crashed before settling.
        detail = body.get("detail")
        return isinstance(detail, str) and detail.endswith("You were not charged.")

    @contextmanager
    def _reading_paid_result(self, response: requests.Response):
        """
        Parse a 2xx result; if a payment was sent, a parse failure is not a plain failure.

        The gateway answered success, so the payment was collected and the work
        was most likely done; an unreadable body (version skew, a proxy page)
        must not make the user re-run and pay again.
        """
        try:
            yield
        except Exception as e:
            payment = getattr(response, "x402_payment", None)
            if not payment or isinstance(e, PaymentOutcomeUnknownError):
                raise
            raise PaymentSettledNotDeliveredError(
                f"The payment was collected and the gateway answered HTTP {response.status_code}, "
                f"but its response could not be read ({type(e).__name__}: {e}).",
                status_code=response.status_code, **payment,
            ) from e

    def _raise_for_idempotency_answer(self, response: requests.Response, code: str, body: dict,
                                      payment: dict, outstanding: Optional[dict]) -> None:
        """
        Raise for the gateway's IDEMPOTENCY_* answers (the retry itself was never charged).

        The settled cases describe the FIRST request with this key: its nonce
        or transaction, which is what the user needs, not this retry's.
        """
        status_code = response.status_code
        key = payment.get("idempotency_key")
        first = dict(outstanding or payment)
        first["idempotency_key"] = key
        transaction = body.get("transaction") or response.headers.get("X-Payment-Transaction")
        transaction = transaction if transaction and transaction != "unknown" else None

        if code == "IDEMPOTENCY_KEY_SETTLEMENT_UNKNOWN":
            first.update(nonce=body.get("nonce") or first.get("nonce"), transaction=None,
                         valid_before=first.get("valid_before") if outstanding else None)
            raise PaymentOutcomeUnknownError(
                "The first request with this Idempotency-Key was sent for settlement and no "
                "answer came back, so it may or may not have been collected. This retry was "
                "not charged.",
                status_code=status_code, code=code, **first,
            )
        if code == "IDEMPOTENCY_KEY_SETTLED_PENDING":
            first["transaction"] = transaction
            raise PaymentSettledNotDeliveredError(
                "The first request with this Idempotency-Key was paid, but its result is not "
                "available. This retry was not charged.",
                status_code=status_code, code=code, **first,
            )
        if code == "IDEMPOTENCY_KEY_DELIVERED_NOT_STORED":
            first["transaction"] = transaction
            raise PaymentDeliveredNotStoredError(
                "The first request with this Idempotency-Key succeeded and was paid once, but "
                "its response was too large to keep, so it cannot be returned again. This "
                "retry was not charged.",
                status_code=status_code, code=code, **first,
            )
        if code in ("IDEMPOTENCY_KEY_REUSED", "IDEMPOTENCY_KEY_INVALID"):
            what = ("was already used for a different request" if code == "IDEMPOTENCY_KEY_REUSED"
                    else "is not a valid key")
            if self._idempotency_key_given:
                hint = ("The key given with --idempotency-key (or idempotency_key=) " + what
                        + ". Use the key only to repeat the same command, or leave it out.")
            else:
                hint = ("The key was generated by the client, so this is a bug in its "
                        "Idempotency-Key handling, not in your input. Please report it.")
            raise IdempotencyKeyError(
                f"The gateway refused the Idempotency-Key ({code}). {hint} Nothing was charged.",
                code=code, idempotency_key=key,
            )
        if code == "IDEMPOTENCY_KEY_IN_PROGRESS":
            if outstanding is None:
                first.update(nonce=None, valid_before=None)
            raise PaymentOutcomeUnknownError(
                f"A request with this Idempotency-Key is still running after "
                f"{self.IDEMPOTENT_RETRY_WINDOW} s; its outcome is not known yet. A retry "
                "with the same key returns its result once it finishes.",
                status_code=status_code, code=code, **first,
            )
        if code == "IDEMPOTENCY_UNAVAILABLE":
            if outstanding is not None:
                raise PaymentOutcomeUnknownError(
                    "The gateway cannot check Idempotency-Keys right now, and an earlier "
                    "attempt got no answer. The payment may have been taken.",
                    status_code=status_code, code=code, **first,
                )
            raise PaymentRejectedError(
                "The gateway cannot check Idempotency-Keys right now (IDEMPOTENCY_UNAVAILABLE). "
                "Nothing was charged; try again later.",
                reason=code,
            )

    def _raise_for_paid_failure(self, response: requests.Response, payment: dict,
                                outstanding: Optional[dict] = None) -> None:
        """
        Turn a failed paid response into an error that says what happened to the money.

        - Settled but not delivered (gateway says so): PaymentSettledNotDeliveredError.
        - 402 again: the payment was not accepted: PaymentRejectedError.
        - 5xx: the gateway may have settled first: PaymentOutcomeUnknownError.
        - Other 4xx are left to the caller: the gateway refused the request
          before collecting the payment.
        """
        status_code = response.status_code
        if 200 <= status_code < 300:
            return

        body = self._error_body(response)
        code = str(body.get("code") or "") or None
        gateway_message = body.get("message")

        if code and code.startswith("IDEMPOTENCY"):
            self._raise_for_idempotency_answer(response, code, body, payment, outstanding)

        if (response.headers.get("X-Payment-Status") == "settled_not_delivered"
                or code == "DELIVERY_FAILED_AFTER_PAYMENT"):
            raise PaymentSettledNotDeliveredError(
                f"The payment was collected but the request failed (HTTP {status_code})."
                + (f" Gateway: {gateway_message}" if gateway_message else ""),
                status_code=status_code, code=code, **payment,
            )
        if status_code == 402:
            reason = gateway_message or body.get("error") or "no reason given"
            raise PaymentRejectedError(
                f"The gateway did not accept the payment: {reason}",
                reason=reason,
            )
        if status_code >= 500 and not self._says_not_charged(body):
            raise PaymentOutcomeUnknownError(
                f"The paid request failed with HTTP {status_code}. "
                "The payment may have been taken."
                + (f" Gateway: {gateway_message}" if gateway_message else ""),
                status_code=status_code, code=code, **payment,
            )

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

    def list_stamps(self, wallet: Optional[str] = None, verbose: bool = False) -> StampListResponse:
        """
        List all postage stamp batches.

        Args:
            wallet: Only stamps bought by this wallet address (e.g. the x402
                    payer's). Sent lowercased with `exclusive=true`: the gateway
                    stores owners lowercased and matches them exactly, and
                    without `exclusive` also returns shared and untracked
                    stamps. The filter needs x402 enabled on the gateway.
            verbose: Enable debug output

        Returns:
            StampListResponse with list of stamps and total count.
        """
        url = self._make_url("/api/v1/stamps/")
        params = {"wallet": wallet.strip().lower(), "exclusive": "true"} if wallet else None
        if verbose:
            print(f"--- DEBUG: List Stamps ---")
            print(f"URL: GET {url}" + (f" (wallet={wallet})" if wallet else ""))

        try:
            response = requests.get(url, headers=self._get_headers(), params=params, timeout=30)
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
                timeout=self.PAID_REQUEST_TIMEOUT,
                verbose=verbose,
            )
            if verbose:
                print(f"DEBUG: Purchase stamp status: {response.status_code}")
            if response.status_code == 202:
                self._raise_purchase_pending(response)
            response.raise_for_status()
            with self._reading_paid_result(response):
                result = StampPurchaseResponse.model_validate(response.json())
            if verbose:
                print(f"DEBUG: Purchased stamp ID: {result.batchID}")
            return result.batchID
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Purchase stamp failed: {e}")
            raise ConnectionError(f"Failed to purchase stamp: {e}") from e

    def _raise_purchase_pending(self, response: requests.Response) -> None:
        """
        Raise for a 202 PURCHASE_PENDING: paid, batch not yet confirmed by Bee.

        Raises:
            StampPurchasePendingError: Always.
        """
        body = self._error_body(response)
        payment = dict(getattr(response, "x402_payment", None) or {})
        payment["transaction"] = body.get("transaction") or payment.get("transaction")
        raise StampPurchasePendingError(
            body.get("message")
            or "Payment received, but the stamp purchase is not confirmed yet.",
            label=body.get("label"),
            depth=body.get("depth"),
            lookup=body.get("lookup"),
            status_code=response.status_code,
            code=body.get("code"),
            **payment,
        )

    def get_stamp(self, stamp_id: str, verbose: bool = False) -> Optional[StampDetails]:
        """
        Get details of a specific stamp.

        Args:
            stamp_id: The stamp batch ID
            verbose: Enable debug output

        Returns:
            StampDetails if found, None if stamp doesn't exist.
        """
        from .file_utils import is_stamp_id
        if not is_stamp_id(stamp_id):
            raise ValueError(f"Not a stamp ID (64 hex characters): {stamp_id!r}")
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
        from .file_utils import is_stamp_id
        if not is_stamp_id(stamp_id):
            raise ValueError(f"Not a stamp ID (64 hex characters): {stamp_id!r}")
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
            if self.free_tier:
                headers["X-Payment-Mode"] = "free"

            # Use _make_paid_request for x402 support
            response = self._make_paid_request(
                "POST",
                url,
                params=params,
                files=files,
                headers=headers,
                timeout=self.PAID_REQUEST_TIMEOUT,
                verbose=verbose,
            )
            if verbose:
                print(f"DEBUG: Upload status: {response.status_code}")
            response.raise_for_status()
            with self._reading_paid_result(response):
                result = DataUploadResponse.model_validate(response.json())
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

        Raises:
            ValueError: If reference is not a Swarm reference (64 or 128 hex
                characters); it is placed in the URL path.
        """
        from .file_utils import is_swarm_reference
        if not is_swarm_reference(reference):
            raise ValueError(f"Not a Swarm reference (64 or 128 hex characters): {reference!r}")
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

    # --- Stamp Pool ---

    # Mapping from size name to depth
    SIZE_TO_DEPTH = {
        "small": 17,
        "medium": 20,
        "large": 22,
    }

    def get_pool_status(self, verbose: bool = False) -> PoolStatusResponse:
        """
        Get current stamp pool status.

        Returns:
            PoolStatusResponse with pool state and available stamps.

        Raises:
            PoolNotEnabledError: If pool is not enabled on this gateway
        """
        url = self._make_url("/api/v1/pool/status")
        if verbose:
            print(f"--- DEBUG: Get Pool Status ---")
            print(f"URL: GET {url}")

        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            if verbose:
                print(f"DEBUG: Pool status response: {response.status_code}")

            if response.status_code == 404:
                raise PoolNotEnabledError("Stamp pool is not enabled on this gateway.")

            response.raise_for_status()
            data = response.json()
            return PoolStatusResponse.model_validate(data)
        except PoolNotEnabledError:
            raise
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Get pool status failed: {e}")
            raise ConnectionError(f"Failed to get pool status: {e}") from e

    def get_pool_available_count(
        self,
        size: Optional[str] = None,
        depth: Optional[int] = None,
        verbose: bool = False,
    ) -> int:
        """
        Get count of available stamps in pool for given size/depth.

        Args:
            size: Size preset ('small', 'medium', 'large')
            depth: Specific depth (overrides size)
            verbose: Enable debug output

        Returns:
            Number of available stamps matching the criteria.

        Raises:
            PoolNotEnabledError: If pool is not enabled on this gateway
        """
        status = self.get_pool_status(verbose=verbose)

        if not status.enabled:
            raise PoolNotEnabledError("Stamp pool is not enabled on this gateway.")

        # Determine target depth
        target_depth = depth
        if target_depth is None and size:
            target_depth = self.SIZE_TO_DEPTH.get(size.lower())
        if target_depth is None:
            # Default to small if neither specified
            target_depth = self.SIZE_TO_DEPTH["small"]

        # Count stamps for specific depth
        depth_str = str(target_depth)
        return len(status.available_stamps.get(depth_str, []))

    def list_pool_stamps(self, verbose: bool = False) -> List[PoolStampInfo]:
        """
        List all stamps currently available in the pool.

        Returns:
            List of PoolStampInfo objects.

        Raises:
            PoolNotEnabledError: If pool is not enabled on this gateway
        """
        url = self._make_url("/api/v1/pool/stamps")
        if verbose:
            print(f"--- DEBUG: List Pool Stamps ---")
            print(f"URL: GET {url}")

        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            if verbose:
                print(f"DEBUG: List pool stamps response: {response.status_code}")

            if response.status_code == 404:
                raise PoolNotEnabledError("Stamp pool is not enabled on this gateway.")

            response.raise_for_status()
            data = response.json()
            # Response contains {"stamps": [...], "count": n}
            stamps_data = data.get("stamps", data)
            if isinstance(stamps_data, list):
                return [PoolStampInfo.model_validate(item) for item in stamps_data]
            return []
        except PoolNotEnabledError:
            raise
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: List pool stamps failed: {e}")
            raise ConnectionError(f"Failed to list pool stamps: {e}") from e

    def acquire_stamp_from_pool(
        self,
        size: Optional[str] = None,
        depth: Optional[int] = None,
        verbose: bool = False,
    ) -> AcquireStampResponse:
        """
        Acquire a stamp from the pool for immediate use.

        This is much faster than purchasing a new stamp (~5 seconds vs >1 minute).

        Args:
            size: Preferred size ('small', 'medium', 'large')
            depth: Specific depth (overrides size)
            verbose: Enable debug output

        Returns:
            AcquireStampResponse with batch_id, depth, size_name, fallback_used.

        Raises:
            PoolNotEnabledError: If pool is not enabled on this gateway
            PoolEmptyError: If no stamps available for requested size/depth
            PoolAcquisitionError: If acquisition fails despite availability
        """
        size_desc = size or "default"
        if depth:
            size_desc = f"depth {depth}"

        # Attempt acquisition
        url = self._make_url("/api/v1/pool/acquire")
        payload = {}
        if size:
            payload["size"] = size
        if depth:
            payload["depth"] = depth

        if verbose:
            print(f"--- DEBUG: Acquire Stamp from Pool ---")
            print(f"URL: POST {url}")
            print(f"Payload: {payload}")

        try:
            response = self._make_paid_request(
                "POST",
                url,
                json=payload,
                headers=self._get_headers(),
                timeout=self.PAID_REQUEST_TIMEOUT,
                verbose=verbose,
            )
            if verbose:
                print(f"DEBUG: Acquire response: {response.status_code}")
            response.raise_for_status()
            with self._reading_paid_result(response):
                result = AcquireStampResponse.model_validate(response.json())

            if not result.success:
                raise PoolAcquisitionError(
                    f"Failed to acquire stamp from pool: {result.message}. "
                    "Retry may succeed.",
                    available_count=0,
                )

            if verbose:
                print(f"DEBUG: Acquired stamp: {result.batch_id} (size={result.size_name}, depth={result.depth})")
                if result.fallback_used:
                    print(f"DEBUG: Note: A larger stamp was used as fallback")

            return result

        except (PoolNotEnabledError, PoolEmptyError, PoolAcquisitionError):
            raise
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Acquire stamp failed: {e}")
            raise PoolAcquisitionError(
                f"Failed to acquire stamp from pool: {e}",
                available_count=0,
            ) from e

    def check_stamp_health(
        self,
        stamp_id: str,
        verbose: bool = False,
    ) -> StampHealthCheckResponse:
        """
        Perform health check on a specific stamp.

        Checks if the stamp can be used for uploads and reports
        any errors or warnings.

        Args:
            stamp_id: The stamp batch ID to check
            verbose: Enable debug output

        Returns:
            StampHealthCheckResponse with health status.

        Raises:
            StampNotFoundError: If the stamp does not exist
        """
        from .file_utils import is_stamp_id
        if not is_stamp_id(stamp_id):
            raise ValueError(f"Not a stamp ID (64 hex characters): {stamp_id!r}")
        url = self._make_url(f"/api/v1/stamps/{stamp_id.lower()}/check")
        if verbose:
            print(f"--- DEBUG: Check Stamp Health ---")
            print(f"URL: GET {url}")

        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            if verbose:
                print(f"DEBUG: Stamp health check response: {response.status_code}")

            if response.status_code == 404:
                raise StampNotFoundError(f"Stamp {stamp_id} not found.")

            response.raise_for_status()
            data = response.json()
            return StampHealthCheckResponse.model_validate(data)
        except StampNotFoundError:
            raise
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Stamp health check failed: {e}")
            raise ConnectionError(f"Failed to check stamp health: {e}") from e

    # --- Notary Signing ---

    def get_notary_info(self, verbose: bool = False) -> NotaryInfoResponse:
        """
        Get notary service status and signer address.

        Returns:
            NotaryInfoResponse with enabled, available, address, and message.

        Raises:
            NotaryNotEnabledError: If notary endpoint returns 404
        """
        url = self._make_url("/api/v1/notary/info")
        if verbose:
            print(f"--- DEBUG: Get Notary Info ---")
            print(f"URL: GET {url}")

        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            if verbose:
                print(f"DEBUG: Notary info response: {response.status_code}")

            if response.status_code == 404:
                raise NotaryNotEnabledError("Notary signing is not enabled on this gateway.")

            response.raise_for_status()
            data = response.json()
            return NotaryInfoResponse.model_validate(data)
        except NotaryNotEnabledError:
            raise
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Get notary info failed: {e}")
            raise ConnectionError(f"Failed to get notary info: {e}") from e

    def get_notary_status(self, verbose: bool = False) -> NotaryStatusResponse:
        """
        Get simplified notary service status (health check).

        Returns:
            NotaryStatusResponse with enabled and available flags.

        Raises:
            NotaryNotEnabledError: If notary endpoint returns 404
        """
        url = self._make_url("/api/v1/notary/status")
        if verbose:
            print(f"--- DEBUG: Get Notary Status ---")
            print(f"URL: GET {url}")

        try:
            response = requests.get(url, headers=self._get_headers(), timeout=10)
            if verbose:
                print(f"DEBUG: Notary status response: {response.status_code}")

            if response.status_code == 404:
                raise NotaryNotEnabledError("Notary signing is not enabled on this gateway.")

            response.raise_for_status()
            data = response.json()
            return NotaryStatusResponse.model_validate(data)
        except NotaryNotEnabledError:
            raise
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Get notary status failed: {e}")
            raise ConnectionError(f"Failed to get notary status: {e}") from e

    def upload_data_with_signing(
        self,
        data: bytes,
        stamp_id: str,
        sign: str = "notary",
        content_type: str = "application/json",
        verbose: bool = False,
    ) -> SignedDocumentResponse:
        """
        Upload data to Swarm with notary signing.

        The gateway will add a cryptographic signature to the document
        before storing it on Swarm.

        Args:
            data: The bytes to upload (must be valid JSON with 'data' field)
            stamp_id: Postage stamp ID to use
            sign: Signing mode, currently only 'notary' is supported
            content_type: Content type (always forced to application/json for signing)
            verbose: Enable debug output

        Returns:
            SignedDocumentResponse with reference and optional signed_document.

        Raises:
            NotaryNotEnabledError: If notary is not enabled
            NotaryNotConfiguredError: If notary is enabled but not configured
            InvalidDocumentFormatError: If document is not valid JSON or missing 'data' field
        """
        url = self._make_url("/api/v1/data/")
        params = {
            "stamp_id": stamp_id.lower(),
            "sign": sign,
            "content_type": "application/json",  # Always JSON for signed documents
        }

        if verbose:
            print(f"--- DEBUG: Upload Data with Signing ---")
            print(f"URL: POST {url}")
            print(f"Params: {params}")
            print(f"Data size: {len(data)} bytes")

        try:
            # Gateway expects multipart form data
            files = {"file": ("data", data, "application/json")}
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            if self.free_tier:
                headers["X-Payment-Mode"] = "free"

            # Use _make_paid_request for x402 support
            response = self._make_paid_request(
                "POST",
                url,
                params=params,
                files=files,
                headers=headers,
                timeout=self.PAID_REQUEST_TIMEOUT,
                verbose=verbose,
            )

            if verbose:
                print(f"DEBUG: Upload with signing status: {response.status_code}")

            # Handle specific error codes
            if response.status_code == 400:
                try:
                    error_data = response.json()
                    error_code = error_data.get("code", "")
                    error_message = error_data.get("detail", str(error_data))

                    if error_code == "NOTARY_NOT_ENABLED":
                        raise NotaryNotEnabledError(
                            "Notary signing is not enabled on this gateway."
                        )
                    elif error_code == "NOTARY_NOT_CONFIGURED":
                        raise NotaryNotConfiguredError(
                            "Notary is enabled but not fully configured on this gateway."
                        )
                    elif error_code == "INVALID_DOCUMENT_FORMAT":
                        raise InvalidDocumentFormatError(
                            f"Invalid document format: {error_message}"
                        )
                    elif error_code == "INVALID_SIGN_OPTION":
                        raise ValueError(f"Invalid sign option: {error_message}")
                except (ValueError, KeyError):
                    pass  # Fall through to raise_for_status

            response.raise_for_status()
            with self._reading_paid_result(response):
                data_response = response.json()

                # Build response - gateway may return signed_document or just reference
                reference = data_response.get("reference", "")
                signed_doc = data_response.get("signed_document")
                message = data_response.get("message")
                if response.x402_payment and not reference:
                    raise ValueError("no reference in the response")

            if verbose:
                print(f"DEBUG: Upload reference: {reference}")
                if signed_doc:
                    sigs = signed_doc.get("signatures", [])
                    print(f"DEBUG: Document has {len(sigs)} signature(s)")

            return SignedDocumentResponse(
                reference=reference,
                signed_document=signed_doc,
                message=message,
            )

        except (NotaryNotEnabledError, NotaryNotConfiguredError, InvalidDocumentFormatError):
            raise
        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Upload with signing failed: {e}")
            raise ConnectionError(f"Failed to upload data with signing: {e}") from e

    def upload_manifest(
        self,
        tar_path: str,
        stamp_id: str,
        validate_stamp: bool = True,
        deferred: bool = False,
        include_timing: bool = False,
        redundancy: bool = False,
        verbose: bool = False,
    ) -> ManifestUploadResponse:
        """Upload a TAR archive as a Swarm manifest.

        Creates a manifest that preserves directory structure and allows
        individual file access via path-based URLs.

        Args:
            tar_path: Path to the TAR archive file.
            stamp_id: Postage stamp ID to use.
            validate_stamp: Whether to validate stamp before upload.
            deferred: Use deferred upload mode.
            include_timing: Include timing breakdown in response.
            redundancy: Enable redundancy for the upload.
            verbose: Enable debug output.

        Returns:
            ManifestUploadResponse with reference and file count.
        """
        url = self._make_url("/api/v1/data/manifest")
        params = {"stamp_id": stamp_id.lower()}
        if not validate_stamp:
            params["validate_stamp"] = "false"
        if deferred:
            params["deferred"] = "true"
        if include_timing:
            params["include_timing"] = "true"
        if redundancy:
            params["redundancy"] = "true"

        if verbose:
            print(f"--- DEBUG: Upload Manifest ---")
            print(f"URL: POST {url}")
            print(f"Params: {params}")
            print(f"TAR file: {tar_path}")

        try:
            with open(tar_path, "rb") as f:
                tar_data = f.read()

            if verbose:
                print(f"DEBUG: TAR size: {len(tar_data)} bytes")

            files = {"file": ("collection.tar", tar_data, "application/x-tar")}
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            if self.free_tier:
                headers["X-Payment-Mode"] = "free"

            response = self._make_paid_request(
                "POST",
                url,
                params=params,
                files=files,
                headers=headers,
                timeout=self.PAID_REQUEST_TIMEOUT,
                verbose=verbose,
            )

            if verbose:
                print(f"DEBUG: Upload manifest status: {response.status_code}")

            response.raise_for_status()
            with self._reading_paid_result(response):
                data = response.json()

                timing = None
                if include_timing and "timing" in data:
                    timing = ManifestUploadTiming.model_validate(data["timing"])

                result = ManifestUploadResponse(
                    reference=data.get("reference", ""),
                    file_count=data.get("file_count"),
                    message=data.get("message"),
                    timing=timing,
                )
                if response.x402_payment and not result.reference:
                    raise ValueError("no reference in the response")

            if verbose:
                print(f"DEBUG: Manifest reference: {result.reference}")
                if result.file_count is not None:
                    print(f"DEBUG: File count: {result.file_count}")

            return result

        except requests.exceptions.RequestException as e:
            if verbose:
                print(f"ERROR: Upload manifest failed: {e}")
            raise ConnectionError(f"Failed to upload manifest: {e}") from e
