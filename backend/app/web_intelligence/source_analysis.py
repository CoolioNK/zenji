"""Source Analysis Engine – Quellenbewertung & Widerspruchserkennung (Phase 3).

Bewusst **keine** erfundenen Vertrauenswerte: Die Engine liefert
nachvollziehbare Kriterien mit Begründungen:

- ``source_type``: Klassifikation nach Herkunft (Domain-/Pfad-Heuristik) mit
  ``type_reason`` – eine Klassifikation ist **keine** Wahrheitsbewertung.
- ``freshness``: Alter laut Veröffentlichungsdatum (Label, nicht Score).
- ``transparency``: Autor/Datum/Canonical vorhanden? (Label, nicht Score)
- ``relevance``: Begriffsüberdeckung zwischen Thema und Inhalt (0–1,
  deterministisch berechenbar).

Widersprüche werden erkannt, indem Aussagen mit Zahlen gruppiert werden:
Sätze mit gleichem Satzbild (Zahlen entfernt) aber unterschiedlichen
Zahlen gelten als Konflikt – transparent und nachvollziehbar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Iterable

#: Mindestalter-Grenzen (Tage) für Frische-Labels.
FRESH_DAYS_CURRENT = 90
FRESH_DAYS_OLD = 730

_DOMAIN_HINTS: tuple[tuple[str, str], ...] = (
    # Offizielle Primärquellen:
    ("arxiv.org", "wissenschaftlich"),
    ("nature.com", "wissenschaftlich"),
    ("science.org", "wissenschaftlich"),
    ("springer", "wissenschaftlich"),
    ("ieee.org", "wissenschaftlich"),
    ("acm.org", "wissenschaftlich"),
    ("pubmed", "wissenschaftlich"),
    ("ncbi.nlm", "wissenschaftlich"),
    ("doi.org", "wissenschaftlich"),
    ("jstor", "wissenschaftlich"),
    # Nachrichten:
    ("tagesschau.de", "nachrichten"),
    ("spiegel.de", "nachrichten"),
    ("zeit.de", "nachrichten"),
    ("faz.net", "nachrichten"),
    ("sueddeutsche.de", "nachrichten"),
    ("heise.de", "nachrichten"),
    ("golem.de", "nachrichten"),
    ("reuters.com", "nachrichten"),
    ("bbc.", "nachrichten"),
    ("guardian.com", "nachrichten"),
    ("nytimes.com", "nachrichten"),
    ("washingtonpost.com", "nachrichten"),
    ("ndr.de", "nachrichten"),
    ("zdf.de", "nachrichten"),
    ("ard.de", "nachrichten"),
    # Community:
    ("reddit.com", "community"),
    ("stackexchange.com", "community"),
    ("stackoverflow.com", "community"),
    ("news.ycombinator.com", "community"),
    ("github.com", "community"),
    ("wikipedia.org", "community"),
    ("forum", "community"),
    ("discourse", "community"),
    ("quora.com", "community"),
    ("mastodon", "community"),
)

_OFFICIAL_PATH_HINTS = ("docs", "documentation", "doku", "official", "handbuch", "referenz")
_OFFICIAL_DOMAIN_PARTS = (".gov", ".gov.", ".edu", ".mil", ".europa.eu", ".bund.de")

_OPINION_TEXT_HINTS = (
    "meiner meinung nach",
    "ich denke,",
    "ich finde,",
    "ich bin überzeugt",
    "meiner ansicht nach",
    "persönlich halte ich",
)


@dataclass(frozen=True, slots=True)
class NumericClaim:
    """Aussage mit Zahl (Quelle + Satz + Zahlenwerte)."""

    source_id: str
    text: str
    key: str
    numbers: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class Conflict:
    """Widerspruch: gleiches Satzbild, unterschiedliche Zahlen."""

    key: str
    statements: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SourceAssessment:
    """Nachvollziehbare Bewertung einer Quelle (Labels + Begründungen)."""

    source_type: str
    type_reason: str
    freshness_label: str
    age_days: int | None
    transparency_label: str
    transparency: dict[str, bool]
    relevance: float
    notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "type_reason": self.type_reason,
            "freshness_label": self.freshness_label,
            "age_days": self.age_days,
            "transparency_label": self.transparency_label,
            "transparency": dict(self.transparency),
            "relevance": round(self.relevance, 3),
            "notes": list(self.notes),
        }


class SourceAnalysisEngine:
    """Klassifiziert Quellen und findet widersprüchliche Aussagen."""

    name = "source_analysis"

    # --- Klassifikation ----------------------------------------------------------------

    def classify(self, url: str, *, content_text: str = "") -> tuple[str, str]:
        """Quelltyp + Begründung (Deterministisch, Domain-/Pfad-Heuristik)."""
        lowered_url = (url or "").lower()
        domain = _domain_of(lowered_url)

        for hint, source_type in _DOMAIN_HINTS:
            if hint in domain:
                return source_type, f"Domain '{domain}' ist als {source_type}-Quelle bekannt."

        if any(part in domain for part in _OFFICIAL_DOMAIN_PARTS):
            return "offiziell", f"Domain '{domain}' ist eine Behörden-/Bildungsdomain."

        if any(hint in lowered_url for hint in _OFFICIAL_PATH_HINTS):
            return "offiziell", "URL enthält Dokumentations-/Referenzpfad (Primärquelle)."

        if "/blog/" in lowered_url or "blog." in domain:
            return "meinung", "Blog-Struktur – persönlich geschriebener Beitrag."

        if content_text and any(hint in content_text.lower()[:2000] for hint in _OPINION_TEXT_HINTS):
            return "meinung", "Text enthält ausdrückliche Meinungsformulierung."

        return "unbekannt", "Herkunft nicht einordenbar – kein Known-Host, kein Muster."

    # --- Bewertung ------------------------------------------------------------------------

    def assess(
        self,
        *,
        url: str,
        title: str,
        content_text: str,
        topic: str,
        published_at: datetime | None,
        author: str | None,
        has_canonical: bool,
        now: datetime | None = None,
    ) -> SourceAssessment:
        """Nachvollziehbare Kriterien: Typ, Frische, Transparenz, Relevanz."""
        source_type, type_reason = self.classify(url, content_text=content_text)
        now = now or datetime.now(UTC)

        age_days: int | None = None
        if published_at is not None:
            age_days = max(0, (now - published_at).days)
            if age_days <= FRESH_DAYS_CURRENT:
                freshness = "aktuell"
            elif age_days <= FRESH_DAYS_OLD:
                freshness = "gealtert"
            else:
                freshness = "alt"
        else:
            freshness = "ohne Datum"

        transparency = {
            "author": bool(author),
            "date": published_at is not None,
            "canonical": has_canonical,
        }
        given = sum(1 for value in transparency.values() if value)
        transparency_label = "voll" if given == 3 else "teilweise" if given >= 1 else "gering"

        relevance = self.relevance(topic, content_text + " " + title)

        notes: list[str] = []
        if freshness == "ohne Datum":
            notes.append("Kein Veröffentlichungsdatum erkennbar – Aktualität unklar.")
        if transparency_label == "gering":
            notes.append("Wenig Transparenz (kein Autor, kein Datum).")
        if source_type in ("community", "meinung", "unbekannt"):
            notes.append(
                f"Klassifikation '{source_type}' – Aussagen ggf. ungeprüft; "
                "mit anderen Quellen abgleichen."
            )

        return SourceAssessment(
            source_type=source_type,
            type_reason=type_reason,
            freshness_label=freshness,
            age_days=age_days,
            transparency_label=transparency_label,
            transparency=transparency,
            relevance=relevance,
            notes=notes,
        )

    def relevance(self, topic: str, content_text: str) -> float:
        """Begriffsüberdeckung Thema↔Inhalt (0–1, deterministisch)."""
        topic_tokens = _tokens(topic)
        if not topic_tokens:
            return 0.0
        content_tokens = set(_tokens(content_text))
        overlap = sum(1 for token in topic_tokens if token in content_tokens)
        return overlap / len(topic_tokens)

    # --- Widerspruchserkennung -----------------------------------------------------------------

    def extract_claims(self, source_id: str, text: str) -> list[NumericClaim]:
        """Sätze mit Zahlen → strukturierte Aussagen (Satzbild als Schlüssel)."""
        claims: list[NumericClaim] = []
        for sentence in _sentences(text):
            numbers = _numbers_in(sentence)
            if not numbers:
                continue
            claims.append(
                NumericClaim(
                    source_id=source_id,
                    text=sentence,
                    key=_shape(sentence),
                    numbers=numbers,
                )
            )
        return claims

    def detect_conflicts(self, claims: Iterable[NumericClaim]) -> list[Conflict]:
        """Gleiches Satzbild + unterschiedliche Zahlen → Widerspruch."""
        grouped: dict[str, list[NumericClaim]] = {}
        for claim in claims:
            grouped.setdefault(claim.key, []).append(claim)

        conflicts: list[Conflict] = []
        for key, members in grouped.items():
            distinct = {member.numbers for member in members}
            if len(members) >= 2 and len(distinct) > 1:
                conflicts.append(
                    Conflict(
                        key=key,
                        statements=[
                            {
                                "source_id": member.source_id,
                                "text": member.text,
                                "numbers": list(member.numbers),
                            }
                            for member in members
                        ],
                    )
                )
        conflicts.sort(key=lambda c: len(c.statements), reverse=True)
        return conflicts


# --- Helfer (deterministisch) ----------------------------------------------------------------------


def _domain_of(url: str) -> str:
    from app.web_intelligence.search_engine import domain_of

    return domain_of(url or "")


def _tokens(text: str) -> list[str]:
    """Themen-/Inhalts-Token (klein, ohne Stopwörter, min. 3 Zeichen)."""
    from app.web_intelligence.research_planner import STOPWORDS

    words = re.findall(r"[\wäöüÄÖÜß-]+", (text or "").lower())
    return [w for w in words if len(w) >= 3 and w not in STOPWORDS]


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").replace("\n", " "))
    return [s.strip() for s in parts if len(s.strip()) >= 15]


def _numbers_in(sentence: str) -> tuple[float, ...]:
    values: list[float] = []
    for match in re.finditer(r"\d+(?:[.,]\d+)?", sentence):
        raw = match.group(0).replace(",", ".")
        try:
            values.append(float(raw))
        except ValueError:  # pragma: no cover – Regex garantiert parsebar
            continue
    return tuple(values)


def _shape(sentence: str) -> str:
    """Satzbild: Zahlen durch '#' ersetzt (Vergleichsschlüssel)."""
    shaped = re.sub(r"\d+(?:[.,]\d+)?", "#", sentence.lower())
    return re.sub(r"\s+", " ", shaped).strip(" .,;:!?")


__all__ = [
    "Conflict",
    "FRESH_DAYS_CURRENT",
    "FRESH_DAYS_OLD",
    "NumericClaim",
    "SourceAnalysisEngine",
    "SourceAssessment",
]
