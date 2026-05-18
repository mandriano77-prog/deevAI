"""Secrets vault — encrypt/decrypt tenant credentials at rest.

- **Development** (no ``KMS_KEY_ID``): Fernet key derived from ``API_SECRET_KEY``.
- **Production / KMS configured**: AWS KMS envelope via ``Encrypt`` / ``Decrypt``.

Ciphertext is prefixed with ``mkms1:`` so legacy Fernet blobs in the DB keep
working until re-saved under KMS.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from cryptography.fernet import Fernet, InvalidToken

from ..config import get_settings

log = logging.getLogger(__name__)

_KMS_PREFIX = b"mkms1:"
_FERNET_PREFIX = b"mfer1:"


def _use_kms() -> bool:
    settings = get_settings()
    return bool(settings.kms_key_id)


@lru_cache
def _kms_client():
    settings = get_settings()
    return boto3.client("kms", region_name=settings.aws_region)


def _fernet() -> Fernet:
    settings = get_settings()
    if settings.is_production and not settings.kms_key_id:
        log.warning(
            "KMS_KEY_ID not set — using Fernet vault keyed by API_SECRET_KEY in production. "
            "Set KMS_KEY_ID + IAM credentials for tenant secrets."
        )
    digest = hashlib.sha256(settings.api_secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _kms_encrypt(plaintext: str) -> bytes:
    settings = get_settings()
    key_id = settings.kms_key_id
    if not key_id:
        raise RuntimeError("KMS_KEY_ID is required for KMS encrypt")
    try:
        response = _kms_client().encrypt(
            KeyId=key_id,
            Plaintext=plaintext.encode("utf-8"),
        )
    except (ClientError, BotoCoreError) as exc:
        log.error("KMS encrypt failed: %s", exc.__class__.__name__)
        raise RuntimeError("KMS encrypt failed") from exc
    blob = response["CiphertextBlob"]
    return _KMS_PREFIX + blob


def _kms_decrypt(ciphertext: bytes) -> str:
    if not ciphertext.startswith(_KMS_PREFIX):
        raise ValueError("Not a KMS ciphertext blob")
    blob = ciphertext[len(_KMS_PREFIX) :]
    try:
        response = _kms_client().decrypt(CiphertextBlob=blob)
    except (ClientError, BotoCoreError) as exc:
        log.error("KMS decrypt failed: %s", exc.__class__.__name__)
        raise RuntimeError("KMS decrypt failed") from exc
    return response["Plaintext"].decode("utf-8")


def _fernet_encrypt(plaintext: str) -> bytes:
    token = _fernet().encrypt(plaintext.encode("utf-8"))
    return _FERNET_PREFIX + token


def _fernet_decrypt(ciphertext: bytes) -> str:
    if ciphertext.startswith(_FERNET_PREFIX):
        token = ciphertext[len(_FERNET_PREFIX) :]
    else:
        # Legacy rows written before the prefix convention.
        token = ciphertext
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        log.error("Vault decrypt failed — wrong key or tampered ciphertext")
        raise RuntimeError("Vault decrypt failed") from exc


def encrypt(plaintext: str) -> bytes:
    """Encrypt a UTF-8 string for storage in a LargeBinary column."""
    if plaintext is None:
        raise ValueError("Cannot encrypt None")
    if _use_kms():
        return _kms_encrypt(plaintext)
    return _fernet_encrypt(plaintext)


def decrypt(ciphertext: bytes) -> str:
    """Decrypt back to UTF-8. Supports KMS and legacy Fernet ciphertext."""
    if not ciphertext:
        raise ValueError("Cannot decrypt empty ciphertext")
    if ciphertext.startswith(_KMS_PREFIX):
        return _kms_decrypt(ciphertext)
    return _fernet_decrypt(ciphertext)


def vault_backend() -> str:
    """Return active backend id for health/diagnostics (never log secrets)."""
    return "kms" if _use_kms() else "fernet"
