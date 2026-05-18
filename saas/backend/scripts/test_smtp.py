#!/usr/bin/env python3
"""
Send a one-off test message using the same SMTP settings as the API.

Run from the backend directory with the same env vars as production (or a .env file):

  cd saas/backend
  python3 scripts/test_smtp.py recipient@example.com

If this fails, fix SMTP_USER / SMTP_PASSWORD (Google App Password),
EMAIL_FROM alignment, or host firewall before debugging the forgot-password route.
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
    parser = argparse.ArgumentParser(description="Test SMTP using app Settings")
    parser.add_argument("to_email", help="Address to receive the test mail")
    args = parser.parse_args()

    get_settings.cache_clear()
    settings = get_settings()
    if not is_email_configured(settings):
        print("SMTP is not configured (need EMAIL_FROM, SMTP_HOST, SMTP_PORT).", file=sys.stderr)
        sys.exit(1)

    link = "https://example.com/reset-password?token=diagnostic-not-real"
    print(f"Host={settings.smtp_host!r} port={settings.smtp_port} tls={settings.smtp_use_tls} ssl={settings.smtp_use_ssl}")
    print(f"From={settings.email_from!r} user={settings.smtp_user!r} to={args.to_email!r}")
    send_password_reset_email(settings, args.to_email.strip(), link)
    print("Send finished without exception (check inbox and spam).")


if __name__ == "__main__":
    main()
