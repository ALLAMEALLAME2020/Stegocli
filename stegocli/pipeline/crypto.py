"""
StegoCLI — Cryptographic operations.

Primitives used (all from stdlib + cryptography package):
  - Key derivation : Scrypt (N=2^17, r=8, p=1) — memory-hard, GPU-resistant
  - Encryption     : AES-256-GCM  — authenticated encryption
  - Integrity hash : BLAKE2b-256   — payload fingerprint in header
  - PRNG seed      : BLAKE2b derived from key — for scatter strategy

Design goals:
  - Wrong password → AuthenticationError (GCM tag mismatch)
  - Tampered bytes → AuthenticationError (identical error, no oracle)
  - Keys are zeroed from memory after use where possible
"""
from __future__ import annotations
import hashlib
import os
import secrets
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.backends import default_backend

from stegocli.core.exceptions import AuthenticationError, CryptoError


# ── Constants ──────────────────────────────────────────────────────────────────

SCRYPT_N = 1 << 17      # 2^17 = 131 072  (memory: N*128*r = 128 MiB)
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LEN   = 32          # 256 bits for AES-256
NONCE_LEN = 12          # 96-bit nonce for GCM
SALT_LEN  = 16          # 128-bit Scrypt salt
HASH_LEN  = 32          # BLAKE2b-256 digest size
GCM_TAG_LEN = 16        # appended by AESGCM internally

# "Fast" parameters used in dry-run / verification-only paths where no real
# secret is involved.  NEVER use these for actual encryption.
SCRYPT_N_FAST = 1 << 14


# ── Key derivation ─────────────────────────────────────────────────────────────

def derive_key(password: str, salt: bytes, fast: bool = False) -> bytes:
    """
    Derive a 256-bit key from *password* using Scrypt.

    Parameters
    ----------
    password : str   — user passphrase (UTF-8 encoded internally)
    salt     : bytes — 16 random bytes stored in the header
    fast     : bool  — use reduced parameters (benchmarking / testing only)

    Returns
    -------
    32-byte AES key
    """
    n = SCRYPT_N_FAST if fast else SCRYPT_N
    try:
        kdf = Scrypt(salt=salt, length=KEY_LEN, n=n, r=SCRYPT_R, p=SCRYPT_P,
                     backend=default_backend())
        key = kdf.derive(password.encode("utf-8"))
        return key
    except Exception as exc:
        raise CryptoError(f"Key derivation failed: {exc}") from exc


def generate_salt() -> bytes:
    """Return 16 cryptographically random bytes."""
    return secrets.token_bytes(SALT_LEN)


def generate_nonce() -> bytes:
    """Return 12 cryptographically random bytes (AES-GCM nonce)."""
    return secrets.token_bytes(NONCE_LEN)


# ── Encryption / decryption ───────────────────────────────────────────────────

def encrypt(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    """
    Encrypt *plaintext* with AES-256-GCM.

    Returns ciphertext + 16-byte authentication tag (concatenated by
    cryptography's AESGCM implementation automatically).
    """
    try:
        aesgcm = AESGCM(key)
        return aesgcm.encrypt(nonce, plaintext, None)
    except Exception as exc:
        raise CryptoError(f"Encryption failed: {exc}") from exc


def decrypt(ciphertext_with_tag: bytes, key: bytes, nonce: bytes) -> bytes:
    """
    Decrypt and authenticate AES-256-GCM ciphertext.

    Raises AuthenticationError on tag mismatch (wrong key or tampered data).
    The error message is intentionally ambiguous.
    """
    try:
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ciphertext_with_tag, None)
    except Exception:
        raise AuthenticationError(
            "Decryption failed — incorrect password or tampered carrier.",
            hint="Ensure you are using the exact passphrase used during embedding.",
        )


# ── Integrity hashing ─────────────────────────────────────────────────────────

def hash_payload(data: bytes) -> bytes:
    """Return BLAKE2b-256 digest of *data*."""
    h = hashlib.blake2b(data, digest_size=HASH_LEN)
    return h.digest()


def hash_payload_hex(data: bytes) -> str:
    """Return hex-encoded BLAKE2b-256 digest."""
    return hash_payload(data).hex()


def verify_hash(data: bytes, expected_digest: bytes) -> bool:
    """Constant-time comparison of BLAKE2b digest."""
    computed = hash_payload(data)
    # Use hmac.compare_digest for constant-time comparison
    import hmac
    return hmac.compare_digest(computed, expected_digest)


# ── PRNG seeding ───────────────────────────────────────────────────────────────

def derive_prng_seed(key: bytes) -> int:
    """
    Derive a 64-bit integer seed for the scatter PRNG from the encryption key.
    Using the key (not the password) ties the scatter pattern to the
    key derivation — changing the password changes the scatter.
    """
    h = hashlib.blake2b(key, digest_size=8)
    return struct.unpack(">Q", h.digest())[0]


# ── KDF parameter pack/unpack ─────────────────────────────────────────────────

def pack_kdf_params(salt: bytes, n_log2: int = 17) -> bytes:
    """
    Pack Scrypt parameters into 17 bytes for header storage.
    Format: 1 byte n_log2, 16 bytes salt.
    """
    return struct.pack(">B", n_log2) + salt


def unpack_kdf_params(data: bytes) -> tuple[int, bytes]:
    """
    Unpack Scrypt params from 17 bytes.
    Returns (n_log2, salt).
    """
    n_log2 = struct.unpack(">B", data[:1])[0]
    salt = data[1:17]
    return n_log2, salt
