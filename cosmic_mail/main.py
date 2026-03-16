from __future__ import annotations

from contextlib import asynccontextmanager
from importlib import resources
from pathlib import Path

import time
from collections import defaultdict
from threading import Lock

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from cosmic_mail.api.routes.approvals import router as approvals_router
from cosmic_mail.api.routes.search import router as search_router
from cosmic_mail.api.routes.attachments import router as attachments_router
from cosmic_mail.api.routes.agents import router as agents_router
from cosmic_mail.api.routes.drafts import router as drafts_router
from cosmic_mail.api.routes.domains import router as domains_router
from cosmic_mail.api.routes.mailboxes import router as mailboxes_router
from cosmic_mail.api.routes.organizations import router as organizations_router
from cosmic_mail.api.routes.system import router as system_router
from cosmic_mail.api.routes.threads import router as threads_router
from cosmic_mail.api.routes.webhooks import router as webhooks_router
from cosmic_mail.core.config import Settings, get_settings
from cosmic_mail.core.database import build_engine, build_session_factory, init_db
from cosmic_mail.domain.schemas import HealthRead, ReadyCheck
from cosmic_mail.services.dns import DNSVerifier, DnsPythonVerifier
from cosmic_mail.services.inbound import IMAPInboundMailboxClient, InboundMailboxClient
from cosmic_mail.services.james import JamesMailEngine
from cosmic_mail.services.mail_engine import MailEngine, NoopMailEngine
from cosmic_mail.services.outbound import OutboundMailSender, SMTPOutboundMailSender
from cosmic_mail.services.sync_manager import SyncWorker

WEB_STATIC_DIR = Path(__file__).resolve().parent / "web" / "static"

_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_rate_limit_lock = Lock()
_RATE_LIMIT_REQUESTS = 120
_RATE_LIMIT_WINDOW = 60  # seconds


def _check_rate_limit(key: str) -> bool:
    """Return True if the request is allowed, False if rate limited."""
    now = time.monotonic()
    cutoff = now - _RATE_LIMIT_WINDOW
    with _rate_limit_lock:
        timestamps = _rate_limit_store[key]
        # Prune old timestamps
        timestamps[:] = [t for t in timestamps if t > cutoff]
        if len(timestamps) >= _RATE_LIMIT_REQUESTS:
            return False
        timestamps.append(now)
    return True


def _mount_static_assets(app: FastAPI) -> bool:
    if WEB_STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(WEB_STATIC_DIR)), name="static")
        return True

    try:
        app.mount("/static", StaticFiles(packages=[("cosmic_mail.web", "static")]), name="static")
        return True
    except RuntimeError:
        return False


def _load_web_console_html() -> str:
    source_index = WEB_STATIC_DIR / "index.html"
    if source_index.is_file():
        return source_index.read_text(encoding="utf-8")

    package_index = resources.files("cosmic_mail.web").joinpath("static", "index.html")
    return package_index.read_text(encoding="utf-8")


def _build_mail_engine(settings: Settings) -> MailEngine:
    backend = settings.mail_engine_backend.lower()
    if backend == "james":
        return JamesMailEngine(
            base_url=settings.james_webadmin_url,
            admin_token=settings.james_admin_token,
        )
    return NoopMailEngine()


def _build_dns_verifier() -> DNSVerifier:
    return DnsPythonVerifier()


def _build_outbound_sender(settings: Settings) -> OutboundMailSender:
    return SMTPOutboundMailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        use_ssl=settings.smtp_use_ssl,
        use_starttls=settings.smtp_use_starttls,
        validate_certs=settings.smtp_validate_certs,
        auth_enabled=settings.smtp_auth_enabled,
        timeout_seconds=settings.smtp_timeout_seconds,
    )


def _build_inbound_client(settings: Settings) -> InboundMailboxClient:
    return IMAPInboundMailboxClient(
        host=settings.imap_host,
        port=settings.imap_port,
        use_ssl=settings.imap_use_ssl,
        use_starttls=settings.imap_use_starttls,
        validate_certs=settings.imap_validate_certs,
        timeout_seconds=settings.imap_timeout_seconds,
    )


