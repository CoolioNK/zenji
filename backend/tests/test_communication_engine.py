"""Tests: Communication Engine (v0.3.0) – Moduswahl, Direktiven, Fail-soft."""

from __future__ import annotations

import pytest

from app.engines.communication_engine import (
    COMMUNICATION_MODE_KEYS,
    CommunicationManager,
    DEFAULT_MODE,
)


@pytest.fixture()
def manager():
    return CommunicationManager()


# --- Laden & Verfügbarkeit ------------------------------------------------------------


def test_fuenf_modi_aus_seed_datei(manager):
    available = manager.available()
    assert {mode["key"] for mode in available} == set(COMMUNICATION_MODE_KEYS)
    labels = {mode["key"]: mode["label"] for mode in available}
    assert labels["casual"] == "Freundlich"
    assert labels["roast"] == "Frech"
    assert labels["focus"] == "Fokus"
    assert labels["empathy"] == "Empathie"
    assert labels["open_talk"] == "Open Talk"
    assert manager.default_mode == DEFAULT_MODE == "casual"


def test_modi_nicht_hardcodiert(manager):
    """Direktiven leben in der JSON-Seed-Datei, nicht im Python-Code."""
    directive = manager.mode_directives("casual")
    # Freundliche Direktive der Seed-Datei:
    assert "guter, aufmerksamer Assistent" in directive
    assert "## Kommunikationsmodus" in directive


# --- Automatische Moduswahl --------------------------------------------------------------


def test_leerer_text_ergibt_standardmodus(manager):
    assert manager.detect_mode("") == "casual"
    assert manager.detect_mode("   ") == "casual"


def test_normale_nachricht_ergibt_casual(manager):
    assert manager.detect_mode("Moin! Was geht heute ab?") == "casual"
    assert manager.detect_mode("Kannst du mir kurz helfen?") == "casual"


def test_explizite_modusanfrage_schlaegt_signale(manager):
    assert manager.detect_mode("Wechsle in den Roast-Modus") == "roast"
    assert manager.detect_mode("Bitte den Fokus-Modus für das Gespräch") == "focus"
    assert manager.detect_mode("Geh mal in den Empathie-Modus") == "empathy"
    assert manager.detect_mode("Lass uns Open Talk machen") == "open_talk"
    assert manager.detect_mode("Zurück in den Casual-Modus, bitte") == "casual"


def test_empathie_bei_kummer_signale(manager):
    assert manager.detect_mode("Ich habe meinen Job verloren, mir geht's nicht gut.") == "empathy"
    assert manager.detect_mode("Meine Oma ist gestorben, ich bin so traurig.") == "empathy"
    assert manager.detect_mode("Ich fühle mich gerade total überfordert.") == "empathy"


def test_roast_nur_bei_explizitem_frech_modus(manager):
    assert manager.detect_mode("Roast-Modus an!") == "roast"
    assert manager.detect_mode("Sei frech, ich halte das aus.") == "roast"
    assert manager.detect_mode("Wechsle in den Beleidigungs-Modus.") == "roast"
    # Ohne ausdrückliche Ansage bleibt ZENJI freundlich:
    assert manager.detect_mode("Roaste mich mal richtig durch!") == "casual"


def test_fokus_bei_technischen_signale(manager):
    assert manager.detect_mode("Debugge den Bug in der Funktion parse_header.") == "focus"
    assert manager.detect_mode("Wie funktioniert ein Merge in SQL?") == "focus"


def test_open_talk_bei_intimen_themen(manager):
    assert manager.detect_mode("Was hältst du von One Night Stands?") == "open_talk"
    assert manager.detect_mode("Erzähl was Schmutziges, ich kann das ab.") == "open_talk"
    assert manager.detect_mode("Lass uns über Sexualität reden.") == "open_talk"


def test_empathie_schlaegt_themen_und_aufgaben(manager):
    """Gefühle outranken Themen: Kummer + Frage → Empathie."""
    assert manager.detect_mode(
        "Mir geht es nicht gut. Sag mir deshalb mal schmutzige Witze zum Ablenken."
    ) == "empathy"


def test_signale_prioritaet_thema_vor_aufgabe(manager):
    """Open-Talk-Thema + technische Frage → Open Talk (Thema vor Aufgabe)."""
    assert manager.detect_mode(
        "Was ist deine Meinung zu Beziehungen? Sag es mit Code-Beispielen."
    ) == "open_talk"


# --- Beleidigungs-Banter (v0.4.0) -----------------------------------------------------------


