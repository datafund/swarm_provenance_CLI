"""Where settings come from: the .env file, the x402 key and the RPC URLs (#141)."""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from swarm_provenance_uploader.cli import app, _chain_config

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "swarm_provenance_uploader"
runner = CliRunner()

KEY_VARS = ("X402_PRIVATE_KEY_ENV", "X402_PRIVATE_KEY", "SWARM_X402_PRIVATE_KEY", "MY_X402_KEY")  # gitleaks:allow (variable names, not keys)
KEY_A = "0x" + "a" * 64
KEY_B = "0x" + "b" * 64
KEY_C = "0x" + "c" * 64


@pytest.fixture
def no_key_env(monkeypatch):
    """Start with none of the x402 key variables set."""
    for name in KEY_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def _clean_env(**extra):
    """The current environment without the settings the tests set through a .env file."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("PROVENANCE_GATEWAY_URL", "CHAIN_RPC_URLS", "PYTHONPATH")}
    env.update(extra)
    return env


def _run(code, cwd, env):
    # Run a script file, not "python -c": python-dotenv treats a session
    # without a __main__ file as interactive and searches from the working
    # directory either way, which would hide the bug. The installed
    # swarm-prov-upload entry point is a script file too.
    script = Path(cwd).parent / ("_run_%s.py" % Path(cwd).name)
    script.write_text(code + "\n")
    result = subprocess.run([sys.executable, str(script)], cwd=str(cwd), env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()


PRINT_GATEWAY = ("import swarm_provenance_uploader.config as c; "
                 "print(c.__file__); print(c.GATEWAY_URL)")


# --- .env resolution ---------------------------------------------------------

def test_dotenv_loaded_from_working_directory(tmp_path):
    """A .env in the folder the command runs from is loaded."""
    tmp_path = tmp_path / "work"
    tmp_path.mkdir()
    (tmp_path / ".env").write_text("PROVENANCE_GATEWAY_URL=https://from-cwd.example\n")

    _, gateway = _run(PRINT_GATEWAY, tmp_path, _clean_env())

    assert gateway == "https://from-cwd.example"


def test_dotenv_next_to_install_directory_ignored(tmp_path):
    """A .env beside the installed package does not apply when running from elsewhere."""
    install = tmp_path / "install"
    work = tmp_path / "work"
    work.mkdir()
    shutil.copytree(PACKAGE, install / "swarm_provenance_uploader",
                    ignore=shutil.ignore_patterns("__pycache__"))
    (install / ".env").write_text("PROVENANCE_GATEWAY_URL=https://from-install-dir.example\n")

    module_file, gateway = _run(PRINT_GATEWAY, work, _clean_env(PYTHONPATH=str(install)))

    assert module_file.startswith(str(install.resolve())) or module_file.startswith(str(install))
    assert gateway != "https://from-install-dir.example"


# --- One key source for status display and signing ---------------------------

def test_resolve_key_precedence(no_key_env):
    from swarm_provenance_uploader.core.x402_client import resolve_x402_private_key

    assert resolve_x402_private_key() == (None, None)

    no_key_env.setenv("SWARM_X402_PRIVATE_KEY", KEY_C)
    assert resolve_x402_private_key() == (KEY_C, "SWARM_X402_PRIVATE_KEY")  # gitleaks:allow (variable names, not keys)

    no_key_env.setenv("X402_PRIVATE_KEY", KEY_B)
    assert resolve_x402_private_key() == (KEY_B, "X402_PRIVATE_KEY")  # gitleaks:allow (variable names, not keys)

    no_key_env.setenv("X402_PRIVATE_KEY_ENV", "MY_X402_KEY")
    no_key_env.setenv("MY_X402_KEY", KEY_A)
    assert resolve_x402_private_key() == (KEY_A, "MY_X402_KEY")


def test_custom_key_env_is_strict(no_key_env):
    """With X402_PRIVATE_KEY_ENV set to another name, only that variable is read."""
    from swarm_provenance_uploader.core.x402_client import (
        resolve_x402_private_key, x402_private_key_env_name)

    no_key_env.setenv("X402_PRIVATE_KEY_ENV", "MY_X402_KEY")
    no_key_env.setenv("X402_PRIVATE_KEY", KEY_B)
    no_key_env.setenv("SWARM_X402_PRIVATE_KEY", KEY_C)

    assert resolve_x402_private_key() == (None, None)
    assert x402_private_key_env_name() == "MY_X402_KEY"


def test_key_env_naming_the_default_keeps_legacy_fallback(no_key_env):
    from swarm_provenance_uploader.core.x402_client import resolve_x402_private_key

    no_key_env.setenv("X402_PRIVATE_KEY_ENV", "X402_PRIVATE_KEY")  # gitleaks:allow (variable names, not keys)
    no_key_env.setenv("SWARM_X402_PRIVATE_KEY", KEY_C)

    assert resolve_x402_private_key() == (KEY_C, "SWARM_X402_PRIVATE_KEY")  # gitleaks:allow (variable names, not keys)


def test_x402_status_shows_legacy_key_as_configured(no_key_env):
    """The legacy variable signs, so the status display must count it."""
    no_key_env.setenv("SWARM_X402_PRIVATE_KEY", KEY_C)

    result = runner.invoke(app, ["x402", "status"])

    assert result.exit_code == 0
    assert "Configured" in result.stdout
    assert "SWARM_X402_PRIVATE_KEY" in result.stdout
    assert "c" * 16 not in result.output


def test_x402_status_custom_key_env_not_set(no_key_env):
    """A custom X402_PRIVATE_KEY_ENV whose variable is empty shows Not set, like the signer."""
    no_key_env.setenv("X402_PRIVATE_KEY_ENV", "MY_X402_KEY")
    no_key_env.setenv("X402_PRIVATE_KEY", KEY_B)

    result = runner.invoke(app, ["x402", "status"])

    assert result.exit_code == 0
    assert "Not set" in result.stdout
    assert "export MY_X402_KEY=" in result.stdout
    assert "b" * 16 not in result.output


def test_x402_status_custom_key_env_configured(no_key_env):
    no_key_env.setenv("X402_PRIVATE_KEY_ENV", "MY_X402_KEY")
    no_key_env.setenv("MY_X402_KEY", KEY_A)

    result = runner.invoke(app, ["x402", "status"])

    assert result.exit_code == 0
    assert "Configured" in result.stdout
    assert "MY_X402_KEY" in result.stdout
    assert "a" * 16 not in result.output


def test_x402_balance_accepts_legacy_key(no_key_env):
    no_key_env.setenv("SWARM_X402_PRIVATE_KEY", KEY_C)
    client = MagicMock(wallet_address="0x" + "1" * 40)
    client.get_usdc_balance.return_value = (5_000_000, 5.0)

    with patch("swarm_provenance_uploader.core.x402_client.X402Client", return_value=client):
        result = runner.invoke(app, ["x402", "balance"])

    assert result.exit_code == 0, result.output
    assert "$5.000000" in result.stdout


def test_x402_balance_refuses_when_custom_key_env_empty(no_key_env):
    no_key_env.setenv("X402_PRIVATE_KEY_ENV", "MY_X402_KEY")
    no_key_env.setenv("X402_PRIVATE_KEY", KEY_B)

    with patch("swarm_provenance_uploader.core.x402_client.X402Client") as client_class:
        result = runner.invoke(app, ["x402", "balance"])

    assert result.exit_code == 1
    assert "export MY_X402_KEY=" in result.stdout
    client_class.assert_not_called()


def test_x402_balance_error_redacts_rpc_url(no_key_env):
    """An error that repeats X402_RPC_URL does not print its API key."""
    no_key_env.setenv("X402_PRIVATE_KEY", KEY_A)
    url = "https://base-sepolia.g.alchemy.com/v2/Sup3rSecretApiKey42"
    client = MagicMock()
    client.get_usdc_balance.side_effect = RuntimeError(f"401 Client Error: Unauthorized for url: {url}")

    with patch("swarm_provenance_uploader.core.x402_client.X402Client", return_value=client):
        result = runner.invoke(app, ["x402", "balance"])

    assert result.exit_code == 1
    assert "Sup3rSecretApiKey42" not in result.output
    assert "base-sepolia.g.alchemy.com" in result.output


# --- RPC settings ------------------------------------------------------------

def test_chain_rpc_urls_parsed_from_env(tmp_path):
    tmp_path = tmp_path / "work"
    tmp_path.mkdir()
    env = _clean_env(CHAIN_RPC_URLS=" https://a.example/x , ,https://b.example/y,")
    out = _run("import swarm_provenance_uploader.config as c; print(c.CHAIN_RPC_URLS)", tmp_path, env)
    assert out == ["['https://a.example/x', 'https://b.example/y']"]


def test_chain_rpc_urls_unset_is_none(tmp_path):
    tmp_path = tmp_path / "work"
    tmp_path.mkdir()
    out = _run("import swarm_provenance_uploader.config as c; print(c.CHAIN_RPC_URLS)", tmp_path, _clean_env())
    assert out == ["None"]


def test_chain_rpc_urls_passed_to_chain_client():
    from swarm_provenance_uploader.cli import _get_chain_client

    saved = dict(_chain_config)
    _chain_config["rpc_fallbacks"] = ["https://a.example/x", "https://b.example/y"]
    try:
        with patch("swarm_provenance_uploader.core.chain_client.ChainClient") as client_class:
            _get_chain_client()
    finally:
        _chain_config.clear()
        _chain_config.update(saved)

    assert client_class.call_args.kwargs["rpc_fallbacks"] == ["https://a.example/x", "https://b.example/y"]


def test_chain_enabled_setting_removed():
    """CHAIN_ENABLED did nothing; it is gone from the code and the docs."""
    from swarm_provenance_uploader import config

    assert not hasattr(config, "CHAIN_ENABLED")
    assert "enabled" not in _chain_config
    for doc in ("README.md", "CLAUDE.md", ".env.example", "docs/chain-setup.md"):
        assert "CHAIN_ENABLED" not in (ROOT / doc).read_text(), doc


# --- A key put into X402_PRIVATE_KEY_ENV by mistake is never printed ----------

KEY_AS_NAME = "0x" + "d" * 64
INVALID_NAME_MESSAGE = "X402_PRIVATE_KEY_ENV is not a valid variable name"


def test_invalid_key_env_name_resolves_no_key(no_key_env):
    from swarm_provenance_uploader.core.x402_client import (
        resolve_x402_private_key, x402_private_key_env_name)

    no_key_env.setenv("X402_PRIVATE_KEY_ENV", KEY_AS_NAME)
    no_key_env.setenv("X402_PRIVATE_KEY", KEY_B)

    assert x402_private_key_env_name() is None
    assert resolve_x402_private_key() == (None, None)


@pytest.mark.parametrize("name", ["MY_KEY", "_k", "X402_PRIVATE_KEY", "a1", " MY_KEY "])
def test_valid_key_env_names_accepted(no_key_env, name):
    from swarm_provenance_uploader.core.x402_client import x402_private_key_env_name

    no_key_env.setenv("X402_PRIVATE_KEY_ENV", name)
    assert x402_private_key_env_name() == name.strip()


@pytest.mark.parametrize("name", [KEY_AS_NAME, "d" * 64, "1ABC", "MY-KEY", "MY KEY", "MY\nKEY", "A" * 64])
def test_invalid_key_env_names_rejected(no_key_env, name):
    from swarm_provenance_uploader.core.x402_client import x402_private_key_env_name

    no_key_env.setenv("X402_PRIVATE_KEY_ENV", name)
    assert x402_private_key_env_name() is None


def test_x402_status_does_not_echo_key_in_key_env(no_key_env):
    no_key_env.setenv("X402_PRIVATE_KEY_ENV", KEY_AS_NAME)

    result = runner.invoke(app, ["x402", "status"])

    assert result.exit_code == 0
    assert "d" * 16 not in result.output
    assert INVALID_NAME_MESSAGE in result.output
    assert "Not set" in result.output


def test_x402_balance_does_not_echo_key_in_key_env(no_key_env):
    no_key_env.setenv("X402_PRIVATE_KEY_ENV", KEY_AS_NAME)

    with patch("swarm_provenance_uploader.core.x402_client.X402Client") as client_class:
        result = runner.invoke(app, ["x402", "balance"])

    assert result.exit_code == 1
    assert "d" * 16 not in result.output
    assert INVALID_NAME_MESSAGE in result.output
    client_class.assert_not_called()


def test_config_has_no_unread_x402_constants():
    """The CLI reads these through x402_client at call time; the config copies were unread."""
    from swarm_provenance_uploader import config

    assert not hasattr(config, "X402_PRIVATE_KEY_ENV")
    assert not hasattr(config, "X402_RPC_URL")


# Key-shaped values of other lengths (review round 2): a key with its
# leading zero dropped (63 digits), or any long hex string, is not a name.
def _hex_value(length, first, prefix):
    digits = (first + "7e3a9c51b8f20d64" * 8)[:length]
    return prefix + digits


HEX_VALUES = [
    pytest.param(_hex_value(n, first, prefix), id=f"{n}-{first}-{'0x' if prefix else 'bare'}")
    for n in (63, 40, 32)
    for first in ("d", "1")
    for prefix in ("", "0x")
]


@pytest.mark.parametrize("value", HEX_VALUES)
def test_hex_key_env_value_is_invalid(no_key_env, value):
    from swarm_provenance_uploader.core.x402_client import x402_private_key_env_name

    no_key_env.setenv("X402_PRIVATE_KEY_ENV", value)
    assert x402_private_key_env_name() is None


@pytest.mark.parametrize("value", HEX_VALUES)
def test_x402_status_never_echoes_hex_key_env(no_key_env, value):
    no_key_env.setenv("X402_PRIVATE_KEY_ENV", value)

    result = runner.invoke(app, ["x402", "status"])

    assert result.exit_code == 0
    assert value.replace("0x", "")[:12] not in result.output
    assert INVALID_NAME_MESSAGE in result.output


@pytest.mark.parametrize("value", HEX_VALUES)
def test_x402_balance_never_echoes_hex_key_env(no_key_env, value):
    no_key_env.setenv("X402_PRIVATE_KEY_ENV", value)

    with patch("swarm_provenance_uploader.core.x402_client.X402Client") as client_class:
        result = runner.invoke(app, ["x402", "balance"])

    assert result.exit_code == 1
    assert value.replace("0x", "")[:12] not in result.output
    assert INVALID_NAME_MESSAGE in result.output
    client_class.assert_not_called()


@pytest.mark.parametrize("value", HEX_VALUES)
def test_x402_client_error_never_echoes_hex_key_env(no_key_env, value):
    from swarm_provenance_uploader.core import x402_client
    from swarm_provenance_uploader.exceptions import X402ConfigurationError

    no_key_env.setenv("X402_PRIVATE_KEY_ENV", value)
    with patch.object(x402_client, "_import_x402_deps", return_value=(MagicMock(), MagicMock())):
        with pytest.raises(X402ConfigurationError) as exc_info:
            x402_client.X402Client()

    assert value.replace("0x", "")[:12] not in str(exc_info.value)
    assert INVALID_NAME_MESSAGE in str(exc_info.value)


@pytest.mark.parametrize("name", ["deadbeef", "CAFE", "abc123"])
def test_short_all_hex_name_is_not_printed(no_key_env, name):
    """A valid but all-hex name is used, but never printed: it could be part of a key."""
    from swarm_provenance_uploader.core.x402_client import x402_private_key_env_name

    no_key_env.setenv("X402_PRIVATE_KEY_ENV", name)
    assert x402_private_key_env_name() == name

    status = runner.invoke(app, ["x402", "status"])
    with patch("swarm_provenance_uploader.core.x402_client.X402Client"):
        balance = runner.invoke(app, ["x402", "balance"])

    for result in (status, balance):
        assert name not in result.output
        assert "the variable named by X402_PRIVATE_KEY_ENV" in result.output

    no_key_env.setenv(name, KEY_A)
    status = runner.invoke(app, ["x402", "status"])
    assert "Configured" in status.output
    assert name not in status.output


def test_x402_info_mentions_key_env_and_legacy_name():
    result = runner.invoke(app, ["x402", "info"])

    assert result.exit_code == 0
    assert "X402_PRIVATE_KEY_ENV" in result.output
    assert "SWARM_X402_PRIVATE_KEY" in result.output
