"""SMTP helpers for password reset (sync, runs in FastAPI threadpool)."""

from __future__ import annotations

import json
import smtplib
import socket
import urllib.error
import urllib.request
from email.message import EmailMessage

from app.config import Settings


def is_email_configured(settings: Settings) -> bool:
    if settings.email_from and settings.resend_api_key:
        return True
    return bool(settings.email_from and settings.smtp_host and settings.smtp_port)


def _send_via_resend(settings: Settings, to_email: str, subject: str, text: str) -> None:
    key = settings.resend_api_key
    sender = settings.email_from
    if not key or not sender:
        raise RuntimeError("Resend requires RESEND_API_KEY and EMAIL_FROM")

    payload = {"from": sender, "to": [to_email], "subject": subject, "text": text}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
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


def send_password_reset_email(settings: Settings, to_email: str, reset_link: str) -> None:
    subject = "Reset your FIR Automation password"
    text = (
        f"You requested a password reset.\n\nOpen this link to choose a new password (expires in 1 hour):\n{reset_link}\n\n"
        "If you did not request this, you can ignore this email."
    )

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

    # Envelope sender should match the authenticated SMTP user when set (Gmail/Workspace often reject or drop otherwise).
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
