"""Packaging regression tests (#133)."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".sh", ".toml", ".txt", ".cfg", ".ini"}

# An install of the package by name from an index, with any installer and flags.
INSTALL_BY_NAME = re.compile(
    r"(?i)\b(?:pip3?|pipx|uv\s+(?:pip|tool)|python3?\s+-m\s+pip)\s+install\b[^\n]*?"
    r"[\"']?swarm[-_]provenance[-_]uploader\b(?![^\n]*?@\s*git\+)"
    r"|\b(?:uv|poetry)\s+add\b[^\n]*?swarm[-_]provenance[-_]uploader\b(?![^\n]*?@\s*git\+)"
)
# Lines that warn about exactly this are allowed
WARNING = re.compile(r"(?i)not (?:published )?on PyPI|\bnever\b")


def _tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        paths = [ROOT / line for line in out.splitlines()]
    except (OSError, subprocess.CalledProcessError):
        skip = {".git", ".venv", "venv", "env", ".tox", ".nox", "build", "dist", "node_modules"}
        paths = [p for p in ROOT.rglob("*")
                 if not (set(p.relative_to(ROOT).parts) & skip)
                 and not any(part.endswith(".egg-info") for part in p.relative_to(ROOT).parts)]
    return [p for p in paths if p.is_file() and p.suffix in TEXT_SUFFIXES]


def test_installer_regex_catches_common_forms():
    for line in ["pip install swarm-provenance-uploader", "pip install -U swarm-provenance-uploader",
                 "pip3 install --upgrade 'swarm-provenance-uploader[x402]'", "python -m pip install swarm_provenance_uploader",
                 "uv pip install swarm-provenance-uploader", "pipx install swarm-provenance-uploader",
                 "uv add swarm-provenance-uploader", "poetry add Swarm-Provenance-Uploader"]:
        assert INSTALL_BY_NAME.search(line), line
    assert not INSTALL_BY_NAME.search(
        'pip install "swarm-provenance-uploader[x402] @ git+https://github.com/datafund/swarm_provenance_CLI@v1"')


def test_no_instruction_installs_the_unregistered_pypi_name():
    """The package is not on PyPI: installing it by name would fetch someone else's."""
    offenders = []
    for path in _tracked_files():
        # This file's own examples, and the changelog's description of the issue
        if path.name in ("test_packaging.py", "CHANGELOG.md"):
            continue
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            if INSTALL_BY_NAME.search(line) and not WARNING.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    assert offenders == []


def _project_table():
    pyproject = (ROOT / "pyproject.toml").read_text()
    return pyproject.split("[project]", 1)[1].split("\n[", 1)[0], pyproject


def test_single_version_source():
    project, pyproject = _project_table()
    assert re.search(r"(?m)^version\s*=", project) is None
    assert re.search(r"(?m)^dynamic\s*=\s*\[[^\]]*[\"']version[\"']", project)
    assert re.search(r"version\s*=\s*\{\s*attr\s*=\s*[\"']swarm_provenance_uploader\.__version_base__[\"']", pyproject)


def test_unused_x402_sdk_not_a_dependency():
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert re.search(r"""(?m)^\s*["']x402\s*(?:[<>=!~;\[]|["'])""", pyproject) is None


def test_install_hints_match_the_extras():
    """The floors printed in install hints are the ones pyproject declares."""
    from swarm_provenance_uploader._requirements import ETH_ACCOUNT_REQUIREMENT, WEB3_REQUIREMENT

    pyproject = (ROOT / "pyproject.toml").read_text()
    for extra in ("x402", "blockchain"):
        block = re.search(rf"(?m)^{extra}\s*=\s*\[(.*?)\]", pyproject, re.S).group(1)
        assert f'"{WEB3_REQUIREMENT}"' in block, extra
        assert f'"{ETH_ACCOUNT_REQUIREMENT}"' in block, extra
