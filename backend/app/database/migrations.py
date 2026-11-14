"""Datenbank-Migrationen und -Seeding für ZENJI.

Philosophie (siehe docs/DEVELOPMENT.md):

- Das Schema wird mit ``create_all`` idempotent angelegt – bestehende Tabellen
  und **alle Daten** bleiben unberührt, neue Tabellen kommen hinzu.
- ``PRAGMA user_version`` zählt die angewendete Migrationsstufe. Jede Stufe ist
  eine kleine, idempotente Funktion.
- Phase 2 ergänzt die Tabellen ``personalities``, ``policies``, ``memories``
  und ``schema_version`` sowie das Seeding der Standardprofile und
  Systemregeln aus JSON-Konfigurationsdateien (``backend/app/config/``).
- Seeding ist bewusst **additiv**: existierende Nutzerdaten werden niemals
  überschrieben oder gelöscht; fehlende Standardprofile/-regeln werden nur
  ergänzt.

Kein Alembic: ZENJI ist eine Single-File-SQLite-Anwendung mit wenigen,
kontrollierten Schemaänderungen.  Die Migrationsliste hier ist bewusst
transparent lesbar (Rückstand bewusst dokumentiert, siehe docs/ROADMAP.md).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.database.models import (
    MEMORY_TYPES,
    MEMORY_STATUSES,
    POLICY_SOURCES,
    POLICY_SCOPES,
    PERSONALITY_BASES,
    RESPONSE_LENGTHS,
    MemoryModel,
    PersonalityModel,
    PolicyModel,
    SchemaVersionModel,
    content_hash,
    new_id,
    normalize_content,
)

log = get_logger("migrations")

#: Migrationsdateien mit den Seed-Daten (kein Python-Hardcoding von Profilen).
CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
PERSONALITIES_FILE = CONFIG_DIR / "personalities.json"
POLICIES_FILE = CONFIG_DIR / "system_policies.json"

#: Aktuelle Schema-Stufe. Erhöhen, wenn eine neue Migration hinzukommt.
LATEST_VERSION = 2

# --- Migrationsstufen --------------------------------------------------------


def _migrate_1_to_2(session: Session) -> None:
    """Phase 2: Seed Persönlichkeitsprofile und System-/Beispielregeln.

    ``create_all`` hat die neuen Tabellen bereits angelegt (Schemaänderung =
    Tabellen *hinzufügen*, nichts verändern).  Hier werden nur fehlende
    Standardinhalte ergänzt.
    """
    _seed_personalities(session)
    _seed_policies(session)


MIGRATIONS: dict[int, Callable[[Session], None]] = {
    2: _migrate_1_to_2,
}


# --- Öffentliche API ----------------------------------------------------------


def current_version(engine: Engine) -> int:
    """Angewendete Migrationsstufe (0 = vor Phase 2, ohne Metadaten)."""
    with engine.connect() as conn:
        try:
            row = conn.execute(text("PRAGMA user_version")).scalar()
            return int(row or 0)
        except Exception:  # noqa: BLE001 – Statusabfrage darf nicht crashen
            return 0


def run_migrations(engine: Engine) -> int:
    """Bringt die Datenbank auf ``LATEST_VERSION`` (idempotent).

    ``create_all`` ist bereits vor dem Aufruf gelaufen (neue Tabellen existieren
    also schon); die Stufen kümmern sich um Datenmigration und Seeding.
    Rückgabe: erreichte Stufe.
    """
    version = current_version(engine)
    if version >= LATEST_VERSION:
        return version

    with Session(engine) as session:
        for target in sorted(MIGRATIONS):
            if target <= version:
                continue
            log.info("Migration %d → %d wird angewendet …", version, target)
            MIGRATIONS[target](session)
            _set_version(session, target)
            session.commit()
            version = target
            log.info("Migration auf Stufe %d abgeschlossen.", target)
    return version


def _set_version(session: Session, version: int) -> None:
    """Setzt ``PRAGMA user_version`` UND die Metadaten-Tabelle (doppelt festgehalten)."""
    session.execute(text(f"PRAGMA user_version = {int(version)}"))
    row = session.get(SchemaVersionModel, 1)
    if row is None:
        session.add(SchemaVersionModel(id=1, version=version))
    else:
        row.version = version


# --- Seeding -------------------------------------------------------------------


def _seed_personalities(session: Session, *, force_inactive: bool = False) -> None:
    """Legt Standardprofile aus ``personalities.json`` an, sofern Name fehlt."""
    profiles = _load_json(PERSONALITIES_FILE, "profiles")
    existing = {
        name for (name,) in session.execute(select(PersonalityModel.name)).all()
    }
    has_active = session.execute(
        select(PersonalityModel.id).where(PersonalityModel.is_active.is_(True)).limit(1)
    ).scalar() is not None

    created_count = 0
    created_any = False
    for index, entry in enumerate(profiles):
        name = str(entry.get("name", "")).strip()
        if not name or name in existing:
            continue
        profile = PersonalityModel(
            id=new_id(),
            name=name,
            identity=str(entry.get("identity", "")),
            base_personality=_pick(entry.get("base_personality"), PERSONALITY_BASES, "neutral"),
            communication_style=str(entry.get("communication_style", "")),
            formality=_clamp(entry.get("formality", 0.5)),
            humor=_clamp(entry.get("humor", 0.2)),
            directness=_clamp(entry.get("directness", 0.6)),
            creativity=_clamp(entry.get("creativity", 0.5)),
            response_length=_pick(entry.get("response_length"), RESPONSE_LENGTHS, "balanced"),
            language=str(entry.get("language", "auto")),
            situational_behavior=json.dumps(
                entry.get("situational_behavior", {}), ensure_ascii=False
            ),
            is_system=bool(entry.get("is_system", True)),
            # „Neutral" (erster Eintrag) wird Standardaktiv, wenn nichts aktiv ist.
            is_active=(not force_inactive and not has_active and index == 0),
        )
        session.add(profile)
        existing.add(name)
        created_any = True
        created_count += 1

    if created_any:
        session.flush()
        log.info("Persönlichkeitsprofile geseedet (%d neu).", created_count)


def _seed_policies(session: Session) -> None:
    """Legt Systemregeln + eine Beispiel-Nutzerregel aus JSON an, sofern ID fehlt."""
    rules = _load_json(POLICIES_FILE, "policies")
    existing = {pid for (pid,) in session.execute(select(PolicyModel.id)).all()}
    created = 0
    for entry in rules:
        policy_id = str(entry.get("id", "")).strip()
        if not policy_id or policy_id in existing:
            continue
        session.add(
            PolicyModel(
                id=policy_id,
                name=str(entry.get("name", policy_id)),
                instruction=str(entry.get("instruction", "")),
                priority=max(0, min(100, int(entry.get("priority", 50)))),
                enabled=bool(entry.get("enabled", True)),
                category=str(entry.get("category", "stil")),
                scope=_pick(entry.get("scope"), POLICY_SCOPES, "global"),
                source=_pick(entry.get("source"), POLICY_SOURCES, "user"),
            )
        )
        existing.add(policy_id)
        created += 1
    if created:
        session.flush()
        log.info("Regeln geseedet (%d neu).", created)


def seed_default_memories(session: Session) -> int:
    """Optionale Starterinnerungen – aktuell keine (nichts Erfinden).

    Bewusst leer: ZENJI erfindet keine Erinnerungen.  Die Funktion existiert,
    damit Phase 3 hier anknüpfen kann, ohne die Migration anzufassen.
    """
    return 0


# --- Hilfsfunktionen ------------------------------------------------------------


def _load_json(path: Path, key: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        items = data.get(key, [])
        return items if isinstance(items, list) else []
    except (OSError, ValueError) as exc:
        log.warning("Seed-Datei '%s' nicht lesbar (%s) – Seed übersprungen.", path, exc)
        return []


def _pick(value: Any, allowed: tuple[str, ...], default: str) -> str:
    as_str = str(value or "").strip().lower()
    return as_str if as_str in allowed else default


def _clamp(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


__all__ = [
    "LATEST_VERSION",
    "current_version",
    "run_migrations",
    "seed_default_memories",
    "normalize_content",
    "content_hash",
    "MEMORY_TYPES",
    "MEMORY_STATUSES",
]
