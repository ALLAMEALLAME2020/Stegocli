<div align="center">

```
  ███████╗████████╗███████╗ ██████╗  ██████╗ ██████╗██╗     ██╗
  ██╔════╝╚══██╔══╝██╔════╝██╔════╝ ██╔═══██╗██╔════╝██║    ██║
  ███████╗   ██║   █████╗  ██║  ███╗██║   ██║██║     ██║    ██║
  ╚════██║   ██║   ██╔══╝  ██║   ██║██║   ██║██║     ██║    ██║
  ███████║   ██║   ███████╗╚██████╔╝╚██████╔╝╚██████╗███████╗██║
  ╚══════╝   ╚═╝   ╚══════╝ ╚═════╝  ╚═════╝  ╚═════╝╚══════╝╚═╝
```

**Production-grade steganography — hide any file inside a PNG or BMP image.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue?style=flat-square&logo=python)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square)]()
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-38%20passing-brightgreen?style=flat-square)]()
[![Version](https://img.shields.io/badge/Version-1.0.0-orange?style=flat-square)]()

</div>

---

## What is StegoCLI?

StegoCLI lets you **hide arbitrary files — PDFs, text documents, JSON, ZIP archives, binaries — inside ordinary-looking PNG or BMP images** with no visible degradation. The carrier image looks identical to the naked eye before and after embedding. The hidden payload can be extracted later with perfect byte-for-byte integrity.

It is designed as a **serious, production-grade tool**, not a proof of concept. Every operation either succeeds with a verified result or fails loudly with a precise, actionable error message. No silent corruptions. No partial writes. No ambiguous states.

```
Before embedding               After embedding
┌──────────────┐               ┌──────────────┐
│              │               │              │
│  photo.png   │  +  📄 PDF   │  photo.png   │  ← visually identical
│  (carrier)   │               │  (stego)     │
└──────────────┘               └──────────────┘
     2.1 MB                         2.1 MB       hidden: 340 KB PDF
```

---

## Features

| Feature | Detail |
|---|---|
| **Encryption** | AES-256-GCM with Scrypt KDF (N=2¹⁷, 128 MB RAM) — military-grade |
| **Integrity** | BLAKE2b-256 hash stored in encrypted header, verified on every extraction |
| **Three modes** | `ultra-stealth`, `balanced`, `maximum` — control stealth vs capacity |
| **Three strategies** | PRNG scatter, adaptive LSB, sequential LSB |
| **Compression** | zlib compression before embedding (skipped automatically if it doesn't help) |
| **Atomic writes** | Temp file → verify → rename — interrupted operations never corrupt files |
| **Carrier formats** | PNG and BMP (lossless only — never JPEG) |
| **Password security** | Prompts securely via `getpass` — never echoed, never logged |
| **Interactive menu** | Guided step-by-step mode for users who prefer not to memorise flags |
| **Cross-platform** | Runs identically on Windows, Linux, and macOS |

---

## Requirements

- Python **3.9** or newer
- [Pillow](https://pillow.readthedocs.io/) — image I/O
- [cryptography](https://cryptography.io/) — AES-GCM and Scrypt

```bash
pip install Pillow cryptography
```

No other dependencies. Everything else is Python standard library.

---

## Installation

**Option A — clone and run directly (recommended):**
```bash
git clone https://github.com/yourname/stegocli.git
cd stegocli
pip install Pillow cryptography
python stegocli.py --help
```

**Option B — install as a package:**
```bash
pip install Pillow cryptography
pip install .
stegocli --help
```

**Option C — download the zip, extract, and run:**
```bash
# After extracting stegocli_v1.0.0.zip:
cd stegocli_v1.0.0
pip install Pillow cryptography
python stegocli.py --help
```

---

## Quick Start

```bash
# 1. Check what fits in your carrier image
python stegocli.py inspect photo.png

# 2. Hide a file (prompts for passphrase)
python stegocli.py embed photo.png secret.pdf output.png

# 3. Verify the result
python stegocli.py verify output.png

# 4. Recover the file on any machine
python stegocli.py extract output.png --output-dir ./recovered/
```

---

## Usage

### Running modes

**Interactive guided menu** — run with no arguments:
```bash
python stegocli.py
```
Presents a numbered menu. Asks one question at a time. No flags to remember.

**Direct command-line** — pass a command and flags:
```bash
python stegocli.py <command> [options] [arguments]
```

---

### `embed` — Hide a file inside a carrier image

```
python stegocli.py embed CARRIER PAYLOAD OUTPUT [options]
```

| Argument | Description |
|---|---|
| `CARRIER` | Source PNG or BMP image to use as the carrier |
| `PAYLOAD` | File to hide (any type: PDF, TXT, JSON, ZIP, binary, …) |
| `OUTPUT` | Path for the output stego image |

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--mode` | `balanced` | `ultra-stealth` / `balanced` / `maximum` / `custom` |
| `--password PASS` | *(prompted)* | Encryption passphrase |
| `--password-file FILE` | — | Read passphrase from first line of a file |
| `--no-encrypt` | off | Skip encryption (integrity hash still applied) |
| `--no-compress` | off | Skip zlib compression |
| `--dry-run` | off | Analyse and simulate without writing any file |
| `--overwrite` | off | Allow replacing an existing output file |
| `--channels b\|bg\|rgb` | *(from mode)* | Override channel selection (`custom` mode) |
| `--strategy sequential\|adaptive\|prng-scatter` | *(from mode)* | Override strategy (`custom` mode) |
| `--max-lsb 1\|2` | *(from mode)* | Override LSB depth (`custom` mode) |
| `--quiet` | off | Suppress all output except errors |
| `--verbose` | off | Print full audit trail including timing |

**Examples:**

```bash
# Simplest — prompts for passphrase interactively
python stegocli.py embed photo.png report.pdf stego.png

# Maximum stealth with passphrase from file
python stegocli.py embed photo.png report.pdf stego.png \
    --mode ultra-stealth \
    --password-file ./my_key.txt

# Maximum capacity, no encryption
python stegocli.py embed photo.png archive.zip stego.png \
    --mode maximum \
    --no-encrypt

# Dry run — check if payload fits without writing anything
python stegocli.py embed photo.png report.pdf stego.png --dry-run

# Custom mode — full manual control
python stegocli.py embed photo.png payload.bin out.png \
    --mode custom \
    --strategy prng-scatter \
    --channels rgb \
    --max-lsb 2
```

**Sample output:**
```
  Embedding report.pdf → photo.png [balanced]

Embed Complete
────────────────────────────────────────────────────────────
  ✓ Success
  Output:                   stego.png
  Carrier:                  PNG
  Mode:                     balanced
  Strategy:                 prng-scatter
  Channels:                 bg
  Original size:            1.2 MB
  Compressed:               487.3 KB  (2.5× smaller)
  Payload hash:             a3f9c12e04bd7801…c94f2e18
  Bits written:             3,997,680

  Capacity used          [████░░░░░░░░░░░░░░░░░░░░░░░░░░]   5.5%

  Time: 3.12s
```

---

### `extract` — Recover the hidden file

```
python stegocli.py extract CARRIER [options]
```

| Argument | Description |
|---|---|
| `CARRIER` | Stego image to extract from |

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--mode` | `balanced` | Must match the mode used during embedding |
| `--password PASS` | *(prompted if needed)* | Decryption passphrase |
| `--password-file FILE` | — | Read passphrase from file |
| `--output-dir DIR` | `.` (current dir) | Directory to write the extracted file |
| `--output-name NAME` | *(from header)* | Override the extracted filename |
| `--no-verify` | off | Skip BLAKE2b integrity check *(not recommended)* |
| `--quiet` | off | Print only the output path on success |

**Examples:**

```bash
# Basic extraction — prompts for passphrase
python stegocli.py extract stego.png

# Specify output directory and mode
python stegocli.py extract stego.png \
    --mode ultra-stealth \
    --output-dir ./recovered/

# Scripting-friendly quiet mode
python stegocli.py extract stego.png \
    --password-file key.txt \
    --quiet
```

**Sample output:**
```
Extract Complete
────────────────────────────────────────────────────────────
  ✓ Success   Integrity: ✓ PASS
  Output file:              ./recovered/report.pdf
  Filename:                 report.pdf
  Original size:            1.2 MB
  Compressed:               yes
  Encrypted:                yes
  Hash (stored):            a3f9c12e04bd7801…
  Hash (actual):            a3f9c12e04bd7801…

  Time: 1.84s
```

---

### `inspect` — Analyse a carrier's capacity

```
python stegocli.py inspect CARRIER
```

Scans a carrier image and reports resolution, colour mode, maximum embeddable payload size for each mode, and whether an existing StegoCLI signature is already present.

```bash
python stegocli.py inspect vacation_photo.png
```

```
Carrier Analysis — vacation_photo.png
────────────────────────────────────────────────────────────
  Format:                   PNG
  Dimensions:               4032 × 3024 px
  Color mode:               RGB
  Pixel count:              12,192,768
  Channels:                 3
  Stego sig:                none detected

  Mode               Capacity     Description
  ────────────────────────────────────────────────────────────
  ultra-stealth       1.4 MB      1-bit blue LSB, PRNG scatter
  balanced            2.9 MB      1-2 bit adaptive, B+G, PRNG scatter
  maximum             8.7 MB      2-bit adaptive RGB
```

> **Tip:** Always run `inspect` before embedding to confirm your payload fits.

---

### `verify` — Check a stego carrier's integrity

```
python stegocli.py verify CARRIER [options]
```

Without a password, confirms that the StegoCLI signature and header are intact.  
With a password, fully authenticates the payload via AES-GCM tag verification.

| Flag | Description |
|---|---|
| `--password PASS` | Passphrase for full payload authentication |
| `--password-file FILE` | Read passphrase from file |

```bash
python stegocli.py verify stego.png --password "my passphrase"
```

```
Verify — stego.png
────────────────────────────────────────────────────────────
  Signature:                ✓ present
  Header:                   ✓ intact
  Payload auth:             ✓ verified
  Encrypted:                yes
  Compressed:               yes
  Filename:                 report.pdf
  Original size:            1.2 MB

  Carrier verified — signature present and header intact.
```

---

### `benchmark` — Measure embed/extract speed

```
python stegocli.py benchmark CARRIER [--mode MODE] [--size KB]
```

Performs a full embed → extract round-trip with randomly generated data of the specified size and reports throughput in KB/s.

```bash
python stegocli.py benchmark vacation_photo.png --mode balanced --size 1024
```

```
Benchmark — vacation_photo.png [balanced]
────────────────────────────────────────────────────────────
  Mode:             balanced
  Payload size:     1024.0 KB
  Embed time:       5.43s   (188 KB/s)
  Extract time:     3.21s   (319 KB/s)
  Capacity used:    36.8%
  Integrity:        ✓ PASS
```

---

## Embedding Modes

The mode controls the stealth-vs-capacity trade-off. **The mode used at extraction must match the mode used at embedding.**

| Mode | Strategy | Channels | LSB depth | Est. capacity | Best for |
|---|---|---|---|---|---|
| `ultra-stealth` | PRNG scatter | Blue only | 1 bit | ~12% of pixels | Maximum deniability; small payloads |
| `balanced` | PRNG scatter | Blue + Green | 1–2 bits adaptive | ~25% of pixels | General use *(default)* |
| `maximum` | Adaptive LSB | R + G + B | 2 bits | ~75% of pixels | Large payloads; stealth secondary |
| `custom` | *your choice* | *your choice* | *your choice* | varies | Full manual control |

---

## How It Works

### Embedding pipeline

```
Payload file
     │
     ▼
[1]  BLAKE2b-256 hash         ← integrity fingerprint, stored in header
     │
     ▼
[2]  zlib compress             ← skipped automatically if no size benefit
     │
     ▼
[3]  Build inner block         ← sizes + hash + filename + compressed data
     │
     ▼
[4]  AES-256-GCM encrypt       ← Scrypt(password + salt) → 256-bit key
     │                            bootstrap header used as AAD (authenticated)
     ▼
[5]  Prepend bootstrap         ← 39 bytes unencrypted: magic + flags + salt + nonce
     │
     ▼
[6]  Embed bits into carrier   ← bootstrap: pixels 0–311, sequential blue LSB
     │                            payload:   pixels 312+, chosen strategy
     ▼
[7]  Atomic save               ← write .stgtmp → verify bootstrap magic → rename
     │
     ▼
[8]  Post-write verify         ← re-read bootstrap from output file; delete+abort if wrong
```

### Binary header format

```
UNENCRYPTED BOOTSTRAP — 39 bytes (authenticated as GCM AAD)
 ┌──────────┬───────┬───────┬──────────────────────┬─────────────┐
 │  Magic   │  Ver  │ Flags │    KDF params         │  GCM nonce  │
 │  8 bytes │ 1 byte│ 1 byte│  1 (n_log2) + 16 (salt)│  12 bytes  │
 └──────────┴───────┴───────┴──────────────────────┴─────────────┘

ENCRYPTED INNER BLOCK — variable (includes 16-byte GCM auth tag)
 ┌────────────┬────────────────┬────────────┬──────────┬──────────┬──────────┐
 │ orig_size  │ compressed_size│  BLAKE2b   │ fname_len│ filename │   data   │
 │  4 bytes   │    4 bytes     │  32 bytes  │  1 byte  │  N bytes │  M bytes │
 └────────────┴────────────────┴────────────┴──────────┴──────────┴──────────┘
                                                              + 16-byte GCM tag
```

### PRNG scatter strategy

In `balanced` and `ultra-stealth` modes, bits are not written sequentially. A seed derived from the AES key via BLAKE2b determines a Fisher-Yates shuffle of all available pixel-channel slots. An observer cannot extract the payload without the passphrase because the **embedding positions themselves are secret**.

```
All slots (example):   [0,B] [0,G] [1,B] [1,G] [2,B] [2,G] ...
Shuffled by key seed:  [847,G] [12,B] [3021,G] [5,B] [1204,G] ...
                           ↑ indistinguishable from noise without the key
```

---

## Security Design

### Cryptographic primitives

| Primitive | Algorithm | Purpose |
|---|---|---|
| Key derivation | Scrypt (N=2¹⁷, r=8, p=1) | Password → 256-bit key. 128 MB RAM cost resists GPU brute-force |
| Encryption | AES-256-GCM | Authenticated encryption of payload + inner header |
| Integrity | BLAKE2b-256 | Hash of original payload stored in encrypted header |
| PRNG seed | BLAKE2b-8 of AES key | Scatter position derivation |
| Nonce | 96-bit CSPRNG | Fresh random nonce per embed operation |
| Salt | 128-bit CSPRNG | Fresh random salt per embed operation |

### Tamper detection

AES-GCM provides **authenticated encryption**. The bootstrap header is passed as additional authenticated data (AAD). Any modification to any bit of the embedded data — payload, inner header, or bootstrap — causes GCM tag verification to fail instantly. The error message is intentionally ambiguous:

```
Decryption failed — incorrect password or tampered carrier.
```

This prevents oracle attacks: an attacker cannot determine whether their modification was detected or whether the password was wrong.

### What the bootstrap reveals without a password

The 39-byte bootstrap is always readable. It reveals:
- That StegoCLI was used (magic bytes)
- Whether the payload is encrypted/compressed (flags)
- The Scrypt salt and AES-GCM nonce (needed to *attempt* decryption)

It reveals **nothing** about payload content, filename, size, or type.

### Password handling

- Passwords are **never logged**, stored, or printed
- Interactive prompts use `getpass` — no terminal echo, no shell history exposure
- Use `--password-file` for automation to avoid the passphrase appearing in process lists
- Scrypt takes 2–4 seconds intentionally — this makes offline brute-force attacks against the passphrase extremely expensive

---

## Edge Cases and Error Handling

| Situation | Error raised | Message |
|---|---|---|
| Wrong password | `AuthenticationError` | *"Decryption failed — incorrect password or tampered carrier."* |
| Tampered carrier bytes | `AuthenticationError` | *(same — deliberately identical)* |
| Payload too large | `CapacityError` | Shows payload size, available capacity, and suggests alternatives |
| Image has no signature | `NoSignatureError` | *"No stego signature found in this carrier."* |
| Image re-saved as JPEG | `NoSignatureError` | LSB data is destroyed by JPEG compression |
| BLAKE2b hash mismatch | `IntegrityError` | *"Payload integrity check failed — BLAKE2b hash mismatch."* |
| Interrupted write | *(rolled back)* | `.stgtmp` deleted; original carrier untouched |
| Output file already exists | `PayloadError` | Requires explicit `--overwrite` flag |
| Unsupported format (.jpg) | `UnsupportedFormatError` | Lists supported formats, suggests PNG conversion |
| Corrupted bootstrap header | `HeaderError` | Reports which field failed to parse |
| Carrier too small | `CapacityError` | Reports pixel count and minimum required |

> **Important:** PNG files must **never** be re-saved with lossy compression after embedding. Uploading to social media platforms that re-compress images (Instagram, Twitter/X, WhatsApp) will destroy the hidden data irreversibly. Always transfer stego files as attachments or through services that preserve lossless images.

---

## Project Structure

```
stegocli_v1.0.0/
│
├── stegocli.py               ← Main entry point (interactive menu + CLI)
├── setup.py                  ← pip install support
├── test_stegocli.py          ← 38-test suite (no external test framework needed)
├── README.md
│
└── stegocli/                 ← Core package (2,019 lines, 17 modules)
    │
    ├── __init__.py            version = "1.0.0"
    ├── __main__.py            python -m stegocli support
    │
    ├── cli/
    │   ├── main.py            argparse CLI — 5 commands with all flags
    │   └── display.py         ANSI terminal output, progress bars, result tables
    │
    ├── core/
    │   ├── embedder.py        Embed orchestration — 8-step pipeline
    │   ├── extractor.py       Extract orchestration — mirrors embed layout
    │   ├── inspector.py       Carrier capacity analysis
    │   ├── verifier.py        Signature + integrity verification
    │   ├── models.py          Typed dataclasses, enums, mode presets
    │   └── exceptions.py      12-class typed exception hierarchy
    │
    ├── carriers/
    │   └── image.py           PNG/BMP load, pixel I/O, atomic save
    │
    ├── pipeline/
    │   ├── crypto.py          AES-256-GCM, Scrypt KDF, BLAKE2b
    │   ├── compression.py     zlib with automatic benefit-testing
    │   └── header.py          Binary header pack/unpack (bootstrap + inner block)
    │
    └── strategies/
        └── lsb.py             Sequential / Adaptive / PRNG scatter (all 3 strategies)
```

---

## Running the Tests

```bash
python test_stegocli.py
```

The test suite requires no external test framework — it runs with the Python standard library. All 38 tests cover:

- Crypto: key derivation, AES-GCM round-trip, tamper detection, wrong password, BLAKE2b
- Compression: round-trips, incompressible data handling
- Header: bootstrap and inner block pack/unpack, bad magic detection
- Strategies: all three embed/extract strategies, LSB delta verification, seed uniqueness
- Carrier I/O: PNG load/save, BMP load/save, unsupported format rejection, dimension preservation
- End-to-end: all three modes, binary/text/JSON payloads, BMP carriers, filename preservation, atomic writes
- Dry run, inspector, error handling for every failure mode

```
  Results: 38 passed  0 failed  (total 38)
  All tests passed! ✓
```

---

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Verification failed (`verify` command) |
| `2` | StegoCLI operational error (wrong password, capacity exceeded, bad format, etc.) |
| `3` | Unexpected internal error |
| `130` | Interrupted by Ctrl+C |

Exit codes make StegoCLI easy to use in shell scripts:

```bash
#!/bin/bash
python stegocli.py verify stego.png --password-file key.txt
if [ $? -eq 0 ]; then
    python stegocli.py extract stego.png \
        --password-file key.txt \
        --output-dir ./recovered/ \
        --quiet
    echo "Extracted: $?"
fi
```

---

## Limitations

**Carrier must be lossless.** JPEG re-compression destroys LSB data. Always use PNG or BMP. Convert JPEG carriers before use:
```bash
python -c "from PIL import Image; Image.open('photo.jpg').save('photo.png')"
```

**Mode must match on both ends.** The extraction mode must be the same as the embedding mode. The mode is deliberately *not* stored in the unencrypted bootstrap — knowing the strategy provides information to an attacker.

**Large carriers recommended.** A 4K image (3840×2160) holds ~30 MB in maximum mode. A 400×400 image holds ~87 KB in balanced mode. Use `inspect` to check before embedding.

**Scrypt is slow by design.** Key derivation takes 2–4 seconds. This is a security feature, not a bug — it makes brute-force attacks prohibitively expensive. The embed/extract operations themselves are fast; the delay is purely key derivation.

---

## Roadmap

- [ ] WebP and JPEG-LS carrier support (lossless variants)
- [ ] DCT-domain embedding strategy for JPEG tolerance  
- [ ] Batch operations across multiple carriers
- [ ] Carrier quality scoring (chi-square, entropy analysis)
- [ ] GUI wrapper
- [ ] Passphrase strength meter

---


---

## Acknowledgements

Built on open standards and open-source libraries:

- [Pillow](https://pillow.readthedocs.io/) — image processing
- [cryptography](https://cryptography.io/) — AES-GCM and Scrypt via OpenSSL
- Python standard library — `zlib`, `hashlib`, `secrets`, `argparse`, `struct`, `getpass`

No proprietary dependencies. No telemetry. No network access at runtime.

---

<div align="center">

*"The best hidden message is one whose existence is not suspected."*

</div>
