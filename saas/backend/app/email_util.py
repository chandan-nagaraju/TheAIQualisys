"""Transactional email: password reset, subscription reminders (Resend or SMTP)."""

from __future__ import annotations

import html
import json
import smtplib
import socket
import urllib.error
import urllib.request
from datetime import date
from email.message import EmailMessage
from html import escape

from app.config import Settings

SUBSCRIPTION_EXPIRY_SUBJECT = "Your FIR Automation subscription ends today"
SUBSCRIPTION_EXPIRY_REPLY_TO = "admin@theaiqualisys.com"


def is_email_configured(settings: Settings) -> bool:
    if settings.email_from and settings.resend_api_key:
        return True
    return bool(settings.email_from and settings.smtp_host and settings.smtp_port)


def _send_via_resend(
    settings: Settings,
    to_email: str,
    subject: str,
    text: str,
    *,
    html: str | None = None,
    reply_to: str | None = None,
) -> None:
    key = settings.resend_api_key
    sender = settings.email_from
    if not key or not sender:
        raise RuntimeError("Resend requires RESEND_API_KEY and EMAIL_FROM")

    payload: dict[str, object] = {
        "from": sender,
        "to": [to_email],
        "subject": subject,
        "text": text,
    }
    if html is not None:
        payload["html"] = html
    if reply_to:
        payload["reply_to"] = reply_to

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "TheAIQualisys-Backend/1.0 (+https://www.theaiqualisys.com)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend API HTTP {exc.code}: {body}") from exc


def _ipv4_tcp_connection(
    host: str,
    port: int,
    timeout: float | None,
    source_address: tuple[str, int] | None,
) -> socket.socket:
    """TCP connect using the first working IPv4 address (keeps TLS hostname as `host` on the session)."""
    infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    if not infos:
        raise OSError(f"No IPv4 address found for {host!r}")
    last_exc: OSError | None = None
    for fam, socktype, proto, _canon, sockaddr in infos:
        sock: socket.socket | None = None
        try:
            sock = socket.socket(fam, socktype, proto)
            if timeout is not None:
                sock.settimeout(timeout)
            if source_address is not None:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            last_exc = exc
            if sock is not None:
                sock.close()
    assert last_exc is not None
    raise last_exc


class _SMTPPreferIPv4(smtplib.SMTP):
    def _get_socket(self, host: str, port: int, timeout: float | None) -> socket.socket:
        if timeout is not None and not timeout:
            raise ValueError("Non-blocking socket (timeout=0) is not supported")
        if self.debuglevel > 0:
            self._print_debug("connect: to", (host, port), self.source_address)
        return _ipv4_tcp_connection(host, port, timeout, self.source_address)


class _SMTP_SSLPreferIPv4(smtplib.SMTP_SSL):
    def _get_socket(self, host: str, port: int, timeout: float | None) -> socket.socket:
        if self.debuglevel > 0:
            self._print_debug("connect:", (host, port))
        new_socket = _ipv4_tcp_connection(host, port, timeout, self.source_address)
        return self.context.wrap_socket(new_socket, server_hostname=self._host)


def send_plain_text_email(settings: Settings, to_email: str, subject: str, text: str) -> None:
    """Send a single plain-text email via Resend (if configured) or SMTP."""
    if settings.resend_api_key:
        _send_via_resend(settings, to_email, subject, text)
        return

    if not (settings.email_from and settings.smtp_host and settings.smtp_port):
        raise RuntimeError("SMTP is not configured")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = to_email
    msg.set_content(text)

    envelope_from = (settings.smtp_user or settings.email_from or "").strip()
    timeout = 20
    host = settings.smtp_host
    assert host is not None

    if settings.smtp_use_ssl:
        smtp_cls = _SMTP_SSLPreferIPv4 if settings.smtp_force_ipv4 else smtplib.SMTP_SSL
        with smtp_cls(host, settings.smtp_port, timeout=timeout) as smtp:
            if settings.smtp_user and settings.smtp_password is not None:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg, from_addr=envelope_from, to_addrs=[to_email])
        return

    smtp_cls = _SMTPPreferIPv4 if settings.smtp_force_ipv4 else smtplib.SMTP
    with smtp_cls(host, settings.smtp_port, timeout=timeout) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password is not None:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg, from_addr=envelope_from, to_addrs=[to_email])


