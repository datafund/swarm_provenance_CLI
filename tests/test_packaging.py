"""Packaging regression tests (#133)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".sh", ".toml", ".txt", ".cfg"}
INSTALL_BY_NAME = re.compile(r"pip install\s+[\"']?swarm[-_]provenance[-_]uploader")


def _project_files():
    for path in ROOT.rglob("*"):
        parts = set(path.relative_to(ROOT).parts)
        if parts & {".git", ".venv", "venv", "build", "dist", "node_modules"} or any(
                p.endswith(".egg-info") for p in parts):
            continue
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            yield path


def test_no_instruction_installs_the_unregistered_pypi_name():
    """The package is not on PyPI: installing it by name would fetch someone else's."""
    offenders = []
    for path in _project_files():
        if path.name == "test_packaging.py":
            continue
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            # A warning that explains the risk (inside backticks) is fine
            # Installing by name is fine only as "name @ git+https://..." (a direct
            # reference); a warning that explains the risk (in backticks) too.
            if (INSTALL_BY_NAME.search(line) and "@ git+https://" not in line
                    and "`pip install swarm-provenance-uploader`" not in line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    assert offenders == []


def test_single_version_source():
    pyproject = (ROOT / "pyproject.toml").read_text()
    project = pyproject.split("[project]", 1)[1].split("\n[", 1)[0]
    assert re.search(r'(?m)^version\s*=', project) is None
    assert 'dynamic = ["version"]' in project
    assert 'attr = "swarm_provenance_uploader.__version_base__"' in pyproject


def test_unused_x402_sdk_not_a_dependency():
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert re.search(r'(?m)^\s*"x402[<>=]', pyproject) is None
