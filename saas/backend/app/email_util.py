"""SMTP helpers for password reset (sync, runs in FastAPI threadpool)."""

from __future__ import annotations

import json
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from app.config import Settings


def is_email_configured(settings: Settings) -> bool:
    return bool(settings.email_from and settings.smtp_host and settings.smtp_port)


def send_password_reset_email(settings: Settings, to_email: str, reset_link: str) -> None:
    if not is_email_configured(settings):
        raise RuntimeError("SMTP is not configured")

    msg = EmailMessage()
    msg["Subject"] = "Reset your FIR Automation password"
    msg["From"] = settings.email_from
    msg["To"] = to_email
    msg.set_content(
        f"You requested a password reset.\n\nOpen this link to choose a new password (expires in 1 hour):\n{reset_link}\n\n"
        "If you did not request this, you can ignore this email."
    )

    timeout = 20
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout) as smtp:
            if settings.smtp_user and settings.smtp_password is not None:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password is not None:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def is_signup_email_configured(settings: Settings) -> bool:
    return bool(settings.resend_api_key and settings.email_from)


def send_signup_verification_email(settings: Settings, to_email: str, verification_link: str) -> None:
    """Send signup verification via Resend (https://resend.com/docs)."""
    if not is_signup_email_configured(settings):
        raise RuntimeError("Resend is not configured (RESEND_API_KEY and EMAIL_FROM required)")
    body = f"""Hello,

Thank you for your interest in The AI Qualisys.

Please verify your email address by clicking the link below:

{verification_link}

This link will allow you to set your password and complete your account setup.

If you did not request this, you can safely ignore this email.

Warm regards,
Chandan N
Founder, The AI Qualisys"""
    payload = json.dumps(
        {
            "from": settings.email_from,
            "to": [to_email],
            "subject": "Verify your email to create your The AI Qualisys account",
            "text": body,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status not in (200, 201):
                raise RuntimeError(f"Resend HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend error HTTP {e.code}: {err_body}") from e
