#!/usr/bin/env python3
"""
StegoCLI — Interactive command-line launcher.

Run this script directly:
    python stegocli.py
    python stegocli.py embed photo.png secret.pdf output.png
    python stegocli.py --help
"""
import sys
import os

# Make sure the package directory is importable whether the user
# runs this from inside or outside the stegocli_v1.0.0 folder.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ── Dependency check ──────────────────────────────────────────────────────────
def _check_deps():
    missing = []
    try:
        import PIL
    except ImportError:
        missing.append("Pillow")
    try:
        import cryptography
    except ImportError:
        missing.append("cryptography")
    if missing:
        print("\n  \033[31mError:\033[0m Missing required packages: " + ", ".join(missing))
        print("  Install with:  pip install " + " ".join(missing))
        print()
        sys.exit(1)

_check_deps()

# ── Interactive menu (no args given) ─────────────────────────────────────────
def _interactive_menu():
    """Full guided interactive mode for users who run the script with no arguments."""
    import getpass, tempfile
    from pathlib import Path
    from stegocli.cli.display import (
        print_banner, section, print_kv, fmt_size,
        green, red, yellow, cyan, bold, dim,
        print_embed_result, print_extract_result,
        print_inspect_result, print_verify_result,
    )

    print_banner()

    MENU = [
        ("embed",     "Hide a file inside a carrier image"),
        ("extract",   "Recover a hidden file from a stego image"),
        ("inspect",   "Analyse a carrier's capacity"),
        ("verify",    "Check a stego image's signature & integrity"),
        ("benchmark", "Benchmark embed/extract speed"),
        ("quit",      "Exit"),
    ]

    def _pick(prompt, options, allow_blank=False, default=None):
        """Display a numbered menu and return the chosen value."""
        for i, (val, desc) in enumerate(options, 1):
            marker = f"  {cyan(str(i)+'.')} {bold(val):<22} {dim(desc)}"
            if default and val == default:
                marker += f"  {dim('[default]')}"
            print(marker)
        print()
        while True:
            raw = input(f"  {prompt}: ").strip()
            if allow_blank and raw == "" and default:
                return default
            if raw == "" and not allow_blank:
                print(f"  {red('Please enter a number.')}")
                continue
            try:
                idx = int(raw) - 1
                if 0 <= idx < len(options):
                    return options[idx][0]
            except ValueError:
                pass
            print(f"  {red('Invalid choice — enter a number 1–'+str(len(options)))}")

    def _ask(prompt, default=None, secret=False):
        """Ask a single question and return the answer."""
        hint = f" [{dim(default)}]" if default else ""
        while True:
            if secret:
                val = getpass.getpass(f"  {prompt}{hint}: ")
            else:
                val = input(f"  {prompt}{hint}: ").strip()
            if val:
                return val
            if default is not None:
                return default
            print(f"  {red('This field is required.')}")

    def _confirm(prompt, default=True):
        hint = "Y/n" if default else "y/N"
        raw = input(f"  {prompt} [{dim(hint)}]: ").strip().lower()
        if raw == "":
            return default
        return raw in ("y", "yes")

    def _path(prompt, must_exist=True):
        while True:
            raw = input(f"  {prompt}: ").strip().strip('"').strip("'")
            p = Path(raw)
            if must_exist and not p.exists():
                print(f"  {red('File not found:')} {p}")
                continue
            return p

    while True:
        section("Main menu")
        cmd = _pick("Choose a command", MENU)
        print()

        if cmd == "quit":
            print(f"  {dim('Goodbye.')}\n")
            sys.exit(0)

        # ── EMBED ──────────────────────────────────────────────────────────
        elif cmd == "embed":
            section("Embed — hide a file inside an image")
            carrier = _path("Carrier image (PNG or BMP)", must_exist=True)
            payload = _path("File to hide", must_exist=True)
            out_default = carrier.parent / ("stego_" + carrier.name)
            print(f"  Output image {dim('(press Enter for: '+str(out_default)+')')}")
            raw_out = input("  Output path: ").strip().strip('"').strip("'")
            output  = Path(raw_out) if raw_out else out_default

            print()
            section("Options")
            mode = _pick("Embedding mode", [
                ("balanced",      "Recommended — PRNG scatter, B+G, ~25% capacity"),
                ("ultra-stealth", "Maximum stealth — blue channel only, ~12% capacity"),
                ("maximum",       "Maximum capacity — adaptive RGB, ~75% capacity"),
            ], allow_blank=True, default="balanced")
            print()

            do_encrypt = _confirm("Encrypt payload? (AES-256-GCM)", default=True)
            password   = None
            if do_encrypt:
                while True:
                    password = getpass.getpass(f"  Passphrase: ")
                    if not password:
                        print(f"  {red('Passphrase cannot be empty.')}")
                        continue
                    confirm = getpass.getpass(f"  Confirm passphrase: ")
                    if password != confirm:
                        print(f"  {red('Passphrases do not match — try again.')}")
                        continue
                    break
            print()

            do_compress = _confirm("Compress payload before embedding?", default=True)
            dry_run     = _confirm("Dry run (analyse without writing)?", default=False)
            overwrite   = False
            if output.exists() and not dry_run:
                overwrite = _confirm(f"Output '{output.name}' exists — overwrite?", default=False)
            print()

            from stegocli.core.models import EmbedConfig, EmbedMode
            from stegocli.core.embedder import run_embed
            M = {"balanced": EmbedMode.BALANCED,
                 "ultra-stealth": EmbedMode.ULTRA_STEALTH,
                 "maximum": EmbedMode.MAXIMUM}
            cfg = EmbedConfig(
                carrier_path=carrier, payload_path=payload, output_path=output,
                mode=M[mode], password=password,
                encrypt=do_encrypt, compress=do_compress,
                dry_run=dry_run, overwrite=overwrite,
            )
            try:
                result = run_embed(cfg)
                print_embed_result(result)
            except Exception as exc:
                print(f"\n  {red('Error:')} {exc}\n")

        # ── EXTRACT ────────────────────────────────────────────────────────
        elif cmd == "extract":
            section("Extract — recover a hidden file")
            carrier = _path("Stego carrier image", must_exist=True)
            out_dir_raw = input(f"  Output directory [{dim('current directory')}]: ").strip().strip('"').strip("'")
            out_dir = Path(out_dir_raw) if out_dir_raw else Path(".")

            print()
            mode = _pick("Mode used during embedding", [
                ("balanced",      "Default — PRNG scatter, B+G"),
                ("ultra-stealth", "Blue channel only"),
                ("maximum",       "Adaptive RGB"),
            ], allow_blank=True, default="balanced")
            print()

            # Peek at bootstrap to know if encrypted
            from stegocli.carriers.image import load_carrier
            from stegocli.strategies.lsb import extract_sequential
            from stegocli.pipeline.header import Bootstrap, BOOTSTRAP_LEN
            from stegocli.core.models import ChannelSet
            try:
                c = load_carrier(carrier)
                raw_bs = extract_sequential(c.pixels[:BOOTSTRAP_LEN*8],
                                            BOOTSTRAP_LEN*8, ChannelSet.BLUE_ONLY, 1)
                boot = Bootstrap.unpack(raw_bs)
                needs_pw = boot.encrypted
            except Exception:
                needs_pw = True

            password = None
            if needs_pw:
                password = getpass.getpass(f"  Passphrase: ")
            print()

            from stegocli.core.models import ExtractConfig, EmbedMode
            from stegocli.core.extractor import run_extract
            M = {"balanced": EmbedMode.BALANCED,
                 "ultra-stealth": EmbedMode.ULTRA_STEALTH,
                 "maximum": EmbedMode.MAXIMUM}
            cfg = ExtractConfig(carrier_path=carrier, output_dir=out_dir, password=password)
            try:
                result = run_extract(cfg, mode=M[mode])
                print_extract_result(result)
            except Exception as exc:
                print(f"\n  {red('Error:')} {exc}\n")

        # ── INSPECT ────────────────────────────────────────────────────────
        elif cmd == "inspect":
            section("Inspect — carrier capacity analysis")
            carrier = _path("Carrier image", must_exist=True)
            print()
            from stegocli.core.inspector import run_inspect
            from stegocli.core.models import InspectConfig
            try:
                result = run_inspect(InspectConfig(carrier_path=carrier))
                print_inspect_result(result, carrier)
            except Exception as exc:
                print(f"\n  {red('Error:')} {exc}\n")

        # ── VERIFY ─────────────────────────────────────────────────────────
        elif cmd == "verify":
            section("Verify — check signature and integrity")
            carrier = _path("Stego carrier image", must_exist=True)
            provide_pw = _confirm("Provide password for full payload authentication?", default=True)
            password = None
            if provide_pw:
                password = getpass.getpass(f"  Passphrase: ")
            print()
            from stegocli.core.verifier import run_verify
            from stegocli.core.models import VerifyConfig
            try:
                result = run_verify(VerifyConfig(carrier_path=carrier, password=password))
                print_verify_result(result, carrier)
            except Exception as exc:
                print(f"\n  {red('Error:')} {exc}\n")

        # ── BENCHMARK ──────────────────────────────────────────────────────
        elif cmd == "benchmark":
            section("Benchmark — speed test")
            carrier = _path("Carrier image", must_exist=True)
            mode    = _pick("Mode to benchmark", [
                ("balanced",      "Balanced"),
                ("ultra-stealth", "Ultra stealth"),
                ("maximum",       "Maximum"),
            ], allow_blank=True, default="balanced")
            raw_sz = input(f"  Synthetic payload size in KB [{dim('512')}]: ").strip()
            size_kb = int(raw_sz) if raw_sz.isdigit() else 512
            print()
            import types
            args = types.SimpleNamespace(carrier=carrier, mode=mode, size=size_kb)
            from stegocli.cli.main import cmd_benchmark
            try:
                cmd_benchmark(args)
            except Exception as exc:
                print(f"\n  {red('Error:')} {exc}\n")

        input(f"  {dim('Press Enter to return to main menu...')}")
        print()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # No arguments → interactive guided menu
        try:
            _interactive_menu()
        except KeyboardInterrupt:
            print("\n\n  Aborted.\n")
            sys.exit(130)
    else:
        # Arguments present → pass directly to the CLI parser
        from stegocli.cli.main import main
        main()
