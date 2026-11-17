"""Tests: Begleiter-Persönlichkeit (v0.3.0) – Seed, Migration 2→3, Persistenz.

Schwerpunkte:

- Zenji-Standardprofil mit den Spezifikationswerten (0–100 → 0–1).
- Migration 2→3 aktualisiert Systemregeln/-profile und respektiert Nutzerwahl.
- Persönlichkeit überlebt Neustarts und ist unabhängig vom Sprachmodell.
- Modi sind temporär und verändern niemals die dauerhafte Persönlichkeit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select, text, update

from app.core.config import DEFAULT_PERSONA, LEGACY_PERSONA, Settings
from app.database.database import Database
from app.database.migrations import LATEST_VERSION, run_migrations
from app.database.models import (
    PersonalityModel,
    PolicyModel,
    SchemaVersionModel,
    SettingModel,
)
import app.engines.personality_engine as personality_engine_module
from app.engines.communication_engine import CommunicationManager
from app.engines.context_engine import ContextEngine
from app.engines.llm_engine import LLMEngine
from app.engines.memory_engine import MemoryEngine
from app.engines.personality_engine import PersonalityEngine
from app.engines.policy_engine import PolicyEngine
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService
from app.services.conversation_service import ConversationService
from app.services.settings_service import SettingsService
from app.services.zenji_core import ZenjiCore
from tests.conftest import FAKE_REPLY, FakeProvider

#: Spezifikationswerte der Aufgabe (Skala 0–100 → 0–1).
SPEC_VALUES = {
    "humor": 0.45,
    "sarcasm": 0.1,
    "cheekiness": 0.15,
    "directness": 0.7,
    "friendliness": 0.95,
    "empathy": 0.85,
    "curiosity": 0.85,
    "initiative": 0.7,
}


@pytest.fixture()
def db(tmp_path):
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    database = Database(settings)
    database.create_schema()
    run_migrations(database.engine)
    return database


# --- Zenji-Standardprofil ---------------------------------------------------------------


def test_zenji_profil_hat_spezifikationswerte(db):
    with db.session() as session:
        zenji = session.scalars(
            select(PersonalityModel).where(PersonalityModel.name == "Zenji")
        ).first()
        assert zenji is not None
        assert zenji.is_system is True
        assert zenji.is_active is True
        for field, expected in SPEC_VALUES.items():
            assert getattr(zenji, field) == pytest.approx(expected), field


def test_alle_systemprofile_haben_neue_achsen(db):
    with db.session() as session:
        profiles = session.scalars(
            select(PersonalityModel).where(PersonalityModel.is_system.is_(True))
        ).all()
        assert len(profiles) == 5
        for profile in profiles:
            for field in SPEC_VALUES:
                value = getattr(profile, field)
                assert 0.0 <= value <= 1.0, (profile.name, field)
        # Abgestufte Charaktere statt einer Einheitsflotte:
        by_name = {p.name: p for p in profiles}
        assert by_name["Professional"].humor < by_name["Zenji"].humor
        assert by_name["Friendly"].sarcasm > by_name["Neutral"].sarcasm


def test_kompilierung_zeigt_neue_achsen(db):
    engine = PersonalityEngine()
    with db.session() as session:
        compiled = engine.compile_context(engine.require_active(session))
    assert "Humor: mittel" in compiled
    assert "Sarkasmus: sehr gering" in compiled
    assert "Frechheit: sehr gering" in compiled
    assert "Direktheit: stark" in compiled
    assert "Freundlichkeit: sehr stark" in compiled
    assert "Empathie: sehr stark" in compiled
    assert "Neugier: sehr stark" in compiled
    assert "Eigeninitiative: stark" in compiled


def test_kein_profil_hartcodiert_in_engine():
    """Die Engine enthält keine Zahlenwerte zur Persönlichkeit."""
    source = Path(personality_engine_module.__file__).resolve()
    text = source.read_text(encoding="utf-8")
    # Die Spezifikationswerte (0.9/0.65/0.75/0.95/…) dürfen nicht im Code stehen:
    for forbidden in ("0.65", "0.75", "0.95", "0.85"):
        assert forbidden not in text, forbidden


# --- Migration 2→3 --------------------------------------------------------------------------


def _simulate_phase2_state(db: Database) -> None:
    """Bringt eine v3-Datenbank auf den Phase-2-Stand (v2) zurück."""
    with db.session() as session:
        # Zenji-Profil und neue Regeln entfernen (existierten in v2 nicht):
        zenji = session.scalars(
            select(PersonalityModel).where(PersonalityModel.name == "Zenji")
        ).first()
        if zenji is not None:
            session.delete(zenji)
        for rule_id in ("communication_freedom", "independent_opinions"):
            rule = session.get(PolicyModel, rule_id)
            if rule is not None:
                session.delete(rule)
        # Alte Regeltexte (v0.2.0):
        session.get(PolicyModel, "zenji_identity").instruction = (
            "Du bist ZENJI, ein eigenständiges KI-System. Das Sprachmodell ist nur "
            "dein Generierungskern – Identität, Regeln und Kontext kommen aus ZENJI selbst."
        )
        session.get(PolicyModel, "honesty_first").instruction = (
            "Wenn du etwas nicht sicher weißt, sage es offen, statt zu spekulieren. "
            "Erfinde niemals Fakten, Quellen oder Zahlen."
        )
        # Neue Achsen auf ALTER-Defaults zurücksetzen:
        session.execute(
            update(PersonalityModel).values(
                sarcasm=0.0, cheekiness=0.0, friendliness=0.0,
                empathy=0.0, curiosity=0.0, initiative=0.0,
            )
        )
        # Phase-2-Standardaktivierung: Neutral aktiv statt Zenji:
        session.execute(update(PersonalityModel).values(is_active=False))
        neutral = session.scalars(
            select(PersonalityModel).where(PersonalityModel.name == "Neutral")
        ).first()
        neutral.is_active = True
        # v0.2.0-Standard-Identität in den Einstellungen speichert:
        session.add(
            SettingModel(
                key="persona",
                value=json.dumps({"system_prompt": LEGACY_PERSONA}, ensure_ascii=False),
            )
        )
        session.execute(text("PRAGMA user_version = 2"))
        meta = session.get(SchemaVersionModel, 1)
        meta.version = 2


def test_migration_2_zu_3_aktualisiert_und_aktiviert_zenji(tmp_path):
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings)
    db.create_schema()
    run_migrations(db.engine)
    _simulate_phase2_state(db)

    # Erneut migrieren (v2 → v3):
    assert run_migrations(db.engine) == LATEST_VERSION

    with db.session() as session:
        zenji = session.scalars(
            select(PersonalityModel).where(PersonalityModel.name == "Zenji")
        ).first()
        assert zenji is not None and zenji.is_active
        for field, expected in SPEC_VALUES.items():
            assert getattr(zenji, field) == pytest.approx(expected)
        # Systemregeltexte auf v0.3.0 aktualisiert:
        identity = session.get(PolicyModel, "zenji_identity")
        assert "Augenhöhe" in identity.instruction
        assert identity.priority == 100
        honesty = session.get(PolicyModel, "honesty_first")
        assert "Bewusstsein" in honesty.instruction
        # Neue Regeln vorhanden:
        assert session.get(PolicyModel, "communication_freedom") is not None
        assert session.get(PolicyModel, "independent_opinions") is not None
        # Gespeicherter Persona-Prompt wurde ersetzt:
        stored = session.get(SettingModel, "persona")
        assert json.loads(stored.value)["system_prompt"] == DEFAULT_PERSONA


def test_migration_respektiert_aktiviertes_nutzerprofil(tmp_path):
    """Ein bewusst gewähltes Profil wird von der Migration nicht überschrieben."""
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings)
    db.create_schema()
    run_migrations(db.engine)

    engine = PersonalityEngine()
    with db.session() as session:
        profile = engine.create(session, {"name": "Mein Sachlich", "humor": 0.1})
        engine.activate(session, profile.id)

    # Erzwinge Re-Migration (Version auf 2 zurück):
    with db.session() as session:
        session.execute(text("PRAGMA user_version = 2"))
        meta = session.get(SchemaVersionModel, 1)
        meta.version = 2
    run_migrations(db.engine)

    with db.session() as session:
        active = session.scalars(
            select(PersonalityModel).where(PersonalityModel.is_active.is_(True))
        ).first()
        assert active.name == "Mein Sachlich"


def test_migration_erhaelt_nutzerprofil_unberuehrt(tmp_path):
    """Nutzerprofile bekommen die neutralen ALTER-Defaults, keine Zenji-Werte."""
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings)
    db.create_schema()
    run_migrations(db.engine)

    engine = PersonalityEngine()
    with db.session() as session:
        profile = engine.create(session, {"name": "Eigenbrötler"})
        profile_id = profile.id

    # Migration erneut (z. B. nach Restore):
    with db.session() as session:
        session.execute(text("PRAGMA user_version = 2"))
        session.get(SchemaVersionModel, 1).version = 2
    run_migrations(db.engine)

    with db.session() as session:
        profile = session.get(PersonalityModel, profile_id)
        # Nicht überschrieben durch die Zenji-Werte:
        assert profile.sarcasm == pytest.approx(0.3)   # Create-Default
        assert profile.cheekiness == pytest.approx(0.4)
        assert profile.name == "Eigenbrötler"


def test_migration_respektiert_angepassten_persona_prompt(tmp_path):
    """Ein individuell geänderter Persona-Prompt wird niemals ersetzt."""
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings)
    db.create_schema()
    run_migrations(db.engine)

    custom = "Mein ganz eigener Prompt mit eigener Note."
    with db.session() as session:
        session.add(
            SettingModel(
                key="persona",
                value=json.dumps({"system_prompt": custom}, ensure_ascii=False),
            )
        )
        session.execute(text("PRAGMA user_version = 2"))
        session.get(SchemaVersionModel, 1).version = 2
    run_migrations(db.engine)

    with db.session() as session:
        stored = session.get(SettingModel, "persona")
        assert json.loads(stored.value)["system_prompt"] == custom


# --- Persistenz (Neustart) -----------------------------------------------------------------


def test_persoenlichkeit_ueberlebt_neustart(tmp_path):
    """Einstellungen sind in der DB: zweite Database-Instanz sieht dieselben Werte."""
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings)
    db.create_schema()
    run_migrations(db.engine)

    engine = PersonalityEngine()
    with db.session() as session:
        profile = engine.create(session, {"name": "Dauerhaft", "sarcasm": 0.8})
        engine.activate(session, profile.id)

    # „Neustart": komplett neue Instanzen auf derselben Datenbank:
    db2 = Database(settings)
    db2.create_schema()
    run_migrations(db2.engine)
    engine2 = PersonalityEngine()
    with db2.session() as session:
        active = engine2.require_active(session)
        assert active is not None
        assert active.name == "Dauerhaft"
        assert active.sarcasm == pytest.approx(0.8)
        zenji = session.scalars(
            select(PersonalityModel).where(PersonalityModel.name == "Zenji")
        ).first()
        assert zenji.humor == pytest.approx(0.45)  # Seed unverändert


# --- Modell-Unabhängigkeit -----------------------------------------------------------------


def _core_harness(settings: Settings, db: Database) -> ZenjiCore:
    core = ZenjiCore(
        settings_service=SettingsService(settings),
        conversation_service=ConversationService(),
        personality_engine=PersonalityEngine(),
        policy_engine=PolicyEngine(),
        memory_engine=MemoryEngine(),
        context_engine=ContextEngine(),
        communication_engine=CommunicationManager(),
    )
    with db.session() as session:
        MemoryEngine().init_search(session)
    return core


async def test_persoenlichkeit_unabhaengig_vom_modell(tmp_path):
    """Zweier Modelleinstellungen → identischer Persönlichkeits-/Kontextabschnitt."""
    settings_a = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings_a)
    db.create_schema()
    run_migrations(db.engine)

    personality = PersonalityEngine()
    with db.session() as session:
        active = personality.require_active(session)
        compiled = personality.compile_context(active)

    settings_b = Settings(
        _env_file=None, ssd_root=tmp_path, llm={"model": "llama3:1b"}  # type: ignore[arg-type]
    )
    with db.session() as session:
        compiled_again = personality.compile_context(personality.require_active(session))

    assert compiled == compiled_again
    assert "Name: Zenji" in compiled

    # Und auf Chat-Ebene: gleicher Systemprompt für beide Modelleinstellungen
    core_a = _core_harness(settings_a, db)
    core_b = _core_harness(settings_b, db)
    with db.session() as session:
        prepared_a = await core_a.prepare_turn(session, conversation_id=None, user_message="Hallo")
        prepared_b = await core_b.prepare_turn(session, conversation_id=None, user_message="Hallo")
    assert prepared_a.plan.system_text == prepared_b.plan.system_text


# --- Temporärer Modus vs. permanente Persönlichkeit ----------------------------------------


def _chat_harness(settings: Settings, db: Database) -> ChatService:
    provider = FakeProvider()
    memory = MemoryEngine()
    with db.session() as session:
        memory.init_search(session)
    core = ZenjiCore(
        settings_service=SettingsService(settings),
        conversation_service=ConversationService(),
        personality_engine=PersonalityEngine(),
        policy_engine=PolicyEngine(),
        memory_engine=memory,
        context_engine=ContextEngine(),
        communication_engine=CommunicationManager(),
    )
    return ChatService(
        database=db,
        engine=LLMEngine(provider),
        settings_service=SettingsService(settings),
        conversation_service=ConversationService(),
        core=core,
    )


async def test_roast_modus_veraendert_persoenlichkeit_nicht(tmp_path):
    """Ein temporärer Roast-Modus lässt die gespeicherten Profilwerte unberührt."""
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings)
    db.create_schema()
    run_migrations(db.engine)
    service = _chat_harness(settings, db)

    turn = await service.send_message(
        ChatRequest(message="Roaste mich mal richtig durch!", mode="roast")
    )
    assert turn.assistant_message.content == FAKE_REPLY

    with db.session() as session:
        zenji = session.scalars(
            select(PersonalityModel).where(PersonalityModel.name == "Zenji")
        ).first()
        for field, expected in SPEC_VALUES.items():
            assert getattr(zenji, field) == pytest.approx(expected), field


async def test_systemprompt_enthaelt_modus_und_persoenlichkeit_getrennt(tmp_path):
    """Der Modus-Abschnitt markiert sich selbst als temporär (abgetrennt vom Profil)."""
    settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
    db = Database(settings)
    db.create_schema()
    run_migrations(db.engine)
    service = _chat_harness(settings, db)

    await service.send_message(
        ChatRequest(message="Sei sarkastisch mit mir.", mode="roast")
    )
    provider = service._engine.provider  # öffentliche Property (Testzugriff)
    system = provider.chat_calls[-1]["messages"][0].content
    mode_pos = system.find("## Kommunikationsmodus")
    persona_pos = system.find("## Persönlichkeit")
    assert 0 < persona_pos < mode_pos  # Modus direkt hinter der Persönlichkeit
    assert "temporärer Modus" in system
    assert "Name: Zenji" in system
