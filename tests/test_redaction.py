"""Tests for URL redaction of credential-bearing RPC URLs (issue #169).

RPC provider URLs carry API keys in the path (Alchemy/Infura/QuickNode
``/v2/<KEY>``) and in userinfo (``key@host``). Chain errors used to echo
them verbatim into terminal output, CI logs and agent transcripts, so
redaction is applied where the errors are constructed and where the CLI
prints them: scheme and host survive, path, query and userinfo do not.
"""

import pytest
from unittest.mock import MagicMock, patch

from swarm_provenance_uploader.redaction import redact_url, redact_urls_in_text
from swarm_provenance_uploader.exceptions import ChainConnectionError


KEYED_URL = "https://eth-sepolia.g.alchemy.com/v2/SECRET_API_KEY_123"
REDACTED = "https://eth-sepolia.g.alchemy.com"


class TestRedactUrl:
    def test_path_api_key_is_stripped(self):
        assert redact_url(KEYED_URL) == REDACTED

    def test_userinfo_is_stripped(self):
        assert redact_url("https://user:pass@rpc.example.com") == "https://rpc.example.com"

    def test_query_string_is_stripped(self):
        assert (
            redact_url("https://rpc.example.com/rpc?apikey=SECRET")
            == "https://rpc.example.com"
        )

    def test_port_is_kept(self):
        assert redact_url("http://127.0.0.1:8545") == "http://127.0.0.1:8545"

    def test_none_passes_through(self):
        assert redact_url(None) is None
        assert redact_url("") == ""

    def test_non_url_becomes_placeholder(self):
        assert redact_url("not a url") == "<url>"
        assert "SECRET" not in redact_url("https://<broken")


class TestRedactUrlsInText:
    def test_embedded_url_in_exception_text(self):
        msg = f"requests.exceptions.ConnectionError: HTTPSConnectionPool(host='x', url={KEYED_URL}/): Max retries exceeded"
        redacted = redact_urls_in_text(msg)
        assert "SECRET_API_KEY_123" not in redacted
        assert REDACTED in redacted
        # Non-URL context around the match survives.
        assert redacted.startswith("requests.exceptions.ConnectionError:")

    def test_plain_text_unchanged(self):
        assert redact_urls_in_text("Transaction reverted (status=0)") == "Transaction reverted (status=0)"
        assert redact_urls_in_text(None) is None


class TestChainErrorsCarryRedactedUrls:
    def test_health_check_failure_redacts_rpc_url(self):
        """The provider must construct ChainConnectionError with a redacted URL."""
        import swarm_provenance_uploader.chain.provider as provider_module

        mock_web3_instance = MagicMock()
        mock_web3_instance.is_connected.return_value = False
        mock_web3_class = MagicMock(return_value=mock_web3_instance)

        with patch.dict("sys.modules", {"web3": MagicMock(Web3=mock_web3_class)}):
            provider_module._Web3 = None
            try:
                from swarm_provenance_uploader.chain.provider import ChainProvider

                provider = ChainProvider(
                    chain="base-sepolia",
                    rpc_url=KEYED_URL,
                    rpc_fallbacks=[],
                )
                with pytest.raises(ChainConnectionError) as excinfo:
                    provider.health_check()

                assert excinfo.value.rpc_url == REDACTED
                assert "SECRET_API_KEY_123" not in str(excinfo.value)
                assert "SECRET_API_KEY_123" not in excinfo.value.message if hasattr(excinfo.value, "message") else True
            finally:
                provider_module._Web3 = None
