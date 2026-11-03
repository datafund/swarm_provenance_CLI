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


class TestUrlAfterWordCharacter:
    """A URL is redacted when a word character comes directly before it (#190).

    No secrets are registered here, so only the URL pattern can remove the key.
    """

    @pytest.mark.parametrize(
        "prefix",
        ["1", "rpc_", "%22"],
        ids=["digit", "underscore", "percent-encoded-quote"],
    )
    def test_prefix_before_url(self, prefix):
        out = redact_urls(f"failed: {prefix}{PATH_KEY_URL}")
        assert KEY not in out
        assert out == f"failed: {prefix}https://base-sepolia.g.alchemy.com/{PLACEHOLDER}"

    def test_long_run_of_scheme_characters_before_url(self):
        """More than 31 scheme characters before "://" still let the URL match."""
        out = redact_urls("failed: " + "x" * 40 + PATH_KEY_URL)
        assert KEY not in out
        assert out.endswith(f"https://base-sepolia.g.alchemy.com/{PLACEHOLDER}")


def _assert_linear_time(func, build, size, factor=10, max_ratio=20, fail_ratio=50, attempts=3,
                        min_total=0.1, deadline=5.0):
    """Fail if func(build(size)) takes max_ratio times longer than func(build(size // factor)).

    A linear scan takes about factor times longer on the larger input, and a
    quadratic one about factor ** 2 times longer. A ratio, not a fixed time
    limit, stays the same on a slow machine (#238). The time is the CPU time
    of this thread, so other processes on the machine do not count. Each
    input is run again until the calls took min_total seconds in total, and
    the time per call is compared, the way timeit's autorange does: a clock
    that ticks only every 15.6 ms (time.thread_time on Windows) then still
    measures a call that takes less than a millisecond. A ratio of
    fail_ratio or more fails at once. A ratio from max_ratio up to
    fail_ratio is measured again, up to attempts times, so that one pause
    does not fail the test. If thread_time has not reached min_total after
    deadline seconds of wall-clock time, the test fails instead of looping.
    """
    import time

    def timed(text):
        calls = 0
        start = time.thread_time()
        give_up = time.perf_counter() + deadline
        while True:
            func(text)
            calls += 1
            total = time.thread_time() - start
            if total >= min_total:
                return total / calls
            if time.perf_counter() >= give_up:
                pytest.fail(f"time.thread_time did not reach {min_total} s after {calls} calls")

    small, large = build(size // factor), build(size)
    ratios = []
    for _ in range(attempts):
        small_time, large_time = timed(small), timed(large)
        ratio = large_time / max(small_time, 1e-6)
        if ratio < max_ratio:
            return
        ratios.append(f"{ratio:.1f} ({small_time:.3f} s, {large_time:.3f} s)")
        if ratio >= fail_ratio:
            break
    pytest.fail(f"{factor}x the input took more than {max_ratio}x the time: {', '.join(ratios)}")


class TestAssertLinearTime:
    """The timing helper with a clock as coarse as time.thread_time on Windows (about 15.6 ms)."""

    @pytest.fixture
    def coarse_clock(self, monkeypatch):
        import time

        real = time.thread_time
        tick = 0.0156
        monkeypatch.setattr(time, "thread_time", lambda: (real() // tick) * tick)

    @staticmethod
    def _quadratic(text):
        return sum(1 for _ in range(len(text)) for _ in range(len(text) // 100))

    @pytest.mark.parametrize("size", [10_000, 100_000, 1_000_000])
    def test_linear_passes_with_coarse_clock(self, coarse_clock, size):
        _assert_linear_time(redact_urls, lambda n: "a" * n + f" {PATH_KEY_URL}", size)

    def test_frozen_clock_fails_after_deadline(self, monkeypatch):
        """A thread_time that never advances fails the test after about 5 s instead of hanging."""
        import time

        monkeypatch.setattr(time, "thread_time", lambda: 0.0)
        start = time.perf_counter()
        with pytest.raises(pytest.fail.Exception, match=r"time\.thread_time did not reach 0\.1 s after \d+ calls"):
            _assert_linear_time(len, lambda n: "a" * n, 1_000)
        assert 4.5 <= time.perf_counter() - start < 10

    def test_quadratic_fails_with_coarse_clock(self, coarse_clock):
        with pytest.raises(pytest.fail.Exception, match="took more than 20x the time"):
            _assert_linear_time(self._quadratic, lambda n: "a" * n, 10_000)


class TestRedactUrlsSpeed:
    """The time check runs first, on inputs small enough that a quadratic
    scan fails it within seconds. The full-size call after it checks the
    output."""

    def test_long_run_of_trailing_punctuation(self):
        """Trailing punctuation is stripped in linear time: a quadratic loop took 24 s here."""
        _assert_linear_time(redact_urls, lambda n: f"failed {PATH_KEY_URL}" + ")" * n, 100_000)
        text = f"failed {PATH_KEY_URL}" + ")" * 1_000_000
        out = redact_urls(text)
        assert KEY not in out
        assert out.endswith(")" * 1_000_000)

    @pytest.mark.parametrize(
        "build, size, timed_size",
        [
            (lambda n: "a." * n, 100_000, 10_000),
            (lambda n: "Could not decode '<html><body>" + "a-" * n + "</body></html>'", 50_000, 10_000),
            (lambda n: "a" * n, 1_000_000, 10_000),
        ],
        ids=["dotted-run", "hyphenated-html-body", "letter-run"],
    )
    def test_long_run_of_scheme_characters(self, build, size, timed_size):
        """A long run of letters joined by dots or hyphens is scanned in linear time.

        An unbounded scheme pattern took about 58 s on "a." * 100000.
        """
        _assert_linear_time(redact_urls, lambda n: build(n) + f" {PATH_KEY_URL}", timed_size)
        text = build(size)
        out = redact_urls(text + f" {PATH_KEY_URL}")
        assert out.startswith(text)
        assert KEY not in out


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


class TestRegisteredSecretsDoNotOverRedact:
    """Only credential-like URL pieces are registered; chain names and hashes survive."""

    @staticmethod
    def _provider(rpc_url):
        """A real ChainProvider (it registers the URL secrets), with web3 mocked."""
        from unittest.mock import MagicMock, patch

        from swarm_provenance_uploader.chain.provider import ChainProvider

        web3_cls = MagicMock()
        web3_cls.return_value.eth.chain_id = 84532
        with patch("swarm_provenance_uploader.chain.provider._import_web3", return_value=web3_cls):
            return ChainProvider(chain="base-sepolia", rpc_url=rpc_url)

    @pytest.mark.parametrize("rpc_url", [
        f"https://lb.drpc.org/ogrpc?network=base-sepolia&dkey={KEY}",
        f"https://lb.drpc.live/base-sepolia/{KEY}",
    ], ids=["drpc-query", "drpc-path"])
    def test_drpc_network_name_survives(self, rpc_url):
        self._provider(rpc_url)
        message = str(ChainConfigurationError(
            f"No contract code at {'0x' + 'ab' * 20} on base-sepolia: wrong contract address or chain."
        ))
        assert message.endswith("on base-sepolia: wrong contract address or chain.")
        echoed = redact_urls(f"Could not decode '<html>No route for {rpc_url.split('drpc.', 1)[1][3:]}</html>'")
        assert KEY not in echoed
        assert KEY not in redact_urls(f"invalid dkey {KEY}")

    @pytest.mark.parametrize("segment", ["deadbeef", "00000000", "network", "mainnet"])
    def test_hex_or_word_segment_not_registered(self, segment):
        register_url_secrets([f"https://rpc.example.org/{segment}/v2"])
        tx_hash = "0x" + segment * 8
        assert redact_urls(f"Transaction {tx_hash} failed") == f"Transaction {tx_hash} failed"
        assert redact_urls(f"segment {segment} alone") == f"segment {segment} alone"

    def test_query_keys_never_registered(self):
        register_url_secrets([f"https://rpc.example.org/?subscription_key1={KEY}"])
        assert redact_urls("missing subscription_key1") == "missing subscription_key1"
        assert KEY not in redact_urls(f"bad value {KEY}")

    def test_credential_like_pieces_registered(self):
        register_url_secrets(["https://rpc.example.org/v2/abc12345/x?token=AAAAAAAAAAAAAAAAAAA"])
        assert redact_urls("key abc12345 rejected") == f"key {PLACEHOLDER} rejected"
        assert redact_urls("token AAAAAAAAAAAAAAAAAAA rejected") == f"token {PLACEHOLDER} rejected"

    def test_public_strings_skipped(self):
        register_url_secrets([f"https://rpc.example.org/base-sepolia-archive1/{KEY}"],
                             public=["https://base-sepolia-archive1.example.org"])
        assert redact_urls("on base-sepolia-archive1") == "on base-sepolia-archive1"
        assert KEY not in redact_urls(f"key {KEY}")


class TestAlwaysRegisteredParts:
    """The last path segment and credential-named query values are registered whatever their shape."""

    TOKEN = "abcdefghijklmno"

    @pytest.mark.parametrize("url", [
        f"https://rpc.example.org/rpc/{TOKEN}",
        f"https://rpc.example.org/rpc/{TOKEN}/",
        f"https://rpc.example.org/?apikey={TOKEN}",
        f"https://rpc.example.org/?API_KEY={TOKEN}",
        f"https://rpc.example.org/?network=base&Access_Token={TOKEN}",
    ])
    def test_short_letters_only_token(self, url):
        register_url_secrets([url])
        assert redact_urls(f"invalid api key: {self.TOKEN}") == f"invalid api key: {PLACEHOLDER}"

    def test_other_query_values_still_need_a_key_shape(self):
        register_url_secrets([f"https://rpc.example.org/?region={self.TOKEN}"])
        assert redact_urls(f"region {self.TOKEN}") == f"region {self.TOKEN}"

    def test_last_segment_that_is_a_preset_string_is_skipped(self):
        register_url_secrets(["https://rpc.example.org/base-sepolia"], public=["base-sepolia"])
        assert redact_urls("on base-sepolia") == "on base-sepolia"


class TestCodeCheckRejection:
    """The contract code check reports a JSON-RPC error answer as a rejection (#169)."""

    @staticmethod
    def _client():
        from unittest.mock import MagicMock, patch

        from swarm_provenance_uploader.core.chain_client import ChainClient

        client = ChainClient.__new__(ChainClient)
        client._contract_code_checked = False
        client._contract = MagicMock(address="0x" + "ab" * 20)
        client._provider = MagicMock(rpc_url=PATH_KEY_URL, chain="base-sepolia")
        return client

    def test_web3_rpc_error_is_a_rejection(self):
        web3_exceptions = pytest.importorskip("web3.exceptions")
        client = self._client()
        client._provider.web3.eth.get_code.side_effect = web3_exceptions.Web3RPCError(
            "{'code': -32601, 'message': 'method not allowed'}",
            rpc_response={"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "method not allowed"}},
        )
        with pytest.raises(ChainConfigurationError) as exc_info:
            client._check_contract_code()
        assert not isinstance(exc_info.value, ChainConnectionError)
        assert str(exc_info.value) == "The RPC rejected the contract code check: method not allowed"

    def test_web3_rpc_error_dict_repr_without_response(self):
        """Without rpc_response, a dict-repr text gives only the node's message, redacted."""
        web3_exceptions = pytest.importorskip("web3.exceptions")
        client = self._client()
        client._provider.web3.eth.get_code.side_effect = web3_exceptions.Web3RPCError(
            f"{{'code': -32601, 'message': 'method not allowed at {PATH_KEY_URL}'}}"
        )
        with pytest.raises(ChainConfigurationError) as exc_info:
            client._check_contract_code()
        assert not isinstance(exc_info.value, ChainConnectionError)
        message = str(exc_info.value)
        assert message.startswith("The RPC rejected the contract code check: method not allowed at ")
        assert "'code'" not in message
        assert KEY not in message

    def test_request_timed_out_stays_connection_error(self):
        web3_exceptions = pytest.importorskip("web3.exceptions")
        client = self._client()
        client._provider.web3.eth.get_code.side_effect = web3_exceptions.RequestTimedOut("timed out")
        with pytest.raises(ChainConnectionError) as exc_info:
            client._check_contract_code()
        assert "did not answer the contract code check" in str(exc_info.value)
        assert KEY not in exc_info.value.rpc_url

    def test_transport_failure_stays_connection_error(self):
        client = self._client()
        client._provider.web3.eth.get_code.side_effect = ConnectionError(f"refused: {PATH_KEY_URL}")
        with pytest.raises(ChainConnectionError) as exc_info:
            client._check_contract_code()
        assert KEY not in str(exc_info.value)


def _linked(error):
    """Every exception reachable from error through __cause__ and __context__, error first."""
    seen, found, todo = set(), [], [error]
    while todo:
        exc = todo.pop(0)
        if exc is None or id(exc) in seen:
            continue
        seen.add(id(exc))
        found.append(exc)
        todo.extend([exc.__cause__, exc.__context__])
    return found


def _raise(exc):
    raise exc


class TestRedactExceptionChain:
    """redact_exception_chain replaces the raw exceptions linked to a ChainError (#187)."""

    def test_cause_is_replaced_with_a_redacted_copy(self):
        import traceback

        from swarm_provenance_uploader.chain.exceptions import (
            RedactedException,
            redact_exception_chain,
        )

        original = ConnectionError(f"401 Client Error: Unauthorized for url: {PATH_KEY_URL}")
        try:
            try:
                _raise(original)
            except ConnectionError as e:
                raise ChainConnectionError("The RPC endpoint failed") from e
        except ChainConnectionError as e:
            error = e

        assert redact_exception_chain(error) is error
        cause = error.__cause__
        assert isinstance(cause, RedactedException)
        assert cause.original_type == "builtins.ConnectionError"
        assert str(cause) == (
            "builtins.ConnectionError: 401 Client Error: Unauthorized for url: "
            f"https://base-sepolia.g.alchemy.com/{PLACEHOLDER}"
        )
        # The original frames are kept, so the traceback still shows where it failed
        assert cause.__traceback__ is original.__traceback__
        text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        assert KEY not in text
        assert "_raise" in text
        assert error.__suppress_context__ is True
        # The original object is not changed
        assert KEY in str(original)

    def test_context_and_nested_links(self):
        from swarm_provenance_uploader.chain.exceptions import (
            RedactedException,
            redact_exception_chain,
        )

        register_url_secrets([PATH_KEY_URL])
        inner = OSError(f"refused: /v2/{KEY}")
        middle = ValueError(f"decode failed for {QUERY_KEY_URL}")
        middle.__context__ = inner
        error = ChainConnectionError("failed")
        error.__context__ = middle

        redact_exception_chain(error)

        linked = _linked(error)
        assert len(linked) == 3
        assert all(isinstance(exc, RedactedException) for exc in linked[1:])
        assert [exc.original_type for exc in linked[1:]] == ["builtins.ValueError", "builtins.OSError"]
        for exc in linked:
            assert KEY not in str(exc)
            assert KEY not in repr(exc.args)
        # An implicit context stays shown as a context, not as a cause
        assert error.__suppress_context__ is False
        assert error.__cause__ is None

    def test_suppressed_context_stays_suppressed(self):
        from swarm_provenance_uploader.chain.exceptions import (
            RedactedException,
            redact_exception_chain,
        )

        try:
            try:
                raise ConnectionError(f"for url: {PATH_KEY_URL}")
            except ConnectionError:
                raise ChainConnectionError("failed") from None
        except ChainConnectionError as e:
            error = e

        redact_exception_chain(error)

        assert error.__cause__ is None
        assert error.__suppress_context__ is True
        assert isinstance(error.__context__, RedactedException)
        assert KEY not in str(error.__context__)

    def test_chain_error_link_is_kept_and_its_chain_redacted(self):
        from swarm_provenance_uploader.chain.exceptions import (
            RedactedException,
            redact_exception_chain,
        )

        raw = ConnectionError(f"for url: {PATH_KEY_URL}")
        inner = ChainConnectionError(f"failed: {PATH_KEY_URL}")
        inner.__cause__ = raw
        error = ChainConfigurationError("outer")
        error.__cause__ = inner

        redact_exception_chain(error)

        assert error.__cause__ is inner
        assert isinstance(inner.__cause__, RedactedException)
        assert all(KEY not in str(exc) for exc in _linked(error))

    def test_cycle_and_second_pass(self):
        from swarm_provenance_uploader.chain.exceptions import (
            RedactedException,
            redact_exception_chain,
        )

        first = ValueError(f"a {PATH_KEY_URL}")
        second = ValueError(f"b {PATH_KEY_URL}")
        first.__context__ = second
        second.__context__ = first
        error = ChainConnectionError("failed")
        error.__cause__ = first

        redact_exception_chain(error)
        copy = error.__cause__
        redact_exception_chain(error)

        assert error.__cause__ is copy
        linked = _linked(error)
        assert len(linked) == 3
        assert all(isinstance(exc, RedactedException) for exc in linked[1:])
        assert all(KEY not in str(exc) for exc in linked)

    def test_error_without_chain_is_unchanged(self):
        from swarm_provenance_uploader.chain.exceptions import redact_exception_chain

        error = ChainConnectionError("failed")
        assert redact_exception_chain(error) is error
        assert error.__cause__ is None
        assert error.__context__ is None
        assert error.__suppress_context__ is False

    def test_exception_whose_str_fails(self):
        from swarm_provenance_uploader.chain.exceptions import (
            RedactedException,
            redact_exception_chain,
        )

        class Broken(Exception):
            def __str__(self):
                raise RuntimeError("no text")

        error = ChainConnectionError("failed")
        error.__cause__ = Broken()

        redact_exception_chain(error)

        assert isinstance(error.__cause__, RedactedException)
        assert error.__cause__.original_type.endswith("Broken")
