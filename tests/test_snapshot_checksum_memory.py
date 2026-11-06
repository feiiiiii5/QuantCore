"""Large snapshot checksums must not allocate an extra complete file in memory."""

from __future__ import annotations

import hashlib
import tracemalloc

from quantcore.snapshot.checksums import sha256_file


def test_real_16_mib_file_hash_is_exact_with_bounded_memory(tmp_path):
    path = tmp_path / "generated-panel.qpanel"
    block = bytes(range(256)) * 4096  # One MiB; file creation is outside measurement.
    expected = hashlib.sha256()
    with path.open("wb") as handle:
        for _ in range(16):
            handle.write(block)
            expected.update(block)
    assert path.stat().st_size == 16 * 1024**2
    tracemalloc.start()
    try:
        actual = sha256_file(path)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert actual == expected.hexdigest()
    assert peak < 2 * 1024**2, f"checksum allocated {peak} bytes for a 16 MiB file"
