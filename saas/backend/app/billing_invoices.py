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
_SELLER_INCOMPLETE = (
    "Seller billing information is incomplete. Please complete Billing Settings before generating the invoice."
)
_CUSTOMER_INCOMPLETE = (
    "Customer billing information is incomplete. Please update the customer/company profile before generating the invoice."
)


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rate(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _norm_state_code(raw: str | None) -> str:
    return "".join(ch for ch in (raw or "") if ch.isalnum()).upper()


def _blank(raw: str | None) -> bool:
    return not (raw or "").strip()


def _compose_seller_address(row: BillingSettings) -> str | None:
    parts = [
        (getattr(row, "address_line1", None) or "").strip(),
        (getattr(row, "address_line2", None) or "").strip(),
        (getattr(row, "city", None) or "").strip(),
        (getattr(row, "pincode", None) or "").strip(),
        (getattr(row, "country", None) or "").strip(),
    ]
    composed = ", ".join(p for p in parts if p)
    return composed or (row.business_address or None)


def get_billing_settings(db: Session) -> BillingSettings:
    row = db.get(BillingSettings, 1)
    if row:
        return row
    row = BillingSettings(
        id=1,
        invoice_prefix="INV-",
        cgst_rate=9,
        sgst_rate=9,
        igst_rate=18,
        country="India",
    )
    db.add(row)
    db.flush()
    return row


def serialize_billing_settings(row: BillingSettings) -> dict[str, Any]:
    address_line1 = getattr(row, "address_line1", None)
    if _blank(address_line1) and not _blank(row.business_address) and _blank(getattr(row, "city", None)):
        address_line1 = row.business_address
    return {
        "business_name": row.business_name,
        "legal_business_name": getattr(row, "legal_business_name", None),
        "business_address": row.business_address or _compose_seller_address(row),
        "address_line1": address_line1,
        "address_line2": getattr(row, "address_line2", None),
        "city": getattr(row, "city", None),
        "gstin": row.gstin,
        "state": row.state,
        "state_code": row.state_code,
        "pincode": getattr(row, "pincode", None),
        "country": getattr(row, "country", None) or "India",
        "email": row.email,
        "phone": row.phone,
        "website": getattr(row, "website", None),
        "pan": getattr(row, "pan", None),
        "logo_path": row.logo_path,
        "invoice_prefix": row.invoice_prefix or "INV-",
        "cgst_rate": float(row.cgst_rate) if row.cgst_rate is not None else 9,
        "sgst_rate": float(row.sgst_rate) if row.sgst_rate is not None else 9,
        "igst_rate": float(row.igst_rate) if row.igst_rate is not None else 18,
        "terms_notes": row.terms_notes,
    }


def update_billing_settings(db: Session, body: dict[str, Any]) -> BillingSettings:
    """Upsert the singleton seller row (id=1). Never inserts a second record."""
    row = get_billing_settings(db)
    allowed = {
        "business_name",
        "legal_business_name",
        "business_address",
        "address_line1",
        "address_line2",
        "city",
        "gstin",
        "state",
        "state_code",
        "pincode",
        "country",
        "email",
        "phone",
        "website",
        "pan",
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
        elif key == "state_code" and val is not None:
            setattr(row, key, _norm_state_code(str(val)) or None)
        else:
            setattr(row, key, (str(val).strip() if isinstance(val, str) else val) or None)
    if _blank(row.business_address):
        row.business_address = _compose_seller_address(row)
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
        missing.append("business name")
    address = settings.business_address or _compose_seller_address(settings)
    if _blank(address) and _blank(getattr(settings, "address_line1", None)):
        missing.append("business address")
    if _blank(getattr(settings, "city", None)) and _blank(address):
        missing.append("city")
    if _blank(settings.state) or _blank(settings.state_code):
        missing.append("state / state code")
    if _blank(getattr(settings, "pincode", None)) and _blank(address):
        missing.append("pincode")
    if _blank(settings.email):
        missing.append("email")
    if _blank(settings.phone):
        missing.append("phone")
    if _blank(settings.gstin):
        missing.append("GSTIN")
    return missing


def _customer_gaps(company: Company | None) -> list[str]:
    if company is None:
        return ["customer company"]
    missing: list[str] = []
    if _blank(company.company_name):
        missing.append("company name")
    if _blank(company.billing_address):
        missing.append("address")
    if _blank(company.billing_city):
        missing.append("city")
    if _blank(company.billing_state) or _blank(company.billing_state_code):
        missing.append("state / state code")
    if _blank(company.billing_pincode):
        missing.append("pincode")
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
    if _seller_gaps(settings):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_SELLER_INCOMPLETE)
    if _customer_gaps(company):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_CUSTOMER_INCOMPLETE)

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
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _pdf_text(value: Any) -> str:
    s = str(value or "")
    return (
        s.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("₹", "INR ")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def render_invoice_pdf(data: dict[str, Any]) -> bytes:
    """Selectable-text PDF (Helvetica). No screenshot/image invoice."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def line(h: float, text: str, *, bold: bool = False, size: int = 9) -> None:
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.cell(0, h, _pdf_text(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "TAX INVOICE", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    seller = data.get("seller") or {}
    line(6, seller.get("business_name") or "Seller", bold=True, size=11)
    legal = (seller.get("legal_business_name") or "").strip()
    if legal and legal != (seller.get("business_name") or "").strip():
        line(5, legal)
    pdf.set_font("Helvetica", "", 9)
    addr = seller.get("business_address") or ", ".join(
        p
        for p in (
            seller.get("address_line1"),
            seller.get("address_line2"),
            seller.get("city"),
            seller.get("pincode"),
            seller.get("country"),
        )
        if p
    )
    for item in (
        addr,
        f"{seller.get('city') or ''} {seller.get('pincode') or ''}  {seller.get('state') or ''} ({seller.get('state_code') or ''})".strip(),
        f"Country: {seller.get('country') or '-'}" if seller.get("country") else None,
        f"GSTIN: {seller.get('gstin') or '-'}",
        f"PAN: {seller.get('pan')}" if seller.get("pan") else None,
        f"Email: {seller.get('email') or '-'}  Phone: {seller.get('phone') or '-'}",
        f"Website: {seller.get('website')}" if seller.get("website") else None,
    ):
        if item:
            line(5, item)
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(95, 6, _pdf_text(f"Invoice: {data.get('invoice_number') or ''}"))
    pdf.cell(95, 6, _pdf_text(f"Date: {data.get('invoice_date') or ''}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    line(5, f"Payment: {data.get('payment_code') or ''}  Method: {data.get('payment_method') or ''}  Ref: {data.get('payment_reference') or '-'}")
    line(5, f"Payment verified: {data.get('payment_verified_at') or '-'}")
    pdf.ln(2)
    line(6, "Bill To", bold=True, size=10)
    line(5, data.get("customer_name") or data.get("company_name") or "")
    line(5, data.get("company_name") or "")
    line(5, data.get("billing_address") or "")
    line(5, f"{data.get('city') or ''} {data.get('pincode') or ''}  {data.get('state') or ''} ({data.get('state_code') or ''})")
    line(5, f"GSTIN: {data.get('gstin') or '-'}  Email: {data.get('email') or '-'}  Phone: {data.get('phone') or '-'}")
    start = data.get("subscription_start_date") or "-"
    end = data.get("subscription_end_date") or "-"
    pdf.ln(2)
    line(5, f"Subscription period: {start} to {end}")
    line(5, f"Billing period: {data.get('billing_period_label') or data.get('billing_period') or ''}")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(100, 7, "Description", border=1)
    pdf.cell(20, 7, "Qty", border=1)
    pdf.cell(35, 7, "Rate", border=1)
    pdf.cell(35, 7, "Amount", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    desc = _pdf_text(data.get("line_description") or "")[:90]
    pdf.cell(100, 7, desc, border=1)
    pdf.cell(20, 7, str(data.get("quantity") or 1), border=1)
    pdf.cell(35, 7, _inr(data.get("rate")), border=1)
    pdf.cell(35, 7, _inr(data.get("subtotal")), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)
    pdf.cell(155, 6, "Taxable value")
    pdf.cell(35, 6, _inr(data.get("taxable_amount")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    mode = data.get("tax_mode")
    if mode == TAX_CGST_SGST:
        pdf.cell(155, 6, _pdf_text(f"CGST @ {data.get('cgst_rate')}%"))
        pdf.cell(35, 6, _inr(data.get("cgst")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(155, 6, _pdf_text(f"SGST @ {data.get('sgst_rate')}%"))
        pdf.cell(35, 6, _inr(data.get("sgst")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.cell(155, 6, _pdf_text(f"IGST @ {data.get('igst_rate')}%"))
        pdf.cell(35, 6, _inr(data.get("igst")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(155, 6, "Total tax")
    pdf.cell(35, 6, _inr(data.get("total_tax")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(155, 7, "Grand total")
    pdf.cell(35, 7, _inr(data.get("grand_total")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    notes = data.get("terms_notes") or (seller.get("terms_notes") if isinstance(seller, dict) else None)
    if notes:
        pdf.ln(4)
        pdf.set_font("Helvetica", "", 8)
        pdf.multi_cell(0, 4, _pdf_text(notes))
    return bytes(pdf.output())


def _inr(value: Any) -> str:
    try:
        n = _money(value or 0)
    except Exception:
        n = _money(0)
    return f"INR {n:,.2f}"
