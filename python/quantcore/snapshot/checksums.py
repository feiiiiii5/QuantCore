"""File checksum support shared by snapshot construction and verification."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    """Return a SHA-256 digest with memory independent of the file's size."""
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()
