"""
StegoCLI — Bit-level embedding strategies.

Three strategies:
1. SEQUENTIAL  — raster order, 1 or 2 LSBs, fast, statistically detectable
2. ADAPTIVE    — position-based LSB depth: even pixels get max_lsb, odd get 1
                 NOTE: texture detection is position-based (not pixel-value-based)
                 so embed/extract decisions are always identical.
3. PRNG_SCATTER — Fisher-Yates shuffled pixel-channel indices from seed
"""
from __future__ import annotations
import random
from stegocli.core.exceptions import CapacityError, StrategyError
from stegocli.core.models import ChannelSet, Strategy

CHANNEL_INDICES: dict[ChannelSet, list[int]] = {
    ChannelSet.BLUE_ONLY:  [2],
    ChannelSet.BLUE_GREEN: [2, 1],
    ChannelSet.RGB:        [2, 1, 0],
}

# ── Capacity ───────────────────────────────────────────────────────────────────
def available_bits(pixel_count, channels, max_lsb, strategy, **_) -> int:
    ch = len(CHANNEL_INDICES[channels])
    slots = pixel_count * ch
    if strategy == Strategy.ADAPTIVE and max_lsb > 1:
        # Half pixels use max_lsb, half use 1 (position-based split)
        return (slots // 2) * max_lsb + (slots - slots // 2) * 1
    return slots * 1

def available_bytes(pixel_count, channels, max_lsb, strategy) -> int:
    return available_bits(pixel_count, channels, max_lsb, strategy) // 8

# ── Bit helpers ────────────────────────────────────────────────────────────────
def bytes_to_bits(data: bytes) -> list[int]:
    bits = []
    for b in data:
        for i in range(7,-1,-1):
            bits.append((b >> i) & 1)
    return bits

def bits_to_bytes(bits: list[int]) -> bytes:
    if len(bits) % 8:
        bits = bits + [0] * (8 - len(bits) % 8)
    out = bytearray()
    for i in range(0, len(bits), 8):
        v = 0
        for j in range(8): v = (v << 1) | bits[i+j]
        out.append(v)
    return bytes(out)

# ── Sequential ─────────────────────────────────────────────────────────────────
def embed_sequential(pixels, data, channels, max_lsb=1):
    ch = CHANNEL_INDICES[channels]
    bits = bytes_to_bits(data); total = len(bits); i = 0
    pixels = [list(p) for p in pixels]
    for px in pixels:
        if i >= total: break
        for c in ch:
            if c >= len(px) or i >= total: break
            for bp in range(max_lsb-1, -1, -1):
                if i >= total: break
                px[c] = (px[c] & ~(1 << bp)) | (bits[i] << bp); i += 1
    if i < total:
        raise CapacityError(f"Sequential: needed {total} bits, wrote {i}")
    return pixels

def extract_sequential(pixels, bit_count, channels, max_lsb=1):
    ch = CHANNEL_INDICES[channels]; bits = []
    for px in pixels:
        if len(bits) >= bit_count: break
        for c in ch:
            if c >= len(px) or len(bits) >= bit_count: break
            for bp in range(max_lsb-1, -1, -1):
                if len(bits) >= bit_count: break
                bits.append((px[c] >> bp) & 1)
    return bits_to_bytes(bits[:bit_count])

# ── Adaptive (position-based — deterministic at embed AND extract) ─────────────
def _adaptive_depth(pixel_idx: int, max_lsb: int) -> int:
    """Deterministic texture decision: every other pixel gets max_lsb."""
    return max_lsb if (pixel_idx % 2 == 0 and max_lsb > 1) else 1

def embed_adaptive(pixels, data, channels, max_lsb=2, width=0):
    ch = CHANNEL_INDICES[channels]
    bits = bytes_to_bits(data); total = len(bits); i = 0
    pixels = [list(p) for p in pixels]
    for idx, px in enumerate(pixels):
        if i >= total: break
        depth = _adaptive_depth(idx, max_lsb)
        for c in ch:
            if c >= len(px) or i >= total: break
            for bp in range(depth-1, -1, -1):
                if i >= total: break
                px[c] = (px[c] & ~(1 << bp)) | (bits[i] << bp); i += 1
    if i < total:
        raise CapacityError(f"Adaptive: needed {total} bits, wrote {i}")
    return pixels

def extract_adaptive(pixels, bit_count, channels, max_lsb=2, width=0):
    ch = CHANNEL_INDICES[channels]; bits = []
    for idx, px in enumerate(pixels):
        if len(bits) >= bit_count: break
        depth = _adaptive_depth(idx, max_lsb)
        for c in ch:
            if c >= len(px) or len(bits) >= bit_count: break
            for bp in range(depth-1, -1, -1):
                if len(bits) >= bit_count: break
                bits.append((px[c] >> bp) & 1)
    return bits_to_bytes(bits[:bit_count])

# ── PRNG scatter ───────────────────────────────────────────────────────────────
def _scatter_slots(pixel_count, channels, seed):
    ch = CHANNEL_INDICES[channels]
    slots = [(pi, c) for pi in range(pixel_count) for c in ch]
    random.Random(seed).shuffle(slots)
    return slots

def embed_prng_scatter(pixels, data, channels, seed, max_lsb=1):
    bits = bytes_to_bits(data); total = len(bits)
    slots = _scatter_slots(len(pixels), channels, seed)
    if len(slots) < total:
        raise CapacityError(f"Scatter: {len(slots)} slots for {total} bits")
    pixels = [list(p) for p in pixels]
    for i, (pi, c) in enumerate(slots):
        if i >= total: break
        px = pixels[pi]
        if c < len(px):
            px[c] = (px[c] & 0xFE) | bits[i]
    return pixels

def extract_prng_scatter(pixels, bit_count, channels, seed, max_lsb=1):
    slots = _scatter_slots(len(pixels), channels, seed); bits = []
    for pi, c in slots:
        if len(bits) >= bit_count: break
        if c < len(pixels[pi]):
            bits.append(pixels[pi][c] & 1)
    return bits_to_bytes(bits[:bit_count])

# ── Unified dispatch ───────────────────────────────────────────────────────────
def embed(pixels, data, strategy, channels, max_lsb, seed=0, width=0):
    if strategy == Strategy.SEQUENTIAL:
        return embed_sequential(pixels, data, channels, max_lsb)
    elif strategy == Strategy.ADAPTIVE:
        return embed_adaptive(pixels, data, channels, max_lsb, width)
    elif strategy == Strategy.PRNG_SCATTER:
        return embed_prng_scatter(pixels, data, channels, seed, max_lsb)
    raise StrategyError(f"Unknown strategy: {strategy}")

def extract(pixels, byte_count, strategy, channels, max_lsb, seed=0, width=0):
    bit_count = byte_count * 8
    if strategy == Strategy.SEQUENTIAL:
        return extract_sequential(pixels, bit_count, channels, max_lsb)
    elif strategy == Strategy.ADAPTIVE:
        return extract_adaptive(pixels, bit_count, channels, max_lsb, width)
    elif strategy == Strategy.PRNG_SCATTER:
        return extract_prng_scatter(pixels, bit_count, channels, seed)
    raise StrategyError(f"Unknown strategy: {strategy}")
