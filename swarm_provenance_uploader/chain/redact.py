"""Redact RPC URLs before they are shown to the user.

RPC URLs often carry a provider API key: in the path (Alchemy ``/v2/<key>``,
Infura ``/v3/<key>``), in the query (``?apikey=``) or as basic auth
(``user:password@``). Error texts from ``requests``, ``urllib3`` and ``web3``
repeat the full URL, or its path and query. These helpers keep the scheme,
host and port, which tell the user which endpoint failed, and replace the rest.

Standard library only, so they work without the ``blockchain`` extra.
"""

import re
from typing import Optional
from urllib.parse import urlsplit

# What replaces the path, query, fragment and user:password of a URL
PLACEHOLDER = "…"

# A URL with a scheme. Stops at whitespace, quotes and angle brackets.
_URL_RE = re.compile(r"\b(?:https?|wss?)://[^\s\"'<>]+", re.IGNORECASE)

# urllib3 prints only the path and query: "Max retries exceeded with url: /v2/<key>?a=b"
_URL_PATH_RE = re.compile(r"(\burl: )(/[^\s\"'<>]*)", re.IGNORECASE)

# Punctuation that usually ends a sentence or a bracket rather than the URL
_TRAILING = ".,;:!?)]}"


def redact_url(url: Optional[str]) -> Optional[str]:
    """
    Return ``url`` with only its scheme, host and port.

    The path, query, fragment and any ``user:password@`` are replaced with
    a placeholder: ``https://base-sepolia.g.alchemy.com/v2/KEY`` becomes
    ``https://base-sepolia.g.alchemy.com/…``. A URL with nothing to remove
    is returned unchanged. Text that is not a URL with a host is replaced
    entirely, since it cannot be shortened safely.

    Args:
        url: The URL to redact. None and "" are returned as they are.

    Returns:
        The redacted URL.
    """
    if not url:
        return url
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        port = parts.port
    except ValueError:
        return PLACEHOLDER
    if not parts.scheme or not host:
        return PLACEHOLDER
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    base = f"{parts.scheme}://{host}"
    if port is not None:
        base += f":{port}"
    hidden = (
        (parts.path not in ("", "/"))
        or parts.query
        or parts.fragment
        or "@" in parts.netloc
        # A "?" or "#" with nothing after it is still not the bare host
        or url.strip().endswith(("?", "#"))
    )
    if not hidden:
        return base + ("/" if parts.path == "/" else "")
    return f"{base}/{PLACEHOLDER}"


def redact_urls(text: Optional[str]) -> Optional[str]:
    """
    Redact every URL in an error text, and keep the rest of the text.

    Full URLs are shortened with :func:`redact_url`. The bare path that
    urllib3 prints (``with url: /v2/<key>``) is replaced with the placeholder.
    The HTTP status and the error description stay, for example
    ``401 Client Error: Unauthorized for url: https://host/…``.

    Args:
        text: An error message, or ``str()`` of an exception.

    Returns:
        The text without URL paths, queries or credentials.
    """
    if not text:
        return text

    def _full(match: "re.Match") -> str:
        url = match.group(0)
        tail = ""
        while url and url[-1] in _TRAILING:
            tail = url[-1] + tail
            url = url[:-1]
        return redact_url(url) + tail

    text = _URL_RE.sub(_full, text)
    return _URL_PATH_RE.sub(lambda m: f"{m.group(1)}/{PLACEHOLDER}", text)