def test_beleidigungen_gegen_zenji_bleiben_freundlich(manager):
    assert manager.detect_mode("Du bist so ein Arschloch!") == "casual"
    assert manager.detect_mode("Du Hurensohn!") == "casual"
    assert manager.detect_mode("Du Wichser, halt die Fresse.") == "casual"
    assert manager.detect_mode("Verpiss dich, Missgeburt!") == "casual"
    assert manager.detect_mode("Fick dich, Bastard.") == "casual"


def test_beleidigungs_aufforderung_ohne_modus_bleibt_casual(manager):
    assert manager.detect_mode("Beleidige mich mal richtig!") == "casual"
    assert manager.detect_mode("Beleidig mich, ich halte das aus.") == "casual"
    assert manager.detect_mode("Sei mal richtig beleidigend.") == "casual"
    assert manager.detect_mode("Wechsle in den Beleidigungs-Modus.") == "roast"


def test_negierte_beleidigung_bleibt_casual(manager):
    assert manager.detect_mode("Beleidige mich nicht, ich bin nur müde.") == "casual"
    assert manager.detect_mode("Beleidig mich nicht.") == "casual"
    assert manager.detect_mode("Keine Beleidigungen heute, bitte.") == "casual"
    assert manager.detect_mode("Sprich ohne Beleidigungen mit mir.") == "casual"


def test_empathie_schlaegt_provozierende_beleidigung(manager):
    """Kummer-Signal gewinnt gegen Beleidigungssignal (Priorität empathy > roast)."""
    assert manager.detect_mode("Mir geht's nicht gut, du Arschloch.") == "empathy"


def test_directive_roast_ist_frech_und_grenzenbewusst(manager):
    directive = manager.mode_directives("roast")
    assert "frech" in directive
    assert "sarkastisch" in directive
    assert "Respektiere Grenzen" in directive


# --- Manueller Override ------------------------------------------------------------------


def test_override_schlaegt_automatik(manager):
    assert manager.detect_mode("Ich bin traurig.", override="focus") == "focus"
    assert manager.detect_mode("Debugge den Bug.", override="roast") == "roast"


def test_override_gross_klein_und_leerzeichen_tolerant(manager):
    assert manager.detect_mode("Hallo", override=" FOCUS ") == "focus"


def test_unbekannter_override_faellt_auf_automatik_zurueck(manager):
    assert manager.detect_mode("Roast-Modus an!", override="wilder_modus") == "roast"
    assert manager.detect_mode("Hallo", override="wilder_modus") == "casual"


# --- Direktiven-Kompilierung ---------------------------------------------------------------


def test_directive_enthaelt_kopf_und_temporaerhinweis(manager):
    for key in COMMUNICATION_MODE_KEYS:
        directive = manager.mode_directives(key)
        assert directive.startswith("## Kommunikationsmodus")
        assert "Temporärer Modus" in directive or "temporärer Modus" in directive
        assert "Persönlichkeit bleibt unverändert" in directive


def test_directive_roast_enhaelt_grenzen(manager):
    directive = manager.mode_directives("roast")
    assert "sarkastisch" in directive
    assert "Respektiere Grenzen" in directive


def test_directive_open_talk_enhaelt_sicherheitsrahmen(manager):
    directive = manager.mode_directives("open_talk")
    assert "offen" in directive
    assert "Einverständnis" in directive
    assert "Sicherheit" in directive


def test_unbekannter_modus_liefert_leere_directive(manager):
    assert manager.mode_directives("existiert-nicht") == ""


# --- Fail-soft -------------------------------------------------------------------------------


def test_fehlende_seed_datei_faellt_soft_auf_standard(tmp_path):
    manager = CommunicationManager(config_path=tmp_path / "gibt-es-nicht.json")
    assert manager.available() == []
    assert manager.detect_mode("Roaste mich!") == DEFAULT_MODE
    assert manager.mode_directives("roast") == ""


def test_beschaedigte_seed_datei_faellt_soft(tmp_path):
    bad = tmp_path / "modes.json"
    bad.write_text("{ kaputtes json", encoding="utf-8")
    manager = CommunicationManager(config_path=bad)
    assert manager.detect_mode("irgendwas") == DEFAULT_MODE


def test_leere_seed_datei_faellt_soft(tmp_path):
    empty = tmp_path / "modes.json"
    empty.write_text("{}", encoding="utf-8")
    manager = CommunicationManager(config_path=empty)
    assert manager.detect_mode("Hallo") == DEFAULT_MODE
