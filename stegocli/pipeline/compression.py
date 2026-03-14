"""
StegoCLI — Payload compression.

Uses zlib (stdlib) with level 9. We test whether compression
actually reduces the payload size — if not (e.g. payload is already
a zip/jpeg/mp3), we skip it and record the decision in the header flag.

This prevents situations where compression *increases* the payload size
and wastes carrier capacity.
"""
from __future__ import annotations
import zlib

from stegocli.core.exceptions import PayloadError


ZLIB_LEVEL = 9          # Maximum compression
MIN_BENEFIT_BYTES = 8   # Only compress if we save at least this many bytes


def compress(data: bytes) -> tuple[bytes, bool]:
    """
    Attempt to compress *data*.

    Returns
    -------
    (result_bytes, was_compressed)
      was_compressed is True only if compression actually reduced the size.
    """
    try:
        compressed = zlib.compress(data, level=ZLIB_LEVEL)
    except zlib.error as exc:
        raise PayloadError(f"Compression failed: {exc}") from exc

    if len(compressed) + MIN_BENEFIT_BYTES < len(data):
        return compressed, True
    return data, False


def decompress(data: bytes) -> bytes:
    """
    Decompress zlib-compressed *data*.

    Raises PayloadError on decompression failure (e.g. corrupted data).
    """
    try:
        return zlib.decompress(data)
    except zlib.error as exc:
        raise PayloadError(
            f"Decompression failed — payload may be corrupted: {exc}",
            hint="If encryption was used, decryption happens before decompression. "
                 "A wrong password would have already raised an error.",
        ) from exc


def compression_ratio(original: bytes, compressed: bytes) -> float:
    """Return compression ratio as a float (< 1.0 = smaller)."""
    if not original:
        return 1.0
    return len(compressed) / len(original)
