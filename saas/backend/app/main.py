from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.s3_assets import s3_assets_configured
from app.migration_runner import apply_sql_migrations
from app.models import PlatformAdmin
from app.pricing_seed import ensure_module_pricing_seeded
from app.routers import admin, auth, billing, modules, pricing_public, subscription
from app.routers.v2.endpoints import router as v2_router
from app.routers.workspace import fir_preview as legacy_fir_preview_alias, router as workspace_router
from app.security import hash_password, verify_password


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    # Ensure incremental SQL migrations are applied in hosted environments
    # (e.g. Supabase/Render) after base tables exist.
    apply_sql_migrations(engine, settings.backend_root)
    db = SessionLocal()
    try:
        ensure_module_pricing_seeded(db)
        if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
            email = settings.bootstrap_admin_email.lower().strip()
            admin = db.execute(select(PlatformAdmin).where(PlatformAdmin.email == email)).scalar_one_or_none()
            if not admin:
                db.add(
                    PlatformAdmin(
                        email=email,
                        password_hash=hash_password(settings.bootstrap_admin_password),
                    )
                )
                db.commit()
            elif not verify_password(settings.bootstrap_admin_password, admin.password_hash):
                admin.password_hash = hash_password(settings.bootstrap_admin_password)
                db.add(admin)
                db.commit()
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="FIR Automation SaaS API", lifespan=lifespan)

    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    # Hosted setups often set PUBLIC_APP_URL for reset links but forget CORS_ORIGINS; allow the SPA either way.
    pub = (settings.public_app_url or "").strip().rstrip("/")
    if pub and pub not in origins:
        origins.append(pub)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(auth.router, prefix="/api")
    app.include_router(pricing_public.router)
    app.include_router(billing.router)
    app.include_router(modules.router)
    app.include_router(subscription.router)
    app.include_router(subscription.router, prefix="/api")
    app.include_router(admin.router)
    app.include_router(admin.router, prefix="/api")
    app.include_router(v2_router)
    app.include_router(workspace_router)
    # Backward-compatible alias for older frontend bundles that call
    # /api/ap/fir-preview (missing one "p" in "app").
    app.add_api_route(
        "/api/ap/fir-preview",
        legacy_fir_preview_alias,
        methods=["GET"],
        response_class=HTMLResponse,
        include_in_schema=False,
    )

    @app.get("/health")
    def health():
        cfg = get_settings()
        return {
            "status": "ok",
            "enable_subscription": cfg.enable_subscription,
            # True when all S3 env vars are set (AWS keys, region, bucket, PUBLIC_S3_BASE_URL).
            # Use this after deploy to confirm Railway/hosting picked up secrets without opening settings.
            "s3_assets_configured": s3_assets_configured(cfg),
        }

    return app


app = create_app()
