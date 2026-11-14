"""Memory Engine – persistentes Gedächtnis über Konversationsgrenzen hinweg.

Grundsätze:

- ZENJI speichert **nicht** jede Nachricht dauerhaft.  Automatisch werden nur
  explizite Merkmuster erkannt („Merke dir …", „Ich heiße …", „Ich arbeite an
  …" u. ä.) – alles andere bleibt im Gesprächsverlauf (SQLite, Phase 1).
- Vier Erinnerungstypen: ``conversation`` (kurzfristig), ``long_term``,
  ``preference`` (Nutzerpräferenzen) und ``project`` (Projekte/Vorhaben).
- Duplikate werden erkannt (normalisierter Hash) und **aktualisiert**, nicht
  doppelt angelegt.
- Veraltete Informationen: nahezu identische, neuere Erinnerung verdrängt die
  ältere (Status ``superseded``) – Aktualität schlägt Relevanz.
- Widersprüchliche aktive Erinnerungen werden im Kontext **beide** geliefert
  und als Konflikt markiert; die Systemregel ``memory_conflict_ask`` zwingt
  ZENJI, nachzufragen statt zu raten.
- Suche modular: FTS5 (bm25) mit LIKE-Fallback; Schnittstelle hält Phase-3-
  Embeddings offen (siehe repositories/memories.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.core.exceptions import MemoryNotFoundError, ValidationError
from app.core.logging import get_logger
from app.database.models import MemoryModel, content_hash, normalize_content
from app.database.repositories.memories import MemoryRepository
from app.interfaces.base import ZenjiEngine

log = get_logger("memory_engine")

#: Ab dieser Ähnlichkeit (0–1) verdrängt eine neue Erinnerung die alte.
SUPERSEDE_SIMILARITY = 0.85
#: Unterer Ähnlichkeitsbereich für "möglicher Widerspruch" (beide aktiv).
CONFLICT_SIMILARITY_LOW = 0.5

_MEMORY_TYPE_BY_PATTERN = (
    (re.compile(r"\b(ich heiße|mein name ist|ich bin der|ich bin die)\b", re.I), "preference"),
    (re.compile(r"\b(ich bevorzuge|ich mag|ich mag es|ich möchte immer|ich mag keine)\b", re.I), "preference"),
    (re.compile(r"\b(ich arbeite an|mein projekt|unsere projekt|das projekt heißt)\b", re.I), "project"),
)

_AUTO_PATTERNS = (
    re.compile(r"\bmerke dir[:\s]+(.+)", re.I),
    re.compile(r"\bdenk daran[:\s]+(.+)", re.I),
    re.compile(r"\berinnere dich[:\s]+(.+)", re.I),
    re.compile(r"\bnotiere[:\s]+(.+)", re.I),
    re.compile(r"\b(ab jetzt|von jetzt an)[:\s]+(.+)", re.I),
)

_STOPWORDS = frozenset(
    """und oder der die das ein eine einem einem den dem des ist sind war wie was
    wer wo wann warum bitte danke mir mich ich du er sie es wir ihr zum zur im in
    am an auf für mit von zu aus bei nach über unter nicht auch noch schon nur
    dass wenn aber denn man kann kannst könnte würde sollten müssen sehr mehr
    hier da dies diese dieser tell me what about the and for with this that
    from have has can could would should please you your""".split()
)

_TYPE_WEIGHT = {"preference": 1.25, "long_term": 1.0, "project": 1.1, "conversation": 0.6}


def _as_utc(value: datetime | None) -> datetime:
    """Normalisiert DB-Zeitwerte (SQLite liefert teils naive Datetimes)."""
    if value is None:
        return datetime(1, 1, 1, tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@dataclass(slots=True)
class RelevantMemory:
    """Eine für den Kontext ausgewählte Erinnerung."""

    memory: MemoryModel
    score: float
    conflict: bool = False


class MemoryEngine(ZenjiEngine):
    """Gedächtnis: Speichern, Suchen, Auswählen, Veralten."""

    name = "memory"

    def __init__(self) -> None:
        self._repo = MemoryRepository()

    # --- Lifecycle -----------------------------------------------------------------
    async def start(self) -> None:
        log.info("MemoryEngine bereit.")

    async def stop(self) -> None:
        return None

    def init_search(self, session: Session) -> None:
        """Suchindex initialisieren (beim App-Start; FTS5 mit LIKE-Fallback)."""
        self._repo.init_search(session)
        log.info("Memory-Suche aktiv: %s", self._repo.search_provider.name)

    # --- CRUD (delegiert, mit fachlicher Validierung) -----------------------------------
    def get(self, session: Session, memory_id: str) -> MemoryModel:
        memory = self._repo.get(session, memory_id)
        if memory is None:
            raise MemoryNotFoundError(f"Erinnerung '{memory_id}' existiert nicht.")
        return memory

    def create(
        self,
        session: Session,
        *,
        content: str,
        category: str = "allgemein",
        memory_type: str = "long_term",
        source: str = "user",
        source_ref: str | None = None,
        relevance: float = 0.5,
        supersedes_id: str | None = None,
    ) -> tuple[MemoryModel, bool]:
        """Erinnerung anlegen. Rückgabe: (Erinnerung, wurde_duplikat_zusammengeführt).

        Duplikaterkennung: identischer normalisierter Inhalt → bestehende
        Erinnerung wird aktualisiert (Relevanz erhöht, aktualisiert) statt
        doppelt gespeichert.
        """
        content = content.strip()
        if not content:
            raise ValidationError("Erinnerungsinhalt darf nicht leer sein.")
        if len(content) > 2000:
            raise ValidationError("Erinnerungsinhalt ist zu lang (max. 2000 Zeichen).")
        if memory_type not in ("conversation", "long_term", "preference", "project"):
            raise ValidationError(f"Unbekannter Erinnerungstyp '{memory_type}'.")
        if not 0 <= float(relevance) <= 1:
            raise ValidationError("Relevanz muss zwischen 0 und 1 liegen.")

        digest = content_hash(content)
        existing = self._repo.find_by_hash(session, digest)
        if existing is not None:
            self._repo.update(
                session,
                existing,
                relevance=min(1.0, max(existing.relevance, float(relevance)) + 0.05),
                category=category or existing.category,
            )
            log.info("Duplikat erkannt – Erinnerung aktualisiert statt neu angelegt.")
            return existing, True

        memory = self._repo.create(
            session,
            content=content,
            content_hash=digest,
            category=category or "allgemein",
            memory_type=memory_type,
            source=source,
            source_ref=source_ref,
            relevance=float(relevance),
            supersedes_id=supersedes_id,
        )
        self._apply_superseding(session, memory)
        return memory, False

    def update(self, session: Session, memory_id: str, fields: dict) -> MemoryModel:  # noqa: ANN401
        memory = self.get(session, memory_id)
        allowed = {"content", "category", "memory_type", "relevance", "status"}
        if "content" in fields and not str(fields["content"]).strip():
            raise ValidationError("Erinnerungsinhalt darf nicht leer sein.")
        if "relevance" in fields and not 0 <= float(fields["relevance"]) <= 1:
            raise ValidationError("Relevanz muss zwischen 0 und 1 liegen.")
        if "status" in fields and fields["status"] not in ("active", "superseded", "archived"):
            raise ValidationError(f"Unbekannter Status '{fields['status']}'.")
        clean = {k: v for k, v in fields.items() if k in allowed}
        self._repo.update(session, memory, **clean)
        if "content" in clean:
            self._apply_superseding(session, memory)
        return memory

    def delete(self, session: Session, memory_id: str) -> None:
        if not self._repo.delete(session, memory_id):
            raise MemoryNotFoundError(f"Erinnerung '{memory_id}' existiert nicht.")

    def list(self, session: Session, **filters) -> list[MemoryModel]:  # noqa: ANN003
        return self._repo.list(session, **filters)

    def mark_used(self, session: Session, memory_ids: list[str]) -> None:
        """Setzt ``last_used_at`` für im Kontext verwendete Erinnerungen."""
        self._repo.touch_used(session, memory_ids)

    def categories(self, session: Session) -> list[tuple[str, int]]:
        """Aktive Kategorien mit Anzahl (Control Center)."""
        return self._repo.categories(session)

    def stats(self, session: Session) -> dict[str, object]:
        """Zähler für Core-Status und Control Center."""
        by_status = self._repo.count_by_status(session)
        by_type = self._repo.count_by_type(session)
        return {
            "total": sum(by_status.values()),
            "active": by_status.get("active", 0),
            "superseded": by_status.get("superseded", 0),
            "archived": by_status.get("archived", 0),
            "by_type": by_type,
            "search_provider": self._repo.search_provider.name,
        }

    def search(
        self, session: Session, query: str, *, memory_type: str | None = None,
        category: str | None = None, limit: int = 20,
    ) -> list[tuple[MemoryModel, float]]:
        """Suche über den aktiven SearchProvider (FTS5 oder LIKE).

        Begriffe werden mit ODER verknüpft (Treffer mit mehr Begriffen ranken
        höher); unsichere Zeichen werden durch Anführungszeichen neutralisiert.
        """
        terms = [t for t in query.split() if len(t) >= 2]
        if not terms:
            return []
        or_query = " OR ".join(f'"{t}"' for t in terms)
        results = self._repo.search_provider.search(session, or_query, limit * 3)
        items: list[tuple[MemoryModel, float]] = []
        for memory_id, score in results:
            memory = self._repo.get(session, memory_id)
            if memory is None or memory.status != "active":
                continue
            if memory_type and memory.memory_type != memory_type:
                continue
            if category and memory.category != category:
                continue
            items.append((memory, score))
            if len(items) >= limit:
                break
        return items

    # --- Automatische Auswahl für Gespräche ------------------------------------------------
    def collect_relevant(
        self, session: Session, user_message: str, *, limit: int = 5
    ) -> list[RelevantMemory]:
        """Wählt relevante Erinnerungen für eine Anfrage aus.

        1. Schlagwortsuche über die Nutzeranfrage (FTS5/LIKE).
        2. Fallback: relevanteste aktive Präferenzen/Langzeit-Erinnerungen.
        3. Konfliktmarkierung: ähnliche aktive Erinnerungen werden mitgeliefert.
        """
        keywords = self._keywords(user_message)
        selected: dict[str, RelevantMemory] = {}

        if keywords:
            query = " ".join(keywords[:12])
            for memory, score in self.search(session, query, limit=limit * 2):
                weighted = score * _TYPE_WEIGHT.get(memory.memory_type, 1.0)
                selected[memory.id] = RelevantMemory(memory=memory, score=weighted)

        if len(selected) < limit:
            for memory in self._repo.top_for_context(
                session, limit=limit * 2
            ):
                if memory.id not in selected:
                    # Fallback-Erinnerungen leicht abgewertet, Suchtreffer behalten Vortritt.
                    selected[memory.id] = RelevantMemory(
                        memory=memory,
                        score=0.3 * _TYPE_WEIGHT.get(memory.memory_type, 1.0) * memory.relevance,
                    )

        ranked = sorted(selected.values(), key=lambda item: item.score, reverse=True)[:limit]
        for item in ranked:
            item.conflict = self._has_conflict(session, item.memory)
        return ranked

    def remember_candidates(self, session: Session, user_message: str,
                            *, conversation_id: str | None = None) -> list[MemoryModel]:
        """Erkennt explizite Merkmuster und speichert sie (source='chat').

        Bewusst konservativ: ohne Muster wird **nichts** gespeichert.
        """
        created: list[MemoryModel] = []
        stripped = user_message.strip()
        for pattern in _AUTO_PATTERNS:
            match = pattern.search(stripped)
            if match is None:
                continue
            fact = " ".join(match.groups()[-1].split()).strip(" .!?")
            if not fact or len(fact) < 3:
                continue
            fact = fact[0].upper() + fact[1:]
            memory, _merged = self.create(
                session,
                content=fact,
                category=self._category_for(fact),
                memory_type=self._type_for(stripped),
                source="chat",
                source_ref=conversation_id,
                relevance=0.7,
            )
            created.append(memory)
        return created

    # --- Interna ------------------------------------------------------------------------------
    def _apply_superseding(self, session: Session, memory: MemoryModel) -> None:
        """Neuere, nahezu identische Erinnerung verdrängt ältere (gleicher Typ)."""
        for other in self._repo.similar_active(session, exclude_id=memory.id):
            if other.memory_type != memory.memory_type:
                continue  # Veralten gilt innerhalb eines Typs, nicht typübergreifend
            if _as_utc(other.created_at) > _as_utc(memory.created_at):
                continue  # nur ÄLTERE verdrängen
            similarity = SequenceMatcher(
                None, normalize_content(memory.content), normalize_content(other.content)
            ).ratio()
            if similarity >= SUPERSEDE_SIMILARITY:
                self._repo.update(session, other, status="superseded")
                memory.supersedes_id = other.id
                log.info(
                    "Erinnerung '%s' verdrängt ältere ähnliche Erinnerung '%s'.",
                    memory.id[:8], other.id[:8],
                )
                break

    def _has_conflict(self, session: Session, memory: MemoryModel) -> bool:
        """True, wenn eine ähnliche *aktive* Erinnerung im Konfliktband liegt."""
        for other in self._repo.similar_active(session, exclude_id=memory.id):
            similarity = SequenceMatcher(
                None, normalize_content(memory.content), normalize_content(other.content)
            ).ratio()
            if CONFLICT_SIMILARITY_LOW <= similarity < SUPERSEDE_SIMILARITY:
                if other.memory_type == memory.memory_type:
                    return True
        return False

    @staticmethod
    def _keywords(user_message: str) -> list[str]:
        tokens = re.findall(r"[\wäöüß]{3,}", user_message.lower())
        return [t for t in tokens if t not in _STOPWORDS]

    @staticmethod
    def _type_for(message: str) -> str:
        for pattern, memory_type in _MEMORY_TYPE_BY_PATTERN:
            if pattern.search(message):
                return memory_type
        return "long_term"

    @staticmethod
    def _category_for(fact: str) -> str:
        lowered = fact.lower()
        if any(word in lowered for word in ("name", "heiße", "heißt")):
            return "identität"
        if any(word in lowered for word in ("projekt", "arbeit", "team")):
            return "projekt"
        if any(word in lowered for word in ("bevorzug", "mag", "möchte", "lieber")):
            return "präferenz"
        return "fakt"