def _send_text_and_html_email(
    settings: Settings,
    to_email: str,
    subject: str,
    text: str,
    html: str,
    *,
    reply_to: str | None = None,
) -> None:
    if settings.resend_api_key:
        _send_via_resend(
            settings,
            to_email,
            subject,
            text,
            html=html,
            reply_to=reply_to,
        )
        return

    if not (settings.email_from and settings.smtp_host and settings.smtp_port):
        raise RuntimeError("SMTP is not configured")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.email_from
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    envelope_from = (settings.smtp_user or settings.email_from or "").strip()
    timeout = 20
    host = settings.smtp_host
    assert host is not None

    if settings.smtp_use_ssl:
        smtp_cls = _SMTP_SSLPreferIPv4 if settings.smtp_force_ipv4 else smtplib.SMTP_SSL
        with smtp_cls(host, settings.smtp_port, timeout=timeout) as smtp:
            if settings.smtp_user and settings.smtp_password is not None:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg, from_addr=envelope_from, to_addrs=[to_email])
        return

    smtp_cls = _SMTPPreferIPv4 if settings.smtp_force_ipv4 else smtplib.SMTP
    with smtp_cls(host, settings.smtp_port, timeout=timeout) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_user and settings.smtp_password is not None:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg, from_addr=envelope_from, to_addrs=[to_email])


def _format_subscription_end_human(subscription_end: date) -> str:
    """e.g. 18 May 2026"""
    return f"{subscription_end.day} {subscription_end.strftime('%B')} {subscription_end.year}"


def _subscription_expiry_text_body(
    company_name: str,
    subscription_end_formatted: str,
    fir_count: int,
    billing_url: str,
) -> str:
    return (
        "Hello,\n\n"
        "We hope FIR Automation has been helping your team save time and make inspection reporting easier.\n\n"
        f"We wanted to gently remind you that your subscription for {company_name} is scheduled to end today, "
        f"{subscription_end_formatted}.\n\n"
        f"Over the past month, your team has processed {fir_count} FIR report entries through the platform. "
        "It has been a pleasure supporting your work, and we would be honored to continue helping your team "
        "streamline inspection and reporting.\n\n"
        "To avoid any interruption in service, you can renew your subscription here:\n\n"
        f"{billing_url}\n\n"
        "If you need any assistance, have questions, or would like to discuss your plan, simply reply to this email. "
        "We are always happy to help.\n\n"
        "Thank you for placing your trust in us.\n\n"
        "Warm regards,\n\n"
        "Chandan N\n"
        "Founder, The AI Qualisys\n"
        "admin@theaiqualisys.com\n"
    )


def _subscription_expiry_html_body(
    company_name: str,
    subscription_end_formatted: str,
    fir_count: int,
    billing_url: str,
) -> str:
    cn = escape(company_name)
    df = escape(subscription_end_formatted)
    safe_url = escape(billing_url, quote=True)
    count_bold = f"<strong>{fir_count}</strong>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /></head>
