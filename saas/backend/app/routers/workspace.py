"""
Legacy FIR workspace APIs — same workflows as Flask; scoped by JWT company_id.
"""

from __future__ import annotations

import base64
import mimetypes
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, defer

from app.config import Settings, get_settings
from app.s3_assets import (
    build_s3_public_url,
    delete_s3_object,
    fetch_s3_object_bytes,
    is_company_scoped_storage_key,
    is_stored_s3_key,
    normalize_storage_key,
    presign_settings_asset_put,
    s3_assets_configured,
)
from app.dates import billing_today
from app.deps import (
    get_company_for_user,
    get_company_user_from_token_str,
    get_db_session,
    impersonated_by_admin_from_request,
)
from app.fir_excel import enrich_rows_with_parts, parse_invoice_excel
from app.fir_intelligence_ingest import (
    ingest_fir_intelligence_rows,
    parse_row_for_intelligence,
    preview_fir_intelligence_batch,
)
from app.fir_part_excel import build_part_master_template_xlsx, parse_parts_excel_to_bundle_dict
from app.part_field_validation import sanitize_part_master_alnum_upper
from app.subscription_logic import (
    FIR_WORKSPACE_FORBIDDEN_CODE,
    FIR_WORKSPACE_FORBIDDEN_MESSAGE,
    can_access_fir_workspace,
    can_record_fir_reports,
    count_combined_usage_this_month,
    count_fir_reports_this_month,
    count_invoices_this_month,
    plan_invoice_limit,
)
from app.models import (
    Company,
    CompanySettings,
    CompanyUser,
    Customer,
    PartCoatingV2,
    PartComplaintV2,
    PartMaterialV2,
    PartRevisionHistory,
    PartSpecV2,
    PartV2,
)

router = APIRouter(prefix="/api/app", tags=["workspace"])
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_BACKEND_TEMPLATES = _BACKEND_ROOT / "templates"
_BACKEND_STATIC = _BACKEND_ROOT / "static"
templates = Jinja2Templates(directory=str(_BACKEND_TEMPLATES))

@dataclass
class WsContext:
    user: CompanyUser
    company: Company
    db: Session
    customer: Customer | None


