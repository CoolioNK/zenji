"""Tests: Kommunikationsmodi im Chat (v0.3.0) – repräsentative Gespräche.

Jeder Test führt eine realistische Nutzeranfrage durch den **echten
Chat-Pfad** (ChatService → ZenjiCore → ContextEngine) und prüft, welcher
Kontext dem Sprachmodell tatsächlich übergeben wird.  Da der FakeProvider
eine feste Antwort liefert, ist die Verifizierung auf Prompt-/Instruktionsebene
(siehe Limitationen im Entwicklungsbericht); das Live-Verhalten wurde
zusätzlich manuell gegen Qwen3 8B geprüft.

Abgedeckte Verhaltensziele der Spezifikation:
1 informal, 2 Kraftausdrücke, 3 Witze/Roasts, 4 intime Themen, 5 Widerspruch,
6 Moduswechsel, 9 ernste Situation → Empathie, 10 Bestand bleibt funktional.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.database.database import Database
from app.database.migrations import run_migrations
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
from tests.conftest import FAKE_REPLY, FakeProvider, parse_sse


class _Harness:
    """Vollständige Chat-Umgebung wie in Produktion (FakeProvider)."""

    def __init__(self, tmp_path) -> None:
        settings = Settings(_env_file=None, ssd_root=tmp_path)  # type: ignore[arg-type]
        self.db = Database(settings)
        self.db.create_schema()
        run_migrations(self.db.engine)
        self.provider = FakeProvider()
        self.memory = MemoryEngine()
        with self.db.session() as session:
            self.memory.init_search(session)
        self.core = ZenjiCore(
            settings_service=SettingsService(settings),
            conversation_service=ConversationService(),
            personality_engine=PersonalityEngine(),
            policy_engine=PolicyEngine(),
            memory_engine=self.memory,
            context_engine=ContextEngine(),
            communication_engine=CommunicationManager(),
        )
        self.service = ChatService(
            database=self.db,
            engine=LLMEngine(self.provider),
            settings_service=SettingsService(settings),
            conversation_service=ConversationService(),
            core=self.core,
        )

    async def chat(self, message: str, *, mode: str | None = None) -> str:
        request = ChatRequest(message=message) if mode is None else ChatRequest(
            message=message, mode=mode
        )
        turn = await self.service.send_message(request)
        return turn.conversation_id

    @property
    def last_system(self) -> str:
        return self.provider.chat_calls[-1]["messages"][0].content


@pytest.fixture()
def harness(tmp_path):
    return _Harness(tmp_path)


# --- Grundton: informell, humorvoll, kein Corporate-Sprech --------------------------


async def test_standard_modus_ist_casual_und_informell(harness):
    await harness.chat("Moin! Was geht bei dir heute so?")
    system = harness.last_system
    assert "## Kommunikationsmodus" in system
    assert "Casual" in system
    assert "locker, freundlich und humorvoll" in system
    assert "Kein Berichterton" in system
    # Persönlichkeit bleibt voll erhalten:
    assert "Name: Zenji" in system
    assert "Humor: sehr stark" in system


async def test_kraftausdruecke_und_schwarzer_humor_erlaubt(harness):
    await harness.chat("Du kannst ruhig Scheiße sagen, ich bin nicht aus Zucker.")
    system = harness.last_system
    # Systemregel communication_freedom gibt es freigegeben:
    assert "Kraftausdrücke" in system
    assert "schwarzer Humor" in system
    assert "Kein Corporate-Sprech" in system


async def test_jokes_und_roasts_sind_verankert(harness):
    await harness.chat("Erzähl mir einen richtig dummen Witz über Programmierer.")
    system = harness.last_system
    assert "freches Necken" in system  # Roast/Erlaubnis aus communication_freedom


# --- Intime & kontrovers Themen -----------------------------------------------------


async def test_intime_themen_oeffnen_open_talk(harness):
    await harness.chat("Darf ich dich was Persönliches fragen – was hältst du von One Night Stands?")
    system = harness.last_system
    assert "Open Talk" in system
    assert "ohne Ausweichen" in system
    # Sicherheitsrahmen bleibt immer sichtbar:
    assert "Einverständnis" in system
    assert "Sicherheit" in system


async def test_kontroverse_meinung_und_widerspruch_erlaubt(harness):
    await harness.chat("Sag mal ehrlich deine Meinung, ohne Rücksicht auf Verluste.")
    system = harness.last_system
    assert "eigene, begründete Meinungen" in system
    assert "Widersprich dem Nutzer" in system
    assert "Zustimmung nur zum Gefallen" in system


# --- Situationswechsel im Gespräch ----------------------------------------------------


async def test_ernte_kummer_loest_empathie_aus(harness):
    await harness.chat("Mir geht's heute wirklich dreckig, ich habe meinen Job verloren.")
    system = harness.last_system
    assert "Empathie" in system
    assert "höre zuerst zu" in system
    assert "nimm die Gefühle ernst" in system


async def test_technische_frage_loest_fokus_aus(harness):
    await harness.chat("Debugge den Bug in der Funktion: parse_header() wirft None.")
    system = harness.last_system
    assert "Fokus" in system
    assert "präzise" in system
    assert "konkrete Schritte" in system


async def test_moduswechsel_in_der_gleichen_konversation(harness):
    """Casual → Fokus → Roast: jede Nachricht bekommt ihren Modus, Profil bleibt."""
    conversation_id = await harness.chat("Hey, alles klar bei dir?")
    assert "Casual" in harness.last_system

    await harness.service.send_message(
        ChatRequest(
            conversation_id=conversation_id,
            message="Okay, jetzt konkret: Erkläre mir die SQL-Syntax von Fensterfunktionen.",
        )
    )
    assert "Fokus" in harness.last_system

    await harness.service.send_message(
        ChatRequest(
            conversation_id=conversation_id,
            message="Und jetzt Roast-Modus: wie schlecht war meine Syntaxfrage wirklich?",
        )
    )
    roast_system = harness.last_system
    assert "Roast" in roast_system
    assert "sarkastisch" in roast_system
    # Identität/Persönlichkeit in jeder Runde unverändert:
    assert "Name: Zenji" in roast_system
    assert "Humor: sehr stark" in roast_system


async def test_manueller_override_schlaegt_automatik(harness):
    """User sagt 'Roast-Modus an' zu einer traurigen Nachricht → Roast gewinnt."""
    await harness.chat("Mir geht's dreckig. Aber Roast-Modus an, dann lacht wenigstens einer.")
    assert "Roast" in harness.last_system


async def test_manuelles_mode_feld_im_request(harness):
    """ChatRequest.mode erzwingt den Modus unabhängig vom Nachrichtentext."""
    await harness.chat("Wie funktioniert ein Verbrennungsmotor?", mode="roast")
    system = harness.last_system
    assert "Roast" in system
    assert "sarkastisch" in system


def test_unbekannter_modus_wird_abgelehnt():
    with pytest.raises(Exception):
        ChatRequest(message="Hallo", mode="wilder-modus")


# --- Bestand bleibt funktional (Spezifikationspunkt 10) -----------------------------


async def test_chat_persistiert_und_gedaechtnis_bleibt(harness):
    conversation_id = await harness.chat("Merke dir: Ich arbeite an Projekt Fenris")
    with harness.db.session() as session:
        memories = harness.memory.list(session, status="active")
        assert len(memories) == 1
        assert memories[0].content == "Ich arbeite an Projekt Fenris"
        assert memories[0].memory_type == "project"

    # Erinnerung landet im Kontext des nächsten Turns (Datenblock!):
    await harness.service.send_message(
        ChatRequest(conversation_id=conversation_id, message="An welchem Projekt war das noch?")
    )
    system = harness.last_system
    assert "## Erinnerungen" in system
    assert "[INHALT_BEGINN]" in system
    assert "Ich arbeite an Projekt Fenris" in system
    # Und der Modus-Abschnitt ist trotzdem da:
    assert "## Kommunikationsmodus" in system


async def test_antwort_wird_gespeichert(harness):
    conversation_id = await harness.chat("Hallo ZENJI, alter Kumpel!")
    from sqlalchemy import select

    from app.database.models import ConversationModel, MessageModel

    with harness.db.session() as session:
        conversation = session.get(ConversationModel, conversation_id)
        assert conversation is not None
        messages = list(
            session.scalars(
                select(MessageModel).where(MessageModel.conversation_id == conversation_id)
            )
        )
        roles = [m.role for m in messages]
        assert roles == ["user", "assistant"]
        assert messages[1].content == FAKE_REPLY


# --- API-Ebene (echter Endpunkt) -------------------------------------------------------


async def test_api_chat_stream_mit_modus(client):
    http, _app = client
    response = await http.post(
        "/api/chat/stream",
        json={"message": "Roaste mich mal ordentlich!", "mode": "roast"},
    )
    assert response.status_code == 200
    events = parse_sse(response.content)
    assert events[0][0] == "start"
    assert events[-1][0] == "done"

    preview = await http.get(
        "/api/core/context-preview",
        params={"message": "Test", "mode": "open_talk"},
    )
    assert preview.status_code == 200
    assert preview.json()["mode"] == "open_talk"
    system_text = preview.json()["system_text"]
    assert "## Kommunikationsmodus" in system_text
    assert "Open Talk" in system_text


async def test_api_chat_stream_mit_unbekanntem_modus_422(client):
    http, _app = client
    response = await http.post(
        "/api/chat/stream", json={"message": "Hallo", "mode": "falscher-modus"}
    )
    assert response.status_code == 422
