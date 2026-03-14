"""
StegoCLI — Embedder.

Bootstrap layout (pixels 0..BOOTSTRAP_PIXEL_SKIP-1):
  43 bytes embedded sequentially in blue channel LSBs.
  BOOTSTRAP_PIXEL_SKIP = 43*8 = 344 pixels.

Payload portion (pixels BOOTSTRAP_PIXEL_SKIP+):
  Encrypted/plain inner block embedded using chosen strategy.
"""
from __future__ import annotations
import time
from pathlib import Path
from stegocli.core.exceptions import CapacityError, PayloadError, AtomicWriteError
from stegocli.core.models import (
    EmbedConfig, EmbedResult, EmbedMode, ChannelSet, Strategy,
    MODE_PRESETS, CHANNEL_INDICES,
)
from stegocli.carriers.image import load_carrier
from stegocli.pipeline.compression import compress
from stegocli.pipeline.crypto import (
    derive_key, generate_salt, generate_nonce, hash_payload, hash_payload_hex, derive_prng_seed,
)
from stegocli.pipeline.header import (
    Bootstrap, InnerBlock, pack_stream, BOOTSTRAP_LEN, VERSION, compute_stream_size,
)
from stegocli.strategies.lsb import (
    embed_sequential, embed_prng_scatter, embed_adaptive,
    extract_sequential, available_bytes,
)

BOOTSTRAP_PIXEL_SKIP = BOOTSTRAP_LEN * 8   # 43 * 8 = 344 pixels


