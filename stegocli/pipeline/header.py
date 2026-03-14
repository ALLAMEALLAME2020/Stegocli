"""
StegoCLI — Binary header format v2.

UNENCRYPTED BOOTSTRAP (43 bytes, authenticated as GCM AAD):
  0       8     Magic b'STGCLI\x01\x00'
  8       1     Version 0x01
  9       1     Flags (bit0=compressed, bit1=encrypted)
 10       1     KDF n_log2 (0 if no encryption)
 11      16     KDF salt  (zeros if no encryption)
 27      12     AES-GCM nonce (zeros if no encryption)
 39       4     Inner blob length in bytes (uint32 big-endian)
                = len(encrypted_or_plain_inner_block)
                  includes GCM tag (16 bytes) if encrypted.

INNER BLOCK (plaintext before encryption):
  0       4     Original payload size  (uint32 big-endian)
  4       4     Compressed payload size (uint32 big-endian)
  8      32     BLAKE2b-256 of ORIGINAL payload
 40       1     Filename length N
 41       N     Filename (UTF-8)
 41+N    M     Raw payload bytes (M = compressed_size)

After encryption: inner_block_bytes + 16-byte GCM tag
"""
from __future__ import annotations
import struct
from dataclasses import dataclass
from stegocli.core.exceptions import HeaderError, NoSignatureError

MAGIC         = b"STGCLI\x01\x00"
MAGIC_LEN     = 8
VERSION       = 0x01
BOOTSTRAP_LEN = 43          # was 39, now +4 for blob_length
FLAG_COMPRESSED = 0b00000001
FLAG_ENCRYPTED  = 0b00000010
MAX_FILENAME_LEN = 255


@dataclass
class Bootstrap:
    version:     int
    compressed:  bool
    encrypted:   bool
    kdf_n_log2:  int
    kdf_salt:    bytes    # 16 bytes
    nonce:       bytes    # 12 bytes
    blob_length: int      # exact byte length of the inner blob following bootstrap

    @property
    def flags(self) -> int:
        return (FLAG_COMPRESSED if self.compressed else 0) | (FLAG_ENCRYPTED if self.encrypted else 0)

    def pack(self) -> bytes:
        assert len(self.kdf_salt) == 16
        assert len(self.nonce)    == 12
        return (MAGIC
                + struct.pack(">BB",  self.version, self.flags)
                + struct.pack(">B",   self.kdf_n_log2)
                + self.kdf_salt
                + self.nonce
                + struct.pack(">I",   self.blob_length))

    @staticmethod
    def unpack(data: bytes) -> "Bootstrap":
        if len(data) < BOOTSTRAP_LEN:
            raise HeaderError(f"Bootstrap too short: {len(data)} < {BOOTSTRAP_LEN}")
        if data[:MAGIC_LEN] != MAGIC:
            raise NoSignatureError(
                "No stego signature found in this carrier.",
                hint="Not a StegoCLI file, or re-saved with lossy compression.",
            )
        version = data[8]
        if version != VERSION:
            raise HeaderError(f"Unsupported version: {version}")
        flags      = data[9]
        kdf_n_log2 = data[10]
        kdf_salt   = data[11:27]
        nonce      = data[27:39]
        blob_length = struct.unpack(">I", data[39:43])[0]
        return Bootstrap(
            version=version,
            compressed=bool(flags & FLAG_COMPRESSED),
            encrypted=bool(flags & FLAG_ENCRYPTED),
            kdf_n_log2=kdf_n_log2,
            kdf_salt=kdf_salt,
            nonce=nonce,
            blob_length=blob_length,
        )


@dataclass
class InnerBlock:
    original_size:   int
    compressed_size: int
    payload_hash:    bytes   # 32 bytes BLAKE2b
    filename:        str
    payload_data:    bytes

    def pack(self) -> bytes:
        fname_b = self.filename.encode("utf-8")[:MAX_FILENAME_LEN]
        return (struct.pack(">II", self.original_size, self.compressed_size)
                + self.payload_hash
                + struct.pack(">B", len(fname_b))
                + fname_b
                + self.payload_data)

    @staticmethod
    def unpack(data: bytes) -> "InnerBlock":
        if len(data) < 4 + 4 + 32 + 1:
            raise HeaderError("Inner block too short.")
        off = 0
        original_size   = struct.unpack(">I", data[off:off+4])[0]; off += 4
        compressed_size = struct.unpack(">I", data[off:off+4])[0]; off += 4
        payload_hash    = data[off:off+32]; off += 32
        fname_len       = data[off]; off += 1
        filename        = data[off:off+fname_len].decode("utf-8", errors="replace"); off += fname_len
        payload_data    = data[off:off+compressed_size]
        return InnerBlock(
            original_size=original_size,
            compressed_size=compressed_size,
            payload_hash=payload_hash,
            filename=filename,
            payload_data=payload_data,
        )


def pack_stream(bootstrap: Bootstrap, inner: InnerBlock, encrypt_fn=None) -> bytes:
    """Build the full embeddable byte stream."""
    inner_bytes     = inner.pack()
    bootstrap_bytes = bootstrap.pack()          # already has blob_length set
    if encrypt_fn is not None and bootstrap.encrypted:
        blob = encrypt_fn(inner_bytes, bootstrap.nonce, bootstrap_bytes)
    else:
        blob = inner_bytes
    return bootstrap_bytes + blob


def unpack_stream(stream: bytes, decrypt_fn=None):
    """Parse a full stream; decrypt if needed. Returns (Bootstrap, InnerBlock)."""
    bootstrap = Bootstrap.unpack(stream[:BOOTSTRAP_LEN])
    # Use blob_length for exact slice — critical for GCM correctness
    blob = stream[BOOTSTRAP_LEN : BOOTSTRAP_LEN + bootstrap.blob_length]
    if bootstrap.encrypted and decrypt_fn is not None:
        aad         = stream[:BOOTSTRAP_LEN]
        inner_bytes = decrypt_fn(blob, bootstrap.nonce, aad)
    else:
        inner_bytes = blob
    inner = InnerBlock.unpack(inner_bytes)
    return bootstrap, inner


def compute_stream_size(filename: str, payload_size: int, encrypted: bool) -> int:
    fname_len  = len(filename.encode("utf-8")[:MAX_FILENAME_LEN])
    inner_size = 4 + 4 + 32 + 1 + fname_len + payload_size
    gcm_tag    = 16 if encrypted else 0
    return BOOTSTRAP_LEN + inner_size + gcm_tag
