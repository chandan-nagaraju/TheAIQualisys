#!/usr/bin/env python3
"""
Send a one-off test message using the same settings as the API (SMTP or Resend).

Run from the backend directory with the same env vars as production (or a .env file):

  cd saas/backend
  python3 scripts/test_smtp.py recipient@example.com

If SMTP times out (Railway often blocks port 587), set RESEND_API_KEY and verify EMAIL_FROM at resend.com.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_backend_root = Path(__file__).resolve().parents[1]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from app.config import get_settings  # noqa: E402
from app.email_util import is_email_configured, send_password_reset_email  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Test password-reset email (SMTP or Resend)")
    parser.add_argument("to_email", help="Address to receive the test mail")
    args = parser.parse_args()

    get_settings.cache_clear()
    settings = get_settings()
    if not is_email_configured(settings):
        print("Email not configured: need EMAIL_FROM and (RESEND_API_KEY or SMTP_HOST+SMTP_PORT).", file=sys.stderr)
        sys.exit(1)

    link = "https://example.com/reset-password?token=diagnostic-not-real"
    if settings.resend_api_key:
        print(f"Using Resend API. From={settings.email_from!r} to={args.to_email!r}")
    else:
        print(
            f"Using SMTP. Host={settings.smtp_host!r} port={settings.smtp_port} tls={settings.smtp_use_tls} "
            f"ssl={settings.smtp_use_ssl} force_ipv4={settings.smtp_force_ipv4}"
        )
        print(f"From={settings.email_from!r} user={settings.smtp_user!r}")
    send_password_reset_email(settings, args.to_email.strip(), link)
    print("Send finished without exception (check inbox and spam).")


if __name__ == "__main__":
    main()
