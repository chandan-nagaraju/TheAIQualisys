import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.config import Settings, get_settings
from app.cors_origins import expand_cors_origins
from app.database import Base, SessionLocal, engine
from app.s3_assets import s3_assets_configured
from app.migration_runner import apply_sql_migrations
from app.models import PlatformAdmin
from app.pricing_seed import ensure_module_pricing_seeded
from app.routers import admin, auth, billing, cron, modules, pricing_public, subscription
from app.routers.v2.endpoints import router as v2_router
from app.routers.workspace import fir_preview as legacy_fir_preview_alias, router as workspace_router
from app.security import hash_password, verify_password

logger = logging.getLogger(__name__)


def _startup_error_json(request: Request) -> str | None:
    err = getattr(request.app.state, "startup_error", None)
    if err is None:
        return None
    s = str(err).strip()
    return s or None


def _sync_lifespan_heavy(settings: Settings) -> None:
    # Run SQL migrations BEFORE create_all so migration 009 can rename fir_report_events → fir_events.
    # If create_all runs first, it creates an empty fir_events and the rename is skipped (data stays
    # in fir_report_events while the ORM reads empty fir_events — FIR Intelligence shows zero events).
    apply_sql_migrations(engine, settings.backend_root)
    Base.metadata.create_all(bind=engine)
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Yield quickly so load balancers (e.g. Railway healthchecks) get HTTP 200 from /health
    while migrations and seeding run in a worker thread.
    """
    settings = get_settings()
    app.state.startup_complete = False
    app.state.startup_error = None
    # pending | ok | error — makes /health clear when db_ready is false but nothing failed yet
    app.state.startup_status = "pending"
    app.state.startup_started_monotonic = time.monotonic()

    async def _run_startup() -> None:
        try:
            await asyncio.to_thread(_sync_lifespan_heavy, settings)
        except Exception as e:
            logger.exception("Background startup (migrations / seed) failed")
            msg = f"{type(e).__name__}: {e}"[:4000].strip()
            app.state.startup_error = msg or f"{type(e).__name__} (no message)"
            app.state.startup_status = "error"
            return
        app.state.startup_error = None
        app.state.startup_complete = True
        app.state.startup_status = "ok"
        app.state.startup_elapsed_sec = round(time.monotonic() - app.state.startup_started_monotonic, 2)

    asyncio.create_task(_run_startup())
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="FIR Automation SaaS API", lifespan=lifespan)

    raw_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    pub = (settings.public_app_url or "").strip().rstrip("/")
    if pub:
        raw_origins.append(pub)
    # Add apex ⟷ www variants so users on either URL pass CORS (common production footgun).
    origins = expand_cors_origins(raw_origins)
    if not origins:
        origins = ["http://localhost:5173"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
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
    app.include_router(cron.router)
    app.include_router(cron.router, prefix="/api")
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

    @app.get("/")
    def service_root(request: Request):
        """Visiting the bare Railway URL: quick status without opening /health."""
        ready = getattr(request.app.state, "startup_complete", False)
        status = getattr(request.app.state, "startup_status", "pending")
        elapsed = round(time.monotonic() - getattr(request.app.state, "startup_started_monotonic", time.monotonic()), 2)
        return {
            "service": "FIR Automation SaaS API",
            "health": "/health",
            "docs": "/docs",
            "db_ready": ready,
            "startup_status": status,
            "startup_elapsed_sec": getattr(request.app.state, "startup_elapsed_sec", None) if ready else elapsed,
            "startup_error": _startup_error_json(request),
        }

    @app.get("/health")
    def health(request: Request):
        cfg = get_settings()
        ready = getattr(request.app.state, "startup_complete", False)
        status = getattr(request.app.state, "startup_status", "pending")
        elapsed = round(time.monotonic() - getattr(request.app.state, "startup_started_monotonic", time.monotonic()), 2)
        # Always HTTP 200 when the process is up so load balancers mark the instance healthy.
        # Use db_ready / startup_error for observability and alerting.
        return {
            "status": "ok",
            "enable_subscription": cfg.enable_subscription,
            # True when all S3 env vars are set (AWS keys, region, bucket, PUBLIC_S3_BASE_URL).
            # Use this after deploy to confirm Railway/hosting picked up secrets without opening settings.
            "s3_assets_configured": s3_assets_configured(cfg),
            "db_ready": ready,
            "startup_status": status,
            "startup_elapsed_sec": getattr(request.app.state, "startup_elapsed_sec", None) if ready else elapsed,
            "startup_error": _startup_error_json(request),
        }

    return app


app = create_app()
