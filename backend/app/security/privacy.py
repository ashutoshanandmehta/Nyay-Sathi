"""Guest-only privacy: signed credentials, per-case envelope encryption, erasure, and portable transfer."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

ENVELOPE_PREFIX = "enc:v1:"
TRANSFER_SCHEMA = "nyay-case-transfer-v1"
PBKDF2_ITERATIONS = 200_000


class CaseKeyDestroyedError(PermissionError):
    """Raised when attempting to decrypt data for a cryptographically erased case."""


def _derive_subkeys(key_bytes: bytes, context: bytes) -> tuple[bytes, bytes]:
    prk = hmac.new(b"nyay-aead-v1", key_bytes, hashlib.sha256).digest()
    enc_key = hmac.new(prk, context + b"|enc|\x01", hashlib.sha256).digest()
    mac_key = hmac.new(prk, context + b"|mac|\x02", hashlib.sha256).digest()
    return enc_key, mac_key


def _xor_bytes(data: bytes, stream: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, stream, strict=True))


def aead_encrypt(key_bytes: bytes, plaintext: bytes, aad: bytes = b"") -> str:
    """Authenticated Encrypt-then-MAC using SHAKE256 stream + constant-time HMAC-SHA256."""
    nonce = secrets.token_bytes(16)
    enc_key, mac_key = _derive_subkeys(key_bytes, nonce)
    keystream = hashlib.shake_256(enc_key + nonce).digest(len(plaintext)) if plaintext else b""
    ciphertext = _xor_bytes(plaintext, keystream) if plaintext else b""
    mac = hmac.new(mac_key, b"v1|" + nonce + b"|" + aad + b"|" + ciphertext, hashlib.sha256).digest()
    blob = nonce + mac + ciphertext
    return base64.urlsafe_b64encode(blob).decode("ascii")


def aead_decrypt(key_bytes: bytes, encoded: str, aad: bytes = b"") -> bytes:
    try:
        blob = base64.urlsafe_b64decode(encoded.encode("ascii"))
    except Exception as exc:
        raise ValueError("Malformed encrypted payload") from exc
    if len(blob) < 48:
        raise ValueError("Truncated encrypted payload")
    nonce, mac, ciphertext = blob[:16], blob[16:48], blob[48:]
    enc_key, mac_key = _derive_subkeys(key_bytes, nonce)
    expected = hmac.new(
        mac_key, b"v1|" + nonce + b"|" + aad + b"|" + ciphertext, hashlib.sha256
    ).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Authentication tag verification failed")
    if not ciphertext:
        return b""
    keystream = hashlib.shake_256(enc_key + nonce).digest(len(ciphertext))
    return _xor_bytes(ciphertext, keystream)


def sign_device_token(raw_token: str, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), raw_token.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    return f"{raw_token}.{sig}"


def verify_device_token(cookie_value: str, secret: str, *, allow_unsigned: bool = True) -> str | None:
    if "." not in cookie_value:
        return cookie_value if allow_unsigned else None
    raw, sig = cookie_value.rsplit(".", 1)
    if not raw or not sig:
        return None
    expected = hmac.new(secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
    if not hmac.compare_digest(sig, expected):
        return None
    return raw


class EnvelopeCipher:
    """Manages per-case Data Encryption Keys (DEKs) wrapped by the KMS Master KEK."""

    def __init__(self, master_secret: str, key_id: str = "local-kek-v1"):
        self.kek = hashlib.sha256(f"nyay-kek|{key_id}|{master_secret}".encode()).digest()
        self.key_id = key_id

    def generate_wrapped_dek(self, conversation_id: str) -> str:
        dek = secrets.token_bytes(32)
        return aead_encrypt(self.kek, dek, aad=conversation_id.encode("utf-8"))

    def unwrap_dek(self, conversation_id: str, wrapped_dek: str) -> bytes:
        if not wrapped_dek:
            raise CaseKeyDestroyedError("Case encryption key has been cryptographically destroyed")
        return aead_decrypt(self.kek, wrapped_dek, aad=conversation_id.encode("utf-8"))

    def encrypt_text(self, conversation_id: str, wrapped_dek: str, text: str) -> str:
        if text == "" or text.startswith(ENVELOPE_PREFIX):
            return text
        dek = self.unwrap_dek(conversation_id, wrapped_dek)
        token = aead_encrypt(dek, text.encode("utf-8"), aad=conversation_id.encode("utf-8"))
        return ENVELOPE_PREFIX + token

    def decrypt_text(self, conversation_id: str, wrapped_dek: str | None, value: str) -> str:
        if not value or not value.startswith(ENVELOPE_PREFIX):
            return value
        if not wrapped_dek:
            raise CaseKeyDestroyedError("Case encryption key has been cryptographically destroyed")
        dek = self.unwrap_dek(conversation_id, wrapped_dek)
        raw = aead_decrypt(
            dek, value[len(ENVELOPE_PREFIX) :], aad=conversation_id.encode("utf-8")
        )
        return raw.decode("utf-8")

    def encrypt_bytes(self, conversation_id: str, wrapped_dek: str, data: bytes) -> bytes:
        dek = self.unwrap_dek(conversation_id, wrapped_dek)
        token = aead_encrypt(dek, data, aad=conversation_id.encode("utf-8"))
        return (ENVELOPE_PREFIX + token).encode("ascii")

    def decrypt_bytes(self, conversation_id: str, wrapped_dek: str | None, data: bytes) -> bytes:
        prefix = ENVELOPE_PREFIX.encode("ascii")
        if not data.startswith(prefix):
            return data
        if not wrapped_dek:
            raise CaseKeyDestroyedError("Case encryption key has been cryptographically destroyed")
        dek = self.unwrap_dek(conversation_id, wrapped_dek)
        return aead_decrypt(
            dek, data[len(prefix) :].decode("ascii"), aad=conversation_id.encode("utf-8")
        )


def export_encrypted_transfer_bundle(case_snapshot: dict[str, Any], passphrase: str) -> dict[str, Any]:
    """Create a passphrase-encrypted portable transfer package for guest device migration."""
    if len(passphrase) < 8:
        raise ValueError("Passphrase must be at least 8 characters")
    salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=32
    )
    aad = TRANSFER_SCHEMA.encode("utf-8")
    plaintext = json.dumps(case_snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ciphertext = aead_encrypt(derived, plaintext, aad=aad)
    return {
        "schema": TRANSFER_SCHEMA,
        "kdf": "PBKDF2-HMAC-SHA256",
        "iterations": PBKDF2_ITERATIONS,
        "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
        "ciphertext": ciphertext,
        "exported_at": datetime.now(UTC).isoformat(),
        "loss_warning": (
            "Nyay Saathi uses guest-only pseudonymous access with no phone or email recovery. "
            "Losing both your browser credential and this transfer package (or its passphrase) permanently loses access."
        ),
    }


def import_encrypted_transfer_bundle(bundle: dict[str, Any], passphrase: str) -> dict[str, Any]:
    """Verify and decrypt a portable guest case-transfer package."""
    if bundle.get("schema") != TRANSFER_SCHEMA:
        raise ValueError("Unsupported transfer bundle schema")
    try:
        salt = base64.urlsafe_b64decode(str(bundle["salt"]).encode("ascii"))
        iterations = int(bundle.get("iterations", PBKDF2_ITERATIONS))
        if iterations < 50_000 or iterations > 1_000_000:
            raise ValueError("Invalid KDF iterations")
        derived = hashlib.pbkdf2_hmac(
            "sha256", passphrase.encode("utf-8"), salt, iterations, dklen=32
        )
        plaintext = aead_decrypt(derived, str(bundle["ciphertext"]), aad=TRANSFER_SCHEMA.encode("utf-8"))
        return json.loads(plaintext.decode("utf-8"))
    except ValueError as exc:
        raise ValueError("Invalid passphrase or corrupted transfer package") from exc


def retention_status(updated_at_iso: str, inactivity_days: int = 365) -> dict[str, Any]:
    """Compute transparent 1-year inactivity retention window for guest cases."""
    try:
        updated = datetime.fromisoformat(updated_at_iso.replace("Z", "+00:00"))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=UTC)
    except ValueError:
        updated = datetime.now(UTC)
    expires_at = updated + timedelta(days=inactivity_days)
    remaining = max(0, (expires_at - datetime.now(UTC)).days)
    return {
        "policy": "inactivity_auto_purge",
        "inactivity_retention_days": inactivity_days,
        "last_active_at": updated.isoformat(),
        "expires_at": expires_at.isoformat(),
        "days_remaining": remaining,
        "user_deletable_anytime": True,
        "cross_case_training_permitted": False,
        "advertising_or_brokerage_permitted": False,
    }
