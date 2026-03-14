"""
StegoCLI — Extractor.
Phase 1: extract bootstrap from pixels[0..343] (sequential blue 1-bit)
Phase 2: extract blob_length bytes from pixels[344+] using mode strategy
"""
from __future__ import annotations
import os, shutil, tempfile, time
from pathlib import Path
from stegocli.core.exceptions import AuthenticationError, IntegrityError, PayloadError, NoSignatureError
from stegocli.core.models import ExtractConfig, ExtractResult, EmbedMode, ChannelSet, Strategy, MODE_PRESETS
from stegocli.carriers.image import load_carrier
from stegocli.pipeline.compression import decompress
from stegocli.pipeline.crypto import hash_payload_hex, verify_hash, derive_prng_seed
from stegocli.pipeline.header import Bootstrap, InnerBlock, unpack_stream, BOOTSTRAP_LEN
from stegocli.strategies.lsb import extract_sequential, extract_prng_scatter, extract_adaptive, available_bytes

BOOTSTRAP_PIXEL_SKIP = BOOTSTRAP_LEN * 8   # 344


def run_extract(config: ExtractConfig, mode: EmbedMode = EmbedMode.BALANCED) -> ExtractResult:
    t0 = time.monotonic()

    # ── Resolve mode ──────────────────────────────────────────────────────
    if mode != EmbedMode.CUSTOM:
        preset   = MODE_PRESETS[mode]
        strategy = preset["strategy"]
        max_lsb  = preset["max_lsb_depth"]
        channels = preset["channels"]
    else:
        strategy = Strategy.PRNG_SCATTER; max_lsb = 1; channels = ChannelSet.BLUE_ONLY

    # ── Load carrier ──────────────────────────────────────────────────────
    carrier = load_carrier(config.carrier_path)

    # ── Phase 1: bootstrap from pixels 0..343 ────────────────────────────
    bootstrap_raw = extract_sequential(
        carrier.pixels[:BOOTSTRAP_PIXEL_SKIP],
        bit_count=BOOTSTRAP_LEN * 8,
        channels=ChannelSet.BLUE_ONLY, max_lsb=1,
    )
    bootstrap = Bootstrap.unpack(bootstrap_raw)

    # ── Derive key ────────────────────────────────────────────────────────
    if bootstrap.encrypted:
        if not config.password:
            raise AuthenticationError("This carrier is encrypted — provide --password.")
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        from cryptography.hazmat.backends import default_backend
        kdf = Scrypt(salt=bootstrap.kdf_salt, length=32,
                     n=1<<bootstrap.kdf_n_log2, r=8, p=1, backend=default_backend())
        key = kdf.derive(config.password.encode())
        prng_seed = derive_prng_seed(key)
    else:
        key = None; prng_seed = 0

    # ── Phase 2: extract exact blob_length bytes from pixels 344+ ────────
    blob_length  = bootstrap.blob_length
    pixels_tail  = carrier.pixels[BOOTSTRAP_PIXEL_SKIP:]

    if strategy == Strategy.SEQUENTIAL:
        blob = extract_sequential(pixels_tail, bit_count=blob_length*8,
                                   channels=channels, max_lsb=max_lsb)
    elif strategy == Strategy.PRNG_SCATTER:
        blob = extract_prng_scatter(pixels_tail, bit_count=blob_length*8,
                                     channels=channels, seed=prng_seed)
    elif strategy == Strategy.ADAPTIVE:
        blob = extract_adaptive(pixels_tail, bit_count=blob_length*8,
                                 channels=channels, max_lsb=max_lsb, width=carrier.width)
    else:
        blob = extract_sequential(pixels_tail, bit_count=blob_length*8,
                                   channels=channels, max_lsb=max_lsb)

    # ── Decrypt + unpack ──────────────────────────────────────────────────
    full_stream = bootstrap_raw + blob

    def _dec(ct, nonce, aad):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        try:
            return AESGCM(key).decrypt(nonce, ct, aad)
        except Exception:
            raise AuthenticationError(
                "Decryption failed — incorrect password or tampered carrier.",
                hint="Ensure you use the exact passphrase from embedding.",
            )

    _, inner = unpack_stream(full_stream, decrypt_fn=_dec if bootstrap.encrypted else None)

    # ── Decompress ────────────────────────────────────────────────────────
    payload_raw = decompress(inner.payload_data) if bootstrap.compressed else inner.payload_data

    # ── Integrity check ───────────────────────────────────────────────────
    if config.verify:
        ok = verify_hash(payload_raw, inner.payload_hash)
        if not ok:
            raise IntegrityError("Payload integrity check failed — BLAKE2b mismatch.",
                                  hint="The carrier may have been altered after embedding.")
    else:
        ok = True

    # ── Write output ──────────────────────────────────────────────────────
    out_name = config.output_name_override or inner.filename or "extracted_payload"
    out_path = config.output_dir / out_name
    config.output_dir.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        fd, ts = tempfile.mkstemp(dir=config.output_dir, prefix=".stegocli_")
        os.close(fd); tmp = Path(ts); tmp.write_bytes(payload_raw)
        shutil.move(str(tmp), str(out_path)); tmp = None
    except Exception as exc:
        raise PayloadError(f"Failed to write output: {exc}") from exc
    finally:
        if tmp and tmp.exists():
            try: tmp.unlink()
            except OSError: pass

    elapsed = time.monotonic() - t0
    return ExtractResult(
        success=True, output_path=out_path, filename=out_name,
        original_size=inner.original_size,
        payload_hash_stored=inner.payload_hash.hex(),
        payload_hash_computed=hash_payload_hex(payload_raw),
        integrity_ok=ok, was_compressed=bootstrap.compressed,
        was_encrypted=bootstrap.encrypted, elapsed_seconds=elapsed,
        message="Extraction successful.",
    )
