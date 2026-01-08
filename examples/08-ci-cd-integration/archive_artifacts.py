#!/usr/bin/env python3
"""
CI/CD Artifact Archival Script

Archives build artifacts to Swarm with manifest generation.
Designed for use in CI/CD pipelines.

Usage:
    python archive_artifacts.py ./dist --std "RELEASE-V1" --size medium

Environment variables:
    CI_COMMIT_SHA    - Git commit SHA
    CI_COMMIT_REF    - Git ref (branch/tag)
    CI_PIPELINE_ID   - Pipeline identifier
    CI_JOB_ID        - Job identifier
    GITHUB_SHA       - GitHub commit SHA (alternative)
    GITHUB_REF       - GitHub ref (alternative)
"""

import subprocess
import sys
import os
import json
import re
import hashlib
import argparse
from pathlib import Path
from datetime import datetime, timezone


def run_command(args: list) -> tuple:
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def extract_ref(output: str) -> str:
    match = re.search(r"[a-f0-9]{64}", output)
    return match.group(0) if match else ""


def compute_sha256(file_path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def get_ci_environment() -> dict:
    """Detect and return CI environment information."""
    env = {}

    # GitHub Actions
    if os.environ.get("GITHUB_ACTIONS"):
        env = {
            "platform": "github-actions",
            "repository": os.environ.get("GITHUB_REPOSITORY", ""),
            "run_id": os.environ.get("GITHUB_RUN_ID", ""),
            "run_number": os.environ.get("GITHUB_RUN_NUMBER", ""),
            "commit_sha": os.environ.get("GITHUB_SHA", ""),
            "ref": os.environ.get("GITHUB_REF", ""),
            "actor": os.environ.get("GITHUB_ACTOR", ""),
        }
    # GitLab CI
    elif os.environ.get("GITLAB_CI"):
        env = {
            "platform": "gitlab-ci",
            "project": os.environ.get("CI_PROJECT_PATH", ""),
            "pipeline_id": os.environ.get("CI_PIPELINE_ID", ""),
            "job_id": os.environ.get("CI_JOB_ID", ""),
            "commit_sha": os.environ.get("CI_COMMIT_SHA", ""),
            "ref": os.environ.get("CI_COMMIT_REF_NAME", ""),
            "tag": os.environ.get("CI_COMMIT_TAG", ""),
        }
    # Jenkins
    elif os.environ.get("JENKINS_URL"):
        env = {
            "platform": "jenkins",
            "build_number": os.environ.get("BUILD_NUMBER", ""),
            "job_name": os.environ.get("JOB_NAME", ""),
            "commit_sha": os.environ.get("GIT_COMMIT", ""),
            "branch": os.environ.get("GIT_BRANCH", ""),
        }
    # Generic/Local
    else:
        env = {
            "platform": "local",
            "user": os.environ.get("USER", "unknown"),
            "hostname": os.environ.get("HOSTNAME", "unknown"),
        }

    return env


def archive_artifacts(
    directory: Path,
    std: str = "RELEASE-V1",
    size: str = "medium",
    pattern: str = "*",
    output_dir: Path = None,
) -> dict:
    """
    Archive all matching files in directory to Swarm.

    Returns:
        Manifest dictionary
    """
    directory = Path(directory)
    if output_dir is None:
        output_dir = Path("./artifacts")
    output_dir.mkdir(exist_ok=True)

    # Find files
    files = list(directory.glob(pattern))
    if not files:
        print(f"No files matching '{pattern}' in {directory}")
        return {}

    print(f"Found {len(files)} file(s) to archive")
    print()

    artifacts = []
    stamp_id = None

    for i, file_path in enumerate(files):
        if not file_path.is_file():
            continue

        print(f"[{i+1}/{len(files)}] Archiving: {file_path.name}")

        # Build upload command
        cmd = [
            "swarm-prov-upload", "upload",
            "--file", str(file_path),
            "--std", std,
        ]

        # First file: get new stamp
        if i == 0:
            cmd.extend(["--size", size])
        elif stamp_id:
            cmd.extend(["--stamp-id", stamp_id])

        returncode, stdout, stderr = run_command(cmd)

        if returncode != 0:
            print(f"  ERROR: {stderr}")
            continue

        swarm_ref = extract_ref(stdout)

        # Extract stamp ID from first upload
        if i == 0:
            match = re.search(r"Stamp purchased: ([a-f0-9]+)", stdout)
            if match:
                stamp_id = match.group(1)

        print(f"  Reference: {swarm_ref}")

        artifacts.append({
            "filename": file_path.name,
            "swarm_ref": swarm_ref,
            "size": file_path.stat().st_size,
            "sha256": compute_sha256(file_path),
        })

    # Create manifest
    manifest = {
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ci_environment": get_ci_environment(),
        "provenance_standard": std,
        "stamp_id": stamp_id,
        "total_artifacts": len(artifacts),
        "total_size": sum(a["size"] for a in artifacts),
        "artifacts": artifacts,
    }

    # Save manifest
    manifest_file = output_dir / "release-manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2))

    print()
    print(f"Manifest saved: {manifest_file}")

    return manifest


def main():
    parser = argparse.ArgumentParser(
        description="Archive build artifacts to Swarm"
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory containing artifacts"
    )
    parser.add_argument(
        "--std",
        default="RELEASE-V1",
        help="Provenance standard (default: RELEASE-V1)"
    )
    parser.add_argument(
        "--size",
        choices=["small", "medium", "large"],
        default="medium",
        help="Stamp size preset"
    )
    parser.add_argument(
        "--pattern",
        default="*",
        help="Glob pattern for files (default: *)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./artifacts"),
        help="Output directory for manifest"
    )

    args = parser.parse_args()

    print("=" * 55)
    print("Swarm Provenance CLI - CI/CD Artifact Archival")
    print("=" * 55)
    print()

    # Check CLI
    returncode, stdout, _ = run_command(["swarm-prov-upload", "--version"])
    if returncode != 0:
        print("ERROR: swarm-prov-upload not found")
        sys.exit(1)
    print(f"CLI: {stdout.strip()}")

    # Health check
    returncode, _, stderr = run_command(["swarm-prov-upload", "health"])
    if returncode != 0:
        print(f"WARNING: Health check failed: {stderr}")
    print()

    # Show CI environment
    ci_env = get_ci_environment()
    print(f"CI Platform: {ci_env.get('platform', 'unknown')}")
    if ci_env.get("commit_sha"):
        print(f"Commit: {ci_env['commit_sha'][:12]}...")
    print()

    # Archive
    manifest = archive_artifacts(
        args.directory,
        std=args.std,
        size=args.size,
        pattern=args.pattern,
        output_dir=args.output_dir,
    )

    if not manifest:
        print("No artifacts archived")
        sys.exit(1)

    print()
    print("=" * 55)
    print("Archive Complete")
    print("=" * 55)
    print()
    print(f"Artifacts: {manifest['total_artifacts']}")
    print(f"Total size: {manifest['total_size']} bytes")
    print(f"Manifest: {args.output_dir / 'release-manifest.json'}")

    # Output for CI systems
    if manifest["artifacts"]:
        first_ref = manifest["artifacts"][0]["swarm_ref"]
        print()
        print(f"::set-output name=swarm_ref::{first_ref}")  # GitHub Actions
        print(f"SWARM_REF={first_ref}")  # Generic

    return 0


if __name__ == "__main__":
    sys.exit(main())
