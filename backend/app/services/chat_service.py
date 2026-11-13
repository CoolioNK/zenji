"""Chat-Service: Orchestrierung von Konversation, Persona und LLM Engine.

Ablauf (streamend und nicht-streamend identisch):

1. Konversation ermitteln (bzw. automatisch neu anlegen)
2. Nutzernachricht persistieren
3. Kontextfenster bauen: Persona-Systemprompt + Verlauf + neue Anfrage
   (Erweiterungspunkt Phase 2: MemoryEngine ergänzt hier Erinnerungen,
    PolicyEngine prüft die Anfrage vor dem Senden – beide fail-soft)
4. LLM Engine aufrufen (nur Kommunikation, keine Logik)
5. Antwort streamen bzw. komplett zurückgeben und speichern

Fehler werden klar differenziert: fehlende SSD (503), fehlende Ollama-
Verbindung (502), fehlendes Modell (409) – das Frontend zeigt jeweils eine
verständliche Meldung, statt abzustürzen.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:  # pragma: no cover
    from app.services.settings_service import SettingsService as _S

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
    ) -> None:
        self._db = database
        self._engine = engine
        self._settings = settings_service
        self._conversations = conversation_service or ConversationService()
        self._extensions = extensions or ExtensionRegistry()

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
            with self._db.session() as session:
                conversation_id = self._ensure_conversation(session, request)
                user_model = self._conversations.add_message(
                    session, conversation_id, "user", request.message
                )
                context = self._build_context(
                    session, conversation_id, request.message,
                    persona=settings.persona.system_prompt,
                    exclude_ids={user_model.id},
                )
                content, _meta = await self._engine.generate(
                    context, options, model=model, keep_alive=self._settings.keep_alive(settings)
                )
                assistant_model = self._conversations.add_message(
                    session, conversation_id, "assistant", content
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

        Eventsequenz: ``start`` → ``delta``* → ``done`` (oder ``error``).
        Vor dem Stream wird die Modellverfügbarkeit geprüft, damit ein
        fehlendes Modell als saubere HTTP-Fehlermeldung (409) endet und nicht
        mitten im Stream.
        """
        settings = self._effective_settings()
        model = settings.llm.model
        await self._engine.ensure_model_available(model)

        with self._db.session() as session:
            conversation_id = self._ensure_conversation(session, request)
            user_model = self._conversations.add_message(
                session, conversation_id, "user", request.message
            )
            user_id = user_model.id
            options = self._settings.llm_options(settings)
            context = self._build_context(
                session, conversation_id, request.message,
                persona=settings.persona.system_prompt,
                exclude_ids={user_id},
            )

        yield self._sse("start", {
            "conversation_id": conversation_id,
            "user_message_id": user_id,
            "assistant_message_id": None,
        })

        collected: list[str] = []
        assistant_id: str | None = None
        try:
            stream = self._engine.stream(
                context, options, model=model, keep_alive=self._settings.keep_alive(settings)
            )
            async for chunk in stream:
                if chunk.content:
                    collected.append(chunk.content)
                    yield self._sse("delta", {"content": chunk.content})
                if chunk.done:
                    break
            content = "".join(collected)

            with self._db.session() as session:
                assistant_model = self._conversations.add_message(
                    session, conversation_id, "assistant", content
                )
                assistant_id = assistant_model.id

            yield self._sse("done", {
                "conversation_id": conversation_id,
                "assistant_message_id": assistant_id,
                "content": content,
            })
        except Exception as exc:  # noqa: BLE001 – Stream darf nicht abreißen
            log.exception("Stream fehlgeschlagen: %s", exc)
            # Bereits gesammelten Text persistieren (Teilantwort bleibt erhalten).
            partial = "".join(collected)
            if partial:
                try:
                    with self._db.session() as session:
                        self._conversations.add_message(session, conversation_id, "assistant", partial)
                except Exception:  # noqa: BLE001
                    log.exception("Teilantwort konnte nicht gespeichert werden.")
            yield self._sse("error", {
                "code": getattr(exc, "code", "LLM_ERROR"),
                "message": str(exc),
            })

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
