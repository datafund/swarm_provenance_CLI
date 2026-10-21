"""Tests for RPC URL redaction in chain errors (#169)."""

import pytest

from swarm_provenance_uploader.chain.redact import (
    PLACEHOLDER,
    clear_url_secrets,
    redact_url,
    redact_urls,
    register_url_secrets,
)
from swarm_provenance_uploader.exceptions import (
    ChainConfigurationError,
    ChainConnectionError,
    ChainTransactionError,
    TransactionNotVerifiedError,
)

KEY = "SECRETKEYSECRETKEY"
PATH_KEY_URL = f"https://base-sepolia.g.alchemy.com/v2/{KEY}"
QUERY_KEY_URL = f"https://rpc.example.org/base?apikey={KEY}"
BASIC_AUTH_URL = f"https://rpcuser:{KEY}@rpc.example.org:8545"

SECRET_URLS = [PATH_KEY_URL, QUERY_KEY_URL, BASIC_AUTH_URL]
SECRET_IDS = ["path", "query", "basic-auth"]


class TestRedactUrl:
    def test_path_key(self):
        assert redact_url(PATH_KEY_URL) == f"https://base-sepolia.g.alchemy.com/{PLACEHOLDER}"

    def test_query_key(self):
        assert redact_url(QUERY_KEY_URL) == f"https://rpc.example.org/{PLACEHOLDER}"

    def test_basic_auth_keeps_port(self):
        assert redact_url(BASIC_AUTH_URL) == f"https://rpc.example.org:8545/{PLACEHOLDER}"

    def test_fragment(self):
        assert redact_url("https://rpc.example.org#token") == f"https://rpc.example.org/{PLACEHOLDER}"

    @pytest.mark.parametrize("url", [
        "https://sepolia.base.org",
        "https://sepolia.base.org/",
        "http://127.0.0.1:8545",
    ])
    def test_nothing_to_remove(self, url):
        assert redact_url(url) == url

    def test_ipv6_host(self):
        assert redact_url(f"http://[::1]:8545/{KEY}") == f"http://[::1]:8545/{PLACEHOLDER}"

    @pytest.mark.parametrize("value", [None, ""])
    def test_empty(self, value):
        assert redact_url(value) == value

    @pytest.mark.parametrize("value", [f"rpc.example.org/{KEY}", KEY, "http://[bad/" + KEY])
    def test_not_a_url_is_replaced(self, value):
        assert redact_url(value) == PLACEHOLDER

    def test_idempotent(self):
        once = redact_url(PATH_KEY_URL)
        assert redact_url(once) == once


class TestRedactUrls:
    def test_requests_http_error_keeps_status_and_host(self):
        text = f"401 Client Error: Unauthorized for url: {PATH_KEY_URL}"
        assert redact_urls(text) == (
            f"401 Client Error: Unauthorized for url: https://base-sepolia.g.alchemy.com/{PLACEHOLDER}"
        )

    def test_urllib3_path_only(self):
        # requests.ConnectionError repeats only the path and query of the URL
        text = (
            "HTTPSConnectionPool(host='base-sepolia.g.alchemy.com', port=443): Max retries "
            f"exceeded with url: /v2/{KEY}?apikey={KEY} (Caused by NewConnectionError('refused'))"
        )
        out = redact_urls(text)
        assert KEY not in out
        assert "host='base-sepolia.g.alchemy.com', port=443" in out
        assert f"with url: /{PLACEHOLDER} (Caused by" in out

    @pytest.mark.parametrize("url", SECRET_URLS, ids=SECRET_IDS)
    def test_every_form(self, url):
        out = redact_urls(f"Cannot connect to RPC endpoint: {url}")
        assert KEY not in out
        assert out == f"Cannot connect to RPC endpoint: {redact_url(url)}"
        assert out.endswith(PLACEHOLDER)

    def test_trailing_punctuation_and_quotes(self):
        text = f"failed ('{QUERY_KEY_URL}'), then ({PATH_KEY_URL})."
        out = redact_urls(text)
        assert KEY not in out
        assert out == (
            f"failed ('https://rpc.example.org/{PLACEHOLDER}'), "
            f"then (https://base-sepolia.g.alchemy.com/{PLACEHOLDER})."
        )

    def test_several_urls(self):
        out = redact_urls(f"switched from {PATH_KEY_URL} to {BASIC_AUTH_URL}")
        assert KEY not in out
        assert out.count(PLACEHOLDER) == 2

    def test_text_without_urls_unchanged(self):
        text = "execution reverted: already registered"
        assert redact_urls(text) == text

    @pytest.mark.parametrize("value", [None, ""])
    def test_empty(self, value):
        assert redact_urls(value) == value


class TestChainErrorsRedact:
    @pytest.mark.parametrize("url", SECRET_URLS, ids=SECRET_IDS)
    def test_connection_error_message_and_rpc_url(self, url):
        e = ChainConnectionError(f"RPC health check failed: 503 Server Error for url: {url}", rpc_url=url)
        assert KEY not in str(e)
        assert KEY not in e.rpc_url
        assert "503 Server Error" in str(e)
        assert e.rpc_url.endswith(PLACEHOLDER)

    def test_transaction_error_message(self):
        e = ChainTransactionError(f"Transaction failed: 429 Too Many Requests for url: {PATH_KEY_URL}")
        assert KEY not in str(e)
        assert "429 Too Many Requests" in str(e)

    def test_configuration_error_message(self):
        e = ChainConfigurationError(f"Could not check the contract code at 0x1: {QUERY_KEY_URL}")
        assert KEY not in str(e)

    def test_not_verified_reason(self):
        e = TransactionNotVerifiedError("Not verified", reason=f"timeout for url: {PATH_KEY_URL}")
        assert KEY not in e.reason


class TestRegisteredSecrets:
    """Parts of configured RPC URLs that error texts repeat without the URL (#169)."""

    def test_body_echo_of_path_and_query(self):
        register_url_secrets([f"https://rpc.example.org/v2/{KEY}?apikey={KEY}2"])
        text = f"Could not decode '<html>The requested URL /v2/{KEY}?apikey={KEY}2 was not found</html>'"
        out = redact_urls(text)
        assert KEY not in out
        assert out == f"Could not decode '<html>The requested URL /{PLACEHOLDER} was not found</html>'"

    def test_segment_and_query_value_alone(self):
        register_url_secrets([f"https://rpc.example.org/v2/{KEY}?apikey={KEY}2&network=base"])
        assert KEY not in redact_urls(f"unknown key {KEY}")
        assert KEY not in redact_urls(f"rate limit for {KEY}2")
        # Short parts are not registered: they would match ordinary words
        assert redact_urls("network base v2") == "network base v2"

    def test_userinfo_and_password(self):
        register_url_secrets([f"https://rpcuser:{KEY}@rpc.example.org"])
        assert KEY not in redact_urls(f"auth failed for rpcuser:{KEY}")
        assert KEY not in redact_urls(f"password {KEY} rejected")

    def test_encoded_forms(self):
        # Configured with a space: an error text may show it percent-encoded
        register_url_secrets(["https://rpc.example.org/v2/my key 12345"])
        assert redact_urls("not found: /v2/my%20key%2012345") == f"not found: /{PLACEHOLDER}"
        assert "my%20key" not in redact_urls("segment my%20key%2012345 rejected")
        # Configured percent-encoded: an error text may show it decoded
        register_url_secrets(["https://rpc.example.org/v3/other%20key%2067890"])
        assert "other key" not in redact_urls("segment other key 67890 rejected")
        # HTML-escaped query, as an error page would quote it
        register_url_secrets([f"https://rpc.example.org/?a={KEY}&b={KEY}3"])
        assert KEY not in redact_urls(f"<p>?a={KEY}&amp;b={KEY}3</p>")

    def test_host_is_not_registered(self):
        register_url_secrets([f"https://base-sepolia.g.alchemy.com/v2/{KEY}"])
        assert redact_urls("host base-sepolia.g.alchemy.com timed out") == (
            "host base-sepolia.g.alchemy.com timed out"
        )

    def test_none_and_bare_host(self):
        register_url_secrets([None, "", "https://sepolia.base.org", "https://sepolia.base.org/"])
        assert redact_urls("https sepolia.base.org /") == "https sepolia.base.org /"

    def test_clear(self):
        register_url_secrets([f"https://rpc.example.org/v2/{KEY}"])
        clear_url_secrets()
        assert redact_urls(f"unknown key {KEY}") == f"unknown key {KEY}"


class TestMalformedRpcUrls:
    """requests quotes the URL as given when it cannot use it."""

    def test_no_scheme(self):
        out = redact_urls(f"No connection adapters were found for '127.0.0.1:8545/v2/{KEY}'")
        assert out == f"No connection adapters were found for '127.0.0.1:8545/{PLACEHOLDER}'"

    def test_misspelled_scheme(self):
        out = redact_urls(f"No connection adapters were found for 'htps://rpc.example.org/v2/{KEY}'")
        assert out == f"No connection adapters were found for 'htps://rpc.example.org/{PLACEHOLDER}'"

    def test_other_scheme_with_userinfo(self):
        out = redact_urls(f"failed: ftp://user:{KEY}@rpc.example.org/x")
        assert out == f"failed: ftp://rpc.example.org/{PLACEHOLDER}"

    def test_invalid_url(self):
        out = redact_urls(f"Invalid URL 'user:{KEY}@rpc.example.org/v2/{KEY}': No scheme supplied")
        assert KEY not in out
        assert out.startswith("Invalid URL 'rpc.example.org/")

    def test_quoted_bare_host_unchanged(self):
        text = "No connection adapters were found for 'localhost:8545'"
        assert redact_urls(text) == text


class TestRedactUrlsSpeed:
    def test_long_run_of_trailing_punctuation(self):
        """Trailing punctuation is stripped in linear time: a quadratic loop took 24 s here."""
        import time

        text = f"failed {PATH_KEY_URL}" + ")" * 1_000_000
        start = time.perf_counter()
        out = redact_urls(text)
        elapsed = time.perf_counter() - start
        assert KEY not in out
        assert out.endswith(")" * 1_000_000)
        assert elapsed < 1.0, f"took {elapsed:.2f} s"


class TestRedactUrlNonString:
    def test_non_string_value_is_converted(self):
        """A non-string rpc_url (for example a mock provider attribute) does not raise."""
        from unittest.mock import MagicMock

        class UrlObject:
            def __str__(self):
                return PATH_KEY_URL

        assert redact_url(UrlObject()) == f"https://base-sepolia.g.alchemy.com/{PLACEHOLDER}"
        assert isinstance(redact_url(MagicMock()), str)
        assert ChainConnectionError("failed", rpc_url=MagicMock()).rpc_url
