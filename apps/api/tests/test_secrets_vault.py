"""Secrets vault — Fernet dev path and KMS path."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from deevai_api.services import secrets_vault


@pytest.fixture(autouse=True)
def _clear_kms_cache() -> None:
    secrets_vault._kms_client.cache_clear()
    yield
    secrets_vault._kms_client.cache_clear()


def test_fernet_roundtrip() -> None:
    with patch.object(secrets_vault, "_use_kms", return_value=False):
        blob = secrets_vault.encrypt("refresh-token-abc")
        assert blob.startswith(secrets_vault._FERNET_PREFIX)
        assert secrets_vault.decrypt(blob) == "refresh-token-abc"


def test_legacy_fernet_without_prefix() -> None:
    with patch.object(secrets_vault, "_use_kms", return_value=False):
        raw = secrets_vault._fernet().encrypt(b"legacy")
        assert secrets_vault.decrypt(raw) == "legacy"


def test_kms_roundtrip() -> None:
    mock_client = MagicMock()
    mock_client.encrypt.return_value = {"CiphertextBlob": b"kms-blob-bytes"}
    mock_client.decrypt.return_value = {"Plaintext": b"amazon-refresh"}

    with (
        patch.object(secrets_vault, "_use_kms", return_value=True),
        patch.object(secrets_vault, "_kms_client", return_value=mock_client),
        patch(
            "deevai_api.services.secrets_vault.get_settings",
        ) as mock_settings,
    ):
        mock_settings.return_value.kms_key_id = "arn:aws:kms:eu-central-1:123:key/abc"
        blob = secrets_vault.encrypt("amazon-refresh")
        assert blob.startswith(secrets_vault._KMS_PREFIX)
        assert secrets_vault.decrypt(blob) == "amazon-refresh"

    mock_client.encrypt.assert_called_once()
    mock_client.decrypt.assert_called_once()


def test_vault_backend_label() -> None:
    with patch("deevai_api.services.secrets_vault.get_settings") as mock_settings:
        mock_settings.return_value.kms_key_id = None
        assert secrets_vault.vault_backend() == "fernet"
        mock_settings.return_value.kms_key_id = "arn:aws:kms:eu-central-1:123:key/abc"
        assert secrets_vault.vault_backend() == "kms"