def create_app(
    settings: Settings | None = None,
    *,
    mail_engine: MailEngine | None = None,
    dns_verifier: DNSVerifier | None = None,
    outbound_sender: OutboundMailSender | None = None,
    inbound_client: InboundMailboxClient | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()
    engine = build_engine(active_settings.database_url)
    session_factory = build_session_factory(engine)
    active_mail_engine = mail_engine or _build_mail_engine(active_settings)
    active_dns_verifier = dns_verifier or _build_dns_verifier()
    active_outbound_sender = outbound_sender or _build_outbound_sender(active_settings)
    active_inbound_client = inbound_client or _build_inbound_client(active_settings)
    active_sync_worker = SyncWorker(session_factory, active_settings, active_inbound_client)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(engine)
        active_sync_worker.start()
        yield
        active_sync_worker.stop()
        for resource in (active_mail_engine, active_outbound_sender, active_inbound_client):
            close = getattr(resource, "close", None)
            if callable(close):
                close()

    app = FastAPI(title=active_settings.app_name, lifespan=lifespan)

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        # Only rate-limit API endpoints
        if request.url.path.startswith("/v1"):
            client_ip = request.client.host if request.client else "unknown"
            api_key = request.headers.get("x-api-key") or ""
            rate_key = f"{client_ip}:{api_key[:16]}"
            if not _check_rate_limit(rate_key):
                return JSONResponse(
                    status_code=429,
                    content={"detail": "rate limit exceeded — max 120 requests per minute"},
                )
        return await call_next(request)

    app.state.settings = active_settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.mail_engine = active_mail_engine
    app.state.dns_verifier = active_dns_verifier
    app.state.outbound_sender = active_outbound_sender
    app.state.inbound_client = active_inbound_client
    app.state.sync_worker = active_sync_worker

    static_assets_available = _mount_static_assets(app)
    console_html = _load_web_console_html()

    @app.get("/", include_in_schema=False)
    def web_console() -> HTMLResponse:
        response = HTMLResponse(console_html)
        if not static_assets_available:
            response.headers["X-Cosmic-Mail-Static-Status"] = "missing"
        return response

    @app.get("/app", include_in_schema=False)
    def web_console_alias() -> HTMLResponse:
        response = HTMLResponse(console_html)
        if not static_assets_available:
            response.headers["X-Cosmic-Mail-Static-Status"] = "missing"
        return response

    @app.get("/health", response_model=HealthRead)
    def health() -> HealthRead:
        return HealthRead(status="ok")

    @app.get("/ready", response_model=ReadyCheck)
    def ready(response: Response) -> ReadyCheck:
        details: dict[str, str] = {"database": "ok", "mail_engine": "ok"}
        current_status_code = status.HTTP_200_OK

        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            details["database"] = f"error: {exc}"
            current_status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        check_health = getattr(active_mail_engine, "check_health", None)
        if callable(check_health):
            try:
                check_health()
            except Exception as exc:
                details["mail_engine"] = f"error: {exc}"
                current_status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        response.status_code = current_status_code
        overall_status = "ok" if current_status_code == status.HTTP_200_OK else "degraded"
        return ReadyCheck(status=overall_status, details=details)

    app.include_router(organizations_router, prefix=active_settings.api_prefix)
    app.include_router(approvals_router, prefix=active_settings.api_prefix)
    app.include_router(agents_router, prefix=active_settings.api_prefix)
    app.include_router(attachments_router, prefix=active_settings.api_prefix)
    app.include_router(domains_router, prefix=active_settings.api_prefix)
    app.include_router(mailboxes_router, prefix=active_settings.api_prefix)
    app.include_router(drafts_router, prefix=active_settings.api_prefix)
    app.include_router(threads_router, prefix=active_settings.api_prefix)
    app.include_router(system_router, prefix=active_settings.api_prefix)
    app.include_router(webhooks_router, prefix=active_settings.api_prefix)
    app.include_router(search_router, prefix=active_settings.api_prefix)
    return app


app = create_app()
