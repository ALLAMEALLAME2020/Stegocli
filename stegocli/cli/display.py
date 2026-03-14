"""
StegoCLI — Rich terminal output using only stdlib (no rich/typer available).
Produces clean, aligned tables and coloured output via ANSI escape codes.
Auto-detects whether the terminal supports colour.
"""
from __future__ import annotations
import os, sys, textwrap
from pathlib import Path


# ── ANSI colours ───────────────────────────────────────────────────────────────
def _supports_color() -> bool:
    if os.environ.get("NO_COLOR") or os.environ.get("STEGOCLI_NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()

_COLOR = _supports_color()

def _c(code: str, text: str) -> str:
    if not _COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

def green(t):  return _c("32", t)
def red(t):    return _c("31", t)
def yellow(t): return _c("33", t)
def cyan(t):   return _c("36", t)
def bold(t):   return _c("1",  t)
def dim(t):    return _c("2",  t)
def blue(t):   return _c("34", t)


# ── Progress bar ───────────────────────────────────────────────────────────────
def progress_bar(label: str, pct: float, width: int = 30) -> str:
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return f"{label:<22} [{bar}] {pct:5.1f}%"


# ── Section header ─────────────────────────────────────────────────────────────
def section(title: str) -> None:
    line = "─" * 60
    print(f"\n{bold(title)}")
    print(dim(line))


def print_kv(key: str, value: str, width: int = 24) -> None:
    print(f"  {dim(key + ':'):<{width+1}} {value}")


def fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"


# ── Specific formatters ────────────────────────────────────────────────────────

def print_banner() -> None:
    banner = r"""
  ███████╗████████╗███████╗ ██████╗  ██████╗ ██████╗██╗     ██╗
  ██╔════╝╚══██╔══╝██╔════╝██╔════╝ ██╔═══██╗██╔════╝██║    ██║
  ███████╗   ██║   █████╗  ██║  ███╗██║   ██║██║     ██║    ██║
  ╚════██║   ██║   ██╔══╝  ██║   ██║██║   ██║██║     ██║    ██║
  ███████║   ██║   ███████╗╚██████╔╝╚██████╔╝╚██████╗███████╗██║
  ╚══════╝   ╚═╝   ╚══════╝ ╚═════╝  ╚═════╝  ╚═════╝╚══════╝╚═╝
    """
    print(cyan(banner))
    print(dim("  Secure steganography — hide files inside images\n"))


def print_embed_result(result) -> None:
    from stegocli.core.models import EmbedResult
    if result.dry_run:
        section("Dry Run Result")
        print(f"  {yellow('DRY RUN — no files written')}")
    else:
        section("Embed Complete")
        print(f"  {green('✓ Success')}")

    print_kv("Output",       str(result.output_path) if result.output_path else "—")
    print_kv("Carrier",      result.carrier)
    print_kv("Mode",         result.mode)
    print_kv("Strategy",     result.strategy_used)
    print_kv("Channels",     result.channels_used)
    print_kv("Original size",fmt_size(result.payload_size_original))
    if result.payload_size_compressed < result.payload_size_original:
        ratio = result.payload_size_original / max(result.payload_size_compressed, 1)
        print_kv("Compressed",  f"{fmt_size(result.payload_size_compressed)} ({ratio:.1f}× smaller)")
    print_kv("Payload hash", result.payload_hash[:16] + "…" + result.payload_hash[-8:])
    print_kv("Bits written", f"{result.bits_written:,}")
    print(f"\n  {progress_bar('Capacity used', result.capacity_used_pct)}")
    print(f"\n  {dim('Time:')} {result.elapsed_seconds:.2f}s")
    print()


def print_extract_result(result) -> None:
    section("Extract Complete")
    ok = green("✓ PASS") if result.integrity_ok else red("✗ FAIL")
    print(f"  {green('✓ Success')}   Integrity: {ok}")
    print_kv("Output file",  str(result.output_path))
    print_kv("Filename",     result.filename)
    print_kv("Original size",fmt_size(result.original_size))
    print_kv("Compressed",   green("yes") if result.was_compressed else "no")
    print_kv("Encrypted",    green("yes") if result.was_encrypted  else "no")
    print_kv("Hash (stored)",result.payload_hash_stored[:16] + "…")
    print_kv("Hash (actual)",result.payload_hash_computed[:16] + "…")
    print(f"\n  {dim('Time:')} {result.elapsed_seconds:.2f}s")
    print()


def print_inspect_result(result, carrier_path: Path) -> None:
    section(f"Carrier Analysis — {carrier_path.name}")
    print_kv("Format",       result.format_name)
    print_kv("Dimensions",   f"{result.width} × {result.height} px")
    print_kv("Color mode",   result.color_mode)
    print_kv("Pixel count",  f"{result.pixel_count:,}")
    print_kv("Channels",     str(result.channel_count))
    if result.has_signature:
        print_kv("Stego sig",    yellow("⚠ signature detected"))
    else:
        print_kv("Stego sig",    dim("none detected"))

    print(f"\n  {'Mode':<18} {'Capacity':<12} {'Description'}")
    print(f"  {dim('─'*60)}")
    rows = [
        ("ultra-stealth", result.ultra_stealth_bytes,
         "1-bit blue LSB, PRNG scatter"),
        ("balanced",      result.balanced_bytes,
         "1-2 bit adaptive, B+G, PRNG scatter"),
        ("maximum",       result.maximum_bytes,
         "2-bit adaptive RGB"),
    ]
    for name, cap, desc in rows:
        cap_s = fmt_size(cap) if cap > 0 else red("—")
        print(f"  {cyan(name):<27} {cap_s:<20} {dim(desc)}")
    print()


def print_verify_result(result, carrier_path: Path) -> None:
    section(f"Verify — {carrier_path.name}")
    if not result.has_signature:
        print(f"  {red('✗')} No StegoCLI signature detected.")
        return

    sig_s    = green("✓ present")    if result.has_signature     else red("✗ absent")
    hdr_s    = green("✓ intact")     if result.header_intact     else red("✗ malformed")
    auth_s   = green("✓ verified")   if result.payload_authenticated else dim("— (no password)")
    enc_s    = green("yes")          if result.was_encrypted     else "no"
    comp_s   = green("yes")          if result.was_compressed    else "no"

    print_kv("Signature",    sig_s)
    print_kv("Header",       hdr_s)
    print_kv("Payload auth", auth_s)
    print_kv("Encrypted",    enc_s)
    print_kv("Compressed",   comp_s)
    if result.filename:
        print_kv("Filename",     result.filename)
    if result.original_size:
        print_kv("Original size",fmt_size(result.original_size))
    print(f"\n  {dim(result.message)}")
    print()


def print_error(exc: Exception) -> None:
    msg = str(exc)
    lines = msg.split("\n")
    print(f"\n  {red('Error:')} {lines[0]}", file=sys.stderr)
    for line in lines[1:]:
        print(f"         {dim(line)}", file=sys.stderr)
    print(file=sys.stderr)


def prompt_password(confirm: bool = False) -> str:
    import getpass
    while True:
        pw = getpass.getpass("  Passphrase: ")
        if not pw:
            print(red("  Passphrase cannot be empty."), file=sys.stderr)
            continue
        if confirm:
            pw2 = getpass.getpass("  Confirm passphrase: ")
            if pw != pw2:
                print(red("  Passphrases do not match — try again."), file=sys.stderr)
                continue
        return pw
