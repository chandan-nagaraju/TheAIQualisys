"""Machine license API route foundation (Phase 1 stubs; Phase 7 implements Ed25519).

Paths match the approved central authority:
  POST /api/license/activate
  POST /api/license/validate
  POST /api/license/refresh
  POST /api/license/deactivate
  GET  /api/license/public-key
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from app.licensing.feature_flag import require_desktop_licensing_enabled
from app.licensing.schemas import MachineApiStubOut

router = APIRouter(prefix="/api/license", tags=["license-machine"])

_PHASE1_DETAIL = (
    "Machine license API is reserved. Ed25519 activate/validate/refresh/deactivate "
    "and public-key serving ship in Phase 7. Trial activation ships in Phase 7A."
)


def _stub_response() -> JSONResponse:
    body = MachineApiStubOut(detail=_PHASE1_DETAIL).model_dump()
    return JSONResponse(status_code=status.HTTP_501_NOT_IMPLEMENTED, content=body)


@router.post("/activate")
def license_activate(
    request: Request,
    _: None = Depends(require_desktop_licensing_enabled),
):
    del request
    return _stub_response()


@router.post("/validate")
def license_validate(
    request: Request,
    _: None = Depends(require_desktop_licensing_enabled),
):
    del request
    return _stub_response()


@router.post("/refresh")
def license_refresh(
    request: Request,
    _: None = Depends(require_desktop_licensing_enabled),
):
    del request
    return _stub_response()


@router.post("/deactivate")
def license_deactivate(
    request: Request,
    _: None = Depends(require_desktop_licensing_enabled),
):
    del request
    return _stub_response()


@router.get("/public-key")
def license_public_key(
    _: None = Depends(require_desktop_licensing_enabled),
):
    return _stub_response()
