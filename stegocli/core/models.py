"""
StegoCLI — Typed dataclasses for all operation inputs, outputs, and reports.
No business logic lives here — pure data containers.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────

class EmbedMode(Enum):
    ULTRA_STEALTH = "ultra-stealth"
    BALANCED = "balanced"
    MAXIMUM = "maximum"
    CUSTOM = "custom"


class ChannelSet(Enum):
    BLUE_ONLY = "b"
    BLUE_GREEN = "bg"
    RGB = "rgb"


class Strategy(Enum):
    SEQUENTIAL = "sequential"
    ADAPTIVE = "adaptive"
    PRNG_SCATTER = "prng-scatter"


# ──────────────────────────────────────────────
# Mode presets
# ──────────────────────────────────────────────

MODE_PRESETS: dict[EmbedMode, dict] = {
    EmbedMode.ULTRA_STEALTH: {
        "strategy": Strategy.PRNG_SCATTER,
        "max_lsb_depth": 1,
        "channels": ChannelSet.BLUE_ONLY,
        "description": "Maximum stealth. PRNG scatter, 1 LSB blue only. ~12% capacity.",
    },
    EmbedMode.BALANCED: {
        "strategy": Strategy.PRNG_SCATTER,
        "max_lsb_depth": 2,
        "channels": ChannelSet.BLUE_GREEN,
        "description": "Balanced stealth/capacity. Adaptive LSB, PRNG scatter, B+G. ~25% capacity.",
    },
    EmbedMode.MAXIMUM: {
        "strategy": Strategy.ADAPTIVE,
        "max_lsb_depth": 2,
        "channels": ChannelSet.RGB,
        "description": "Maximum capacity. Adaptive 2-bit RGB. ~75% capacity.",
    },
}


# ──────────────────────────────────────────────
# Request / config objects
# ──────────────────────────────────────────────

@dataclass
class EmbedConfig:
    carrier_path: Path
    payload_path: Path
    output_path: Path
    mode: EmbedMode = EmbedMode.BALANCED
    password: Optional[str] = None
    encrypt: bool = True
    compress: bool = True
    dry_run: bool = False
    overwrite: bool = False
    # Advanced overrides (CUSTOM mode)
    strategy: Optional[Strategy] = None
    channels: Optional[ChannelSet] = None
    max_lsb_depth: int = 1
    verbose: bool = False
    quiet: bool = False


@dataclass
class ExtractConfig:
    carrier_path: Path
    output_dir: Path
    password: Optional[str] = None
    output_name_override: Optional[str] = None
    verify: bool = True
    verbose: bool = False
    quiet: bool = False


@dataclass
class InspectConfig:
    carrier_path: Path
    verbose: bool = False


@dataclass
class VerifyConfig:
    carrier_path: Path
    password: Optional[str] = None
    verbose: bool = False


# ──────────────────────────────────────────────
# Result / report objects
# ──────────────────────────────────────────────

@dataclass
class CapacityReport:
    pixel_count: int
    channel_count: int
    ultra_stealth_bytes: int
    balanced_bytes: int
    maximum_bytes: int
    has_signature: bool
    width: int
    height: int
    format_name: str
    color_mode: str


@dataclass
class EmbedResult:
    success: bool
    output_path: Optional[Path]
    payload_size_original: int
    payload_size_compressed: int
    payload_hash: str           # hex BLAKE2b of original
    carrier: str
    mode: str
    strategy_used: str
    channels_used: str
    bits_written: int
    capacity_used_pct: float
    elapsed_seconds: float
    dry_run: bool
    message: str = ""


@dataclass
class ExtractResult:
    success: bool
    output_path: Optional[Path]
    filename: str
    original_size: int
    payload_hash_stored: str    # from header
    payload_hash_computed: str  # from extracted bytes
    integrity_ok: bool
    was_compressed: bool
    was_encrypted: bool
    elapsed_seconds: float
    message: str = ""


@dataclass
class VerifyResult:
    success: bool
    has_signature: bool
    header_intact: bool
    payload_authenticated: bool   # GCM tag verified (needs password)
    payload_hash_stored: str
    filename: str
    original_size: int
    was_compressed: bool
    was_encrypted: bool
    message: str = ""

# Channel index map — mirrors strategies/lsb.py but imported by embedder
CHANNEL_INDICES: dict = {
    ChannelSet.BLUE_ONLY:  [2],
    ChannelSet.BLUE_GREEN: [2, 1],
    ChannelSet.RGB:        [2, 1, 0],
}
