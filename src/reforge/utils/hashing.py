"""Content hashing for cache keys and reproducibility provenance."""

from __future__ import annotations

import hashlib
from pathlib import Path


def hash_bytes(data: bytes) -> str:
    """Return the hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    """Return the hex SHA-256 of ``text`` (UTF-8)."""
    return hash_bytes(text.encode("utf-8"))


def hash_file(path: Path) -> str:
    """Return the hex SHA-256 of a file's contents, streamed in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def short(digest: str, length: int = 12) -> str:
    """Truncate a hex digest for use in image tags and run ids."""
    return digest[:length]
