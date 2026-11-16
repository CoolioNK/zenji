"""ZENJI Core – zentrale Orchestrierung aller Engines (Phase 2).

Ablauf einer Nachricht (Spezifikation, Schritte 1–12):

 1. Nutzernachricht empfangen                (ChatService übergibt sie hier)
 2. Gespräch und Einstellungen laden         (SettingsService + ConversationService)
 3. Persönlichkeit laden                     (PersonalityEngine)
 4. Aktive Regeln laden                      (PolicyEngine)
 5. Relevante Erinnerungen suchen            (MemoryEngine)
 6. Kontext aufbauen                         (ContextEngine)
 7. Kontext validieren                       (Budget-Plan + Injection-Flags)
 8.–11. LLM-Aufruf und Rückgabe              (bleibt beim ChatService/LLMEngine)
12. Relevante Informationen vormerken        (finalize: Merkmuster + last_used_at)

Grundsätze:

- Der Core enthält **keine** Datenbankdetails (nur Services/Engines mit Session)
  und **keine** Provider-spezifische Logik.
- Fail-soft: fehlt eine Engine oder schlägt ein Schritt fehl, läuft der Chat
  mit reduziertem Kontext weiter – niemals ein Abbruch wegen Zierfunktion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.engines.communication_engine import CommunicationManager
from app.engines.context_engine import ContextEngine, ContextPlan, MemoryCandidate
from app.engines.memory_engine import MemoryEngine
from app.engines.personality_engine import PersonalityEngine
from app.engines.policy_engine import PolicyCompilation, PolicyEngine
from app.engines.providers.base import ChatMessage
from app.services.conversation_service import ConversationService
from app.services.settings_service import SettingsService

if TYPE_CHECKING:  # pragma: no cover
    from app.services.web_intelligence_service import WebIntelligenceService

log = get_logger("zenji_core")

MAX_HISTORY_MESSAGES = 50


@dataclass(slots=True)
class PreparedTurn:
    """Ergebnis der Vorbereitung (Schritte 1–7)."""

    messages: list[ChatMessage]
    plan: ContextPlan
    personality_name: str | None
    active_policy_count: int
    used_memory_ids: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    #: Aktiver Kommunikationsmodus (v0.3.0; leer ohne CommunicationManager).
    mode: str = ""
    #: Recherche-Report (v0.5.0; None ohne Recherche) + Kontext-Datenblock.
    research_report: dict[str, Any] | None = None
    research_block: str = ""


class ZenjiCore:
    """Koordiniert Personality, Policy, Memory, Communication und Context."""

    name = "core"

    def __init__(
        self,
        *,
        settings_service: SettingsService,
        conversation_service: ConversationService,
        personality_engine: PersonalityEngine,
        policy_engine: PolicyEngine,
        memory_engine: MemoryEngine,
        context_engine: ContextEngine,
        communication_engine: CommunicationManager | None = None,
        web_engine: "WebIntelligenceService | None" = None,
    ) -> None:
        self._settings_service = settings_service
        self._conversations = conversation_service
        self._personality = personality_engine
        self._policy = policy_engine
        self._memory = memory_engine
        self._context = context_engine
        self._communication = communication_engine
        self._web = web_engine

    # --- Vorbereitung (Schritte 1–7) ----------------------------------------------------
    async def prepare_turn(
        self,
        session: Session,
        *,
        conversation_id: str | None,
        user_message: str,
        exclude_ids: set[str] | None = None,
        mode_override: str | None = None,
        research_override: str | None = None,
        research_progress: Any = None,
        research_abort_event: Any = None,
    ) -> PreparedTurn:
        """Baut den vollständigen Kontext für eine Anfrage.

        Ohne ``conversation_id`` (z. B. Kontext-Preview) entfällt der Verlauf.
        ``mode_override`` erzwingt einen Kommunikationsmodus (manuelle Nutzer-
        anfrage); ohne Override wählt der CommunicationManager automatisch.

        ``research_override`` (v0.5.0): ``None``/``"auto"`` → Bedarfserkennung;
        ``"off"`` → nie recherchieren; ``quick|standard|deep`` → erzwungener
        Recherche-Modus.  Fehlt die Web-Engine oder schlägt die Recherche fehl,
        läuft der Chat ohne Recherche weiter (fail-soft, ehrliche Meldung im
        Progress-Stream).
        """
        # (2) Einstellungen laden
        settings = self._settings_service.effective(session)

        # (3) Persönlichkeit laden
        personality = self._personality.require_active(session)
        personality_text = self._personality.compile_context(personality)

        # (3b) Situativer Kommunikationsmodus (v0.3.0; fail-soft)
        mode = ""
        communication_text = ""
        if self._communication is not None:
            try:
                mode = self._communication.detect_mode(
                    user_message, override=mode_override
                )
                communication_text = self._communication.mode_directives(mode)
            except Exception as exc:  # noqa: BLE001 – Modus darf nie den Chat brechen
                log.warning(
                    "Kommunikationsmodus konnte nicht bestimmt werden (fail-soft): %s", exc
                )

        # (4) Aktive Regeln laden und kompilieren
        compilation = self._policy.compile(session)

        # (5) Relevante Erinnerungen suchen
        relevant = self._memory.collect_relevant(session, user_message)
        candidates = [
            MemoryCandidate(
                memory_id=item.memory.id,
                content=item.memory.content,
                memory_type=item.memory.memory_type,
                category=item.memory.category,
                source=item.memory.source,
                score=item.score,
                conflict=item.conflict,
            )
            for item in relevant
        ]

        # Verlauf laden (Service-Schicht, kein direkter DB-Zugriff; fail-soft)
        history: list[ChatMessage] = []
        if conversation_id:
            try:
                history_models = self._conversations.history(
                    session,
                    conversation_id,
                    limit=MAX_HISTORY_MESSAGES,
                    exclude_ids=exclude_ids,
                )
                history = [
                    ChatMessage(role=m.role, content=m.content) for m in history_models
                ]
            except Exception as exc:  # noqa: BLE001 – Chat funktioniert auch ohne Verlauf
                log.warning("Verlauf konnte nicht geladen werden (fail-soft): %s", exc)

        # Untrusted-Content-Prüfung (fail-soft, nur Flags)
        flags: list[str] = []
        try:
            check = await self._policy.check_incoming(user_message)
            flags = list(check.get("flags") or [])
        except Exception as exc:  # noqa: BLE001 – Prüfung darf den Chat nie blockieren
            log.warning("Policy-Prüfung fehlgeschlagen (fail-soft): %s", exc)

        # (5b) Web-Recherche (v0.5.0; fail-soft, zwischen Memory und Verlauf)
        research_report: dict[str, Any] | None = None
        research_block = ""
        if self._web is not None:
            research_report, research_block = await self._run_research(
                user_message,
                research_override=research_override,
                progress=research_progress,
                abort_event=research_abort_event,
            )

        # (6)+(7) Kontext aufbauen und über Budget-Plan validieren
        messages, plan = self._context.build(
            system_identity=settings.persona.system_prompt,
            personality_text=personality_text,
            policies_text=compilation.context_text,
            memories=candidates,
            history=history,
            current_message=user_message,
            num_ctx=settings.llm.num_ctx,
            num_predict=settings.llm.num_predict,
            flags=flags,
            communication_text=communication_text,
            mode=mode,
            research=research_block,
        )

        return PreparedTurn(
            messages=messages,
            plan=plan,
            personality_name=personality.name if personality else None,
            active_policy_count=len(compilation.active_rules),
            used_memory_ids=plan.used_memory_ids,
            flags=flags,
            mode=mode,
            research_report=research_report,
            research_block=research_block,
        )

    # --- Recherche (v0.5.0) ---------------------------------------------------------------
    async def _run_research(
        self,
        user_message: str,
        *,
        research_override: str | None,
        progress: Any,
        abort_event: Any,
    ) -> tuple[dict[str, Any] | None, str]:
        """Entscheidet und führt eine Recherche durch (fail-soft).

        Rückgabe: (Report oder None, Kontext-Datenblock).  Die Entscheidung:
        ``off`` → nie; ``quick|standard|deep`` → erzwungen; ``auto`` → nur bei
        Bedarf (Bedarfserkennung des Planners).  Der Recherche-Report geht
        **nicht** automatisch ins Memory – er ist Sitzungsdaten.
        """
        assert self._web is not None
        from app.web_intelligence.research_planner import normalize_mode

        normalized = normalize_mode(research_override)
        if normalized == "off":
            return None, ""
        forced = bool(normalized)
        if not forced and not self._web.needs_research(user_message):
            return None, ""

        emit = progress or (lambda event: None)
        try:
            emit({"step": "planning", "detail": "Recherchebedarf geprüft – Recherche startet."})
            report = await self._web.research(
                user_message,
                mode=normalized or None,
                progress=emit,
                abort_event=abort_event,
            )
        except Exception as exc:  # noqa: BLE001 – Recherche darf den Chat nie brechen
            log.warning("Recherche fehlgeschlagen (fail-soft): %s", exc)
            emit(
                {
                    "step": "research_failed",
                    "detail": "Recherche nicht möglich – Antwort erfolgt ohne Webbelege.",
                }
            )
            return None, ""
        status = report.get("status")
        if status == "failed":
            detail = report.get("stats", {}).get("error") or "keine Quelle erreichbar"
            log.info("Recherche ohne Ergebnis: %s", detail)
            emit(
                {
                    "step": "research_failed",
                    "detail": f"Recherche ohne Ergebnis ({detail}) – Antwort ohne Webbelege.",
                }
            )
            # Auch ein "failed"-Report bleibt dokumentiert, bringt aber keinen Block.
            return report, ""
        return report, self._web.context_block(report)

    # --- Abschluss (Schritt 12) ------------------------------------------------------------
    def finalize_turn(
        self,
        session: Session,
        *,
        conversation_id: str,
        user_text: str,
        assistant_text: str,
        used_memory_ids: list[str],
    ) -> list[str]:
        """Vormerken von Gedächtnis-Kandidaten + Nutzungs-Markierung.

        Rückgabe: IDs neu angelegter Erinnerungen (für Diagnose/UI).  Fehler sind
        hier bewusst nicht fatale – die Antwort wurde bereits erzeugt.
        """
        created_ids: list[str] = []
        try:
            created = self._memory.remember_candidates(
                session, user_text, conversation_id=conversation_id
            )
            created_ids = [memory.id for memory in created]
        except Exception as exc:  # noqa: BLE001
            log.warning("Gedächtnis-Kandidaten konnten nicht gespeichert werden: %s", exc)

        try:
            self._memory.mark_used(session, used_memory_ids)
        except Exception as exc:  # noqa: BLE001
            log.warning("last_used_at konnte nicht aktualisiert werden: %s", exc)

        if created_ids:
            log.info(
                "%d Erinnerung(en) aus Chat-Merkmustern angelegt.", len(created_ids)
            )
        return created_ids

    # --- Status (für GET /api/core/status) -----------------------------------------------------
    def status(self, session: Session, *, settings) -> dict[str, object]:
        """Aktuelle Kern-Zustände für das Control Center."""
        personality = self._personality.require_active(session)
        compilation: PolicyCompilation = self._policy.compile(session)
        memory_stats = self._memory.stats(session)
        return {
            "personality": personality.name if personality else None,
            "personality_id": personality.id if personality else None,
            "active_policies": len(compilation.active_rules),
            "policy_conflicts": len(compilation.conflicts),
            "memories": memory_stats,
            "model": settings.llm.model,
            "provider": settings.llm.provider,
            "num_ctx": settings.llm.num_ctx,
            "num_predict": settings.llm.num_predict,
            # v0.3.0: verfügbare Kommunikationsmodi für das UI.
            "communication_modes": (
                self._communication.available() if self._communication else []
            ),
            "communication_default_mode": (
                self._communication.default_mode if self._communication else ""
            ),
        }

    # --- Context-Preview (für GET /api/core/context-preview) --------------------------------
    async def context_preview(
        self,
        session: Session,
        *,
        conversation_id: str | None,
        sample_message: str,
        mode_override: str | None = None,
    ) -> dict[str, object]:
        """Nachvollziehbarer Kontext-Entwurf ohne LLM-Aufruf.

        Ohne ``conversation_id`` entfällt der Verlauf – der Entwurf zeigt dann
        Systemabschnitte + Beispielnachricht.  ``mode_override`` erzwingt einen
        Modus (gleiche Semantik wie im Chat).  Recherche läuft im Preview
        **nie live** (kein Netzwerkzugriff durch eine Vorschau); angezeigt wird
        nur, ob der Planner Bedarf erkennen würde.
        """
        research_would_run = False
        if self._web is not None:
            try:
                research_would_run = self._web.needs_research(sample_message)
            except Exception:  # noqa: BLE001 – Anzeige, kein Verhalten
                research_would_run = False
        prepared = await self.prepare_turn(
            session,
            conversation_id=conversation_id,
            user_message=sample_message,
            exclude_ids=None,
            mode_override=mode_override,
            research_override="off",
        )
        plan = prepared.plan
        return {
            "mode": prepared.mode,
            "sections": [
                {
                    "key": section.key,
                    "title": section.title,
                    "tokens_est": section.tokens_est,
                    "included": section.included,
                    "truncated": section.truncated,
                    "detail": section.detail,
                }
                for section in plan.sections
            ],
            "budget_tokens": plan.budget_tokens,
            "used_tokens": plan.used_tokens,
            "usage_ratio": round(plan.usage_ratio, 4),
            "history_kept": plan.history_kept,
            "history_dropped": plan.history_dropped,
            "memories_kept": plan.memories_kept,
            "memories_dropped": plan.memories_dropped,
            "conflicts": plan.conflicts,
            "flags": plan.flags,
            "research_planned": research_would_run,
            "research_tokens": plan.research_tokens,
            "system_text": plan.system_text,
            "messages": ContextEngine.preview_messages(prepared.messages),
            "used_memory_ids": prepared.used_memory_ids,
        }
