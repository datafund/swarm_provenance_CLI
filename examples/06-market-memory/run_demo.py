#!/usr/bin/env python3
"""
Market Memory Demo - Python Version

Demonstrates market prediction memory units on Swarm:
1. Verify canonical hash of a prediction memory unit
2. Upload prediction with --std "MARKET-MEMORY-V1"
3. Create and upload observation linking to the prediction
4. Download both and verify canonical hashes

Usage:
    python run_demo.py
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

# Import canonical hashing from create_memory_unit
sys.path.insert(0, str(SCRIPT_DIR))
from create_memory_unit import canonical_hash, verify_hash


def sha256_file(path: str) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cli(*args) -> subprocess.CompletedProcess:
    """Run a swarm-prov-upload CLI command."""
    cmd = ["swarm-prov-upload"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result


def extract_swarm_ref(output: str) -> str:
    """Extract Swarm reference hash from CLI output."""
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if "Swarm Reference Hash:" in line and i + 1 < len(lines):
            ref = lines[i + 1].strip()
            if len(ref) >= 64:
                return ref
    return ""


def main():
    parser = argparse.ArgumentParser(description="Market memory demo")
    parser.add_argument(
        "--prediction", "-p",
        default=str(SCRIPT_DIR / "prediction_001.json"),
        help="Prediction JSON file (default: prediction_001.json)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.prediction):
        print(f"ERROR: File not found: {args.prediction}")
        sys.exit(1)

    print("=" * 55)
    print("  Swarm Provenance CLI - Market Memory (Python)")
    print("=" * 55)

    # --- Step 1: Verify canonical hash ---
    print("\n--- Step 1: Verify prediction canonical hash ---")
    with open(args.prediction) as f:
        prediction = json.load(f)

    if verify_hash(prediction):
        print(f"PASS: Canonical hash verified for prediction")
        print(f"  Hash: {prediction['content_hash']}")
    else:
        print(f"FAIL: Canonical hash mismatch!")
        sys.exit(1)

    # --- Step 2: Check health ---
    print("\n--- Step 2: Check gateway health ---")
    result = run_cli("health")
    if result.returncode != 0:
        print(f"Gateway not available: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    # --- Step 3: Upload prediction ---
    print("\n--- Step 3: Upload prediction with --std MARKET-MEMORY-V1 ---")
    pred_hash = sha256_file(args.prediction)
    print(f"File:   {args.prediction}")
    print(f"SHA256: {pred_hash}")

    print("\nUploading (trying pool first)...")
    result = run_cli("upload", "--file", args.prediction, "--std", "MARKET-MEMORY-V1", "--usePool")
    if result.returncode != 0:
        print("Pool not available, falling back to regular stamp purchase...")
        result = run_cli("upload", "--file", args.prediction, "--std", "MARKET-MEMORY-V1")
        if result.returncode != 0:
            print(f"Upload failed: {result.stderr or result.stdout}")
            sys.exit(1)

    print(result.stdout.strip())
    pred_ref = extract_swarm_ref(result.stdout)
    if not pred_ref:
        print("Could not extract Swarm reference from output")
        sys.exit(1)
    print(f"\nPrediction Reference: {pred_ref}")

    # --- Step 4: Create and upload observation ---
    print("\n--- Step 4: Upload observation linking to prediction ---")

    # Load the sample observation and update prediction_ref
    obs_path = str(SCRIPT_DIR / "observation_001.json")
    with open(obs_path) as f:
        observation = json.load(f)

    observation["prediction_ref"] = pred_ref
    # Recompute canonical hash with the actual prediction reference
    observation["content_hash"] = canonical_hash(observation)

    # Write updated observation to temp file
    temp_obs = str(SCRIPT_DIR / "observation_temp.json")
    with open(temp_obs, "w") as f:
        json.dump(observation, f, indent=2)
        f.write("\n")

    obs_hash = sha256_file(temp_obs)
    print(f"Observation links to prediction: {pred_ref}")
    print(f"SHA256: {obs_hash}")

    print("\nUploading (trying pool first)...")
    result = run_cli("upload", "--file", temp_obs, "--std", "MARKET-MEMORY-V1", "--usePool")
    if result.returncode != 0:
        print("Pool not available, falling back to regular stamp purchase...")
        result = run_cli("upload", "--file", temp_obs, "--std", "MARKET-MEMORY-V1")
        if result.returncode != 0:
            print(f"Upload failed: {result.stderr or result.stdout}")
            os.remove(temp_obs)
            sys.exit(1)

    print(result.stdout.strip())
    obs_ref = extract_swarm_ref(result.stdout)
    os.remove(temp_obs)

    if not obs_ref:
        print("Could not extract Swarm reference from output")
        sys.exit(1)
    print(f"\nObservation Reference: {obs_ref}")

    # --- Step 5: Download and verify prediction ---
    print("\n--- Step 5: Download and verify prediction ---")
    download_dir = str(SCRIPT_DIR / "downloads")
    os.makedirs(download_dir, exist_ok=True)
    for f in os.listdir(download_dir):
        os.remove(os.path.join(download_dir, f))

    result = run_cli("download", pred_ref, "--output-dir", download_dir)
    if result.returncode != 0:
        print(f"Download failed: {result.stderr or result.stdout}")
        sys.exit(1)
    print(result.stdout.strip())

    downloaded_files = os.listdir(download_dir)
    if not downloaded_files:
        print("ERROR: No files in download directory")
        sys.exit(1)

    data_files = [f for f in downloaded_files if f.endswith(".data")]
    if data_files:
        downloaded_file = os.path.join(download_dir, data_files[0])
    else:
        downloaded_file = os.path.join(download_dir, downloaded_files[0])

    # Verify file hash
    original_hash = sha256_file(args.prediction)
    downloaded_hash = sha256_file(downloaded_file)
    print(f"\nOriginal:   {original_hash}")
    print(f"Downloaded: {downloaded_hash}")

    if original_hash != downloaded_hash:
        print("\nFAIL: Prediction hash mismatch!")
        sys.exit(1)
    print("\nPASS: Prediction data integrity verified.")

    # Verify canonical hash of downloaded prediction
    print("\nVerifying canonical hash of downloaded prediction...")
    with open(downloaded_file) as f:
        downloaded_pred = json.load(f)

    if verify_hash(downloaded_pred):
        print(f"PASS: Canonical hash verified.")
    else:
        print(f"FAIL: Canonical hash mismatch!")
        sys.exit(1)

    # --- Summary ---
    print("\n--- Summary ---")
    print(f"Prediction Reference:  {pred_ref}")
    print(f"Observation Reference: {obs_ref}")
    print(f"Prediction→Outcome chain: {pred_ref} ← {obs_ref}")
    print("Both memory units use canonical hashing for content integrity.")


if __name__ == "__main__":
    main()