def _parse_optional_int_header(raw: str | None, *, label: str) -> int | None:
    """Headers are always strings; empty / whitespace must mean “unset”, not a validation error."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{label} must be a valid integer",
        ) from e


def optional_customer_id_query(
    customer_id: Annotated[str | None, Query(default=None)] = None,
) -> int | None:
    """Query param can be absent, or present but empty (e.g. ?customer_id=); both mean no filter."""
    return _parse_optional_int_header(customer_id, label="customer_id")


def get_ws(
    user: CompanyUser = Depends(get_company_user_from_token_str),
    db: Session = Depends(get_db_session),
    x_customer_id_header: Annotated[str | None, Header(alias="X-Customer-Id", default=None)] = None,
    admin_impersonation: bool = Depends(impersonated_by_admin_from_request),
) -> WsContext:
    settings = get_settings()
    company = get_company_for_user(user, db)
    if not can_access_fir_workspace(
        company,
        enable_subscription=settings.enable_subscription,
        today=billing_today(),
        impersonated_by_admin=admin_impersonation,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": FIR_WORKSPACE_FORBIDDEN_CODE,
                "message": FIR_WORKSPACE_FORBIDDEN_MESSAGE,
            },
        )
    x_customer_id = _parse_optional_int_header(x_customer_id_header, label="X-Customer-Id")
    cust = None
    if x_customer_id is not None:
        cust = db.execute(
            select(Customer).where(
                Customer.id == x_customer_id,
                Customer.company_id == company.id,
            )
        ).scalar_one_or_none()
    return WsContext(user=user, company=company, db=db, customer=cust)


def _upload_root() -> Path:
    p = get_settings().workspace_upload_dir
    p.mkdir(parents=True, exist_ok=True)
    return p


def _norm_rev(v: str | None) -> str:
    return (v or "").strip()


def _part_drawing_dir(company_id: int, part_id: int) -> Path:
    p = _upload_root() / "parts" / str(company_id) / str(part_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _part_drawing_file_path(company_id: int, part_id: int, filename: str | None) -> Path | None:
    """Resolve on-disk path without creating directories (safe for list endpoints)."""
    if not filename:
        return None
    path = _upload_root() / "parts" / str(company_id) / str(part_id) / filename
    return path if path.is_file() else None


def _drawing_file_exists(company_id: int, p: PartV2) -> bool:
    return _part_drawing_file_path(company_id, p.id, p.drawing_pdf_filename) is not None


def _reconcile_stale_drawing_metadata(ws: WsContext, p: PartV2) -> None:
    """Clear drawing fields if DB points to a missing file so the app keeps working and UI can offer upload."""
    if not p.drawing_pdf_filename:
        return
    if _part_drawing_file_path(ws.company.id, p.id, p.drawing_pdf_filename) is not None:
        return
    p.drawing_pdf_filename = None
    p.drawing_pdf_mime = None
    p.drawing_updated_at = None
    ws.db.commit()
    ws.db.refresh(p)


def _drawing_http_404(part_id: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": code, "message": message, "part_id": part_id},
    )


def _record_revision_if_changed(
    ws: WsContext,
    part: PartV2,
    old_rev: str | None,
    new_rev: str | None,
    reason: str | None,
) -> None:
    if _norm_rev(old_rev) == _norm_rev(new_rev):
        return
    if not reason or not str(reason).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="revision_change_reason is required when changing drawing revision",
        )
    ws.db.add(
        PartRevisionHistory(
            part_id=part.id,
            previous_rev=old_rev,
            new_rev=new_rev,
            reason=str(reason).strip(),
            changed_by_user_id=ws.user.id,
        )
    )


def _save_upload(company_id: int, prefix: str, file: UploadFile) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    raw = file.file.read()
    safe = f"{prefix}_{ts}_{file.filename or 'file'}"
    folder = _upload_root() / str(company_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / safe
    path.write_bytes(raw)
    return f"{company_id}/{safe}"


def _read_upload_file(file: UploadFile | None) -> tuple[str, str, bytes] | None:
    if not file or not file.filename:
        return None
    raw = file.file.read()
    if not raw:
        return None
    mime = (file.content_type or "").strip() or mimetypes.guess_type(file.filename)[0] or "application/octet-stream"
    return file.filename, mime, raw


_MAX_QUALI_FONT_BYTES = 5 * 1024 * 1024


def _read_quali_font_upload(file: UploadFile | None) -> tuple[str, str, bytes] | None:
    """Accept .ttf only; used for FIR measured-value font (replaces bundled Quali_1)."""
    tup = _read_upload_file(file)
    if not tup:
        return None
    name, mime, raw = tup
    if not name.lower().endswith(".ttf"):
        raise HTTPException(status_code=400, detail="Quali font must be a .ttf file")
    if len(raw) > _MAX_QUALI_FONT_BYTES:
        raise HTTPException(status_code=400, detail=f"Font file too large (max {_MAX_QUALI_FONT_BYTES // (1024 * 1024)} MB)")
    allowed = {
        "font/ttf",
        "application/x-font-ttf",
        "application/x-font-truetype",
        "application/octet-stream",
        "application/font-sfnt",
        "",
    }
    m = (mime or "").split(";")[0].strip().lower()
    if m and m not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported font MIME type for .ttf upload")
    return name, "font/ttf", raw


def _company_settings_select(company_id: int, *, load_asset_blobs: bool):
    """
    When S3 is configured, omit BYTEA columns so Postgres never transfers logo/signatures/font bytes
    (saves Supabase/Railway DB egress on read paths).
    """
    q = select(CompanySettings).where(CompanySettings.company_id == company_id)
    if not load_asset_blobs:
        q = q.options(
            defer(CompanySettings.logo_blob),
            defer(CompanySettings.inspector_signature_blob),
            defer(CompanySettings.quality_signature_blob),
            defer(CompanySettings.quali_font_blob),
        )
    return q


def _quali_font_src_from_settings(
    app_settings: Settings, st: CompanySettings | None
) -> tuple[str | None, str]:
    """Return (font src URL or data: URI, css_format) for custom Quali replacement."""
    if not st:
        return None, "truetype"
    s3_on = s3_assets_configured(app_settings)
    qpath = (st.quali_font_path or "").strip()
    if qpath:
        if qpath.startswith("http://") or qpath.startswith("https://"):
            return qpath, "truetype"
        if s3_on and is_company_scoped_storage_key(st.company_id, qpath):
            return build_s3_public_url(app_settings, qpath), "truetype"
    if not s3_on and st.quali_font_blob:
        mime = (st.quali_font_mime or "font/ttf").split(";")[0].strip() or "font/ttf"
        b64 = base64.b64encode(st.quali_font_blob).decode("ascii")
        return f"data:{mime};base64,{b64}", "truetype"
    return None, "truetype"


def _default_static_quali_font() -> tuple[str | None, str]:
    """Bundled Quali_1 in backend static (first format found)."""
    quali_font_data_uri = None
    quali_font_format = "truetype"
    for name, mime, fmt in [
        ("Quali_1.woff2", "font/woff2", "woff2"),
        ("Quali_1.woff", "font/woff", "woff"),
        ("Quali_1.ttf", "font/ttf", "truetype"),
    ]:
        path = _BACKEND_STATIC / "fonts" / name
        if path.is_file():
            try:
                data = base64.b64encode(path.read_bytes()).decode("ascii")
                quali_font_data_uri = f"data:{mime};base64,{data}"
                quali_font_format = fmt
            except OSError:
                pass
            break
    return quali_font_data_uri, quali_font_format


def _resolve_settings_image_url(app_settings: Settings, st: CompanySettings, field_prefix: str) -> str | None:
    """data: URI, https URL, or None for logo / inspector_signature / quality_signature."""
    s3_on = s3_assets_configured(app_settings)
    if not s3_on:
        blob = getattr(st, f"{field_prefix}_blob", None)
        if blob is not None:
            mime = getattr(st, f"{field_prefix}_mime", None) or "application/octet-stream"
            b64 = base64.b64encode(blob).decode("ascii")
            return f"data:{mime};base64,{b64}"
    path_val = getattr(st, f"{field_prefix}_path", None)
    if not path_val:
        return None
    path_s = path_val.strip()
    if path_s.startswith("http://") or path_s.startswith("https://"):
        return path_s
    local = _upload_root() / path_s
    if local.is_file():
        mime, _ = mimetypes.guess_type(str(local))
        mime = mime or "application/octet-stream"
        b64 = base64.b64encode(local.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"
    if s3_on and is_company_scoped_storage_key(st.company_id, path_s):
        return build_s3_public_url(app_settings, path_s)
    return None


def _file_to_data_uri(rel: str | None) -> str | None:
    if not rel:
        return None
    path = _upload_root() / rel
    if not path.is_file():
        return None
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "application/octet-stream"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _settings_dict_for_fir(db: Session, company_id: int) -> dict[str, Any]:
    app_settings = get_settings()
    st = db.execute(
        _company_settings_select(company_id, load_asset_blobs=not s3_assets_configured(app_settings))
    ).scalar_one_or_none()
    if not st:
        return {
            "company_name": "",
            "logo_path": None,
            "inspector_signature_path": None,
            "quality_signature_path": None,
            "format_no": "",
            "issue_date": "",
            "doc_rev_no": "",
            "rev_date": "",
        }
    return {
        "company_name": st.company_name or "",
        # With S3: paths/URLs only (blobs not loaded). Without S3: blobs or disk paths.
        "logo_path": _resolve_settings_image_url(app_settings, st, "logo"),
        "inspector_signature_path": _resolve_settings_image_url(app_settings, st, "inspector_signature"),
        "quality_signature_path": _resolve_settings_image_url(app_settings, st, "quality_signature"),
        "format_no": st.format_no or "",
        "issue_date": st.issue_date or "",
        "doc_rev_no": st.doc_rev_no or "",
        "rev_date": st.rev_date or "",
    }


def _get_part(ws: WsContext, part_id: int) -> PartV2:
    p = ws.db.get(PartV2, part_id)
    if not p or p.company_id != ws.company.id:
        raise HTTPException(status_code=404, detail="Part not found")
    return p


def _resolve_default_customer_id(ws: WsContext) -> int:
    rows = (
        ws.db.execute(select(Customer).where(Customer.company_id == ws.company.id).order_by(Customer.id))
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(status_code=400, detail="Add at least one customer before managing parts.")
    if len(rows) == 1:
        return rows[0].id
    if ws.customer is not None:
        return ws.customer.id
    raise HTTPException(status_code=400, detail="select_customer_required")


def _get_customer_for_part_upsert(ws: WsContext, customer_id: int | None) -> Customer:
    if customer_id is None:
        cid = _resolve_default_customer_id(ws)
        c = ws.db.get(Customer, cid)
        if not c:
            raise HTTPException(status_code=400, detail="Customer not found")
        return c
    c = ws.db.execute(
        select(Customer).where(Customer.id == customer_id, Customer.company_id == ws.company.id)
    ).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=400, detail="Invalid customer for this workspace")
    return c


# --- Customers ---
@router.get("/customers")
def list_customers(ws: WsContext = Depends(get_ws)):
    rows = (
        ws.db.execute(
            select(Customer).where(Customer.company_id == ws.company.id).order_by(Customer.name)
        )
        .scalars()
        .all()
    )
    return [{"id": r.id, "vendor_code": r.vendor_code, "name": r.name} for r in rows]


class CustomerCreate(BaseModel):
    vendor_code: str
    name: str


@router.post("/customers")
def create_customer(body: CustomerCreate, ws: WsContext = Depends(get_ws)):
    vc = body.vendor_code.strip()
    nm = body.name.strip()
    if not vc or not nm:
        raise HTTPException(status_code=400, detail="vendor_code and name required")
    exists = ws.db.execute(
        select(Customer).where(Customer.company_id == ws.company.id, Customer.vendor_code == vc)
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Vendor code already exists")
    c = Customer(company_id=ws.company.id, vendor_code=vc, name=nm)
    ws.db.add(c)
    ws.db.commit()
    ws.db.refresh(c)
    return {"id": c.id, "vendor_code": c.vendor_code, "name": c.name}


# --- Settings ---
class SettingsAssetPresignBody(BaseModel):
    kind: Literal["logo", "inspector_signature", "quality_signature", "quali_font"]
    content_type: str = ""


@router.post("/settings/asset-upload-url")
def settings_asset_upload_presign(body: SettingsAssetPresignBody, ws: WsContext = Depends(get_ws)):
    """Return a presigned PUT URL so the browser can upload directly to S3."""
    app_settings = get_settings()
    if not s3_assets_configured(app_settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="S3 asset uploads are not configured on the server",
        )
    ct = (body.content_type or "").strip()
    if body.kind == "quali_font" and not ct:
        ct = "application/octet-stream"
    if body.kind != "quali_font" and not ct:
        ct = "image/png"
    try:
        return presign_settings_asset_put(
            app_settings,
            company_id=ws.company.id,
            kind=body.kind,
            content_type=ct,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/settings")
def get_settings_api(request: Request, ws: WsContext = Depends(get_ws)):
    app_settings = get_settings()
    st = ws.db.execute(
        _company_settings_select(ws.company.id, load_asset_blobs=not s3_assets_configured(app_settings))
    ).scalar_one_or_none()
    if not st:
        return {
            "company_name": "",
            "format_no": "",
            "issue_date": "",
            "doc_rev_no": "",
            "rev_date": "",
            "logo_url": None,
            "inspector_signature_url": None,
            "quality_signature_url": None,
            "quali_font_configured": False,
            "s3_assets_enabled": s3_assets_configured(app_settings),
        }
    return {
        "company_name": st.company_name or "",
        "format_no": st.format_no or "",
        "issue_date": st.issue_date or "",
        "doc_rev_no": st.doc_rev_no or "",
        "rev_date": st.rev_date or "",
        "logo_url": _resolve_settings_image_url(app_settings, st, "logo"),
        "inspector_signature_url": _resolve_settings_image_url(app_settings, st, "inspector_signature"),
        "quality_signature_url": _resolve_settings_image_url(app_settings, st, "quality_signature"),
        "quali_font_configured": (
            bool((st.quali_font_path or "").strip())
            if s3_assets_configured(app_settings)
            else bool(st.quali_font_blob or (st.quali_font_path or "").strip())
        ),
        "s3_assets_enabled": s3_assets_configured(app_settings),
    }


@router.post("/settings")
async def save_settings(
    request: Request,
    ws: WsContext = Depends(get_ws),
    company_name: str = Form(""),
    format_no: str = Form(""),
    issue_date: str = Form(""),
    doc_rev_no: str = Form(""),
    rev_date: str = Form(""),
    logo: UploadFile | None = File(None),
    inspector_signature: UploadFile | None = File(None),
    quality_signature: UploadFile | None = File(None),
    quali_font: UploadFile | None = File(None),
    clear_quali_font: str = Form(""),
    logo_storage_key: str = Form(""),
    inspector_signature_storage_key: str = Form(""),
    quality_signature_storage_key: str = Form(""),
    quali_font_storage_key: str = Form(""),
):
    app_settings = get_settings()
    s3_on = s3_assets_configured(app_settings)
    st = ws.db.execute(
        _company_settings_select(ws.company.id, load_asset_blobs=not s3_on)
    ).scalar_one_or_none()
    if not st:
        st = CompanySettings(company_id=ws.company.id)
        ws.db.add(st)
        ws.db.flush()

    st.company_name = company_name.strip() or None
    st.format_no = format_no.strip() or None
    st.issue_date = issue_date.strip() or None
    st.doc_rev_no = doc_rev_no.strip() or None
    st.rev_date = rev_date.strip() or None

    def _delete_replaced_s3_key(old_path: str | None, new_key: str) -> None:
        if not old_path or old_path == new_key:
            return
        if is_stored_s3_key(app_settings, ws.company.id, old_path):
            delete_s3_object(app_settings, old_path)

    if s3_on and (k := (logo_storage_key or "").strip()):
        try:
            key = normalize_storage_key(ws.company.id, k)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid logo storage key")
        _delete_replaced_s3_key(st.logo_path, key)
        st.logo_path = key
        st.logo_blob = None
        st.logo_mime = None
    else:
        logo_payload = _read_upload_file(logo)
        if logo_payload:
            if is_stored_s3_key(app_settings, ws.company.id, st.logo_path):
                delete_s3_object(app_settings, st.logo_path)
            _name, mime, raw = logo_payload
            st.logo_blob = raw
            st.logo_mime = mime
            st.logo_path = None

    if s3_on and (k := (inspector_signature_storage_key or "").strip()):
        try:
            key = normalize_storage_key(ws.company.id, k)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid inspector signature storage key")
        _delete_replaced_s3_key(st.inspector_signature_path, key)
        st.inspector_signature_path = key
        st.inspector_signature_blob = None
        st.inspector_signature_mime = None
    else:
        inspector_payload = _read_upload_file(inspector_signature)
        if inspector_payload:
            if is_stored_s3_key(app_settings, ws.company.id, st.inspector_signature_path):
                delete_s3_object(app_settings, st.inspector_signature_path)
            _name, mime, raw = inspector_payload
            st.inspector_signature_blob = raw
            st.inspector_signature_mime = mime
            st.inspector_signature_path = None

    if s3_on and (k := (quality_signature_storage_key or "").strip()):
        try:
            key = normalize_storage_key(ws.company.id, k)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid quality signature storage key")
        _delete_replaced_s3_key(st.quality_signature_path, key)
        st.quality_signature_path = key
        st.quality_signature_blob = None
        st.quality_signature_mime = None
    else:
        quality_payload = _read_upload_file(quality_signature)
        if quality_payload:
            if is_stored_s3_key(app_settings, ws.company.id, st.quality_signature_path):
                delete_s3_object(app_settings, st.quality_signature_path)
            _name, mime, raw = quality_payload
            st.quality_signature_blob = raw
            st.quality_signature_mime = mime
            st.quality_signature_path = None

    clear_q = (clear_quali_font or "").strip().lower() in ("1", "true", "on", "yes")
    if clear_q:
        if is_stored_s3_key(app_settings, ws.company.id, st.quali_font_path):
            delete_s3_object(app_settings, st.quali_font_path)
        st.quali_font_blob = None
        st.quali_font_mime = None
        st.quali_font_path = None
    elif s3_on and (qk := (quali_font_storage_key or "").strip()):
        try:
            key = normalize_storage_key(ws.company.id, qk)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid font storage key")
        _delete_replaced_s3_key(st.quali_font_path, key)
        st.quali_font_path = key
        st.quali_font_blob = None
        st.quali_font_mime = None
    else:
        quali_payload = _read_quali_font_upload(quali_font)
        if quali_payload:
            if is_stored_s3_key(app_settings, ws.company.id, st.quali_font_path):
                delete_s3_object(app_settings, st.quali_font_path)
            _name, mime, raw = quali_payload
            st.quali_font_blob = raw
            st.quali_font_mime = mime
            st.quali_font_path = None

    ws.db.commit()
    return get_settings_api(request, ws)


# --- Parts ---
@router.get("/parts")
def list_parts(
    customer_id: int | None = Depends(optional_customer_id_query),
    ws: WsContext = Depends(get_ws),
):
    q = select(PartV2).where(PartV2.company_id == ws.company.id)
    if customer_id is not None:
        q = q.where(PartV2.customer_id == customer_id)
    rows = ws.db.execute(q.order_by(PartV2.part_no)).scalars().all()
    cust_rows = ws.db.execute(select(Customer).where(Customer.company_id == ws.company.id)).scalars().all()
    cust_by_id = {c.id: c for c in cust_rows}
    return [
        {
            "part_id": r.id,
            "part_no": r.part_no,
            "customer_id": r.customer_id,
            "customer_vendor_code": cust_by_id[r.customer_id].vendor_code if r.customer_id in cust_by_id else "",
            "customer_name": cust_by_id[r.customer_id].name if r.customer_id in cust_by_id else "",
            "drawing_rev": r.drawing_rev,
            "description": r.description,
            "has_drawing": _drawing_file_exists(ws.company.id, r),
        }
        for r in rows
    ]


class PartUpsert(BaseModel):
    part_no: str
    description: str | None = None
    drawing_rev: str | None = None
    part_id: int | None = None
    revision_change_reason: str | None = None
    customer_id: int | None = None


@router.post("/parts")
def upsert_part(body: PartUpsert, ws: WsContext = Depends(get_ws)):
    part_no = sanitize_part_master_alnum_upper(body.part_no)
    if not part_no:
        raise HTTPException(status_code=400, detail="part_no must contain only A–Z and 0–9, at least one character")
    description = sanitize_part_master_alnum_upper(body.description) if body.description is not None else None
    description = description if description else None

    cust = _get_customer_for_part_upsert(ws, body.customer_id)
    cust_id = cust.id

    if body.part_id is not None:
        p = _get_part(ws, body.part_id)
        old_rev = p.drawing_rev
        p.part_no = part_no
        p.customer_id = cust_id
        p.description = description
        p.drawing_rev = body.drawing_rev
        _record_revision_if_changed(ws, p, old_rev, p.drawing_rev, body.revision_change_reason)
        ws.db.commit()
        ws.db.refresh(p)
        return {"part_id": p.id, "part_no": p.part_no, "drawing_rev": p.drawing_rev, "description": p.description}

    existing = ws.db.execute(
        select(PartV2).where(
            PartV2.company_id == ws.company.id,
            PartV2.customer_id == cust_id,
            PartV2.part_no == part_no,
        )
    ).scalar_one_or_none()
    if existing:
        old_rev = existing.drawing_rev
        existing.description = description
        existing.drawing_rev = body.drawing_rev
        _record_revision_if_changed(ws, existing, old_rev, existing.drawing_rev, body.revision_change_reason)
        ws.db.commit()
        ws.db.refresh(existing)
        return {
            "part_id": existing.id,
            "part_no": existing.part_no,
            "drawing_rev": existing.drawing_rev,
            "description": existing.description,
        }

    p = PartV2(
        company_id=ws.company.id,
        customer_id=cust_id,
        part_no=part_no,
        description=description,
        drawing_rev=body.drawing_rev,
    )
    ws.db.add(p)
    ws.db.commit()
    ws.db.refresh(p)
    return {"part_id": p.id, "part_no": p.part_no, "drawing_rev": p.drawing_rev, "description": p.description}


@router.delete("/parts/{part_id}")
def delete_part(part_id: int, ws: WsContext = Depends(get_ws)):
    """Remove a part and its A–D rows (cascade); delete drawing files on disk if present."""
    p = _get_part(ws, part_id)
    folder = _upload_root() / "parts" / str(ws.company.id) / str(part_id)
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
    ws.db.delete(p)
    ws.db.commit()
    return {"ok": True, "part_id": part_id}


def _serialize_part_detail(ws: WsContext, p: PartV2) -> dict[str, Any]:
    specs = (
        ws.db.execute(select(PartSpecV2).where(PartSpecV2.part_id == p.id).order_by(PartSpecV2.id))
        .scalars()
        .all()
    )
    cps = (
        ws.db.execute(select(PartComplaintV2).where(PartComplaintV2.part_id == p.id).order_by(PartComplaintV2.id))
        .scalars()
        .all()
    )
    mats = (
        ws.db.execute(select(PartMaterialV2).where(PartMaterialV2.part_id == p.id).order_by(PartMaterialV2.id))
        .scalars()
        .all()
    )
    coats = (
        ws.db.execute(select(PartCoatingV2).where(PartCoatingV2.part_id == p.id).order_by(PartCoatingV2.id))
        .scalars()
        .all()
    )
    revs = (
        ws.db.execute(
            select(PartRevisionHistory)
            .where(PartRevisionHistory.part_id == p.id)
            .order_by(PartRevisionHistory.id.desc())
        )
        .scalars()
        .all()
    )
    cust = ws.db.get(Customer, p.customer_id)
    return {
        "part_id": p.id,
        "part_no": p.part_no,
        "customer_id": p.customer_id,
        "customer_vendor_code": cust.vendor_code if cust else "",
        "customer_name": cust.name if cust else "",
        "drawing_rev": p.drawing_rev,
        "description": p.description,
        "drawing_pdf_filename": p.drawing_pdf_filename,
        "drawing_pdf_mime": p.drawing_pdf_mime,
        "drawing_updated_at": p.drawing_updated_at.isoformat() if p.drawing_updated_at else None,
        "drawing_file_present": _drawing_file_exists(ws.company.id, p),
        "revision_rows": [
            {
                "id": r.id,
                "previous_rev": r.previous_rev,
                "new_rev": r.new_rev,
                "reason": r.reason,
                "changed_by_user_id": r.changed_by_user_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in revs
        ],
        "spec_rows": [
            {
                "id": s.id,
                "parameter": s.parameter,
                "specification": s.specification,
                "special_char": s.special_char,
                "method_of_inspection": s.method_of_inspection,
            }
            for s in specs
        ],
        "ccp_rows": [
            {
                "parameter": c.parameter,
                "specification": c.specification,
                "special_char": c.special_char,
                "method_of_inspection": c.method_of_inspection,
            }
            for c in cps
        ],
        "material_rows": [{"material_grade": m.material_grade} for m in mats],
        "coating_rows": [
            {
                "parameter": c.parameter,
                "specification": c.specification,
                "special_char": c.special_char,
                "method_of_inspection": c.method_of_inspection,
            }
            for c in coats
        ],
    }


@router.get("/parts/{part_id}")
def get_part_detail(part_id: int, ws: WsContext = Depends(get_ws)):
    p = _get_part(ws, part_id)
    _reconcile_stale_drawing_metadata(ws, p)
    return _serialize_part_detail(ws, p)


@router.post("/parts/{part_id}/drawing")
async def upload_part_drawing(part_id: int, file: UploadFile, ws: WsContext = Depends(get_ws)):
    p = _get_part(ws, part_id)
    fn = (file.filename or "").lower()
    if not fn.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF file required")
    dest_dir = _part_drawing_dir(ws.company.id, part_id)
    dest = dest_dir / "drawing.pdf"
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file")
    dest.write_bytes(raw)
    mime = file.content_type or "application/pdf"
    p.drawing_pdf_filename = "drawing.pdf"
    p.drawing_pdf_mime = mime
    p.drawing_updated_at = datetime.now(timezone.utc)
    ws.db.commit()
    return {"ok": True}


@router.get("/parts/{part_id}/drawing")
def get_part_drawing_file(part_id: int, download: bool = False, ws: WsContext = Depends(get_ws)):
    p = _get_part(ws, part_id)
    _reconcile_stale_drawing_metadata(ws, p)
    if not p.drawing_pdf_filename:
        raise _drawing_http_404(
            part_id,
            "DRAWING_NOT_FOUND",
            "No drawing PDF for this part yet. Upload a PDF from the part detail page or the Parts master form.",
        )
    path = _part_drawing_file_path(ws.company.id, part_id, p.drawing_pdf_filename)
    if path is None:
        _reconcile_stale_drawing_metadata(ws, p)
        raise _drawing_http_404(
            part_id,
            "DRAWING_FILE_MISSING",
            "Drawing file was not on disk; metadata was cleared. Upload a PDF again from the part page.",
        )
    safe = re.sub(r"[^\w.\-]+", "_", str(p.part_no or "part").strip())[:120] or "part"
    fname = f"{safe}_drawing.pdf"
    disp = "attachment" if download else "inline"
    try:
        content = path.read_bytes()
    except OSError:
        _reconcile_stale_drawing_metadata(ws, p)
        raise _drawing_http_404(
            part_id,
            "DRAWING_READ_ERROR",
            "Could not read the drawing file. Upload a new PDF from the part page.",
        ) from None
    return Response(
        content=content,
        media_type=p.drawing_pdf_mime or "application/pdf",
        headers={"Content-Disposition": f'{disp}; filename="{fname}"'},
    )


def _row4_dict(r: dict[str, Any]) -> dict[str, str]:
    return {
        "parameter": str(r.get("parameter") or ""),
        "specification": str(r.get("specification") or ""),
        "special_char": str(r.get("special_char") or ""),
        "method_of_inspection": str(r.get("method_of_inspection") or ""),
    }


@router.get("/parts/{part_id}/export")
def export_part_master_json(part_id: int, ws: WsContext = Depends(get_ws)):
    """Same JSON shape as legacy `/parts/<id>/export` for backup or tenant moves."""
    p = _get_part(ws, part_id)
    inner = _serialize_part_detail(ws, p)
    payload = {
        "format": "fir_part_master_v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_from": "saas",
        "part": {
            "part_no": inner["part_no"],
            "drawing_rev": inner.get("drawing_rev") or "",
            "description": inner.get("description") or "",
        },
        "spec_rows": [_row4_dict(r) for r in inner["spec_rows"]],
        "ccp_rows": [_row4_dict(r) for r in inner["ccp_rows"]],
        "material_rows": [{"material_grade": str(m.get("material_grade") or "")} for m in inner["material_rows"]],
        "coating_rows": [_row4_dict(r) for r in inner["coating_rows"]],
    }
    safe_no = re.sub(r"[^\w.\-]+", "_", str(inner["part_no"] or "part").strip())[:120] or "part"
    filename = f"fir_part_master_{safe_no}.json"
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


class SpecRowIn(BaseModel):
    parameter: str
    specification: str | None = None
    special_char: str | None = None
    method_of_inspection: str | None = None


class SpecBulkBody(BaseModel):
    rows: list[SpecRowIn]


@router.put("/parts/{part_id}/specs")
def replace_specs(part_id: int, body: SpecBulkBody, ws: WsContext = Depends(get_ws)):
    p = _get_part(ws, part_id)
    ws.db.execute(delete(PartSpecV2).where(PartSpecV2.part_id == p.id))
    for row in body.rows:
        if not row.parameter.strip():
            continue
        ws.db.add(
            PartSpecV2(
                part_id=p.id,
                parameter=row.parameter.strip(),
                specification=row.specification,
                special_char=row.special_char,
                method_of_inspection=row.method_of_inspection,
            )
        )
    ws.db.commit()
    return {"ok": True}


@router.put("/parts/{part_id}/complaints")
def replace_complaints(part_id: int, body: SpecBulkBody, ws: WsContext = Depends(get_ws)):
    p = _get_part(ws, part_id)
    ws.db.execute(delete(PartComplaintV2).where(PartComplaintV2.part_id == p.id))
    for row in body.rows:
        if not row.parameter.strip():
            continue
        ws.db.add(
            PartComplaintV2(
                part_id=p.id,
                parameter=row.parameter.strip(),
                specification=row.specification,
                special_char=row.special_char,
                method_of_inspection=row.method_of_inspection,
            )
        )
    ws.db.commit()
    return {"ok": True}


class MaterialsBody(BaseModel):
    grades: list[str]


@router.put("/parts/{part_id}/materials")
def replace_materials(part_id: int, body: MaterialsBody, ws: WsContext = Depends(get_ws)):
    p = _get_part(ws, part_id)
    ws.db.execute(delete(PartMaterialV2).where(PartMaterialV2.part_id == p.id))
    for g in body.grades:
        if g and str(g).strip():
            ws.db.add(PartMaterialV2(part_id=p.id, material_grade=str(g).strip()))
    ws.db.commit()
    return {"ok": True}


@router.put("/parts/{part_id}/coatings")
def replace_coatings(part_id: int, body: SpecBulkBody, ws: WsContext = Depends(get_ws)):
    p = _get_part(ws, part_id)
    ws.db.execute(delete(PartCoatingV2).where(PartCoatingV2.part_id == p.id))
    for row in body.rows:
        if not row.parameter.strip():
            continue
        ws.db.add(
            PartCoatingV2(
                part_id=p.id,
                parameter=row.parameter.strip(),
                specification=row.specification,
                special_char=row.special_char,
                method_of_inspection=row.method_of_inspection,
            )
        )
    ws.db.commit()
    return {"ok": True}


def _norm_opt_str(s: str | None) -> str | None:
    if s is None:
        return None
    t = str(s).strip()
    return t if t else None


class PartMasterPartBlock(BaseModel):
    model_config = ConfigDict(extra="ignore")
    part_no: str
    drawing_rev: str | None = None
    description: str | None = None

    @field_validator("part_no", mode="before")
    @classmethod
    def _part_no_sanitize(cls, v: object) -> str:
        return sanitize_part_master_alnum_upper(v if isinstance(v, str) else (str(v) if v is not None else None))

    @field_validator("description", mode="before")
    @classmethod
    def _description_sanitize(cls, v: object) -> str | None:
        if v is None:
            return None
        s = sanitize_part_master_alnum_upper(v if isinstance(v, str) else str(v))
        return s if s else None

    @field_validator("part_no")
    @classmethod
    def _part_no_nonempty(cls, v: str) -> str:
        if not v:
            raise ValueError("part.part_no is required (A–Z and 0–9 only)")
        return v


class PartMasterRowAD(BaseModel):
    model_config = ConfigDict(extra="ignore")
    parameter: str = ""
    specification: str | None = None
    special_char: str | None = None
    method_of_inspection: str | None = None


class PartMasterRowMat(BaseModel):
    model_config = ConfigDict(extra="ignore")
    material_grade: str = ""


class PartMasterSlice(BaseModel):
    """One part + A–D rows (no outer format key). Used inside bundle files."""

    model_config = ConfigDict(extra="ignore")
    part: PartMasterPartBlock
    spec_rows: list[PartMasterRowAD] | None = None
    ccp_rows: list[PartMasterRowAD] | None = None
    material_rows: list[PartMasterRowMat] | None = None
    coating_rows: list[PartMasterRowAD] | None = None


class PartMasterImportBody(PartMasterSlice):
    format: str


class PartMasterBundleBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    format: str
    parts: list[PartMasterSlice]


def _apply_part_master_slice(ws: WsContext, body: PartMasterSlice, *, customer_id: int) -> PartV2:
    pn = body.part.part_no
    drawing_rev = _norm_opt_str(body.part.drawing_rev)
    description = _norm_opt_str(body.part.description)

    p = ws.db.execute(
        select(PartV2).where(
            PartV2.company_id == ws.company.id,
            PartV2.customer_id == customer_id,
            PartV2.part_no == pn,
        )
    ).scalar_one_or_none()
    if p:
        p.drawing_rev = drawing_rev
        p.description = description
    else:
        p = PartV2(
            company_id=ws.company.id,
            customer_id=customer_id,
            part_no=pn,
            drawing_rev=drawing_rev,
            description=description,
        )
        ws.db.add(p)
        ws.db.flush()

    ws.db.execute(delete(PartSpecV2).where(PartSpecV2.part_id == p.id))
    for row in body.spec_rows or []:
        if not (row.parameter or "").strip():
            continue
        ws.db.add(
            PartSpecV2(
                part_id=p.id,
                parameter=row.parameter.strip(),
                specification=_norm_opt_str(row.specification),
                special_char=_norm_opt_str(row.special_char),
                method_of_inspection=_norm_opt_str(row.method_of_inspection),
            )
        )

    ws.db.execute(delete(PartComplaintV2).where(PartComplaintV2.part_id == p.id))
    for row in body.ccp_rows or []:
        if not (row.parameter or "").strip():
            continue
        ws.db.add(
            PartComplaintV2(
                part_id=p.id,
                parameter=row.parameter.strip(),
                specification=_norm_opt_str(row.specification),
                special_char=_norm_opt_str(row.special_char),
                method_of_inspection=_norm_opt_str(row.method_of_inspection),
            )
        )

    ws.db.execute(delete(PartMaterialV2).where(PartMaterialV2.part_id == p.id))
    for row in body.material_rows or []:
        g = (row.material_grade or "").strip()
        if g:
            ws.db.add(PartMaterialV2(part_id=p.id, material_grade=g))

    ws.db.execute(delete(PartCoatingV2).where(PartCoatingV2.part_id == p.id))
    for row in body.coating_rows or []:
        if not (row.parameter or "").strip():
            continue
        ws.db.add(
            PartCoatingV2(
                part_id=p.id,
                parameter=row.parameter.strip(),
                specification=_norm_opt_str(row.specification),
                special_char=_norm_opt_str(row.special_char),
                method_of_inspection=_norm_opt_str(row.method_of_inspection),
            )
        )
    return p


@router.post("/parts/import-master")
def import_part_master(body: PartMasterImportBody, ws: WsContext = Depends(get_ws)):
    if body.format != "fir_part_master_v1":
        raise HTTPException(
            status_code=400,
            detail='Expected format "fir_part_master_v1" (download from legacy part page or SaaS export).',
        )
    slice_body = PartMasterSlice(
        part=body.part,
        spec_rows=body.spec_rows,
        ccp_rows=body.ccp_rows,
        material_rows=body.material_rows,
        coating_rows=body.coating_rows,
    )
    pn = slice_body.part.part_no
    cust = _get_customer_for_part_upsert(ws, None)
    existing = ws.db.scalars(
        select(PartV2.part_no).where(
            PartV2.company_id == ws.company.id,
            PartV2.customer_id == cust.id,
        )
    ).all()
    existing_sanitized = {sanitize_part_master_alnum_upper(r) for r in existing}
    existing_sanitized.discard("")
    if pn in existing_sanitized:
        raise HTTPException(
            status_code=400,
            detail=f'Part number "{pn}" is already in Parts master for this customer — delete it first or use a different part number.',
        )
    p = _apply_part_master_slice(ws, slice_body, customer_id=cust.id)
    ws.db.commit()
    ws.db.refresh(p)
    return {"ok": True, "part_id": p.id, "part_no": p.part_no}


@router.post("/parts/import-bundle")
def import_part_bundle(body: PartMasterBundleBody, ws: WsContext = Depends(get_ws)):
    if body.format != "fir_part_master_bundle_v1":
        raise HTTPException(
            status_code=400,
            detail='Expected format "fir_part_master_bundle_v1" (use Download all parts JSON).',
        )
    if not body.parts:
        raise HTTPException(status_code=400, detail="parts array is empty")
    cust = _get_customer_for_part_upsert(ws, None)
    existing_rows = ws.db.scalars(
        select(PartV2.part_no).where(
            PartV2.company_id == ws.company.id,
            PartV2.customer_id == cust.id,
        )
    ).all()
    existing_sanitized = {sanitize_part_master_alnum_upper(r) for r in existing_rows}
    existing_sanitized.discard("")
    conflicts: list[str] = []
    for sl in body.parts:
        pn = sl.part.part_no
        if pn in existing_sanitized:
            conflicts.append(pn)
    if conflicts:
        shown = conflicts[:12]
        more = len(conflicts) - len(shown)
        tail = f"; and {more} more" if more > 0 else ""
        raise HTTPException(
            status_code=400,
            detail="Part number(s) already in Parts master for this customer — remove duplicates from the import or delete the existing part(s) first: "
            + ", ".join(shown)
            + tail,
        )
    last: PartV2 | None = None
    for sl in body.parts:
        last = _apply_part_master_slice(ws, sl, customer_id=cust.id)
    ws.db.commit()
    if last:
        ws.db.refresh(last)
    return {"ok": True, "imported": len(body.parts)}


@router.get("/parts/excel-template")
def download_part_master_excel_template():
    """Blank workbook: Parts, Section_A–D with header rows matching import parser."""
    body = build_part_master_template_xlsx()
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="fir_part_master_template.xlsx"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/parts/preview-excel-master")
async def preview_part_master_excel(
    file: UploadFile = File(...),
    ws: WsContext = Depends(get_ws),
):
    """Parse .xlsx/.xls → fir_part_master_bundle_v1 JSON (no DB write)."""
    fn = (file.filename or "").lower()
    if not (fn.endswith(".xlsx") or fn.endswith(".xls")):
        raise HTTPException(status_code=400, detail="Upload .xlsx or .xls")
    raw = await file.read()
    try:
        bundle_dict = parse_parts_excel_to_bundle_dict(
            raw,
            source_filename=file.filename,
            first_sheet_only=True,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        PartMasterBundleBody(**bundle_dict)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Structure error: {e}") from e
    return JSONResponse(content=bundle_dict)


@router.post("/parts/import-excel-master")
async def import_part_master_excel(
    file: UploadFile = File(...),
    ws: WsContext = Depends(get_ws),
):
    """Parse Excel and upsert parts + A–D (same rules as JSON import-bundle)."""
    fn = (file.filename or "").lower()
    if not (fn.endswith(".xlsx") or fn.endswith(".xls")):
        raise HTTPException(status_code=400, detail="Upload .xlsx or .xls")
    raw = await file.read()
    try:
        bundle_dict = parse_parts_excel_to_bundle_dict(raw, source_filename=file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    try:
        body = PartMasterBundleBody(**bundle_dict)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Structure error: {e}") from e
    cust = _get_customer_for_part_upsert(ws, None)
    last: PartV2 | None = None
    for sl in body.parts:
        last = _apply_part_master_slice(ws, sl, customer_id=cust.id)
    ws.db.commit()
    if last:
        ws.db.refresh(last)
    return {"ok": True, "imported": len(body.parts), "format": body.format}


@router.get("/parts/export-all")
def export_all_parts_master(
    customer_id: int | None = Depends(optional_customer_id_query),
    ws: WsContext = Depends(get_ws),
):
    q = select(PartV2).where(PartV2.company_id == ws.company.id)
    if customer_id is not None:
        q = q.where(PartV2.customer_id == customer_id)
    rows = ws.db.execute(q.order_by(PartV2.part_no)).scalars().all()
    parts_out: list[dict[str, Any]] = []
    for p in rows:
        inner = _serialize_part_detail(ws, p)

        # Be defensive with legacy-imported data: some old rows may have
        # non-string values in text fields. Normalize everything to strings
        # so JSON export never fails with validation/type parse errors.
        def _safe_text(v: Any) -> str:
            return "" if v is None else str(v)

        spec_rows = [
            {
                "parameter": _safe_text(r.get("parameter")),
                "specification": _safe_text(r.get("specification")),
                "special_char": _safe_text(r.get("special_char")),
                "method_of_inspection": _safe_text(r.get("method_of_inspection")),
            }
            for r in inner["spec_rows"]
        ]
        ccp_rows = [
            {
                "parameter": _safe_text(r.get("parameter")),
                "specification": _safe_text(r.get("specification")),
                "special_char": _safe_text(r.get("special_char")),
                "method_of_inspection": _safe_text(r.get("method_of_inspection")),
            }
            for r in inner["ccp_rows"]
        ]
        material_rows = [{"material_grade": _safe_text(m.get("material_grade"))} for m in inner["material_rows"]]
        coating_rows = [
            {
                "parameter": _safe_text(r.get("parameter")),
                "specification": _safe_text(r.get("specification")),
                "special_char": _safe_text(r.get("special_char")),
                "method_of_inspection": _safe_text(r.get("method_of_inspection")),
            }
            for r in inner["coating_rows"]
        ]
        parts_out.append(
            {
                "part": {
                    "part_no": _safe_text(inner["part_no"]),
                    "drawing_rev": _safe_text(inner.get("drawing_rev")),
                    "description": _safe_text(inner.get("description")),
                    "customer_id": inner.get("customer_id"),
                    "customer_vendor_code": _safe_text(inner.get("customer_vendor_code")),
                    "customer_name": _safe_text(inner.get("customer_name")),
                },
                "spec_rows": spec_rows,
                "ccp_rows": ccp_rows,
                "material_rows": material_rows,
                "coating_rows": coating_rows,
            }
        )
    payload = {
        "format": "fir_part_master_bundle_v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "exported_from": "saas",
        "parts": parts_out,
    }
    filename = "fir_all_parts_master.json"
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.delete("/parts/{part_id}/specs/{spec_row_id}")
def delete_spec_row(part_id: int, spec_row_id: int, ws: WsContext = Depends(get_ws)):
    p = _get_part(ws, part_id)
    row = ws.db.get(PartSpecV2, spec_row_id)
    if not row or row.part_id != p.id:
        raise HTTPException(status_code=404, detail="Not found")
    ws.db.delete(row)
    ws.db.commit()
    return {"ok": True}


# --- Upload & inspection ---
@router.post("/upload/invoice")
async def upload_invoice(ws: WsContext = Depends(get_ws), invoice_file: UploadFile = File(...)):
    customers = ws.db.execute(select(Customer).where(Customer.company_id == ws.company.id)).scalars().all()
    if not customers:
        raise HTTPException(status_code=400, detail="Add at least one customer before upload")
    if len(customers) > 1 and ws.customer is None:
        raise HTTPException(status_code=400, detail="select_customer_required", headers={"X-Reason": "select_customer"})

    fn = (invoice_file.filename or "").lower()
    if not (fn.endswith(".xlsx") or fn.endswith(".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx or .xls supported")
    raw = invoice_file.file.read()
    try:
        rows, columns = parse_invoice_excel(raw, filename=invoice_file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read Excel: {e}") from e

    return {"rows": rows, "columns": columns, "filename": invoice_file.filename or ""}


class EnrichBody(BaseModel):
    rows: list[dict[str, Any]]
    source_file: str | None = None


@router.post("/inspection/enrich")
def inspection_enrich(body: EnrichBody, ws: WsContext = Depends(get_ws)):
    cust_id = _resolve_default_customer_id(ws)
    parts = ws.db.execute(
        select(PartV2.id, PartV2.part_no, PartV2.drawing_rev, PartV2.customer_id, PartV2.description).where(
            PartV2.company_id == ws.company.id
        )
    ).fetchall()
    part_rows = [(str(pno).strip(), dr, pid, cid, desc) for pid, pno, dr, cid, desc in parts]
    counts = {
        r[0]: r[1]
        for r in ws.db.execute(
            select(PartSpecV2.part_id, func.count(PartSpecV2.id)).group_by(PartSpecV2.part_id)
        ).fetchall()
    }
    enriched = enrich_rows_with_parts(
        body.rows,
        part_rows=part_rows,
        workspace_customer_id=cust_id,
        param_count_by_part_id=counts,
    )
    customer = None
    if ws.customer:
        customer = {
            "id": ws.customer.id,
            "vendor_code": ws.customer.vendor_code,
            "name": ws.customer.name,
        }
    return {
        "rows": enriched,
        "customer": customer,
        "current_date": datetime.now(timezone.utc).date().isoformat(),
    }


@router.post("/inspection/preview-fir-intelligence")
def inspection_preview_fir_intelligence(body: EnrichBody, ws: WsContext = Depends(get_ws)):
    """Predict new vs duplicate intelligence rows (same logic as record-reports) for quota UI."""
    rows_in = body.rows or []
    parsed = [parse_row_for_intelligence(r, company_id=ws.company.id) for r in rows_in]
    prev = preview_fir_intelligence_batch(ws.db, company_id=ws.company.id, parsed=parsed)
    return {
        "rows_total": prev.rows_total,
        "rows_invalid": prev.rows_invalid,
        "prospective_new_intelligence_records": prev.prospective_new,
        "prospective_duplicate_intelligence_records": prev.prospective_duplicates,
    }


@router.get("/inspection/fir-quota")
def inspection_fir_quota(
    n: int = 0,
    ws: WsContext = Depends(get_ws),
):
    """Headroom for batch ZIP: invoices + FIR reports share the same monthly cap when billing is on."""
    settings = get_settings()
    today = billing_today()
    company = ws.company
    inv = count_invoices_this_month(ws.db, company.id, today)
    fir = count_fir_reports_this_month(ws.db, company.id, today)
    combined = count_combined_usage_this_month(ws.db, company.id, today)
    limit = plan_invoice_limit(ws.db, company.plan_type)
    want = max(0, n)
    ok, msg = can_record_fir_reports(
        ws.db, company, n=want, enable_subscription=settings.enable_subscription, today=today
    )
    remaining = None if limit is None else max(0, (limit or 0) - combined)
    after = None if limit is None else max(0, (limit or 0) - combined - want)
    return {
        "allowed_for_n": ok,
        "message": msg,
        "invoices_this_month": inv,
        "fir_reports_this_month": fir,
        "usage_this_month": combined,
        "usage_limit": limit,
        "remaining": remaining,
        "would_remain_after_n": after,
    }


@router.post("/inspection/record-reports")
def inspection_record_reports(body: EnrichBody, ws: WsContext = Depends(get_ws)):
    """Persist deduplicated FIR intelligence events after a batch download. FIR PDFs always succeed independently."""
    settings = get_settings()
    today = billing_today()
    rows_in = body.rows or []
    parsed = [parse_row_for_intelligence(r, company_id=ws.company.id) for r in rows_in]
    prev = preview_fir_intelligence_batch(ws.db, company_id=ws.company.id, parsed=parsed)
    prospective_new = prev.prospective_new

    ok, msg = can_record_fir_reports(
        ws.db, ws.company, n=prospective_new, enable_subscription=settings.enable_subscription, today=today
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=msg or "Usage limit exceeded")

    cust_id = ws.customer.id if ws.customer else None
    summary = ingest_fir_intelligence_rows(
        ws.db,
        company_id=ws.company.id,
        customer_id=cust_id,
        rows=rows_in,
        source_file=body.source_file,
    )
    ws.db.commit()

    combined = count_combined_usage_this_month(ws.db, ws.company.id, today)
    return {
        "rows_processed": summary.rows_total,
        "rows_invalid": summary.rows_invalid,
        "new_intelligence_records": summary.new_records,
        "duplicate_intelligence_records": summary.duplicate_records,
        "fir_reports_generated": summary.reports_generated,
        "invoices_this_month": count_invoices_this_month(ws.db, ws.company.id, today),
        "fir_reports_this_month": count_fir_reports_this_month(ws.db, ws.company.id, today),
        "usage_this_month": combined,
        "usage_limit": plan_invoice_limit(ws.db, ws.company.plan_type),
        "recorded": summary.new_records,
    }


FirAssetWhich = Literal["logo", "inspector_signature", "quality_signature"]

# Browsers reuse GETs across many FIR iframes (same URL per asset); cuts repeat S3 GetObject per page load.
_FIR_ASSET_CACHE_CONTROL = {"Cache-Control": "private, max-age=120"}


@router.get("/fir-asset")
def fir_workspace_asset(
    which: FirAssetWhich = Query(..., description="Which company settings image to stream"),
    user: CompanyUser = Depends(get_company_user_from_token_str),
    db: Session = Depends(get_db_session),
    admin_impersonation: bool = Depends(impersonated_by_admin_from_request),
):
    """Same-origin image bytes for FIR HTML (logos/signatures) so html2canvas/PDF capture works with S3."""
    app_settings = get_settings()
    company = get_company_for_user(user, db)
    if not can_access_fir_workspace(
        company,
        enable_subscription=app_settings.enable_subscription,
        today=billing_today(),
        impersonated_by_admin=admin_impersonation,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": FIR_WORKSPACE_FORBIDDEN_CODE,
                "message": FIR_WORKSPACE_FORBIDDEN_MESSAGE,
            },
        )
    st = db.get(CompanySettings, company.id)
    if not st:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No company settings")

    blob_attr, mime_attr, path_attr = {
        "logo": ("logo_blob", "logo_mime", "logo_path"),
        "inspector_signature": ("inspector_signature_blob", "inspector_signature_mime", "inspector_signature_path"),
        "quality_signature": ("quality_signature_blob", "quality_signature_mime", "quality_signature_path"),
    }[which]
    blob_v = getattr(st, blob_attr)
    mime_v = getattr(st, mime_attr)
    path_v = getattr(st, path_attr)
    media_default = "image/png"
    media = ((mime_v or media_default).split(";")[0].strip() or media_default) if mime_v else media_default

    if blob_v:
        return Response(content=bytes(blob_v), media_type=media, headers=_FIR_ASSET_CACHE_CONTROL)

    path_s = (path_v or "").strip()
    if not path_s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not configured")

    if path_s.startswith("http://") or path_s.startswith("https://"):
        try:
            req = Request(path_s, headers={"User-Agent": "TheAIQualisys-FIR/1.0"})
            with urlopen(req, timeout=45) as resp:
                data = resp.read()
            ct = (resp.headers.get("Content-Type") or media_default).split(";")[0].strip()
            return Response(content=data, media_type=ct or media_default, headers=_FIR_ASSET_CACHE_CONTROL)
        except (HTTPError, URLError, TimeoutError, OSError):
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch asset URL")

    if s3_assets_configured(app_settings) and is_company_scoped_storage_key(company.id, path_s):
        try:
            data, ct = fetch_s3_object_bytes(app_settings, path_s)
            return Response(content=data, media_type=(ct.split(";")[0].strip() if ct else media) or media, headers=_FIR_ASSET_CACHE_CONTROL)
        except Exception:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to load asset from storage")

    upload_root = _upload_root().resolve()
    prefix = str(company.id) + "/"
    if path_s.startswith(prefix):
        local = (upload_root / path_s).resolve()
        try:
            local.relative_to(upload_root)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset file not found")
        if local.is_file():
            mt, _ = mimetypes.guess_type(str(local))
            return FileResponse(local, media_type=mt or media or "application/octet-stream", headers=_FIR_ASSET_CACHE_CONTROL)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset file not found")


# --- FIR preview (HTML) — Bearer or ?token= for new tab ---
@router.get("/fir-preview", response_class=HTMLResponse)
def fir_preview(
    request: Request,
    user: CompanyUser = Depends(get_company_user_from_token_str),
    db: Session = Depends(get_db_session),
    admin_impersonation: bool = Depends(impersonated_by_admin_from_request),
    partName: str = "",
):
    company = get_company_for_user(user, db)
    settings = get_settings()
    if not can_access_fir_workspace(
        company,
        enable_subscription=settings.enable_subscription,
        today=billing_today(),
        impersonated_by_admin=admin_impersonation,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": FIR_WORKSPACE_FORBIDDEN_CODE,
                "message": FIR_WORKSPACE_FORBIDDEN_MESSAGE,
            },
        )
    part_no = (partName or "").strip()
    spec_data: list[dict] = []
    ccp_data: list[dict] = []
    material_data: list[dict] = []
    coating_data: list[dict] = []
    if part_no:
        part = db.execute(
            select(PartV2).where(PartV2.company_id == company.id, PartV2.part_no == part_no)
        ).scalar_one_or_none()
        if part:
            spec_data = [
                {
                    "parameter": s.parameter,
                    "specification": s.specification,
                    "special_char": s.special_char,
                    "method_of_inspection": s.method_of_inspection,
                }
                for s in db.execute(select(PartSpecV2).where(PartSpecV2.part_id == part.id).order_by(PartSpecV2.id))
                .scalars()
                .all()
            ]
            ccp_data = [
                {
                    "parameter": s.parameter,
                    "specification": s.specification,
                    "special_char": s.special_char,
                    "method_of_inspection": s.method_of_inspection,
                }
                for s in db.execute(
                    select(PartComplaintV2).where(PartComplaintV2.part_id == part.id).order_by(PartComplaintV2.id)
                )
                .scalars()
                .all()
            ]
            material_data = [
                {"material_grade": m.material_grade}
                for m in db.execute(
                    select(PartMaterialV2).where(PartMaterialV2.part_id == part.id).order_by(PartMaterialV2.id)
                )
                .scalars()
                .all()
            ]
            coating_data = [
                {
                    "parameter": s.parameter,
                    "specification": s.specification,
                    "special_char": s.special_char,
                    "method_of_inspection": s.method_of_inspection,
                }
                for s in db.execute(
                    select(PartCoatingV2).where(PartCoatingV2.part_id == part.id).order_by(PartCoatingV2.id)
                )
                .scalars()
                .all()
            ]

    st = db.execute(
        _company_settings_select(company.id, load_asset_blobs=not s3_assets_configured(settings))
    ).scalar_one_or_none()
    quali_font_data_uri, quali_font_format = _quali_font_src_from_settings(settings, st)
    if not quali_font_data_uri:
        quali_font_data_uri, quali_font_format = _default_static_quali_font()

    fir_ctx_settings = _settings_dict_for_fir(db, company.id)
    token = request.query_params.get("token") or ""
    api_origin = str(request.base_url).rstrip("/")
    for which_key, settings_key in (
        ("logo", "logo_path"),
        ("inspector_signature", "inspector_signature_path"),
        ("quality_signature", "quality_signature_path"),
    ):
        v = fir_ctx_settings.get(settings_key)
        if v and token:
            q = f"which={which_key}&token={quote(token, safe='')}"
            fir_ctx_settings[settings_key] = f"{api_origin}/api/app/fir-asset?{q}"

    api_static_base = api_origin + "/api/app/static/"

    return templates.TemplateResponse(
        request=request,
        name="fir_preview.html",
        context={
            "settings": fir_ctx_settings,
            "spec_data": spec_data,
            "ccp_data": ccp_data,
            "material_data": material_data,
            "coating_data": coating_data,
            "quali_font_data_uri": quali_font_data_uri,
            "quali_font_format": quali_font_format,
            "api_static_base": api_static_base,
        },
    )


@router.get("/static/{path:path}")
def serve_static(path: str):
    root = _BACKEND_STATIC
    file_path = (root / path).resolve()
    try:
        file_path.relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=404)
    if not file_path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(file_path)


@router.get("/uploads/{path:path}")
def serve_upload(path: str, ws: WsContext = Depends(get_ws)):
    prefix = str(ws.company.id) + "/"
    if not path.startswith(prefix):
        raise HTTPException(status_code=403)
    full = (_upload_root() / path).resolve()
    try:
        full.relative_to(_upload_root().resolve())
    except ValueError:
        raise HTTPException(status_code=404)
    if not full.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(full)


@router.get("/upload-check")
def upload_precheck(ws: WsContext = Depends(get_ws)):
    customers = ws.db.execute(select(Customer).where(Customer.company_id == ws.company.id)).scalars().all()
    if not customers:
        return {"ok": False, "reason": "no_customers"}
    if len(customers) == 1:
        return {"ok": True, "auto_customer_id": customers[0].id}
    if ws.customer is None:
        return {"ok": False, "reason": "select_customer"}
    return {"ok": True, "customer_id": ws.customer.id}
