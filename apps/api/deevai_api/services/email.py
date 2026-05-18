"""Transactional email via Resend.

If RESEND_API_KEY is unset, emails are logged and skipped (dev-friendly).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)


def _send_sync(
    *,
    to: str,
    subject: str,
    html: str,
    idempotency_key: str,
) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        log.info(
            "Email skipped (no RESEND_API_KEY): to=%s subject=%s",
            to,
            subject,
        )
        return

    import resend

    resend.api_key = settings.resend_api_key
    params: dict[str, Any] = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    result = resend.Emails.send(params, idempotency_key=idempotency_key)
    err = getattr(result, "error", None) if not isinstance(result, dict) else result.get("error")
    if err:
        raise RuntimeError(str(err))


async def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    idempotency_key: str,
) -> None:
    await asyncio.to_thread(
        _send_sync,
        to=to,
        subject=subject,
        html=html,
        idempotency_key=idempotency_key,
    )


def welcome_email_html(*, name: str | None, tenant_name: str, login_url: str) -> str:
    greeting = name or "ciao"
    return f"""
<p>Ciao {greeting},</p>
<p>Il workspace <strong>{tenant_name}</strong> su deevAI è pronto.</p>
<p>Nei primi 14 giorni l&apos;agente lavora in <strong>observation only</strong>:
propone ottimizzazioni sui bid ma non applica nulla sul tuo seat Amazon DSP.</p>
<p><a href="{login_url}">Accedi alla dashboard</a></p>
<p>Quando sei pronto, completa l&apos;onboarding per collegare Amazon DSP.</p>
<p>— Il team deevAI</p>
"""


def password_reset_email_html(*, reset_url: str) -> str:
    return f"""
<p>Hai richiesto il reset della password per il tuo account deevAI.</p>
<p><a href="{reset_url}">Imposta una nuova password</a></p>
<p>Il link scade tra un&apos;ora. Se non hai richiesto tu il reset, ignora questa email.</p>
<p>— Il team deevAI</p>
"""


async def send_welcome_email(
    *,
    to: str,
    user_id: str,
    name: str | None,
    tenant_name: str,
) -> None:
    settings = get_settings()
    login_url = f"{settings.app_base_url.rstrip('/')}/login"
    await send_email(
        to=to,
        subject="Benvenuto su deevAI",
        html=welcome_email_html(
            name=name,
            tenant_name=tenant_name,
            login_url=login_url,
        ),
        idempotency_key=f"welcome/{user_id}",
    )


async def send_password_reset_email(*, to: str, user_id: str, token: str) -> None:
    settings = get_settings()
    reset_url = (
        f"{settings.app_base_url.rstrip('/')}/reset-password"
        f"?token={token}"
    )
    await send_email(
        to=to,
        subject="Reimposta la password deevAI",
        html=password_reset_email_html(reset_url=reset_url),
        idempotency_key=f"password-reset/{user_id}",
    )
