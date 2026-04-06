from collections.abc import Generator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import Company, CompanyUser, PlatformAdmin
from app.security import decode_access_token, decode_admin_token
from app.subscription_logic import can_access_app, can_create_invoice

bearer_scheme = HTTPBearer(auto_error=False)


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
    cid = payload.get("company_id")
    if cid is not None and int(cid) != user.company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token mismatch")
    return user


def get_company_for_user(user: CompanyUser, db: Session) -> Company:
    company = db.get(Company, user.company_id)
    if not company:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company not found")
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
    return user
