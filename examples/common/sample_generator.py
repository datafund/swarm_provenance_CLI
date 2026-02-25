"""
Utilities for generating sample data files used in examples.

Usage:
    from common.sample_generator import generate_text_file, generate_json_file
"""

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def generate_text_file(path: str, content: str = None) -> str:
    """
    Generate a sample text file.

    Args:
        path: Output file path.
        content: Custom content. If None, generates a default provenance record.

    Returns:
        Absolute path to the created file.
    """
    if content is None:
        content = (
            f"Provenance Record\n"
            f"Generated: {datetime.now(timezone.utc).isoformat()}\n"
            f"Source: Swarm Provenance CLI Example\n"
            f"\n"
            f"This is a sample data file demonstrating provenance tracking\n"
            f"on the Swarm decentralized storage network.\n"
        )

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content)
    return str(Path(path).resolve())


def generate_json_file(path: str, data: dict = None) -> str:
    """
    Generate a sample JSON file.

    Args:
        path: Output file path.
        data: Custom data dict. If None, generates a sample record.

    Returns:
        Absolute path to the created file.
    """
    if data is None:
        data = {
            "type": "provenance-record",
            "version": "1.0",
            "created": datetime.now(timezone.utc).isoformat(),
            "source": "swarm-provenance-cli-example",
            "payload": {
                "description": "Sample data for provenance demonstration",
                "tags": ["example", "demo", "provenance"],
            },
        }

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2) + "\n")
    return str(Path(path).resolve())


def generate_csv_file(path: str, rows: list = None, headers: list = None) -> str:
    """
    Generate a sample CSV file.

    Args:
        path: Output file path.
        rows: List of row dicts. If None, generates sample data.
        headers: Column headers. Inferred from rows if not provided.

    Returns:
        Absolute path to the created file.
    """
    if rows is None:
        rows = [
            {"id": 1, "timestamp": "2025-01-01T00:00:00Z", "value": 42.5, "label": "sensor-A"},
            {"id": 2, "timestamp": "2025-01-01T01:00:00Z", "value": 43.1, "label": "sensor-A"},
            {"id": 3, "timestamp": "2025-01-01T02:00:00Z", "value": 41.8, "label": "sensor-B"},
        ]

    if headers is None:
        headers = list(rows[0].keys())

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    return str(Path(path).resolve())
