"""
StegoCLI — Main CLI entry point.

Commands:
  stegocli embed    CARRIER PAYLOAD OUTPUT  [options]
  stegocli extract  STEGO_CARRIER           [options]
  stegocli inspect  CARRIER
  stegocli verify   STEGO_CARRIER           [options]
  stegocli benchmark CARRIER
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

from stegocli import __version__
from stegocli.cli.display import (
    print_banner, print_embed_result, print_extract_result,
    print_inspect_result, print_verify_result,
    print_error, prompt_password, section, print_kv, fmt_size, cyan, bold, dim, green, red, yellow,
)
from stegocli.core.exceptions import StegoCLIError
from stegocli.core.models import (
    EmbedConfig, ExtractConfig, InspectConfig, VerifyConfig,
    EmbedMode, ChannelSet, Strategy,
)


# ── Argument parser construction ───────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stegocli",
        description="StegoCLI — Secure steganography: hide files inside images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap_dedent("""
Examples:
  # Embed a PDF into a PNG with balanced stealth (prompts for password)
  stegocli embed photo.png secret.pdf output.png

  # Embed with explicit mode and password file
  stegocli embed photo.png secret.pdf output.png --mode ultra-stealth --password-file pw.txt

  # Embed without encryption (still hashes for integrity)
  stegocli embed photo.png data.json output.png --no-encrypt

  # Extract payload (prompts for password)
  stegocli extract output.png --output-dir ./recovered/

  # Inspect carrier capacity before embedding
  stegocli inspect photo.png

  # Verify a stego carrier (checks signature and header only)
  stegocli verify output.png

  # Verify and authenticate payload with password
  stegocli verify output.png --password-file pw.txt

  # Dry run — analyse without writing
  stegocli embed photo.png secret.pdf output.png --dry-run
        """),
    )
    parser.add_argument("--version", action="version",
                        version=f"StegoCLI {__version__}")

    subs = parser.add_subparsers(dest="command", metavar="COMMAND")
    subs.required = True

    # ── embed ──────────────────────────────────────────────────────────────────
    p_embed = subs.add_parser(
        "embed",
        help="Hide a payload file inside a carrier image.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Embed a file inside a carrier PNG or BMP image.",
    )
    p_embed.add_argument("carrier",  type=Path, metavar="CARRIER",
                         help="Carrier image (PNG or BMP).")
    p_embed.add_argument("payload",  type=Path, metavar="PAYLOAD",
                         help="File to hide (any type).")
    p_embed.add_argument("output",   type=Path, metavar="OUTPUT",
                         help="Output stego image path.")
    p_embed.add_argument("--mode", choices=["ultra-stealth","balanced","maximum","custom"],
                         default="balanced",
                         help="Embedding mode preset (default: balanced).")
    p_embed.add_argument("--password",     metavar="PASS",
                         help="Encryption passphrase (prompted if omitted and --no-encrypt not set).")
    p_embed.add_argument("--password-file", metavar="FILE", type=Path,
                         help="Read passphrase from file (first line).")
    p_embed.add_argument("--no-encrypt",   action="store_true",
                         help="Skip encryption (payload is still integrity-hashed).")
    p_embed.add_argument("--no-compress",  action="store_true",
                         help="Skip compression.")
    p_embed.add_argument("--channels",     choices=["b","bg","rgb"],
                         help="Override channel selection (custom mode only).")
    p_embed.add_argument("--strategy",     choices=["sequential","adaptive","prng-scatter"],
                         help="Override embedding strategy (custom mode only).")
    p_embed.add_argument("--max-lsb",      type=int, choices=[1, 2], default=1,
                         help="Max LSB depth override (custom mode only).")
    p_embed.add_argument("--dry-run",      action="store_true",
                         help="Analyse and simulate without writing output.")
    p_embed.add_argument("--overwrite",    action="store_true",
                         help="Allow overwriting an existing output file.")
    p_embed.add_argument("--quiet",        action="store_true",
                         help="Suppress all output except errors.")
    p_embed.add_argument("--verbose",      action="store_true",
                         help="Print full audit trail.")

    # ── extract ────────────────────────────────────────────────────────────────
    p_ext = subs.add_parser(
        "extract",
        help="Recover a hidden payload from a stego carrier.",
        description="Extract and decrypt the payload hidden in a stego image.",
    )
    p_ext.add_argument("carrier",     type=Path, metavar="CARRIER",
                       help="Stego carrier image to extract from.")
    p_ext.add_argument("--mode",      choices=["ultra-stealth","balanced","maximum","custom"],
                       default="balanced",
                       help="Mode used during embedding (must match, default: balanced).")
    p_ext.add_argument("--password",  metavar="PASS",
                       help="Decryption passphrase.")
    p_ext.add_argument("--password-file", metavar="FILE", type=Path,
                       help="Read passphrase from file.")
    p_ext.add_argument("--output-dir", type=Path, default=Path("."),
                       metavar="DIR", help="Directory to write extracted file (default: current dir).")
    p_ext.add_argument("--output-name", metavar="NAME",
                       help="Override filename for extracted file.")
    p_ext.add_argument("--no-verify",  action="store_true",
                       help="Skip integrity hash verification after extraction.")
    p_ext.add_argument("--quiet",      action="store_true")
    p_ext.add_argument("--verbose",    action="store_true")

    # ── inspect ────────────────────────────────────────────────────────────────
    p_ins = subs.add_parser(
        "inspect",
        help="Analyse a carrier's steganographic capacity.",
        description="Show capacity for all modes and detect existing signatures.",
    )
    p_ins.add_argument("carrier", type=Path, metavar="CARRIER")
    p_ins.add_argument("--verbose", action="store_true")

    # ── verify ─────────────────────────────────────────────────────────────────
    p_ver = subs.add_parser(
        "verify",
        help="Verify a stego carrier's signature and integrity.",
        description="Check signature, header integrity, and (with --password) payload authentication.",
    )
    p_ver.add_argument("carrier",      type=Path, metavar="CARRIER")
    p_ver.add_argument("--password",   metavar="PASS")
    p_ver.add_argument("--password-file", metavar="FILE", type=Path)
    p_ver.add_argument("--verbose",    action="store_true")

    # ── benchmark ──────────────────────────────────────────────────────────────
    p_bench = subs.add_parser(
        "benchmark",
        help="Benchmark embedding and extraction speed on a carrier.",
        description="Time a full embed+extract round-trip with synthetic payload.",
    )
    p_bench.add_argument("carrier", type=Path, metavar="CARRIER")
    p_bench.add_argument("--mode", choices=["ultra-stealth","balanced","maximum"],
                         default="balanced")
    p_bench.add_argument("--size", type=int, default=512,
                         metavar="KB", help="Synthetic payload size in KB (default: 512).")

    return parser


def textwrap_dedent(s: str) -> str:
    import textwrap
    return textwrap.dedent(s)


# ── Password resolution ────────────────────────────────────────────────────────

def resolve_password(args, require_confirm: bool = False) -> str | None:
    """Return passphrase from flag, file, or interactive prompt."""
    if getattr(args, "no_encrypt", False):
        return None
    pw_file = getattr(args, "password_file", None)
    if pw_file:
        p = Path(pw_file)
        if not p.exists():
            print_error(Exception(f"Password file not found: {p}"))
            sys.exit(1)
        return p.read_text().splitlines()[0].strip()
    pw = getattr(args, "password", None)
    if pw:
        return pw
    return prompt_password(confirm=require_confirm)


# ── Command handlers ───────────────────────────────────────────────────────────

def cmd_embed(args: argparse.Namespace) -> int:
    if not args.quiet:
        print_banner()

    password = resolve_password(args, require_confirm=True)

    mode_map = {
        "ultra-stealth": EmbedMode.ULTRA_STEALTH,
        "balanced":      EmbedMode.BALANCED,
        "maximum":       EmbedMode.MAXIMUM,
        "custom":        EmbedMode.CUSTOM,
    }
    ch_map = {"b": ChannelSet.BLUE_ONLY, "bg": ChannelSet.BLUE_GREEN, "rgb": ChannelSet.RGB}
    st_map = {
        "sequential":   Strategy.SEQUENTIAL,
        "adaptive":     Strategy.ADAPTIVE,
        "prng-scatter": Strategy.PRNG_SCATTER,
    }

    config = EmbedConfig(
        carrier_path=args.carrier,
        payload_path=args.payload,
        output_path=args.output,
        mode=mode_map[args.mode],
        password=password,
        encrypt=not args.no_encrypt,
        compress=not args.no_compress,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        channels=ch_map.get(getattr(args, "channels", None) or ""),
        strategy=st_map.get(getattr(args, "strategy", None) or ""),
        max_lsb_depth=getattr(args, "max_lsb", 1),
        verbose=args.verbose,
        quiet=args.quiet,
    )

    if not args.quiet:
        print(f"  {bold('Embedding')} {args.payload.name}"
              f" → {args.carrier.name} [{cyan(args.mode)}]")
        if args.dry_run:
            print(f"  {yellow('Dry run mode — no files will be written')}")
        print()

    from stegocli.core.embedder import run_embed
    result = run_embed(config)

    if not args.quiet:
        print_embed_result(result)
    elif result.success:
        if not result.dry_run:
            print(result.output_path)

    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    if not args.quiet:
        print_banner()

    mode_map = {
        "ultra-stealth": EmbedMode.ULTRA_STEALTH,
        "balanced":      EmbedMode.BALANCED,
        "maximum":       EmbedMode.MAXIMUM,
        "custom":        EmbedMode.CUSTOM,
    }

    # Peek at bootstrap to see if encrypted before prompting
    from stegocli.carriers.image import load_carrier
    from stegocli.strategies.lsb import extract_sequential
    from stegocli.pipeline.header import Bootstrap, BOOTSTRAP_LEN
    from stegocli.core.models import ChannelSet
    try:
        carrier = load_carrier(args.carrier)
        raw = extract_sequential(carrier.pixels, bit_count=BOOTSTRAP_LEN*8,
                                  channels=ChannelSet.BLUE_ONLY, max_lsb=1)
        boot = Bootstrap.unpack(raw)
        needs_pw = boot.encrypted
    except Exception:
        needs_pw = True   # assume encrypted if we can't read

    if needs_pw:
        password = resolve_password(args, require_confirm=False)
    else:
        password = getattr(args, "password", None)

    config = ExtractConfig(
        carrier_path=args.carrier,
        output_dir=args.output_dir,
        password=password,
        output_name_override=getattr(args, "output_name", None),
        verify=not args.no_verify,
        verbose=args.verbose,
        quiet=args.quiet,
    )

    if not args.quiet:
        print(f"  {bold('Extracting')} from {args.carrier.name}"
              f" [{cyan(args.mode)}]")
        print()

    from stegocli.core.extractor import run_extract
    result = run_extract(config, mode=mode_map[args.mode])

    if not args.quiet:
        print_extract_result(result)
    else:
        print(result.output_path)

    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    from stegocli.core.inspector import run_inspect
    config = InspectConfig(carrier_path=args.carrier, verbose=args.verbose)
    result = run_inspect(config)
    print_inspect_result(result, args.carrier)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    pw_file = getattr(args, "password_file", None)
    password = None
    if pw_file and Path(pw_file).exists():
        password = Path(pw_file).read_text().splitlines()[0].strip()
    elif getattr(args, "password", None):
        password = args.password

    from stegocli.core.verifier import run_verify
    config = VerifyConfig(
        carrier_path=args.carrier,
        password=password,
        verbose=args.verbose,
    )
    result = run_verify(config)
    print_verify_result(result, args.carrier)
    return 0 if result.success else 1


def cmd_benchmark(args: argparse.Namespace) -> int:
    import tempfile, time, os
    print_banner()
    section(f"Benchmark — {args.carrier.name} [{args.mode}]")

    payload_kb = args.size
    payload_bytes = os.urandom(payload_kb * 1024)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        payload_path = td / "bench_payload.bin"
        output_path  = td / "bench_output.png"
        payload_path.write_bytes(payload_bytes)

        mode_map = {
            "ultra-stealth": EmbedMode.ULTRA_STEALTH,
            "balanced":      EmbedMode.BALANCED,
            "maximum":       EmbedMode.MAXIMUM,
        }
        config = EmbedConfig(
            carrier_path=args.carrier,
            payload_path=payload_path,
            output_path=output_path,
            mode=mode_map[args.mode],
            password="benchmarkpassword",
            encrypt=True,
            compress=True,
            overwrite=True,
        )
        from stegocli.core.embedder import run_embed
        t0 = time.monotonic()
        embed_result = run_embed(config)
        t_embed = time.monotonic() - t0

        ex_config = ExtractConfig(
            carrier_path=output_path,
            output_dir=td / "out",
            password="benchmarkpassword",
        )
        from stegocli.core.extractor import run_extract
        t1 = time.monotonic()
        ext_result = run_extract(ex_config, mode=mode_map[args.mode])
        t_extract = time.monotonic() - t1

    print_kv("Mode",          args.mode)
    print_kv("Payload size",  fmt_size(payload_kb * 1024))
    print_kv("Embed time",    f"{t_embed:.2f}s  ({payload_kb/t_embed:.0f} KB/s)")
    print_kv("Extract time",  f"{t_extract:.2f}s  ({payload_kb/t_extract:.0f} KB/s)")
    print_kv("Capacity used", f"{embed_result.capacity_used_pct:.1f}%")
    print_kv("Integrity",     green("PASS") if ext_result.integrity_ok else red("FAIL"))
    print()
    return 0


# ── Main entry point ───────────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    try:
        handlers = {
            "embed":     cmd_embed,
            "extract":   cmd_extract,
            "inspect":   cmd_inspect,
            "verify":    cmd_verify,
            "benchmark": cmd_benchmark,
        }
        rc = handlers[args.command](args)
        sys.exit(rc)
    except KeyboardInterrupt:
        print("\n  Aborted.", file=sys.stderr)
        sys.exit(130)
    except StegoCLIError as exc:
        print_error(exc)
        sys.exit(2)
    except Exception as exc:
        print_error(exc)
        if "--verbose" in sys.argv or "-v" in sys.argv:
            import traceback
            traceback.print_exc()
        sys.exit(3)


if __name__ == "__main__":
    main()
