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
from typing import Literal

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
        "Team,\n"
        "TheAIQualisys\n"
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
    <p style="margin:16px 0 4px;">Team,<br />TheAIQualisys</p>
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


ADMIN_MANUAL_SUBSCRIPTION_ENDING_SUBJECT = "Your TheAiQualisys Subscription is Ending Soon"
ADMIN_MANUAL_SUBSCRIPTION_EXPIRED_SUBJECT = "Your TheAiQualisys Subscription Has Expired"


def build_admin_manual_subscription_reminder_email(
    *,
    reminder_type: str,
    customer_name: str,
    plan_name: str,
    end_date_display: str,
    current_month_name: str,
    current_month_report_count: int,
    total_report_count: int,
    renewal_link: str,
) -> tuple[str, str]:
    """Plain-text subject + body for platform-admin manual subscription reminders."""
    if reminder_type == "ending_soon":
        subject = ADMIN_MANUAL_SUBSCRIPTION_ENDING_SUBJECT
        text = (
            f"Dear {customer_name},\n\n"
            f"Your subscription for the {plan_name} plan is scheduled to expire on {end_date_display}.\n\n"
            f"In {current_month_name}, you have generated **{current_month_report_count} inspection reports** using TheAiQualisys.\n\n"
            "This month, TheAiQualisys has helped your team simplify inspection report generation by automating repetitive work, "
            "reducing manual effort, improving accuracy, and saving valuable time in your quality process.\n\n"
            "To continue generating reports without interruption and maintain the efficiency you have achieved, please renew "
            "your subscription before the expiry date.\n\n"
            f"Renew your subscription here: {renewal_link}\n\n"
            "Thank you for trusting TheAiQualisys to streamline your inspection and reporting workflow.\n\n"
            "Team,\n"
            "TheAiQualisys"
        )
        return subject, text
    if reminder_type == "already_ended":
        subject = ADMIN_MANUAL_SUBSCRIPTION_EXPIRED_SUBJECT
        text = (
            f"Dear {customer_name},\n\n"
            f"Your subscription for the {plan_name} plan expired on {end_date_display}.\n\n"
            f"In {current_month_name}, you generated **{current_month_report_count} inspection reports**.\n\n"
            f"Since you started using TheAiQualisys, you have generated a total of **{total_report_count} inspection reports**.\n\n"
            "Throughout your subscription, TheAiQualisys helped automate report generation, reduce repetitive manual work, "
            "improve consistency, and save significant time for your quality and production teams.\n\n"
            "Your access to automated report generation is currently inactive. Renew your subscription to restore full access "
            "and continue generating reports efficiently.\n\n"
            f"Renew your subscription here: {renewal_link}\n\n"
            "Thank you for being a valued customer of TheAiQualisys.\n\n"
            "Team,\n"
            "TheAiQualisys"
        )
        return subject, text
    raise ValueError(f"Unknown reminder_type: {reminder_type!r}")


THANK_YOU_PERFORMANCE_SUBJECT = "Thank You for Using TheAiQualisys – Your Performance Summary"
DEFAULT_MINUTES_PER_MANUAL_REPORT = 15

ThankYouEmailSingleCategory = Literal["running", "regular", "occasional", "stranger", "new"]

THANK_YOU_ALL_CATEGORY_SUBJECT = "Thank You & Performance Summary"
THANK_YOU_ALL_MINUTES_PER_REPORT = 10
THANK_YOU_ALL_INR_PER_MANUAL_HOUR = 500


def _thank_you_time_saved_totals(
    total_report_count: int, *, minutes_per_report: int = DEFAULT_MINUTES_PER_MANUAL_REPORT
) -> tuple[float, float]:
    total_minutes = total_report_count * minutes_per_report
    total_time_saved_hours = round(total_minutes / 60.0, 1)
    working_days_saved = round(total_time_saved_hours / 8.0, 1)
    return total_time_saved_hours, working_days_saved


