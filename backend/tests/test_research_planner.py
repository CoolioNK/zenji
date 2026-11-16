"""Tests: Research Planner (Phase 3) – Bedarf, Modi, Suchanfragen, Limits."""

from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.web_intelligence.research_planner import (
    MODE_LIMITS,
    ResearchPlan,
    ResearchPlanner,
    normalize_mode,
)


@pytest.fixture()
def planner():
    return ResearchPlanner()


# --- Bedarfserkennung (Spezifikationsbeispiele) ---------------------------------------


def test_konzeptfrage_braucht_keine_recherche(planner):
    assert planner.needs_research("Wie funktioniert ein Transformer-Modell?") is False
    assert planner.needs_research("Erkläre mir Rekursion in Python.") is False
    assert planner.needs_research("Moin!") is False


def test_frischefrage_braucht_recherche(planner):
    assert planner.needs_research("Was ist die neueste Version von Python?") is True
    assert planner.needs_research("Was sind aktuell die besten lokalen KI-Modelle für einen Mac mit 16 GB RAM?") is True
    assert planner.needs_research("Wie ist heute das Wetter in Berlin?") is True


def test_vergleich_und_aktuell_braucht_recherche(planner):
    assert planner.needs_research("Vergleiche die aktuell besten KI-Modelle für meinen Mac.") is True


def test_ausdrueckliche_aufforderung_recherchiert_immer(planner):
    assert planner.needs_research("Recherchiere mal die Fakten zu Kernkraft.") is True
    assert planner.needs_research("Such im Internet nach dem Preis von X.") is True


def test_jahresangabe_plus_frischesignal(planner):
    assert planner.needs_research("Welches Modell lohnt sich 2026?") is True


# --- Moduswahl ------------------------------------------------------------------------


def test_automatik_quick_bei_einfacher_frischefrage(planner):
    assert planner.choose_mode("Was ist die neueste Version von Python?") == "quick"


def test_automatik_standard_bei_vergleich(planner):
    assert planner.choose_mode(
        "Vergleiche die aktuell besten KI-Modelle für meinen Mac."
    ) == "standard"


def test_automatik_deep_bei_ausdruecklicher_umfangsfrage(planner):
    assert planner.choose_mode("Mach eine ausführliche Recherche zu Kernkraft.") == "deep"


def test_manueller_override_schlaegt_automatik(planner):
    assert planner.choose_mode("Moin", override="deep") == "deep"
    assert planner.choose_mode("Was ist aktuell?", override="quick") == "quick"


def test_unbekannter_override_abgelehnt(planner):
    with pytest.raises(ValidationError):
        planner.choose_mode("Hallo", override="wilder-modus")


def test_normalize_mode_variante_und_off():
    assert normalize_mode(None) == ""
    assert normalize_mode("Auto") == ""
    assert normalize_mode("off") == "off"
    assert normalize_mode("Quick-Search") == "quick"
    assert normalize_mode("DEEP") == "deep"
    with pytest.raises(ValidationError):
        normalize_mode("mega")


# --- Suchanfragen-Generierung -----------------------------------------------------------


def test_quick_hat_genau_eine_anfrage(planner):
    plan = planner.build_plan("Was ist die neueste Version von Python?", mode="quick")
    assert plan.queries == ["neueste version python"]


def test_standard_erzeugt_mehrere_varianten(planner):
    plan = planner.build_plan(
        "Was sind aktuell die besten lokalen KI-Modelle für einen Mac mit 16 GB RAM?",
        mode="standard",
    )
    assert 2 <= len(plan.queries) <= MODE_LIMITS["standard"].max_queries
    assert any("2026" in query for query in plan.queries)
    assert any("vergleich" in query for query in plan.queries)


def test_deep_erzeugt_umfangreichste_menge(planner):
    plan = planner.build_plan("Vergleiche die aktuellen LLM-Modelle.", mode="deep")
    assert len(plan.queries) >= 3
    assert len(plan.queries) <= MODE_LIMITS["deep"].max_queries


def test_anfragen_sind_dedupliziert(planner):
    plan = planner.build_plan("Neueste Version von Python?", mode="deep")
    assert len(plan.queries) == len(set(plan.queries))


# --- Limits & Struktur ------------------------------------------------------------------


def test_limit_kaskade_ist_monoton(planner):
    assert (
        MODE_LIMITS["quick"].max_queries
        < MODE_LIMITS["standard"].max_queries
        <= MODE_LIMITS["deep"].max_queries
    )
    assert (
        MODE_LIMITS["quick"].max_sources
        < MODE_LIMITS["standard"].max_sources
        <= MODE_LIMITS["deep"].max_sources
    )
    # Endlosschleifen unmöglich: Zeitbudget und Zyklen sind endlich
    assert MODE_LIMITS["deep"].max_follow_up_cycles <= 2
    assert MODE_LIMITS["deep"].max_time_s <= 120


def test_plan_ist_strukturiert_nicht_freiext(planner):
    plan = planner.build_plan("Was ist aktuell der Stand von WASM?", force=True)
    assert isinstance(plan, ResearchPlan)
    data = plan.as_dict()
    assert data["mode"] in ("quick", "standard", "deep")
    assert isinstance(data["queries"], list) and data["queries"]
    assert set(data["limits"]) == {
        "max_queries", "max_sources", "max_follow_up_cycles",
        "max_total_chars", "max_time_s",
    }
    assert isinstance(data["needs_research"], bool)
    assert data["reason"]


def test_force_ueberspringt_bedarf(planner):
    plan = planner.build_plan("Wie funktioniert ein Transformer-Modell?", force=True)
    assert plan.needs_research is True


def test_ohne_force_keine_recherche_bei_konzept(planner):
    plan = planner.build_plan("Wie funktioniert ein Transformer-Modell?")
    assert plan.needs_research is False
    # Trotzdem gibt es einen gültigen Plan (Engine läuft nicht ohne Grund):
    assert plan.mode in ("quick", "standard", "deep")


def test_leere_anfrage_abgelehnt(planner):
    with pytest.raises(ValidationError):
        planner.build_plan("   ")
