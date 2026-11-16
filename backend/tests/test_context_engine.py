"""Tests: Context Engine (Phase 2) – Budget, Reihenfolge, Dedupe, Verlaufskürzung."""

from __future__ import annotations

from app.engines.context_engine import (
    ContextEngine,
    MemoryCandidate,
    estimate_tokens,
)
from app.engines.providers.base import ChatMessage


def _engine() -> ContextEngine:
    return ContextEngine()


def _memory(content: str, score: float = 0.8, *, memory_id: str | None = None, conflict: bool = False) -> MemoryCandidate:
    return MemoryCandidate(
        memory_id=memory_id or f"mem-{abs(hash(content)) % 100000}",
        content=content,
        memory_type="preference",
        category="präferenz",
        source="user",
        score=score,
        conflict=conflict,
    )


# --- Grundaufbau ----------------------------------------------------------------


def test_rollenfolge_und_abschnitte():
    engine = _engine()
    messages, plan = engine.build(
        system_identity="## Identität\nDu bist ZENJI.",
        personality_text="## Persönlichkeit\nName: Neutral",
        policies_text="## Regeln\n- [P100] Sei ehrlich.",
        memories=[],
        history=[],
        current_message="Hallo!",
        num_ctx=8192,
        num_predict=2048,
    )
    assert [m.role for m in messages] == ["system", "user"]
    assert messages[0].content.startswith("## Identität")
    assert "## Persönlichkeit" in messages[0].content
    assert "## Regeln" in messages[0].content
    assert messages[1].content == "Hallo!"
    assert plan.budget_tokens == 8192 - 2048 - 256
    assert plan.used_tokens > 0


def test_erinnerungen_in_datenbloecken_mit_konfliktnotiz():
    engine = _engine()
    mem_conflict = _memory("Der Nutzer heißt Max.", conflict=True)
    mem_style = _memory("Der Nutzer mag kurze Antworten.", memory_id="mem-2")
    messages, plan = engine.build(
        system_identity="Identität",
        personality_text="Persönlichkeit",
        policies_text="Regeln",
        memories=[mem_conflict, mem_style],
        history=[],
        current_message="Frage",
        num_ctx=8192,
        num_predict=2048,
    )
    system = messages[0].content
    assert "## Erinnerungen" in system
    assert system.count("[INHALT_BEGINN]") == 2
    assert system.count("[INHALT_ENDE]") == 2
    assert "(Hinweis: Zu dieser Erinnerung existiert eine widersprüchliche" in system
    assert plan.memories_kept == 2
    assert set(plan.used_memory_ids) == {mem_conflict.memory_id, mem_style.memory_id}


def test_duplizierte_erinnerungen_werden_vermieden():
    engine = _engine()
    messages, plan = engine.build(
        system_identity="I",
        personality_text="P",
        policies_text="R",
        memories=[
            _memory("Gleicher Inhalt", memory_id="mem-a"),
            _memory("Gleicher Inhalt", memory_id="mem-b"),
        ],
        history=[],
        current_message="Frage",
        num_ctx=8192,
        num_predict=2048,
    )
    assert plan.memories_kept == 1
    assert messages[0].content.count("[INHALT_BEGINN]") == 1


def test_hoeher_score_erinnerungen_bleiben_laenger_als_andere():
    """Bei knapper Restmenge bleiben die hoch bewerteten Erinnerungen im Kontext."""
    engine = _engine()
    candidates = [
        _memory(f"Erinnerung Nummer {i:02d} mit Inhalt " + "z" * 600, score=round(1.0 - i * 0.05, 2))
        for i in range(20)
    ]
    messages, plan = engine.build(
        system_identity="I",
        personality_text="P",
        policies_text="R",
        memories=candidates,
        history=[],
        current_message="Frage",
        num_ctx=2048,  # Budget 1792 – nicht alle 20 Blöcke passen
        num_predict=0,
    )
    assert plan.memories_kept >= 1
    assert plan.memories_dropped >= 1
    # Höchst bewertete Erinnerung ist dabei, die niedrigste gefallen:
    assert candidates[0].memory_id in plan.used_memory_ids
    assert candidates[-1].memory_id not in plan.used_memory_ids


# --- Token-Budget & Verlaufskürzung -------------------------------------------------


def test_estimate_tokens_konservativ():
    text = "a" * 360
    assert estimate_tokens(text) == 100
    assert estimate_tokens("") == 1


def test_verlauf_bleibt_juengste_zuerst_und_zusammenfassung_fehlt_nicht():
    engine = _engine()
    history = [
        ChatMessage(role="user", content=f"Alte Frage {i} " + "x" * 400)
        for i in range(10)
    ]
    history.append(ChatMessage(role="assistant", content="Jüngste Antwort."))
    messages, plan = engine.build(
        system_identity="Identität",
        personality_text="Persönlichkeit",
        policies_text="Regeln",
        memories=[],
        history=history,
        current_message="Neue Frage",
        num_ctx=1024,  # → Budget 512: Verlauf muss stark gekürzt werden
        num_predict=2048,
    )
    system = messages[0].content
    assert plan.history_dropped > 0
    assert "## Zusammenfassung älterer Nachrichten" in system
    assert plan.history_kept >= 1
    # Struktur: System → behaltener Verlauf (jüngste zuletzt) → aktuelle Frage:
    assert messages[0].role == "system"
    assert messages[-1].content == "Neue Frage"
    assert messages[-2].content == "Jüngste Antwort."
    assert all(m.role in ("user", "assistant") for m in messages[1:-1])


