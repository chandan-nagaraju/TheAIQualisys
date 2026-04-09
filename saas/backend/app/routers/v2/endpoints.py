import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.deps import (
    get_company_for_user,
    get_current_company_user,
    get_db_session,
    require_invoice_create_allowed,
    require_subscription_access,
)
from app.models import Company, CompanyUser, Customer, InvoiceV2, PartSpecV2, PartV2
from app.schemas import (
    CompanyOut,
    CompanyUserOut,
    InvoiceCreateV2,
    InvoiceOutV2,
    MeResponse,
    PartCreateV2,
    PartOutV2,
    SpecOutV2,
)
from app.subscription_logic import (
    can_access_fir_workspace,
    can_create_invoice,
    can_record_fir_reports,
    count_combined_usage_this_month,
    count_fir_reports_this_month,
    count_invoices_this_month,
    plan_invoice_limit,
)

router = APIRouter(prefix="/api/v2", tags=["v2"])

def _v2_default_customer_id(db: Session, company_id: int) -> int:
    rows = db.execute(select(Customer).where(Customer.company_id == company_id).order_by(Customer.id)).scalars().all()
    if not rows:
        c = Customer(company_id=company_id, vendor_code="IMPORT", name="Imported parts")
        db.add(c)
        db.flush()
        return c.id
    return rows[0].id




@router.get("/me", response_model=MeResponse)
def v2_me(
    user_company: tuple[CompanyUser, Company] = Depends(require_subscription_access),
    db: Session = Depends(get_db_session),
):
    user, company = user_company
    settings = get_settings()
    today = date.today()
    inv = count_invoices_this_month(db, company.id, today)
    fir = count_fir_reports_this_month(db, company.id, today)
    usage = count_combined_usage_this_month(db, company.id, today)
    limit = plan_invoice_limit(db, company.plan_type)
    ok, sub_msg = can_create_invoice(db, company, enable_subscription=settings.enable_subscription)
    ok_fir, _ = can_record_fir_reports(
        db, company, n=1, enable_subscription=settings.enable_subscription, today=today
    )
    return MeResponse(
        user=CompanyUserOut.model_validate(user),
        company=CompanyOut.model_validate(company),
        invoices_this_month=inv,
        fir_reports_this_month=fir,
        usage_this_month=usage,
        invoice_limit=limit,
        can_create_invoice=ok,
        can_record_fir_report=ok_fir,
        can_access_fir_workspace=can_access_fir_workspace(
            company, enable_subscription=settings.enable_subscription, today=today
        ),
        subscription_message=None if ok else sub_msg,
    )


