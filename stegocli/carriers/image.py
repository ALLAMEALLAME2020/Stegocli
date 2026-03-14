"""
StegoCLI — Carrier image I/O.

Supported formats: PNG, BMP.
All writes are atomic: temp file → verify → rename.

Key constraint: images must be written as LOSSLESS pixel data.
PNG is re-encoded with PIL using no palette optimisation and
maximum compression for the image format (not the stego payload).
BMP is always lossless.

Alpha channels are preserved but not used for embedding (too suspicious).
"""
from __future__ import annotations
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image

from stegocli.core.exceptions import (
    CarrierError, UnsupportedFormatError, AtomicWriteError
)


SUPPORTED_FORMATS = {".png", ".bmp"}


# ── Format validation ──────────────────────────────────────────────────────────

def validate_carrier(path: Path) -> None:
    """Raise CarrierError / UnsupportedFormatError if carrier is not usable."""
    if not path.exists():
        raise CarrierError(f"Carrier file not found: {path}")
    if not path.is_file():
        raise CarrierError(f"Carrier path is not a file: {path}")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise UnsupportedFormatError(
            f"Unsupported carrier format: '{suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_FORMATS))}",
            hint="Convert your image to PNG or BMP before embedding.",
        )
    # Attempt to open to verify it's a real image
    try:
        with Image.open(path) as img:
            img.verify()
    except Exception as exc:
        raise CarrierError(
            f"Cannot open carrier image '{path.name}': {exc}",
            hint="The file may be corrupted or not a valid image.",
        )


def get_format(path: Path) -> str:
    """Return uppercase format name: 'PNG' or 'BMP'."""
    return path.suffix.upper().lstrip(".")


# ── Pixel read ─────────────────────────────────────────────────────────────────

class CarrierImage:
    """
    Wraps a loaded carrier image with its pixel data.

    Pixels are stored as a flat list of channel lists, e.g.:
      [[R,G,B], [R,G,B], ...]  for RGB
      [[R,G,B,A], ...]          for RGBA

    This is intentionally memory-inefficient for clarity and correctness.
    For very large images (>50 MP) consider bytearray optimisation.
    """

    def __init__(self, path: Path):
        self.path = path
        self._img: Optional[Image.Image] = None
        self.width: int = 0
        self.height: int = 0
        self.mode: str = ""
        self.format_name: str = ""
        self.channels: int = 0
        self.pixels: list = []

    def load(self) -> "CarrierImage":
        """Load image and extract pixel data."""
        try:
            img = Image.open(self.path)
            img.load()
        except Exception as exc:
            raise CarrierError(f"Failed to load '{self.path.name}': {exc}")

        # Convert palette images to RGB/RGBA for consistent channel access
        if img.mode == "P":
            img = img.convert("RGBA" if img.info.get("transparency") is not None else "RGB")
        elif img.mode == "L":
            img = img.convert("RGB")
        elif img.mode == "LA":
            img = img.convert("RGBA")

        self._img = img
        self.width = img.width
        self.height = img.height
        self.mode = img.mode
        self.format_name = get_format(self.path)
        self.channels = len(img.mode)    # 3 for RGB, 4 for RGBA

        # Extract pixels as flat list of lists
        raw = list(img.getdata())
        # PIL returns tuples; convert to mutable lists
        if isinstance(raw[0], int):
            # Grayscale-like — shouldn't happen after conversion, but be safe
            self.pixels = [[v, v, v] for v in raw]
        else:
            self.pixels = [list(px) for px in raw]

        return self

    @property
    def pixel_count(self) -> int:
        return self.width * self.height

    def save(self, output_path: Path) -> None:
        """
        Write modified pixels back to a new image file atomically.

        Steps:
          1. Reconstruct PIL image from self.pixels
          2. Write to temp file in same directory
          3. Verify temp file is readable
          4. Rename to output_path (atomic on most OSes)
        """
        if self._img is None:
            raise CarrierError("No image loaded — cannot save.")

        # Rebuild the image from modified pixel data
        flat_pixels = [tuple(p) for p in self.pixels]
        new_img = Image.new(self.mode, (self.width, self.height))
        new_img.putdata(flat_pixels)

        # Choose output format
        out_suffix = output_path.suffix.lower()
        if out_suffix == ".png":
            save_kwargs = {"format": "PNG", "compress_level": 9, "optimize": False}
        elif out_suffix == ".bmp":
            save_kwargs = {"format": "BMP"}
        else:
            raise UnsupportedFormatError(f"Cannot save to format: {out_suffix}")

        # Atomic write: temp → verify → rename
        parent = output_path.parent
        parent.mkdir(parents=True, exist_ok=True)

        tmp_path = None
        try:
            fd, tmp_str = tempfile.mkstemp(
                suffix=".stgtmp", dir=parent, prefix=".stegocli_"
            )
            os.close(fd)
            tmp_path = Path(tmp_str)

            new_img.save(tmp_path, **save_kwargs)

            # Verify the temp file is readable and has pixels
            with Image.open(tmp_path) as verify_img:
                verify_img.load()
                if verify_img.size != (self.width, self.height):
                    raise AtomicWriteError(
                        "Output image dimensions don't match original — aborting."
                    )

            # Atomic rename
            shutil.move(str(tmp_path), str(output_path))
            tmp_path = None  # moved, don't clean up

        except AtomicWriteError:
            raise
        except Exception as exc:
            raise AtomicWriteError(
                f"Failed to write output carrier: {exc}",
                hint="Check available disk space and write permissions.",
            ) from exc
        finally:
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass


# ── Convenience functions ──────────────────────────────────────────────────────

def load_carrier(path: Path) -> CarrierImage:
    """Validate and load a carrier image."""
    validate_carrier(path)
    return CarrierImage(path).load()


def capacity_bytes(carrier: CarrierImage, ch_count: int, lsb_bits: int = 1) -> int:
    """
    Simple capacity calculation: (pixels × channels × lsb_bits) / 8
    """
    return (carrier.pixel_count * ch_count * lsb_bits) // 8
