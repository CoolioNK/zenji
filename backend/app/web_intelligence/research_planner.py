"""Research Planner – strukturierte Rechercheplanung (Phase 3).

Der Planner entscheidet **deterministisch** (kein LLM, offline testbar):

1. Ob eine Webrecherche sinnvoll ist (Bedarfsheuristik) oder die normale
   Antwort ohne Recherche ausreicht.
2. Welcher Recherchemodus passt (Quick Search / Standard Research /
   Deep Research) – manuelle Anfrage schlägt Automatik.
3. Welche konkreten Suchanfragen ausgeführt werden (mehrere Varianten,
   abhängig vom Modus).
4. Welche harten Limits gelten (Anfragen, Quellen, Nachforsch-Zyklen,
   Zeit, Textmenge).

Rückgabe ist immer **strukturiert** (:class:`ResearchPlan`), niemals
uncontrollierter Freitext.  Unendliche Recherche-Schleifen sind
ausgeschlossen: Nachforsch-Zyklen sind pro Modus limitiert und die
Research Engine prüft zusätzlich Gesamtzeit/Gesamtanzahl.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.exceptions import ValidationError

RESEARCH_MODES = ("quick", "standard", "deep")

#: Ausdrückliche Recherche-Aufforderungen (immer recherchieren).
EXPLICIT_SIGNALS = (
    "recherchiere",
    "recherche",
    "recherchier",
    "such im internet",
    "suche im internet",
    "such im web",
    "suche im web",
    "googele",
    "google mal",
    "googel mal",
    "websuche",
    "web-suche",
    "im internet finden",
    "mit quellen",
    "mit belegen",
    "such das raus",
    "finde raus",
)

#: Frische-/Aktualitätssignale: die Antwort braucht aktuelle Informationen.
FRESHNESS_SIGNALS = (
    "aktuell",
    "aktuelle",
    "aktuelles",
    "aktuellste",
    "neueste",
    "neuesten",
    "neuste",
    "neusten",
    "heute",
    "gerade jetzt",
    "zurzeit",
    "momentan",
    "im moment",
    "letzt",
    "grade eben",
    "news",
    "nachrichten",
    "kurs",
    "aktienkurs",
    "wetter",
    "umfrage",
    "ergebnis",
    "ergebnisse",
    "ergebnissen",
    "wahlen",
    "wahl",
    "premiere",
    "release",
    "version",
    "update",
    "preis",
    "preise",
    "kostet",
)

#: Vergleichssignale (mit Frische-Signal zusammen → Standard/Deep).
COMPARISON_SIGNALS = (
    "vergleiche",
    "vergleich",
    "vergleichst",
    "im vergleich",
    "beste",
    "besten",
    "bestes",
    "empfehlung",
    "empfehlungen",
    "welche ist besser",
    "was ist besser",
    "empfiehlst",
)

#: Signale für besonders umfassende Recherche (→ Deep Research).
DEEP_SIGNALS = (
    "deep research",
    "ausführlich",
    "umfassend",
    "ausführliche",
    "umfassende",
    "genau recherchieren",
    "alle quellen",
    "detailliert",
    "gründlich",
    "gründliche",
)

#: Force-Signale im Text, die auch bei Konzeptfragen recherchieren.
#: (bewusst Teil von EXPLICIT_SIGNALS – hier keine zusätzliche Liste.)

#: Frage-/Füllwörter, die aus dem Suchbegriff herausgefiltert werden.
STOPWORDS = frozenset(
    {
        "was", "welche", "welcher", "welches", "wie", "warum", "wieso", "weshalb",
        "ist", "sind", "seid", "gibt", "es", "kannst", "kann", "du", "mir", "mich",
        "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen", "einer",
        "eines", "für", "mit", "und", "oder", "aber", "von", "vom", "im", "in",
        "auf", "um", "zu", "zum", "zur", "beim", "bei", "am", "an", "aus", "als",
        "bitte", "mal", "eigentlich", "denn", "so", "sich", "werden", "wird",
        "haben", "hat", "hast", "habe", "mein", "meine", "dein", "deine", "derzeit",
        "man", "nicht", "jetzt", "noch", "schon", "sehr", "denn", "etwas", "was",
    }
)

_YEAR = re.compile(r"\b(20[2-9]\d)\b")
_QUESTION_MARK = re.compile(r"[?!.,;:]+$")


@dataclass(frozen=True, slots=True)
class ResearchLimits:
    """Harte Grenzen eines Recherchemodus (keine Endlosschleifen möglich)."""

    max_queries: int
    max_sources: int
    max_follow_up_cycles: int
    max_total_chars: int
    max_time_s: float


@dataclass(frozen=True, slots=True)
class ResearchPlan:
    """Strukturierter Rechercheplan (Eingabe der Research Engine)."""

    question: str
    mode: str
    queries: list[str]
    limits: ResearchLimits
    needs_research: bool
    reason: str = ""
    topic: str = ""

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "mode": self.mode,
            "queries": list(self.queries),
            "limits": {
                "max_queries": self.limits.max_queries,
                "max_sources": self.limits.max_sources,
                "max_follow_up_cycles": self.limits.max_follow_up_cycles,
                "max_total_chars": self.limits.max_total_chars,
                "max_time_s": self.limits.max_time_s,
            },
            "needs_research": self.needs_research,
            "reason": self.reason,
            "topic": self.topic,
        }


#: Modus-Limits (Basiswerte; Einstellungen können sie pro Lauf weiter senken).
MODE_LIMITS: dict[str, ResearchLimits] = {
    "quick": ResearchLimits(
        max_queries=1, max_sources=3, max_follow_up_cycles=0,
        max_total_chars=12_000, max_time_s=20.0,
    ),
    "standard": ResearchLimits(
        max_queries=3, max_sources=6, max_follow_up_cycles=1,
        max_total_chars=40_000, max_time_s=60.0,
    ),
    "deep": ResearchLimits(
        max_queries=5, max_sources=10, max_follow_up_cycles=2,
        max_total_chars=90_000, max_time_s=120.0,
    ),
}

MODE_LABELS = {
    "quick": "Quick Search",
    "standard": "Standard Research",
    "deep": "Deep Research",
}


def normalize_mode(mode: str | None) -> str:
    """Modusangabe normalisieren; Unbekannter/leerer Modus → Fehlerfreiheit."""
    value = (mode or "").strip().lower().replace("-", "_").replace(" ", "_")
    if value in ("", "auto", "none", "null", "default"):
        return ""
    if value in ("off", "aus", "no", "false"):
        return "off"
    if value in RESEARCH_MODES:
        return value
    if value in ("quick_search", "schnell"):
        return "quick"
    if value in ("standard_research", "normal"):
        return "standard"
    if value in ("deep_research", "tief"):
        return "deep"
    raise ValidationError(
        f"Unbekannter Recherchemodus '{mode}'. Erlaubt: auto|off|{RESEARCH_MODES}."
    )


class ResearchPlanner:
    """Erzeugt strukturierte Recherchepläne aus Nutzerfragen."""

    name = "research_planner"

    # --- Bedarfserkennung ------------------------------------------------------

    def needs_research(self, text: str) -> bool:
        """True, wenn die Anfrage von aktuellen/webspezifischen Infos profitiert.

        Konzeptfragen („Wie funktioniert ein Transformer?") bleiben ohne
        Recherche; Frische-/Vergleichssignale und ausdrückliche Aufforderungen
        lösen sie aus.  Regen-Ausschluss: sehr kurze oder reine Smalltalk-
        Nachrichten werden nie recherchiert.
        """
        cleaned = (text or "").strip().lower()
        if len(cleaned) < 4:
            return False
        if any(signal in cleaned for signal in EXPLICIT_SIGNALS):
            return True
        fresh = any(signal in cleaned for signal in FRESHNESS_SIGNALS)
        compare = any(signal in cleaned for signal in COMPARISON_SIGNALS)
        if fresh and compare:
            return True
        # Jahresangabe allein ist ein starkes Frischesignal (Zeitbezug):
        if _YEAR.search(cleaned):
            return True
        # Einzelne Frische-Signale wie „version" allein genügen, wenn die
        # Frage nach einem konkreten Stand fragt („neueste", „aktuell"):
        strong_fresh = any(
            signal in cleaned
            for signal in ("aktuell", "neueste", "neuste", "heute", "zurzeit", "momentan")
        )
        return strong_fresh

    def choose_mode(self, text: str, *, override: str | None = None) -> str:
        """Modus wählen: manuelle Anfrage schlägt Automatik; Ungültiges → Fehler."""
        forced = normalize_mode(override)
        if forced in ("", "off"):
            # off wird vom Core separat behandelt; hier nur Automatik:
            return self._auto_mode(text)
        return forced

    def _auto_mode(self, text: str) -> str:
        cleaned = (text or "").lower()
        if any(signal in cleaned for signal in DEEP_SIGNALS):
            return "deep"
        if any(signal in cleaned for signal in COMPARISON_SIGNALS) and any(
            signal in cleaned for signal in FRESHNESS_SIGNALS
        ):
            return "standard"
        # Ausdrückliche Aufforderung ohne Vergleich → Standard:
        if any(signal in cleaned for signal in EXPLICIT_SIGNALS):
            return "standard"
        return "quick"

    # --- Suchanfragen-Generierung ------------------------------------------------

    def extract_topic(self, text: str) -> str:
        """Kernthema der Frage (Stopwörter entfernt, max. 8 Begriffe)."""
        words = re.findall(r"[\wäöüÄÖÜß.+-]+", text or "", re.UNICODE)
        kept: list[str] = []
        for word in words:
            token = word.strip(_QUESTION_MARK.pattern or "?!.,;:").lower()
            if not token or token in STOPWORDS or token.isdigit():
                continue
            kept.append(token)
            if len(kept) >= 8:
                break
        return " ".join(kept)

    def build_queries(self, question: str, mode: str) -> list[str]:
        """Konkrete Suchanfragen je Modus (deterministische Varianten)."""
        topic = self.extract_topic(question)
        if not topic:
            topic = (question or "").strip()[:80].lower()
        cleaned_question = (question or "").strip().rstrip("?!.")
        cleaned_question = cleaned_question[0].lower() + cleaned_question[1:] if cleaned_question else topic
        year = _YEAR.search(question)
        year_token = year.group(1) if year else "2026"

        queries: list[str] = []
        if mode == "quick":
            queries.append(topic)
        elif mode == "standard":
            queries.append(topic)
            queries.append(f"{topic} {year_token}")
            if self._mentions_comparison(question):
                queries.append(f"vergleich {topic}")
        else:  # deep
            queries.append(topic)
            queries.append(f"{topic} {year_token}")
            queries.append(f"vergleich {topic}")
            if self._mentions_comparison(question):
                queries.append(f"beste {topic} empfehlung")
            else:
                queries.append(f"{topic} erfahrungen")
            queries.append(f"{topic} foren meinungen")
        # Dedupe + Begrenzung auf Moduslimit:
        limit = MODE_LIMITS[mode].max_queries
        unique: list[str] = []
        for query in queries:
            normalized = " ".join(query.split())
            if normalized and normalized not in unique:
                unique.append(normalized)
            if len(unique) >= limit:
                break
        return unique

    def _mentions_comparison(self, text: str) -> bool:
        cleaned = (text or "").lower()
        return any(signal in cleaned for signal in COMPARISON_SIGNALS)

    # --- Plan ------------------------------------------------------------------

    def build_plan(
        self,
        question: str,
        *,
        mode: str | None = None,
        force: bool = False,
    ) -> ResearchPlan:
        """Vollständiger, strukturierter Rechercheplan.

        ``mode=None`` → Automatik (Bedarfsheuristik + Moduswahl).
        ``force=True`` übergeht die Bedarfsheuristik (manuelle Recherche).
        """
        cleaned = (question or "").strip()
        if not cleaned:
            raise ValidationError("Rechercheanfrage darf nicht leer sein.")
        resolved_mode = self.choose_mode(cleaned, override=mode)
        limits = MODE_LIMITS[resolved_mode]
        needs = force or self.needs_research(cleaned)
        reason = self._explain(cleaned, needs)
        return ResearchPlan(
            question=cleaned,
            mode=resolved_mode,
            queries=self.build_queries(cleaned, resolved_mode),
            limits=limits,
            needs_research=needs,
            reason=reason,
            topic=self.extract_topic(cleaned),
        )

    def _explain(self, cleaned: str, needs: bool) -> str:
        if not needs:
            return (
                "Keine Aktualitäts-/Vergleichssignale – normale Antwort ohne "
                "Webrecherche genügt."
            )
        if any(signal in cleaned for signal in EXPLICIT_SIGNALS):
            return "Ausdrückliche Recherche-Aufforderung erkannt."
        if any(signal in cleaned for signal in DEEP_SIGNALS):
            return "Umfassende Recherche ausdrücklich gewünscht."
        if any(signal in cleaned for signal in COMPARISON_SIGNALS):
            return "Vergleichsfrage mit Aktualitätsbezug."
        return "Aktualitäts-/Frischesignal erkannt."


__all__ = [
    "MODE_LABELS",
    "MODE_LIMITS",
    "RESEARCH_MODES",
    "ResearchLimits",
    "ResearchPlan",
    "ResearchPlanner",
    "normalize_mode",
]
