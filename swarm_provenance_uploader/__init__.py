"""Swarm Provenance Uploader - CLI toolkit for uploading data to Swarm."""

import subprocess
from pathlib import Path

__version_base__ = "0.3.0"


def _get_git_hash() -> str:
    """Get short git commit hash if available."""
    try:
        # Get the directory where this package is installed
        package_dir = Path(__file__).parent.parent
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=package_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return ""


def get_version() -> str:
    """Get full version string with git hash if available."""
    git_hash = _get_git_hash()
    if git_hash:
        return f"{__version_base__}+git.{git_hash}"
    return __version_base__


# For compatibility with tools that expect __version__
__version__ = get_version()