def run_embed(config: EmbedConfig) -> EmbedResult:
    t0 = time.monotonic()

    # ── Resolve mode ──────────────────────────────────────────────────────
    if config.mode != EmbedMode.CUSTOM:
        preset   = MODE_PRESETS[config.mode]
        strategy = preset["strategy"]
        max_lsb  = preset["max_lsb_depth"]
        channels = preset["channels"]
    else:
        strategy = config.strategy or Strategy.PRNG_SCATTER
        max_lsb  = config.max_lsb_depth
        channels = config.channels or ChannelSet.BLUE_ONLY

    # ── Validate ──────────────────────────────────────────────────────────
    if not config.carrier_path.exists():
        raise PayloadError(f"Carrier not found: {config.carrier_path}")
    if not config.payload_path.exists():
        raise PayloadError(f"Payload not found: {config.payload_path}")
    if config.output_path.exists() and not config.overwrite:
        raise PayloadError(f"Output already exists: {config.output_path}",
                           hint="Use --overwrite to replace it.")

    # ── Load payload ──────────────────────────────────────────────────────
    payload_original    = config.payload_path.read_bytes()
    original_size       = len(payload_original)
    original_hash_bytes = hash_payload(payload_original)
    original_hash_hex   = original_hash_bytes.hex()
    filename            = config.payload_path.name

    # ── Load carrier ──────────────────────────────────────────────────────
    carrier = load_carrier(config.carrier_path)
    if carrier.pixel_count < BOOTSTRAP_PIXEL_SKIP + 64:
        raise CapacityError(f"Carrier too small ({carrier.pixel_count} px).")

    # ── Capacity check ────────────────────────────────────────────────────
    ppc      = carrier.pixel_count - BOOTSTRAP_PIXEL_SKIP
    pay_cap  = available_bytes(ppc, channels, max_lsb, strategy)
    do_enc   = config.encrypt and bool(config.password)
    overhead = compute_stream_size(filename, 0, do_enc)
    net_cap  = pay_cap - overhead

    if original_size > net_cap and not config.compress:
        raise CapacityError(
            f"Payload ({_sz(original_size)}) too large for '{config.mode.value}' "
            f"mode ({_sz(net_cap)} available).",
            hint="Try --compress, --mode maximum, or a larger carrier.",
        )

    # ── Compress ──────────────────────────────────────────────────────────
    payload_data, was_compressed = compress(payload_original) if config.compress else (payload_original, False)
    compressed_size = len(payload_data)

    est = compute_stream_size(filename, compressed_size, do_enc)
    if est > pay_cap:
        raise CapacityError(f"Payload too large even after compression ({_sz(est)} > {_sz(pay_cap)}).",
                            hint="Use a larger carrier or --mode maximum.")

    # ── Crypto ────────────────────────────────────────────────────────────
    if do_enc:
        salt = generate_salt(); nonce = generate_nonce()
        key  = derive_key(config.password, salt)
        prng_seed = derive_prng_seed(key)
        def _enc(pt, n, aad):
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            return AESGCM(key).encrypt(n, pt, aad)
    else:
        salt = b"\x00"*16; nonce = b"\x00"*12
        prng_seed = 0; _enc = None

    # ── Build stream ──────────────────────────────────────────────────────
    inner = InnerBlock(
        original_size=original_size,
        compressed_size=compressed_size,
        payload_hash=original_hash_bytes,
        filename=filename,
        payload_data=payload_data,
    )
    # Compute blob length before building bootstrap (needed for blob_length field)
    inner_bytes = inner.pack()
    if do_enc:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        # Compute actual blob size: encrypted = len(inner_bytes) + 16 (GCM tag)
        blob_length = len(inner_bytes) + 16
    else:
        blob_length = len(inner_bytes)

    bootstrap = Bootstrap(
        version=VERSION, compressed=was_compressed, encrypted=do_enc,
        kdf_n_log2=17 if do_enc else 0,
        kdf_salt=salt, nonce=nonce, blob_length=blob_length,
    )
    full_stream     = pack_stream(bootstrap, inner, encrypt_fn=_enc)
    bootstrap_bytes = full_stream[:BOOTSTRAP_LEN]
    payload_bytes   = full_stream[BOOTSTRAP_LEN:]
    assert len(payload_bytes) == blob_length, f"{len(payload_bytes)} != {blob_length}"

    total_bits = len(full_stream) * 8

    # ── Dry run ───────────────────────────────────────────────────────────
    if config.dry_run:
        elapsed = time.monotonic() - t0
        return EmbedResult(
            success=True, output_path=None,
            payload_size_original=original_size, payload_size_compressed=compressed_size,
            payload_hash=original_hash_hex, carrier=carrier.format_name,
            mode=config.mode.value, strategy_used=strategy.value, channels_used=channels.value,
            bits_written=total_bits, capacity_used_pct=len(full_stream)/max(pay_cap,1)*100,
            elapsed_seconds=elapsed, dry_run=True,
            message=f"Dry run OK — would embed {_sz(len(full_stream))} ({len(full_stream)/max(pay_cap,1)*100:.1f}%).",
        )

    # ── Embed ─────────────────────────────────────────────────────────────
    pixels = [list(p) for p in carrier.pixels]
    # Phase 1: bootstrap → sequential blue 1-bit, pixels 0..BOOTSTRAP_PIXEL_SKIP-1
    pixels = embed_sequential(pixels, bootstrap_bytes, ChannelSet.BLUE_ONLY, max_lsb=1)
    # Phase 2: payload → chosen strategy, pixels BOOTSTRAP_PIXEL_SKIP+
    head = pixels[:BOOTSTRAP_PIXEL_SKIP]
    tail = pixels[BOOTSTRAP_PIXEL_SKIP:]
    if strategy == Strategy.SEQUENTIAL:
        tail = embed_sequential(tail, payload_bytes, channels, max_lsb)
    elif strategy == Strategy.PRNG_SCATTER:
        tail = embed_prng_scatter(tail, payload_bytes, channels, prng_seed, max_lsb)
    elif strategy == Strategy.ADAPTIVE:
        tail = embed_adaptive(tail, payload_bytes, channels, max_lsb, carrier.width)
    pixels = head + tail
    carrier.pixels = pixels

    # ── Save ──────────────────────────────────────────────────────────────
    carrier.save(config.output_path)

    # ── Post-write verify ─────────────────────────────────────────────────
    from stegocli.carriers.image import CarrierImage
    v     = CarrierImage(config.output_path).load()
    check = extract_sequential(v.pixels[:BOOTSTRAP_PIXEL_SKIP],
                                bit_count=BOOTSTRAP_LEN*8, channels=ChannelSet.BLUE_ONLY, max_lsb=1)
    if check[:8] != bootstrap_bytes[:8]:
        config.output_path.unlink(missing_ok=True)
        raise AtomicWriteError("Post-write verification failed. Output deleted.")

    elapsed = time.monotonic() - t0
    return EmbedResult(
        success=True, output_path=config.output_path,
        payload_size_original=original_size, payload_size_compressed=compressed_size,
        payload_hash=original_hash_hex, carrier=carrier.format_name,
        mode=config.mode.value, strategy_used=strategy.value, channels_used=channels.value,
        bits_written=total_bits, capacity_used_pct=len(full_stream)/max(pay_cap,1)*100,
        elapsed_seconds=elapsed, dry_run=False, message="Embed successful.",
    )


def _sz(n):
    for u in ("B","KB","MB","GB"):
        if n < 1024: return f"{n:.1f} {u}" if u!="B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"