def _thank_you_tone_copy(category: ThankYouEmailSingleCategory) -> tuple[str, str]:
    """Closing tone after Estimated Time Saved (category-specific)."""
    if category == "running":
        after_saved = (
            "The figures above summarize your cumulative impact, your most-run parts, and the time your teams have "
            "gained back — all of it made possible by your continued partnership. "
            "We are grateful for the collaboration and look forward to helping you keep this momentum going."
        )
        penultimate = (
            "Thank you again for choosing TheAiQualisys — we value this partnership and are here whenever you need us."
        )
        return after_saved, penultimate

    if category == "regular":
        after_saved = (
            "These lifetime figures illustrate the steady value your organization has captured with the platform — "
            "reliable throughput, clearer documentation, and less manual repetition in inspection reporting. "
            "We appreciate the continuity you bring to the partnership."
        )
        penultimate = "Thank you for your continued trust; we are glad to be part of your day-to-day operations."
        return after_saved, penultimate

    if category == "occasional":
        after_saved = (
            "The totals above reflect everything your team has achieved to date with TheAiQualisys. Many organizations find that leaning on "
            "FIR automation more consistently multiplies these gains: faster turnaround on audits, fewer surprises before "
            "customer visits, and less time lost to re-keying data."
        )
        penultimate = (
            "Whenever you are ready to expand usage, we are here to help you get even more from the same workflow."
        )
        return after_saved, penultimate

    if category == "stranger":
        after_saved = (
            "The metrics above reflect the impact your organization has already seen with TheAiQualisys. If priorities have "
            "shifted, that is understandable — when you are ready to reconnect, the same time savings, consistency, and "
            "audit-ready documentation will be waiting."
        )
        penultimate = (
            "We would welcome the chance to support you again; please reach out if you would like a quick refresher "
            "or a walkthrough of what is new."
        )
        return after_saved, penultimate

    if category == "new":
        after_saved = (
            "The usage snapshot below is based on everything recorded to date. As you scale up, you can expect the same "
            "standardized outputs, fewer errors from manual entry, and more time back for engineering and shop-floor "
            "quality work."
        )
        penultimate = (
            "Thank you for joining us — our team is here if you have questions as you ramp up."
        )
        return after_saved, penultimate

    raise ValueError(f"Unknown thank-you category: {category!r}")


def _thank_you_shared_opening(total_report_count: int) -> str:
    return (
        "Thank you for choosing TheAiQualisys as your partner in automating inspection report generation.\n\n"
        f"Till date, your organization has generated **{total_report_count} inspection reports** using TheAiQualisys.\n\n"
        "By automating repetitive report preparation tasks, TheAiQualisys has helped reduce manual effort, improve "
        "reporting accuracy, and save significant time for your quality and manufacturing teams."
    )


def _format_thank_you_top_parts_mysql_table(
    top_parts: list[tuple[str, int, str, str]],
    *,
    max_part_no_width: int = 24,
) -> str:
    """Box-drawn plain-text table similar to the MySQL client ASCII output."""
    headers = ["Rank", "Part Number", "Reports Generated", "Median Gap (Days)", "Last Dispatched Date"]

    def prep_part_no(pn: str) -> str:
        if len(pn) <= max_part_no_width:
            return pn
        return pn[: max_part_no_width - 1] + "…"

    data_rows: list[list[str]] = []
    for i, (pn, cn, gap_lbl, last_lbl) in enumerate(top_parts, start=1):
        data_rows.append([str(i), prep_part_no(str(pn)), str(cn), str(gap_lbl), str(last_lbl)])

    widths: list[int] = [len(h) for h in headers]
    for row in data_rows:
        for col, cell in enumerate(row):
            widths[col] = max(widths[col], len(cell))

    def horizontal_rule() -> str:
        return "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def fmt_row(cells: list[str]) -> str:
        segs = [" " + cells[i].ljust(widths[i]) + " " for i in range(len(cells))]
        return "|" + "|".join(segs) + "|"

    lines = [horizontal_rule(), fmt_row(headers), horizontal_rule()]
    for row in data_rows:
        lines.append(fmt_row(row))
    lines.append(horizontal_rule())
    return "\n".join(lines)


def build_admin_thank_you_all_email(
    *,
    customer_name: str,
    total_report_count: int,
    top_parts_overall: list[tuple[str, int, str, str]],
    engagement_sections: list[tuple[str, int, int, list[tuple[str, int, str, str]]]],
) -> tuple[str, str, float]:
    """Combined thank-you for ``thank_you_category == \"all\"`` (lifetime + per-engagement Top 5 tables).

    Each engagement tuple is ``(section_title, fir_report_row_count, fir_row_count, top_5_table_rows)``.
    Row counts match ``fir_events`` usage elsewhere (one row per ingested invoice line).
    Time saved uses :data:`THANK_YOU_ALL_MINUTES_PER_REPORT`; cost uses INR per hour constant.
    """
    if len(top_parts_overall) != 5:
        raise ValueError("top_parts_overall must contain exactly 5 rows")
    for _t, _rc, _rr, rows in engagement_sections:
        if len(rows) != 5:
            raise ValueError("each engagement section must have exactly 5 top_parts rows")

    greeting = f"Dear {customer_name},"
    total_minutes_saved = total_report_count * THANK_YOU_ALL_MINUTES_PER_REPORT
    hours_saved = total_minutes_saved / 60.0
    hours_saved_rounded = round(hours_saved, 1)
    cost_saved = hours_saved * THANK_YOU_ALL_INR_PER_MANUAL_HOUR

    overall_table = _format_thank_you_top_parts_mysql_table(top_parts_overall)

    section_blocks: list[str] = []
    for title, report_count, row_count, top_rows in engagement_sections:
        if report_count <= 0:
            continue
        table_block = _format_thank_you_top_parts_mysql_table(top_rows)
        section_blocks.append(
            f"{title}\n"
            f"- FIR Reports Generated: {report_count}\n"
            f"- FIR Report Rows Processed: {row_count}\n\n"
            f"Top 5 Parts\n"
            f"{table_block}"
        )

    all_sections = "\n\n".join(section_blocks)

    text = (
        f"{greeting}\n\n"
        "Thank you for partnering with TheAiQualisys.\n\n"
        "Below is your complete performance summary based on all reports generated till date.\n\n"
        "📊 Lifetime Metrics\n"
        f"- Total FIR Reports Generated: {total_report_count}\n"
        f"- Total FIR Report Rows Processed: {total_report_count}\n"
        f"- Estimated Manual Time Saved: {hours_saved_rounded:.1f} hours\n"
        f"- Estimated Cost Saved: ₹{cost_saved:,.0f}\n\n"
        "🏆 Overall Top 5 Most Frequently Generated Parts\n"
        f"{overall_table}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📂 Customer Engagement Category Summaries\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{all_sections}\n\n"
        "Thank you for your continued trust and support.\n\n"
        "Team,\n"
        "TheAiQualisys"
    )
    return THANK_YOU_ALL_CATEGORY_SUBJECT, text, hours_saved_rounded


