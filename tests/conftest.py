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