@router.get("/invoices", response_model=list[InvoiceOutV2])
def list_invoices(
    user_company: tuple[CompanyUser, Company] = Depends(require_subscription_access),
    db: Session = Depends(get_db_session),
):
    _, company = user_company
    rows = (
        db.execute(
            select(InvoiceV2)
            .where(InvoiceV2.company_id == company.id)
            .order_by(InvoiceV2.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [InvoiceOutV2.model_validate(r) for r in rows]


@router.post("/invoices", response_model=InvoiceOutV2)
def create_invoice(
    body: InvoiceCreateV2,
    user_company: tuple[CompanyUser, Company] = Depends(require_invoice_create_allowed),
    db: Session = Depends(get_db_session),
):
    _, company = user_company
    inv = InvoiceV2(company_id=company.id, invoice_number=body.invoice_number)
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return InvoiceOutV2.model_validate(inv)


@router.get("/parts", response_model=list[PartOutV2])
def list_parts(
    user_company: tuple[CompanyUser, Company] = Depends(require_subscription_access),
    db: Session = Depends(get_db_session),
):
    _, company = user_company
    rows = (
        db.execute(select(PartV2).where(PartV2.company_id == company.id).order_by(PartV2.part_no))
        .scalars()
        .all()
    )
    return [PartOutV2.model_validate(r) for r in rows]


@router.post("/parts", response_model=PartOutV2)
def create_part(
    body: PartCreateV2,
    user_company: tuple[CompanyUser, Company] = Depends(require_subscription_access),
    db: Session = Depends(get_db_session),
):
    _, company = user_company
    cid = _v2_default_customer_id(db, company.id)
    exists = db.execute(
        select(PartV2).where(
            PartV2.company_id == company.id,
            PartV2.customer_id == cid,
            PartV2.part_no == body.part_no.strip(),
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Part number already exists for this company")
    p = PartV2(
        company_id=company.id,
        customer_id=cid,
        part_no=body.part_no.strip(),
        drawing_rev=body.drawing_rev,
        description=body.description,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return PartOutV2.model_validate(p)


@router.get("/parts/{part_id}/specs", response_model=list[SpecOutV2])
def list_specs(
    part_id: int,
    user_company: tuple[CompanyUser, Company] = Depends(require_subscription_access),
    db: Session = Depends(get_db_session),
):
    _, company = user_company
    part = db.get(PartV2, part_id)
    if not part or part.company_id != company.id:
        raise HTTPException(status_code=404, detail="Part not found")
    rows = (
        db.execute(select(PartSpecV2).where(PartSpecV2.part_id == part_id).order_by(PartSpecV2.id))
        .scalars()
        .all()
    )
    return [SpecOutV2.model_validate(r) for r in rows]


@router.post("/parts/{part_id}/specs", response_model=SpecOutV2)
def add_spec(
    part_id: int,
    payload: dict = Body(...),
    user_company: tuple[CompanyUser, Company] = Depends(require_subscription_access),
    db: Session = Depends(get_db_session),
):
    _, company = user_company
    part = db.get(PartV2, part_id)
    if not part or part.company_id != company.id:
        raise HTTPException(status_code=404, detail="Part not found")
    row = PartSpecV2(
        part_id=part_id,
        parameter=str(payload.get("parameter", "")).strip() or "—",
        specification=payload.get("specification"),
        special_char=payload.get("special_char"),
        method_of_inspection=payload.get("method_of_inspection"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return SpecOutV2.model_validate(row)


@router.get("/export")
def export_data(
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    company = get_company_for_user(user, db)
    parts = db.execute(select(PartV2).where(PartV2.company_id == company.id)).scalars().all()
    invoices = db.execute(select(InvoiceV2).where(InvoiceV2.company_id == company.id)).scalars().all()
    specs_out = []
    for p in parts:
        spec_rows = (
            db.execute(select(PartSpecV2).where(PartSpecV2.part_id == p.id).order_by(PartSpecV2.id))
            .scalars()
            .all()
        )
        for s in spec_rows:
            specs_out.append(
                {
                    "part_no": p.part_no,
                    "parameter": s.parameter,
                    "specification": s.specification,
                    "special_char": s.special_char,
                    "method_of_inspection": s.method_of_inspection,
                }
            )

    payload = {
        "company": company.company_name,
        "vendor_code": company.vendor_code,
        "export_date": datetime.now(timezone.utc).isoformat(),
        "data": {
            "parts": [
                {"part_no": p.part_no, "drawing_rev": p.drawing_rev, "description": p.description}
                for p in parts
            ],
            "invoices": [
                {
                    "invoice_number": i.invoice_number,
                    "created_at": i.created_at.isoformat() if i.created_at else None,
                }
                for i in invoices
            ],
            "specs": specs_out,
        },
    }

    def iter_bytes():
        yield json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    filename = f"fir-export-{company.vendor_code}.json"
    return StreamingResponse(
        iter_bytes(),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_data(
    file: UploadFile = File(...),
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    company = get_company_for_user(user, db)
    raw = await file.read()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON file")

    data = doc.get("data") or {}
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Invalid export format: missing data object")

    # Remove existing tenant data (prevent duplicates / cross-leak: always scoped to this company_id)
    for inv in db.execute(select(InvoiceV2).where(InvoiceV2.company_id == company.id)).scalars().all():
        db.delete(inv)
    parts_existing = db.execute(select(PartV2).where(PartV2.company_id == company.id)).scalars().all()
    for p in parts_existing:
        db.delete(p)
    db.commit()

    parts_in = data.get("parts") or []
    specs_in = data.get("specs") or []
    invoices_in = data.get("invoices") or []

    cid_imp = _v2_default_customer_id(db, company.id)
    part_by_no: dict[str, PartV2] = {}
    for row in parts_in:
        if not isinstance(row, dict):
            continue
        pn = str(row.get("part_no", "")).strip()
        if not pn:
            continue
        p = PartV2(
            company_id=company.id,
            customer_id=cid_imp,
            part_no=pn,
            drawing_rev=row.get("drawing_rev"),
            description=row.get("description"),
        )
        db.add(p)
        db.flush()
        part_by_no[pn] = p

    for row in specs_in:
        if not isinstance(row, dict):
            continue
        pn = str(row.get("part_no", "")).strip()
        p = part_by_no.get(pn)
        if not p:
            continue
        db.add(
            PartSpecV2(
                part_id=p.id,
                parameter=str(row.get("parameter", "")).strip() or "—",
                specification=row.get("specification"),
                special_char=row.get("special_char"),
                method_of_inspection=row.get("method_of_inspection"),
            )
        )

    for row in invoices_in:
        if not isinstance(row, dict):
            continue
        created_raw = row.get("created_at")
        created_at = datetime.now(timezone.utc)
        if created_raw:
            try:
                s = str(created_raw).replace("Z", "+00:00")
                parsed = datetime.fromisoformat(s)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                created_at = parsed
            except (TypeError, ValueError):
                pass
        inv = InvoiceV2(
            company_id=company.id,
            invoice_number=row.get("invoice_number"),
            created_at=created_at,
        )
        db.add(inv)

    db.commit()
    return JSONResponse({"ok": True, "imported_parts": len(part_by_no), "message": "Import completed for your company."})
