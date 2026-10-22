"""Redaction helpers for URLs that may carry credentials.

RPC provider URLs frequently embed API keys (Alchemy, Infura and QuickNode
use both ``https://host/v2/<API_KEY>`` path keys and ``user:pass@host``
userinfo). Errors that echo them verbatim leak those keys into terminal
output, CI logs and agent transcripts, so every URL-derived fragment is
redacted before it reaches an exception message or the CLI's error output:
the scheme and host survive, the path, query and userinfo do not.
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

#: An http(s) URL embedded in free text (exception messages, log lines).
_URL_IN_TEXT = re.compile(r"\bhttps?://[^\s'\"<>\\]+")


def redact_url(url: Optional[str]) -> Optional[str]:
    """Return ``url`` with its path, query and userinfo removed.

    ``https://k@eth-mainnet.g.alchemy.com/v2/API_KEY?x=1`` becomes
    ``https://eth-mainnet.g.alchemy.com``. A value that is not an http(s)
    URL with a host becomes ``<url>`` so nothing unredacted can slip
    through a parse gap. ``None``/empty passes through unchanged.
    """
    if not url:
        return url
    try:
        parsed = urlparse(url)
    except ValueError:
        return "<url>"
    host = parsed.hostname
    if not parsed.scheme or not host:
        return "<url>"
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return f"{parsed.scheme}://{netloc}"


def redact_urls_in_text(text: Optional[str]) -> Optional[str]:
    """Replace every http(s) URL embedded in ``text`` with its redacted form.

    Underlying web3/requests exception messages quote the request URL
    verbatim, so wrapping them into chain errors or printing them as-is
    would leak any embedded key; this keeps the diagnostic shape (the
    failure and the host it happened against) without the secret part.
    """
    if not text:
        return text
    return _URL_IN_TEXT.sub(lambda m: redact_url(m.group(0)), text)