<body style="margin:0;padding:24px;font-family:Georgia,'Times New Roman',serif;font-size:16px;line-height:1.65;color:#1e293b;background:#f8fafc;">
  <div style="max-width:560px;margin:0 auto;background:#ffffff;padding:32px;border-radius:12px;border:1px solid #e2e8f0;">
    <p style="margin:0 0 16px;">Hello,</p>
    <p style="margin:0 0 16px;">We hope FIR Automation has been helping your team save time and make inspection reporting easier.</p>
    <p style="margin:0 0 16px;">We wanted to gently remind you that your subscription for <strong>{cn}</strong> is scheduled to end today, <strong>{df}</strong>.</p>
    <p style="margin:0 0 16px;">Over the past month, your team has processed {count_bold} FIR report entries through the platform. It has been a pleasure supporting your work, and we would be honored to continue helping your team streamline inspection and reporting.</p>
    <p style="margin:0 0 20px;">To avoid any interruption in service, you can renew your subscription using the button below:</p>
    <div style="text-align:center;margin:28px 0;">
      <a href="{safe_url}" style="display:inline-block;background:#2563eb;color:#ffffff !important;text-decoration:none;font-weight:600;padding:14px 28px;border-radius:10px;font-family:system-ui,sans-serif;">Renew Subscription</a>
    </div>
    <p style="margin:0 0 16px;font-size:15px;">If you need any assistance, have questions, or would like to discuss your plan, simply reply to this email. We are always happy to help.</p>
    <p style="margin:24px 0 8px;">Thank you for placing your trust in us.</p>
    <p style="margin:16px 0 4px;">Warm regards,</p>
    <p style="margin:0;line-height:1.5;">Chandan N<br />Founder, The AI Qualisys<br /><a href="mailto:admin@theaiqualisys.com" style="color:#2563eb;">admin@theaiqualisys.com</a></p>
  </div>
</body>
</html>"""


def send_password_reset_email(settings: Settings, to_email: str, reset_link: str) -> None:
    subject = "Reset your FIR Automation password"
    text = (
        f"You requested a password reset.\n\nOpen this link to choose a new password (expires in 1 hour):\n{reset_link}\n\n"
        "If you did not request this, you can ignore this email."
    )
    send_plain_text_email(settings, to_email, subject, text)


def send_subscription_expiring_email(
    settings: Settings,
    to_email: str,
    *,
    company_name: str,
    subscription_end_date: date,
    fir_count: int,
    billing_url: str,
) -> None:
    """Warm renewal reminder; same copy for morning and evening sends (multipart text + HTML)."""
    subscription_end_formatted = _format_subscription_end_human(subscription_end_date)
    text = _subscription_expiry_text_body(
        company_name,
        subscription_end_formatted,
        fir_count,
        billing_url,
    )
    html = _subscription_expiry_html_body(
        company_name,
        subscription_end_formatted,
        fir_count,
        billing_url,
    )
    _send_text_and_html_email(
        settings,
        to_email,
        SUBSCRIPTION_EXPIRY_SUBJECT,
        text,
        html,
        reply_to=SUBSCRIPTION_EXPIRY_REPLY_TO,
    )


SIGNUP_VERIFY_SUBJECT = "Verify your email to create your The AI Qualisys account"


def is_signup_email_configured(settings: Settings) -> bool:
    return bool(settings.resend_api_key and settings.email_from)


def send_signup_verification_email(settings: Settings, to_email: str, verification_link: str) -> None:
    """Signup verification: multipart text + HTML via Resend (required — see is_signup_email_configured)."""
    if not is_signup_email_configured(settings):
        raise RuntimeError("Resend is not configured (RESEND_API_KEY and EMAIL_FROM required)")
    text = f"""Hello,

Thank you for your interest in The AI Qualisys.

Please verify your email address by clicking the link below:

{verification_link}

This link will allow you to set your password and complete your account setup.

If you did not request this, you can safely ignore this email.

Team,
TheAIQualisys"""
    safe_href = escape(verification_link, quote=True)
    safe_display = escape(verification_link, quote=False)
    html = f"""<!DOCTYPE html>
<html>
<body>
<p>Hello,</p>
<p>Thank you for your interest in The AI Qualisys.</p>
<p>Please verify your email address by clicking the link below:</p>
<p><a href="{safe_href}">{safe_display}</a></p>
<p>This link will allow you to set your password and complete your account setup.</p>
<p>If you did not request this, you can safely ignore this email.</p>
<p>Team,<br>TheAIQualisys</p>
</body>
</html>"""
    _send_text_and_html_email(settings, to_email, SIGNUP_VERIFY_SUBJECT, text, html)
