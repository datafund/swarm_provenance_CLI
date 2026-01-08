"""
Sample data generators for Swarm Provenance CLI examples.

Provides utilities to create realistic sample data for demonstrations.
"""

import json
import hashlib
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path


def generate_text_file(
    output_path: Path,
    content: Optional[str] = None,
    lines: int = 10
) -> Path:
    """
    Generate a simple text file for basic upload demos.

    Args:
        output_path: Path where the file will be created
        content: Custom content (if None, generates sample content)
        lines: Number of lines to generate if using default content

    Returns:
        Path to the created file
    """
    if content is None:
        timestamp = datetime.now(timezone.utc).isoformat()
        content_lines = [
            f"Sample data file generated at {timestamp}",
            "=" * 50,
            "",
        ]
        for i in range(1, lines + 1):
            content_lines.append(f"Line {i}: This is sample provenance data.")
        content_lines.append("")
        content_lines.append("End of sample file.")
        content = "\n".join(content_lines)

    output_path = Path(output_path)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def generate_audit_log(
    output_path: Path,
    event_type: str = "DATA_ACCESS",
    user_id: str = "user-001",
    resource: str = "/api/data/records",
    action: str = "READ",
    num_entries: int = 1,
) -> Path:
    """
    Generate a realistic audit log JSON file.

    Args:
        output_path: Path where the file will be created
        event_type: Type of audit event
        user_id: User identifier
        resource: Resource being accessed
        action: Action performed
        num_entries: Number of audit entries to generate

    Returns:
        Path to the created file
    """
    entries = []
    base_time = datetime.now(timezone.utc)

    for i in range(num_entries):
        entry = {
            "id": f"audit-{base_time.strftime('%Y%m%d')}-{i+1:04d}",
            "timestamp": base_time.isoformat(),
            "event_type": event_type,
            "user_id": user_id,
            "resource": resource,
            "action": action,
            "ip_address": f"192.168.1.{100 + i}",
            "user_agent": "Mozilla/5.0 (compatible; AuditSystem/1.0)",
            "status": "SUCCESS",
            "metadata": {
                "session_id": f"sess-{hashlib.sha256(f'{user_id}-{i}'.encode()).hexdigest()[:12]}",
                "request_id": f"req-{hashlib.sha256(f'{base_time.isoformat()}-{i}'.encode()).hexdigest()[:16]}",
            }
        }
        entries.append(entry)

    audit_log = {
        "schema_version": "1.0",
        "generated_at": base_time.isoformat(),
        "source_system": "compliance-audit-service",
        "entries": entries,
    }

    output_path = Path(output_path)
    output_path.write_text(
        json.dumps(audit_log, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return output_path


def generate_dataset_metadata(
    output_path: Path,
    title: str = "Sample Research Dataset",
    authors: Optional[list] = None,
    description: str = "A sample dataset for demonstration purposes.",
    keywords: Optional[list] = None,
) -> Path:
    """
    Generate a research dataset metadata file (inspired by DataCite schema).

    Args:
        output_path: Path where the file will be created
        title: Dataset title
        authors: List of author names
        description: Dataset description
        keywords: List of keywords

    Returns:
        Path to the created file
    """
    if authors is None:
        authors = ["Jane Doe", "John Smith"]
    if keywords is None:
        keywords = ["sample", "research", "provenance", "data"]

    timestamp = datetime.now(timezone.utc)

    metadata = {
        "schema_version": "datacite-4.4",
        "identifier": {
            "type": "DOI",
            "value": f"10.5281/example.{timestamp.strftime('%Y%m%d%H%M%S')}"
        },
        "title": title,
        "creators": [{"name": author} for author in authors],
        "publication_year": timestamp.year,
        "description": description,
        "subjects": [{"term": kw} for kw in keywords],
        "dates": [
            {"date": timestamp.date().isoformat(), "type": "Created"},
        ],
        "rights": {
            "identifier": "CC-BY-4.0",
            "name": "Creative Commons Attribution 4.0 International"
        },
        "provenance": {
            "standard": "PROV-O",
            "generated_at": timestamp.isoformat(),
            "generator": "swarm-provenance-cli-examples"
        }
    }

    output_path = Path(output_path)
    output_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return output_path


def generate_memory_unit(
    output_path: Path,
    domain: str = "market-forecast",
    payload: Optional[dict] = None,
    unit_id: Optional[str] = None,
) -> Path:
    """
    Generate a SemantiCord-inspired memory unit JSON file.

    Memory units are self-contained records with:
    - Unique identifier
    - Domain classification
    - Timestamp
    - Payload (domain-specific data)
    - Content hash for verification

    Args:
        output_path: Path where the file will be created
        domain: Domain classification for the memory unit
        payload: Domain-specific payload data
        unit_id: Custom unit ID (auto-generated if None)

    Returns:
        Path to the created file
    """
    timestamp = datetime.now(timezone.utc)

    if unit_id is None:
        unit_id = f"mu-{timestamp.strftime('%Y%m%d%H%M%S')}"

    if payload is None:
        payload = {
            "event": "price_observation",
            "asset": "BTC/USD",
            "price": 45000.00,
            "volume_24h": 28500000000,
            "source": "aggregated"
        }

    # Create the memory unit without hash first
    memory_unit = {
        "id": unit_id,
        "version": "1.0",
        "domain": domain,
        "timestamp": timestamp.isoformat(),
        "payload": payload,
        "metadata": {
            "created_by": "swarm-provenance-cli-examples",
            "schema": f"{domain}-v1"
        }
    }

    # Compute canonical hash (sorted keys, no whitespace)
    canonical = json.dumps(memory_unit, sort_keys=True, separators=(",", ":"))
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # Add hash to the unit
    memory_unit["content_hash"] = content_hash

    output_path = Path(output_path)
    output_path.write_text(
        json.dumps(memory_unit, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return output_path


def generate_csv_dataset(
    output_path: Path,
    rows: int = 100,
    columns: Optional[list] = None,
) -> Path:
    """
    Generate a sample CSV dataset for scientific data examples.

    Args:
        output_path: Path where the file will be created
        rows: Number of data rows to generate
        columns: Column names (uses defaults if None)

    Returns:
        Path to the created file
    """
    import random

    if columns is None:
        columns = ["timestamp", "sensor_id", "temperature", "humidity", "pressure"]

    lines = [",".join(columns)]
    base_time = datetime.now(timezone.utc)

    for i in range(rows):
        row_time = base_time.replace(minute=i % 60, second=0)
        row = [
            row_time.isoformat(),
            f"sensor-{(i % 5) + 1:03d}",
            f"{20 + random.uniform(-5, 10):.2f}",
            f"{45 + random.uniform(-10, 20):.1f}",
            f"{1013 + random.uniform(-10, 10):.1f}",
        ]
        lines.append(",".join(row))

    output_path = Path(output_path)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
