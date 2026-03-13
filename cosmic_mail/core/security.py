from __future__ import annotations

import base64
import hmac
import hashlib
import secrets

from cryptography.fernet import Fernet


class SecretBox:
    def __init__(self, secret_key: str) -> None:
        digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt_text(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt_text(self, value: str) -> str:
        return self._fernet.decrypt(value.encode("utf-8")).decode("utf-8")


def fingerprint_token(secret_key: str, token: str) -> str:
    return hmac.new(
        secret_key.encode("utf-8"),
        token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def compare_secret(candidate: str, expected: str) -> bool:
    return hmac.compare_digest(candidate, expected)


def generate_api_key() -> str:
    return f"cm_org_{secrets.token_urlsafe(32)}"
