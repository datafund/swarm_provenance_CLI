"""Tests for RPC URL redaction in chain errors (#169)."""

import pytest

from swarm_provenance_uploader.chain.redact import PLACEHOLDER, redact_url, redact_urls
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
