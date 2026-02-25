import hashlib
import base64
import tarfile
from pathlib import Path
from typing import List, Tuple

def read_file_content(file_path: Path) -> bytes:
    """Reads a file and returns its raw byte content."""
    with file_path.open("rb") as f:
        content = f.read()
    return content

def calculate_sha256(data: bytes) -> str:
     """Calculates SHA256 hash of byte data and returns hex string."""
     return hashlib.sha256(data).hexdigest()

def base64_encode_data(data: bytes) -> str:
     """Base64 encodes byte data and returns UTF-8 decoded string."""
     return base64.b64encode(data).decode('utf-8')

def get_data_size(data: bytes) -> int:
     """Gets the size of byte data."""
     return len(data)
     
def save_bytes_to_file(file_path: Path, data: bytes) -> None:
    """Saves byte data to the specified file_path."""
    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("wb") as f:
        f.write(data)

def base64_decode_data(b64_data: str) -> bytes:
    """Base64 decodes a string and returns bytes."""
    try:
        return base64.b64decode(b64_data)
    except Exception as e: # Catch potential base64 padding errors etc.
        raise ValueError(f"Invalid Base64 data: {e}") from e


def create_tar_from_directory(directory: Path, output_path: Path) -> Path:
    """Creates a raw TAR archive (no compression) from a directory.

    Swarm requires uncompressed TAR for manifest uploads.

    Args:
        directory: Path to the directory to archive.
        output_path: Path where the TAR file will be written.

    Returns:
        Path to the created TAR file.

    Raises:
        ValueError: If directory is empty or doesn't exist.
        OSError: If TAR creation fails.
    """
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    # Check directory is not empty
    files = [f for f in directory.rglob("*") if f.is_file()]
    if not files:
        raise ValueError(f"Directory is empty: {directory}")

    with tarfile.open(output_path, "w") as tar:
        for file_path in sorted(files):
            arcname = str(file_path.relative_to(directory))
            tar.add(str(file_path), arcname=arcname)

    return output_path


def calculate_directory_hash_and_files(directory: Path) -> Tuple[str, List[dict]]:
    """Calculates per-file SHA-256 hashes and an overall collection hash.

    The overall hash is computed as SHA-256 of the sorted concatenation
    of individual file hashes, ensuring deterministic results.

    Args:
        directory: Path to the directory to scan.

    Returns:
        Tuple of (overall_hash, file_info_list) where file_info_list
        contains dicts with 'path', 'size', and 'content_hash' keys.

    Raises:
        ValueError: If directory doesn't exist or is empty.
    """
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError(f"Not a directory: {directory}")

    files = sorted(f for f in directory.rglob("*") if f.is_file())
    if not files:
        raise ValueError(f"Directory is empty: {directory}")

    file_infos = []
    file_hashes = []

    for file_path in files:
        content = file_path.read_bytes()
        file_hash = hashlib.sha256(content).hexdigest()
        rel_path = str(file_path.relative_to(directory))

        file_infos.append({
            "path": rel_path,
            "size": len(content),
            "content_hash": file_hash,
        })
        file_hashes.append(file_hash)

    # Overall hash: SHA-256 of sorted concatenated file hashes
    overall_hash = hashlib.sha256("".join(sorted(file_hashes)).encode()).hexdigest()

    return overall_hash, file_infos
