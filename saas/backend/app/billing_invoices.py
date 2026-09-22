"""SaaS subscription invoices generated from verified billing_payments.

Does not change Payment Done / verify / reject. Invoice amounts come from the
payment row, not the client. GST split uses seller vs customer state codes from
billing_settings and companies.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.billing_payments import STATUS_VERIFIED, get_billing_payment, payment_code_for, serialize_billing_payment
from app.billing_period import period_label
from app.config import Settings, get_settings
from app.dates import billing_today
from app.models import BillingInvoice, BillingPayment, BillingSettings, Company

STATUS_GENERATED = "generated"
STATUS_CANCELLED = "cancelled"
TAX_CGST_SGST = "cgst_sgst"
TAX_IGST = "igst"

_MISSING_INVOICEABLE = "Invoice can only be generated after payment verification."
_DUPLICATE = "Invoice already generated for this payment."
# SAC for IT design and development / SaaS subscription (not configured on Billing Settings).
SAAS_SAC = "998314"


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rate(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _norm_state_code(raw: str | None) -> str:
    return "".join(ch for ch in (raw or "") if ch.isalnum()).upper()


def _blank(raw: str | None) -> bool:
    return not (raw or "").strip()


def get_billing_settings(db: Session) -> BillingSettings:
    row = db.get(BillingSettings, 1)
    if row:
        return row
    row = BillingSettings(id=1, invoice_prefix="INV-", cgst_rate=9, sgst_rate=9, igst_rate=18)
    db.add(row)
    db.flush()
    return row


def serialize_billing_settings(row: BillingSettings) -> dict[str, Any]:
    return {
        "business_name": row.business_name,
        "business_address": row.business_address,
        "gstin": row.gstin,
        "state": row.state,
        "state_code": row.state_code,
        "email": row.email,
        "phone": row.phone,
        "logo_path": row.logo_path,
        "invoice_prefix": row.invoice_prefix or "INV-",
        "cgst_rate": float(row.cgst_rate) if row.cgst_rate is not None else 9,
        "sgst_rate": float(row.sgst_rate) if row.sgst_rate is not None else 9,
        "igst_rate": float(row.igst_rate) if row.igst_rate is not None else 18,
        "terms_notes": row.terms_notes,
    }


def update_billing_settings(db: Session, body: dict[str, Any]) -> BillingSettings:
    row = get_billing_settings(db)
    allowed = {
        "business_name",
        "business_address",
        "gstin",
        "state",
        "state_code",
        "email",
        "phone",
        "logo_path",
        "invoice_prefix",
        "cgst_rate",
        "sgst_rate",
        "igst_rate",
        "terms_notes",
    }
    for key, val in body.items():
        if key not in allowed:
            continue
        if key == "invoice_prefix" and val:
            setattr(row, key, str(val).strip()[:16] or "INV-")
        elif key in {"cgst_rate", "sgst_rate", "igst_rate"} and val is not None:
            setattr(row, key, _rate(val))
        else:
            setattr(row, key, (str(val).strip() if isinstance(val, str) else val) or None)
    db.add(row)
    db.flush()
    return row


def generated_invoice_for_payment(db: Session, payment_id: int) -> BillingInvoice | None:
    return db.execute(
        select(BillingInvoice).where(
            BillingInvoice.payment_id == payment_id,
            BillingInvoice.status == STATUS_GENERATED,
        )
    ).scalar_one_or_none()


def invoice_counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(BillingInvoice.status, func.count(BillingInvoice.id)).group_by(BillingInvoice.status)).all()
    counts = {"generated": 0, "cancelled": 0, "draft": 0}
    for status_val, n in rows:
        key = (status_val or "").lower()
        if key in counts:
            counts[key] += int(n)
    counts["total"] = sum(counts.values())
    return counts


def list_billing_invoices(db: Session, *, status_filter: str | None = None, limit: int = 500) -> list[BillingInvoice]:
    q = select(BillingInvoice).options(
        selectinload(BillingInvoice.payment).selectinload(BillingPayment.company),
        selectinload(BillingInvoice.payment).selectinload(BillingPayment.user),
        selectinload(BillingInvoice.company),
    )
    if status_filter:
        want = status_filter.strip().lower()
        if want not in {STATUS_GENERATED, STATUS_CANCELLED}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invoice status")
        q = q.where(BillingInvoice.status == want)
    q = q.order_by(BillingInvoice.id.desc()).limit(limit)
    return list(db.execute(q).scalars().all())


def get_billing_invoice(db: Session, invoice_id: int) -> BillingInvoice:
    row = db.execute(
        select(BillingInvoice)
        .options(
            selectinload(BillingInvoice.payment).selectinload(BillingPayment.company).selectinload(Company.users),
            selectinload(BillingInvoice.payment).selectinload(BillingPayment.user),
            selectinload(BillingInvoice.company),
        )
        .where(BillingInvoice.id == invoice_id)
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return row


def _next_invoice_number(db: Session, prefix: str) -> str:
    prefix = (prefix or "INV-").strip() or "INV-"
    last = db.execute(select(func.max(BillingInvoice.id))).scalar_one()
    n = int(last or 0) + 1
    for _ in range(20):
        code = f"{prefix}{n:05d}"
        exists = db.execute(select(BillingInvoice.id).where(BillingInvoice.invoice_number == code)).scalar_one_or_none()
        if not exists:
            return code
        n += 1
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not allocate invoice number")


def _seller_gaps(settings: BillingSettings) -> list[str]:
    missing: list[str] = []
    if _blank(settings.business_name):
        missing.append("seller business name")
    if _blank(settings.business_address):
        missing.append("seller business address")
    if _blank(settings.gstin):
        missing.append("seller GSTIN")
    if _blank(settings.state) or _blank(settings.state_code):
        missing.append("seller state / state code")
    return missing


def _customer_gaps(company: Company | None) -> list[str]:
    if company is None:
        return ["customer company"]
    missing: list[str] = []
    if _blank(company.company_name):
        missing.append("customer company name")
    if _blank(company.billing_state) or _blank(company.billing_state_code):
        missing.append("customer billing state / state code")
    return missing


def compute_tax(*, taxable: Decimal, seller_state_code: str, customer_state_code: str, settings: BillingSettings) -> dict[str, Any]:
    cgst_rate = _rate(settings.cgst_rate)
    sgst_rate = _rate(settings.sgst_rate)
    igst_rate = _rate(settings.igst_rate)
    if _norm_state_code(seller_state_code) == _norm_state_code(customer_state_code):
        cgst = _money(taxable * cgst_rate / Decimal(100))
        sgst = _money(taxable * sgst_rate / Decimal(100))
        igst = _money(0)
        mode = TAX_CGST_SGST
    else:
        cgst = _money(0)
        sgst = _money(0)
        igst = _money(taxable * igst_rate / Decimal(100))
        mode = TAX_IGST
    total_tax = _money(cgst + sgst + igst)
    return {
        "tax_mode": mode,
        "cgst_rate": cgst_rate,
        "sgst_rate": sgst_rate,
        "igst_rate": igst_rate,
        "cgst": cgst,
        "sgst": sgst,
        "igst": igst,
        "total_tax": total_tax,
        "grand_total": _money(taxable + total_tax),
    }


def _line_description(payment: BillingPayment) -> str:
    module = payment.module_label or payment.module_key or "FIR"
    plan = payment.plan_name or "Plan"
    period = period_label(payment.billing_period or "MONTHLY")
    return f"{module} - {plan} Plan - {period} Subscription"


def preview_invoice(db: Session, *, payment_id: int) -> dict[str, Any]:
    payment = get_billing_payment(db, payment_id)
    st = payment.status if payment.status != "pending" else "pending_verification"
    if st != STATUS_VERIFIED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_MISSING_INVOICEABLE)
    existing = generated_invoice_for_payment(db, payment.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_DUPLICATE,
            headers={"X-Invoice-Id": str(existing.id)},
        )
    if payment.amount_inr is None or int(payment.amount_inr) <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payment amount is invalid")
    if payment.subscription_start_date is None or payment.subscription_end_date is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription dates are missing on this payment. Verify the payment first.",
        )
    if payment.subscription_end_date < payment.subscription_start_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Subscription dates are invalid")

    settings = get_billing_settings(db)
    company = payment.company
    missing = _seller_gaps(settings) + _customer_gaps(company)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot generate invoice. Missing: " + ", ".join(missing) + ".",
        )

    taxable = _money(payment.amount_inr)
    tax = compute_tax(
        taxable=taxable,
        seller_state_code=settings.state_code or "",
        customer_state_code=company.billing_state_code or "",
        settings=settings,
    )
    user = payment.user
    if user is None and company and company.users:
        user = sorted(company.users, key=lambda u: u.id)[0]
    period = payment.billing_period or "MONTHLY"
    invoice_date = billing_today()
    return {
        "payment_id": payment.id,
        "payment_code": payment.payment_code or payment_code_for(payment.id),
        "payment_method": payment.payment_method,
        "payment_reference": payment.reference_note or payment.payment_code,
        "payment_verified_at": payment.verified_at.isoformat() if payment.verified_at else None,
        "customer_name": payment.customer_name_snapshot or (user.name if user and user.name else None) or (company.company_name if company else None),
        "company_id": payment.company_id,
        "company_name": payment.company_name_snapshot or (company.company_name if company else None),
        "email": payment.email_snapshot or (user.email if user else None),
        "phone": company.phone if company else None,
        "billing_address": company.billing_address if company else None,
        "city": company.billing_city if company else None,
        "state": company.billing_state if company else None,
        "state_code": company.billing_state_code if company else None,
        "pincode": company.billing_pincode if company else None,
        "gstin": company.gstin if company else None,
        "module_key": payment.module_key,
        "module_name": payment.module_label or payment.module_key,
        "plan_name": payment.plan_name,
        "plan_id": (payment.pricing_snapshot or {}).get("catalog_id") if isinstance(payment.pricing_snapshot, dict) else None,
        "billing_period": period,
        "billing_period_label": period_label(period),
        "subscription_start_date": payment.subscription_start_date.isoformat(),
        "subscription_end_date": payment.subscription_end_date.isoformat(),
        "invoice_date": invoice_date.isoformat(),
        "line_description": _line_description(payment),
        "quantity": 1,
        "rate": float(taxable),
        "subtotal": float(taxable),
        "taxable_amount": float(taxable),
        "cgst": float(tax["cgst"]),
        "sgst": float(tax["sgst"]),
        "igst": float(tax["igst"]),
        "total_tax": float(tax["total_tax"]),
        "grand_total": float(tax["grand_total"]),
        "currency": payment.currency or "INR",
        "tax_mode": tax["tax_mode"],
        "cgst_rate": float(tax["cgst_rate"]),
        "sgst_rate": float(tax["sgst_rate"]),
        "igst_rate": float(tax["igst_rate"]),
        "seller": serialize_billing_settings(settings),
        "vendor_code": company.vendor_code if company else None,
        "hsn_sac": SAAS_SAC,
        "uom": "Nos",
    }


def generate_invoice(db: Session, *, payment_id: int, settings_app: Settings | None = None) -> BillingInvoice:
    preview = preview_invoice(db, payment_id=payment_id)
    payment = get_billing_payment(db, payment_id)
    settings = get_billing_settings(db)
    prefix = settings.invoice_prefix or "INV-"
    number = _next_invoice_number(db, prefix)
    invoice_date = date.fromisoformat(preview["invoice_date"])
    row = BillingInvoice(
        invoice_number=number,
        payment_id=payment.id,
        company_id=payment.company_id,
        user_id=payment.user_id,
        module_key=payment.module_key,
        module_name=preview["module_name"],
        plan_name=payment.plan_name,
        billing_period=payment.billing_period,
        invoice_date=invoice_date,
        subscription_start_date=payment.subscription_start_date,
        subscription_end_date=payment.subscription_end_date,
        subtotal=preview["subtotal"],
        taxable_amount=preview["taxable_amount"],
        cgst=preview["cgst"],
        sgst=preview["sgst"],
        igst=preview["igst"],
        total_tax=preview["total_tax"],
        grand_total=preview["grand_total"],
        currency=preview["currency"],
        tax_mode=preview["tax_mode"],
        cgst_rate=preview["cgst_rate"],
        sgst_rate=preview["sgst_rate"],
        igst_rate=preview["igst_rate"],
        status=STATUS_GENERATED,
        line_description=preview["line_description"],
        snapshot=preview,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        existing = generated_invoice_for_payment(db, payment_id)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_DUPLICATE) from exc
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Invoice number already used") from exc

    pdf_bytes = render_invoice_pdf(serialize_billing_invoice(row, db=db))
    row.pdf_path = _store_pdf(row, pdf_bytes, settings_app or get_settings())
    db.add(row)
    db.flush()
    return row


def _store_pdf(row: BillingInvoice, pdf_bytes: bytes, app_settings: Settings) -> str | None:
    year = row.invoice_date.year if row.invoice_date else billing_today().year
    key = f"invoices/{year}/{row.invoice_number}.pdf"
    try:
        from app.s3_assets import s3_assets_configured, _s3_client

        if s3_assets_configured(app_settings) and app_settings.s3_bucket_name:
            client = _s3_client(app_settings)
            client.put_object(
                Bucket=app_settings.s3_bucket_name,
                Key=key,
                Body=pdf_bytes,
                ContentType="application/pdf",
            )
            return key
    except Exception:
        return key
    return key


def serialize_billing_invoice(row: BillingInvoice, *, db: Session | None = None) -> dict[str, Any]:
    snap = row.snapshot if isinstance(row.snapshot, dict) else {}
    payment = row.payment
    company = row.company or (payment.company if payment else None)
    pay = serialize_billing_payment(payment) if payment else {}
    return {
        "id": row.id,
        "invoice_id": row.invoice_number,
        "invoice_number": row.invoice_number,
        "payment_id": row.payment_id,
        "payment_code": pay.get("payment_code") or (payment_code_for(row.payment_id) if row.payment_id else None),
        "customer_id": pay.get("customer_id") or row.user_id,
        "company_id": row.company_id,
        "user_id": row.user_id,
        "module_id": snap.get("plan_id"),
        "module_key": row.module_key,
        "module_name": row.module_name,
        "plan_id": snap.get("plan_id"),
        "plan_name": row.plan_name,
        "billing_period": row.billing_period,
        "billing_period_label": period_label(row.billing_period or "MONTHLY"),
        "invoice_date": row.invoice_date.isoformat() if row.invoice_date else None,
        "subscription_start_date": row.subscription_start_date.isoformat() if row.subscription_start_date else None,
        "subscription_end_date": row.subscription_end_date.isoformat() if row.subscription_end_date else None,
        "subtotal": float(row.subtotal),
        "taxable_amount": float(row.taxable_amount),
        "cgst": float(row.cgst),
        "sgst": float(row.sgst),
        "igst": float(row.igst),
        "total_tax": float(row.total_tax),
        "grand_total": float(row.grand_total),
        "currency": row.currency,
        "tax_mode": row.tax_mode,
        "cgst_rate": float(row.cgst_rate) if row.cgst_rate is not None else None,
        "sgst_rate": float(row.sgst_rate) if row.sgst_rate is not None else None,
        "igst_rate": float(row.igst_rate) if row.igst_rate is not None else None,
        "status": row.status,
        "pdf_path": row.pdf_path,
        "line_description": row.line_description,
        "customer_name": snap.get("customer_name") or pay.get("customer_name"),
        "company_name": snap.get("company_name") or (company.company_name if company else None),
        "email": snap.get("email") or pay.get("email"),
        "phone": snap.get("phone") or pay.get("phone"),
        "billing_address": snap.get("billing_address"),
        "city": snap.get("city"),
        "state": snap.get("state"),
        "state_code": snap.get("state_code"),
        "pincode": snap.get("pincode"),
        "gstin": snap.get("gstin"),
        "payment_method": snap.get("payment_method") or pay.get("payment_method"),
        "payment_reference": snap.get("payment_reference") or pay.get("reference_note"),
        "payment_verified_at": snap.get("payment_verified_at") or pay.get("payment_verified_at"),
        "seller": snap.get("seller"),
        "quantity": snap.get("quantity") or 1,
        "rate": snap.get("rate") if snap.get("rate") is not None else float(row.subtotal),
        "terms_notes": (snap.get("seller") or {}).get("terms_notes") if isinstance(snap.get("seller"), dict) else None,
        "vendor_code": snap.get("vendor_code") or (company.vendor_code if company else None),
        "hsn_sac": snap.get("hsn_sac") or SAAS_SAC,
        "uom": snap.get("uom") or "Nos",
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


_ONES = (
    "",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
)
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")


def _pdf_text(value: Any) -> str:
    s = str(value or "")
    return (
        s.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("₹", "Rs. ")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def _display_date(raw: Any) -> str:
    if raw is None or raw == "":
        return ""
    text = str(raw)
    try:
        d = date.fromisoformat(text[:10])
        return d.strftime("%d-%b-%y")
    except ValueError:
        return text[:12]


def _indian_comma(value: Any) -> str:
    n = _money(value or 0)
    sign = "-" if n < 0 else ""
    n = abs(n)
    rupees, paise = f"{n:.2f}".split(".")
    if len(rupees) <= 3:
        body = rupees
    else:
        last3 = rupees[-3:]
        rest = rupees[:-3]
        groups: list[str] = []
        while rest:
            groups.append(rest[-2:])
            rest = rest[:-2]
        body = ",".join([*reversed(groups), last3])
    return f"{sign}{body}.{paise}"


def _two_digit_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return f"{_TENS[tens]} {_ONES[ones]}".strip()


def _amount_in_words(value: Any) -> str:
    n = _money(value or 0)
    rupees = int(n)
    paise = int((n - rupees) * 100)
    if rupees == 0:
        words = "Zero"
    else:
        crore, rem = divmod(rupees, 10000000)
        lakh, rem = divmod(rem, 100000)
        thousand, rem = divmod(rem, 1000)
        hundred, rem = divmod(rem, 100)
        parts: list[str] = []
        if crore:
            parts.append(f"{_two_digit_words(crore)} Crore")
        if lakh:
            parts.append(f"{_two_digit_words(lakh)} Lakh")
        if thousand:
            parts.append(f"{_two_digit_words(thousand)} Thousand")
        if hundred:
            parts.append(f"{_ONES[hundred]} Hundred")
        if rem:
            parts.append(_two_digit_words(rem))
        words = " ".join(parts)
    result = f"Indian Rupees {words}"
    if paise:
        result += f" and {_two_digit_words(paise)} Paise"
    return result + " Only"


def _inr(value: Any) -> str:
    return _indian_comma(value)


def _party_lines(data: dict[str, Any], *, seller: bool = False) -> list[str]:
    if seller:
        s = data.get("seller") or {}
        name = s.get("business_name") or "TheAIQualisys"
        legal = (s.get("legal_business_name") or "").strip()
        addr = s.get("business_address") or ", ".join(
            p for p in (s.get("address_line1"), s.get("address_line2"), s.get("city"), s.get("pincode")) if p
        )
        lines = [name]
        if legal and legal != name:
            lines.append(legal)
        if addr:
            lines.append(str(addr))
        lines.append(f"GSTIN/UIN: {s.get('gstin') or '-'}")
        lines.append(f"State Name : {s.get('state') or '-'} , Code : {s.get('state_code') or '-'}")
        if s.get("email") or s.get("phone"):
            lines.append(f"E-Mail : {s.get('email') or '-'}  Ph: {s.get('phone') or '-'}")
        return [str(x) for x in lines if x]
    name = data.get("company_name") or data.get("customer_name") or ""
    addr_bits = [data.get("billing_address"), data.get("city"), data.get("pincode")]
    lines = [name]
    addr = ", ".join(str(p) for p in addr_bits if p)
    if addr:
        lines.append(addr)
    lines.append(f"GSTIN/UIN : {data.get('gstin') or '-'}")
    lines.append(f"State Name : {data.get('state') or '-'} , Code : {data.get('state_code') or '-'}")
    return [str(x) for x in lines if x]


def render_invoice_pdf(data: dict[str, Any]) -> bytes:
    """Tally-style GST tax invoice. Selectable Helvetica text. No IRN/e-invoice QR."""
    from fpdf import FPDF

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=False, margin=8)
    pdf.add_page()
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.2)

    x0, y0 = 8.0, 8.0
    w = 194.0
    x1 = x0 + w
    mid = x0 + 108.0

    def put(x: float, y: float, cw: float, ch: float, text: str, *, bold: bool = False, size: int = 7, align: str = "L") -> None:
        pdf.set_xy(x, y)
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.cell(cw, ch, _pdf_text(text), align=align)

    def wrap(x: float, y: float, cw: float, text: str, *, bold: bool = False, size: int = 7, lh: float = 3.4) -> float:
        pdf.set_xy(x, y)
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.multi_cell(cw, lh, _pdf_text(text))
        return float(pdf.get_y())

    seller = data.get("seller") if isinstance(data.get("seller"), dict) else {}
    mode = data.get("tax_mode")
    hsn = str(data.get("hsn_sac") or SAAS_SAC)
    qty = str(data.get("quantity") or 1)
    uom = str(data.get("uom") or "Nos")
    inv_no = str(data.get("invoice_number") or "")
    inv_dt = _display_date(data.get("invoice_date"))
    pay_ref = str(data.get("payment_code") or data.get("payment_reference") or "")
    pay_method = str(data.get("payment_method") or "UPI")
    vendor = str(data.get("vendor_code") or "")
    start = _display_date(data.get("subscription_start_date"))
    end = _display_date(data.get("subscription_end_date"))
    period = str(data.get("billing_period_label") or data.get("billing_period") or "")
    terms = f"{period}  {start} to {end}".strip()

    # Outer title
    pdf.rect(x0, y0, w, 8)
    put(x0, y0 + 1.5, w, 5, "TAX INVOICE", bold=True, size=12, align="C")

    header_y = y0 + 8
    header_h = 42
    pdf.rect(x0, header_y, mid - x0, header_h)
    pdf.rect(mid, header_y, x1 - mid, header_h)

    sy = header_y + 1.5
    for i, line in enumerate(_party_lines(data, seller=True)):
        sy = wrap(x0 + 1.5, sy, mid - x0 - 3, line, bold=i == 0, size=9 if i == 0 else 7, lh=3.6)
        if sy > header_y + header_h - 2:
            break

    meta_rows = [
        ("Invoice No.", inv_no, "Dated", inv_dt),
        ("Delivery Note", "", "Mode/Terms of Payment", pay_method),
        ("Reference No. & Date.", pay_ref, "Other References", ""),
        ("Buyer's Order No.", "", "Dated", ""),
        ("Dispatch Doc No.", "", "Delivery Note Date", ""),
        ("Dispatched through", "", "Destination", ""),
        ("Supplier / Vendor Code", vendor, "Terms of Delivery", terms),
    ]
    rh = header_h / len(meta_rows)
    mw = x1 - mid
    col = mw / 2
    for i, (l1, v1, l2, v2) in enumerate(meta_rows):
        y = header_y + i * rh
        pdf.line(mid, y, x1, y)
        pdf.line(mid + col, y, mid + col, y + rh)
        put(mid + 0.6, y + 0.2, col - 1.2, 3, l1, size=5.5)
        put(mid + 0.6, y + 2.6, col - 1.2, 3, v1, bold=True, size=6.5)
        put(mid + col + 0.6, y + 0.2, col - 1.2, 3, l2, size=5.5)
        put(mid + col + 0.6, y + 2.6, col - 1.2, 3, v2, bold=True, size=6.5)
    pdf.line(mid, header_y + header_h, x1, header_y + header_h)

    party_y = header_y + header_h
    party_h = 32
    split = x0 + w / 2
    pdf.rect(x0, party_y, split - x0, party_h)
    pdf.rect(split, party_y, x1 - split, party_h)
    put(x0 + 1.5, party_y + 0.5, split - x0 - 3, 4, "Consignee (Ship to)", bold=True, size=7)
    put(split + 1.5, party_y + 0.5, x1 - split - 3, 4, "Buyer (Bill to)", bold=True, size=7)
    by = party_y + 5
    wrap_y = by
    for i, line in enumerate(_party_lines(data, seller=False)):
        wrap_y = wrap(x0 + 1.5, wrap_y, split - x0 - 3, line, bold=i == 0, size=8 if i == 0 else 7, lh=3.4)
    wrap_y = by
    for i, line in enumerate(_party_lines(data, seller=False)):
        wrap_y = wrap(split + 1.5, wrap_y, x1 - split - 3, line, bold=i == 0, size=8 if i == 0 else 7, lh=3.4)

    # Line items
    cols = [8, 78, 22, 16, 22, 14, 34]
    headers = ["SI", "Description of Services", "HSN/SAC", "Quantity", "Rate", "per", "Amount"]
    ty = party_y + party_h
    th = 7
    pdf.rect(x0, ty, w, th)
    cx = x0
    for i, (cw, label) in enumerate(zip(cols, headers, strict=True)):
        if i:
            pdf.line(cx, ty, cx, ty + th)
        put(cx, ty + 1.5, cw, 4, label, bold=True, size=6.5, align="C")
        cx += cw

    row_h = 10
    iy = ty + th
    pdf.rect(x0, iy, w, row_h)
    desc = str(data.get("line_description") or "")
    vals = [
        "1",
        desc,
        hsn,
        f"{qty} {uom}",
        _indian_comma(data.get("rate")),
        uom,
        _indian_comma(data.get("taxable_amount")),
    ]
    aligns = ["C", "L", "C", "C", "R", "C", "R"]
    cx = x0
    for i, (cw, val, al) in enumerate(zip(cols, vals, aligns, strict=True)):
        if i:
            pdf.line(cx, iy, cx, iy + row_h)
        pad = 0.8 if al != "C" else 0
        put(cx + pad, iy + 2.5, cw - pad * 2, 5, val, size=7, align=al)
        cx += cw

    tax_rows: list[tuple[str, str]] = []
    if mode == TAX_CGST_SGST:
        tax_rows.append((f"CGST @ {data.get('cgst_rate')}%", _indian_comma(data.get("cgst"))))
        tax_rows.append((f"SGST @ {data.get('sgst_rate')}%", _indian_comma(data.get("sgst"))))
    else:
        tax_rows.append((f"IGST @ {data.get('igst_rate')}%", _indian_comma(data.get("igst"))))

    gy = iy + row_h
    for label, amt in tax_rows:
        pdf.rect(x0, gy, w, 6)
        cx = x0
        for i, cw in enumerate(cols):
            if i:
                pdf.line(cx, gy, cx, gy + 6)
            if i == 1:
                put(cx + 8, gy + 1, cw - 10, 4, label, size=7, align="R")
            if i == 6:
                put(cx, gy + 1, cw - 1, 4, amt, size=7, align="R")
            cx += cw
        gy += 6

    pdf.rect(x0, gy, w, 7)
    cx = x0
    for i, cw in enumerate(cols):
        if i:
            pdf.line(cx, gy, cx, gy + 7)
        if i == 1:
            put(cx + 1, gy + 1.5, cw - 2, 4, "Total", bold=True, size=8)
        if i == 3:
            put(cx, gy + 1.5, cw, 4, f"{qty} {uom}", bold=True, size=7, align="C")
        if i == 6:
            put(cx, gy + 1.5, cw - 1, 4, _indian_comma(data.get("grand_total")), bold=True, size=8, align="R")
        cx += cw

    words_y = gy + 7
    pdf.rect(x0, words_y, w, 10)
    put(x0 + 1.5, words_y + 0.5, w - 40, 4, "Amount Chargeable (in words)", size=6)
    put(x0 + w - 22, words_y + 0.5, 20, 4, "E. & O.E", size=6, align="R")
    put(x0 + 1.5, words_y + 4.5, w - 4, 5, _amount_in_words(data.get("grand_total")), bold=True, size=8)

    # HSN tax summary
    hy = words_y + 10
    if mode == TAX_CGST_SGST:
        tax_headers = ["HSN/SAC", "Taxable Value", "CGST Rate", "CGST Amount", "SGST Rate", "SGST Amount", "Total Tax Amount"]
        tax_vals = [
            hsn,
            _indian_comma(data.get("taxable_amount")),
            f"{data.get('cgst_rate')}%",
            _indian_comma(data.get("cgst")),
            f"{data.get('sgst_rate')}%",
            _indian_comma(data.get("sgst")),
            _indian_comma(data.get("total_tax")),
        ]
        tcols = [28, 30, 22, 28, 22, 28, 36]
    else:
        tax_headers = ["HSN/SAC", "Taxable Value", "IGST Rate", "IGST Amount", "Total Tax Amount"]
        tax_vals = [
            hsn,
            _indian_comma(data.get("taxable_amount")),
            f"{data.get('igst_rate')}%",
            _indian_comma(data.get("igst")),
            _indian_comma(data.get("total_tax")),
        ]
        tcols = [36, 40, 28, 40, 50]
    pdf.rect(x0, hy, w, 6)
    cx = x0
    for i, (cw, label) in enumerate(zip(tcols, tax_headers, strict=True)):
        if i:
            pdf.line(cx, hy, cx, hy + 6)
        put(cx, hy + 1.2, cw, 4, label, bold=True, size=6, align="C")
        cx += cw
    hy2 = hy + 6
    pdf.rect(x0, hy2, w, 6)
    cx = x0
    for i, (cw, val) in enumerate(zip(tcols, tax_vals, strict=True)):
        if i:
            pdf.line(cx, hy2, cx, hy2 + 6)
        put(cx, hy2 + 1.2, cw, 4, val, size=7, align="C")
        cx += cw
    hy3 = hy2 + 6
    pdf.rect(x0, hy3, w, 6)
    put(x0 + 1, hy3 + 1.2, 40, 4, "Total", bold=True, size=7)
    put(x1 - 38, hy3 + 1.2, 36, 4, _indian_comma(data.get("total_tax")), bold=True, size=7, align="C")

    tw = hy3 + 6
    pdf.rect(x0, tw, w, 8)
    put(x0 + 1.5, tw + 0.4, w - 3, 3.5, "Tax Amount (in words) :", size=6)
    put(x0 + 1.5, tw + 3.6, w - 3, 4, _amount_in_words(data.get("total_tax")), bold=True, size=7)
    pan = (seller or {}).get("pan") if isinstance(seller, dict) else None
    if pan:
        put(x0 + 1.5, tw + 8.2, w - 3, 4, f"Company's PAN : {pan}", size=7)

    foot = tw + (14 if pan else 8)
    split_f = x0 + 100
    fh = 36
    pdf.rect(x0, foot, split_f - x0, fh)
    pdf.rect(split_f, foot, x1 - split_f, fh)
    put(x0 + 1.5, foot + 1, 90, 4, "Declaration", bold=True, size=7)
    wrap(
        x0 + 1.5,
        foot + 5.5,
        split_f - x0 - 3,
        "We declare that this invoice shows the actual price of the "
        "services described and that all particulars are true and correct.",
        size=6.5,
        lh=3.3,
    )
    put(x0 + 1.5, foot + fh - 8, 90, 4, "Customer's Seal and Signature", size=6.5)
    seller_name = (seller or {}).get("business_name") or "TheAIQualisys"
    put(split_f + 1.5, foot + 1, x1 - split_f - 3, 4, f"for {seller_name}", bold=True, size=7, align="R")
    put(split_f + 1.5, foot + fh - 8, x1 - split_f - 3, 4, "Authorised Signatory", size=6.5, align="R")

    notes = data.get("terms_notes") or ((seller or {}).get("terms_notes") if isinstance(seller, dict) else None)
    if notes:
        wrap(x0, foot + fh + 1, w, str(notes), size=6, lh=3)

    city = (seller or {}).get("city") or (seller or {}).get("state") or ""
    if city:
        put(x0, 285, w, 4, f"SUBJECT TO {str(city).upper()} JURISDICTION", bold=True, size=7, align="C")
    return bytes(pdf.output())
