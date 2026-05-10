"""AES-256-GCM helpers for PII mapping and OAuth refresh token storage.

Per ARCH-001 §8.3 — two separate keys (PII vs OAuth) so rotating one doesn't
invalidate the other. Key rotation script (DESIGN-001 §X) uses these primitives
to re-encrypt existing rows.

Format: ciphertext = nonce(12) || tag(16) || encrypted_data
- 12-byte nonce per record (random) — meets NIST SP 800-38D requirements
- AESGCM construction binds tag inside the ciphertext envelope (cryptography library
  encodes it as the last 16 bytes of `encrypt()` return value)
- Storing nonce inside the ciphertext blob means callers don't manage it separately;
  the BLOB column is self-contained
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12
KEY_BYTES = 32  # AES-256


@dataclass(frozen=True)
class Cipher:
    """Wraps a single AES-256-GCM key.

    Construct one per logical key (one for PII, one for OAuth). Key bytes are held
    in-memory only — never logged, never serialised, never written to disk by us.
    """

    _aesgcm: AESGCM

    @classmethod
    def from_base64_key(cls, b64_key: str) -> Cipher:
        raw = base64.b64decode(b64_key, validate=True)
        if len(raw) != KEY_BYTES:
            raise ValueError(
                f"Encryption key must be {KEY_BYTES} bytes (AES-256); got {len(raw)}"
            )
        return cls(_aesgcm=AESGCM(raw))

    def encrypt(self, plaintext: bytes, *, associated_data: bytes | None = None) -> bytes:
        """Encrypt; returned blob includes the random nonce as a 12-byte prefix."""
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, associated_data)
        return nonce + ciphertext

    def decrypt(self, blob: bytes, *, associated_data: bytes | None = None) -> bytes:
        if len(blob) < NONCE_BYTES + 16:  # 16 = GCM tag size
            raise ValueError("Ciphertext too short to contain nonce + tag")
        nonce, ciphertext = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
        return self._aesgcm.decrypt(nonce, ciphertext, associated_data)

    def encrypt_str(self, plaintext: str, *, associated_data: bytes | None = None) -> bytes:
        return self.encrypt(plaintext.encode("utf-8"), associated_data=associated_data)

    def decrypt_str(self, blob: bytes, *, associated_data: bytes | None = None) -> str:
        return self.decrypt(blob, associated_data=associated_data).decode("utf-8")


# ── Cipher cache (module-level) ─────────────────────────────────────
# Build once on first access to avoid re-validating keys on every encryption call.
_pii_cipher: Cipher | None = None
_oauth_cipher: Cipher | None = None


def get_pii_cipher() -> Cipher:
    """Cipher for `pii_mapping.original_value_encrypted`."""
    global _pii_cipher
    if _pii_cipher is None:
        from app.config import get_settings  # local import: avoid circular at module load
        _pii_cipher = Cipher.from_base64_key(
            get_settings().pii_encryption_key.get_secret_value()
        )
    return _pii_cipher


def get_oauth_cipher() -> Cipher:
    """Cipher for `teacher.oauth_refresh_token_encrypted`."""
    global _oauth_cipher
    if _oauth_cipher is None:
        from app.config import get_settings
        _oauth_cipher = Cipher.from_base64_key(
            get_settings().oauth_token_encryption_key.get_secret_value()
        )
    return _oauth_cipher


def reset_cipher_cache() -> None:
    """Test-only — drop cached ciphers so a key rotation in tests takes effect."""
    global _pii_cipher, _oauth_cipher
    _pii_cipher = None
    _oauth_cipher = None
