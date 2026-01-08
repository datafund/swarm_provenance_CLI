"""
Common utilities for Swarm Provenance CLI examples.

Provides shared functionality for generating sample data and verifying uploads.
"""

from .sample_generator import (
    generate_text_file,
    generate_audit_log,
    generate_dataset_metadata,
    generate_memory_unit,
)
from .verify import (
    verify_download,
    compare_hashes,
    compute_sha256,
    format_verification_report,
)

__all__ = [
    "generate_text_file",
    "generate_audit_log",
    "generate_dataset_metadata",
    "generate_memory_unit",
    "verify_download",
    "compare_hashes",
    "compute_sha256",
    "format_verification_report",
]
