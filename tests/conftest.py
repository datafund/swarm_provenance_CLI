"""Shared test configuration — loads .env before any test module is imported."""

from dotenv import load_dotenv

load_dotenv()

import pytest


@pytest.fixture(autouse=True)
def _clear_rpc_url_secrets():
    """ChainProvider registers RPC URL secrets in a module-level registry: start each test empty."""
    from swarm_provenance_uploader.chain.redact import clear_url_secrets

    clear_url_secrets()
    yield
    clear_url_secrets()


@pytest.fixture
def failing_rpc_server():
    """A local "RPC" that fails every request and repeats the request path (#187).

    Set ``server.mode``: "http401" answers HTTP 401 with the path in the
    body; "jsonrpc" answers a JSON-RPC error whose message holds the path;
    "html" answers HTTP 200 with an HTML page (not JSON) that quotes the path.
    """
    import http.server
    import json
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.server.mode == "http401":
                body = f"Unauthorized: {self.path}".encode()
                status, content_type = 401, "text/plain"
            elif self.server.mode == "html":
                body = f"<html><body>The requested URL {self.path} was not found</body></html>".encode()
                status, content_type = 200, "text/html"
            else:
                request = json.loads(raw)
                body = json.dumps({
                    "jsonrpc": "2.0",
                    "id": request.get("id"),
                    "error": {"code": -32005, "message": f"invalid api key in {self.path}"},
                }).encode()
                status, content_type = 200, "application/json"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    server.mode = "http401"
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def closed_port():
    """A local port with nothing listening: connections to it are refused."""
    import socket

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture
def no_web3_retry_sleep(monkeypatch):
    """Skip the backoff sleep of web3's HTTP retries, which makes failing-RPC tests slow."""
    rpc = pytest.importorskip("web3.providers.rpc.rpc")
    monkeypatch.setattr(rpc.time, "sleep", lambda seconds: None)
