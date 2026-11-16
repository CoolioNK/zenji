"""Chat-Service: Orchestrierung von Konversation, Persona und LLM Engine.

Ablauf (streamend und nicht-streamend identisch):

1. Konversation ermitteln (bzw. automatisch neu anlegen)
2. Nutzernachricht persistieren
3. Kontextfenster bauen:
   - **mit ZenjiCore (Phase 2)**: Core orchestriert Persönlichkeit, Regeln,
     Erinnerungen und Context Engine (Schritte 1–7 der Spezifikation)
   - **ohne Core (Phase-1-Fallback)**: Persona-Systemprompt + Verlauf + Anfrage
4. LLM Engine aufrufen (nur Kommunikation, keine Logik)
5. Antwort streamen bzw. komplett zurückgeben und speichern
6. Mit Core: Gedächtnis-Nachbereitung (Merkmuster, ``last_used_at``)

Fehler werden klar differenziert: fehlende SSD (503), fehlende Ollama-
Verbindung (502), fehlendes Modell (409) – das Frontend zeigt jeweils eine
verständliche Meldung, statt abzustürzen.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.extensions import ExtensionRegistry
from app.core.logging import get_logger
from app.database.database import Database
from app.engines.llm_engine import LLMEngine
from app.engines.providers.base import ChatMessage, StreamChunk
from app.schemas.chat import ChatRequest
from app.schemas.conversation import MessageOut
from app.services.conversation_service import ConversationService
from app.services.settings_service import SettingsService
from app.services.zenji_core import ZenjiCore
from app.web_intelligence.citation_engine import CitationEngine, SourceRef

log = get_logger("chat_service")

MAX_HISTORY_MESSAGES = 50


@dataclass(slots=True)
class ChatTurn:
    """Ergebnis eines nicht-streamenden Chat-Durchgangs."""

    conversation_id: str
    user_message: MessageOut
    assistant_message: MessageOut


class ChatService:
    """Verbindet Persistenz, Kontextaufbau und LLM Engine."""

    def __init__(
        self,
        database: Database,
        engine: LLMEngine,
        settings_service: SettingsService,
        conversation_service: ConversationService | None = None,
        extensions: ExtensionRegistry | None = None,
        core: ZenjiCore | None = None,
    ) -> None:
        self._db = database
        self._engine = engine
        self._settings = settings_service
        self._conversations = conversation_service or ConversationService()
        self._extensions = extensions or ExtensionRegistry()
        # Phase 2: Mit Core = vollständige Orchestrierung (Persönlichkeit,
        # Regeln, Gedächtnis, Context Engine).  Ohne Core = Phase-1-Verhalten
        # (Persona-Systemprompt + Verlauf) – wichtig für Kompatibilität/Tests.
        self._core = core

    # --- Vorabprüfung (für API-Routen) -----------------------------------------------
    async def preflight(self, request: ChatRequest) -> None:
        """Prüft Settings, Konversation und Modellverfügbarkeit **vor** dem
        Streaming, damit Fehler als saubere HTTP-Statuscodes (503/502/409/404)
        enden und nicht mitten im SSE-Stream."""
        settings = self._effective_settings()
        if request.conversation_id:
            with self._db.session() as session:
                self._conversations._require(session, request.conversation_id)
        await self._engine.ensure_model_available(settings.llm.model)

    # --- Kontextaufbau ------------------------------------------------------------
    def _build_context(
        self,
        session: Session,
        conversation_id: str,
        user_message: str,
        *,
        persona: str,
        exclude_ids: set[str] | None = None,
        max_history: int = MAX_HISTORY_MESSAGES,
    ) -> list[ChatMessage]:
        messages: list[ChatMessage] = [ChatMessage(role="system", content=persona)]

        # Erweiterungspunkt Phase 2 – MemoryEngine (fail-soft):
        memory = self._extensions.get("memory")
        if memory is not None:
            log.debug("MemoryEngine registriert – Kontextanreicherung aktiv.")
            # Schnittstelle steht; konkrete Integration folgt in Phase 2.

        history = self._conversations.history(
            session, conversation_id, limit=max_history, exclude_ids=exclude_ids
        )
        messages.extend(ChatMessage(role=m.role, content=m.content) for m in history)
        messages.append(ChatMessage(role="user", content=user_message))
        return messages

    # --- Nicht-streamend --------------------------------------------------------------
    async def send_message(self, request: ChatRequest) -> ChatTurn:
        """Vollständige Antwort generieren (POST /api/chat)."""
        settings = self._effective_settings()
        model = settings.llm.model
        await self._engine.ensure_model_available(model)
        options = self._settings.llm_options(settings)

        async def _run() -> ChatTurn:
            # 1) Konversation + Nutzernachricht (eigene Transaktion; commit
            #    vor der Recherche, damit deren DB-Writes nicht auf den
            #    offenen Schreib-Lock dieser Session treffen (SQLite/WAL)).
            with self._db.session() as session:
                conversation_id = self._ensure_conversation(session, request)
                user_model = self._conversations.add_message(
                    session, conversation_id, "user", request.message
                )
                user_id = user_model.id

            # 2) Kontextaufbau (nur Lesezugriffe) + optionale Recherche:
            prepared: Any = None
            with self._db.session() as session:
                if self._core is not None:
                    # Phase-2-Pfad: ZenjiCore orchestriert alle Engines (inkl.
                    # optionaler Web-Recherche, v0.5.0).
                    prepared = await self._core.prepare_turn(
                        session,
                        conversation_id=conversation_id,
                        user_message=request.message,
                        exclude_ids={user_id},
                        mode_override=request.mode,
                        research_override=request.research,
                    )
                    context = prepared.messages
                else:
                    context = self._build_context(
                        session, conversation_id, request.message,
                        persona=settings.persona.system_prompt,
                        exclude_ids={user_id},
                    )

            # 3) Modellaufruf (ohne offene DB-Session):
            content, _meta = await self._engine.generate(
                context, options, model=model, keep_alive=self._settings.keep_alive(settings)
            )
            if prepared is not None and prepared.research_report:
                content, warnings = self._validate_citations(
                    content, prepared.research_report
                )
                if warnings:
                    log.info("Zitat-Validierung: %d Marker korrigiert.", len(warnings))

            # 4) Antwort persistieren + Gedächtnis-Vormerkung:
            with self._db.session() as session:
                assistant_model = self._conversations.add_message(
                    session, conversation_id, "assistant", content
                )
                if self._core is not None:
                    self._core.finalize_turn(
                        session,
                        conversation_id=conversation_id,
                        user_text=request.message,
                        assistant_text=content,
                        used_memory_ids=prepared.used_memory_ids if prepared else [],
                    )
                return ChatTurn(
                    conversation_id=conversation_id,
                    user_message=MessageOut.model_validate(user_model),
                    assistant_message=MessageOut.model_validate(assistant_model),
                )

        return await _run()

    # --- Streamend ---------------------------------------------------------------------
    async def stream_message(self, request: ChatRequest) -> AsyncIterator[bytes]:
        """SSE-Events für POST /api/chat/stream.

        Eventsequenz: ``start`` → (``research``*) → ``delta``* → ``done``
        (oder ``error``).  ``research``-Events (v0.5.0) werden **live** während
        der Recherche gesendet – jeder Event beschreibt einen tatsächlich
        ausgeführten Schritt (Suchanfrage, Abruf, Vergleich), nie einen
        erfundenen Fortschritt.

        Vor dem Stream wird die Modellverfügbarkeit geprüft, damit ein
        fehlendes Modell als saubere HTTP-Fehlermeldung (409) endet und nicht
        mitten im Stream.  Der Turn läuft als Task und pusht seine SSE-Bytes
        in eine Queue, damit Recherche-Fortschritt und Antwort-Deltas sich
        echt verzahnen.
        """
        settings = self._effective_settings()
        model = settings.llm.model
        await self._engine.ensure_model_available(model)

        queue: asyncio.Queue[bytes | None] = asyncio.Queue()

        async def _run_turn() -> None:
            conversation_id: str | None = None
            collected: list[str] = []
            try:
                # 1) Konversation + Nutzernachricht (eigene Transaktion, commit
                #    vor der Recherche – verhindert SQLite-Schreibkonflikte mit
                #    den eigenen Sessions der Recherche-Engine).
                with self._db.session() as session:
                    conversation_id = self._ensure_conversation(session, request)
                    user_model = self._conversations.add_message(
                        session, conversation_id, "user", request.message
                    )
                    user_id = user_model.id

                await queue.put(self._sse("start", {
                    "conversation_id": conversation_id,
                    "user_message_id": user_id,
                    "assistant_message_id": None,
                }))

                options = self._settings.llm_options(settings)
                prepared: Any = None
                with self._db.session() as session:
                    if self._core is not None:
                        # Recherche-Fortschritt live in den Stream (Callback
                        # pusht direkt in die Queue – ehrliche Ereigniskette).
                        def on_research(event: dict[str, Any]) -> None:
                            queue.put_nowait(self._sse("research", event))

                        prepared = await self._core.prepare_turn(
                            session,
                            conversation_id=conversation_id,
                            user_message=request.message,
                            exclude_ids={user_id},
                            mode_override=request.mode,
                            research_override=request.research,
                            research_progress=on_research,
                        )
                        context = prepared.messages
                        used_memory_ids = prepared.used_memory_ids
                    else:
                        context = self._build_context(
                            session, conversation_id, request.message,
                            persona=settings.persona.system_prompt,
                            exclude_ids={user_id},
                        )
                        used_memory_ids = []

                assistant_id: str | None = None
                stream = self._engine.stream(
                    context, options, model=model, keep_alive=self._settings.keep_alive(settings)
                )
                async for chunk in stream:
                    if chunk.content:
                        collected.append(chunk.content)
                        await queue.put(self._sse("delta", {"content": chunk.content}))
                    if chunk.done:
                        break
                content = "".join(collected)

                research_summary: dict[str, Any] | None = None
                if prepared is not None and prepared.research_report:
                    content, warnings = self._validate_citations(
                        content, prepared.research_report
                    )
                    research_summary = self._research_summary(
                        prepared.research_report, warnings
                    )

                with self._db.session() as session:
                    assistant_model = self._conversations.add_message(
                        session, conversation_id, "assistant", content
                    )
                    assistant_id = assistant_model.id
                    if self._core is not None:
                        self._core.finalize_turn(
                            session,
                            conversation_id=conversation_id,
                            user_text=request.message,
                            assistant_text=content,
                            used_memory_ids=used_memory_ids,
                        )

                done_payload: dict[str, Any] = {
                    "conversation_id": conversation_id,
                    "assistant_message_id": assistant_id,
                    "content": content,
                }
                if research_summary is not None:
                    done_payload["research"] = research_summary
                await queue.put(self._sse("done", done_payload))
            except Exception as exc:  # noqa: BLE001 – Stream darf nicht abreißen
                log.exception("Stream fehlgeschlagen: %s", exc)
                # Bereits gesammelten Text persistieren (Teilantwort bleibt).
                partial = "".join(collected)
                if partial and conversation_id:
                    try:
                        with self._db.session() as session:
                            self._conversations.add_message(
                                session, conversation_id, "assistant", partial
                            )
                    except Exception:  # noqa: BLE001
                        log.exception("Teilantwort konnte nicht gespeichert werden.")
                await queue.put(self._sse("error", {
                    "code": getattr(exc, "code", "LLM_ERROR"),
                    "message": str(exc),
                }))
            finally:
                await queue.put(None)

        task = asyncio.create_task(_run_turn())
        try:
            while True:
                chunk = await queue.get()
                if chunk is None:
                    break
                yield chunk
        finally:
            if not task.done():
                task.cancel()

    # --- Recherche-Unterstützung (v0.5.0) ------------------------------------------------
    @staticmethod
    def _validate_citations(text: str, report: dict[str, Any]) -> tuple[str, list[str]]:
        """Entfernt erfundene [n]-Marker (Belege nur aus echten Quellen)."""
        refs = [
            SourceRef(
                source_id=str(ref.get("source_id", "")),
                title=str(ref.get("title", "")),
                url=str(ref.get("url", "")),
                domain=str(ref.get("domain", "")),
                source_type=str(ref.get("source_type", "unbekannt")),
            )
            for ref in (report.get("refs") or [])
        ]
        result = CitationEngine().validate(text, refs)
        return result.cleaned_text, list(result.warnings)

    @staticmethod
    def _research_summary(
        report: dict[str, Any], warnings: list[str]
    ) -> dict[str, Any]:
        """Kompakte Recherche-Zusammenfassung für das ``done``-Event."""
        return {
            "session_id": report.get("session_id"),
            "status": report.get("status"),
            "mode": report.get("mode"),
            "queries": report.get("queries") or [],
            "sources": [
                {
                    "marker": source.get("marker"),
                    "title": source.get("title"),
                    "url": source.get("url"),
                    "source_type": source.get("source_type"),
                    "status": source.get("status"),
                }
                for source in (report.get("sources") or [])
            ],
            "contradiction_count": len(report.get("contradictions") or []),
            "citations_corrected": len(warnings),
            "warnings": warnings,
        }

    # --- Hilfsfunktionen ----------------------------------------------------------------
    def _effective_settings(self):
        """Einstellungen laden (DB-Fehler werden vom Database-Layer übersetzt)."""
        with self._db.session() as session:
            return self._settings.effective(session)

    def _ensure_conversation(self, session: Session, request: ChatRequest) -> str:
        if request.conversation_id:
            self._conversations._require(session, request.conversation_id)
            return request.conversation_id
        conversation = self._conversations.create(
            session, self._conversations.title_for_first_message(request.message)
        )
        return conversation.id

    @staticmethod
    def _sse(event: str, data: dict) -> bytes:
        payload = json.dumps(data, ensure_ascii=False)
        return f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
