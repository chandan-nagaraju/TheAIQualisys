import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.dates import billing_today
from app.deps import company_impersonated_by_admin, get_current_company_user, get_db_session, get_company_for_user
from app.email_util import is_email_configured, send_password_reset_email
from app.models import Company, CompanyUser, PasswordResetToken, PlanType, PlatformAdmin, SubscriptionStatus
from app.schemas import (
    ChangePasswordRequest,
    CompanyOut,
    CompanyUserOut,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    ResetPasswordRequest,
    SignupRequest,
    TokenResponse,
    UnifiedLoginResponse,
)
from app.security import (
    create_access_token,
    create_admin_token,
    hash_password,
    verify_password,
    verify_password_and_upgrade,
)
from app.subscription_logic import (
    can_access_fir_workspace,
    can_create_invoice,
    can_record_fir_reports,
    count_combined_usage_this_month,
    count_fir_reports_this_month,
    count_invoices_this_month,
    plan_invoice_limit,
    subscription_is_active,
    trial_is_valid,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db_session)):
    existing = db.execute(select(CompanyUser).where(CompanyUser.email == body.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    vc = body.vendor_code.strip()
    exists_vc = db.execute(select(Company).where(Company.vendor_code == vc)).scalar_one_or_none()
    if exists_vc:
        raise HTTPException(status_code=400, detail="Vendor code already in use")

    today = billing_today()
    trial_end = today + timedelta(days=7)

    company = Company(
        company_name=body.company_name.strip(),
        vendor_code=vc,
        trial_start_date=today,
        trial_end_date=trial_end,
        plan_type=PlanType.basic.value,
        subscription_status=SubscriptionStatus.trial.value,
    )
    db.add(company)
    db.flush()

    user = CompanyUser(
        company_id=company.id,
        email=str(body.email).lower().strip(),
        password_hash=hash_password(body.password),
        name=None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(
        str(user.id),
        {"company_id": company.id},
    )
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db_session)):
    ident = body.identifier.strip()
    password = body.password

    user: CompanyUser | None = None
    if "@" in ident:
        user = db.execute(select(CompanyUser).where(CompanyUser.email == ident.lower())).scalar_one_or_none()
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if bool(user.is_blocked):
            raise HTTPException(status_code=403, detail="User account is blocked")
    else:
        company = db.execute(select(Company).where(Company.vendor_code == ident)).scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        users = db.execute(select(CompanyUser).where(CompanyUser.company_id == company.id)).scalars().all()
        for u in users:
            if verify_password(password, u.password_hash):
                user = u
                break
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if bool(user.is_blocked):
            raise HTTPException(status_code=403, detail="User account is blocked")

    token = create_access_token(str(user.id), {"company_id": user.company_id})
    return TokenResponse(access_token=token)


@router.post("/unified-login", response_model=UnifiedLoginResponse)
def unified_login(body: LoginRequest, db: Session = Depends(get_db_session)):
    """
    Single sign-in: if identifier is an email and matches a platform admin, returns admin JWT;
    otherwise uses company login (email or vendor code).
    """
    ident = body.identifier.strip()
    password = body.password

    if "@" in ident:
        admin = db.execute(
            select(PlatformAdmin).where(PlatformAdmin.email == ident.lower())
        ).scalar_one_or_none()
        if admin:
            ok, upgraded_hash = verify_password_and_upgrade(password, admin.password_hash)
            if ok:
                if upgraded_hash:
                    admin.password_hash = upgraded_hash
                    db.commit()
                return UnifiedLoginResponse(
                    access_token=create_admin_token(str(admin.id)),
                    role="platform_admin",
                )
            raise HTTPException(status_code=401, detail="Invalid credentials")

    user: CompanyUser | None = None
    if "@" in ident:
        user = db.execute(select(CompanyUser).where(CompanyUser.email == ident.lower())).scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if bool(user.is_blocked):
            raise HTTPException(status_code=403, detail="User account is blocked")
        ok, upgraded_hash = verify_password_and_upgrade(password, user.password_hash)
        if not ok:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if upgraded_hash:
            user.password_hash = upgraded_hash
            db.commit()
    else:
        company = db.execute(select(Company).where(Company.vendor_code == ident)).scalar_one_or_none()
        if not company:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        users = db.execute(select(CompanyUser).where(CompanyUser.company_id == company.id)).scalars().all()
        for u in users:
            ok, upgraded_hash = verify_password_and_upgrade(password, u.password_hash)
            if ok:
                if upgraded_hash:
                    u.password_hash = upgraded_hash
                    db.commit()
                user = u
                break
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if bool(user.is_blocked):
            raise HTTPException(status_code=403, detail="User account is blocked")

    token = create_access_token(str(user.id), {"company_id": user.company_id})
    return UnifiedLoginResponse(access_token=token, role="company")


@router.get("/me", response_model=MeResponse)
def me(
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
    admin_impersonation: bool = Depends(company_impersonated_by_admin),
):
    settings = get_settings()
    company = get_company_for_user(user, db)
    today = billing_today()
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
        trial_active=trial_is_valid(company, today),
        subscription_active=subscription_is_active(company, today),
        subscription_message=None if ok else sub_msg,
        can_access_fir_workspace=can_access_fir_workspace(
            company,
            enable_subscription=settings.enable_subscription,
            today=today,
            impersonated_by_admin=admin_impersonation,
        ),
    )


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db_session)):
    settings = get_settings()
    email = str(body.email).lower().strip()
    if not is_email_configured(settings):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset email is not configured. Set EMAIL_FROM, SMTP_HOST and SMTP_PORT.",
        )
    user = db.execute(select(CompanyUser).where(CompanyUser.email == email)).scalar_one_or_none()
    if not user:
        return {"ok": True}
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    db.add(PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=expires))
    db.commit()
    link = f"{settings.public_app_url.rstrip('/')}/reset-password?token={raw}"
    try:
        send_password_reset_email(settings, user.email, link)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Could not send email: {exc!s}",
        ) from exc
    return {"ok": True}


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db_session)):
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    row = db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not row:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < now:
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")
    user = db.get(CompanyUser, row.user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset link")
    user.password_hash = hash_password(body.new_password)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
