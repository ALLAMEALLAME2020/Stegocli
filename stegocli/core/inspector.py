"""StegoCLI — Inspector: analyse a carrier's capacity and detect stego signatures."""
from __future__ import annotations
from pathlib import Path
from stegocli.core.models import InspectConfig, CapacityReport, ChannelSet, Strategy
from stegocli.carriers.image import load_carrier
from stegocli.strategies.lsb import available_bytes, extract_sequential
from stegocli.pipeline.header import Bootstrap, BOOTSTRAP_LEN
from stegocli.core.exceptions import NoSignatureError

BOOTSTRAP_PIXEL_SKIP = BOOTSTRAP_LEN * 8  # 344


def run_inspect(config: InspectConfig) -> CapacityReport:
    carrier = load_carrier(config.carrier_path)
    # Usable pixels for payload (after bootstrap region)
    ppc = max(0, carrier.pixel_count - BOOTSTRAP_PIXEL_SKIP)
    overhead = 200  # conservative header overhead estimate

    ultra    = max(0, available_bytes(ppc, ChannelSet.BLUE_ONLY,  1, Strategy.PRNG_SCATTER) - overhead)
    balanced = max(0, available_bytes(ppc, ChannelSet.BLUE_GREEN, 2, Strategy.PRNG_SCATTER) - overhead)
    maximum  = max(0, available_bytes(ppc, ChannelSet.RGB,        2, Strategy.ADAPTIVE)     - overhead)

    # Check for signature
    has_sig = False
    if carrier.pixel_count >= BOOTSTRAP_PIXEL_SKIP:
        try:
            raw = extract_sequential(
                carrier.pixels[:BOOTSTRAP_PIXEL_SKIP],
                bit_count=BOOTSTRAP_LEN * 8,
                channels=ChannelSet.BLUE_ONLY, max_lsb=1,
            )
            Bootstrap.unpack(raw)
            has_sig = True
        except Exception:
            pass

    return CapacityReport(
        pixel_count=carrier.pixel_count,
        channel_count=carrier.channels,
        ultra_stealth_bytes=ultra,
        balanced_bytes=balanced,
        maximum_bytes=maximum,
        has_signature=has_sig,
        width=carrier.width, height=carrier.height,
        format_name=carrier.format_name,
        color_mode=carrier.mode,
    )
