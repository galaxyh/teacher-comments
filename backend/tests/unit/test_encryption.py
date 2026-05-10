"""Unit tests for AES-256-GCM helpers (security.md anonymize-restore round-trip prereq)."""

from __future__ import annotations

import base64
import os

import pytest

from app.services.encryption import KEY_BYTES, NONCE_BYTES, Cipher


@pytest.fixture
def cipher() -> Cipher:
    return Cipher.from_base64_key(base64.b64encode(os.urandom(KEY_BYTES)).decode())


class TestRoundTrip:
    def test_bytes_round_trip(self, cipher: Cipher) -> None:
        plaintext = b"\xff\x00\xa5 sensitive data"
        blob = cipher.encrypt(plaintext)
        assert cipher.decrypt(blob) == plaintext

    def test_str_round_trip(self, cipher: Cipher) -> None:
        plaintext = "王小明 — 中文 PII string"
        blob = cipher.encrypt_str(plaintext)
        assert cipher.decrypt_str(blob) == plaintext

    def test_each_encryption_uses_fresh_nonce(self, cipher: Cipher) -> None:
        """Two encryptions of the same plaintext yield different ciphertexts.

        Without unique nonces, GCM is broken. This is the load-bearing security property.
        """
        plaintext = b"identical input"
        blob1 = cipher.encrypt(plaintext)
        blob2 = cipher.encrypt(plaintext)
        assert blob1 != blob2
        # Both still decrypt to the same plaintext
        assert cipher.decrypt(blob1) == plaintext
        assert cipher.decrypt(blob2) == plaintext


class TestTamperDetection:
    def test_tampered_ciphertext_fails(self, cipher: Cipher) -> None:
        """GCM tag verifies integrity — flipping any bit must raise."""
        from cryptography.exceptions import InvalidTag

        blob = bytearray(cipher.encrypt(b"original"))
        # Flip a byte in the ciphertext body (after nonce)
        blob[NONCE_BYTES + 2] ^= 0x01
        with pytest.raises(InvalidTag):
            cipher.decrypt(bytes(blob))

    def test_truncated_ciphertext_fails(self, cipher: Cipher) -> None:
        with pytest.raises(ValueError, match="too short"):
            cipher.decrypt(b"short")

    def test_wrong_key_fails(self) -> None:
        from cryptography.exceptions import InvalidTag

        c1 = Cipher.from_base64_key(base64.b64encode(os.urandom(KEY_BYTES)).decode())
        c2 = Cipher.from_base64_key(base64.b64encode(os.urandom(KEY_BYTES)).decode())
        blob = c1.encrypt(b"secret")
        with pytest.raises(InvalidTag):
            c2.decrypt(blob)


class TestAssociatedData:
    def test_ad_binds_context(self, cipher: Cipher) -> None:
        """AD that doesn't match on decrypt must fail — prevents ciphertext relocation attack."""
        from cryptography.exceptions import InvalidTag

        plaintext = "student_name=王小明".encode()
        blob = cipher.encrypt(plaintext, associated_data=b"teacher_id=alice")
        # Same key + ciphertext but different AD → reject
        with pytest.raises(InvalidTag):
            cipher.decrypt(blob, associated_data=b"teacher_id=bob")
        # Correct AD → succeed
        assert cipher.decrypt(blob, associated_data=b"teacher_id=alice") == plaintext


class TestKeyValidation:
    def test_short_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="32 bytes"):
            Cipher.from_base64_key(base64.b64encode(b"\x00" * 16).decode())

    def test_invalid_base64_rejected(self) -> None:
        with pytest.raises(Exception):  # noqa: B017 — base64 raises various; we don't care which
            Cipher.from_base64_key("not-valid-base64-!!!")
