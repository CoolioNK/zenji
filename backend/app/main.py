"""ZENJI Backend – FastAPI-Anwendung.

Start (Entwicklung):
    cd backend && ../.venv/bin/uvicorn app.main:app --port 8000

Der ``create_app``-Fabrikansatz erlaubt Tests, einen eigenen Provider (Mock)
einzuspritzen, ohne Umgebungspfade oder Module zu monkeypatchen.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.routes import api_router
from app.core.config import Settings
from app.core.exceptions import ValidationError, ZenjiError
from app.core.extensions import ExtensionRegistry
from app.core.logging import get_logger, setup_logging
from app.core.storage import StorageManager
from app.database.database import Database
from app.database.migrations import run_migrations
from app.engines.context_engine import ContextEngine
from app.engines.llm_engine import LLMEngine
from app.engines.memory_engine import MemoryEngine
from app.engines.personality_engine import PersonalityEngine
from app.engines.policy_engine import PolicyEngine
from app.engines.providers import create_provider
from app.engines.providers.base import LLMProvider
from app.services.chat_service import ChatService
from app.services.conversation_service import ConversationService
from app.services.settings_service import SettingsService
from app.services.zenji_core import ZenjiCore

log = get_logger("main")

ProviderFactory = Callable[[str, dict[str, Any]], LLMProvider]


def _default_provider_factory(name: str, config: dict[str, Any]) -> LLMProvider:
    return create_provider(name, config)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start-/Stopproutine: Logging, Speicher, Datenbank, Engines.

    Fehlende SSD oder Ollama führen **nicht** zu einem Absturz: ZENJI startet,
    und ``/api/health`` berichtet den Zustand.  Nur echte Programmierfehler
    brechen den Start ab.
    """
    state = app.state
    settings: Settings = state.settings
    setup_logging(settings.resolved_log_dir, settings.log_level)
    log.info("ZENJI Backend v%s startet …", __version__)

    storage: StorageManager = state.storage
    status = storage.status()
    if status.available:
        try:
            storage.ensure_structure()
        except ZenjiError as exc:
            log.warning("%s", exc.message)
    log.warning("%s", status.message) if not status.available else log.info(
        "Speicherort: %s", status.root
    )

    database: Database = state.database
    try:
        database.create_schema()
        # Phase 2: Migrationen (Schema-Stufen) und Suchindex initialisieren.
        version = run_migrations(database.engine)
        log.info("Datenbank bereit (Schema-Stufe %d): %s", version, database.db_path)
        memory_engine: MemoryEngine = state.memory_engine
        with database.session() as session:
            memory_engine.init_search(session)
    except ZenjiError as exc:
        log.warning("Datenbank nicht verfügbar: %s", exc.message)

    extensions: ExtensionRegistry = state.extensions
    await extensions.start_all()

    yield

    await extensions.stop_all()
    await state.llm_engine.aclose()
    database.dispose()
    log.info("ZENJI Backend beendet.")


def create_app(
    *,
    settings: Settings | None = None,
    provider_factory: ProviderFactory | None = None,
) -> FastAPI:
    """Baut die ZENJI-Anwendung. Tests injizieren optional eine Providerfabrik."""
    settings = settings or Settings.load()
    factory = provider_factory or _default_provider_factory

    storage = StorageManager(settings)
    database = Database(settings)
    settings_service = SettingsService(settings)
    conversation_service = ConversationService()
    extensions = ExtensionRegistry()

    # Phase 2: Engines + ZENJI Core (alle fail-soft, registriert im Registry).
    personality_engine = PersonalityEngine()
    policy_engine = PolicyEngine()
    memory_engine = MemoryEngine()
    context_engine = ContextEngine()
    zenji_core = ZenjiCore(
        settings_service=settings_service,
        conversation_service=conversation_service,
        personality_engine=personality_engine,
        policy_engine=policy_engine,
        memory_engine=memory_engine,
        context_engine=context_engine,
    )
    extensions.register(personality_engine)
    extensions.register(policy_engine)
    extensions.register(memory_engine)
    extensions.register(context_engine)

    app = FastAPI(
        title="ZENJI API",
        version=__version__,
        description="Modulares KI-System – Phase 2: Core Intelligence (Persönlichkeit, Regeln, Gedächtnis, Kontext).",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Komponenten an app.state hängen (DI via app.api.deps).
    app.state.settings = settings
    app.state.storage = storage
    app.state.database = database
    app.state.extensions = extensions
    app.state.settings_service = settings_service
    app.state.conversation_service = conversation_service
    app.state.personality_engine = personality_engine
    app.state.policy_engine = policy_engine
    app.state.memory_engine = memory_engine
    app.state.context_engine = context_engine
    app.state.zenji_core = zenji_core

    provider_config = {
        "base_url": settings.ollama_base_url,
        **settings.ollama.model_dump(),
    }
    provider = factory(settings.llm.provider, provider_config)
    engine = LLMEngine(provider)
    chat_service = ChatService(
        database=database,
        engine=engine,
        settings_service=settings_service,
        conversation_service=conversation_service,
        extensions=extensions,
        core=zenji_core,
    )
    app.state.llm_engine = engine
    app.state.chat_service = chat_service

    app.include_router(api_router)

    @app.exception_handler(ZenjiError)
    async def zenji_error_handler(_request: Request, exc: ZenjiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "detail": exc.detail,
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Einheitliches Format {"error": {...}} auch für HTTPException."""
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            return JSONResponse(status_code=exc.status_code, content={"error": detail})
        code_by_status = {
            404: "NOT_FOUND",
            405: "METHOD_NOT_ALLOWED",
            422: "VALIDATION_ERROR",
        }
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code_by_status.get(exc.status_code, "HTTP_ERROR"),
                    "message": str(detail),
                    "detail": None,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            f"{'.'.join(str(p) for p in e.get('loc', [])[1:]) or 'body'}: {e.get('msg', 'ungültig')}"
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Ungültige Anfrage: " + "; ".join(fields),
                    "detail": None,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
        log.exception("Unbehandelter Fehler: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Ein interner Fehler ist aufgetreten. Details im Backend-Log.",
                    "detail": None,
                }
            },
        )

    @app.exception_handler(ValidationError)
    async def zenji_validation_handler(_request: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "detail": exc.detail}},
        )

    return app


app = create_app()
