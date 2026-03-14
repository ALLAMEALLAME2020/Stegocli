"""
StegoCLI — Custom exceptions with rich context for every failure mode.
"""


class StegoCLIError(Exception):
    """Base exception for all StegoCLI errors."""
    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.message = message
        self.hint = hint

    def __str__(self):
        if self.hint:
            return f"{self.message}\n  Hint: {self.hint}"
        return self.message


class CarrierError(StegoCLIError):
    """Problems reading or writing carrier files."""


class UnsupportedFormatError(CarrierError):
    """Carrier file format is not supported."""


class CapacityError(StegoCLIError):
    """Payload is too large for the carrier in the selected mode."""


class PayloadError(StegoCLIError):
    """Problems with the payload file."""


class CryptoError(StegoCLIError):
    """Encryption / decryption failures."""


class AuthenticationError(CryptoError):
    """Wrong password or tampered data — GCM tag verification failed."""


class IntegrityError(StegoCLIError):
    """BLAKE2b hash mismatch after extraction."""


class HeaderError(StegoCLIError):
    """Embedded header is missing, malformed, or corrupted."""


class NoSignatureError(HeaderError):
    """No stego signature found in this carrier."""


class StrategyError(StegoCLIError):
    """Invalid or conflicting strategy configuration."""


class AtomicWriteError(StegoCLIError):
    """Failed to atomically write output file."""
