"""Redact RPC URLs before they are shown to the user.

RPC URLs often carry a provider API key: in the path (Alchemy ``/v2/<key>``,
Infura ``/v3/<key>``), in the query (``?apikey=``) or as basic auth
(``user:password@``). Error texts from ``requests``, ``urllib3`` and ``web3``
repeat the full URL, or its path and query. These helpers keep the scheme,
host and port, which tell the user which endpoint failed, and replace the rest.

Some texts quote parts of the URL with no recognizable URL around them, for
example an HTML error page that says "The requested URL /v2/<key> was not
found". ChainProvider therefore registers the secret parts of each configured
RPC URL with :func:`register_url_secrets`, and :func:`redact_urls` replaces
those exact strings wherever they appear.

Standard library only, so they work without the ``blockchain`` extra.
"""

import html
import re
import threading
from typing import Iterable, List, Optional, Tuple
from urllib.parse import quote, unquote, urlsplit

# What replaces the path, query, fragment and user:password of a URL
PLACEHOLDER = "…"

# A URL with any scheme, also a misspelled one such as "htps://". Stops at
# whitespace, quotes and angle brackets.
_URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s\"'<>]+", re.IGNORECASE)

# A scheme at the start of a string
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)

# requests quotes the URL as given, also when it has no scheme:
# "No connection adapters were found for '<url>'", "Invalid URL '<url>': ..."
_QUOTED_URL_RE = re.compile(
    r"((?:No connection adapters were found for|Invalid URL) ')([^']*)(')",
    re.IGNORECASE,
)

# Secret parts of configured RPC URLs shorter than this are not registered:
# a short string would also match ordinary words in error texts.
MIN_SECRET_LENGTH = 8

_secrets_lock = threading.Lock()
_secrets: set = set()
# Registered secrets, longest first, so a longer one is replaced before a part of it
_secrets_sorted: Tuple[str, ...] = ()

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
        url: The URL to redact. None and "" are returned as they are; any
            other non-string value is converted with str() first.

    Returns:
        The redacted URL.
    """
    if not url:
        return url
    if not isinstance(url, str):
        # A caller may hold a non-string (a mock, a URL object): redact its text
        url = str(url)
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


def _redact_loose(value: str) -> str:
    """Redact a URL that may have no scheme, such as ``127.0.0.1:8545/v2/<key>``."""
    if _SCHEME_RE.match(value):
        return redact_url(value)
    authority, rest = re.match(r"([^/?#]*)(.*)", value, re.DOTALL).groups()
    had_userinfo = "@" in authority
    authority = authority.rsplit("@", 1)[-1]
    if not authority:
        return PLACEHOLDER
    if rest in ("", "/") and not had_userinfo:
        return value
    return f"{authority}/{PLACEHOLDER}"


def _secret_parts(url: str) -> List[str]:
    """The parts of a URL that may hold a credential: everything but the scheme and host."""
    rest_of_url = _SCHEME_RE.sub("", url.strip(), count=1)
    authority, rest = re.match(r"([^/?#]*)(.*)", rest_of_url, re.DOTALL).groups()
    parts = []
    if "@" in authority:
        userinfo = authority.rsplit("@", 1)[0]
        parts.append(userinfo)
        parts.extend(userinfo.split(":", 1))
    if rest:
        parts.append(rest)
        before_fragment, _, fragment = rest.partition("#")
        path, _, query = before_fragment.partition("?")
        parts.extend([before_fragment, path, query, fragment])
        parts.extend(path.split("/"))
        for pair in query.split("&"):
            parts.extend(pair.split("=", 1))
    return parts


def register_url_secrets(urls: Iterable[Optional[str]]) -> None:
    """
    Remember the secret parts of RPC URLs, so :func:`redact_urls` removes them.

    For each URL, the path, query, fragment, ``user:password``, and each path
    segment and query value are registered, when they are at least
    MIN_SECRET_LENGTH characters long. Their percent-encoded, decoded and
    HTML-escaped forms are registered too. The scheme, host and port are not.

    Args:
        urls: The configured RPC URLs (primary and fallbacks). None is skipped.
    """
    found = set()
    for url in urls:
        if not url:
            continue
        for part in _secret_parts(url):
            for form in (part, unquote(part), quote(part, safe="/"), quote(part, safe=""),
                         html.escape(part)):
                if len(form) >= MIN_SECRET_LENGTH and form.strip("/"):
                    found.add(form)
    global _secrets_sorted
    with _secrets_lock:
        if found <= _secrets:
            return
        _secrets.update(found)
        _secrets_sorted = tuple(sorted(_secrets, key=len, reverse=True))


def clear_url_secrets() -> None:
    """Forget all registered URL secrets (for tests)."""
    global _secrets_sorted
    with _secrets_lock:
        _secrets.clear()
        _secrets_sorted = ()


def redact_urls(text: Optional[str]) -> Optional[str]:
    """
    Redact every URL in an error text, and keep the rest of the text.

    Full URLs, with any scheme, are shortened with :func:`redact_url`. The
    URL that requests quotes in "No connection adapters were found for '...'"
    and "Invalid URL '...'" is shortened even without a scheme. The bare path
    that urllib3 prints (``with url: /v2/<key>``) is replaced with the
    placeholder. Last, every secret registered with
    :func:`register_url_secrets` is replaced wherever it appears.
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
        stripped = url.rstrip(_TRAILING)
        return redact_url(stripped) + url[len(stripped):]

    text = _QUOTED_URL_RE.sub(lambda m: m.group(1) + _redact_loose(m.group(2)) + m.group(3), text)
    text = _URL_RE.sub(_full, text)
    text = _URL_PATH_RE.sub(lambda m: f"{m.group(1)}/{PLACEHOLDER}", text)
    for secret in _secrets_sorted:
        if secret in text:
            text = text.replace(secret, f"/{PLACEHOLDER}" if secret.startswith("/") else PLACEHOLDER)
    return text
