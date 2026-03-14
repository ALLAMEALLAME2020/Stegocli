"""StegoCLI — Verifier: checks stego signature without full extraction."""
from __future__ import annotations
from stegocli.core.models import VerifyConfig, VerifyResult, ChannelSet
from stegocli.carriers.image import load_carrier
from stegocli.pipeline.header import Bootstrap, BOOTSTRAP_LEN
from stegocli.strategies.lsb import extract_sequential
from stegocli.core.exceptions import NoSignatureError, AuthenticationError

BOOTSTRAP_PIXEL_SKIP = BOOTSTRAP_LEN * 8


def run_verify(config: VerifyConfig) -> VerifyResult:
    carrier = load_carrier(config.carrier_path)

    if carrier.pixel_count < BOOTSTRAP_PIXEL_SKIP:
        return VerifyResult(success=False, has_signature=False, header_intact=False,
            payload_authenticated=False, payload_hash_stored="", filename="",
            original_size=0, was_compressed=False, was_encrypted=False,
            message="Carrier too small to contain a StegoCLI payload.")

    bootstrap_raw = extract_sequential(
        carrier.pixels[:BOOTSTRAP_PIXEL_SKIP],
        bit_count=BOOTSTRAP_LEN * 8,
        channels=ChannelSet.BLUE_ONLY, max_lsb=1,
    )
    try:
        bootstrap = Bootstrap.unpack(bootstrap_raw)
    except NoSignatureError:
        return VerifyResult(success=False, has_signature=False, header_intact=False,
            payload_authenticated=False, payload_hash_stored="", filename="",
            original_size=0, was_compressed=False, was_encrypted=False,
            message="No StegoCLI signature found in this carrier.")
    except Exception as exc:
        return VerifyResult(success=False, has_signature=True, header_intact=False,
            payload_authenticated=False, payload_hash_stored="", filename="",
            original_size=0, was_compressed=False, was_encrypted=False,
            message=f"Bootstrap header found but malformed: {exc}")

    # Try full authentication if password given
    payload_authenticated = False; filename = ""; original_size = 0; phash = ""
    if config.password or not bootstrap.encrypted:
        try:
            import tempfile; from pathlib import Path
            from stegocli.core.extractor import run_extract
            from stegocli.core.models import ExtractConfig, EmbedMode
            with tempfile.TemporaryDirectory() as td:
                ec = ExtractConfig(carrier_path=config.carrier_path,
                    output_dir=Path(td), password=config.password, verify=True)
                r = run_extract(ec)
                payload_authenticated = r.integrity_ok
                filename = r.filename; original_size = r.original_size
                phash = r.payload_hash_stored
        except (AuthenticationError, Exception):
            payload_authenticated = False

    return VerifyResult(
        success=True, has_signature=True, header_intact=True,
        payload_authenticated=payload_authenticated,
        payload_hash_stored=phash, filename=filename, original_size=original_size,
        was_compressed=bootstrap.compressed, was_encrypted=bootstrap.encrypted,
        message="Carrier verified — signature present and header intact."
                if payload_authenticated else
                "Signature found. Provide --password to authenticate payload.",
    )
