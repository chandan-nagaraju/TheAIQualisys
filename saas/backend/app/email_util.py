"""SMTP helpers for password reset (sync, runs in FastAPI threadpool)."""

from __future__ import annotations

import smtplib
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

    # Envelope sender should match the authenticated SMTP user when set (Gmail/Workspace often reject or drop otherwise).
    envelope_from = (settings.smtp_user or settings.email_from or "").strip()
    timeout = 20
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout) as smtp:
            if settings.smtp_user and settings.smtp_password is not None:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg, from_addr=envelope_from, to_addrs=[to_email])
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password is not None:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg, from_addr=envelope_from, to_addrs=[to_email])
