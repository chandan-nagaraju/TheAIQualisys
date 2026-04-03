"""Public read-only module pricing (landing, product pages)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db_session
from app.pricing_catalog import list_all_pricing_rows
from app.schemas import ModulePricingPublicOut

router = APIRouter(prefix="/api/pricing", tags=["pricing"])


@router.get("/modules", response_model=list[ModulePricingPublicOut])
def list_module_pricing(db: Session = Depends(get_db_session)):
    rows = list_all_pricing_rows(db)
    return [ModulePricingPublicOut.model_validate(r) for r in rows]
