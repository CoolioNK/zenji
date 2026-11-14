"""Repository für Erinnerungen (Memory) inkl. FTS5-Suchindex.

Sucharchitektur (modular, Phase-3-fähig):

- Primary: SQLite **FTS5**-Volltextsuche (``memories_fts``), vom Repository
  bei jedem Schreibvorgang synchron gehalten.
- Fallback: wenn FTS5 in der SQLite-Build nicht verfügbar ist, LIKE-Suche
  über alle Begriffe (``_LIKE_PROVIDER``).

Für Phase 3 (semantische Suche/Embeddings) implementiert ein künftiger
``EmbeddingSearchProvider`` dieselbe Schnittstelle
(``index`` / ``remove`` / ``search``) – das Repository bleibt unverändert.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.models import MemoryModel, new_id, utcnow

log = get_logger("memories_repo")

_FTS_TABLE = """
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    memory_id UNINDEXED,
    content,
    tokenize='unicode61 remove_diacritics 2'
)
"""


class FtsSearchProvider:
    """FTS5-basierte Suche (bm25-Ranking)."""

    name = "fts5"

    def __init__(self) -> None:
        self.available = False

    def ensure_index(self, session: Session) -> None:
        try:
            session.execute(text(_FTS_TABLE))
            self.available = True
        except Exception as exc:  # noqa: BLE001 – Fallback entscheidet zur Laufzeit
            log.info("FTS5 nicht verfügbar (%s) – LIKE-Fallback aktiv.", exc.__class__.__name__)
            self.available = False

    def index(self, session: Session, memory_id: str, content: str) -> None:
        if not self.available:
            return
        self.remove(session, memory_id)
        session.execute(
            text("INSERT INTO memories_fts (memory_id, content) VALUES (:mid, :content)"),
            {"mid": memory_id, "content": content},
        )

    def remove(self, session: Session, memory_id: str) -> None:
        if not self.available:
            return
        session.execute(
            text("DELETE FROM memories_fts WHERE memory_id = :mid"), {"mid": memory_id}
        )

    def rebuild(self, session: Session) -> None:
        """Index aus der Tabelle neu aufbauen (z. B. nach Migration/Restore)."""
        if not self.available:
            return
        session.execute(text("DELETE FROM memories_fts"))
        for memory_id, content in session.execute(
            select(MemoryModel.id, MemoryModel.content)
        ):
            session.execute(
                text("INSERT INTO memories_fts (memory_id, content) VALUES (:mid, :content)"),
                {"mid": memory_id, "content": content},
            )

    def search(self, session: Session, query: str, limit: int) -> list[tuple[str, float]]:
        """Liefert (memory_id, score) mit score ∈ (0, 1] (höher = relevanter)."""
        if not self.available:
            return []
        try:
            rows = session.execute(
                text(
                    "SELECT memory_id, bm25(memories_fts) AS rank "
                    "FROM memories_fts WHERE memories_fts MATCH :q "
                    "ORDER BY rank LIMIT :limit"
                ),
                {"q": query, "limit": limit},
            ).all()
        except Exception as exc:  # noqa: BLE001 – Match-Syntaxprobleme → Fallback
            log.debug("FTS-Query fehlgeschlagen (%s) – leeres Ergebnis.", exc)
            return []
        results: list[tuple[str, float]] = []
        for memory_id, rank in rows:
            # bm25 liefert negative Werte (kleiner = besser): normalisieren.
            score = 1.0 / (1.0 + max(0.0, -float(rank)))
            results.append((memory_id, score))
        return results


class LikeSearchProvider:
    """Fallback: LIKE-Suche über alle Begriffe, Score = Trefferquote der Begriffe."""

    name = "like"

    def ensure_index(self, session: Session) -> None:  # noqa: ARG002
        return None

    def index(self, session: Session, memory_id: str, content: str) -> None:  # noqa: ARG002
        return None

    def remove(self, session: Session, memory_id: str) -> None:  # noqa: ARG002
        return None

    def rebuild(self, session: Session) -> None:  # noqa: ARG002
        return None

    def search(self, session: Session, query: str, limit: int) -> list[tuple[str, float]]:
        """Score = Anteil der Begriffe, die im Inhalt vorkommen (0 < score ≤ 1)."""
        raw_terms = query.lower().split()
        terms = [t.strip('"') for t in raw_terms if len(t.strip('"')) >= 2]
        if not terms:
            return []
        conditions = " OR ".join(
            f"lower(content) LIKE :term{i}" for i in range(len(terms))
        )
        params: dict[str, Any] = {f"term{i}": f"%{t}%" for i, t in enumerate(terms)}
        rows = session.execute(
            text(f"SELECT id, lower(content) FROM memories WHERE ({conditions}) LIMIT :limit"),
            params | {"limit": max(limit * 10, 50)},
        ).all()
        scored: list[tuple[str, float]] = []
        for memory_id, content in rows:
            hits = sum(1 for t in terms if t in (content or ""))
            scored.append((memory_id, hits / len(terms)))
        scored = [item for item in scored if item[1] > 0]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]


_LIKE_PROVIDER = LikeSearchProvider()


class MemoryRepository:
    """CRUD + Suche für Erinnerungen."""

    def __init__(self) -> None:
        self.search_provider: FtsSearchProvider | LikeSearchProvider = _LIKE_PROVIDER

    # --- Index-Verwaltung --------------------------------------------------------
    def init_search(self, session: Session) -> None:
        """FTS5 versuchen; bei Nichtverfügbarkeit LIKE-Fallback behalten."""
        fts = FtsSearchProvider()
        fts.ensure_index(session)
        if fts.available:
            self.search_provider = fts

    def rebuild_search_index(self, session: Session) -> None:
        self.search_provider.rebuild(session)

    # --- CRUD ----------------------------------------------------------------------
    def create(
        self,
        session: Session,
        *,
        content: str,
        content_hash: str,
        category: str = "allgemein",
        memory_type: str = "long_term",
        source: str = "user",
        source_ref: str | None = None,
        relevance: float = 0.5,
        status: str = "active",
        supersedes_id: str | None = None,
    ) -> MemoryModel:
        memory = MemoryModel(
            id=new_id(),
            content=content,
            content_hash=content_hash,
            category=category,
            memory_type=memory_type,
            source=source,
            source_ref=source_ref,
            relevance=relevance,
            status=status,
            supersedes_id=supersedes_id,
        )
        session.add(memory)
        session.flush()
        self.search_provider.index(session, memory.id, memory.content)
        return memory

    def update(self, session: Session, memory: MemoryModel, **fields) -> MemoryModel:  # noqa: ANN003
        for key, value in fields.items():
            setattr(memory, key, value)
        memory.updated_at = utcnow()
        session.flush()
        if "content" in fields:
            from app.database.models import content_hash as _hash

            memory.content_hash = _hash(memory.content)
            self.search_provider.index(session, memory.id, memory.content)
        return memory

    def get(self, session: Session, memory_id: str) -> MemoryModel | None:
        return session.get(MemoryModel, memory_id)

    def delete(self, session: Session, memory_id: str) -> bool:
        memory = self.get(session, memory_id)
        if memory is None:
            return False
        session.delete(memory)
        self.search_provider.remove(session, memory_id)
        session.flush()
        return True

    def list(
        self,
        session: Session,
        *,
        memory_type: str | None = None,
        category: str | None = None,
        status: str = "active",
        limit: int = 200,
    ) -> list[MemoryModel]:
        stmt = select(MemoryModel).order_by(MemoryModel.updated_at.desc()).limit(limit)
        if memory_type:
            stmt = stmt.where(MemoryModel.memory_type == memory_type)
        if category:
            stmt = stmt.where(MemoryModel.category == category)
        if status is not None:
            stmt = stmt.where(MemoryModel.status == status)
        return list(session.scalars(stmt))

    def count_by_status(self, session: Session) -> dict[str, int]:
        stmt = select(MemoryModel.status, func.count(MemoryModel.id)).group_by(
            MemoryModel.status
        )
        return {status: count for status, count in session.execute(stmt)}

    def count_by_type(self, session: Session) -> dict[str, int]:
        stmt = select(MemoryModel.memory_type, func.count(MemoryModel.id)).group_by(
            MemoryModel.memory_type
        )
        return {mtype: count for mtype, count in session.execute(stmt)}

    # --- Duplikate & Rangfolge -------------------------------------------------------
    def find_by_hash(self, session: Session, content_hash: str) -> MemoryModel | None:
        stmt = (
            select(MemoryModel)
            .where(MemoryModel.content_hash == content_hash)
            .where(MemoryModel.status == "active")
            .limit(1)
        )
        return session.scalars(stmt).first()

    def similar_active(
        self, session: Session, *, exclude_id: str | None = None
    ) -> list[MemoryModel]:
        """Aktive Erinnerungen für Ähnlichkeits-/Widerspruchsvergleiche."""
        stmt = select(MemoryModel).where(MemoryModel.status == "active")
        if exclude_id:
            stmt = stmt.where(MemoryModel.id != exclude_id)
        return list(session.scalars(stmt))

    def top_for_context(
        self,
        session: Session,
        *,
        types: tuple[str, ...] = ("preference", "long_term"),
        limit: int = 5,
    ) -> list[MemoryModel]:
        """Fallback-Auswahl: relevanteste aktive Erinnerungen (Typ gewichtet)."""
        stmt = (
            select(MemoryModel)
            .where(MemoryModel.status == "active")
            .where(MemoryModel.memory_type.in_(types))
            .order_by(MemoryModel.relevance.desc(), MemoryModel.updated_at.desc())
            .limit(limit)
        )
        return list(session.scalars(stmt))

    def touch_used(self, session: Session, memory_ids: list[str]) -> None:
        """Setzt ``last_used_at`` für im Kontext verwendete Erinnerungen."""
        if not memory_ids:
            return
        now = utcnow()
        session.execute(
            update(MemoryModel)
            .where(MemoryModel.id.in_(memory_ids))
            .values(last_used_at=now)
        )
        session.flush()

    def categories(self, session: Session) -> list[tuple[str, int]]:
        stmt = (
            select(MemoryModel.category, func.count(MemoryModel.id))
            .where(MemoryModel.status == "active")
            .group_by(MemoryModel.category)
            .order_by(func.count(MemoryModel.id).desc())
        )
        return [(cat, count) for cat, count in session.execute(stmt)]