def build_admin_thank_you_email(
    *,
    category: ThankYouEmailSingleCategory,
    customer_name: str,
    plan_name: str,
    subscription_start_date: str,
    subscription_end_date: str,
    total_report_count: int,
    workspace_user_count: int,
    top_parts: list[tuple[str, int, str, str]],
    minutes_per_report: int = DEFAULT_MINUTES_PER_MANUAL_REPORT,
) -> tuple[str, str, float, float]:
    """Thank-you + lifetime usage summary (plain text). Returns subject, body, hours_saved, days_saved.

    ``top_parts`` rows: (part_no, count, median_gap_label, last_dispatched_label).
    """
    if len(top_parts) != 5:
        raise ValueError("top_parts must contain exactly 5 rows")

    total_time_saved_hours, working_days_saved = _thank_you_time_saved_totals(
        total_report_count, minutes_per_report=minutes_per_report
    )

    table_block = _format_thank_you_top_parts_mysql_table(top_parts)
    shared_opening = _thank_you_shared_opening(total_report_count)
    after_saved, penultimate = _thank_you_tone_copy(category)

    subject = THANK_YOU_PERFORMANCE_SUBJECT
    text = (
        f"Dear {customer_name},\n\n"
        f"{shared_opening}\n\n"
        "## Your Usage Summary\n\n"
        f"* Current Plan: {plan_name}\n"
        f"* Subscription Start Date: {subscription_start_date}\n"
        f"* Subscription End Date: {subscription_end_date}\n"
        f"* Total Reports Generated Till Date: **{total_report_count}**\n"
        f"* Total Active Users in Workspace: **{workspace_user_count}**\n\n"
        "## Top 5 Most Frequently Generated Parts Till Date\n\n"
        f"{table_block}\n\n"
        "## Estimated Time Saved\n\n"
        f"Assuming each inspection report takes approximately {minutes_per_report} minutes to prepare manually:\n\n"
        f"* Total Estimated Time Saved: **{total_time_saved_hours} hours**\n"
        f"* Equivalent Working Days Saved: **{working_days_saved} days**\n\n"
        f"{after_saved}\n\n"
        f"{penultimate}\n\n"
        "Warm regards,\n\n"
        "Team,\n"
        "TheAiQualisys"
    )
    return subject, text, total_time_saved_hours, working_days_saved


def build_admin_thank_you_performance_email(
    *,
    customer_name: str,
    plan_name: str,
    subscription_start_date: str,
    subscription_end_date: str,
    current_month_name: str,
    current_month_report_count: int,
    total_report_count: int,
    workspace_user_count: int,
    top_parts: list[tuple[str, int, str, str]],
    minutes_per_report: int = DEFAULT_MINUTES_PER_MANUAL_REPORT,
) -> tuple[str, str]:
    """Deprecated: use ``build_admin_thank_you_email``. Kept for tests."""
    _ = (current_month_name, current_month_report_count)
    s, t, _h, _d = build_admin_thank_you_email(
        category="running",
        customer_name=customer_name,
        plan_name=plan_name,
        subscription_start_date=subscription_start_date,
        subscription_end_date=subscription_end_date,
        total_report_count=total_report_count,
        workspace_user_count=workspace_user_count,
        top_parts=top_parts,
        minutes_per_report=minutes_per_report,
    )
    return s, t
