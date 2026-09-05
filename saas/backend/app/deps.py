from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Company, CompanyUser, PlatformAdmin
from app.security import decode_access_token, decode_admin_token
from app.dates import billing_today
from app.subscription_logic import can_access_app, can_create_invoice, sync_subscription_status_from_dates

bearer_scheme = HTTPBearer(auto_error=False)


def impersonated_by_admin_from_token(token: str) -> bool:
    p = decode_access_token(token)
    return bool(p and p.get("typ") == "company" and p.get("impersonated_by_admin"))


def company_impersonated_by_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> bool:
    if not creds or creds.scheme.lower() != "bearer":
        return False
    return impersonated_by_admin_from_token(creds.credentials)


def get_db_session() -> Generator[Session, None, None]:
    yield from get_db()


def get_current_company_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
) -> CompanyUser:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_access_token(creds.credentials)
    if not payload or payload.get("typ") != "company":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.get(CompanyUser, int(sub))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if bool(user.is_blocked):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is blocked. Contact admin.")
    cid = payload.get("company_id")
    if cid is not None and int(cid) != user.company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token mismatch")
    return user


def get_oauth_company_user(
    user: CompanyUser = Depends(get_current_company_user),
    impersonated: bool = Depends(company_impersonated_by_admin),
) -> CompanyUser:
    """Company user for desktop OAuth only.

    Admin-impersonated company JWTs may access the SPA for support, but must never
    authorize, preview, consent, or revoke desktop OAuth sessions.
    """
    if impersonated:
        # Imported lazily to avoid circular imports (oauth → deps).
        from app.oauth.constants import ERR_ACCESS_DENIED
        from app.oauth.errors import OAuthError

        raise OAuthError(
            ERR_ACCESS_DENIED,
            description="Desktop authorization requires a direct company login",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return user


def get_company_for_user(user: CompanyUser, db: Session) -> Company:
    company = db.get(Company, user.company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company not found")
    if sync_subscription_status_from_dates(company, billing_today()):
        db.add(company)
        db.commit()
        db.refresh(company)
    return company


def require_subscription_access(
    user: CompanyUser = Depends(get_current_company_user),
    db: Session = Depends(get_db_session),
) -> tuple[CompanyUser, Company]:
    settings = get_settings()
    company = get_company_for_user(user, db)
    if not can_access_app(company, enable_subscription=settings.enable_subscription):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return user, company


def require_invoice_create_allowed(
    user_company: tuple[CompanyUser, Company] = Depends(require_subscription_access),
    db: Session = Depends(get_db_session),
) -> tuple[CompanyUser, Company]:
    user, company = user_company
    settings = get_settings()
    ok, msg = can_create_invoice(db, company, enable_subscription=settings.enable_subscription)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=msg or "Cannot create invoice",
        )
    return user, company


def get_platform_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db_session),
) -> PlatformAdmin:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_admin_token(creds.credentials)
    if not payload or payload.get("typ") != "platform_admin":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    admin = db.get(PlatformAdmin, int(sub))
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")
    return admin


def get_bearer_token_or_query(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if creds and creds.scheme.lower() == "bearer":
        return creds.credentials
    token = request.query_params.get("token")
    if token:
        return token
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def impersonated_by_admin_from_request(
    token: str = Depends(get_bearer_token_or_query),
) -> bool:
    return impersonated_by_admin_from_token(token)


def get_company_user_from_token_str(
    token: str = Depends(get_bearer_token_or_query),
    db: Session = Depends(get_db_session),
) -> CompanyUser:
    payload = decode_access_token(token)
    if not payload or payload.get("typ") != "company":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.get(CompanyUser, int(sub))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if bool(user.is_blocked):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is blocked. Contact admin.")
    return user
