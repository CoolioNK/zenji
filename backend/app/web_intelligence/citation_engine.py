"""Citation Engine – Belege an Aussagen binden (Phase 3).

Grundsätze (Spezifikation §10):

- Jede Quellenangabe geht auf eine **tatsächlich abgerufene** Quelle zurück
  (IDs kommen vom Source Manager, nie vom Sprachmodell).
- ``[n]``-Marker werden validiert: Marker ohne zugeordnete Quelle werden
  entfernt und protokolliert (keine erfundenen Belege).
- Aussagen ohne ausreichenden Beleg bleiben **unmarkiert** und werden im
  Report als unbelegt sichtbar gemacht (nicht verworfen).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

_MARKER = re.compile(r"\[(\d{1,2})\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Belegbare Quelle (vom Source Manager, sortiert nach Marker)."""

    source_id: str
    title: str
    url: str
    domain: str = ""
    source_type: str = "unbekannt"

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class CitationReport:
    """Ergebnis der Zitat-Validierung."""

    cleaned_text: str
    used_markers: tuple[int, ...]
    citations: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    unsupported_sentences: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.warnings


class CitationEngine:
    """Validiert ``[n]``-Marker gegen tatsächlich abgerufene Quellen."""

    name = "citation_engine"

    def validate(
        self, answer: str, sources: Sequence[SourceRef]
    ) -> CitationReport:
        """Prüft die Antwort gegen die Quellenliste (Position = Marker).

        - Marker ``[n]`` mit ``1 <= n <= len(sources)`` → gültig, Satz wird
          als Zitat (Aussage + Quelle) registriert.
        - Marker ohne Quelle → **entfernt** + Warnung (nie erfundene Belege).
        - Sätze ganz ohne Marker → ``unsupported_sentences`` (sichtbar,
          nicht gelöscht).
        """
        max_marker = len(sources)
        warnings: list[str] = []
        citations: list[dict[str, Any]] = []
        unsupported: list[str] = []

        def _replace(match: re.Match[str]) -> str:
            number = int(match.group(1))
            if 1 <= number <= max_marker:
                return match.group(0)
            warnings.append(
                f"Marker [{number}] verweist auf keine abgerufene Quelle – entfernt."
            )
            return ""

        cleaned_parts: list[str] = []
        for sentence in _split_keep(answer or ""):
            filtered = _MARKER.sub(_replace, sentence)
            found = [int(m.group(1)) for m in _MARKER.finditer(filtered)]
            found = sorted(set(found))
            if found:
                for number in found:
                    source = sources[number - 1]
                    citations.append(
                        {
                            "marker": number,
                            "source_id": source.source_id,
                            "statement": _strip_markers(filtered),
                            "title": source.title,
                            "url": source.url,
                        }
                    )
            elif filtered.strip() and _is_substantive(filtered):
                unsupported.append(_strip_markers(filtered))
            cleaned_parts.append(filtered)

        cleaned = _rejoin(cleaned_parts)
        used = tuple(sorted({int(m.group(1)) for m in _MARKER.finditer(cleaned)}))
        return CitationReport(
            cleaned_text=cleaned,
            used_markers=used,
            citations=citations,
            warnings=warnings,
            unsupported_sentences=unsupported,
        )

    def sources_block(self, sources: Sequence[SourceRef]) -> str:
        """Quellenverzeichnis-Text (nur echte, abgerufene Quellen)."""
        lines = []
        for index, source in enumerate(sources, start=1):
            lines.append(f"[{index}] {source.title} — {source.url}")
        return "\n".join(lines)


def _split_keep(text: str) -> list[str]:
    """Satzweise zerlegen, Satzzeichen behalten (markerfreundlich)."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def _strip_markers(text: str) -> str:
    cleaned = _MARKER.sub("", text)
    return re.sub(r"\s+", " ", cleaned).strip()


def _is_substantive(sentence: str) -> bool:
    stripped = _strip_markers(sentence)
    return len(stripped) >= 20 and not stripped.endswith((":", "—", "-"))


def _rejoin(parts: list[str]) -> str:
    """Sätze wieder zusammenfügen (Leerzeichen zwischen Sätzen)."""
    joined = " ".join(part.strip() for part in parts if part.strip())
    return re.sub(r"\s+([\].,;:!?])", r"\1", joined).strip()


__all__ = ["CitationEngine", "CitationReport", "SourceRef"]