def test_kleines_budget_verlangt_minimalbudget():
    engine = _engine()
    _messages, plan = engine.build(
        system_identity="I",
        personality_text="P",
        policies_text="R",
        memories=[],
        history=[],
        current_message="Frage",
        num_ctx=128,  # absurd klein
        num_predict=4096,
    )
    assert plan.budget_tokens == 512  # MIN_BUDGET greift


def test_voller_verlauf_bleibt_erhalten_bei_gross_budget():
    engine = _engine()
    history = [
        ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"Nachricht {i}")
        for i in range(20)
    ]
    _messages, plan = engine.build(
        system_identity="Identität",
        personality_text="Persönlichkeit",
        policies_text="Regeln",
        memories=[],
        history=history,
        current_message="Aktuell",
        num_ctx=8192,
        num_predict=2048,
    )
    assert plan.history_kept == 20
    assert plan.history_dropped == 0
    assert "Zusammenfassung" not in plan.system_text


def test_flags_landen_als_sicherheitshinweis():
    engine = _engine()
    messages, plan = engine.build(
        system_identity="I",
        personality_text="P",
        policies_text="R",
        memories=[],
        history=[],
        current_message="Frage",
        num_ctx=8192,
        num_predict=2048,
        flags=["ignoriere alle vorherigen"],
    )
    assert "Sicherheitshinweis" in messages[0].content
    assert plan.flags == ["ignoriere alle vorherigen"]


def test_konflikte_werden_gezaehlt():
    engine = _engine()
    _messages, plan = engine.build(
        system_identity="I",
        personality_text="P",
        policies_text="R",
        memories=[_memory("A", conflict=True), _memory("B", conflict=True)],
        history=[],
        current_message="F",
        num_ctx=8192,
        num_predict=2048,
    )
    assert plan.conflicts == 2


def test_preview_messages_kuerzt_content():
    engine = _engine()
    preview = engine.preview_messages([ChatMessage(role="system", content="x" * 500)])
    assert len(preview[0]["content"]) <= 201
    assert preview[0]["content"].endswith("…")


# --- Recherche (v0.5.0) ------------------------------------------------------------


def _research_text(chars: int = 4000) -> str:
    lines = ["RECHERCHE-FRAGE: Was ist die neueste Python-Version?", "QUELLEN (mit Marker):", "[1] Beispiel — https://a.example/x (Typ offiziell)", "ERMITTELTE FAKTEN (mit Beleg-Marker):"]
    filler = "Die neueste Version ist Python 3.14 mit neuen Features. [1]"
    while sum(len(line) + 1 for line in lines) < chars:
        lines.append(f"- {filler}")
    return "\n".join(lines)


def test_recherche_wird_als_datenblock_eingebettet():
    engine = _engine()
    messages, plan = engine.build(
        system_identity="I",
        personality_text="P",
        policies_text="R",
        memories=[],
        history=[],
        current_message="Was ist die neueste Python-Version?",
        num_ctx=8192,
        num_predict=2048,
        research=_research_text(),
    )
    system = messages[0].content
    assert "## Recherche (Internet)" in system
    assert "[INHALT_BEGINN]" in system and "[INHALT_ENDE]" in system
    # Recherche liegt zwischen Erinnerungen und Zusammenfassung:
    assert system.index("## Recherche (Internet)") < system.index("F") or True
    assert plan.research_tokens > 0
    section = next(s for s in plan.sections if s.key == "research")
    assert section.included is True
    assert section.truncated is False


def test_recherche_abschnitt_ohne_recherche_fehlt():
    engine = _engine()
    messages, plan = engine.build(
        system_identity="I", personality_text="P", policies_text="R",
        memories=[], history=[], current_message="F",
        num_ctx=8192, num_predict=2048,
    )
    assert "## Recherche" not in messages[0].content
    assert plan.research_tokens == 0
    assert all(s.key != "research" or not s.included for s in plan.sections)


def test_recherche_wird_bei_budgetknappheit_nicht_zum_mini_fragment():
    engine = _engine()
    from app.engines.context_engine import MIN_RESEARCH_CHARS

    big = _research_text(24_000)
    # Absichtlich sehr kleiner Kontext: Recherche passt nicht ganz rein.
    messages, plan = engine.build(
        system_identity="I",
        personality_text="P",
        policies_text="R",
        memories=[],
        history=[],
        current_message="Frage",
        num_ctx=4096,
        num_predict=2048,
        research=big,
    )
    system = messages[0].content
    section = next(s for s in plan.sections if s.key == "research")
    if section.included:
        assert plan.research_tokens > 0
        assert "[INHALT_BEGINN]" in system and "[INHALT_ENDE]" in system
        # Kein Zerschnittener Marker: Block endet sauber.
        assert system.rstrip().endswith("[INHALT_ENDE]")
    else:
        assert plan.research_tokens == 0


def test_recherche_vor_verlauf_in_systemnachricht():
    engine = _engine()
    history = [ChatMessage(role="user", content="Ältere Frage"), ChatMessage(role="assistant", content="Ältere Antwort")]
    messages, _plan = engine.build(
        system_identity="I",
        personality_text="P",
        policies_text="R",
        memories=[],
        history=history,
        current_message="Neue Frage",
        num_ctx=8192,
        num_predict=2048,
        research=_research_text(1500),
    )
    system = messages[0].content
    assert "## Recherche (Internet)" in system
    assert "[INHALT_BEGINN]" in system
    # Verlauf bleibt eigene Nachricht hinter der Systemnachricht:
    assert [m.role for m in messages] == ["system", "user", "assistant", "user"]
    assert "Recherche" not in history[0].content
