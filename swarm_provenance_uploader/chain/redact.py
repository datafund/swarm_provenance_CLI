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
# whitespace, quotes and angle brackets. The scheme is at most 32 characters:
# an unbounded run made matching quadratic on long texts such as
# "a.a.a.…" or "a-a-a-…", which web3 copies from a non-JSON RPC answer.
_URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]{0,31}://[^\s\"'<>]+", re.IGNORECASE)

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


def _looks_like_credential(piece: str) -> bool:
    """True for a single path segment or query value that may be a key.

    Short words such as a network name (``base-sepolia``) and hex-only or
    digit-only strings such as ``deadbeef`` are not keys, and redacting them
    would also cut chain names, addresses and transaction hashes.
    """
    if len(piece) >= 16:
        return True
    return (
        len(piece) >= MIN_SECRET_LENGTH
        and any(c.isalpha() for c in piece)
        and any(c.isdigit() for c in piece)
    )


# Query parameter names whose value is a credential, whatever it looks like
_CREDENTIAL_PARAMS = frozenset({
    "key", "apikey", "api_key", "api-key", "token", "access_token", "accesstoken",
    "dkey", "auth", "secret", "password",
})


def _secret_parts(url: str) -> Tuple[List[str], List[str]]:
    """
    The parts of a URL that may hold a credential: everything but the scheme and host.

    Returns:
        (whole, pieces): ``whole`` holds the path with query and fragment, the
        path, query, fragment, ``user:password``, password, the last non-empty
        path segment (where providers put the key) and the values of
        credential-named query parameters (``apikey=``, ``token=`` and so on).
        These are registered when long enough, whatever they look like.
        ``pieces`` holds the user name, the other path segments and the other
        query values, which are registered only when they look like a
        credential. Query keys are never returned.
    """
    rest_of_url = _SCHEME_RE.sub("", url.strip(), count=1)
    authority, rest = re.match(r"([^/?#]*)(.*)", rest_of_url, re.DOTALL).groups()
    whole: List[str] = []
    pieces: List[str] = []
    if "@" in authority:
        userinfo = authority.rsplit("@", 1)[0]
        user, _, password = userinfo.partition(":")
        whole.extend([userinfo, password])
        pieces.append(user)
    if rest:
        before_fragment, _, fragment = rest.partition("#")
        path, _, query = before_fragment.partition("?")
        whole.extend([rest, before_fragment, path, query, fragment])
        segments = [seg for seg in path.split("/") if seg]
        if segments:
            whole.append(segments[-1])
            pieces.extend(segments[:-1])
        for pair in query.split("&"):
            name, _, value = pair.partition("=")
            if unquote(name).strip().lower() in _CREDENTIAL_PARAMS:
                whole.append(value)
            else:
                pieces.append(value)
    return whole, pieces


def register_url_secrets(urls: Iterable[Optional[str]], public: Iterable[str] = ()) -> None:
    """
    Remember the secret parts of RPC URLs, so :func:`redact_urls` removes them.

    For each URL, the path, query, fragment, ``user:password``, password, last
    non-empty path segment, and the values of credential-named query
    parameters (key, apikey, api_key, api-key, token, access_token,
    accesstoken, dkey, auth, secret, password) are registered when they are at
    least MIN_SECRET_LENGTH characters long. The user name, the other path
    segments and the other query values are registered only when they look
    like a credential: at least 16 characters, or at least
    MIN_SECRET_LENGTH characters with both a letter and a digit. Query keys,
    the scheme, the host and the port are never registered. Percent-encoded,
    decoded and HTML-escaped forms are registered too.

    Args:
        urls: The configured RPC URLs (primary and fallbacks). None is skipped.
        public: Strings that are not secret, such as chain names and preset
            URLs. A part equal to one of them, or contained in one, is skipped.
    """
    public = [p for p in public if p]

    def is_public(form: str) -> bool:
        return any(form in p for p in public)

    found = set()
    for url in urls:
        if not url:
            continue
        whole, pieces = _secret_parts(str(url))
        candidates = whole + [p for p in pieces if _looks_like_credential(p)]
        for part in candidates:
            for form in (part, unquote(part), quote(part, safe="/"), quote(part, safe=""),
                         html.escape(part)):
                if len(form) >= MIN_SECRET_LENGTH and form.strip("/") and not is_public(form):
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
