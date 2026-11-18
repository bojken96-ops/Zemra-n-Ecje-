"""Encryption helpers for OAuth tokens and API keys stored in the database."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class CryptoError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().token_encryption_key
    if not key:
        raise CryptoError("TOKEN_ENCRYPTION_KEY is not configured; refusing to store secrets unencrypted")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:  # pragma: no cover - config error
        raise CryptoError("TOKEN_ENCRYPTION_KEY must be a urlsafe base64 32-byte Fernet key") from exc


def encrypt(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str | None) -> str | None:
    if ciphertext is None:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise CryptoError("Stored secret could not be decrypted (wrong TOKEN_ENCRYPTION_KEY?)") from exc


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge
